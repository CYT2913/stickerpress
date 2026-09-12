# 架构与数据流

三层，从内到外：**装配层（交付基线）→ 产线层（自动化）→ 交互层（易用性）**。

外层可以坏，坏了退回内层照样能交付；内层不能坏。

---

## 1. 分层

```
┌─────────────────────────────────────────────────────────┐
│ 交互层  console/                                         │
│ EdenX + React 19 + TypeScript                            │
│ 浏览器本地：抠图 / 切分 / 刀版 / A5 排版 / 质检 / 下载    │
└───────────────┬─────────────────────────────────────────┘
                │ 规格与策略单向同步
┌───────────────▼─────────────────────────────────────────┐
│ 产线层  engine/stickerpress/                             │
│ 生图 Provider → 三道合规闸 → 色度键抠图 → 连通域切分     │
│ → 异形刀版矢量化 → A5 排版 → 审计报告                    │
│ 依赖：PIL / numpy / scipy + 生图与 VLM 后端              │
└───────────────┬─────────────────────────────────────────┘
                │ 6 张已审核透明资产
┌───────────────▼─────────────────────────────────────────┐
│ 装配层  forge.py + src/sticker_forge/                    │
│ 来源预检 → 权利校验 → 内嵌资产 → A5 SVG → 报告 → 验收   │
│ 依赖：仅 Python 标准库。不联网，不生图，不分析图像内容    │
└─────────────────────────────────────────────────────────┘
```

### 为什么装配层要零依赖

交付物是要送印厂、要花钱的实体。这一层必须：

- 能在任何一台装了 Python 3.9 的机器上跑起来，不用装环境；
- 断网可跑，客户照片不会因为一次库升级就被传到别处；
- 结果可被 `forge.py verify` **独立**复核——验收代码不复用装配代码的几何逻辑，两边都错才会漏。

产线层和交互层都可能因为模型、网络、浏览器而失败；装配层不能。

---

## 2. 数据流

### 2.1 完整产线（engine）

```
用户照片
  ↓  闸1 ingest：EXIF 脱敏 + VLM 审核
  ↓  build_prompt()：主体选材 + 闸2 generation 提示词过滤
  ↓  Provider.generate()   ← 唯一一次生图调用
六宫格大图（真透明 PNG，或品红 #FF00FF 背景）
  ↓  闸3 egress：VLM 复核大图与每一枚
  ↓  chroma.py prepare_rgba()：有 alpha 则直通，否则边缘连通色度键
  ↓  segment.py：alpha 连通域 → 6 枚
  ↓  contour.py：边界追踪 → 形态学外扩 → RDP → Bezier
  ↓  a5_sheet.py：2×3 排版 + CutContour 图层
outputs/：a5-six-stickers.svg + source-original.* + delivery-report.md
```

### 2.2 装配层（forge）

```
用户照片 ──→ load_source()：格式校验 + SHA-256 + 字节级复制
rights.json ─→ 权利校验（缺省即拒绝）→ 不通过则退出码 2，只出报告
6 张资产 ──→ read_size() → spec.fit() → 可选按目标 DPI 居中缩小 → data URI 内嵌
              ↓
         几何硬校验：dpi / 单枚尺寸 / 刀线净距 / 安全边距
              ↓ strict=True 时不达标直接抛错
         a5-six-stickers.svg + manifest.json + delivery-report.md
              ↓
         forge.py verify：独立解析 SVG 复核 10 项
```

`strict=True` 的取舍：宁可不交付，也不交付一份印出来才发现连刀的版。

### 2.3 交互层（console）

浏览器里做的都是**确定性计算**：色度键、切分、刀版、A5 排版、质检、下载。
生图与 VLM 审核仍属服务端职责，不在浏览器里做。

---

## 3. 规格单一真源

同一组数值散落在三层，容易悄悄跑偏。约定：

| 内容 | 真源 | 副本 | 同步方式 |
|---|---|---|---|
| 印刷规格 | `src/sticker_forge/spec.py` | `engine/stickerpress/config.py`<br>`console/src/lib/print/spec.ts` | 单测 `test_spec_parity` 比对 engine 与装配层 |
| 合规策略 | `engine/stickerpress/compliance/policy.yaml` | `console/src/lib/compliance/policy.json` | `python3 engine/tools/sync_policy.py` |
| 示例台纸 | `assets/samples/sample_a5_sheet.svg` | `console/config/public/demo/sticker_sheet_A5.svg` | `cd console && pnpm sync:samples` |

改任何一处规格，必须同步另外两处并跑单测；否则前端说"合格"、后端说"不合格"，最后印厂说"连刀了"。

---

## 4. 关键模块

### 装配层 `src/sticker_forge/`

| 文件 | 职责 |
|---|---|
| `spec.py` | A5 规格、格位计算、等比缩放 fit |
| `imagesize.py` | 零依赖解析 PNG / JPEG / WebP 宽高 |
| `source.py` | 来源照片校验、SHA-256、字节级复制 |
| `rights.py` | 权利声明解析，缺省即拒绝 |
| `assemble.py` | 装配 A5 SVG，可选按目标 DPI 缩小实体尺寸，执行几何硬校验 |
| `verify.py` | 独立复核 SVG，含自写 path 解析 |
| `report.py` | 生成 `delivery-report.md` |

### 产线层 `engine/stickerpress/`

| 模块 | 职责 |
|---|---|
| `config.py` | 规格常量 |
| `pipeline.py` | 端到端编排与质检 |
| `cli.py` | 命令行入口 |
| `imaging/provider.py` | 生图 Provider 抽象（见 [`MODEL_AND_QUOTA.md`](MODEL_AND_QUOTA.md)） |
| `imaging/chroma.py` | 边缘连通色度键 |
| `imaging/segment.py` | alpha 连通域切分 |
| `imaging/contour.py` | 异形刀版矢量化 |
| `layout/a5_sheet.py` | A5 排版与 CutContour 输出 |
| `compliance/policy.yaml` | 策略真源 |
| `compliance/gates.py` | 三道闸 |
| `compliance/reviewer.py` | VLM 审核与输出解包 |
| `compliance/audit.py` | 审计日志 |

---

## 5. 已知取舍

| 取舍 | 理由 | 代价 |
|---|---|---|
| 装配层只做圆角矩形刀线 | 几何必然闭合、不自交、可验证 | 异形轮廓要走产线层 |
| 一次生成六宫格而非六次单图 | 省 6 倍生图额度，风格天然统一 | 一枚不合格要整张重生成 |
| 优先真 alpha、品红色度键降为兜底 | 模型确实能给真透明 PNG，直通质量更好 | 需要额外判别假透明棋盘格 |
| kiss-cut 默认无出血 | 台纸边不参与裁切，出血会让成品超出 A5 | 整切工艺需手动开启 |
| 自写 SVG path 解析而非引库 | 装配层零依赖 | 只支持交付所需的命令子集 |
| 低像素资产只缩小实体尺寸 | 保留原始像素，避免插值制造虚假清晰度 | 成品贴纸会变小，低于单边 20 mm 时拒绝 |

---

## 6. 环境与命令

| 层 | 环境 | 常用命令 |
|---|---|---|
| 装配层 | Python 3.9+，无第三方依赖 | `python3 forge.py --help`<br>`python3 -m unittest discover -s tests -v` |
| 产线层 | Python + PIL/numpy/scipy + 生图/VLM 后端 | `python3 -m engine.stickerpress.cli --help`<br>`python3 engine/tools/redteam_suite.py` |
| 交互层 | Node + pnpm | `cd console && pnpm dev`<br>`pnpm build` / `pnpm sync:samples` |
