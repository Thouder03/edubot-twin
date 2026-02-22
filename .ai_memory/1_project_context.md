# 数字孪生机器人实训平台 - 项目核心设计与规范文档

## 1. 项目概览 (Project Overview)

本项目是一个面向高校机器人教学的**数字孪生实训平台**。前端基于 **vue-element-plus-admin** 架构进行深度定制，后端采用 **FastAPI** + **SQLite/PostgreSQL** + **Docker** 架构。

平台分为两个核心视口：

1.  **教师管理端 (Teacher Portal)**: 侧重于容器集群管理、性能监控、学生学情分析与课程资源分发。
2.  **学生实训端 (Student Workbench)**: 侧重于沉浸式的机器人仿真交互（ROS 3D 可视化 + GzWeb 仿真场景）。

### 前端技术栈

- **Core Framework**: Vue 3.5 (Composition API, `<script setup>`)
- **Build Tool**: Vite 6.0.7
- **UI Library**: Element Plus 2.9.2 (Admin Layout), UnoCSS (Atomic Styles)
- **Robotics & Visualization**:
  - **`roslibjs`**: 与 ROS 系统进行 WebSocket 通信。
  - **`ros3djs`**: 基于 WebGL 的机器人三维可视化（雷达、地图、TF、路径）。
  - **`xterm.js`**: Web 端 SSH/Shell 终端仿真。
  - **`GzWeb`**: 嵌入式 Gazebo 仿真场景 (Iframe集成)。
- **Language**: TypeScript 5.7.3
- **State Management**: Pinia 2.3.0 (User Auth, Docker Status, ROS Connection)
- **CSS Engine**: Less + UnoCSS

### 后端技术栈

- **Framework**: FastAPI 0.115.0 (高性能异步 Web 框架)
- **ORM**: SQLAlchemy 2.0+ (异步模式)
- **Database**: SQLite (开发) / PostgreSQL (生产)
- **Validation**: Pydantic V2
- **Password**: bcrypt 加密
- **Server**: Uvicorn (ASGI)
- **Architecture**: 模块化分层架构 (按角色和功能拆分)

---

## 2. 功能架构设计 (Functional Architecture)

基于需求架构图设计，前端路由与布局分为两套逻辑：

### 2.1 教师端 (Admin Layout)

采用标准的后台管理布局（Sidebar + Header + TagsView）。

- **Dashboard**: 实时展示学生在线数、服务器性能监控 (CPU/Mem)、容器池状态。
- **容器管理 (Docker Manager)**:
  - 容器列表 (二级菜单): 展示容器 ID、对应的学生、IP/Port、性能占用、Diff 文件变动。
  - 控制台: 启动、停止、删除、执行命令 (Exec)、重置环境。
- **教学管理**: 课程文件分发 (roslaunch/py)、自动化评测配置。
- **学情分析**: 学生学习曲线、任务完成度统计。

### 2.2 学生端 (Simulation Layout)

采用全屏沉浸式布局（无 Sidebar，仅保留顶部工具栏或悬浮球）。

- **工作台 (Workbench)**:
  - **左分屏 (ROS3D)**: 显示 RViz 风格的 3D 视图（点云、地图、虚拟摇杆、摄像头流）。
  - **右分屏 (Tools)**:
    - **GzWeb**: 嵌入 Gazebo 物理仿真画面。
    - **Code Editor**: 在线代码编辑与上传。
    - **Terminal**: Web 终端，执行 ROS 命令。
- **模式切换**:
  - **练习模式**: 自由仿真，提供代码调试与重置。
  - **考试模式**: 限制特定功能，显示倒计时与自动评分目标。
- **布局系统 (Golden Layout)**:
  - 采用 **v2.6.0** 版本，支持面板拖拽、拆分、堆叠。
  - **SettingsSidebar**: 左侧可折叠的设置侧栏，支持拖拽调整宽度。
  - **PanelSettings**: 基于 Settings Tree 的通用配置面板，动态生成表单。

---

## 3. 设计语言与样式规范 (Design Language & Styling)

