# SDD：GzWeb 代理通信模式集成规范

> **版本**: 1.0
> **日期**: 2026-03-20
> **状态**: 草案
> **范围**: edubot-twin + gzweb 跨项目集成

---

## 1. 系统架构

### 1.1 四层数据流

```
┌─────────────────────────────────────────────────────────────────┐
│  edubot-twin-web (Vue 3.5 + TypeScript)                         │
│                                                                 │
│  ┌─────────────────────────────────────────────────────────┐    │
│  │ GzWebViewer 面板 (Golden Layout)                        │    │
│  │ ┌──────────────────┐  ┌──────────────────────────────┐  │    │
│  │ │  SimControlBar   │  │  <iframe src="embed.html">   │  │    │
│  │ │  ▶ ⟲ SimTime   │  │    gz3d 3D Engine            │  │    │
│  │ └──────┬───────────┘  │    (Scene/Camera/Renderer)   │  │    │
│  │        │              │    GZIface (ROSLIB.Ros)       │  │    │
│  │        │ postMessage  │         │                     │  │    │
│  │        ├─────────────►│         │                     │  │    │
│  │        │◄─────────────│         │                     │  │    │
│  │        │              └─────────┼─────────────────────┘  │    │
│  └────────────────────────────────┼─────────────────────────┘    │
└───────────────────────────────────┼──────────────────────────────┘
                                    │ L3: WebSocket (ROSLIB)
                                    ▼
┌──────────────────────────────────────────────────────────────────┐
│  Docker 容器 (每个学生独立)                                        │
│  ┌──────────────┐    ┌──────────────┐    ┌────────────────┐      │
│  │  gzbridge    │◄──►│  gzserver    │◄──►│ ROS Master     │      │
│  │  (Node.js)   │IPC │  (Gazebo)    │    │ + 机器人仿真    │      │
│  │  port:8080   │    │              │    │                │      │
│  └──────────────┘    └──────────────┘    └────────────────┘      │
└──────────────────────────────────────────────────────────────────┘
```

### 1.2 通信分层定义

| 层 | 发送方 | 接收方 | 协议 | 职责 |
|---|---|---|---|---|
| **L1** (指令下发) | Vue SimControlBar | iframe embed-bridge.js | `window.postMessage` | 用户指令：暂停/重置/视图控制 |
| **L2** (状态回传) | iframe embed-bridge.js | Vue useGzBridge | `window.postMessage` | 连接状态、仿真时间、场景数据 |
| **L3** (仿真通信) | gz3d GZIface | gzbridge server.js | WebSocket (ROSLIB) | Gazebo Topic 发布/订阅 |
| **L4** (Gazebo IPC) | gzbridge C++ | gzserver | Protobuf over IPC | Gazebo 内部传输层 |

**本规范仅定义 L1 和 L2 层的精确协议。L3/L4 由 gzweb 原有代码处理，不做修改。**

### 1.3 关键设计决策

| 决策 | 选项 | 结论 | 理由 |
|---|---|---|---|
| 3D 引擎集成方式 | iframe 嵌入 vs 直接 import | **iframe** | gz3d 全局变量（GZ3D/THREE/$/angular）与 Vue 环境冲突；GZIface 与 Scene 深度耦合无法单独剥离 |
| 指令传递方式 | postMessage vs 直连 WebSocket | **postMessage** | gzbridge 协议私有且与 gz3d 内部事件耦合；直连需重写整个消息处理层 |
| 嵌入页面 | 修改 index.html vs 新建 embed.html | **新建 embed.html**（复制 index.html 修改） | 不侵入 gzweb 原项目，保持独立可用 |
| 构建产物 | gz3d.js (无 GUI) vs gz3d.gui.js (含 GUI) | **gz3d.gui.js** | gz3d.js 不含 SdfParser 依赖的 GUI 事件绑定逻辑，使用时会报错；用 CSS 隐藏 UI 更可靠 |

---

## 2. postMessage 通信协议规范

### 2.1 消息格式

所有 postMessage 消息 **必须** 遵循以下基础结构：

```typescript
interface GzMessage {
  type: string      // 命名空间前缀 "gz:" + 操作名
  payload: object   // 操作参数
}
```

**命名规则**:
- `type` 字段 **必须** 以 `gz:` 前缀开头
- Vue → iframe 的指令使用**动词/名词**命名：`gz:pause`, `gz:reset`, `gz:showGrid`
- iframe → Vue 的事件使用**名词/状态**命名：`gz:ready`, `gz:connection`, `gz:simTime`

### 2.2 Vue → iframe 指令集（L1 层）

#### 2.2.1 仿真控制

| type | payload | 说明 |
|---|---|---|
| `gz:pause` | `{ paused: boolean }` | 暂停/继续仿真 |
| `gz:reset` | `{ resetType: 'world' \| 'model' }` | 重置世界/仅重置模型姿态 |

**gz:pause 处理逻辑**:
```
接收 gz:pause → globalEmitter.emit('pause', payload.paused)
             → GZIface 监听 'pause' 事件
             → 发布 ~/world_control Topic { pause: paused }
             → gzbridge 转发给 gzserver
```

**gz:reset 处理逻辑**:
```
接收 gz:reset → globalEmitter.emit('reset', payload.resetType)
             → GZIface 监听 'reset' 事件
             → 发布 ~/world_control Topic { reset: { all: true } | { model_only: true } }
```

#### 2.2.2 视图控制

| type | payload | 说明 |
|---|---|---|
| `gz:resetView` | `{}` | 相机恢复默认视角 |
| `gz:showGrid` | `{ visible: boolean }` | 显示/隐藏地面网格 |
| `gz:showCollisions` | `{ visible: boolean }` | 显示/隐藏碰撞体 |
| `gz:showOrbitIndicator` | `{ visible: boolean }` | 显示/隐藏轨道控制器指示点（OrbitControls targetIndicator） |

**gz:resetView 处理逻辑**:
```
接收 gz:resetView → scene.resetView()
                  → 相机位置恢复到 defaultCameraPosition (0, -5, 5)
                  → OrbitControls target 恢复到 (0, 0, 0)
```

**gz:showGrid 处理逻辑**:
```
接收 gz:showGrid → scene.grid.visible = payload.visible
```

#### 2.2.3 健康检测

| type | payload | 说明 |
|---|---|---|
| `gz:ping` | `{}` | 心跳探测 |

