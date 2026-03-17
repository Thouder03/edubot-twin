# 3D 面板差异分析：Lichtblick (React) vs EduBot-Twin (Vue 3)

> 本文档对比 `/home/ubuntu20/lichtblick` 中的原版 Lichtblick 3D 面板（React 技术栈）与本工程 `edubot-twin-web` 中移植实现的 3D 面板（Vue 3 技术栈）之间的架构差异，供后续开发参考。
>
> **参考文档**：
>
> - `/home/ubuntu20/lichtblick/3D_PANEL_ANALYSIS_CN.md`（原版架构分析）
> - `/home/ubuntu20/lichtblick/VUE3_3D_PANEL_GUIDE_CN.md`（Vue3 移植指南）

---

## 1. 整体架构对比

| 维度 | Lichtblick 原版 | EduBot-Twin 移植版 |
| --- | --- | --- |
| **UI 框架** | React 18 + Hooks | Vue 3 + Composition API |
| **状态管理** | React `useState` / `useEffect` | Vue `ref` / `shallowRef` / Composables |
| **3D 引擎** | Three.js（通过 `Renderer.ts`） | Three.js（移植自 Lichtblick `Renderer.ts`） |
| **数据源** | Lichtblick 内置消息管道（`PanelContext`） | ROS WebSocket（支持动态话题订阅） |
| **配置持久化** | `context.saveState()` / `context.initialState` | 已实现（`localStorage` + 防抖保存） |
| **布局系统** | Lichtblick 内置面板布局 | Golden Layout（`GLayout.vue`） |
| **设置面板** | Lichtblick 内置侧栏（`updatePanelSettingsEditor`） | 自定义 Vue 递归组件（已集成到侧栏） |

---

## 2. 核心文件对照表

### 2.1 Lichtblick 原版核心文件

```
packages/suite-base/src/panels/ThreeDeeRender/
├── index.tsx                    # 面板注册入口
├── ThreeDeeRender.tsx           # React 容器组件（核心胶水层）
├── Renderer.ts                  # 渲染引擎核心
├── SceneExtension.ts            # 扩展基类
├── SceneExtensionConfig.ts      # 扩展注册表
├── SettingsManager.ts           # 设置树管理器
├── RendererContext.ts           # React Context（跨组件共享 Renderer）
├── RendererOverlay.tsx          # HUD 覆盖层（工具栏、交互菜单）
└── renderables/                 # 具体扩展实现（17+ 个）
```

### 2.2 EduBot-Twin 移植版核心文件

```
src/views/Simulation/
├── Simulation.vue               # 工作台顶层容器
├── components/
│   ├── GLayout.vue              # Golden Layout 布局管理
│   ├── PanelSettings.vue        # 设置面板内容区
│   └── SettingsSidebar.vue      # 设置侧栏容器
└── panels/ROS3DViewer/
    ├── index.vue                # Vue 容器组件（包含动态订阅逻辑）
    ├── components/
    │   └── ROS3DToolbar.vue     # 右上角工具栏（发布工具控制）
    ├── core/                    # 移植自 Lichtblick 的核心 TS 类
    │   ├── Renderer.ts          # 渲染引擎
    │   ├── SceneExtension.ts    # 扩展基类
    │   ├── SettingsManager.ts   # 设置树管理器
    │   └── transforms/          # TF 变换树与时间对齐组件
    ├── composables/             # Vue Composables
    │   ├── useRenderer.ts       # Renderer 生命周期与配置持久化
    │   └── useRosConnection.ts  # ROS WebSocket 连接管理
    └── extensions/              # 已移植的扩展（11 个）
        ├── SceneSettings.ts     # 场景全局设置
        ├── Grids.ts             # 网格
        ├── FrameAxes.ts         # TF 坐标轴
        ├── Markers.ts           # ROS Markers
        ├── PointClouds.ts       # 点云
        ├── LaserScans.ts        # 激光雷达
        ├── OccupancyGrids.ts    # 占用栅格
        ├── Poses.ts             # 单一位姿
        ├── PoseArrays.ts        # 位姿阵列
        ├── Polygons.ts          # 多边形
        └── PublishSettings.ts   # 发布控制中心
```

---

## 3. 关键差异详解

### 3.1 UI 框架与生命周期

**Lichtblick（React）**：
- 通过 `useEffect` 处理复杂副作用。渲染循环由 `needsRender` 标志控制。

**EduBot-Twin（Vue 3）**：
- 使用 `useRenderer()` 封装实例化逻辑。利用 `shallowRef` 托管 `Renderer` 以避免过度响应式开销。
- 引入了**仿真时钟驱动**：基于 `/clock` 话题自动对齐 Gazebo 时间，解决了 `decayTime` 失效问题。

### 3.2 消息管道与动态订阅

**Lichtblick（React）**：
- 依靠平台底层的消息总线，通过 `context.onRender` 接收数据。

**EduBot-Twin（Vue 3）**：
- **动态话题订阅**：在 `index.vue` 中实现。
- 系统会实时获取 ROS Topic 列表，仅当扩展在设置树中被勾选为 `visible: true` 时才发起订阅，优化网络性能。

