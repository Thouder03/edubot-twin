# 上下文压缩与思维复盘

## [归档日期 2026-02-07]

### 1. 核心议题背景

**问题描述**: 用户报告学生账号（`student`/`student`）登录后出现两个路由问题：

1. 无法访问 `/student/home` 路由（显示空白或错误）
2. 登录后访问根路径 `/` 直接显示 404，但手动输入 `/student/home` 地址栏可以正常访问

**技术背景**:

- 项目基于 `vue-element-plus-admin` 架构
- 使用动态路由模式（`appStore.getDynamicRouter = true`）
- 路由权限由后端（Mock）返回的数据控制

### 2. 关键思维演变路径 (Cognitive Evolution)

#### 阶段一：路由无法访问 - Mock 数据缺失

**用户意图**: 学生用户应该能够访问 `/student/home` 路由

**初步诊断**:

- 检查 `src/router/index.ts`，发现 `/student/home` 路由已在 `asyncRouterMap` 中正确定义
- 检查 `mock/role/index.mock.ts`，发现 `studentList = []` **为空数组**

**冲突/转折**:

- vue-element-plus-admin 支持两种路由模式：
  - **静态模式**: 直接使用 `asyncRouterMap` 中的所有路由
  - **动态模式**: 根据后端返回的路由列表过滤 `asyncRouterMap`
- 项目使用动态模式，后端（Mock）返回的 `studentList` 为空，导致权限系统认为学生**没有任何可访问的路由**

**决策逻辑**:

- 必须在 `mock/role/index.mock.ts` 中的 `studentList` 添加 `/student/home` 路由配置
- Mock 中的路由格式与 `asyncRouterMap` 略有不同：
  - `component: '#'` 表示 Layout 组件
  - `component: 'views/Student/Home'` 使用字符串路径（非动态 import）

**实施方案**:

```typescript
const studentList = [
  {
    path: "/student",
    component: "#",
    redirect: "/student/home",
    name: "Student",
    children: [
      {
        path: "home",
        component: "views/Student/Home",
        name: "StudentHome",
        meta: {
          title: "router.studentHome",
          icon: "vi-carbon:home",
          noCache: true,
          affix: true,
        },
      },
    ],
  },
];
```

#### 阶段二：登录后根路径 404 - 硬编码重定向冲突

**用户意图**: 学生登录后应该自动跳转到 `/student/home`，而不是 404

**新问题发现**:

- 用户修复了 Mock 数据后，发现学生登录成功，但访问根路径 `/` 时显示 404
- 直接在地址栏输入 `/student/home` 可以正常访问

**诊断过程**:

1. 检查 `src/router/index.ts` 中的根路径配置：
   ```typescript
   {
     path: '/',
     component: Layout,
     redirect: '/dashboard/analysis',  // ❌ 硬编码重定向
     name: 'Root'
   }
   ```
2. 检查 `src/permission.ts` 中的权限守卫逻辑：
   ```typescript
   if (to.path === "/login") {
     next({ path: "/" }); // ❌ 登录后跳转到 /，触发 redirect
   }
   ```

**冲突分析**:

- 根路径硬编码 `redirect: '/dashboard/analysis'`
- 学生用户没有 `/dashboard/analysis` 的访问权限
- 访问无权限路由触发 404 兜底规则

**最终共识**:

1. **移除硬编码重定向**: 在 `src/router/index.ts` 中删除根路径的 `redirect` 属性
2. **动态首页跳转**: 在 `src/permission.ts` 中实现基于用户权限的动态重定向逻辑

**核心实现**:

```typescript
// src/permission.ts
if (to.path === "/login" || to.path === "/") {
  if (permissionStore.getAddRouters.length > 0) {
    const firstRoute = permissionStore.getAddRouters[0];
    if (firstRoute.children && firstRoute.children.length > 0) {
      next({
        path: firstRoute.path + "/" + firstRoute.children[0].path,
        replace: true,
      });
    } else {
      next({ path: firstRoute.path, replace: true });
    }
  }
}
```

### 3. 核心设计原则总结 (Design Principles)

#### 3.1 双重配置原则

**每个角色的路由必须在两处配置**：

- `src/router/index.ts` 的 `asyncRouterMap`（完整路由定义）
- `mock/role/index.mock.ts` 中对应角色的列表（权限控制）

