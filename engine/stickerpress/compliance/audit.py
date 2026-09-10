"""审计记录。

商业化的硬要求：任何一张印出来的实体贴纸，都要能回答
"它是谁在什么时候、用哪张原图、经过哪个版本的策略、被谁放行的"。

:class:`AuditRecord` 会落成 ``audit.json``，同时生成一枚 8 位**合规指纹**
印在 A5 台纸页脚，扫码/查号即可拉回完整链路。
"""

from __future__ import annotations

import hashlib
import json
import platform
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional

from .gates import GateResult
from .policy import Action, Policy


@dataclass
class AuditRecord:
    job_id: str
    created_at: str
    operator: str
    policy_version: str
    policy_digest: str
    engine_version: str
    inputs: List[Dict] = field(default_factory=list)
    generation: Dict = field(default_factory=dict)
    gates: List[Dict] = field(default_factory=list)
    quality: Dict = field(default_factory=dict)
    outputs: Dict = field(default_factory=dict)
    final_decision: str = Action.PASS.value
    printable: bool = False
    reasons: List[str] = field(default_factory=list)
    environment: Dict = field(default_factory=dict)

    # ------------------------------------------------------------------
    @staticmethod
    def new(job_id: str, operator: str, policy: Policy, engine_version: str) -> "AuditRecord":
        return AuditRecord(
            job_id=job_id,
            created_at=datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds"),
            operator=operator,
            policy_version=policy.policy_version,
            policy_digest=policy.raw_digest[:16],
            engine_version=engine_version,
            environment={
                "python": platform.python_version(),
                "platform": platform.platform(),
            },
        )

    def add_gate(self, result: GateResult) -> None:
        self.gates.append(result.to_dict())

    def conclude(self, decisions: List[Action]) -> None:
        final = Action.strictest(decisions)
        self.final_decision = final.value
        # 只有 pass / mitigate 才允许下单印刷；review 与 block 都要卡住
        self.printable = final in (Action.PASS, Action.MITIGATE)
        for g in self.gates:
            for n in g.get("notes", []):
                self.reasons.append(f"[{g['gate']}] {n}")
            for c in g.get("checks", []):
                if not c.get("passed"):
                    self.reasons.append(f"[{g['gate']}] {c['name']}：{c.get('detail','')}")

    # ------------------------------------------------------------------
    def fingerprint(self) -> str:
        """合规指纹：对整条审计链取哈希，任何环节被篡改都会变号。"""
        payload = json.dumps(
            {
                "job": self.job_id,
                "at": self.created_at,
                "policy": f"{self.policy_version}:{self.policy_digest}",
                "inputs": [i.get("sha256") for i in self.inputs],
                "gates": [(g["gate"], g["decision"]) for g in self.gates],
                "final": self.final_decision,
            },
            sort_keys=True, ensure_ascii=False,
        )
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:8].upper()

    def to_dict(self) -> Dict:
        d = {k: v for k, v in self.__dict__.items()}
        d["compliance_fingerprint"] = self.fingerprint()
        return d

    def save(self, path: Path) -> Path:
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(self.to_dict(), ensure_ascii=False, indent=2),
                        encoding="utf-8")
        return path

    # ------------------------------------------------------------------
    def human_summary(self) -> str:
        """给运营看的一段话。"""
        icon = {"pass": "✅ 放行", "mitigate": "✅ 放行（已自动处置）",
                "review": "⚠️ 转人工复核", "block": "⛔ 拦截"}
        lines = [
            f"作业号 {self.job_id}    合规指纹 {self.fingerprint()}",
            f"策略版本 {self.policy_version} ({self.policy_digest})",
            f"裁决：{icon.get(self.final_decision, self.final_decision)}"
            f"    可否下单印刷：{'是' if self.printable else '否'}",
        ]
        if self.reasons:
            lines.append("原因：")
            lines += [f"  · {r}" for r in self.reasons]
        return "\n".join(lines)
