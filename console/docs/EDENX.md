<!-- 此文件由 EdenX 自动生成，请勿手动编辑，修改将在下次更新时丢失 -->

# EdenX 开发指南

> 本指南面向熟悉 React 生态的开发者和 AI Agent，详细介绍了 EdenX 的核心概念、配置方式以及与底层技术栈（Rspack、Rsbuild、Hono）的关系，帮助你快速理解如何使用 EdenX 构建高性能的全栈 React 应用。

> 如需更详细的内容，可以参考 [EdenX 官方文档索引](https://edenx.bytedance.net/llms.txt) 查询完整的官网文档。

## ⚠️ 关键约束

在开始使用本文档前，**必须遵守**以下约束。

### 🚫 禁止操作（红线规则）

**1. 禁止绕过框架机制**

- ❌ 禁止使用自行搭建的服务框架运行 EdenX 产物
  - EdenX 内置完整的 Web Server（基于 Hono）
  - 本地预览构建产物**必须**通过 `edenx serve` 命令运行
- ❌ 禁止直接修改 `node_modules` 中的代码

**2. 禁止不安全的版本管理**

- ❌ 禁止使用 `^` 或 `~` 等语义化版本范围
- ❌ 禁止部分升级官方包（必须统一版本号）

### 📋 必须操作（强制要求）

**1. 必须查阅文档**

- ✅ 本文档部分内容附有 EdenX 官网文档链接，执行相关操作前，**必须先完全理解文档内容**
- ✅ 遇到未知配置项时，必须查阅官方文档而非猜测

**2. 必须遵循代码约定**

- ✅ 文件命名必须遵循框架约定（如路由文件命名规则）
- ✅ 导出格式必须符合框架要求（如 API 路由必须导出特定方法）

### 🔍 优先级规则

**1. 优先选择方案**

1. **框架内置方案** > 第三方库 > 自定义实现
2. **官方推荐方案** > 社区方案 > 个人方案
3. **约定优于配置** > 显式配置 > 代码实现

---

## 框架概述

- EdenX 是**基于 React 的全栈 Web 开发框架**。
- EdenX 整合了多个 Web 框架的最佳实践，将通用能力下沉为统一的工程框架，通过开箱即用的方式解决这些问题。
- EdenX 通过**分层架构**将复杂度从开发者手中转移到框架层：

```
┌─────────────────────────────────────┐
│  应用层: React 19 + React Router 7   │  ← UI 和客户端路由
├─────────────────────────────────────┤
│  服务层: Hono.js                     │  ← BFF 和 Web Server 运行时
├─────────────────────────────────────┤
│  构建层: Rsbuild                     │  ← 统一的构建接口
├─────────────────────────────────────┤
│  打包层: Rspack                      │  ← 底层打包器
└─────────────────────────────────────┘
```

---

## 技术栈关系

### Rspack

EdenX **使用** Rspack 作为打包器，提供 5-10 倍于 Webpack 的编译性能

### Rsbuild

Rsbuild 是**构建工具层**，位于框架和打包器之间。EdenX 内部对 Rsbuild 做了封装，所有构建能力都由 Rsbuild 提供。

### React 和 React Router

EdenX 使用 React 19 构建用户界面，使用 React Router 7 处理客户端路由。

### Hono

EdenX 使用 Hono 作为 [BFF](https://edenx.bytedance.net/guides/advanced-features/bff.md) 和 [Web Server](https://edenx.bytedance.net/guides/advanced-features/web-server.md#%E6%96%B9%E5%BC%8F%E4%B8%80%E9%80%9A%E8%BF%87%E9%85%8D%E7%BD%AE%E6%89%A9%E5%B1%95-web-server) 的运行时框架，允许通过 Hono 中间件扩展项目服务端能力。

---

## 工作流原则

**优先复用已有 SKILL 与 Command，避免自行实现工作流**

在以下场景中，**如果已经存在内置能力，则不得自行推断或重建流程**：

- 🆕 **新增功能**：必须优先查找并使用 `edenx:new-v3`
- 🔄 **升级项目**：必须优先查找并使用 `edenx:upgrade`

> 说明：内置 SKILL / Command 已封装标准流程与最佳实践，禁止重复实现或绕过使用。

---

## 常用命令

> 📖 参考文档：[Commands](https://edenx.bytedance.net/apis/app/commands.md)

EdenX 提供了一组内置命令来管理项目的开发、构建和本地预览流程。

```bash
# 1. 开发
edenx dev

# 2. 构建
edenx build

# 3. 预览（需先 build）
edenx serve

# 4. 本地模拟生产环境运行
edenx build && edenx serve
```

---

## 项目结构

EdenX 项目的基本目录结构：

```
.
├── api/                         # （可选）BFF API 目录
├── config/                      # （可选）额外配置目录
├── src/
│   ├── routes/                  # 约定式路由目录
│   │   │                        # 文件结构映射为 URL 路径
│   │   ├── layout.tsx           # 根布局组件，包裹所有子路由
│   │   ├── page.tsx             # 首页组件，对应 / 路由
│   │   └── index.css            # 样式文件
│   ├── edenx-app-env.d.ts       # EdenX 自动生成的类型声明文件
│   └── edenx.runtime.ts         # 运行时配置（路由、状态管理等）
├── edenx.config.ts              # EdenX 主配置文件
├── tsconfig.json                # TypeScript 配置
├── package.json                 # 项目依赖和脚本
├── pnpm-lock.yaml               # 依赖锁定文件
├── biome.json                   # Biome 配置（代码格式化和 Lint）
└── README.md                    # 项目说明文档
```

---

## 配置文件

> 📖 参考文档：[Configuration Usage](https://edenx.bytedance.net/configure/app/usage.md)

`edenx.config.ts` 是 EdenX 项目的**核心配置文件**，位于项目根目录。

### 主要配置分类

| 配置分类      | 作用                                                      |
| ------------- | --------------------------------------------------------- |
| `source`      | 源代码相关配置（入口、别名、编译选项等）                  |
| `output`      | 构建产物相关配置（输出目录、文件名、压缩、Source Map 等） |
| `server`      | 服务器相关配置（端口、SSR、路由等）                       |
| `dev`         | 开发服务器配置（端口、代理、HMR 等）                      |
| `html`        | HTML 模板配置（标题、meta、注入脚本等）                   |
| `tools`       | 底层工具配置（Rspack、Babel、PostCSS 等）                 |
| `runtime`     | 运行时配置（路由、状态管理等）                            |
| `performance` | 性能优化配置（代码分割、预加载等）                        |
| `plugins`     | 插件注册                                                  |

### 插件配置

> 📖 参考文档：[Plugin System](https://edenx.bytedance.net/plugin/plugin-system.md) | [CLI Plugin API](https://edenx.bytedance.net/plugin/cli-plugins/api.md) | [builderPlugins](https://edenx.bytedance.net/configure/app/builder-plugins.md)

EdenX 支持**三种类型的插件**，通过不同的配置字段注册：

- 通过 `plugins` 字段注册 EdenX 插件
- 通过 `builderPlugins` 字段注册 Rsbuild 插件
- 通过 `tools.rspack` 注册 Rspack 插件

---

## 核心依赖

### `@edenx/app-tools`

- CLI 命令（`edenx dev`、`edenx build` 等）
- 配置解析和插件加载
- 集成 Rsbuild，提供构建能力
- 集成 EdenX Server，提供开发和生产服务器

### `@edenx/runtime`

运行时核心包，提供客户端和服务端的运行时能力。

- React 组件和 Hooks（`createRoot`、`render` 等）
- 路由相关功能（从 `@edenx/runtime/router` 导入）

---

## 常用概念

### 项目入口系统

> 📖 参考文档：[Page Entry](https://edenx.bytedance.net/guides/concept/entries.md)

EdenX 使用**基于约定的入口系统**，框架会根据文件结构自动发现入口点。

#### 什么是入口

> 📖 参考文档：[入口概念](https://edenx.bytedance.net/guides/concept/entries.md#%E5%8D%95%E5%85%A5%E5%8F%A3%E4%B8%8E%E5%A4%9A%E5%85%A5%E5%8F%A3)

- 入口代表一个独立的 HTML 页面，每个入口有自己的路由、页面和构建输出
- 框架扫描 `src/` 目录，根据约定的目录结构识别入口
- 自动生成包装后的入口文件到 `node_modules/.edenx/[入口名]/index.js`

> 💡 **重要**：你在 `src/` 中定义的入口文件（如 `App.tsx` 或 `routes/`）不是直接的构建入口，而是被 EdenX 自动生成的入口代码所引用和包装，以便注入框架功能。

#### 入口类型

> 📖 参考文档：[约定式路由入口](https://edenx.bytedance.net/guides/basic-features/routes.md) 和 [配置式入口](https://edenx.bytedance.net/configure/app/source/entries.md)

EdenX 支持两种入口定义方式，默认情况下使用**约定式路由入口**。

#### 自定义入口

> 📖 参考文档：[source.enableCustomEntry](https://edenx.bytedance.net/configure/app/source/enable-custom-entry.md) | [entry.tsx](https://edenx.bytedance.net/apis/app/hooks/src/entry.md)

当需要**完全控制**应用的渲染过程时，可以创建自定义入口文件。在入口目录下创建 `entry.[jt]sx` 文件，EdenX 将不再自动控制渲染：

### 数据获取

> 📖 参考文档：[数据获取](https://edenx.bytedance.net/zh/guides/basic-features/data/data-fetch.md)

EdenX 提供了**基于路由的数据加载机制**，通过 Data Loader 在组件渲染前自动获取数据。

#### Data Loader

**用途：** 在路由组件渲染前获取所需数据，支持 SSR 和 CSR 应用。

- 每个路由组件（`layout.tsx`、`page.tsx`、`$.tsx`）可以有同名的 `.data` 文件
- 在 `.data` 文件中具名导出 `loader` 函数
- 在组件中通过 `useLoaderData()` Hook 获取数据

**执行环境：**

- **CSR 应用**：`loader` 在客户端执行
- **SSR 应用**：`loader` 仅在服务端执行（首屏和路由切换时）

#### 降级机制

> 📖 参考文档 [SSR 降级](https://edenx.bytedance.net/guides/basic-features/render/ssr.md#ssr-%E9%99%8D%E7%BA%A7)

当服务端 `loader` 执行出错时，框架自动降级为 CSR 模式并重新请求数据。可通过 `server.ssr.loaderFailureMode` 配置降级策略。

#### Client Loader

**用途：** 在 SSR 应用中提供仅在客户端执行的数据加载逻辑，减少某些场景下对服务端的额外转发。

**文件约定：** 创建 `.data.client` 文件并具名导出 `loader`

**触发时机：**

- 服务端 Data Loader 报错降级时
- 浏览器端路由切换时

---

## 相关资源

- 📚 [EdenX 官方文档](https://edenx.bytedance.net/llms.txt)
- 🔧 [Rsbuild 文档](https://rsbuild.dev/llms.txt)
- ⚡ [Rspack 文档](https://rspack.dev/llms.txt)
- 🔥 [Hono 文档](https://hono.dev/llms.txt)
- 🛣️ [React Router 文档](https://reactrouter.com/home)
