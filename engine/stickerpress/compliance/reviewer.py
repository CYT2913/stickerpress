"""内容审核器（Reviewer）。

审核器只回答一个问题：**这张图命中了哪些风险类目？**
"命中之后怎么办"由 policy 决定，两者解耦，便于把 VLM 换成公司统一的审核服务。

内置两种实现：

* :class:`VlmReviewer` —— 调用多模态大模型做语义级审核（识别 IP 角色、名人、
  国家象征这类规则引擎做不了的事）。
* :class:`NullReviewer` —— 不具备审核能力时的占位实现，会触发 policy 的
  ``fail_mode``（默认降级转人工），而不是静默放行。

生产环境接公司审核中台时，只需再实现一个 Reviewer 子类。
"""

from __future__ import annotations

import json
import os
import re
import subprocess
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import List, Optional, Sequence

from .policy import Category, Gate


@dataclass
class Finding:
    """一条审核结论。"""

    category_key: str
    hit: bool
    confidence: float           # 0~1
    evidence: str = ""          # 模型给出的判定依据，进审计日志
    reviewer: str = ""

    def to_dict(self) -> dict:
        return asdict(self)


class Reviewer:
    name = "base"

    @property
    def available(self) -> bool:
        return False

    def review(self, images: Sequence[Path], categories: Sequence[Category],
               gate: Gate, context: str = "") -> List[Finding]:
        raise NotImplementedError


# ---------------------------------------------------------------------------
# VLM 审核器
# ---------------------------------------------------------------------------

_PROMPT_TEMPLATE = """你是实体贴纸印刷业务的内容安全审核员。下面的图片将被加工成**可售卖的实体贴纸**，
一旦印刷即无法召回，因此审核标准要严于普通 UGC 平台。

审核环节：{gate_desc}
{context_block}
请逐项判断图片是否命中以下风险类目。**宁可疑似也要标出**，但必须给出具体依据，不要凭空推测。

{category_block}

只输出一个 JSON 对象，不要有任何解释性文字、不要用 markdown 代码块包裹。格式：
{{
  "findings": [
    {{"key": "类目key", "hit": true/false, "confidence": 0.0~1.0, "evidence": "简短中文依据，未命中写空字符串"}}
  ],
  "summary": "一句话总体结论"
}}
必须为上面列出的每一个类目 key 都返回一条记录。"""

_GATE_DESC = {
    Gate.INGEST: "闸1·入料审核 —— 用户刚上传的原始照片，判断它是否可以进入 AI 生成流程",
    Gate.EGRESS: "闸3·出料审核 —— AI 已生成的卡通贴纸成品，判断它是否可以进入印刷环节",
    Gate.GENERATION: "闸2·生成审核",
}


def _find_analyze_image_script() -> Optional[Path]:
    """定位多模态审核脚本。优先环境变量，其次向上逐层查找 inner_skills。"""
    env = os.environ.get("STICKERPRESS_ANALYZE_IMAGE")
    if env and Path(env).exists():
        return Path(env)
    here = Path(__file__).resolve()
    for base in [here, *here.parents]:
        cand = base / "inner_skills" / "analyze_media" / "analyze_image.py"
        if cand.exists():
            return cand
    cwd = Path.cwd()
    for base in [cwd, *cwd.parents]:
        cand = base / "inner_skills" / "analyze_media" / "analyze_image.py"
        if cand.exists():
            return cand
    return None


_WRAPPER_RE = re.compile(r"^\s*[A-Za-z_]\w*\(\s*result\s*=\s*(.+?)\s*\)\s*$", re.S)


def _unwrap_tool_output(text: str) -> str:
    """解开工具层的包装。

    审核脚本可能把结果打成 ``AimeToolResultText(result='...')`` 这种 Python repr，
    里面的换行是字面量 ``\\n``。不解包就会导致**模型明明判出了风险、闸门却读不到**——
    这是最危险的一类静默失效，必须在这里根治。
    """
    raw = text.strip()
    m = _WRAPPER_RE.match(raw)
    if m:
        import ast
        inner = m.group(1)
        try:
            val = ast.literal_eval(inner)
            if isinstance(val, str):
                return val
        except (ValueError, SyntaxError):
            pass
    # 兜底：整段没有真换行却含大量字面量 \n → 反转义
    if "\n" not in raw and raw.count("\\n") >= 2:
        try:
            return raw.encode("utf-8").decode("unicode_escape")
        except UnicodeDecodeError:
            pass
    return raw


