# 变更记录

本文件只增不改。新条目必须写在最上方。

## 2026-09-12 — 补齐 CODEX_ONBOARDING 的过期内容

- 上两条改动漏改了 `docs/CODEX_ONBOARDING.md`（用户发现）：开场白里仍写"我已经用 ChatGPT 生成了一张**品红背景**的六宫格大图"，与"优先真透明、品红降为兜底"的新结论矛盾；单测数量三处仍写 24。
- 3.2 / 3.3 两套开场白按新结论对调优先级：3.2 改为**单张保存路线（推荐）**，3.3 为六宫格整张路线并注明仅在整张导出 ≳2300×3300 时与 3.2 等价。
- 两套开场白都前置 `check_alpha.py` 自检步骤（单张用 `--single`），并要求"假透明或切不出 6 张就停下来，不要硬跑"。
- 3.2 开场白补入一句硬约束：**"SVG 由 forge.py 生成，你不要自己写 SVG 或手改导出的 SVG"**——防止接手的 Codex 把印前文件当成可以生成的内容，凭空编出不闭合刀线与虚假 dpi。
- 单测数量三处 24 → 35。

## 2026-09-12 — check_alpha 支持单枚模式并前置 dpi 预警，补「单张存还是整张存」结论

- `engine/tools/check_alpha.py` 新增 `--single`：每个文件按一枚独立贴纸判定。此前该工具默认把输入当六宫格，检查"一张一张保存"的单枚贴纸时会误报 `1 / 6 张 ❌`——上一条改动推荐单张路线后，这个误报会直接把人劝退。
- 同一工具新增 **dpi 上限预警**，在透明度结论之前就给出"按单枚 56 mm 估算的有效 dpi"及是否过 300 门槛。措辞明确标注是上限（产线按主体外接框裁切后实际更低），避免给出虚假信心。
- `docs/USE_WITH_CHATGPT_PLUS.md` 新增「第 2.5 步：一张一张存，还是 6 张一起存？」。实测同一批素材：单张各 1024×1024 → **505 dpi、自动验收全过**；六宫格整张 1024×1536 → **204.8 dpi、低于 300 门槛不可印**，差约 2.5 倍。结论是优先单张保存（每枚独享导出上限，且完全绕开切分粘连风险），仅当整张导出本身 ≳2300×3300 时两者等价；同时记录单张路线的三个坑：必须正好 6 个文件且与原图分目录、文件名要补零否则格位乱序、需逐枚确认 alpha 未被拍平。

## 2026-09-12 — 修复真透明 PNG 被色度键毁掉，品红背景降为兜底

### 修复（严重）

- `engine/stickerpress/pipeline.py` 原先**无条件**调用 `key_out()`，而 `key_out()` 内部 `image.convert("RGB")` 会直接丢掉输入的 alpha 通道。后果：用户拿到的真透明六宫格 PNG 进产线后背景变不透明，六枚贴纸粘成**一个**连通域，只能切出 1 张，作业失败。
- 起因是早期假设"模型给不出真 alpha，只会把棋盘格画出来"。实测证伪：ChatGPT 贴纸导出的 PNG **确实带真 alpha**，查看器里那层灰白棋格只是底衬，不是文件内容。
- 前端 `console/src/lib/pipeline.ts` 早已有 `hasUsableAlpha()` 分支，行为本来就是对的；这次是 Python 产线补齐，两侧对齐。

### 变更

- `imaging/chroma.py` 新增统一入口 `prepare_rgba()`：先检测可用 alpha，有则**直通**（`mode="alpha"`，不做任何色度键），没有才退回品红色度键（`mode="chroma"`）。真 alpha 直通没有溢色抑制与阈值损失，边缘更干净，连通域切分更准。
- 新增 `alpha_stats()`、`has_usable_alpha()`：按**实际透明像素比例**判断，而非通道是否存在（RGBA 恒有第 4 通道，存在性不说明任何问题）。
- 新增 `looks_like_painted_checkerboard()`：识别"画出来的棋盘格"这类假透明。这种图既没有 alpha 也键不掉，且格子会被原样印在纸上，只能重出图，因此在质检阶段就要拦住并给出明确提示。
- `KeyResult` 新增 `mode` 字段；`pipeline` 报告新增「背景透明化方式」「背景透明像素占比」两行，保留旧字段 `chroma_background_ratio` 兼容。
- 前端 `chroma.ts` 抽出 `transparentRatio()`，`pipeline.ts` 新增 `backgroundMode`，质检项标签按模式区分显示（`透明背景占比（alpha 直通）` / `色度键背景占比（品红兜底）`），不再对 alpha 输入显示"色度键占比 0.0%"这种误导数字。

### 新增

- `engine/tools/check_alpha.py`：出图后先跑它。对任意图片给出四类结论（真透明 / 假透明棋盘格 / 品红可键 / 普通不透明图）、产线实际会走哪条路、以及**能切出几枚**。看到 `6/6` 才算稳。
- `tests/test_imaging_alpha.py`：11 条回归，含一条固化那个 bug 现场的测试（直接 `key_out()` 真透明图会切不出 6 张），防止以后有人把 pipeline 改回去。依赖 PIL/numpy/scipy，缺依赖时整体 skip，不影响装配层零依赖测试。单测总数 24 → 35。

### 文档

- `docs/USE_WITH_CHATGPT_PLUS.md` 提示词从"**必须**品红背景、不要透明背景"改为"**首选**直接要透明背景"，品红移到「第 1.5b 步（可选兜底）」；新增「第 1.5 步：花 2 秒确认是真透明还是假透明」。
- `docs/ARTWORK_CONTRACT.md` 第 3 节重写为路线 A（真 alpha，首选）/ 路线 B（品红，兜底）/ 必须排除的假透明。
- `docs/ARCHITECTURE.md` 数据流与取舍表同步；`ASSUMPTIONS.md` 旧条目标注"已部分失效"并新增 9-12 条目。

### 实测

- 真透明六宫格 2400×3600 → alpha 直通、透明占比 59.2%、切 6/6、最低 399.8 dpi、刀版净距 12.49 mm。
- 同一张图合成到品红底 → 色度键、占比 59.2%、切 6/6，几何结果与上面完全一致，兜底路径无回归。
- 假透明棋盘格 → 正确判定并拦下，切分 1/6（预期失败）。

## 2026-09-11 — 仓库改名为 stickerpress

- GitHub 仓库由 `CYT2913/-` 改名为 `CYT2913/stickerpress`。原名是单个减号，`cd -` 在 shell 里表示"回到上一个目录"，clone 下来的目录名会让人和 Agent 同时踩坑（见下一条 9-11 记录）。
- 新地址：`https://github.com/CYT2913/stickerpress`。GitHub 会为旧地址保留重定向，旧的 clone / remote 暂时仍可用，但请尽快切换。
- 已有本地副本切换 remote：`git remote set-url origin https://github.com/CYT2913/stickerpress.git`。
- 同步更新 `README.md`（新增 clone 步骤）、`docs/CODEX_ONBOARDING.md`、`docs/USE_WITH_CHATGPT_PLUS.md` 中的仓库地址；clone 命令不再需要手动指定目录名。

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