**响应**: iframe 回传 `gz:pong` 事件（见 2.3.4）

### 2.3 iframe → Vue 事件集（L2 层）

#### 2.3.1 生命周期事件

| type | payload | 触发时机 |
|---|---|---|
| `gz:ready` | `{}` | embed-bridge.js 初始化完成，gz3d 引擎就绪 |
| `gz:connection` | `{ connected: boolean }` | WebSocket 连接成功或失败 |
| `gz:sceneLoaded` | `{ name: string }` | Gazebo 场景数据加载完成 |

#### 2.3.2 仿真状态事件

| type | payload | 触发频率 |
|---|---|---|
| `gz:paused` | `{ paused: boolean }` | 仿真暂停/继续时 |
| `gz:simTime` | `{ simTime: string }` | 跟随 gzbridge 的 world_stats 更新（~10Hz） |
| `gz:realTime` | `{ realTime: string }` | 跟随 gzbridge 的 world_stats 更新（~10Hz） |

**时间格式**: `"HH:MM:SS.mmm"`（如 `"00:01:23.456"`），由 gz3d 内部的 `setSimTime`/`setRealTime` 事件提供原始字符串。

#### 2.3.3 场景数据事件（第三期扩展）

| type | payload | 说明 |
|---|---|---|
| `gz:sceneTree` | `{ models: ModelInfo[], lights: LightInfo[] }` | 场景树数据 |
| `gz:entitySelected` | `{ name: string }` | 用户在 3D 场景中点击选中实体 |

```typescript
// 第三期扩展类型定义
interface ModelInfo {
  name: string
  id: number
  position: { x: number; y: number; z: number }
  orientation: { x: number; y: number; z: number; w: number }
  isStatic: boolean
}

interface LightInfo {
  name: string
  type: 'point' | 'spot' | 'directional'
  position: { x: number; y: number; z: number }
}
```

#### 2.3.4 健康检测响应

| type | payload | 说明 |
|---|---|---|
| `gz:pong` | `{ connected: boolean, timestamp: number }` | 心跳响应 |

### 2.4 安全校验规则

1. **origin 白名单**: embed-bridge.js 通过 URL 参数 `origin` 接收允许的来源域名
2. **消息过滤**: 接收方 **必须** 校验 `msg.type` 是否以 `gz:` 开头，忽略所有非规范消息
3. **嵌套防护**: embed-bridge.js **必须** 校验 `window.parent !== window`，避免在顶层窗口误触发

```javascript
// embed-bridge.js 中的安全校验
window.addEventListener('message', function(event) {
  // 1. origin 校验
  if (parentOrigin !== '*' && event.origin !== parentOrigin) return
  // 2. 消息格式校验
  var msg = event.data
  if (!msg || typeof msg.type !== 'string' || !msg.type.startsWith('gz:')) return
  // 3. 处理消息...
})
```

### 2.5 连接状态机

```
                    ┌─────────────┐
                    │disconnected │ ◄── 初始状态
                    └──────┬──────┘
                           │ iframe 加载完成，收到 gz:ready
                           ▼
                    ┌─────────────┐
                    │ connecting  │ ◄── gz3d 正在连接 gzbridge WebSocket
                    └──────┬──────┘
                           │
              ┌────────────┼────────────┐
              │ 收到 gz:connection      │ 收到 gz:connection
              │ { connected: true }     │ { connected: false }
              ▼                         ▼
       ┌─────────────┐          ┌─────────────┐
       │  connected  │          │    error     │
       └──────┬──────┘          └──────┬──────┘
              │                        │
              │ gz:pong 超时            │ GZIface 自动重连
              │ 或 gz:connection false  │ gz:connection { connected: true }
              ▼                        │
       ┌─────────────┐                │
       │    error     │◄───────────────┘
       └─────────────┘
```

**心跳机制**: Vue 端每 **5 秒** 发送 `gz:ping`，若 **3 秒** 内未收到 `gz:pong`，状态切换为 `error`（缩短超时以优化用户体验，让用户尽早感知连接异常）。

---

## 3. GzWeb 前端改造规范

### 3.1 新建 embed.html

**文件路径**: `/home/ubuntu20/gzweb/gz3d/client/embed.html`（源码目录，构建时由 CMake 复制到 `http/client/`）

**基于**: 复制 `index.html`（1143 行）并做以下修改：

#### 3.1.1 CSS 覆盖：隐藏全部原生 UI

在 `<head>` 中添加 `<style>` 块：

```css
/* ── 隐藏 gz3d 原生 UI ── */
.gzGUI,                        /* 所有 GUI 元素的通用类 */
#leftPanel,                    /* 左侧面板容器 (菜单/插入/场景树) */
#mainMenuTab,                  /* 菜单标签 */
#treeMenuTab,                  /* 场景树标签 */
#insertMenuTab,                /* 插入标签 */
#play-header-fieldset,         /* 播放按钮 */
#clock-header-fieldset,        /* 时钟按钮 */
#clock-mouse,                  /* 桌面端时钟显示 */
#clock-touch,                  /* 触摸端时钟弹窗 */
#manipulatorModeFieldset,      /* 操控模式 (view/translate/rotate) */
#simpleShapesFieldset,         /* 快捷形状按钮 (box/sphere/cylinder) */
#lightsFieldset,               /* 快捷灯光按钮 */
#logplay,                      /* 日志回放控制条 */
#notification-popup,           /* 通知弹窗 */
#model-popup                   /* 模型右键菜单 */
{ display: none !important; }

body {
  margin: 0;
  overflow: hidden;
  background: #1e1e2e;
}

#container {
  position: absolute;
  top: 0; left: 0;
  width: 100%; height: 100%;
}
```

#### 3.1.2 HTML body 精简

保留原 `<body>` 中的以下元素（gz3d 渲染和 AngularJS 应用所需）：

```html
<body oncontextmenu="return false;">
  <!-- AngularJS 绑定点 (gzgui.js 需要这些 DOM 节点存在) -->
  <div data-role="page" data-theme="b" data-content-theme="c">
    <!-- 保留全部原始 HTML 结构, CSS 已隐藏不需要的部分 -->
    <!-- ... 原 index.html 的完整 DOM 结构 ... -->
  </div>

  <!-- gz3d 初始化脚本: 替换原版 -->
  <script>
    // 见 3.1.3
  </script>

  <!-- embed bridge: 新增 -->
  <script src="js/embed-bridge.js"></script>
</body>
```