### 3.1 混合样式系统

- **BEM (Less)**: 用于复杂的机器人可视化组件（如 `RosViewer__canvas`, `RosViewer__controls`）。
- **Atomic CSS (UnoCSS)**: 大量用于学生端工作台的 Flex 布局与间距微调。

### 3.2 样式隔离

- 使用 `useDesign` Hook 生成前缀（默认 `v-`），特别是针对 ROS 组件，避免与 Element Plus 样式冲突。

### 3.3 主题与暗黑模式

- **仿真环境适配**: 学生端默认建议开启 **Dark Mode**，以配合 RViz/Terminal 的深色风格，减少视觉疲劳。

---

## 4. 编码风格与目录规范 (Coding Style)

### 4.1 TypeScript 规范

- **ROS Types**: 尽量为 ROS Message 定义 Interface（如 `Twist`, `Odometry`），避免在通信层大量使用 `any`。

### 4.2 目录结构规范 (Directory Structure)

```text
src/
├── api/
│   ├── docker/          # 容器控制接口
│   └── ros/             # 历史数据查询接口
├── components/
│   ├── Ros/             # ROS 相关通用组件
│   │   ├── RosViewer.vue
│   │   ├── Joystick.vue
│   │   └── Terminal.vue
│   └── Docker/          # 容器状态组件
├── views/
│   ├── teacher/         # 教师端页面
│   │   └── Container/
│   ├── student/         # 学生端页面（首页、非仿真页）
│   │   └── Home.vue
│   └── Simulation/      # ★ 核心仿真工作台（独立视图）
│       ├── Simulation.vue
│       ├── components/  # GL 桥接、SettingsSidebar、PanelSettings
│       ├── panels/      # 各类功能面板定义 (Index.vue + settings.ts)
│       └── stores/      # 局部状态 (PanelState)
├── hooks/
│   └── web/
│       ├── useRos.ts    # ROS 连接与状态管理 Hook
│       └── useTerminal.ts
└── store/
    ├── modules/
    │   ├── docker.ts    # 容器状态 Store
    │   └── ros.ts       # ROS 连接状态 Store

```

---

## 5. 核心设计模式 (Design Patterns)

### 5.1 Service Layer (Hybrid)

- **HTTP (Axios)**: 用于常规的 CRUD 操作（如登录、获取学生列表、启动/停止容器）。
- **WebSocket (Native/Roslib)**:
- **ROS 通信**: 使用 `roslibjs` 建立 WebSocket 连接，订阅 `/scan`, `/odom` 等话题。
- **容器监控**: 使用 WebSocket 实时接收 Docker 容器的 `docker stats` 流数据。

### 5.2 Iframe Integration Pattern

- **GzWeb 集成**: 由于 GzWeb 独立运行且技术栈较旧，采用 `iframe` 嵌入学生端右侧面板，通过 `postMessage` 进行简单的父子页面通信（如重置视角）。

### 5.3 Settings Tree Pattern (Simulation)

- **配置驱动**: 每个仿真面板通过 `settings.ts` 导出一个设置树对象（JSON Schema 风格），描述其可配置项。
- **动态渲染**: 通用的 `PanelSettings` 组件读取当前选中面板的设置树，自动生成 Element Plus 表单控件。
- **侧栏集成**: `SettingsSidebar` 作为主布局的一部分（非 GL 组件），提供流畅的配置体验。

### 5.4 Component Encapsulation

- **RosViewer**: 封装 `ros3djs` 的Viewer初始化逻辑，对外暴露 `topic`、`frameId` 等 Props，使业务组件只需关注配置而非底层 WebGL 实现。

### 5.5 ROS3D Renderer Architecture (Lichtblick Shim)

本项目的 `ROS3DViewer` 采用移植自 Lichtblick 的 **Renderer-Extension** 架构，核心原则如下：

1.  **解耦设计**: `Renderer` 类不直接依赖 `roslib`，而是通过 `addMessageEvent()` 接收标准化数据。
2.  **桥接模式 (Bridge Pattern)**:
    - `index.vue` 作为**桥接层**，负责建立 ROS 连接、订阅 Topics (如 `/tf`)。
    - 收到 ROS 消息后，**必须**将其包装为 `{ topic, schemaName, message, receiveTime }` 格式，手动注入 Renderer。
