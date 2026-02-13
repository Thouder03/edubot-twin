# 重构总结：仿真架构

**日期**: 2026-02-12
**目标**: 重构仿真页面架构，将设置面板（Settings Panel）重构为基于配置树（Settings Tree）的通用系统，并采用左侧侧栏（Sidebar）布局。

## 1. 目录结构变更

将 `src/views/Student/Simulation` 移动至 `src/views/Simulation` 作为一个顶级视图。

```text
src/views/Simulation/
├── Simulation.vue              # 主入口 (SettingsSidebar + GLayout)
├── components/
│   ├── GLayout.vue             # Golden Layout 容器与管理器
│   ├── SettingsSidebar.vue     # [新增] 设置侧栏容器
│   ├── PanelSettings.vue       # [新增] 通用设置表单渲染器
│   └── SimulationHeader.vue    # 工具栏
├── panels/                     # [新增] 面板定义
│   ├── registry.ts             # 面板注册表
│   ├── ROS3DViewer/            # 面板：ROS3DViewer
│   │   ├── index.vue
│   │   └── settings.ts         # 设置定义
│   └── ...
├── stores/                     # [新增] 本地状态
│   └── panelState.ts           # 面板选择与设置状态
├── types/                      # [新增] 类型定义
│   └── settings.ts             # 设置树接口
└── config/
    └── predefined-layouts.ts   # 布局预设
```

## 2. 关键架构变更

### A. 设置侧栏 (Settings Sidebar)

- **架构**: 采用 Flex 布局（左 Sidebar + 右 GLayout），而非将设置面板作为 GL 内部组件。
- **行为**: 点击 GL 面板标题栏上的设置齿轮 ⚙，触发 `settings-toggle` 事件。
- **响应**: 主页面 `Simulation.vue` 接收事件，通过 `panelState` 选中目标面板，侧栏滑出显示配置。
- **自适应**: 侧栏开关或拖拽调整宽度时，右侧 GLayout 自动响应尺寸变化。

### B. 设置树模式 (Lichtblick Style)

- **解耦**: 设置 UI 与通用渲染器解耦。
- **定义**: 每个面板定义自己的 `settings.ts`，导出：
  - `defaultConfig`: 初始状态。
  - `buildSettingsTree(config)`: 返回设置 UI 的 JSON 描述（分组、字段、类型）。
  - `createActionHandler(config, save)`: 处理字段更新。
- **渲染**: `PanelSettings.vue` 从 `panelState` 读取树结构，并渲染 Element Plus 表单项。

### C. 面板状态管理

- `stores/panelState.ts` (基于 Composition API 的作用域模块) 管理：
  - `panels`: 已注册的面板实例。
  - `selectedPanelId`: 当前正在编辑的面板 ID。
  - `settingsTrees`: 面板 ID 到设置树的映射。
- 面板通过此共享状态进行通信，无需复杂的属性传递（prop drilling）。

## 3. 收益

1.  **可扩展性**: 添加带有设置的新面板不再需要修改中心化的 `SettingsPanel.vue`。
2.  **交互优化**: 侧栏模式不干扰 GL 布局结构，且支持拖拽调整宽度，体验更流畅。
3.  **可维护性**: 关注点分离清晰。面板逻辑和配置能力放置在同一位置。

## 4. 下一步计划

- 将实际的 `ros3djs` 逻辑集成到 `ROS3DViewer` 中。
- 实现 `GzWeb` iframe 集成。
- 使用新模式添加更多面板类型（终端、代码编辑器）。
