# 变更记录

本文件只增不改。新条目必须写在最上方。

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

