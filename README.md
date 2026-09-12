# StickerPress — 照片转 A5 六枚纸质贴纸

把一张用户**有权商用**的照片，做成可直接交给数码模切店的 **A5 纸质贴纸版**：一张 148 × 210 mm 的自包含 SVG，含 6 枚独立贴纸和 `CutContour` kiss-cut 刀线图层，外加原图字节级副本与交付报告。

灵感来自 ChatGPT App 的 Stickers 功能，但本项目解决的是它不解决的那一段：**印前**。生成模型只负责画，排版、刀线、间距、安全边距、合规复检必须在几何和流程里可核查。

---

## 1. 仓库结构

```
.
├─ forge.py                 # 零依赖装配器 CLI（预检 / 权利模板 / 装配 / 验收）
├─ src/sticker_forge/       # 装配器实现，仅用 Python 标准库，不联网、不生图
├─ tests/                   # 离线单元测试（41 项）
├─ engine/                  # 完整 Python 产线（生图 + 合规 + 抠图 + 切分 + 刀版）
│  ├─ stickerpress/         # 主包
│  ├─ tools/                # 策略同步、红队样本、红队回归
│  └─ samples/              # 红队对抗样本（图片，本地生成，不入库）
├─ console/                 # Web 操作台（EdenX + React 19 + TypeScript）
├─ assets/samples/          # 脱敏示例：A5 台纸 SVG、预览 PNG、6 枚贴纸 PNG
├─ docs/                    # 印刷规格、视觉资产契约、合规、模型与额度
├─ AGENTS.md CONTEXT.md CHANGELOG.md ASSUMPTIONS.md
└─ outputs/                 # 正式交付（已 gitignore，不入库）
```

三层的关系：

| 层 | 位置 | 是否联网 | 职责 |
|---|---|---|---|
| 装配层 | `forge.py` + `src/sticker_forge/` | 否 | 收 6 张已审核透明资产 → 出可交付 A5 SVG + 报告 + 自动验收 |
| 产线层 | `engine/` | 是（生图 / VLM 审核） | 生成六宫格大图、三道合规闸、色度键抠图、连通域切分、异形刀版 |
| 交互层 | `console/` | 浏览器本地计算 | 上传、参数、抠图切分排版预览、质检、下载 |

装配层是**交付基线**：无第三方依赖、可离线运行、结果可被 `forge.py verify` 独立复核。产线层和交互层是提效工具，不能绕过装配层的几何校验。

---

## 2. 快速开始

环境：Python 3.9+，装配层无第三方依赖。

```bash
git clone https://github.com/CYT2913/stickerpress.git
cd stickerpress
python3 -m unittest discover -s tests   # 自检：41 项应全过
```

```bash
# 1) 只做来源预检：校验格式、记录 SHA-256，不产出文件、不联网
python3 forge.py preflight /path/to/photo.jpg

# 2) 生成权利声明模板
python3 forge.py rights-template > rights.json   # 按实填写

# 3) 提供 6 张已人工复核的透明贴纸资产，装配正式交付
python3 forge.py assemble /path/to/photo.jpg \
  --artwork-dir /path/to/six-artworks \
  --rights rights.json \
  --outdir outputs/order-001 \
  --order-id order-001 \
  --target-dpi 300

# 4) 独立验收任意 A5 SVG（可用于复核别人给的文件）
python3 forge.py verify outputs/order-001/a5-six-stickers.svg
```

`--target-dpi` 可选。传入 300 或 400 后，低像素贴纸会按比例缩小实体尺寸直至达到目标 DPI；不会插值放大，也不会突破任一方向 20 mm 的硬下限。不传时保持原有版面行为。

`assemble` 成功后 `outputs/order-001/` 含：

- `a5-six-stickers.svg` — 自包含 A5 SVG，位图以 data URI 内嵌；
- `source-original.<ext>` — 原图字节级副本，SHA-256 与输入一致；
- `delivery-report.md` — 规格、位置尺寸、哈希、合规检查、假设；
- `manifest.json` — 机读清单。

权利声明缺失或写成 `unknown` / `待确认` 时，`assemble` 以退出码 2 拒绝，只产出说明性报告，不产出印刷文件。

### 测试

```bash
python3 -m unittest discover -s tests -v
```

改动 `src/sticker_forge/`、`forge.py`、交付规格或权利校验逻辑后**必须**跑全部单测。

### 完整产线与 Web 操作台

```bash
# 产线 CLI（需要生图与 VLM 后端）
python3 -m engine.stickerpress.cli --help

# 合规策略同步到前端
python3 engine/tools/sync_policy.py

# Web 操作台
cd console && pnpm install && pnpm dev
cd console && pnpm sync:samples   # 同步示例台纸到 demo 资源
```

---

## 3. 印刷规格（硬门槛）