> **注意**: 不能删除 AngularJS 绑定的 DOM 节点（如 `ng-controller="treeControl"` 等），因为 `gz3d.gui.js` 包含 AngularJS 模块初始化代码。如果 DOM 节点缺失，AngularJS 会抛出异常。用 CSS `display: none` 隐藏即可。

#### 3.1.3 初始化脚本改造

替换原 `index.html` 底部的 `<script>` 块：

```javascript
if (!Detector.webgl)
  Detector.addGetWebGLMessage();

// 从 URL 参数读取 WebSocket 地址
// 从 hash fragment 读取 WebSocket 地址（不用 query string 因为 gzbridge 会把它拼进文件路径）
var params = new URLSearchParams(window.location.hash.substring(1));
var wsUrl = params.get('ws') || (location.hostname + ':' + location.port + location.pathname);

var container, stats;
var scene;

init();
animate();

function init() {
  var shaders = new GZ3D.Shaders();
  scene = new GZ3D.Scene(shaders);

  // ★ 关键: GZIface 第二个参数注入 WebSocket URL
  var gui = new GZ3D.Gui(scene);
  iface = new GZ3D.GZIface(scene, wsUrl);
  var sdfparser = new GZ3D.SdfParser(scene, gui, iface);

  container = document.getElementById('container');
  container.appendChild(scene.getDomElement());

  window.addEventListener('resize', onWindowResize, false);
  scene.setSize(window.innerWidth, window.innerHeight);
  window.addEventListener('keydown', scene.onKeyDown, false);
}

function onWindowResize() {
  scene.setSize(window.innerWidth, window.innerHeight);
}

function animate() {
  requestAnimationFrame(animate);
  scene.render();
}
```

> **`GZ3D.Gui` 仍然初始化**：虽然 UI 不可见，但 Gui 实例负责注册 AngularJS 控制器和事件监听器。`SdfParser` 依赖 `gui` 参数来发送通知事件。不初始化 Gui 会导致 `TypeError: Cannot read property 'emit' of undefined`。

### 3.2 embed-bridge.js 规范

**文件路径**: `/home/ubuntu20/gzweb/gz3d/client/js/embed-bridge.js`（源码目录，构建时复制到 `http/client/js/`）

**职责**: 在 iframe 内运行，桥接 postMessage ↔ gz3d globalEmitter

```javascript
/**
 * embed-bridge.js
 *
 * 在 iframe 内运行的桥接脚本。
 * 负责:
 * 1. 监听父窗口的 postMessage 指令，转发到 gz3d globalEmitter
 * 2. 监听 gz3d 事件，回传状态到父窗口
 *
 * URL 参数:
 * - ws: gzbridge WebSocket 地址 (默认: location.hostname:location.port)
 * - origin: 允许的父窗口来源 (默认: '*')
 */
(function() {
  'use strict';

  // 从 hash fragment 读取参数（不用 query string 因为 gzbridge 会把它拼进文件路径）
  var params = new URLSearchParams(window.location.hash.substring(1));
  var parentOrigin = params.get('origin') || '*';
  var emitter = globalEmitter;

  // ── 辅助: 安全发送到父窗口 ──
  function postToParent(msg) {
    if (window.parent && window.parent !== window) {
      window.parent.postMessage(msg, parentOrigin);
    }
  }

  // ════════════════════════════════════════════
  // L2: 状态回传 (iframe → Vue)
  // ════════════════════════════════════════════

  // 连接状态
  emitter.on('connection', function() {
    postToParent({ type: 'gz:connection', payload: { connected: true } });
  });

  emitter.on('connectionError', function() {
    postToParent({ type: 'gz:connection', payload: { connected: false } });
  });

  // 仿真时间
  emitter.on('setSimTime', function(time) {
    postToParent({ type: 'gz:simTime', payload: { simTime: time } });
  });

  emitter.on('setRealTime', function(time) {
    postToParent({ type: 'gz:realTime', payload: { realTime: time } });
  });

  // 暂停状态
  emitter.on('setPaused', function(paused) {
    postToParent({ type: 'gz:paused', payload: { paused: paused } });
  });

  // ════════════════════════════════════════════
  // L1: 接收指令 (Vue → iframe)
  // ════════════════════════════════════════════

  window.addEventListener('message', function(event) {
    // 安全校验
    if (parentOrigin !== '*' && event.origin !== parentOrigin) return;
    var msg = event.data;
    if (!msg || typeof msg.type !== 'string' || !msg.type.startsWith('gz:')) return;

    switch (msg.type) {
      // ── 仿真控制 ──
      case 'gz:pause':
        emitter.emit('pause', msg.payload.paused);
        break;

      case 'gz:reset':
        emitter.emit('reset', msg.payload.resetType || 'world');
        break;

      // ── 视图控制 ──
      case 'gz:resetView':
        if (typeof scene !== 'undefined' && scene.resetView) {
          scene.resetView();
        }
        break;

      case 'gz:showGrid':
        if (typeof scene !== 'undefined' && scene.grid) {
          scene.grid.visible = !!msg.payload.visible;
        }
        break;

      case 'gz:showCollisions':
        if (typeof scene !== 'undefined') {
          scene.showCollisions = !!msg.payload.visible;
          // 触发已有模型的碰撞体可见性刷新
          emitter.emit('show_collisions', msg.payload.visible ? 'show' : 'hide');
        }
        break;

      case 'gz:showOrbitIndicator':
        if (typeof scene !== 'undefined' && scene.controls) {
          scene.controls.showTargetIndicator = !!msg.payload.visible;
        }
        break;

      // ── 健康检测 ──
      case 'gz:ping':
        postToParent({
          type: 'gz:pong',
          payload: {
            connected: (typeof iface !== 'undefined') ? iface.isConnected : false,
            timestamp: Date.now()
          }
        });
        break;
    }
  });

  // ── 通知父窗口: bridge 已就绪 ──
  postToParent({ type: 'gz:ready', payload: {} });
})();
```

### 3.3 gzweb 项目改动清单

