# 变更记录

本文件只增不改。新条目必须写在最上方。

## 2026-09-11 — 新增跨机器 Codex 接手指南

- 新增 `docs/CODEX_ONBOARDING.md`：换电脑后让 Codex 接手本项目的完整说明，含五套可直接粘贴的开场白（通用接手 / 从 ChatGPT 大图跑一单 / 已有 6 张资产 / 改规格 / 提交推送）、每句话防的是什么、跨机器 git 带不过去的东西清单、权限档位建议、人工验收清单。
- 记录 clone 陷阱：仓库名是单个减号 `-`，必须 `git clone https://github.com/CYT2913/-.git stickerpress` 指定目录名，否则 `cd -` 会被 shell 解释为"回到上一个目录"。
- `README.md` 文档索引补入该文。

## 2026-09-10 — 修复 CLI 规格漂移与位图重复内嵌，补 ChatGPT Plus 使用路径

### 修复

- **`engine/stickerpress/cli.py` 的规格漂移**：`--bleed` 默认仍是 `3.0`、`--gutter` 默认仍是 `6.0`，会在运行时覆盖已对齐的 `SheetSpec`，导致命令行跑出来的其实是 154 × 216 mm、6 mm 间距的旧版面——上一次的规格统一在 CLI 这一层是失效的。现改为从 `SheetSpec` 取默认值，改一处即全链路生效。
- **每张位图被内嵌两份**：`<image>` 同时写 `xlink:href` 和 SVG2 的 `href`，两个属性各存一份完整 data URI，文件体积凭空翻倍。示例台纸 11.97 MB → 6.05 MB，前端构建产物 15.2 MB → 9.0 MB。三层（装配层 / engine / console）一并修正，只保留 Illustrator 与印厂 RIP 都认的 `xlink:href`。新增单测按 base64 载荷计数卡住回归。

### 新增

- `docs/USE_WITH_CHATGPT_PLUS.md`：只有 ChatGPT Plus、没有 API 额度时的完整跑通路径。含订阅关系澄清（Codex 含在 Plus 内、Plus 不含 API）、品红六宫格提示词模板、分辨率换算表、`--sheet` 本地装配命令、三条路线成本对比。全流程已实测。
- 单测增至 24 项。

### 变更

- `assets/samples/stickers/*.png` 由 500 px 缩略图替换为示例台纸真正内嵌的印刷级资产（690–883 px）。此前仓库里的示例贴纸与示例台纸并非同一批文件，照着跑复现不出 400 dpi 的结果；现在两者一致，实测 `forge.py assemble` 可直接产出最低 400 dpi、自动验收全过的交付。

## 2026-09-10 — 并入完整产线与操作台，统一印刷规格，补齐文档

### 新增

- 并入 `engine/`：完整 Python 产线，含生图 Provider 抽象、三道合规闸（ingest / generation / egress）、边缘连通色度键抠图、alpha 连通域切分、异形刀版矢量化、A5 排版与审计报告；附 `engine/tools/` 的策略同步与红队回归工具、`engine/samples/redteam/` 对抗样本。
- 并入 `console/`：EdenX + React 19 + TypeScript 操作台，在浏览器本地完成抠图、切分、刀版、A5 排版、质检与下载；新增 `scripts/sync-samples.mjs` 与 `pnpm sync:samples`。
- 新增 `assets/samples/`：脱敏示例台纸 SVG、预览 PNG 与 6 枚贴纸资产，按新规格重新生成。
- 新增文档：`docs/PRINT_SPEC.md`、`docs/COMPLIANCE.md`、`docs/MODEL_AND_QUOTA.md`、`docs/ARCHITECTURE.md`、`ASSUMPTIONS.md`；重写 `README.md` 与 `CONTEXT.md`；扩写 `docs/ARTWORK_CONTRACT.md`。
- 单测增至 23 项，新增 engine 与装配层的规格一致性比对。

### 修复

- **刀线线宽单位错误**：此前写作 `0.25 mm`（≈0.7087 pt），比 `AGENTS.md` 要求的 0.25 pt 粗约 2.8 倍，RIP 可能按印刷线条处理或按粗线中心偏移下刀。现统一为 `0.25 pt = 0.0882 mm`，并进单测。
- **`verify.py` 包围盒解析错误**：原实现把 SVG path 中所有数字按 `(x, y)` 成对取，将 arc 的半径与 flag 误当坐标，导致自身产出的合格文件被判净距 0.00 mm、安全边距 -36.40 mm。改为手写 `_path_points()`，支持 `M/L/H/V/C/S/Q/T/A/Z` 的绝对与相对命令，arc 只取终点。

### 规格对齐（三层统一到 `AGENTS.md` 0.3）

| 项 | 原值 | 现值 |
|---|---|---|
| 画布 | 154 × 216 mm（3 mm 出血） | 148 × 210 mm，kiss-cut 默认无出血 |
| 安全边距 | 6 mm | 10 mm |
| 刀线最小净距 | 3 mm | 8 mm |
| 刀线线宽 | 0.25 mm | 0.25 pt（0.0882 mm） |
| 单枚尺寸 | 未约束 | 建议 22–62 mm，硬下限 20 mm |

裁切标记改为仅在 `bleed > 0` 时输出。合规策略升至 `2026.09-r3`，`min_knife_gap_mm` 由 3.0 改为 8.0。

### 说明

- 生图链路澄清：`GenerationResult.model` 的 `platform-image-edit` 是调用入口标签，底层默认模型为 `image-gen`，可由 `AIME_MULTIMODAL_NAME` 覆盖；装配层与生图完全无关。详见 `docs/MODEL_AND_QUOTA.md`。
- `.gitignore` 为 `assets/samples/` 与 `console/config/public/demo/` 开放例外，仅限自制脱敏素材；客户文件仍一律走被忽略的 `work/` 与 `outputs/`。

## 2026-09-09 — 实现可交接的本地装配产线

- 新增 `forge.py` 与 `src/sticker_forge/`：提供来源预检和六资产 A5 SVG 装配命令，无网络或生图服务依赖。
- 新增 `docs/ARTWORK_CONTRACT.md`：约束视觉 Agent 的权利确认、选材、资产命名与商用复检流程。
- 新增离线单元测试：验证原图字节保全、6 枚 SVG/刀线计数、资源内嵌和不安全权利声明拦截。
- 默认采用可验证的圆角矩形 kiss-cut；异形刀线须经新增验证逻辑后才能支持。

## 2026-09-09 — 初始化生产与合规契约

- 新增项目级 `AGENTS.md`：定义 A5 六枚贴纸、SVG 刀线、原图保全、隐私保护、商用合规和验收门槛。
- 新增 `CONTEXT.md`：记录当前未收到照片、无自动化产线的真实状态及后续输入/输出契约。
- 采用保守合规策略：不复现品牌、角色、隐私信息、受保护的现代地标或授权不明的可识别人物。