3.  **扩展注册显式化**:
    - 所有 3D 功能（网格、坐标系、雷达）都是 **SceneExtension**。
    - 必须在 `useRenderer.ts` 的 `createExtensionConfig()` 中**显式注册**扩展（如 `Grids`, `FrameAxes`），否则对应的配置节点将无效。
4.  **按需渲染 (On-Demand Rendering)**:
    - 渲染循环非自动连续运行（非 Game Loop）。
    - 任何状态变化（相机移动、新消息到达、配置修改）必须调用 `queueAnimationFrame()` 触发下一帧渲染。
5.  **设置-视图双向同步 (Bidirectional Sync)**:
    - **View -> Settings**: 3D 交互（如 OrbitControls）变更状态时，立即更新 `config` 并触发 `updateSettingsTree()`。
    - **Settings -> View**: 设置面板修改 `config` 后，必须显式调用对应的 `setXxxState()`（如 `setCameraState`）以应用变更到 3D 场景。
    - **数值精度**: 涉及浮点数同步时，必须进行 `round` 处理（通常保留 3 位小数），防止无效的高精度数值导致的 UI 抖动或存储浪费。

### 5.6 Markers SceneExtension 完整实现（已完成）

#### 文件清单

```
extensions/
├── Markers.ts              — 主 SceneExtension，订阅 Marker & MarkerArray，管理设置树
├── TopicMarkers.ts         — 管理单 topic 下所有 namespace 的 marker 生命周期
└── markers/
    ├── materials.ts              — 统一材质工厂（Standard/Instanced/Line）
    ├── RenderableMarker.ts       — 所有 Marker 渲染类的基类（含颜色覆盖、过期逻辑）
    ├── MarkerPool.ts             — 按类型缓存 RenderableMarker 实例的对象池
    ├── RenderableArrow.ts        — ARROW (type=0) 箭头，支持 2点/scale 双模式
    ├── RenderableCube.ts         — CUBE (type=1)
    ├── RenderableSphere.ts       — SPHERE (type=2)
    ├── RenderableCylinder.ts     — CYLINDER (type=3)
    ├── RenderableLineStrip.ts    — LINE_STRIP (type=4)  THREE.Line
    ├── RenderableLineList.ts     — LINE_LIST (type=5)   THREE.LineSegments
    ├── RenderableCubeList.ts     — CUBE_LIST (type=6)   THREE.InstancedMesh
    ├── RenderableSphereList.ts   — SPHERE_LIST (type=7) THREE.InstancedMesh
    ├── RenderablePoints.ts       — POINTS (type=8)      THREE.Points
    ├── RenderableTextViewFacing.ts — TEXT_VIEW_FACING (type=9) CanvasTexture Sprite
    ├── RenderableTriangleList.ts — TRIANGLE_LIST (type=11) 动态 BufferGeometry
    └── RenderableMeshResource.ts — MESH_RESOURCE (type=10) ModelCache 异步加载
```

#### 关键设计决策

1. **材质简化**: 放弃 lichtblick 的 `LineMaterialWithAlphaVertex`（需 `@lichtblick/three-renderer`），改用标准 `THREE.LineBasicMaterial`。
2. **LayerSettingsMarker 定义位置**: 类型定义在 `RenderableMarker.ts` 中（不在 `TopicMarkers.ts`），防止循环导入。
3. **normalizeFrameId API**: 在 `IRenderer` 接口中新增 `normalizeFrameId(frameId: string): string` 方法；`Renderer.ts` 实现为：ROS 模式去掉前导 `/`，非 ROS 模式透传。
4. **对象池 MarkerPool**: 按 `MarkerType` 键缓存实例，避免 GPU 资源频繁 GC。
5. **注册点**: `composables/useRenderer.ts` 的 `createExtensionConfig()` 中显式注册。

#### 订阅的 ROS Schema

