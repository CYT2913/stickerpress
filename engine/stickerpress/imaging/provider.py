"""贴纸生成后端（Provider）。

把"怎么调模型"隔离在这一层，业务流水线只认 :class:`StickerProvider` 接口。
换模型、换供应商、走自建服务，都不影响合规与排版。

内置：
* :class:`AimeImageProvider` —— 走平台内置的图像编辑模型，用参考照生成六宫格贴纸大图。
* :class:`SheetFileProvider` —— 直接吃一张已有的六宫格大图（返单重印 / 离线联调 / 无生成额度时使用）。
"""

from __future__ import annotations

import os
import re
import shutil
import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Optional, Sequence

from ..config import CHROMA_KEY_RGB, StyleSpec


@dataclass
class GenerationRequest:
    reference_images: List[Path]
    style: StyleSpec
    subject_hint: str = ""          # 用户描述的主体，如"我家的橘色博美"
    count: int = 6
    cols: int = 2
    rows: int = 3
    guardrails_positive: List[str] = field(default_factory=list)
    guardrails_negative: List[str] = field(default_factory=list)


@dataclass
class GenerationResult:
    sheet_path: Path
    prompt: str
    provider: str
    model: str = ""
    raw_log: str = ""


def _hex(rgb) -> str:
    return "#{:02X}{:02X}{:02X}".format(*rgb)


def build_prompt(req: GenerationRequest) -> str:
    """构造六宫格贴纸大图的提示词。

    三块内容缺一不可：
      1. 版面约束（几行几列、互不粘连、不贴边）—— 决定后续能不能干净切分
      2. 色度键背景约束            —— 决定能不能抠干净
      3. 合规护栏（正向 + 负向）    —— 闸2 注入，防止模型自发越界
    """
    key = _hex(CHROMA_KEY_RGB)
    subject = req.subject_hint.strip() or "the main subject in the reference photo"
    expressions = req.style.expressions[: req.count]
    expr_txt = "; ".join(f"({i+1}) {e}" for i, e in enumerate(expressions))

    parts = [
        f"Create a sheet of exactly {req.count} die-cut sticker designs of {subject}, "
        f"arranged in a clean {req.cols}-column x {req.rows}-row grid.",

        f"BACKGROUND (critical): the entire background must be one flat solid pure "
        f"magenta {key}, absolutely uniform — no gradient, no texture, no checkerboard, "
        f"no drop shadow cast onto the background. The artwork itself must NOT use any "
        f"magenta, fuchsia or hot-pink color anywhere.",

        f"LAYOUT (critical): leave generous even spacing between the {req.count} stickers so "
        f"they never touch each other and never touch the image border. Each sticker must be "
        f"a single connected shape.",

        f"EACH STICKER: keep the subject instantly recognizable and consistent across all "
        f"{req.count} designs (same character, same colors, same markings). Give every sticker a "
        f"thick uniform pure-white outline border in classic die-cut sticker style.",

        f"ART DIRECTION: {req.style.art_direction}.",

        f"EXPRESSIONS, one per sticker: {expr_txt}.",
    ]

    if req.guardrails_positive:
        parts.append("REQUIRED: " + "; ".join(req.guardrails_positive) + ".")
    if req.guardrails_negative:
        parts.append("STRICTLY FORBIDDEN: " + "; ".join(req.guardrails_negative) + ".")

    return " ".join(parts)


# ---------------------------------------------------------------------------


class StickerProvider:
    name = "base"

    @property
    def available(self) -> bool:
        return False

    def generate(self, req: GenerationRequest, outdir: Path) -> GenerationResult:
        raise NotImplementedError


def _find_image_skill() -> Optional[Path]:
    env = os.environ.get("STICKERPRESS_IMAGE_SKILL")
    if env and Path(env).exists():
        return Path(env)
    here = Path(__file__).resolve()
    roots = [here, *here.parents, Path.cwd(), *Path.cwd().parents]
    for base in roots:
        cand = base / "inner_skills" / "image-generate"
        if (cand / "script" / "image_edit.py").exists():
            return cand
    return None


_PATH_RE = re.compile(r"(/\S+\.(?:png|jpg|jpeg|webp))", re.I)


class AimeImageProvider(StickerProvider):
    """调用平台内置图像模型生成六宫格贴纸大图。"""

    name = "aime-image"

    def __init__(self, skill_dir: Path | str | None = None, timeout: int = 600,
                 resolution: str = "2k"):
        self.skill_dir = Path(skill_dir) if skill_dir else _find_image_skill()
        self.timeout = timeout
        self.resolution = resolution

    @property
    def available(self) -> bool:
        return self.skill_dir is not None and (self.skill_dir / "script" / "image_edit.py").exists()

    def generate(self, req: GenerationRequest, outdir: Path) -> GenerationResult:
        if not self.available:
            raise RuntimeError("图像生成后端不可用")
        prompt = build_prompt(req)
        outdir.mkdir(parents=True, exist_ok=True)

        # 2:3 最贴近 2列×3行 的六宫格版面，也最接近 A5 的 1:1.414
        if req.reference_images:
            script = self.skill_dir / "script" / "image_edit.py"
            cmd = ["python3", str(script), "--imageurls",
                   *[str(Path(p).resolve()) for p in req.reference_images],
                   "--prompt", prompt]
        else:
            script = self.skill_dir / "script" / "image_generator.py"
            cmd = ["python3", str(script), "--prompt", prompt]
        cmd += ["--aspectratio", "2:3", "--resolution", self.resolution,
                "--mimetype", "image/png"]

        proc = subprocess.run(cmd, capture_output=True, text=True,
                              timeout=self.timeout, cwd=str(self.skill_dir))
        log = (proc.stdout or "") + (proc.stderr or "")
        if proc.returncode != 0:
            raise RuntimeError(f"图像生成失败：{log[-800:]}")

        produced = [Path(p) for p in _PATH_RE.findall(proc.stdout)]
        produced = [p for p in produced if p.exists()]
        if not produced:
            raise RuntimeError(f"图像生成未返回可用文件：{log[-800:]}")

        src = produced[-1]
        dst = outdir / "sheet_raw.png"
        shutil.copy2(src, dst)
        return GenerationResult(sheet_path=dst, prompt=prompt, provider=self.name,
                                model="platform-image-edit", raw_log=log[-2000:])


class SheetFileProvider(StickerProvider):
    """跳过生成，直接使用一张现成的六宫格大图。"""

    name = "sheet-file"

    def __init__(self, sheet: Path | str):
        self.sheet = Path(sheet)

    @property
    def available(self) -> bool:
        return self.sheet.exists()

    def generate(self, req: GenerationRequest, outdir: Path) -> GenerationResult:
        if not self.available:
            raise RuntimeError(f"指定的贴纸大图不存在：{self.sheet}")
        outdir.mkdir(parents=True, exist_ok=True)
        dst = outdir / "sheet_raw.png"
        shutil.copy2(self.sheet, dst)
        return GenerationResult(sheet_path=dst, prompt="(bypassed: 直接使用现成大图)",
                                provider=self.name, model="none")


def build_provider(kind: str = "auto", sheet: Path | str | None = None) -> StickerProvider:
    if sheet:
        return SheetFileProvider(sheet)
    p = AimeImageProvider()
    if p.available:
        return p
    if kind == "aime":
        raise RuntimeError("要求使用平台图像后端，但未找到可用的生成脚本")
    raise RuntimeError("没有可用的贴纸生成后端；请用 --sheet 指定一张现成的六宫格大图")