| 文件 | 操作 | 说明 |
|---|---|---|
| `gz3d/client/embed.html` | **新建** | 复制 index.html，添加 CSS 隐藏 + 修改初始化脚本 |
| `gz3d/client/js/embed-bridge.js` | **新建** | postMessage 桥接脚本 |
| `CMakeLists.txt` | **修改** | 将新文件加入构建复制列表（复制到 `http/client/`） |
| 其余所有 gz3d/gzbridge 文件 | **不改动** | 保持 gzweb 独立可用 |

---

## 4. iframe 桥接层规范 (edubot-twin 侧)

### 4.1 TypeScript 类型契约

**文件路径**: `edubot-twin-web/src/views/Simulation/panels/GzWebViewer/types.ts`

```typescript
// ════════════════════════════════════════════
// L1: Vue → iframe 指令类型
// ════════════════════════════════════════════

export interface GzPauseCommand {
  type: 'gz:pause'
  payload: { paused: boolean }
}

export interface GzResetCommand {
  type: 'gz:reset'
  payload: { resetType: 'world' | 'model' }
}

export interface GzResetViewCommand {
  type: 'gz:resetView'
  payload: Record<string, never>
}

export interface GzShowGridCommand {
  type: 'gz:showGrid'
  payload: { visible: boolean }
}

export interface GzShowCollisionsCommand {
  type: 'gz:showCollisions'
  payload: { visible: boolean }
}

export interface GzShowOrbitIndicatorCommand {
  type: 'gz:showOrbitIndicator'
  payload: { visible: boolean }
}

export interface GzPingCommand {
  type: 'gz:ping'
  payload: Record<string, never>
}

/** 所有 Vue → iframe 指令的联合类型 */
export type GzCommand =
  | GzPauseCommand
  | GzResetCommand
  | GzResetViewCommand
  | GzShowGridCommand
  | GzShowCollisionsCommand
  | GzShowOrbitIndicatorCommand
  | GzPingCommand

// ════════════════════════════════════════════
// L2: iframe → Vue 事件类型
// ════════════════════════════════════════════

export interface GzReadyEvent {
  type: 'gz:ready'
  payload: Record<string, never>
}

export interface GzConnectionEvent {
  type: 'gz:connection'
  payload: { connected: boolean }
}

export interface GzSimTimeEvent {
  type: 'gz:simTime'
  payload: { simTime: string }
}

export interface GzRealTimeEvent {
  type: 'gz:realTime'
  payload: { realTime: string }
}

export interface GzPausedEvent {
  type: 'gz:paused'
  payload: { paused: boolean }
}

export interface GzPongEvent {
  type: 'gz:pong'
  payload: { connected: boolean; timestamp: number }
}

/** 所有 iframe → Vue 事件的联合类型 */
export type GzEvent =
  | GzReadyEvent
  | GzConnectionEvent
  | GzSimTimeEvent
  | GzRealTimeEvent
  | GzPausedEvent
  | GzPongEvent

// ════════════════════════════════════════════
// 状态类型
// ════════════════════════════════════════════

/** 连接状态机状态 */
export type GzConnectionStatus = 'disconnected' | 'connecting' | 'connected' | 'error'
```

### 4.2 useGzBridge Composable 接口

**文件路径**: `edubot-twin-web/src/views/Simulation/composables/useGzBridge.ts`

**设计原则**: **页面级初始化**——`useGzBridge` 在仿真页面 (`Simulation.vue`) 加载时即创建隐藏 iframe 并建立通信，不依赖 GzWebViewer 面板是否已挂载。GzWebViewer 面板仅负责将 iframe 移入/移出可视容器。

**公开接口**:

```typescript
import type { Ref } from 'vue'
import type { GzCommand, GzConnectionStatus } from '../types'

export interface UseGzBridgeReturn {
  // ── 只读状态 ──
  connectionStatus: Ref<GzConnectionStatus>
  isPaused: Ref<boolean>
  simTime: Ref<string>
  realTime: Ref<string>
  isBridgeReady: Ref<boolean>
  isConnected: ComputedRef<boolean>
  isAttached: Ref<boolean>   // iframe 是否已 attach 到 GzWebViewer 面板

  // ── 页面级生命周期 ──
  initialize: (gzwebUrl: string) => void
  dispose: () => void

  // ── 面板级集成 ──
  attachToContainer: (container: HTMLElement) => void
  detachFromContainer: () => void

  // ── 指令方法 ──
  sendCommand: (command: GzCommand) => void
  pause: () => void
  resume: () => void
  togglePause: () => void
  resetWorld: () => void
  resetModels: () => void
  resetView: () => void
  showGrid: (visible: boolean) => void
  showCollisions: (visible: boolean) => void
  showOrbitIndicator: (visible: boolean) => void
  updateGzwebUrl: (gzwebUrl: string) => void
}
```

**内部实现约束**:

1. `sendCommand()` **必须** 在 `isBridgeReady.value === true` 时才发送，否则静默忽略
2. `handleMessage()` **必须** 校验 `event.data.type` 以 `gz:` 开头
3. 心跳定时器 **必须** 在 `dispose()` 中清理
4. 模块级单例：所有调用者共享同一组状态
5. `initialize()` 自行创建隐藏 iframe 并挂到 `document.body` 上，无需外部传入 iframe 元素
6. iframe 始终是 `document.body` 的直接子元素，**绝不做 DOM 移动**（浏览器会重新加载被移动的 iframe）
7. `attachToContainer()` 通过 `position:fixed` + RAF 循环将 iframe 视觉对齐到容器 `getBoundingClientRect()`
8. `detachFromContainer()` 停止 RAF 循环并将 iframe 移到屏幕外隐藏，通信不中断
9. `_syncPosition()` 内部检测容器是否脱离 DOM（`document.contains()`），自动回退到隐藏状态

### 4.3 iframe URL 构造规则