- `visualization_msgs/Marker` (及 ros2/foxglove 变体) → 单个 Marker
- `visualization_msgs/MarkerArray` (及变体) → 批量 Marker

#### 设置树结构

```
topics/
└── /your_marker_topic/
    ├── visible (boolean)
    ├── color (rgba override, 可选)
    ├── showOutlines (boolean)
    ├── selectedIdVariable (string)
    └── ns:namespace_name/
        └── visible (boolean)
```

---

## 6. 角色系统与路由配置 (Role System & Routing)

### 6.1 角色定义

系统支持三种角色，每种角色拥有独立的路由和菜单配置：

- **admin**: 超级管理员，拥有完整的管理菜单（容器管理、用户管理、权限管理等）
- **test**: 测试账号，拥有部分管理菜单
- **student**: 学生账号，仅访问学生专属工作台，不显示任何管理菜单

### 6.2 测试账号配置

**Mock 数据位置**: `edubot-twin-web/mock/user/index.mock.ts`

| 用户名  | 密码    | 角色    | roleId | 权限                                                 |
| ------- | ------- | ------- | ------ | ---------------------------------------------------- |
| admin   | admin   | admin   | 1      | `['*.*.*']`                                          |
| test    | test    | test    | 2      | `['example:dialog:create', 'example:dialog:delete']` |
| student | student | student | 3      | `[]`                                                 |

### 6.3 学生路由配置

**路由配置位置**: `edubot-twin-web/src/router/index.ts`

学生角色的路由独立配置在 `asyncRouterMap` 中：

```typescript
{
  path: '/student',
  component: Layout,
  redirect: '/student/home',
  name: 'Student',
  meta: {},
  children: [
    {
      path: 'home',
      component: () => import('@/views/Student/Home.vue'),
      name: 'StudentHome',
      meta: {
        title: '首页',
        icon: 'vi-carbon:home',
        noCache: true,
        affix: true
      }
    }
  ]
}
```

**关键特性**:

- 学生登录后，左侧菜单**只显示"首页"**菜单项
- 不继承 admin/test 的任何管理菜单
- Mock 角色配置中 `studentList` 为空数组

### 6.4 国际化配置

**配置位置**: `src/locales/zh-CN.ts` 和 `src/locales/en.ts`

```typescript
router: {
  // ...其他路由翻译
  studentHome: '首页',  // zh-CN
  studentHome: 'Home'  // en
}
```

---

## 7. 学生首页组件设计 (Student Home Component)

### 7.1 组件结构

学生首页采用卡片式布局，包含状态展示和操作入口：

**文件位置**: `edubot-twin-web/src/views/Student/Home.vue`

### 7.2 功能模块

#### 状态卡片区域

- **待完成考试卡片**: 显示待完成的考试数量，点击跳转到考试列表
- **未读消息卡片**: 显示未读消息数量，点击跳转到消息列表

#### 操作按钮区域

- **开始仿真按键**: 启动 ROS 仿真环境（待实现）
- **开始考试/测试按键**: 进入考试/测试模式（待实现）

### 7.3 技术实现

**API 接口**:

```typescript
// src/api/student/index.ts
export const getStudentHomeDataApi = (): Promise<IResponse<StudentHomeData>>

// src/api/student/types.ts
export interface StudentHomeData {
  pendingExams: number
  unreadMessages: number
}
```

**Mock 数据**: `mock/student/index.mock.ts`

```typescript
{
  url: '/mock/student/home',
  response: () => ({
    code: SUCCESS_CODE,
    data: {
      pendingExams: 3,
      unreadMessages: 5
    }
  })
}
```

**组件特性**:

- **骨架屏加载**: 使用 `ElSkeleton` 组件，`loading` 状态控制
- **图标系统**: Carbon 图标集（`vi-carbon:task`, `vi-carbon:email`）
- **悬停动画**: 参考 `PanelGroup.vue`，图标背景色变化 + 卡片上浮
- **响应式数据**: 使用 `ref` 响应式变量，`onMounted` 时异步获取数据

