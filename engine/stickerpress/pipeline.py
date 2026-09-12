"""StickerPress 主流水线。

    照片 → [闸1 入料合规] → [闸2 生成合规+提示词加固] → AI 生成六宫格大图
         → 色度键抠图 → 切成 6 张 → 刀版矢量化 → A5 排版
         → [闸3 出料合规+印刷质检] → 交付（A5 SVG + 原图 + 审计）

设计原则：任何一步失败都不静默吞掉，而是落到审计里并给出明确裁决。
"""

from __future__ import annotations

import json
import shutil
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Sequence

from PIL import Image

from . import __version__
from .compliance import (
    Action, AuditRecord, Check, GateResult, Policy, build_reviewer, load_policy,
    gate_egress, gate_generation, gate_ingest,
)
from .compliance.reviewer import Reviewer
from .config import SheetSpec, StyleSpec, get_style
from .imaging import (
    GenerationRequest, StickerProvider, prepare_rgba, split_sheet,
)
from .layout import build_sheet_svg, render_preview

FINGERPRINT_TOKEN = "@@CHK@@"


@dataclass
class JobResult:
    job_id: str
    outdir: Path
    decision: Action
    printable: bool
    svg_path: Optional[Path] = None
    preview_path: Optional[Path] = None
    original_paths: List[Path] = field(default_factory=list)
    sticker_paths: List[Path] = field(default_factory=list)
    audit_path: Optional[Path] = None
    manifest_path: Optional[Path] = None
    report_path: Optional[Path] = None
    fingerprint: str = ""
    messages: List[str] = field(default_factory=list)
    quality: Dict = field(default_factory=dict)

    @property
    def ok(self) -> bool:
        return self.svg_path is not None


def new_job_id() -> str:
    return datetime.now().strftime("%y%m%d") + "-" + uuid.uuid4().hex[:6].upper()


