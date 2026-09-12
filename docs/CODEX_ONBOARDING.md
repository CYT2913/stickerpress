# 在另一台电脑上让 Codex 接手这个项目

你换了台机器，想让 Codex 继续做这个项目。本文给的是**可以直接复制粘贴的开场白**，以及为什么要那么写。

---

## 0. 最短路径

新机器上装好 Codex CLI，然后：

```bash
git clone https://github.com/CYT2913/stickerpress.git
cd stickerpress
codex
```

进入 Codex 后，粘贴第 3 节的开场白。

> 📌 仓库原名是单个减号 `-`，2026-09-11 改名为 `stickerpress`。旧地址 GitHub 会自动重定向，但请改用新地址。
>
> 如果你在旧机器上还留着叫 `-` 的目录，建议直接删掉重新 clone：`cd -` 在 shell 里的含义是"回到上一个目录"，那个目录名会让你和 Codex 都翻车（本项目开发时踩过）。

---

## 1. 三种 Codex 形态，先选对

| 形态 | 能不能跑通本项目 | 说明 |
|---|---|---|
| **Codex CLI**（终端） | ✅ **推荐** | 能执行 `forge.py`、跑单测、读写本地照片 |
| Codex IDE 扩展 | ✅ | 同上，交互在编辑器里 |
| Codex 云端（ChatGPT 网页里的 Codex） | ⚠️ 部分 | 能直接连 GitHub 仓库改代码，但**拿不到你本地的照片**，也不能把成品 SVG 落到你硬盘上。适合改代码 / 写文档，不适合跑交付 |

三者都**不能生图**。Codex 是编码 Agent，贴纸大图必须你自己在 ChatGPT App 里出——见 [`USE_WITH_CHATGPT_PLUS.md`](USE_WITH_CHATGPT_PLUS.md)。

---

## 2. 新机器准备

```bash
# 1) Codex CLI（Node ≥ 22）
npm install -g @openai/codex
# macOS 也可以：brew install codex

# 2) 用 ChatGPT 账号登录，走你已有的 Plus 订阅，不需要 API Key
codex login          # 选 "Sign in with ChatGPT"

# 3) Python 3.9+ 即可，装配层零第三方依赖
python3 --version

# 4) 拉代码
git clone https://github.com/CYT2913/stickerpress.git
cd stickerpress

# 5) 自检：应该 41 项全过
python3 -m unittest discover -s tests
```

前端操作台是可选的，要用再装：

```bash
cd console && pnpm install && pnpm sync:samples && pnpm dev
```

> 具体命令与参数以你机器上安装的 Codex 版本为准，版本迭代较快。

---

## 3. 开场白（复制这些）

Codex 会自动读取仓库根目录的 `AGENTS.md`，所以**不需要你把规则再背一遍**。开场白只要做三件事：说清你是谁、指路读哪些文件、给一个明确任务。

### 3.1 通用接手（第一次在新机器上用）

```
这是 StickerPress：把用户有权商用的照片做成 A5 六枚纸质贴纸的印前工具。

先按顺序读这几个文件，读完用不超过 200 字告诉我你的理解，先别改代码：
- AGENTS.md（协作纪律与验收红线）
- CONTEXT.md（当前状态、输入输出契约）
- CHANGELOG.md 最近两条
- docs/ARCHITECTURE.md（三层结构）
- docs/PRINT_SPEC.md（印刷硬门槛）

然后跑 `python3 -m unittest discover -s tests`，确认 41 项全过，把结果告诉我。
```

### 3.2 我在 ChatGPT 里一张一张存了 6 枚贴纸（**推荐路线**）

单张保存每枚都能独享导出上限，分辨率远高于六宫格整张，且完全绕开切分环节。