def _extract_json(text: str) -> Optional[dict]:
    """从模型自由文本里抠出 JSON 对象。"""
    text = _unwrap_tool_output(text)
    # 贪婪匹配，避免在嵌套对象的第一个 } 处提前收尾
    fence = re.search(r"```(?:json)?\s*(\{.*\})\s*```", text, re.S)
    if fence:
        try:
            return json.loads(fence.group(1))
        except json.JSONDecodeError:
            pass
    start = text.find("{")
    while start != -1:
        depth, in_str, esc = 0, False, False
        for i in range(start, len(text)):
            ch = text[i]
            if in_str:
                if esc:
                    esc = False
                elif ch == "\\":
                    esc = True
                elif ch == '"':
                    in_str = False
                continue
            if ch == '"':
                in_str = True
            elif ch == "{":
                depth += 1
            elif ch == "}":
                depth -= 1
                if depth == 0:
                    try:
                        return json.loads(text[start:i + 1])
                    except json.JSONDecodeError:
                        break
        start = text.find("{", start + 1)
    return None


class VlmReviewer(Reviewer):
    """通过多模态大模型做语义级内容审核。"""

    name = "vlm"

    def __init__(self, script: Path | str | None = None, timeout: int = 240,
                 min_coverage: float = 0.6):
        self.script = Path(script) if script else _find_analyze_image_script()
        self.timeout = timeout
        self.min_coverage = min_coverage
        self.last_summary = ""
        self.last_error = ""

    @property
    def available(self) -> bool:
        return self.script is not None and self.script.exists()

    def review(self, images: Sequence[Path], categories: Sequence[Category],
               gate: Gate, context: str = "") -> List[Finding]:
        if not self.available:
            raise RuntimeError("VLM 审核脚本不可用")
        if not images:
            return []

        cat_lines = []
        for c in categories:
            desc = f"- {c.key}（{c.code} {c.name}，严重度 {c.severity}）"
            if c.rationale:
                first = c.rationale.strip().splitlines()[0]
                desc += f"：{first}"
            if c.judging_note:
                desc += f"\n    判定口径：{c.judging_note}"
            cat_lines.append(desc)

        ctx_block = f"业务上下文：{context}\n" if context else ""
        task = _PROMPT_TEMPLATE.format(
            gate_desc=_GATE_DESC.get(gate, gate.value),
            context_block=ctx_block,
            category_block="\n".join(cat_lines),
        )

        payload = {"task": task, "paths": [str(Path(p).resolve()) for p in images[:10]]}
        proc = subprocess.run(
            ["python3", str(self.script), "-"],
            input=json.dumps(payload, ensure_ascii=False),
            capture_output=True, text=True, timeout=self.timeout,
            cwd=str(self.script.parent),
        )
        if proc.returncode != 0:
            self.last_error = (proc.stderr or proc.stdout)[-500:]
            raise RuntimeError(f"审核模型调用失败：{self.last_error}")

        data = _extract_json(proc.stdout)
        if not data:
            self.last_error = proc.stdout[-500:]
            raise RuntimeError("审核模型返回内容无法解析为 JSON")

        self.last_summary = str(data.get("summary", "")).strip()
        valid = {c.key for c in categories}
        findings: List[Finding] = []
        seen = set()
        for item in data.get("findings", []):
            key = str(item.get("key", "")).strip()
            if key not in valid or key in seen:
                continue
            seen.add(key)
            findings.append(Finding(
                category_key=key,
                hit=bool(item.get("hit")),
                confidence=float(item.get("confidence") or 0.0),
                evidence=str(item.get("evidence") or "").strip(),
                reviewer=self.name,
            ))

        # 覆盖率兜底（fail-closed）：模型只答了一小部分类目，说明这次审核
        # 根本不可信，绝不能当成"全都没命中"放行，直接判失败让上层走 fail_mode。
        coverage = len(seen) / max(len(valid), 1)
        if coverage < self.min_coverage:
            self.last_error = (f"审核覆盖率不足：{len(seen)}/{len(valid)} "
                               f"({coverage:.0%} < {self.min_coverage:.0%})")
            raise RuntimeError(self.last_error)

        # 少数漏答的类目单独标注，进审计留痕
        for key in sorted(valid - seen):
            findings.append(Finding(category_key=key, hit=False, confidence=0.0,
                                    evidence="模型未返回该类目结论", reviewer="uncovered"))
        return findings


class NullReviewer(Reviewer):
    """无审核能力的占位实现。"""

    name = "null"

    @property
    def available(self) -> bool:
        return False

    def review(self, images, categories, gate, context="") -> List[Finding]:
        raise RuntimeError("未配置内容审核器")


def build_reviewer(kind: str = "auto") -> Reviewer:
    """按需构造审核器。kind: auto / vlm / off"""
    if kind == "off":
        return NullReviewer()
    r = VlmReviewer()
    if r.available:
        return r
    if kind == "vlm":
        raise RuntimeError("要求使用 VLM 审核器，但未找到可用的多模态审核脚本")
    return NullReviewer()
