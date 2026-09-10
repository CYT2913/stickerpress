"""三道合规闸门。

    闸1 ingest      用户上传的原始照片 → 能不能进 AI
    闸2 generation  提示词与用户文案   → 生成请求本身合不合规（并加固提示词）
    闸3 egress      生成出的贴纸与版面 → 能不能进印刷

每道闸返回一个 :class:`GateResult`，包含：规则检查明细、模型审核明细、
自动处置记录、最终裁决。裁决取所有命中项中**最严厉**的动作。
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Dict, List, Optional, Sequence

from PIL import Image, ImageOps

from .policy import Action, Category, Gate, Policy
from .reviewer import Finding, Reviewer

# 允许的上传格式
ALLOWED_FORMATS = {"JPEG", "PNG", "WEBP", "HEIF", "HEIC", "BMP"}
MAX_UPLOAD_BYTES = 25 * 1024 * 1024
MIN_INPUT_EDGE_PX = 512   # 短边下限：低于此值放大成 A5 贴纸必然糊


@dataclass
class Check:
    """一条规则检查结果。"""

    name: str
    passed: bool
    detail: str = ""
    action: Action = Action.PASS

    def to_dict(self) -> dict:
        d = asdict(self)
        d["action"] = self.action.value
        return d


@dataclass
class Mitigation:
    """一次自动处置记录。"""

    category_key: str
    method: str
    detail: str = ""

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class GateResult:
    gate: Gate
    decision: Action = Action.PASS
    checks: List[Check] = field(default_factory=list)
    findings: List[Finding] = field(default_factory=list)
    mitigations: List[Mitigation] = field(default_factory=list)
    reviewer_used: str = "none"
    reviewer_summary: str = ""
    notes: List[str] = field(default_factory=list)
    skipped: bool = False

    @property
    def blocked(self) -> bool:
        return self.decision == Action.BLOCK

    @property
    def needs_human(self) -> bool:
        return self.decision in (Action.REVIEW, Action.BLOCK)

    def hit_categories(self) -> List[str]:
        keys = [f.category_key for f in self.findings if f.hit]
        keys += [c.name for c in self.checks if not c.passed]
        return keys

    def to_dict(self) -> dict:
        return {
            "gate": self.gate.value,
            "decision": self.decision.value,
            "skipped": self.skipped,
            "reviewer": self.reviewer_used,
            "reviewer_summary": self.reviewer_summary,
            "checks": [c.to_dict() for c in self.checks],
            "findings": [f.to_dict() for f in self.findings if f.hit or f.confidence > 0],
            "mitigations": [m.to_dict() for m in self.mitigations],
            "notes": self.notes,
        }


# ---------------------------------------------------------------------------


def _resolve(policy: Policy, findings: Sequence[Finding], gate: Gate,
             threshold: float = 0.45) -> tuple[Action, List[str]]:
    """把模型结论翻译成处置动作。"""
    actions: List[Action] = []
    notes: List[str] = []
    for f in findings:
        if not f.hit or f.confidence < threshold:
            continue
        cat: Optional[Category] = policy.category(f.category_key)
        if not cat or not cat.applies_to(gate):
            continue
        actions.append(cat.action)
        notes.append(f"[{cat.code} {cat.name}] {cat.action.value} · 置信度 {f.confidence:.2f}"
                     + (f" · {f.evidence}" if f.evidence else ""))
    return Action.strictest(actions), notes


def _run_reviewer(policy: Policy, reviewer: Optional[Reviewer], images: Sequence[Path],
                  gate: Gate, result: GateResult, context: str = "") -> None:
    """执行模型审核，并处理不可用时的降级。"""
    cats = policy.categories_for(gate)
    if not cats:
        return
    if reviewer is None or not reviewer.available:
        fallback = Action.REVIEW if policy.fail_mode == "review" else Action.PASS
        result.reviewer_used = "unavailable"
        result.notes.append(
            f"审核模型不可用，按 fail_mode={policy.fail_mode} 降级为 {fallback.value}")
        result.decision = Action.strictest([result.decision, fallback])
        return
    try:
        findings = reviewer.review(images, cats, gate, context=context)
    except Exception as exc:  # noqa: BLE001 - 审核失败必须降级而不是崩掉
        fallback = Action.REVIEW if policy.fail_mode == "review" else Action.PASS
        result.reviewer_used = f"{reviewer.name}(error)"
        result.notes.append(f"审核模型调用异常：{exc} → 降级为 {fallback.value}")
        result.decision = Action.strictest([result.decision, fallback])
        return

    result.reviewer_used = reviewer.name
    result.reviewer_summary = getattr(reviewer, "last_summary", "")
    result.findings.extend(findings)
    act, notes = _resolve(policy, findings, gate)
    result.decision = Action.strictest([result.decision, act])
    result.notes.extend(notes)


# ---------------------------------------------------------------------------
# 闸 1：入料
# ---------------------------------------------------------------------------

def gate_ingest(policy: Policy, image_paths: Sequence[Path], workdir: Path,
                reviewer: Optional[Reviewer] = None) -> tuple[GateResult, List[Path], List[Dict]]:
    """校验并净化用户上传的照片。

    返回 (闸门结果, 净化后的照片路径列表, 每张照片的元信息)。
    净化后的照片就是交付给用户的"原图"——已剥离 EXIF、统一为 sRGB/PNG。
    """
    res = GateResult(gate=Gate.INGEST)
    if not policy.gate_enabled(Gate.INGEST):
        res.skipped = True
        res.notes.append("闸1 已通过策略关闭")
        return res, list(image_paths), []

    clean_dir = workdir / "originals"
    clean_dir.mkdir(parents=True, exist_ok=True)

    cleaned: List[Path] = []
    metas: List[Dict] = []

    for idx, src in enumerate(image_paths, start=1):
        src = Path(src)
        label = src.name

        if not src.exists():
            res.checks.append(Check(f"文件存在性[{label}]", False, "文件不存在", Action.BLOCK))
            res.decision = Action.BLOCK
            continue

        size = src.stat().st_size
        if size > MAX_UPLOAD_BYTES:
            res.checks.append(Check(f"文件体积[{label}]", False,
                                    f"{size/1048576:.1f}MB 超过 {MAX_UPLOAD_BYTES/1048576:.0f}MB",
                                    Action.BLOCK))
            res.decision = Action.BLOCK
            continue

        try:
            with Image.open(src) as probe:
                fmt = (probe.format or "").upper()
                probe.load()
                im = ImageOps.exif_transpose(probe)  # 按 EXIF 方向摆正后再丢弃 EXIF
                exif = probe.getexif()
                w, h = im.size
        except Exception as exc:  # noqa: BLE001
            res.checks.append(Check(f"图像可解码[{label}]", False, f"解码失败：{exc}", Action.BLOCK))
            res.decision = Action.BLOCK
            continue

        if fmt not in ALLOWED_FORMATS:
            res.checks.append(Check(f"文件格式[{label}]", False, f"不支持的格式 {fmt}", Action.BLOCK))
            res.decision = Action.BLOCK
            continue
        res.checks.append(Check(f"文件格式[{label}]", True, fmt))

        if min(w, h) < MIN_INPUT_EDGE_PX:
            res.checks.append(Check(
                f"输入分辨率[{label}]", False,
                f"{w}×{h}，短边不足 {MIN_INPUT_EDGE_PX}px，成品会模糊", Action.REVIEW))
            res.decision = Action.strictest([res.decision, Action.REVIEW])
        else:
            res.checks.append(Check(f"输入分辨率[{label}]", True, f"{w}×{h}"))

        # --- D3 EXIF 脱敏（默认自动处置）-----------------------------------
        geo_tags = {0x8825}  # GPSInfo
        has_geo = any(t in exif for t in geo_tags)
        has_exif = len(exif) > 0
        if has_exif:
            res.mitigations.append(Mitigation(
                category_key="exif_geolocation",
                method="strip_exif",
                detail=f"{label}：已剥离 {len(exif)} 项 EXIF" + ("（含 GPS 定位）" if has_geo else ""),
            ))
            res.decision = Action.strictest([res.decision, Action.MITIGATE])

        digest = hashlib.sha256(src.read_bytes()).hexdigest()

        out = clean_dir / f"original_{idx:02d}.png"
        im.convert("RGB").save(out, format="PNG")  # 重编码即彻底丢弃所有元数据
        cleaned.append(out)
        metas.append({
            "index": idx,
            "source_name": label,
            "sha256": digest,
            "format": fmt,
            "width": w,
            "height": h,
            "bytes": size,
            "exif_stripped": has_exif,
            "gps_found": has_geo,
            "sanitized_path": str(out),
        })

    if not cleaned:
        res.decision = Action.BLOCK
        res.notes.append("没有任何可用的输入照片")
        return res, cleaned, metas

    if policy.gate_uses_vlm(Gate.INGEST):
        _run_reviewer(policy, reviewer, cleaned, Gate.INGEST, res,
                      context="这些是用户上传的原始照片，将被 AI 转成卡通形象后印成实体贴纸售卖。")

    return res, cleaned, metas


# ---------------------------------------------------------------------------
# 闸 2：生成
# ---------------------------------------------------------------------------

def gate_generation(policy: Policy, user_text: str = "") -> GateResult:
    """审核用户自定义文案，并确认提示词护栏已就位。"""
    res = GateResult(gate=Gate.GENERATION)
    if not policy.gate_enabled(Gate.GENERATION):
        res.skipped = True
        return res

    hits = policy.hit_keywords(user_text or "")
    if hits:
        res.checks.append(Check("自定义文案敏感词", False,
                                f"命中：{'、'.join(hits)}", Action.BLOCK))
        res.decision = Action.BLOCK
    else:
        res.checks.append(Check("自定义文案敏感词", True, "未命中"))

    n_neg = len(policy.guardrails_negative)
    res.checks.append(Check("提示词负向护栏", n_neg > 0, f"已注入 {n_neg} 条禁止项"))
    res.checks.append(Check("提示词正向约束", len(policy.guardrails_positive) > 0,
                            f"已注入 {len(policy.guardrails_positive)} 条"))
    return res


# ---------------------------------------------------------------------------
# 闸 3：出料
# ---------------------------------------------------------------------------

def gate_egress(policy: Policy, sticker_paths: Sequence[Path],
                quality_checks: Sequence[Check] = (),
                reviewer: Optional[Reviewer] = None) -> GateResult:
    """审核 AI 生成出来的贴纸成品 + 印刷质量硬指标。"""
    res = GateResult(gate=Gate.EGRESS)
    if not policy.gate_enabled(Gate.EGRESS):
        res.skipped = True
        return res

    for c in quality_checks:
        res.checks.append(c)
        if not c.passed:
            res.decision = Action.strictest([res.decision, c.action])

    if policy.gate_uses_vlm(Gate.EGRESS):
        _run_reviewer(
            policy, reviewer, sticker_paths, Gate.EGRESS, res,
            context=("这些是 AI 生成的卡通贴纸，马上要印成实体商品。"
                     "请特别注意：是否漂移出了知名 IP 角色特征、是否混入了品牌 Logo、"
                     "是否出现了任何文字或二维码。"),
        )
    return res