### 3.3 设置面板与交互

**Lichtblick（React）**：
- 使用平台内置的 `SettingsTreeEditor`，支持搜索过滤和路径聚焦。

**EduBot-Twin（Vue 3）**：
- 自定义 `SettingsNestedGroup` 实现递归渲染。
- **字段类型支持**：已涵盖 `string`、`number`、`boolean`、`select`、`rgb/rgba`、`vec2/vec3`、`gradient`、`autocomplete`。
- **交互增强**：组标题集成眼睛图标支持节点可见性切换；集成 `ROS3DToolbar` 支持点击发布。

---

## 4. 详细对比表

### 4.1 扩展 (SceneExtension) 移植进度

| 扩展名                            | Lichtblick 原版 | EduBot-Twin                   | 备注 |
| --------------------------------- | --------------- | ----------------------------- | ---- |
| SceneSettings（场景全局设置）     | ✅              | ✅                            | 背景色、FPS 统计等 |
| Grids（网格）                     | ✅              | ✅                            | 支持多图层叠加 |
| FrameAxes（TF 坐标轴）            | ✅              | ✅                            | 支持帧过滤 |
| Markers（ROS Markers）            | ✅              | ✅                            | 完整支持基础形状与 Mesh |
| PointClouds（点云）               | ✅              | ✅                            | 支持彩色/环形/衰减 |
| LaserScans（激光雷达）            | ✅              | ✅                            | 支持点云/stixels 样式 |
| OccupancyGrids（占用栅格）        | ✅              | ✅                            | 支持多层级映射 |
| Poses / PoseArrays（位姿）        | ✅              | ✅                            | 位姿箭头与阵列 |
| Polygons（多边形）                | ✅              | ✅                            | |
| PublishSettings（发布设置）       | ✅              | ✅                            | |
| Urdfs（机器人 URDF 模型）         | ✅              | ❌                             | 待移植（需 ColladaLoader） |
| Images（图像话题）                | ✅              | ❌                             | |
| Cameras（相机模型）               | ✅              | ❌                             | |
| MeasurementTool（测量工具）       | ✅              | ❌                             | |

> **当前移植进度**：11/19 个扩展已完整实现。

### 4.2 设置字段类型支持对照

| 字段类型       | Lichtblick 原版 | EduBot-Twin                                |
| -------------- | --------------- | ------------------------------------------ |
| `string`       | ✅              | ✅                                         |
| `number`       | ✅              | ✅                                         |
| `boolean`      | ✅（开关）      | ✅（On/Off 按钮组）                        |
| `select`       | ✅              | ✅                                         |
| `rgb / rgba`   | ✅              | ✅（支持 alpha 通道）                      |
| `vec2 / vec3`  | ✅              | ✅                                         |
| `gradient`     | ✅              | ✅                                         |
| `autocomplete` | ✅              | ✅                                         |
| `messagepath`  | ✅              | ❌                                         |
| 搜索过滤       | ✅              | ❌                                         |
| 路径聚焦       | ✅              | ❌                                         |
| 节点错误显示   | ✅              | ✅（通过 `field.error` 实时反馈）          |
| 节点可见性切换 | ✅              | ✅（组标题眼睛图标）                       |

---

## 5. 数据流对比

### 5.1 Lichtblick 数据流
`消息管道` → `ThreeDeeRender.tsx` → `Renderer.ts` → `SceneExtension.解析` → `Three.js 渲染`

### 5.2 EduBot-Twin 数据流
`ROS WebSocket` → `index.vue (动态路由)` → `Renderer.ts` → `SceneExtension.解析` → `Three.js 渲染`

---

## 6. 已知差距与后续建议

### 6.1 高优先级
1. **URDF 加载**：实现机器人模型渲染。
2. **相机同步**：支持多面相机联动（`syncCamera`）。
3. **设置面板搜索**：随着扩展增多，急需搜索过滤功能。

### 6.2 中/低优先级
4. **图像投影**：实现 `ImageMode`。
5. **测量工具**：支持 3D 空间测距。
6. **数据导出**：支持捕捉当前 3D 场景为图片或视频。

---

## 7. 核心类对照速查

| Lichtblick 类/文件 | EduBot-Twin 对应 | 状态 |
| --- | --- | --- |
| `ThreeDeeRender.tsx` | `index.vue` | ✅ 已移植 |
| `Renderer.ts` | `core/Renderer.ts` | ✅ 已移植 |
| `SceneExtension.ts` | `core/SceneExtension.ts` | ✅ 已移植 |
| `SettingsManager.ts` | `core/SettingsManager.ts` | ✅ 已移植 |
| `RendererContext.ts` | `stores/panelState.ts` | ✅ 等价替代 |
| `PointClouds.ts` | `extensions/PointClouds.ts` | ✅ 已移植 |
| `LaserScans.ts` | `extensions/LaserScans.ts` | ✅ 已移植 |
| `Markers.ts` | `extensions/Markers.ts` | ✅ 已移植 |
| `Urdfs.ts` | — | ❌ 未实现 |
| `lichtblick-shim.ts` | `core/lichtblick-shim.ts` | ✅ 新增（API 垫片） |
