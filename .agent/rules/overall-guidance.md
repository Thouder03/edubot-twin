---
trigger: always_on
---

# Role

You are an expert Full-Stack Developer specializing in **Vue 3.5+**, **TypeScript**, and **Robotics Web Visualization**.
You are building a "Digital Twin Robotics Training Platform" based on the `vue-element-plus-admin` architecture.

# Project Context

- **Goal**: Build a platform with a **Teacher Dashboard** (Docker management, student stats) and a **Student Workbench** (ROS visualization, GzWeb, Terminal, Code Editor).
- **ai_memory**: edubot-twin/.ai_memory
- **Architecture**:
  - **Frontend**: Vue 3.5, Vite 6, Element Plus 2.9, UnoCSS.
  - **Backend Interaction**: Python FastAPI (managing Docker/ROS), communicated via REST API and WebSockets.
  - **Visualization**: `roslibjs`, `ros3djs` (WebGL), `xterm.js` (Web Terminal).

# 1. Technology Stack & Constraints (Strict)

## Framework & Core

- **Vue**: Use Vue 3.5+ with **Composition API** and `<script setup lang="ts">` ONLY.
- **UI Library**: **Element Plus** is the single source of truth for UI components.
  - Do NOT use Tailwind UI, Ant Design, or Bootstrap.
  - Use `el-row`, `el-col`, `el-card` for layouts unless a specific admin component exists.
- **CSS**:
  - **Layout/Utilities**: Use **UnoCSS** (Atomic CSS) for margins, padding, flex, colors, etc. (e.g., `class="mb-20px flex items-center"`).
  - **Component Styling**: Use **Less** with **BEM** naming convention.
  - **Namespace**: ALWAYS use the `useDesign` hook for class names to ensure style isolation.
    ```typescript
    const { getPrefixCls } = useDesign();
    const prefixCls = getPrefixCls("ros-viewer"); // Result: v-ros-viewer
    ```

## Robotics & Visualization

- **ROS Communication**: Use `roslibjs` for WebSocket connections.
- **3D Visualization**: Use `ros3djs` integrated into Vue components.
  - Ensure WebGL contexts are properly disposed of in `onUnmounted`.
- **Terminals**: Use `xterm.js` with `fit-addon`.

# 2. Component Structure & Patterns

## Page Layout

- **Root Element**: Most admin pages must be wrapped in `<ContentWrap>` (from `@/components/ContentWrap`).
- **Student Simulation Page**: Use a custom Full-Screen Flex layout (Split View: Left 3D, Right GzWeb/Tools). Do not use `ContentWrap` if it restricts the viewport height for 3D canvases.

## Props Definition

- **Must** use `propTypes` from `@/utils/propTypes` for runtime validation and type inference.
- **BAD**: `defineProps<{ title: string }>()`
- **GOOD**:
  ```typescript
  import { propTypes } from "@/utils/propTypes";
  defineProps({
    containerId: propTypes.string.isRequired,
    isConnected: propTypes.bool.def(false),
  });
  ```

````

## State Management (Pinia)

* Use **Pinia** for all global state (User, App, Docker Containers, ROS Connection Status).
* Store ID must match the filename.
* Use `persist: true` for persistent data (like User Token, Theme Settings).

# 3. API & Data Fetching

## Axios Wrapper

* **NEVER** use `axios` directly in components.
* Use the encapsulated `service` from `@/axios`.
* Define API calls in `src/api/modules/*.ts`.
* **Typing**: APIs must return `Promise<IResponse<T>>`.

```typescript
// src/api/modules/docker.ts
import service from '@/axios'
import { DockerStats } from './types'

export const getContainerStats = (id: string): Promise<IResponse<DockerStats>> => {
  return service.get({ url: `/docker/stats/${id}` })
}

````

# 4. Coding Style & Naming

- **Files**: PascalCase for `.vue` files (e.g., `RosViewer.vue`, `StudentDashboard.vue`).
- **Directories**:
- `src/views/teacher/`: Teacher specific views.
- `src/views/student/`: Student specific views.
- `src/components/Ros/`: Global ROS related components.

- **Icons**: Use Iconify (`@iconify/vue`) or local SVGs. No FontAwesome.
- **Colors**: Do NOT hardcode hex values. Use CSS variables from Element Plus (e.g., `var(--el-color-primary)`, `var(--el-bg-color)`).

## Vue 模板格式化规范

- **长属性换行**：当 Vue 模板标签的属性值过长时（通常超过 80-100 个字符），必须将属性换行以保持可读性。
- **格式要求**：
  - 开始标签独立一行
  - 属性另起一行，缩进 2 个空格
  - 闭合标签 `>` 独立一行，与开始标签对齐

**错误示例**：

```vue
<!-- ❌ 单行过长，不符合 ESLint/Prettier 规则 -->
<div :class="`${prefixCls}__item--icon ${prefixCls}__item--exam p-16px inline-block rounded-6px`">
```

**正确示例**：

```vue
<!-- ✅ 属性换行并正确缩进 -->
<div
  :class="`${prefixCls}__item--icon ${prefixCls}__item--exam p-16px inline-block rounded-6px`"
>
```

- **触发场景**：当 linter 提示 `Replace ... with ...` 并显示换行符 `⏎` 时，说明需要进行格式调整。
- **适用范围**：所有 Vue 模板中的属性（`:class`, `:style`, `@click`, `:prop` 等）。

# 5. Specific Implementation Rules (Digital Twin)

## Docker/Container Management (Teacher View)

- When displaying container lists, use `<Table>` (encapsulated component) or `el-table`.
- Use `el-tag` for container status (Running=Success, Stopped=Danger).

## ROS Visualization (Student View)

- **Lifecycle**:
- Initialize `ROS` connection in `onMounted`.
- Destroy connection in `onUnmounted`.

- **Performance**:
- If using `ros3djs`, bind the viewer to a specific `div` ID.
- Use `ResizeObserver` to handle window resizing for the 3D canvas.

## Terminal Integration

- Wrap `xterm.js` in a Vue component (`TerminalView.vue`).
- Expose methods via `defineExpose` (e.g., `write`, `clear`) to allow parent components to control it.

# 6. Critical Don'ts

- Do NOT use `Options API` (`data`, `methods`, `computed` object syntax).
- Do NOT use `class` style components.
- Do NOT mix ROS 1 and ROS 2 logic (Stick to ROS 1/Noetic unless specified).
- Do NOT put complex logic inside `<template>`. Extract to `computed` or functions.

# 7. 路由与权限管理

> 📖 **详细规范请参考**: [`.agent/rules/router-map-guidance.md`](./.agent/rules/router-map-guidance.md)

## 快速要点

- **路由模式**: 前端动态路由 (`serverDynamicRouter: false`)
- **后端接口**: `GET /api/v1/auth/routes?role=student` 返回路径列表
- **关键约束**:
  - ⚠️ 根路径 `/` 不要硬编码 `redirect`，在 `permission.ts` 中动态跳转
  - 异步路由必须在**两处配置**: `router/index.ts` + 后端 API/Mock
  - 前后端路径必须完全匹配（如 `["/student", "/student/home"]`）

**完整规范包含**:

- 三种路由模式对比
- 静态路由 vs 异步路由配置
- 权限守卫最佳实践
- 路由元信息 (meta) 详解
- 常见问题排查
- 调试技巧