| 项目 | 规范 |
|---|---|
| 成品画布 | A5 竖版 148 × 210 mm，kiss-cut 默认无出血 |
| 贴纸数量 | 正好 6 枚 |
| 安全边距 | 四边 ≥ 10 mm |
| 贴纸最小净距 | ≥ 8 mm（含刀线） |
| 单枚尺寸 | 建议 22–62 mm，任一方向不得 < 20 mm |
| 刀线 | 独立 `CutContour` 图层，`#FF00FF`，0.25 pt（≈0.0882 mm），闭合路径 |
| SVG | 自包含，不依赖任何本地或远程外部位图 |
| 有效分辨率 | 400 dpi 基准，A5 约 2331 × 3307 px |

细节与常见印厂差异见 [`docs/PRINT_SPEC.md`](docs/PRINT_SPEC.md)。

---

## 4. 合规

三道闸：**输入照片预检 → 选材/提示词过滤 → 成品人工复检**，`fail-mode` 默认 `review`，权利声明缺省即拒绝。

不复现：商标、品牌名、Logo、产品包装、版权角色、盲盒手办形象、景区吉祥物、文创设计、票券二维码、车牌、联系方式等隐私标识；授权不明的可识别人物、现代受保护建筑与艺术装置一律替换或剔除，不用免责声明代替处理。

完整口径见 [`docs/COMPLIANCE.md`](docs/COMPLIANCE.md)；视觉资产的交付要求见 [`docs/ARTWORK_CONTRACT.md`](docs/ARTWORK_CONTRACT.md)。

> 本项目能识别并降低常见风险，**不能替代**权利审查与法律意见。需要法定授权的内容一律标记为“需用户确认”。

---

## 5. 生图模型与额度

产线默认调用平台内置图像能力（Provider 标签 `platform-image-edit`），底层默认模型为 `image-gen`，可由环境变量覆盖。**Codex 订阅不是图片额度包**，能出多少张取决于所用图像服务的独立限额。一次成功作业通常只消耗 1 次生图调用，产出 1 张 A5 台纸 = 6 枚贴纸。

详细链路、覆盖方式和额度换算见 [`docs/MODEL_AND_QUOTA.md`](docs/MODEL_AND_QUOTA.md)。

**只有 ChatGPT Plus、没有 API 额度**也能跑通：在 ChatGPT 里人工出一张六宫格大图，再用 `--sheet` 走本地装配，全程零 API 花费。步骤和提示词模板见 [`docs/USE_WITH_CHATGPT_PLUS.md`](docs/USE_WITH_CHATGPT_PLUS.md)。

大图**首选带真 alpha 的透明 PNG**（ChatGPT 贴纸导出的通常就是），拿不到 alpha 才退回品红 `#FF00FF` 底走色度键。进产线前先花 2 秒确认是真透明还是"画出来的棋盘格"假透明：

```bash
python3 engine/tools/check_alpha.py <大图路径>   # 看到「真透明」+「6 / 6 张」才算稳
```

---

## 6. 文件安全

- 客户照片、成品位图、SVG 导出物、订单文件**不得**提交到版本库；`work/`、`outputs/` 已在 `.gitignore` 中。
- 仓库内仅保留 `assets/samples/` 下经脱敏、显式命名的示例资源。
- `CHANGELOG.md` 只增不改，新条目写在最上方。
- 每次产出的假设记录在 `ASSUMPTIONS.md` 或交付报告中。

---

## 7. 文档索引

- [`AGENTS.md`](AGENTS.md) — Agent 协作纪律与验收红线
- [`CONTEXT.md`](CONTEXT.md) — 当前状态与输入/输出契约
- [`CHANGELOG.md`](CHANGELOG.md) — 变更记录（只增不改）
- [`ASSUMPTIONS.md`](ASSUMPTIONS.md) — 假设、依据与返工成本
- [`docs/PRINT_SPEC.md`](docs/PRINT_SPEC.md) — 印刷与 SVG 规格
- [`docs/ARTWORK_CONTRACT.md`](docs/ARTWORK_CONTRACT.md) — 六张插画资产的交付契约
- [`docs/COMPLIANCE.md`](docs/COMPLIANCE.md) — 合规策略与三道闸
- [`docs/MODEL_AND_QUOTA.md`](docs/MODEL_AND_QUOTA.md) — 生图模型链路与额度换算
- [`docs/USE_WITH_CHATGPT_PLUS.md`](docs/USE_WITH_CHATGPT_PLUS.md) — 只有 ChatGPT Plus 时怎么跑通（含提示词模板）
- [`docs/CODEX_ONBOARDING.md`](docs/CODEX_ONBOARDING.md) — 换台电脑后怎么让 Codex 接手（含开场白模板）
- [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md) — 三层架构与数据流
