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

---

# 上下文压缩与思维复盘

## [归档日期 2026-02-19]

### 1. 核心议题背景

本次会话的核心任务是为 ROS3DViewer 的 Renderer-Extension 架构实现完整的 **ROS Markers SceneExtension**。目标是让 3D 面板能接收并渲染 `visualization_msgs/Marker` 和 `visualization_msgs/MarkerArray` 消息，覆盖全部 12 种 Marker 类型。

参考来源：`/home/ubuntu20/lichtblick/packages/suite-base/src/panels/ThreeDeeRender/renderables/` 目录。

---

### 2. 关键思维演变路径 (Cognitive Evolution)

**阶段一：依赖分析与材质简化决策**
- **用户意图**: 完整移植 lichtblick 的 Markers 扩展
- **冲突**: lichtblick 的 `materials.ts` 依赖 `LineMaterialWithAlphaVertex`（来自 `@lichtblick/three-renderer` 私有包，本项目无此依赖）
- **决策逻辑**: 改用标准 `THREE.LineBasicMaterial` 替代，放弃可变宽度线条（视觉差异可接受，避免引入重量级依赖）

**阶段二：循环导入与类型定位**
- **冲突**: `TopicMarkers.ts` 原先本地定义 `LayerSettingsMarker`，`RenderableMarker.ts` 又从 `TopicMarkers` 导入它 → 循环依赖
- **决策**: 将 `LayerSettingsMarker` 的**权威定义位置**移到 `RenderableMarker.ts`，`TopicMarkers.ts` 保留本地拓展版（添加 `namespaces` 字段），两者解耦

**阶段三：`normalizeFrameId` 接口缺失**
- **冲突**: `RenderableMarker.ts` 和 `TopicMarkers.ts` 调用 `renderer.normalizeFrameId()`，但 `IRenderer` 接口中没有此方法（lichtblick 中它是 Renderer 的模块级私有函数）
- **决策**: 在 `IRenderer` 接口中新增 `normalizeFrameId(frameId: string): string`，在 `Renderer.ts` 中实现为：`this.ros ? frameId.replace(/^\//, '') : frameId`

**阶段四：批量编译错误修复**
- `Markers.ts` 的 `path.length` → `!path || path.length`（undefined guard）
- `RenderableCubeList.ts`、`RenderableTextViewFacing.ts` 未使用导入删除
- `Grids.ts` 的 `RenderableLineList` 多余第5参数（原先为 lichtblick 的 `LINE_OPTIONS`，简化版构造函数不支持）

**阶段五：最终共识**
- 所有 Marker 相关文件 tsc 零错误
- 在 `composables/useRenderer.ts` 的 `createExtensionConfig()` 显式注册 `Markers`

---

### 3. 已确立的架构约定

- **新 SceneExtension 注册点**: `composables/useRenderer.ts` → `createExtensionConfig()`
- **Materials 策略**: 不引入 `LineMaterialWithAlphaVertex`，全用标准 Three.js 材质
- **类型定义位置**: 跨文件共享类型定义在被依赖方（而非依赖方），避免循环导入
- **normalizeFrameId**: `IRenderer` 接口方法，实现在 `Renderer.ts`，供所有 Extension 调用

### 4. 下一步行动指引 (Next Actions)

- [ ] 用 ROS 发布 `visualization_msgs/Marker` 进行端到端联调
- [ ] 实现 `LaserScan` SceneExtension（参考 `RenderablePoints` 的 THREE.Points 方案）
- [ ] 实现 `PointCloud2` SceneExtension
- [ ] 完善设置侧栏中 Markers topic 的命名空间可见性控制 UI

## [归档日期 2026-03-12]

### 1. 核心议题背景

本次会话的核心任务是调试并修复 ROS3DViewer 中 `/scan`（`sensor_msgs/LaserScan`）话题无法渲染的问题。表现为：连接 ROS 后，设置树中 /scan 话题的眼睛图标为关闭且无法点击，3D 视图中不显示任何激光点云。

---

### 2. 关键思维演变路径 (Cognitive Evolution)

**阶段一：错误的初始假设（GPU shader / position attribute）**
- **用户意图**: 修复 LaserScan 不显示
- **初始假设**: lichtblick 原版将 range 存在 `position` attribute（itemSize=1），THREE.js 内部期望 itemSize=3，导致 WebGL VAO 静默失败
- **冲突/转折**: 查阅 lichtblick 源码 line 74 注释：`"Three.JS doesn't render anything if there is no attribute named position, so we use the name position for the 'range' parameter."` — 这是刻意设计，不是 bug
- **决策逻辑**: 放弃 GPU/shader 假设，转向 settingsNodes 过滤逻辑排查

**阶段二：Settings 树串台问题（话题出现在错误的 Extension）**
- **发现**: `/scan` 在连接后出现在 Markers 设置树，因为 `Markers.settingsNodes()` 从 `configTopics` 迭代时没有检查 schema
- **修复**: `configTopics` 中的话题也必须检查 `schema`，断线时只保留有 renderable 的话题

**阶段三：visible 默认值问题**
- **发现**: `DEFAULT_POINT_SETTINGS.visible = false`，首次创建 renderable 时 `settings.visible = false`
- **修复**: `#handleLaserScan` 首次创建时强制 `visible = true`

**阶段四：handleSettingsAction 路径长度问题**
- **发现**: 眼睛图标触发的 action 的 `path.length === 2`，原代码 `if (path.length !== 3) return` 直接忽略
- **修复**: 加入 `path.length === 2` 分支

**阶段五：真正根因——消息永远不到达 handler（3小时后发现）**
- **突破口**: 查看 `index.vue` 的 `syncRosTopicsToRenderer()` 函数
- **冲击性发现**: 该函数里的 `MARKER_SCHEMAS` 集合和 `if (!MARKER_SCHEMAS.has(topic.schemaName)) continue` 过滤逻辑，导致 `sensor_msgs/LaserScan` 话题**从未被 ROSLIB 订阅**，消息根本不会到达 `addMessageEvent`，所有上游的修复都白费
- **根因**: `syncRosTopicsToRenderer` 是所有话题消息的唯一路由入口，但当时只实现了 Marker 订阅
- **修复**: 加入 `LASERSCAN_SCHEMAS` 和 `VISUALIZABLE_SCHEMAS` 合集

### 3. 架构关键约束（教训）

**新增 SceneExtension 必须做的两件事**:
1. `extensions/YourExtension.ts` — 实现 `getSubscriptions()` 返回 schema
2. `index.vue` — 在 `syncRosTopicsToRenderer()` 的 `VISUALIZABLE_SCHEMAS` 中注册 schema

**这是一个"双入口"陷阱**：Renderer 的订阅体系（`getSubscriptions()`）和 ROSLIB 订阅体系（`syncRosTopicsToRenderer()`）是两个独立的层，二者必须同步维护。

### 4. 下一步行动指引 (Next Actions)

- [ ] 端到端测试：验证 /scan 在带TF / 无TF 环境下的渲染
- [ ] 实现 `nav_msgs/OccupancyGrid`（地图）：记得在 VISUALIZABLE_SCHEMAS 注册
- [ ] 实现 `sensor_msgs/PointCloud2`：记得在 VISUALIZABLE_SCHEMAS 注册
- [ ] 考虑将 VISUALIZABLE_SCHEMAS 提取为常量文件，避免分散维护