**交互注意事项**:

- `ElCard` 组件不直接支持 `@click` 事件
- 点击事件应绑定在内部的 `div` 容器上
- 所有业务逻辑点击事件都添加 TODO 标记

### 7.4 样式设计

- **布局**: 响应式 `ElRow` + `ElCol`（移动端单列，桌面端双列）
- **CSS 策略**: Less + UnoCSS 原子类混用
- **颜色方案**:
  - 待完成考试卡片: `#f4516c`（红色）
  - 未读消息卡片: `#36a3f7`（蓝色）

---

## 7. 路由与权限管理核心共识 (Routing & Permission Core Consensus)

### 7.1 双重配置原则 (Dual Configuration Principle)

**问题背景**: vue-element-plus-admin 支持静态路由和动态路由两种模式。动态路由模式下，后端（或 Mock）返回的路由数据决定用户可访问的页面。

**核心规则**: **每个角色的路由必须在两处配置**：

1. **`src/router/index.ts`** 的 `asyncRouterMap` 中定义完整路由结构（用于静态模式）
2. **`mock/role/index.mock.ts`** 中对应角色的路由列表（用于动态模式）

**常见错误**:

```typescript
// ❌ 错误：只在 asyncRouterMap 中定义了 /student/home
// 但 mock 中 studentList = []，导致学生用户无法访问任何路由
const studentList = [];
```

**正确做法**:

```typescript
// ✅ 正确：在 mock 中也必须配置
const studentList = [
  {
    path: "/student",
    component: "#", // '#' 表示 Layout 组件
    redirect: "/student/home",
    name: "Student",
    children: [
      {
        path: "home",
        component: "views/Student/Home", // mock 中使用字符串路径
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

### 7.2 动态首页重定向 (Dynamic Homepage Redirect)

**问题背景**: 根路径 `/` 如果硬编码 `redirect: '/dashboard/analysis'`，会导致学生等无权限用户访问 404。

**解决方案**:

1. **移除硬编码**：在 `src/router/index.ts` 中，根路径不设置 `redirect`
2. **权限守卫处理**：在 `src/permission.ts` 中，根据用户的第一个可访问路由动态跳转

```typescript
// src/permission.ts 核心逻辑
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

### 7.3 常见问题诊断清单 (Troubleshooting Checklist)

| 症状                                          | 原因                                                     | 解决方法                                                 |
| --------------------------------------------- | -------------------------------------------------------- | -------------------------------------------------------- |
| 登录后访问 `/` 显示 404                       | 根路径 redirect 到用户无权访问的路由                     | 移除硬编码 redirect，在 `permission.ts` 中动态处理       |
| 直接访问 `/student/home` 正常，但菜单中看不到 | `meta.hidden: true` 或路由未在 mock 数据中返回           | 检查 `mock/role/index.mock.ts` 中对应角色的路由列表      |
| 可以访问路由，但地址栏显示 `/dashboard`       | 动态路由未在 mock 中配置                                 | 在 `mock/role/index.mock.ts` 的 `studentList` 中添加路由 |
| 切换角色后路由混乱                            | 未调用 `permissionStore.setIsAddRouters(false)` 重置状态 | 登出时清空路由状态和 localStorage                        |

### 7.4 路由元信息关键配置 (Route Meta Configuration)

```typescript
meta: {
  hidden: true,       // 隐藏菜单项（但路由仍可访问，需配合 canTo: true）
  alwaysShow: true,   // 只有一个子路由时也显示父级菜单
  affix: true,        // 固定在标签页，不可关闭（如学生首页）
  noCache: true,      // 不缓存该页面（适用于实时数据页面）
  noTagsView: true,   // 不在标签页中显示
  activeMenu: '/xxx', // 激活指定菜单高亮（用于隐藏路由）
  canTo: true,        // hidden 时仍允许路由跳转
}
```

### 7.5 学生角色路由最佳实践 (Student Role Best Practice)