#### 3.2 动态重定向原则

- **避免硬编码首页**: 根路径 `/` 不应该 redirect 到特定路由
- **权限守卫处理**: 在 `permission.ts` 中根据用户的第一个可访问路由动态跳转

#### 3.3 Mock 数据格式差异

- `component: '#'` → Layout 组件
- `component: '##'` → getParentLayout() 嵌套布局
- `component: 'views/Xxx'` → 字符串路径（系统自动解析）

### 4. 下一步行动指引 (Next Actions)

- [x] 修复学生路由 Mock 配置
- [x] 实现动态首页重定向逻辑
- [x] 更新项目核心知识库文档
- [x] 更新 `.agent/rules/overall-guidance.md` 规则文件
- [ ] 测试多角色切换场景（admin → student → test）

## [归档日期 2026-02-14]

### 1. 核心议题背景

**问题描述**: ROS3DViewer 面板虽然成功挂载，但在运行时出现严重问题：

1.  右侧设置栏报错崩溃（`PanelSettings` 读取 undefined 字段）。
2.  3D 视图黑屏，无网格，无 TF 坐标系，无法用鼠标控制视角。
3.  浏览器性能卡顿（渲染风暴）。

**技术背景**:

- 移植自 Lichtblick 的 `Renderer` 类，采用**非响应式**、**按需渲染**的架构。
- Vue 3 的响应式系统与 Three.js 的命令式渲染循环需要谨慎桥接。

### 2. 关键思维演变路径 (Cognitive Evolution)

#### 阶段一：运行时崩溃与性能风暴

- **现象**: 鼠标移动相机时，设置栏频繁更新导致页面卡死；某些节点报错。
- **根因分析**:
  - `CameraStateSettings` 在每一帧都触发 `settingsTreeChange`，频率过高。
  - `Renderer` 传出的设置树包含 `undefined` 的 fields。
- **决策**:
  - **防御性编程**: 在 `PanelSettings.vue` 中过滤空节点。
  - **事件节流**: 在 `useRenderer.ts` 中使用 `requestAnimationFrame` 合并 `settingsTreeChange` 事件。

#### 阶段二：Canvas 黑屏 (The "Nothing to Render" Issue)

- **现象**: Canvas 有背景色，但无网格。
- **探索**:
  - 检查 `config.layers` -> **空**（无默认层）。
  - 检查 `Grids` 扩展 -> **未注册**。
  - 检查 `RenderableLineList` -> **空桩代码**（无 Three.js 实现）。
- **决策**: **完整落地 Renderer-Extension 架构**。
  - 必须在 `createExtensionConfig` 中显式注册 `Grids`。
  - 必须在 `defaultRendererConfig` 中配置默认层数据。
  - 只需实现核心渲染逻辑，保持与上游架构一致。

#### 阶段三：交互与数据流断裂 (The Missing Bridges)

- **现象**: 鼠标无法控制相机，连接 ROS 后无 TF。
- **认知转折**: `Renderer` 本身是一个**被动**的渲染引擎，它**不主动**连接 ROS，也**不自动**响应 DOM 事件进行重绘。
- **架构修正 (Bridge Pattern)**:
  - **相机桥接**: 监听 `OrbitControls` 的 `change` 事件 -> 发出 `cameraMove` -> 手动调用 `queueAnimationFrame()`。
  - **ROS 桥接**: `useRosConnection` 仅负责 WebSocket 连接；必须在 `index.vue` 中显式订阅 `/tf` 并通过 `addMessageEvent` 注入 Renderer。

### 3. 系统架构新共识 (Architecture Consensus)

- **Renderer 是纯净的**: 不包含业务逻辑，不直接依赖 Vue/Roslib。
- **Index.vue 是控制器**: 负责将 Vue 的生命周期、Roslib 的数据流、DOM 的事件流**编织**在一起，驱动 Renderer 工作。
- **扩展即插件**: 所有 3D 功能（网格、TF）必须作为 SceneExtension 注册才能工作。

### 4. 下一步行动 (Next Actions)

- [ ] GzWeb Iframe 集成
- [ ] Docker 容器状态 WebSocket 对接
- [ ] RobotModel (URDF) 扩展移植