class StickerPressPipeline:
    def __init__(
        self,
        policy: Optional[Policy] = None,
        provider: Optional[StickerProvider] = None,
        reviewer: Optional[Reviewer] = None,
        spec: Optional[SheetSpec] = None,
        operator: str = "unknown",
    ):
        self.policy = policy or load_policy()
        self.provider = provider
        self.reviewer = reviewer if reviewer is not None else build_reviewer("auto")
        self.spec = spec or SheetSpec()
        self.operator = operator

    # ------------------------------------------------------------------
    def run(
        self,
        photos: Sequence[Path],
        outdir: Path,
        style_key: str = "kawaii",
        subject_hint: str = "",
        job_id: Optional[str] = None,
        keep_intermediate: bool = True,
        on_progress=None,
    ) -> JobResult:
        style: StyleSpec = get_style(style_key)
        job_id = job_id or new_job_id()
        outdir = Path(outdir) / job_id
        outdir.mkdir(parents=True, exist_ok=True)

        def step(msg: str) -> None:
            if on_progress:
                on_progress(msg)

        audit = AuditRecord.new(job_id, self.operator, self.policy, __version__)
        result = JobResult(job_id=job_id, outdir=outdir,
                           decision=Action.PASS, printable=False)
        decisions: List[Action] = []

        # ---------- 闸 1 入料 -------------------------------------------
        step("闸1 · 入料合规审核")
        g1, cleaned, metas = gate_ingest(self.policy, [Path(p) for p in photos],
                                         outdir, reviewer=self.reviewer)
        audit.inputs = metas
        audit.add_gate(g1)
        decisions.append(g1.decision)
        result.original_paths = cleaned
        result.messages.append(f"闸1 裁决：{g1.decision.value}")

        if g1.blocked:
            return self._finish(result, audit, decisions, outdir, blocked_at="ingest")

        # ---------- 闸 2 生成 -------------------------------------------
        step("闸2 · 生成合规与提示词加固")
        g2 = gate_generation(self.policy, subject_hint)
        audit.add_gate(g2)
        decisions.append(g2.decision)
        result.messages.append(f"闸2 裁决：{g2.decision.value}")
        if g2.blocked:
            return self._finish(result, audit, decisions, outdir, blocked_at="generation")

        # ---------- 生成 -------------------------------------------------
        step("调用图像模型生成六宫格贴纸大图")
        if self.provider is None:
            raise RuntimeError("未配置贴纸生成后端")
        req = GenerationRequest(
            reference_images=list(cleaned),
            style=style,
            subject_hint=subject_hint,
            count=self.spec.slots,
            cols=self.spec.cols,
            rows=self.spec.rows,
            guardrails_positive=self.policy.guardrails_positive,
            guardrails_negative=self.policy.guardrails_negative,
        )
        gen = self.provider.generate(req, outdir)
        audit.generation = {
            "provider": gen.provider,
            "model": gen.model,
            "style": style.key,
            "style_name": style.name_zh,
            "prompt": gen.prompt,
            "chroma_key": "#FF00FF",
            "sheet_raw": str(gen.sheet_path),
        }

        # ---------- 抠图 + 切分 -------------------------------------------
        step("背景透明化（alpha 直通 / 色度键）+ 六宫格切分")
        raw = Image.open(gen.sheet_path)
        keyed = prepare_rgba(raw)
        pieces, diag = split_sheet(keyed.rgba, expected=self.spec.slots,
                                   rows=self.spec.rows)

        sticker_dir = outdir / "stickers"
        sticker_dir.mkdir(exist_ok=True)
        sticker_paths: List[Path] = []
        for p in pieces:
            sp = sticker_dir / f"sticker_{p.index:02d}.png"
            p.image.save(sp)
            sticker_paths.append(sp)
        result.sticker_paths = sticker_paths

        # ---------- 排版 ---------------------------------------------------
        step("A5 排版 + 刀版轮廓矢量化")
        labels = style.expressions_zh[: len(pieces)]
        sheet = build_sheet_svg(
            pieces, spec=self.spec, job_id=job_id,
            fingerprint=FINGERPRINT_TOKEN,
            policy_version=self.policy.policy_version,
            labels=labels,
        )

        # ---------- 质检 ---------------------------------------------------
        q = self.policy.quality
        checks: List[Check] = []
        checks.append(Check(
            "贴纸张数", len(pieces) == q.required_sticker_count,
            f"切出 {len(pieces)} 张（要求 {q.required_sticker_count}）；" + "；".join(diag),
            Action.BLOCK))
        checks.append(Check(
            "背景透明化", keyed.keyed,
            ("alpha 直通：" if keyed.mode == "alpha" else "色度键：") + keyed.note,
            Action.REVIEW))
        checks.append(Check(
            "有效印刷分辨率", sheet.min_effective_dpi >= q.min_effective_dpi,
            f"最低 {sheet.min_effective_dpi:.0f} dpi（门槛 {q.min_effective_dpi} dpi）",
            Action.REVIEW))
        checks.append(Check(
            "刀版最小净距", sheet.min_knife_gap_mm >= q.min_knife_gap_mm,
            f"{sheet.min_knife_gap_mm:.2f} mm（门槛 {q.min_knife_gap_mm} mm）",
            Action.REVIEW))
        bad_area = [p.index for p in sheet.placements
                    if not (q.min_sticker_area_ratio <= p.area_ratio <= q.max_sticker_area_ratio)]
        checks.append(Check(
            "格位占用率", not bad_area,
            "全部在合理区间" if not bad_area else f"第 {bad_area} 张占比异常（可能抠图残缺或贴边）",
            Action.REVIEW))

        # 单枚成品尺寸：太小撕不起来、贴不牢；太大就不是"贴纸"了。
        sp = self.spec
        too_small = [p.index for p in sheet.placements
                     if min(p.w_mm, p.h_mm) < sp.piece_hard_min_mm]
        off_range = [p.index for p in sheet.placements
                     if not (sp.piece_min_mm <= max(p.w_mm, p.h_mm) <= sp.piece_max_mm)]
        checks.append(Check(
            "单枚贴纸尺寸", not too_small,
            f"最短边 {min((min(p.w_mm, p.h_mm) for p in sheet.placements), default=0):.1f} mm"
            f"（硬下限 {sp.piece_hard_min_mm} mm）"
            + ("" if not too_small else f"；第 {too_small} 张过小"),
            Action.BLOCK))
        if off_range:
            checks.append(Check(
                "单枚尺寸建议区间", False,
                f"第 {off_range} 张长边超出 {sp.piece_min_mm}–{sp.piece_max_mm} mm 建议区间",
                Action.REVIEW))

        # 安全边距：任何刀线都不得进入距成品边 safe_margin_mm 的范围。
        margin = min(
            (min(p.x_mm, p.y_mm,
                 sp.canvas_w_mm - (p.x_mm + p.w_mm),
                 sp.canvas_h_mm - (p.y_mm + p.h_mm))
             for p in sheet.placements), default=0.0)
        checks.append(Check(
            "安全边距", margin >= sp.safe_margin_mm - 1e-6,
            f"最小 {margin:.1f} mm（门槛 {sp.safe_margin_mm} mm）",
            Action.BLOCK))

        result.quality = {
            "sticker_count": len(pieces),
            "min_effective_dpi": round(sheet.min_effective_dpi, 1),
            "min_knife_gap_mm": round(sheet.min_knife_gap_mm, 2),
            "min_safe_margin_mm": round(margin, 2),
            "canvas_mm": [sp.canvas_w_mm, sp.canvas_h_mm],
            "background_mode": keyed.mode,
            "background_ratio": round(keyed.background_ratio, 4),
            # 兼容旧字段名，勿删：早期报告与前端按这个键读数
            "chroma_background_ratio": round(keyed.background_ratio, 4),
            "placements": [p.to_dict() for p in sheet.placements],
            "segmentation": diag,
        }
        audit.quality = result.quality

        # ---------- 闸 3 出料 -----------------------------------------------
        step("闸3 · 出料合规审核与印刷质检")
        g3 = gate_egress(self.policy, sticker_paths, quality_checks=checks,
                         reviewer=self.reviewer)
        audit.add_gate(g3)
        decisions.append(g3.decision)
        result.messages.append(f"闸3 裁决：{g3.decision.value}")

        # ---------- 定稿 ---------------------------------------------------
        audit.conclude(decisions)
        fp = audit.fingerprint()
        result.fingerprint = fp

        svg_text = sheet.svg.replace(FINGERPRINT_TOKEN, fp)
        svg_path = outdir / "sticker_sheet_A5.svg"
        svg_path.write_text(svg_text, encoding="utf-8")
        result.svg_path = svg_path

        preview = render_preview(pieces, sheet.placements, spec=self.spec, dpi=160)
        preview_path = outdir / "preview.png"
        preview.save(preview_path)
        result.preview_path = preview_path

        audit.outputs = {
            "svg": str(svg_path),
            "svg_bytes": svg_path.stat().st_size,
            "preview": str(preview_path),
            "originals": [str(p) for p in cleaned],
            "stickers": [str(p) for p in sticker_paths],
        }

        if not keep_intermediate:
            Path(gen.sheet_path).unlink(missing_ok=True)

        return self._finish(result, audit, decisions, outdir)

    # ------------------------------------------------------------------
    def _finish(self, result: JobResult, audit: AuditRecord,
                decisions: List[Action], outdir: Path,
                blocked_at: str = "") -> JobResult:
        if not audit.final_decision or blocked_at:
            audit.conclude(decisions)
        result.decision = Action(audit.final_decision)
        result.printable = audit.printable
        result.fingerprint = audit.fingerprint()

        result.audit_path = audit.save(outdir / "audit.json")

        manifest = {
            "job_id": result.job_id,
            "engine": __version__,
            "created_at": audit.created_at,
            "operator": self.operator,
            "compliance_fingerprint": result.fingerprint,
            "decision": result.decision.value,
            "printable": result.printable,
            "blocked_at": blocked_at or None,
            "sheet": {
                "format": "A5",
                "trim_mm": [self.spec.page_w_mm, self.spec.page_h_mm],
                "bleed_mm": self.spec.bleed_mm,
                "canvas_mm": [self.spec.canvas_w_mm, self.spec.canvas_h_mm],
                "slots": self.spec.slots,
                "grid": f"{self.spec.cols}x{self.spec.rows}",
            },
            "deliverables": {
                "sheet_svg": _rel(result.svg_path, outdir),
                "preview_png": _rel(result.preview_path, outdir),
                "originals": [_rel(p, outdir) for p in result.original_paths],
                "stickers": [_rel(p, outdir) for p in result.sticker_paths],
                "audit_json": _rel(result.audit_path, outdir),
            },
            "quality": result.quality,
        }
        result.manifest_path = outdir / "manifest.json"
        result.manifest_path.write_text(
            json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")

        result.report_path = outdir / "report.md"
        result.report_path.write_text(_render_report(result, audit, self.policy, self.spec),
                                      encoding="utf-8")
        return result


def _rel(p: Optional[Path], base: Path) -> Optional[str]:
    if p is None:
        return None
    try:
        return str(Path(p).relative_to(base))
    except ValueError:
        return str(p)


# ---------------------------------------------------------------------------


_ICON = {"pass": "✅ 放行", "mitigate": "✅ 放行（已自动处置）",
         "review": "⚠️ 转人工复核", "block": "⛔ 拦截"}


def _render_report(result: JobResult, audit: AuditRecord, policy: Policy,
                   spec: SheetSpec) -> str:
    L: List[str] = []
    L.append(f"# StickerPress 作业报告 · {result.job_id}\n")
    L.append(f"- 生成时间：{audit.created_at}")
    L.append(f"- 操作人：{audit.operator}")
    L.append(f"- 引擎版本：{audit.engine_version}")
    L.append(f"- 策略版本：`{audit.policy_version}` (digest `{audit.policy_digest}`)")
    L.append(f"- **合规指纹：`{result.fingerprint}`**（已印于台纸页脚）")
    L.append(f"- **最终裁决：{_ICON.get(result.decision.value, result.decision.value)}**"
             f"　可否下单印刷：**{'是' if result.printable else '否'}**\n")

    L.append("## 一、合规链路\n")
    L.append("| 闸门 | 裁决 | 审核器 | 命中/异常 |")
    L.append("|---|---|---|---|")
    gate_zh = {"ingest": "闸1 入料", "generation": "闸2 生成", "egress": "闸3 出料"}
    for g in audit.gates:
        bad = [c["name"] for c in g["checks"] if not c["passed"]]
        bad += [f["category_key"] for f in g["findings"] if f.get("hit")]
        L.append(f"| {gate_zh.get(g['gate'], g['gate'])} | "
                 f"{_ICON.get(g['decision'], g['decision'])} | `{g['reviewer']}` | "
                 f"{'、'.join(bad) if bad else '—'} |")
    L.append("")

    mitig = [m for g in audit.gates for m in g.get("mitigations", [])]
    if mitig:
        L.append("**自动处置记录**\n")
        for m in mitig:
            L.append(f"- `{m['category_key']}` → {m['method']}：{m['detail']}")
        L.append("")

    if audit.reasons:
        L.append("**判定依据**\n")
        for r in audit.reasons:
            L.append(f"- {r}")
        L.append("")

    L.append("## 二、印刷质检\n")
    q = result.quality
    if q:
        L.append("| 指标 | 实测 | 门槛 |")
        L.append("|---|---|---|")
        L.append(f"| 贴纸张数 | {q.get('sticker_count')} | {policy.quality.required_sticker_count} |")
        L.append(f"| 最低有效分辨率 | {q.get('min_effective_dpi')} dpi | "
                 f"≥ {policy.quality.min_effective_dpi} dpi |")
        L.append(f"| 刀版最小净距 | {q.get('min_knife_gap_mm')} mm | "
                 f"≥ {policy.quality.min_knife_gap_mm} mm |")
        mode = q.get("background_mode", "chroma")
        mode_zh = "alpha 直通（输入自带透明）" if mode == "alpha" else "色度键（品红兜底）"
        L.append(f"| 背景透明化方式 | {mode_zh} | — |")
        L.append(f"| 背景透明像素占比 | {q.get('background_ratio', q.get('chroma_background_ratio', 0)):.1%} | > 15% |")
        L.append("")
        L.append("**逐张明细**\n")
        L.append("| # | 标签 | 尺寸(mm) | 有效dpi | 格位占用 |")
        L.append("|---|---|---|---|---|")
        for p in q.get("placements", []):
            L.append(f"| {p['index']} | {p['label']} | "
                     f"{p['w_mm']}×{p['h_mm']} | {p['effective_dpi']} | "
                     f"{p['area_ratio']:.0%} |")
        L.append("")

    L.append("## 三、交付物\n")
    if result.svg_path:
        L.append(f"- `sticker_sheet_A5.svg` —— A5 印刷级矢量台纸"
                 f"（{spec.canvas_w_mm:g}×{spec.canvas_h_mm:g}mm 含 {spec.bleed_mm:g}mm 出血，"
                 f"含 `CutContour` 模切图层）")
        L.append("- `preview.png` —— 效果预览（含刀版示意，不用于印刷）")
        L.append(f"- `originals/` —— 已脱敏原图 {len(result.original_paths)} 张"
                 "（剥离 EXIF，重编码为 sRGB PNG）")
        L.append(f"- `stickers/` —— {len(result.sticker_paths)} 张独立透明底贴纸 PNG")
    else:
        L.append("> 作业在合规闸门被终止，未产出任何印刷文件。"
                 "已上传的原图仅用于审核留痕，可随时删除。")
        L.append("")
        blocked = [g for g in audit.gates if g["decision"] == "block"]
        if blocked:
            L.append(f"终止于：**{gate_zh.get(blocked[0]['gate'], blocked[0]['gate'])}**")
            for f in blocked[0]["findings"]:
                if f.get("hit"):
                    cat = policy.category(f["category_key"])
                    if cat and cat.remediation:
                        L.append(f"- 补救路径：{cat.remediation}")
    L.append("- `audit.json` / `manifest.json` —— 全链路审计与交付清单")
    return "\n".join(L) + "\n"
