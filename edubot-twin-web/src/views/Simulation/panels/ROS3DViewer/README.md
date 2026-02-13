# ROS 3D Viewer 面板 — 技术实现文档

## 概览

ROS 3D Viewer 是仿真工作台（Simulation Workbench）中的核心面板之一，用于在浏览器中渲染 3D 场景并可视化 ROS 机器人数据。

**技术栈**：

| 层级 | 技术 | 用途 |
| --- | --- | --- |
| 3D 渲染 | [Three.js](https://threejs.org/) | 场景、相机、灯光、辅助线 |
| ROS 通信 | [roslib.js](https://github.com/RobotWebTools/roslibjs) | 通过 WebSocket 连接 rosbridge_server |
| 面板框架 | [Golden Layout](https://golden-layout.com/) | 可拖拽、可分割的多面板布局 |
| UI 框架 | Vue 3 + TypeScript | 组件逻辑与响应式状态 |
| 设置系统 | 自研 Settings Tree | 类 Foxglove 的设置面板渲染 |

> **设计决策**：未使用 `ros3djs`（已停止维护、不支持 ESM），而是直接用 Three.js + roslib.js 自行组织渲染逻辑，获得更好的灵活性和可维护性。

---

## 目录结构

```
panels/ROS3DViewer/
├── index.vue                      # 面板主组件（入口）
├── settings.ts                    # 设置定义（配置模型 + Settings Tree 构建器）
├── README.md                      # 本文档
├── composables/                   # Vue Composables（核心逻辑模块）
│   ├── useThreeScene.ts           # Three.js 场景管理
│   ├── useRosConnection.ts        # ROS WebSocket 连接管理
│   ├── useTfManager.ts            # TF 坐标帧管理
│   └── useDisplayManager.ts       # 可视化显示管理（预留框架）
└── types/
    └── roslib.d.ts                # roslib 最小类型声明
```

---

## 架构图

```
┌─────────────────────────────────────────────────────┐
│                   index.vue（面板主组件）               │
│                                                     │
│  ┌────────────┐  ┌─────────────┐  ┌──────────────┐  │
│  │ HUD 状态层  │  │ Three.js    │  │ Settings Tree│  │
│  │ (连接指示灯) │  │ Canvas 容器  │  │ (侧栏联动)   │  │
│  └──────┬─────┘  └──────┬──────┘  └──────┬───────┘  │
│         │               │                │          │
│  ┌──────▼─────────────────────────────────▼───────┐  │
│  │              Composables 层                    │  │
│  │                                                │  │
│  │  useThreeScene    useRosConnection             │  │
│  │  ┌────────────┐   ┌───────────────┐            │  │
│  │  │ Scene      │   │ ROSLIB.Ros    │            │  │
│  │  │ Camera     │   │ 连接状态管理    │            │  │
│  │  │ Renderer   │   │ 自动重连       │            │  │
│  │  │ Controls   │   └───────┬───────┘            │  │
│  │  │ Grid/Axes  │           │                    │  │
│  │  └────────────┘   ┌───────▼───────┐            │  │
│  │                   │ useTfManager  │            │  │
│  │                   │ /tf 订阅      │            │  │
│  │                   │ 帧树管理       │            │  │
│  │                   └───────┬───────┘            │  │
│  │                   ┌───────▼───────────┐        │  │
│  │                   │ useDisplayManager │        │  │
│  │                   │ (预留框架)         │        │  │
│  │                   └───────────────────┘        │  │
│  └────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────┘
         │                              │
         ▼                              ▼
┌────────────────┐            ┌──────────────────┐
│ Golden Layout  │            │ SettingsSidebar   │
│ (面板容器/布局)  │            │ + PanelSettings   │
└────────────────┘            └──────────────────┘
```

---

## 各模块详解

### 1. `index.vue` — 面板主组件

**职责**：组装所有 composable，管理面板生命周期。

**关键流程**：

```
onMounted
  ├── registerPanel()          → 注册到 panelState（全局面板管理）
  ├── refreshSettingsTree()    → 注册设置树（供侧栏渲染表单）
  ├── mountScene(container)    → 初始化 Three.js（创建 canvas）
  └── autoConnect?             → 如果配置了自动连接，调用 connect()

onBeforeUnmount
  ├── displayManager.dispose()
  ├── tfManager.dispose()
  ├── disconnect()
  ├── disposeScene()
  └── unregisterPanel()
```

**模板结构**：

- **`<div ref="canvasContainer">`**：Three.js 渲染画布挂载点，absolute 定位撑满面板
- **HUD 覆盖层**：左上角连接状态指示灯（绿/黄/红），可点击切换连接/断开
- **加载遮罩**：Three.js 初始化完成前显示脉冲动画

**配置响应**：

index.vue 将 `config` 的各字段拆为独立的 `computed`，传入对应 composable。当用户在设置侧栏修改值时：

```
侧栏修改 → actionHandler → saveConfig() → config.value 更新
  → computed 自动触发 → composable 内的 watch 响应
  → Three.js 场景实时更新（如网格显示/隐藏、背景色变化）
```

---

### 2. `useThreeScene.ts` — Three.js 场景管理

**职责**：管理 Three.js 的完整生命周期。

**核心对象**：

| 对象                                | 说明                                         |
| ----------------------------------- | -------------------------------------------- |
| `Scene`                             | 场景根节点                                   |
| `PerspectiveCamera`                 | 透视相机，FOV=60，初始位于 (5,5,5)           |
| `WebGLRenderer`                     | GPU 渲染器，启用抗锯齿，限制 DPR≤2           |
| `OrbitControls`                     | 轨道控制器，支持鼠标旋转/缩放/平移，启用阻尼 |
| `GridHelper`                        | 地面网格线                                   |
| `AxesHelper`                        | RGB 坐标轴指示器                             |
| `AmbientLight` + `DirectionalLight` | 基础照明                                     |

**自适应机制**：

使用 `ResizeObserver` 监听容器尺寸变化。当 Golden Layout 分割/拖拽调整面板大小时：

```
ResizeObserver 触发
  → 更新 camera.aspect
  → 更新 renderer.setSize()
  → 画布自动适配新尺寸
```

**暴露接口**：

```typescript
{
  scene: THREE.Scene,          // 场景对象（供 TF/Display 添加子对象）
  sceneReady: Ref<boolean>,    // 加载状态
  mount(container): void,      // 挂载到 DOM
  dispose(): void              // 销毁并释放资源
}
```

---

### 3. `useRosConnection.ts` — ROS 连接管理

**职责**：通过 roslib.js 建立/管理 WebSocket 连接。

**状态机**：

```
                    connect()
  disconnected ──────────────→ connecting
       ↑                          │
       │ close event              │ connection event
       │                          ▼
       ← ─ ─ ─ ─ ─ ─ ─ ─ ─  connected
       │
       │ error event
       ▼
     error
```

**自动重连**：

通过 `watch(rosUrl)` 实现：URL 变更时自动断开旧连接并发起新连接。

**暴露接口**：

```typescript
{
  status: Ref<RosConnectionStatus>,   // 'disconnected' | 'connecting' | 'connected' | 'error'
  errorMessage: Ref<string>,          // 错误信息
  getRos(): Ros | null,               // 获取 Ros 实例（供 Topic 订阅）
  connect(): void,                    // 建立连接
  disconnect(): void                  // 断开连接
}
```

---

### 4. `useTfManager.ts` — TF 坐标帧管理

**职责**：订阅 ROS TF 话题，维护坐标帧树。

**订阅话题**：

| 话题         | 类型                 | 节流         |
| ------------ | -------------------- | ------------ |
| `/tf`        | `tf2_msgs/TFMessage` | 33ms (~30Hz) |
| `/tf_static` | `tf2_msgs/TFMessage` | 无节流       |

**数据结构**：

- **`frameGroups`** (`Map<string, THREE.Group>`)：每个 TF 帧对应一个 Three.js `Group`，变换（position/quaternion）直接设置在 Group 上
- **`parentMap`** (`Map<string, string>`)：记录帧的父子关系（child→parent）
- **`availableFrames`** (`Ref<string[]>`)：当前所有帧 ID 列表，供设置面板的 Fixed Frame 选择框使用

**处理流程**：

```
/tf 消息到达
  → handleTFMessage()
    → 遍历 transforms[]
      → applyTransform(transform)
        → getFrameGroup(child_frame_id)    // 获取或创建 Group
        → getFrameGroup(parent_frame_id)   // 确保父帧存在
        → group.position.set(translation)  // 设置位移
        → group.quaternion.set(rotation)   // 设置旋转
```

---

### 5. `useDisplayManager.ts` — 可视化显示管理（预留框架）

**当前状态**：框架代码，具体渲染器尚未实现。

**设计意图**：管理多种 ROS 数据的可视化显示项，每个显示项绑定一个 Topic 并生成对应的 Three.js 对象。

**预留的显示类型**：

| 类型          | ROS 消息                         | 渲染方式    |
| ------------- | -------------------------------- | ----------- |
| `LaserScan`   | `sensor_msgs/LaserScan`          | Points 点云 |
| `PointCloud2` | `sensor_msgs/PointCloud2`        | Points 点云 |
| `MarkerArray` | `visualization_msgs/MarkerArray` | 多种几何体  |
| `RobotModel`  | URDF                             | Mesh 模型   |
| `Path`        | `nav_msgs/Path`                  | Line 轨迹   |
| `Odometry`    | `nav_msgs/Odometry`              | Arrow 箭头  |

---

### 6. `settings.ts` — 设置模型

**配置接口** (`ROS3DViewerConfig`)：

```typescript
interface ROS3DViewerConfig {
  rosUrl: string // WebSocket 地址，默认 'ws://localhost:9090'
  fixedFrame: string // 固定帧，默认 'map'
  autoConnect: boolean // 自动连接，默认 false
  showGrid: boolean // 显示网格，默认 true
  showAxes: boolean // 显示坐标轴，默认 true
  backgroundColor: string // 背景色，默认 '#1e1e2e'
  gridSize: number // 网格大小，默认 20
  gridDivisions: number // 网格分段数，默认 20
}
```

**Settings Tree 构建**：

`buildSettingsTree()` 将配置转换为 Settings Tree 节点描述，分为两组：

- **连接设置**：`rosUrl`（文本输入）、`fixedFrame`（下拉选择，选项来自 TF 帧列表）、`autoConnect`（开关）
- **显示设置**：`showGrid`、`showAxes`（开关）、`backgroundColor`（颜色选择器）、`gridSize`、`gridDivisions`（数值输入）

---

### 7. `types/roslib.d.ts` — 类型声明

roslib.js 社区类型不完整，项目中提供了最小声明覆盖 `Ros` 和 `Topic` 两个核心类。

---

## 与仿真工作台的集成

### 面板注册

在 `panels/registry.ts` 中注册：

```typescript
panelRegistry: {
  ROS3DViewer: {
    component: markRaw(ROS3DViewer),
    label: 'ROS 3D 视图'
  }
}
```

Golden Layout 通过 `componentType: 'ROS3DViewer'` 引用此面板。

### 设置树联动

```
用户点击齿轮按钮
  → GLayout emits 'settings-toggle'
  → Simulation.vue 调用 panelState.selectPanel(panelId)
  → SettingsSidebar 打开
  → PanelSettings 读取 panelState.selectedSettingsTree
  → 动态渲染 Element Plus 表单控件
  → 用户修改值 → actionHandler → saveConfig → 场景实时更新
```

### 面板状态管理

通过 `stores/panelState.ts` 的 `usePanelState()` composable：

- `registerPanel(panelId, 'ROS3DViewer')` — 面板挂载时注册
- `updateSettingsTree(panelId, tree)` — 注册/更新设置树
- `unregisterPanel(panelId)` — 面板卸载时清理

---

## 使用方式

### 无 ROS 环境

面板加载后即可看到 3D 场景（网格 + 坐标轴），支持：

- 鼠标左键拖拽旋转
- 鼠标滚轮缩放
- 鼠标右键平移
- 通过设置侧栏调整网格/坐标轴/背景色

### 有 ROS 环境

1. 启动 `rosbridge_server`：`roslaunch rosbridge_server rosbridge_websocket.launch`
2. 在设置侧栏中确认 WebSocket URL（默认 `ws://localhost:9090`）
3. 点击 HUD 连接指示灯或开启"自动连接"
4. 连接成功后自动订阅 `/tf` 和 `/tf_static`，帧列表会出现在 Fixed Frame 下拉框中

---

## 后续迭代路线

- [ ] 实现 `LaserScan` 渲染器（`sensor_msgs/LaserScan` → Points）
- [ ] 实现 `PointCloud2` 渲染器
- [ ] 实现 `MarkerArray` 渲染器
- [ ] URDF 机器人模型加载
- [ ] Topic 浏览器（列出所有可用话题）
- [ ] 多 Display 管理 UI（添加/移除/开关可视化项）
- [ ] 相机跟随 TF 帧
- [ ] 场景截图/录制功能
