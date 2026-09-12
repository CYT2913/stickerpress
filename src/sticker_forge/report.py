"""交付报告生成。

报告是交付物的一部分，不是日志。它要能独立回答三个问题：
交付了什么、依据什么规格、哪些风险是"已处理"、哪些是"需用户确认"。

刻意不写"本产品完全合规"这类结论：权利依赖用户声明，工具不做法律判断。
"""

from __future__ import annotations

from datetime import datetime
from typing import List, Optional

from .assemble import AssembleResult
from .rights import Rights
from .source import SourceFile
from .spec import CUT_SPOT_NAME, CUT_STROKE, CUT_STROKE_PT, PRINT_DPI_MIN, SheetSpec
from .verify import VerifyReport


def build_report(
    order_id: str,
    source: SourceFile,
    rights: Rights,
    spec: SheetSpec,
    result: Optional[AssembleResult] = None,
    verify: Optional[VerifyReport] = None,
    source_copy_name: str = "",
    svg_name: str = "",
) -> str:
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    L: List[str] = []
    a = L.append

    a(f"# 交付报告 · {order_id or '(未编号)'}")
    a("")
    a(f"生成时间：{now}")
    a("")

    # ---- 交付物 -----------------------------------------------------------
    a("## 1. 交付物")
    a("")
    if result is None:
        a("**本次未产出印刷文件。** 原因见第 3 节权利检查。")
        a("")
        a(f"- `{source_copy_name or '(未复制)'}`：来源照片副本（逐字节保留）")
    else:
        a("| 文件 | 说明 |")
        a("| --- | --- |")
        a(f"| `{svg_name}` | A5 {spec.page_w_mm:g}×{spec.page_h_mm:g} mm 自包含 SVG，"
          f"含 {len(result.placements)} 枚贴纸与 {CUT_SPOT_NAME} 刀线图层 |")
        a(f"| `{source_copy_name}` | 来源照片副本，与输入逐字节一致 |")
        a("| `delivery-report.md` | 本文件 |")
    a("")

    # ---- 规格 -------------------------------------------------------------
    a("## 2. 印刷规格")
    a("")
    a("| 项目 | 值 |")
    a("| --- | --- |")
    a(f"| 成品尺寸 | {spec.page_w_mm:g} × {spec.page_h_mm:g} mm（ISO A5 竖版）|")
    a(f"| 出血 | {spec.bleed_mm:g} mm"
      f"{'（kiss-cut 台纸无元素跨过成品边，不需要出血）' if spec.bleed_mm == 0 else ''} |")
    a(f"| 安全边距 | ≥ {spec.safe_margin_mm:g} mm |")
    a(f"| 版面 | {spec.cols} 列 × {spec.rows} 行 = {spec.slots} 枚 |")
    a(f"| 刀线 | `{CUT_SPOT_NAME}` 独立图层，{CUT_STROKE}，"
      f"{CUT_STROKE_PT} pt，闭合路径，kiss-cut 半切 |")
    a(f"| 分辨率门槛 | ≥ {PRINT_DPI_MIN} dpi |")
    if result is not None and result.target_dpi is not None:
        a(f"| 自动缩小目标 | {result.target_dpi:g} dpi（仅缩小，不放大；"
          f"本单缩小 {result.auto_shrunk_count}/{len(result.placements)} 枚）|")
    a(f"| 刀线最小净距门槛 | ≥ {spec.min_knife_gap_mm:g} mm |")
    a("")

    if result is not None:
        a("### 实测")
        a("")
        a(f"- 刀线最小净距：**{result.min_knife_gap_mm:.2f} mm**")
        a(f"- 最小安全边距：**{result.min_margin_mm:.2f} mm**")
        a(f"- 最低有效分辨率：**{result.min_effective_dpi:.0f} dpi**")
        a("")
        a("| # | 资产 | 位置 (mm) | 成品尺寸 (mm) | 源像素 | 有效 dpi |")
        a("| --- | --- | --- | --- | --- | --- |")
        for p in result.placements:
            a(f"| {p.index} | `{p.src_name}` | ({p.x_mm:.1f}, {p.y_mm:.1f}) | "
              f"{p.w_mm:.1f} × {p.h_mm:.1f} | {p.src_px[0]}×{p.src_px[1]} | "
              f"{p.effective_dpi:.0f} |")
        a("")

    # ---- 来源与权利 -------------------------------------------------------
    a("## 3. 来源文件与商用权利")
    a("")
    a("| 项目 | 值 |")
    a("| --- | --- |")
    a(f"| 原始文件名 | `{source.path.name}` |")
    a(f"| 字节数 | {source.size_bytes:,} |")
    a(f"| SHA-256 | `{source.sha256}` |")
    a(f"| 格式 / 尺寸 | {source.fmt} · "
      f"{source.width}×{source.height} px |" if source.width else
      f"| 格式 | {source.fmt}（尺寸未解析）|")
    a("")
    if source.notes:
        a("来源预检备注：")
        a("")
        for n in source.notes:
            a(f"- {n}")
        a("")

    a(f"权利声明人：{rights.declared_by or '(未填写)'}"
      f"{'　声明日期：' + rights.declared_at if rights.declared_at else ''}")
    a("")
    a(f"**权利检查结果：{'通过' if rights.ok else '未通过，已拒绝产出印刷文件'}**")
    a("")
    if rights.blockers:
        a("拦截原因：")
        a("")
        for b in rights.blockers:
            a(f"- {b}")
        a("")
    if rights.warnings:
        a("需用户确认 / 注意：")
        a("")
        for w in rights.warnings:
            a(f"- {w}")
        a("")

    # ---- 自动验收 ---------------------------------------------------------
    if verify is not None:
        a("## 4. 成品自动验收")
        a("")
        a("| 检查项 | 结果 | 详情 |")
        a("| --- | --- | --- |")
        for c in verify.checks:
            a(f"| {c.name} | {'✅' if c.passed else '❌'} | {c.detail} |")
        a("")
        if verify.needs_human:
            a("### 无法自动判定，必须人工复检")
            a("")
            for x in verify.needs_human:
                a(f"- {x}")
            a("")

    # ---- 边界 -------------------------------------------------------------
    a("## 5. 本报告的边界")
    a("")
    a("- 权利结论**完全依赖用户声明**，本工具不做法律审查，也不构成法律意见。")
    a("- 自动检查覆盖几何、图层、自包含性；**内容合规必须人工复检**"
      "（品牌 / 版权角色 / 可识别人物 / 隐私信息 / 受保护建筑与艺术品）。")
    a("- 不同模切厂的刀线命名、出血与文件偏好可能不同。"
      f"默认按 `{CUT_SPOT_NAME}` / {CUT_STROKE} / {CUT_STROKE_PT} pt / kiss-cut 交付；"
      "客户有印厂模板时以其模板为准，差异需记录。")
    a("")
    return "\n".join(L) + "\n"


__all__ = ["build_report"]