```typescript
/**
 * 构造 iframe src URL
 *
 * @param gzwebUrl - gzbridge HTTP 服务地址 (如 "http://192.168.1.100:9001")
 * @returns embed.html 完整 URL (如 "http://192.168.1.100:9001/embed.html?ws=192.168.1.100:9001/&origin=http://localhost:4000")
 */
function buildIframeSrc(gzwebUrl: string): string {
  try {
    const url = new URL(gzwebUrl)
    const wsHost = url.hostname + ':' + url.port + '/'
    // 使用 hash fragment 而非 query params
    // 因为 gzbridge server.js 会将 query string 拼进文件路径导致 404
    const hashParams = new URLSearchParams()
    hashParams.set('ws', wsHost)
    hashParams.set('origin', window.location.origin)
    return `${url.origin}/embed.html#${hashParams.toString()}`
  } catch {
    return gzwebUrl + '/embed.html'
  }
}
```

### 4.4 iframe 生命周期管理

```
仿真页面加载 (Simulation.vue onMounted)
  │
  ├─ useGzBridge().initialize(gzwebUrl)
  │   ├─ 创建 iframe (position:fixed 移到屏幕外) 挂到 document.body
  │   ├─ 设置 iframe.src = buildIframeSrc(gzwebUrl)
  │   ├─ 注册 window 'message' 监听器
  │   │
  │   ├─ 等待 gz:ready 事件
  │   │   └─ isBridgeReady = true, connectionStatus = 'connecting'
  │   │   └─ 启动心跳定时器 (5s 间隔)
  │   │
  │   └─ 等待 gz:connection { connected: true }
  │       └─ connectionStatus = 'connected'
  │       └─ SimControlBar 按钮自动变为可用
  │
  └─ 此时 GzWebViewer 面板可能尚未挂载，但通信已建立

GzWebViewer 面板挂载 (onMounted)
  │
  ├─ registerPanel()
  ├─ useGzBridge().attachToContainer(containerEl)
  │   └─ 启动 RAF 位置同步: iframe position:fixed 对齐到容器 → 用户可见 3D 场景
  │   └─ iframe 始终留在 body，不做 DOM 移动
  │
  └─ 正常运行:
      ├─ config.showGrid 变化 → sendCommand(gz:showGrid)
      └─ config.gzwebUrl 变化 → updateGzwebUrl(newUrl)

GzWebViewer 面板卸载 (onBeforeUnmount)
  │
  ├─ useGzBridge().detachFromContainer()
  │   └─ 停止 RAF 位置同步，将 iframe 移到屏幕外隐藏，通信不中断
  │   └─ 若容器已被 GL 从 DOM 移除，_syncPosition 会自动回退
  └─ unregisterPanel()

仿真页面卸载 (Simulation.vue onBeforeUnmount)
  │
  ├─ useGzBridge().dispose()
  │   ├─ 停止心跳定时器
  │   ├─ 移除 'message' 监听器
  │   ├─ 从 DOM 移除 iframe
  │   └─ 重置所有状态
  └─ 保存布局等其他清理
```

---

## 5. Vue 控制 UI 接口规范

### 5.1 核心思路（单实例简化版）

- **架构简化**: 移除所有多实例管理逻辑，系统假定只有一个主 `GzWebViewer` 实例。
- **状态集中化**: 使用一个 **`useGzBridge.ts` composable** 作为**单例（Singleton）**或 **Pinia store**，集中管理所有 GzWeb 连接状态、仿真时间和通信逻辑。
- **组件解耦**: `SimControlBar.vue` (控制栏) 和 `GzWebViewer.vue` (Iframe 容器) 完全解耦。它们不直接通信，而是分别与 `useGzBridge` 交互，读取其状态并调用其方法。
- **自动可用**: `SimControlBar` 的按钮可用性由 `useGzBridge` 中的连接状态 (`connectionStatus`) 自动控制。一旦 `GzWebViewer` 报告连接成功，`SimControlBar` 自动变为可用。

### 5.2 组件架构与文件结构

```
src/
├── views/Simulation/
│   ├── SimulationHeader.vue         # 顶部头，内含 SimControlBar
│   └── panels/GzWebViewer/
│       └── index.vue                # GzWeb iframe 容器
│
├── components/
│   └── SimControlBar.vue            # 新建：独立的仿真控制栏组件
│
└── composables/
    └── useGzBridge.ts               # 新建：全局 GzWeb 状态和通信 Store
```

### 5.3 `useGzBridge.ts` Composable 规范

**文件路径**: `edubot-twin-web/src/views/Simulation/composables/useGzBridge.ts`

**职责**: 整个 GzWeb 集成功能的核心，负责 iframe 创建、状态管理和通信。

**关键设计**: 页面级初始化 + 面板级视图集成
- `initialize(gzwebUrl)`: 由 `Simulation.vue` 在 `onMounted` 时调用，自行创建隐藏 iframe
- `attachToContainer(el)` / `detachFromContainer()`: 由 `GzWebViewer` 调用，将 iframe 移入/移出可视容器
- `dispose()`: 由 `Simulation.vue` 在 `onBeforeUnmount` 时调用，彻底销毁 iframe

```typescript
import { ref, readonly, computed } from 'vue'
import type { GzCommand, GzEvent, GzConnectionStatus } from '...' // 引入类型

// ── 模块级单例状态 ──
const _iframe = ref<HTMLIFrameElement | null>(null)
const _connectionStatus = ref<GzConnectionStatus>('disconnected')
const _isPaused = ref<boolean>(true)
const _simTime = ref('00:00:00.000')
const _realTime = ref('00:00:00.000')
const _isBridgeReady = ref(false)
const _isAttached = ref(false)

