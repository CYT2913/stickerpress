"""合规策略的加载与查询。

策略本体在 ``policy.yaml``，本模块只负责把它变成可编程访问的对象，
并提供"给定风险类目 → 该怎么处置"的判定入口。
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Dict, List, Optional

import yaml

POLICY_PATH = Path(__file__).with_name("policy.yaml")


class Action(str, Enum):
    """处置动作，按严厉程度排序（越靠后越严）。"""

    PASS = "pass"
    MITIGATE = "mitigate"
    REVIEW = "review"
    BLOCK = "block"

    @property
    def rank(self) -> int:
        return {"pass": 0, "mitigate": 1, "review": 2, "block": 3}[self.value]

    @staticmethod
    def strictest(actions) -> "Action":
        acts = [a for a in actions]
        if not acts:
            return Action.PASS
        return max(acts, key=lambda a: a.rank)


class Gate(str, Enum):
    INGEST = "ingest"          # 闸1 入料：用户上传的原始照片
    GENERATION = "generation"  # 闸2 生成：提示词与用户文案
    EGRESS = "egress"          # 闸3 出料：生成后的贴纸与最终版面


@dataclass
class Category:
    code: str
    key: str
    name: str
    group: str
    severity: str
    action: Action
    gates: List[Gate]
    rationale: str = ""
    remediation: str = ""
    #: 给审核模型的判定口径细则，用于压低误报（precision 调优的抓手）
    judging_note: str = ""
    mitigation: Optional[str] = None

    def applies_to(self, gate: Gate) -> bool:
        return gate in self.gates


@dataclass
class QualityThresholds:
    min_effective_dpi: int = 300
    min_sticker_area_ratio: float = 0.25
    max_sticker_area_ratio: float = 0.98
    min_knife_gap_mm: float = 3.0
    min_alpha_components: int = 1
    required_sticker_count: int = 6


@dataclass
class Policy:
    policy_version: str
    updated_at: str
    owner: str
    fail_mode: str
    gates_enabled: Dict[str, dict]
    categories: List[Category]
    guardrails_positive: List[str]
    guardrails_negative: List[str]
    keyword_blocklist: List[str]
    quality: QualityThresholds
    raw_digest: str = ""

    # -- 查询接口 ----------------------------------------------------------
    _by_key: Dict[str, Category] = field(default_factory=dict, repr=False)

    def __post_init__(self) -> None:
        self._by_key = {c.key: c for c in self.categories}

    def category(self, key: str) -> Optional[Category]:
        return self._by_key.get(key)

    def categories_for(self, gate: Gate) -> List[Category]:
        return [c for c in self.categories if c.applies_to(gate)]

    def gate_enabled(self, gate: Gate) -> bool:
        return bool(self.gates_enabled.get(gate.value, {}).get("enabled", True))

    def gate_uses_vlm(self, gate: Gate) -> bool:
        return bool(self.gates_enabled.get(gate.value, {}).get("vlm_review", False))

    def negative_prompt(self) -> str:
        return ", ".join(self.guardrails_negative)

    def positive_prompt(self) -> str:
        return ", ".join(self.guardrails_positive)

    def hit_keywords(self, text: str) -> List[str]:
        if not text:
            return []
        return [kw for kw in self.keyword_blocklist if kw and kw in text]

    def fingerprint(self) -> str:
        """策略指纹：版本号 + 内容摘要，印在成品页脚用于溯源。"""
        return f"{self.policy_version}.{self.raw_digest[:8]}"


def load_policy(path: Path | str | None = None) -> Policy:
    p = Path(path) if path else POLICY_PATH
    text = p.read_text(encoding="utf-8")
    data = yaml.safe_load(text)

    cats: List[Category] = []
    for item in data.get("categories", []):
        cats.append(
            Category(
                code=item["code"],
                key=item["key"],
                name=item["name"],
                group=item.get("group", ""),
                severity=item.get("severity", "S2"),
                action=Action(item.get("action", "review")),
                gates=[Gate(g) for g in item.get("gates", ["ingest"])],
                rationale=(item.get("rationale") or "").strip(),
                remediation=(item.get("remediation") or "").strip(),
                judging_note=" ".join((item.get("judging_note") or "").split()),
                mitigation=item.get("mitigation"),
            )
        )

    q = data.get("quality_thresholds", {}) or {}
    guard = data.get("generation_guardrails", {}) or {}

    return Policy(
        policy_version=data.get("policy_version", "unversioned"),
        updated_at=data.get("updated_at", ""),
        owner=data.get("owner", ""),
        fail_mode=data.get("fail_mode", "review"),
        gates_enabled=data.get("gates", {}) or {},
        categories=cats,
        guardrails_positive=guard.get("positive", []) or [],
        guardrails_negative=guard.get("negative", []) or [],
        keyword_blocklist=data.get("keyword_blocklist", []) or [],
        quality=QualityThresholds(**{k: v for k, v in q.items()
                                     if k in QualityThresholds.__dataclass_fields__}),
        raw_digest=hashlib.sha256(text.encode("utf-8")).hexdigest(),
    )