- **独立路由**：学生路由完全独立，不继承管理菜单
- **Mock 配置**：`studentList` 只包含学生可访问的路由（如 `/student/home`）
- **菜单隔离**：学生登录后左侧菜单只显示学生专属菜单项
- **首页固定**：学生首页使用 `affix: true`，确保标签页始终存在

---

## 8. 后端 API 架构设计 (Backend API Architecture)

### 8.1 架构模式

采用**模块化分层架构**,按角色和功能模块组织 API 端点。

### 8.2 目录结构

```
app/api/v1/endpoints/
├── student/                    # 学生模块
│   ├── __init__.py            # 路由聚合器
│   ├── basic.py               # ✅ 基本 CRUD
│   ├── auth.py                # 🔜 登录、注册
│   ├── exams.py               # 🔜 考试相关
│   ├── containers.py          # 🔜 容器操作
│   ├── learning.py            # 🔜 学习记录
│   └── homework.py            # 🔜 作业提交
├── teacher/                    # 教师模块
│   ├── __init__.py            # ✅ 路由聚合器
│   ├── basic.py               # 🔜 基本 CRUD
│   ├── auth.py                # 🔜 登录
│   ├── exams.py               # 🔜 考试管理
│   ├── containers.py          # 🔜 容器集群管理
│   ├── students.py            # 🔜 学生管理
│   └── resources.py           # 🔜 资源分发
└── common/                     # 公共模块
    └── __init__.py            # ✅ 健康检查等
```

### 8.3 核心原则

1. **低耦合**: 每个模块独立维护,互不影响
2. **高内聚**: 相关功能聚合在同一模块
3. **易扩展**: 添加新功能只需创建新文件并注册路由
4. **易维护**: 单个文件代码量可控 (建议不超过 200 行)

### 8.4 数据库设计

#### 学生表 (students)

| 字段名        | 类型        | 约束                   | 说明              |
| ------------- | ----------- | ---------------------- | ----------------- |
| id            | Integer     | PRIMARY KEY            | 主键 (自增)       |
| username      | String(50)  | UNIQUE, NOT NULL       | 学号/用户名       |
| password_hash | String(255) | NOT NULL               | 密码哈希 (bcrypt) |
| real_name     | String(50)  | NULL                   | 真实姓名          |
| email         | String(100) | UNIQUE, NULL           | 邮箱              |
| is_active     | Boolean     | NOT NULL, DEFAULT TRUE | 账号激活状态      |
| created_at    | DateTime    | NOT NULL               | 创建时间          |
| updated_at    | DateTime    | NOT NULL               | 更新时间          |

### 8.5 API 端点规范

#### 已实现端点

- `GET /api/v1/students` - 获取学生列表 (分页)
- `GET /api/v1/students/{id}` - 获取单个学生
- `POST /api/v1/students` - 创建学生
- `PUT /api/v1/students/{id}` - 更新学生
- `DELETE /api/v1/students/{id}` - 删除学生
- `GET /api/v1/health` - 健康检查

#### 未来扩展路径

- `POST /api/v1/students/auth/login` - 学生登录
- `GET /api/v1/students/exams` - 学生考试列表
- `POST /api/v1/students/containers/start` - 启动容器
- `GET /api/v1/students/learning/stats` - 学习统计
- `POST /api/v1/students/homework/submit` - 提交作业

### 8.6 技术栈选择

- **FastAPI 0.115.0**: 高性能异步 Web 框架
- **SQLAlchemy 2.0+**: 异步 ORM
- **SQLite/PostgreSQL**: 数据库
- **Pydantic V2**: 数据验证
- **bcrypt**: 密码加密
- **Uvicorn**: ASGI 服务器

### 8.7 安全特性

- ✅ 密码使用 bcrypt 哈希存储
- ✅ API 响应自动过滤 `password_hash` 字段
- ✅ Pydantic 自动验证输入数据
- ✅ CORS 配置限制前端跨域访问

### 8.8 扩展指南

添加新功能步骤:

1. 创建新文件 `student/exams.py`
2. 在 `student/__init__.py` 中注册路由
3. 完成! API 自动可用

详细架构文档: `edubot-twin-server/API_ARCHITECTURE.md`