export function useGzBridge() {

  // ── 页面级生命周期（由 Simulation.vue 调用）──

  // 初始化: 创建隐藏 iframe 并开始监听 postMessage
  const initialize = (gzwebUrl: string) => {
    if (_iframe.value) return  // 防止重复初始化
    const el = document.createElement('iframe')
    el.src = buildIframeSrc(gzwebUrl)
    el.style.cssText = 'position:absolute;width:0;height:0;border:none;visibility:hidden;'
    document.body.appendChild(el)
    _iframe.value = el
    window.addEventListener('message', handleMessage)
  }

  // 销毁: 移除 iframe、清理所有监听器和定时器
  const dispose = () => {
    stopHeartbeat()
    window.removeEventListener('message', handleMessage)
    if (_iframe.value) { _iframe.value.remove(); _iframe.value = null }
    resetState()
  }

  // ── 面板级集成（由 GzWebViewer 调用）──

  // 将 iframe 移入可视容器
  const attachToContainer = (container: HTMLElement) => {
    if (!_iframe.value) return
    container.appendChild(_iframe.value)
    _iframe.value.style.cssText = 'width:100%;height:100%;border:none;display:block;'
    _isAttached.value = true
  }

  // 将 iframe 移回 body 隐藏（通信不中断）
  const detachFromContainer = () => {
    if (!_iframe.value) return
    document.body.appendChild(_iframe.value)
    _iframe.value.style.cssText = 'position:absolute;width:0;height:0;border:none;visibility:hidden;'
    _isAttached.value = false
  }

  // ── 指令方法 ──
  const togglePause = () => sendCommand({ type: 'gz:pause', payload: { paused: !_isPaused.value } })
  const resetWorld = () => sendCommand({ type: 'gz:reset', payload: { resetType: 'world' } })
  const updateGzwebUrl = (gzwebUrl: string) => { /* 重新设置 iframe.src */ }
  // ... 其他指令

  return {
    connectionStatus: readonly(_connectionStatus),
    isPaused: readonly(_isPaused),
    simTime: readonly(_simTime),
    realTime: readonly(_realTime),
    isConnected: computed(() => _connectionStatus.value === 'connected'),
    isAttached: readonly(_isAttached),

    initialize, dispose,
    attachToContainer, detachFromContainer,
    togglePause, resetWorld, updateGzwebUrl,
    // ... 其他方法
  }
}
```

### 5.4 `SimControlBar.vue` 组件规范

**文件路径**: `edubot-twin-web/src/components/SimControlBar.vue`

**职责**: 显示仿真状态，提供控制按钮。它是一个纯粹的 UI 组件，业务逻辑完全委托给 `useGzBridge`。

```vue
<template>
  <div class="sim-control-bar">
    <span class="status-light" :class="connectionStatus"></span>
    <button @click="togglePause" :disabled="!isConnected">
      {{ isPaused ? '▶' : '⏸' }}
    </button>
    <button @click="resetWorld" :disabled="!isConnected">⟲</button>
    <div class="time-display">Real: {{ realTime }}</div>
    <div class="time-display">Sim: {{ simTime }}</div>
  </div>
</template>

<script setup lang="ts">
import { useGzBridge } from '@/composables/useGzBridge';

// 从全局 Store 获取所有状态和方法
const {
  connectionStatus,
  isPaused,
  simTime,
  realTime,
  isConnected,
  togglePause,
  resetWorld,
} = useGzBridge();
</script>
```
**关键点**:
- **无 Props/Emits**: 不再需要通过父组件传递状态或事件。
- **直接注入**: 直接调用 `useGzBridge()` 获取所需的一切。

### 5.5 `GzWebViewer/index.vue` 组件规范

**文件路径**: `edubot-twin-web/src/views/Simulation/panels/GzWebViewer/index.vue`

**职责**: 作为 iframe 的**可视窗口**——将 `useGzBridge` 管理的 iframe 移入/移出面板容器。**不负责创建或销毁 iframe**。

```vue
<template>
  <div class="gzweb-viewer">
    <!-- iframe 通过 attachToContainer 移入此 div -->
    <div ref="iframeContainer" class="gzweb-iframe-container"></div>
    <!-- 连接中遮罩层 -->
    <div v-if="connectionStatus !== 'connected'" class="gzweb-overlay">...</div>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted, onBeforeUnmount } from 'vue';
import { useGzBridge } from '../../composables/useGzBridge';

const { connectionStatus, attachToContainer, detachFromContainer, updateGzwebUrl } = useGzBridge();
const iframeContainer = ref<HTMLElement | null>(null);

onMounted(() => {
  // 将 useGzBridge 管理的 iframe 移入面板容器
  if (iframeContainer.value) {
    attachToContainer(iframeContainer.value);
  }
});

onBeforeUnmount(() => {
  // 将 iframe 移回 body（隐藏），通信不中断
  detachFromContainer();
});
</script>
```
**关键点**:
- **不调用 `initialize` / `dispose`**: iframe 生命周期由 `Simulation.vue` 管理。
- **attach/detach 模式**: 面板挂载时 `attachToContainer` 让用户看到 3D 场景；面板卸载时 `detachFromContainer` 让 iframe 回到 body 隐藏，但通信持续。
- **面板关闭不影响仿真控制**: SimControlBar 仍可正常工作。

### 5.6 状态与通信流程 (页面级初始化版)

1.  **仿真页面加载** (`Simulation.vue` onMounted):
    - `Simulation.vue` 调用 `useGzBridge().initialize(gzwebUrl)`。
    - `useGzBridge` 创建隐藏 iframe (`display:none`) 并挂到 `document.body`。
    - 注册 `window` 的 `message` 事件监听器。
    - **此时 GzWebViewer 面板可能尚未挂载，但通信模块已开始工作。**

2.  **连接建立** (与 GzWebViewer 面板无关):
    - 隐藏 iframe 加载 `embed.html`，`embed-bridge.js` 执行。
    - `embed-bridge.js` 发送 `gz:ready` → `useGzBridge` 捕获，`connectionStatus = 'connecting'`，启动心跳。
    - `gz3d` 连接 WebSocket 成功 → `embed-bridge.js` 发送 `gz:connection` → `connectionStatus = 'connected'`。

3.  **UI 自动更新**:
    - `useGzBridge` 中的 `isConnected` computed 属性变为 `true`。
    - `SimControlBar` 依赖此 computed 属性，自动将按钮的 `disabled` 状态移除。**控制栏变为可用。**
    - **即使 GzWebViewer 面板已关闭，SimControlBar 仍可控制仿真。**

4.  **GzWebViewer 面板挂载** (可选):
    - `GzWebViewer` 的 `onMounted` 调用 `attachToContainer(containerEl)`。
    - iframe 从 body 移入面板容器 → 用户可见 3D 场景。

5.  **GzWebViewer 面板关闭** (可选):
    - `onBeforeUnmount` 调用 `detachFromContainer()`。
    - iframe 移回 body (隐藏)，**通信不中断**。
    - SimControlBar 连接灯仍为绿色，仿真时间继续更新。

6.  **用户操作**:
    - 用户点击 `SimControlBar` 上的 "Pause" 按钮。
    - `@click` 事件触发 `useGzBridge` 的 `togglePause` 方法。
    - `togglePause` 方法通过 `sendCommand` 向 (隐藏或可见的) iframe 发送 `gz:pause` 指令。
    - ...后续流程与 `postMessage` 协议定义一致。

7.  **仿真页面卸载** (`Simulation.vue` onBeforeUnmount):
    - 调用 `useGzBridge().dispose()` → 移除 iframe、清理定时器、重置状态。


---

## 6. 后端容器管理 API 规范

### 6.1 数据模型

**文件路径**: `edubot-twin-server/app/models/container.py`

```python
import enum
from datetime import datetime
from typing import Optional
from sqlalchemy import String, Integer, DateTime, Enum, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column
from app.db.base import Base


