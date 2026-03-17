---
description: "# 仿真页面 - 添加新面板指南 (Refactored)  本规则描述如何在仿真工作台（`src/views/Simulation`）中添加新的面板类型。 系统基于 **Golden Layout v2.6.0** 和 **Element Plus**，采用了仿 lichtblick 的**设置树（Settings Tree）**架构。"
---

# 仿真页面 - 添加新面板指南 (Refactored)

本规则描述如何在仿真工作台（`src/views/Simulation`）中添加新的面板类型。
系统基于 **Golden Layout v2.6.0** 和 **Element Plus**，采用了仿 lichtblick 的**设置树（Settings Tree）**架构。

## 目录结构

```text
src/views/Simulation/
├── Simulation.vue                    # 主页面（包含 SettingsSidebar + GLayout）
├── components/
│   ├── GLayout.vue                   # GL 容器，负责渲染布局
│   ├── PanelSettings.vue             # 通用设置表单渲染器
│   ├── SettingsSidebar.vue           # ★ 设置侧栏容器（包裹 PanelSettings）
│   └── SimulationHeader.vue          # 顶部工具栏
├── panels/                           # ★ 面板定义目录
│   ├── registry.ts                   # 面板注册表
│   ├── ROS3DViewer/                  # 具体面板
│   │   ├── index.vue                 # 面板组件
│   │   └── settings.ts               # 设置配置（defaultConfig + buildSettingsTree）
│   └── ...
├── stores/
│   └── panelState.ts                 # 面板状态管理（通过 import 共享）
└── types/
    └── settings.ts                   # 设置树类型定义
```

## 添加新面板 — 完整流程

### 1. 创建面板目录

在 `src/views/Simulation/panels/` 下创建新目录（例如 `Terminal`），并创建 `index.vue` 和 `settings.ts`。

#### A. 定义设置 (`settings.ts`)

```typescript
import type {
  SettingsTreeNodes,
  SettingsTreeAction,
} from "../../types/settings";

// 1. 定义配置接口和默认值
export interface TerminalConfig {
  fontSize: number;
  theme: "dark" | "light";
}

export const defaultConfig: TerminalConfig = {
  fontSize: 14,
  theme: "dark",
};

// 2. 构建设置树（UI 描述）
export function buildSettingsTree(config: TerminalConfig): SettingsTreeNodes {
  return {
    appearance: {
      label: "外观设置",
      fields: {
        fontSize: {
          label: "字体大小",
          input: "number",
          value: config.fontSize,
          min: 10,
          max: 24,
        },
        theme: {
          label: "主题",
          // ... options
        },
      },
    },
  };
}

// 3. 创建 Action Handler (处理变更)
export function createActionHandler(
  config: TerminalConfig,
  saveConfig: (newConfig: TerminalConfig) => void,
) {
  return (action: SettingsTreeAction) => {
    if (action.action !== "update") return;
    const { path, value } = action.payload;
    const fieldKey = path[1] as keyof TerminalConfig;
    saveConfig({ ...config, [fieldKey]: value });
  };
}
```

#### B. 创建组件 (`index.vue`)

- 必须接收 `panelId` prop。
- 使用 `usePanelState` 注册面板和设置树。

```vue
<script setup lang="ts">
import { ref, onMounted, onBeforeUnmount, watch } from "vue";
import { usePanelState } from "../../stores/panelState";
import {
  defaultConfig,
  buildSettingsTree,
  createActionHandler,
  type TerminalConfig,
} from "./settings";

const props = defineProps<{ panelId: string }>();

// 状态集成
const { registerPanel, unregisterPanel, updateSettingsTree } = usePanelState();
const config = ref<TerminalConfig>({ ...defaultConfig });

// 保存配置并刷新设置树
function saveConfig(newConfig: TerminalConfig) {
  config.value = newConfig;
  refreshSettingsTree();
}

function refreshSettingsTree() {
  updateSettingsTree(props.panelId, {
    actionHandler: createActionHandler(config.value, saveConfig),
    nodes: buildSettingsTree(config.value),
  });
}

// 生命周期
onMounted(() => {
  registerPanel(props.panelId, "Terminal"); // 注册面板
  refreshSettingsTree(); // 初始注册设置
});

onBeforeUnmount(() => {
  unregisterPanel(props.panelId);
});

watch(config, refreshSettingsTree, { deep: true });
</script>
```

### 2. 注册面板

打开 `src/views/Simulation/panels/registry.ts`：

1.  导入组件
2.  添加到 `panelRegistry`

```typescript
import Terminal from "./Terminal/index.vue";

export const panelRegistry: Record<string, PanelRegistryEntry> = {
  // ...
  Terminal: {
    component: markRaw(Terminal),
    label: "终端",
  },
};
```

### 3. (可选) 添加到预设布局

如果需要在默认布局中显示，修改 `src/views/Simulation/config/predefined-layouts.ts`。

---

## 架构说明

- **设置树模式**: 每个面板完全控制自己的设置 UI（通过 `buildSettingsTree`），逻辑与渲染分离。
- **SettingsSidebar**:
  - 左侧可折叠的侧栏，不通过 Golden Layout 管理。
  - 内部渲染通用组件 `PanelSettings`，根据各面板提供的 JSON 描述生成表单。
- **GLayout**:
  - 在每个 Stack Header 注入 ⚙ 齿轮按钮。
  - 点击齿轮 → `emit('settings-toggle', panelId)` → 父组件 `Simulation.vue` 控制 `panelState.selectPanel()`。
  - `Simulation.vue` 根据选中状态显示/隐藏 `SettingsSidebar`，并自动调整布局区域宽度（GL 自动 Resize）。
