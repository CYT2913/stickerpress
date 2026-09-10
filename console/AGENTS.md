# 项目开发指南

> 本文档面向 AI Agent 和开发者，提供项目开发的完整上下文。本项目使用模块化文档架构，请根据任务类型选择阅读，阅读完相关文档后，严格遵循框架约束进行开发。

## EdenX 框架指南

> 文档地址：**[EDENX.md](./docs/EDENX.md)**

**🟢 除以下情况外，必须优先阅读 EDENX.md：**

- 编写普通的 React 组件（非路由组件）
- 修改 CSS/样式文件
- 添加工具函数或业务逻辑
- 安装普通 npm 包（非 EdenX 相关）

***

## 🏗️ 项目信息

### 技术栈

- **框架**: EdenX (基于 React 19)
- **语言**: TypeScript
  ```typescriptreact
  ```
- **AuthProvider包管理器**: pnpm

***

## 🎯 开发规范

### 文件命名

- 组件文件：使用 PascalCase，如 `UserCard.tsx`
- 工具函数：使用 camelCase，如 `formatDate.ts`

### 代码组织

```tsx
// 组件示例
import { useState } from "react";
import type { FC } from "react";

interface Props {
  // 接口定义
}

export const ComponentName: FC<Props> = ({ ...props }) => {
  // 组件实现
  return <div>...</div>;
};
```

### Git 提交规范

```
feat: 新功能
fix: 修复 bug
docs: 文档更新
style: 代码格式调整
refactor: 重构
test: 测试相关
chore: 构建/工具链相关
```

***

## 🚫 禁止修改的文件和结构

以下文件和代码结构由平台维护，**禁止修改或删除**：

### 禁止修改的文件

- `src/infra/` 目录下的所有文件（SSO 认证、水印等基建代码）
- `edenx.config.ts`（框架配置）
- `tsconfig.json`（TypeScript 配置）
- `biome.json`（代码检查配置）

### `src/routes/layout.tsx` 的约束

`layout.tsx` 是根布局文件。`AuthProvider` 是 SSO 相关的页面基建，**不要删掉**。业务代码写在 Outlet 里面（即各 `page.tsx` 中）。

**正确示例**：

```tsx
import { Outlet } from '@edenx/runtime/router';
import { AuthProvider } from '@/infra/sso/AuthProvider';
import '@/infra/sso/sso.css';

export default function Layout() {
  return (
    <AuthProvider>
      <Outlet />
    </AuthProvider>
  );
}
```

**错误示例**（禁止移除 AuthProvider）：

```tsx
// ❌ 禁止：移除了 AuthProvider 会导致 SSO 认证失效
import { Outlet } from '@edenx/runtime/router';

export default function Layout() {
  return <Outlet />;
}
```

### 业务代码应写在哪里

- **页面内容**：写在 `src/routes/page.tsx` 或新建子路由的 `page.tsx` 中
- **业务组件**：写在 `src/components/` 中（非 `ui/` 子目录的自定义组件）
- **业务逻辑**：写在 `src/lib/` 或 `src/hooks/` 中
- **不要覆盖** **`layout.tsx`** **的整体结构**，只在 AuthProvider 内部添加内容

***

## 📦 按需依赖

以下包未预装在模板中。当业务需要时，使用 `pnpm add <package>` 安装：

| 需求场景                                                 | 推荐包                         | 安装命令                                       |
| ---------------------------------------------------- | --------------------------- | ------------------------------------------ |
| 动画效果（页面过渡、入场/退场动画、手势交互）                              | `framer-motion`             | `pnpm add framer-motion`                   |
| 复杂企业级组件（高级 Table、TreeSelect、Transfer、DatePicker 多语言） | `@arco-design/web-react`    | `pnpm add @arco-design/web-react`          |
| HTTP 请求库（拦截器、请求取消、进度回调）                              | `axios`                     | `pnpm add axios`                           |
| 日期处理（已预装 `date-fns`，如需 moment 兼容 API）                | `dayjs`                     | `pnpm add dayjs`                           |
| 状态管理（跨组件共享复杂状态）                                      | `zustand`                   | `pnpm add zustand`                         |
| Markdown 渲染                                          | `react-markdown`            | `pnpm add react-markdown`                  |
| 拖拽排序                                                 | `@dnd-kit/core`             | `pnpm add @dnd-kit/core @dnd-kit/sortable` |
| 飞书头像组件（可点击跳转飞书 Profile）                              | `@tod-m/materials` + `less` | `pnpm add @tod-m/materials less`           |

> 注：简单的 HTTP 请求直接使用内置 `fetch` API + `src/infra/sso/auth.ts` 中的 `fetchWithAuth` 即可，无需额外安装 axios。

***

## 📝 注意事项

1. **文档更新**：`docs/EDENX.md` 由命令自动生成，请勿手动编辑
2. **基建代码**：`src/infra/` 目录为平台基建代码（SSO 认证等），请勿随意修改
3. **问题反馈**：遇到框架 bug 或文档问题，请及时反馈