class ContainerStatus(str, enum.Enum):
    """容器生命周期状态"""
    CREATING = "creating"      # Docker 正在创建容器
    RUNNING = "running"        # 容器运行中, gzbridge 可用
    STOPPED = "stopped"        # 容器已停止
    ERROR = "error"            # 创建/运行出错
    REMOVING = "removing"      # 正在删除容器


class SimContainer(Base):
    """仿真容器"""
    __tablename__ = "sim_containers"

    id: Mapped[int] = mapped_column(
        Integer, primary_key=True, autoincrement=True
    )
    container_id: Mapped[Optional[str]] = mapped_column(
        String(64), unique=True, nullable=True,
        comment="Docker 容器 ID (sha256 前 12 位)"
    )
    student_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("students.id"), nullable=False, index=True
    )
    image_name: Mapped[str] = mapped_column(
        String(200), nullable=False, default="edubot/gazebo-ros:latest"
    )
    status: Mapped[ContainerStatus] = mapped_column(
        Enum(ContainerStatus), default=ContainerStatus.CREATING, nullable=False
    )
    gzbridge_port: Mapped[Optional[int]] = mapped_column(
        Integer, nullable=True,
        comment="gzbridge WebSocket 宿主机映射端口"
    )
    rosbridge_port: Mapped[Optional[int]] = mapped_column(
        Integer, nullable=True,
        comment="rosbridge WebSocket 宿主机映射端口"
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, onupdate=datetime.utcnow
    )
```

### 6.2 Pydantic Schemas

**文件路径**: `edubot-twin-server/app/schemas/container.py`

```python
from pydantic import BaseModel
from typing import Optional
from datetime import datetime


class ContainerCreate(BaseModel):
    """创建容器请求体"""
    student_id: int
    image_name: str = "edubot/gazebo-ros:latest"


class ContainerResponse(BaseModel):
    """容器完整信息"""
    id: int
    container_id: Optional[str] = None
    student_id: int
    status: str
    gzbridge_port: Optional[int] = None
    rosbridge_port: Optional[int] = None
    gzbridge_url: Optional[str] = None
    rosbridge_url: Optional[str] = None
    created_at: datetime

    class Config:
        from_attributes = True


class ContainerStatusResponse(BaseModel):
    """容器简要状态"""
    id: int
    status: str
    gzbridge_url: Optional[str] = None
```

### 6.3 RESTful 端点

#### 6.3.1 教师端 (管理操作)

**路由前缀**: `/api/v1/teacher/containers`
**文件路径**: `edubot-twin-server/app/api/v1/endpoints/teacher/containers.py`

| 方法 | 路径 | 请求体 | 响应 | 说明 |
|---|---|---|---|---|
| `POST` | `/` | `ContainerCreate` | `ApiResponse[ContainerResponse]` | 为指定学生创建容器 |
| `GET` | `/` | - | `ApiResponse[list[ContainerResponse]]` | 列出所有容器 |
| `GET` | `/{id}` | - | `ApiResponse[ContainerResponse]` | 获取容器详情 |
| `POST` | `/{id}/start` | - | `ApiResponse[ContainerResponse]` | 启动已停止的容器 |
| `POST` | `/{id}/stop` | - | `ApiResponse[ContainerResponse]` | 停止运行中的容器 |
| `DELETE` | `/{id}` | - | `ApiResponse[None]` | 删除容器 |

#### 6.3.2 学生端 (只读 + 请求分配)

**路由前缀**: `/api/v1/student/container`
**文件路径**: `edubot-twin-server/app/api/v1/endpoints/student/container.py`

| 方法 | 路径 | 请求体 | 响应 | 说明 |
|---|---|---|---|---|
| `GET` | `/mine` | - | `ApiResponse[ContainerStatusResponse]` | 获取当前学生的容器信息 |
| `POST` | `/request` | - | `ApiResponse[ContainerResponse]` | 请求分配容器 |

#### 6.3.3 URL 计算规则

`gzbridge_url` 和 `rosbridge_url` 为计算字段，基于服务器配置：

```python
# 在 Schema 序列化时或 API 层计算
SERVER_HOST = os.getenv("SERVER_HOST", "localhost")

gzbridge_url = f"http://{SERVER_HOST}:{container.gzbridge_port}" if container.gzbridge_port else None
rosbridge_url = f"ws://{SERVER_HOST}:{container.rosbridge_port}" if container.rosbridge_port else None
```

### 6.4 端口分配策略

**文件路径**: `edubot-twin-server/app/core/port_allocator.py`

```python
GZBRIDGE_PORT_RANGE = (9000, 9499)     # 500 个端口, 支持 500 个并发容器
ROSBRIDGE_PORT_RANGE = (9500, 9999)    # 500 个端口

async def allocate_ports(db: AsyncSession) -> tuple[int, int]:
    """
    分配一对可用端口 (gzbridge_port, rosbridge_port)

    算法:
    1. 查询 sim_containers 表中 status IN ('creating', 'running') 的记录
    2. 收集已占用的 gzbridge_port 和 rosbridge_port
    3. 从端口范围中找到第一个未占用的端口
    4. 若范围耗尽, 抛出 PortExhaustedError

    返回: (gzbridge_port, rosbridge_port)
    """
```

### 6.5 Docker 容器操作

```python
# 容器创建参数
container = docker_client.containers.run(
    image=image_name,
    detach=True,
    ports={
        '8080/tcp': gzbridge_port,       # gzbridge WebSocket
        '9090/tcp': rosbridge_port,      # rosbridge WebSocket (ROS 通信)
    },
    mem_limit='2g',                      # 内存限制
    cpus=2.0,                            # CPU 限制
    labels={
        'edubot.student_id': str(student_id),
        'edubot.type': 'simulation'
    },
    name=f'edubot-sim-{student_id}'
)
```

---

## 7. 静态资源部署规范

### 7.1 开发环境

gzweb 前端文件由 `gzbridge/server.js` 提供静态服务（默认端口 8080）。开发时：

```
edubot-twin-web (localhost:4000)  →  iframe src="http://localhost:8080/embed.html"
                                                    ↑
                                              gzbridge server.js 提供
