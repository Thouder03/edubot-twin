<script setup lang="ts">
/**
 * ROS 3D 视图面板 - 真实 Three.js 3D 渲染
 *
 * 核心功能:
 * 1. Three.js 3D 场景渲染（网格/坐标轴/相机控制）
 * 2. ROS WebSocket 连接管理
 * 3. TF 坐标帧订阅（连接后自动激活）
 * 4. 设置树集成（侧栏实时控制）
 */
import { ref, computed, toRef, onMounted, onBeforeUnmount, watch, nextTick } from 'vue'
import { Icon } from '@/components/Icon'
import { usePanelState } from '../../stores/panelState'
import {
  defaultConfig,
  buildSettingsTree,
  createActionHandler,
  type ROS3DViewerConfig
} from './settings'
import { useThreeScene } from './composables/useThreeScene'
import { useRosConnection } from './composables/useRosConnection'
import { useTfManager } from './composables/useTfManager'
import { useDisplayManager } from './composables/useDisplayManager'

// ---------- Props ----------
interface Props {
  panelId: string
}

const props = defineProps<Props>()

// ---------- 面板设置集成 ----------
const { registerPanel, unregisterPanel, updateSettingsTree } = usePanelState()
const config = ref<ROS3DViewerConfig>({ ...defaultConfig })

// ---------- Composables ----------

// 响应式配置引用（传入 composable）
const showGrid = computed(() => config.value.showGrid)
const showAxes = computed(() => config.value.showAxes)
const backgroundColor = computed(() => config.value.backgroundColor)
const gridSize = computed(() => config.value.gridSize)
const gridDivisions = computed(() => config.value.gridDivisions)
const rosUrl = computed(() => config.value.rosUrl)

const {
  scene,
  sceneReady,
  mount: mountScene,
  dispose: disposeScene
} = useThreeScene({
  showGrid: showGrid,
  showAxes: showAxes,
  backgroundColor: backgroundColor,
  gridSize: gridSize,
  gridDivisions: gridDivisions
})

const { status, errorMessage, getRos, connect, disconnect } = useRosConnection(rosUrl)

const tfManager = useTfManager(getRos, status, scene)
const displayManager = useDisplayManager(getRos, status, scene)

// ---------- 模板引用 ----------
const canvasContainer = ref<HTMLElement>()

// ---------- 连接状态显示 ----------
const statusConfig = computed(() => {
  switch (status.value) {
    case 'connected':
      return { color: '#a6e3a1', label: '已连接', icon: 'vi-carbon:checkmark-filled' }
    case 'connecting':
      return { color: '#f9e2af', label: '连接中...', icon: 'vi-carbon:in-progress' }
    case 'error':
      return {
        color: '#f38ba8',
        label: `错误: ${errorMessage.value || '连接失败'}`,
        icon: 'vi-carbon:warning-alt-filled'
      }
    default:
      return { color: '#6c7086', label: '未连接', icon: 'vi-carbon:subtract' }
  }
})

// ---------- 连接/断开按钮 ----------
function handleConnectionToggle() {
  if (status.value === 'connected' || status.value === 'connecting') {
    disconnect()
    tfManager.unsubscribe()
  } else {
    connect()
  }
}

// 连接成功后自动订阅 TF
watch(status, (newStatus) => {
  if (newStatus === 'connected') {
    tfManager.subscribe()
  } else if (newStatus === 'disconnected' || newStatus === 'error') {
    tfManager.unsubscribe()
  }
})

// ---------- 设置树 ----------
function saveConfig(newConfig: ROS3DViewerConfig) {
  config.value = newConfig
  refreshSettingsTree()
}

function refreshSettingsTree() {
  updateSettingsTree(props.panelId, {
    actionHandler: createActionHandler(config.value, saveConfig),
    nodes: buildSettingsTree(config.value, tfManager.availableFrames.value)
  })
}

// ---------- 生命周期 ----------
onMounted(() => {
  registerPanel(props.panelId, 'ROS3DViewer')
  refreshSettingsTree()

  // 挂载 Three.js 场景
  nextTick(() => {
    if (canvasContainer.value) {
      mountScene(canvasContainer.value)
    }
  })

  // 自动连接
  if (config.value.autoConnect) {
    connect()
  }
})

onBeforeUnmount(() => {
  displayManager.dispose()
  tfManager.dispose()
  disconnect()
  disposeScene()
  unregisterPanel(props.panelId)
})

// TF 帧列表变化时更新设置树
watch(() => tfManager.availableFrames.value, refreshSettingsTree, { deep: true })

// 配置变更时更新设置树
watch(config, refreshSettingsTree, { deep: true })
</script>

<template>
  <div class="ros3d-viewer">
    <!-- Three.js 渲染容器 -->
    <div ref="canvasContainer" class="ros3d-canvas-container"></div>
    <!-- HUD 覆盖层 - 连接状态 -->
    <div class="ros3d-hud">
      <div
        class="hud-status"
        @click="handleConnectionToggle"
        :title="status === 'connected' ? '点击断开' : '点击连接'"
      >
        <span class="status-dot" :style="{ backgroundColor: statusConfig.color }"></span>
        <Icon :icon="statusConfig.icon" :size="12" :style="{ color: statusConfig.color }" />
        <span class="status-text" :style="{ color: statusConfig.color }">
          {{ statusConfig.label }}
        </span>
      </div>
    </div>
    <!-- 加载状态 -->
    <div v-if="!sceneReady" class="ros3d-loading">
      <Icon icon="vi-carbon:cube" :size="36" class="loading-icon" />
      <span>初始化 3D 场景...</span>
    </div>
  </div>
</template>

<style lang="less" scoped>
.ros3d-viewer {
  width: 100%;
  height: 100%;
  position: relative;
  overflow: hidden;
  background: #1e1e2e;
}

.ros3d-canvas-container {
  width: 100%;
  height: 100%;
  position: absolute;
  top: 0;
  left: 0;
}

// ---------- HUD 覆盖层 ----------
.ros3d-hud {
  position: absolute;
  top: 8px;
  left: 8px;
  z-index: 10;
  pointer-events: auto;
}

.hud-status {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 4px 10px;
  background: rgba(17, 17, 27, 0.85);
  backdrop-filter: blur(8px);
  border-radius: 6px;
  border: 1px solid rgba(69, 71, 90, 0.5);
  cursor: pointer;
  transition: all 200ms ease;
  user-select: none;
  &:hover {
    background: rgba(30, 30, 46, 0.95);
    border-color: rgba(137, 180, 250, 0.3);
  }
}

.status-dot {
  width: 6px;
  height: 6px;
  border-radius: 50%;
  flex-shrink: 0;
}

.status-text {
  font-size: 11px;
  font-family: 'Consolas', 'Monaco', monospace;
  white-space: nowrap;
}

// ---------- 加载状态 ----------
.ros3d-loading {
  position: absolute;
  top: 0;
  left: 0;
  width: 100%;
  height: 100%;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  background: #1e1e2e;
  color: #6c7086;
  gap: 12px;
  z-index: 5;
  .loading-icon {
    color: #89b4fa;
    animation: pulse 1.5s ease-in-out infinite;
  }

  span {
    font-size: 13px;
  }
}

@keyframes pulse {
  0%,
  100% {
    opacity: 0.4;
  }
  50% {
    opacity: 1;
  }
}
</style>