```
我用 ChatGPT 生成了 6 枚贴纸并一张一张保存，目录：<你的贴纸目录>
原始照片：<你的照片路径>

请按 docs/USE_WITH_CHATGPT_PLUS.md 第 2.5 步之后的流程跑一单：
1. 先 `python3 engine/tools/check_alpha.py <贴纸目录>/*.png --single`，
   逐枚确认「真透明」并记录按 56 mm 估算的 dpi；低于 300 时不要硬跑默认布局，
   改用 `forge.py assemble --target-dpi 300`，若所需实体尺寸会低于单边 20 mm 就停下；
2. 读 docs/ARTWORK_CONTRACT.md 核对资产契约（正好 6 个文件、命名补零、
   资产目录不能混进原图）；
3. `python3 forge.py preflight <照片路径>`，把 SHA-256 和格式念给我；
4. 用 `forge.py rights-template` 生成权利声明模板给我，我填完再继续；
5. 我填完后跑 forge.py assemble，输出到 outputs/<订单号>/；低 dpi 资产按第 1 步显式加 `--target-dpi 300`；
6. 最后 `python3 forge.py verify` 独立验收，把结果贴给我。

注意：SVG 由 forge.py 生成，你不要自己写 SVG 或手改导出的 SVG。
照片和成品都不许进 git，输出放 outputs/ 下。
```

### 3.3 我只有一张六宫格大图

只在整张导出分辨率够大（≳2300×3300）时才和 3.2 等价，否则每格只有整图的 1/6，容易卡在 300 dpi 门槛下。

```
我有一张六宫格贴纸大图，路径：<你的大图路径>
原始照片：<你的照片路径>

1. 先 `python3 engine/tools/check_alpha.py <大图路径>`，告诉我三件事：
   是真透明还是「画出来的棋盘格」假透明、dpi 够不够、能不能切出 6/6；
   假透明或切不出 6 张就停下来告诉我，要重新出图，不要硬跑；
2. `python3 forge.py preflight <照片路径>`，把 SHA-256 和格式念给我；
3. 用 engine CLI 的 --sheet 模式喂这张大图，做背景透明化、切分、刀版、A5 排版；
4. 权利声明我还没填，先用 `forge.py rights-template` 生成模板给我，我填完再继续；
5. 最后跑 `python3 forge.py verify` 做独立验收，把 12 项结果贴给我。

背景透明化优先直通真 alpha；只有拿不到 alpha 时才用品红 #FF00FF 色度键兜底。
注意：照片和成品都不许进 git，输出放 outputs/ 下。
```

### 3.4 改印刷规格

```
印厂要求改成 <你的新要求>。

规格在三层都有副本，改的时候三处都要动，别只改一处：
- src/sticker_forge/spec.py（真源）
- engine/stickerpress/config.py
- console/src/lib/print/spec.ts

改完必须：
1. 跑 `python3 -m unittest discover -s tests -v`，TestSpecParity 会卡住不一致；
2. 重新生成示例台纸并 `forge.py verify`；
3. 在 CHANGELOG.md 最上方加一条（只增不改，不要动历史条目）；
4. 把取舍写进 ASSUMPTIONS.md。
```

### 3.5 提交和推送

```
改完之后：
1. 先 `git status`，把要提交的文件列表念给我确认，特别确认没有客户照片、
   没有 outputs/ 里的东西、没有 node_modules、没有 core dump；
2. 我确认后再 commit，中文提交信息，说清"改了什么 + 为什么"；
3. push 之前再问我一次。
```

---

## 4. 为什么开场白要这么写

| 这句话 | 防的是什么 |
|---|---|
| "先读 AGENTS.md / CONTEXT.md，读完先别改代码" | Agent 上来就动手，绕开合规和印刷红线 |
| "跑单测确认 41 项全过" | 环境有问题时，后面所有结论都不可信 |
| "权利声明我还没填，先给模板" | Agent 自作主张把 `commercial_use_granted` 填成 yes |
| "资产目录里不要混进原图" | 装配层按目录收集，多一张就报"需要正好 6 张" |
| "三处规格都要改 + 跑 TestSpecParity" | 前端说合格、后端说不合格，最后印厂说连刀了 |
| "CHANGELOG 只增不改" | Agent 重写历史条目 |
| "commit 前把文件列表念给我确认" | 客户照片、成品、几百 MB 的 core dump 被误提交（本项目真实发生过） |
| "push 之前再问我一次" | 推到公开仓库的东西撤不回来 |

---

## 5. 跨机器同步：git 带不过去的东西

仓库里**只有代码、文档和自制脱敏示例**。以下都在 `.gitignore` 里，换机器要自己处理：

| 东西 | 怎么办 |
|---|---|
| 客户照片、`work/`、`outputs/` | 手动拷贝，或干脆在新机器上重跑。**不要为了同步方便就提交进仓库** |
| `console/node_modules/` | `cd console && pnpm install` |
| `console/config/public/demo/sticker_sheet_A5.svg` | `cd console && pnpm sync:samples`（12MB，仓库只留 `assets/samples/` 一份真源） |
| `engine/samples/redteam/` 红队样本 | `python3 engine/tools/make_redteam_samples.py` 本地重新生成 |
| ChatGPT 出的六宫格大图 | 在新机器上重新出，或从旧机器拷 |

---

## 6. 权限档位：别一上来就全自动

Codex 默认偏保守，需要审批才动你的文件。建议节奏：

1. **只读探路**：用默认档位，让它先读代码、给方案；
2. **确认计划后放权**：跑装配、跑单测这类需要写盘的操作，再提升审批档位（如 `codex -a on-request`，或 `--full-auto` 交给它连续执行）；
3. **push 永远手动确认**：不要把推送纳入自动授权范围。

处理客户照片时尤其别开全自动——文件安全规则（`AGENTS.md` 0.2、0.6）是靠人守住的，不是靠沙箱。

---

## 7. Codex 说"做完了"之后，你自己跑这三条

不要只听 Agent 的结论。

```bash
# 1) 单测
python3 -m unittest discover -s tests

# 2) 独立验收成品（12 项几何检查）
python3 forge.py verify outputs/<订单号>/a5-six-stickers.svg

# 3) 确认没有该提交的东西被提交
git status --short && git log --stat -1
```

再加两件工具**永远做不了**的事：

- **肉眼逐枚看成品**：有没有品牌、Logo、版权角色、可识别人物、二维码、错字；
- **换个目录/换台机器打开那份 SVG**：确认不缺图、不依赖外部资源。

自动验收通过 ≠ 可以下单印刷。