```

**不需要 Vite 代理**——iframe 直连 gzbridge 端口。

### 7.2 生产环境

通过 Nginx 统一入口，反向代理到各容器端口：

```nginx
# 每个学生容器的 gzbridge 代理
location ~ ^/sim/(\d+)/(.*) {
    set $port $1;
    proxy_pass http://127.0.0.1:$port/$2;
    proxy_http_version 1.1;
    proxy_set_header Upgrade $http_upgrade;
    proxy_set_header Connection "upgrade";    # WebSocket 支持
}
```

### 7.3 模型资源 (assets/)

Gazebo 3D 模型资源（`http/client/assets/` 下的 `.dae`, `.obj`, `.stl` 文件）由 gzbridge 的 HTTP 服务直接提供。

**Docker 镜像构建时包含**:
```dockerfile
COPY gzweb/http/client/ /opt/gzweb/http/client/
```

**无需在 edubot-twin 中托管模型资源**。

---

## 8. 实施分期

### 第一期：iframe 嵌入 + 基础控制 (MVP)

**目标**: GzWebViewer 面板显示 gz3d 3D 场景，支持 Play/Pause/Reset

| 范围 | 文件 | 操作 |
|---|---|---|
| gzweb | `gz3d/client/embed.html` | 新建 (复制 index.html + 修改) |
| gzweb | `gz3d/client/js/embed-bridge.js` | 新建 |
| gzweb | `CMakeLists.txt` | 修改 (将新文件加入构建复制列表) |
| 前端 | `panels/GzWebViewer/types.ts` | 新建 |
| 前端 | `panels/GzWebViewer/composables/useGzBridge.ts` | 新建 |
| 前端 | `panels/GzWebViewer/index.vue` | 改造 (占位 → iframe) |
| 前端 | `panels/GzWebViewer/settings.ts` | 扩展 (新增 showOrbitIndicator 字段) |
| 前端 | `components/SimControlBar.vue` | 新建 (仿真控制栏) |
| 前端 | `components/SimulationHeader.vue` | 改造 (集成 SimControlBar) |

**前置条件**: gzbridge 本地可用 (`npm start`)，gzserver 运行中

**验收标准**:
1. GzWebViewer 面板显示 Gazebo 3D 场景（非占位图）
2. SimulationHeader 顶部控制栏正确显示连接状态、Real Time、Sim Time
3. Play/Pause/Reset World/Reset Models/Reset View 功能正常
4. Settings 侧栏可切换 showGrid、showCollisions、showOrbitIndicator
5. 断开 gzbridge 后，连接状态指示灯变红

### 第二期：容器管理 API + 动态连接

**目标**: 后端管理 Docker 容器生命周期，前端动态获取 gzbridge 地址

| 范围 | 文件 | 操作 |
|---|---|---|
| 后端 | `app/models/container.py` | 新建 |
| 后端 | `app/schemas/container.py` | 新建 |
| 后端 | `app/crud/container.py` | 新建 |
| 后端 | `app/core/port_allocator.py` | 新建 |
| 后端 | `app/api/v1/endpoints/teacher/containers.py` | 新建 |
| 后端 | `app/api/v1/endpoints/student/container.py` | 新建 |
| 前端 | `api/container.ts` | 新建 (HTTP 请求封装) |
| 前端 | `panels/GzWebViewer/index.vue` | 改造 (从 API 获取 URL) |
| Docker | `Dockerfile.gazebo-ros` | 新建 |

**验收标准**:
1. 教师可通过 API 为学生创建/停止/删除容器
2. 学生登录后自动获取分配的容器信息
3. GzWebViewer 面板根据 API 返回的端口自动连接对应容器

### 第三期：高级控制

**目标**: 场景树、模型操作等进阶功能

**扩展 postMessage 指令集**:

| type | payload | 说明 |
|---|---|---|
| `gz:getSceneTree` | `{}` | 请求场景树数据 |
| `gz:selectEntity` | `{ name: string }` | 选中指定实体 |
| `gz:setManipMode` | `{ mode: 'view' \| 'translate' \| 'rotate' }` | 切换操控模式 |
| `gz:deleteEntity` | `{ name: string }` | 删除指定实体 |
| `gz:spawnEntity` | `{ type: string, position: {x,y,z} }` | 生成实体 |

**验收标准**:
1. Vue 侧可显示场景树（模型/灯光列表）
2. 点击场景树中的模型，3D 场景中高亮选中
3. 支持模型的平移/旋转/删除操作

---

## 附录 A: 风险与缓解

| 风险 | 影响 | 缓解方案 |
|---|---|---|
| iframe 跨域 Cookie/Storage 不共享 | 不影响——gz3d 不依赖 Cookie | 无需额外处理 |
| gz3d Three.js (r77) 版本过旧 | iframe 隔离确保不影响 edubot-twin 的 Three.js | 无需升级 |
| AngularJS 初始化报错 (DOM 节点缺失) | 保留完整 DOM 结构，用 CSS 隐藏 | embed.html 复制完整 index.html |
| gzbridge 不支持 HTTPS | 生产环境安全问题 | Nginx 反向代理 + TLS 终止 |
| postMessage 高频状态回传 (simTime ~10Hz) | 可能影响 Vue 渲染性能 | 在 embed-bridge.js 中节流 (throttle 100ms) |
| Docker SDK 异步集成 | Python docker 包同步阻塞 | 使用 `run_in_executor` 或 `aiodocker` |

## 附录 B: gzweb 关键 globalEmitter 事件索引

以下是 embed-bridge.js 需要监听或触发的 gz3d 内部事件：

| 事件名 | 方向 | 参数 | 来源文件 |
|---|---|---|---|
| `connection` | 监听 | - | gziface.js:77 |
| `connectionError` | 监听 | - | gziface.js:56 |
| `setPaused` | 监听 | `paused: boolean` | gzgui.js |
| `setSimTime` | 监听 | `time: string` | gzgui.js |
| `setRealTime` | 监听 | `time: string` | gzgui.js |
| `pause` | 触发 | `paused: boolean` | gziface.js → ~/world_control |
| `reset` | 触发 | `resetType: string` | gziface.js → ~/world_control |
| `show_collisions` | 触发 | `'show' \| 'hide'` | gzgui.js |
