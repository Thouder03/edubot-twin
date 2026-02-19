<script setup lang="ts">
/**
 * ROS 3D 视图面板 — 基于 Lichtblick Renderer-Extension 架构
 *
 * 核心功能:
 * 1. Renderer 驱动的 Three.js 3D 场景渲染
 * 2. ROS WebSocket 连接管理
 * 3. TF / 消息自动路由到 SceneExtension 体系
 * 4. 设置树集成（侧栏实时控制）
 */
import { ref, computed, onMounted, onBeforeUnmount, watch, nextTick } from 'vue'
import { useI18n } from 'vue-i18n'
import { Icon } from '@/components/Icon'
import { Topic as RosTopic } from 'roslib'
import { usePanelState } from '../../stores/panelState'
import { useRenderer } from './composables/useRenderer'
import { useRosConnection } from './composables/useRosConnection'

// ---------- Props ----------
interface Props {
  panelId: string
}

const props = defineProps<Props>()

const { t } = useI18n()

// ---------- 面板设置集成 ----------
const { registerPanel, unregisterPanel, updateSettingsTree } = usePanelState()

// ---------- ROS 连接配置（从 RendererConfig.connection 读取，统一持久化）----------
// 等价于 lichtblick 的 context.initialState 恢复逻辑
const rosUrl = computed(() => renderer.value?.config.connection?.rosUrl ?? 'ws://localhost:9090')
const autoConnect = computed(() => renderer.value?.config.connection?.autoConnect ?? false)

// ---------- Composables ----------
const {
  sceneReady,
  settingsTreeVersion,
  mount: mountRenderer,
  dispose: disposeRenderer,
  handleSettingsAction,
  getSettingsTree,
  addMessageEvent,
  renderer
} = useRenderer()

const { status, errorMessage, getRos, connect, disconnect } = useRosConnection(rosUrl)

// 监听 configChange：当 rosUrl 变化时更新连接 URL
// （RendererConfig 的持久化已由 useRenderer 的 debouncedSave 处理）
watch(
  () => renderer.value?.config.connection?.rosUrl,
  (newUrl) => {
    if (newUrl) {
      // useRosConnection 内部 watch rosUrl，自动响应
    }
  }
)

// ---------- 模板引用 ----------
const canvasContainer = ref<HTMLElement>()

// ---------- ROS TF 订阅桥接 ----------
let tfSubscriptions: RosTopic[] = []

function subscribeTfTopics() {
  unsubscribeTfTopics()

  const ros = getRos()
  if (!ros || !renderer.value) return

  const tfTopics = [
    { name: '/tf', type: 'tf2_msgs/TFMessage' },
    { name: '/tf_static', type: 'tf2_msgs/TFMessage' }
  ]

  // 通知 Renderer 可用的 topics
  renderer.value.setTopics(
    tfTopics.map((t) => ({
      name: t.name,
      schemaName: t.type,
      datatype: t.type
    }))
  )

  for (const topicDef of tfTopics) {
    const rosTopic = new RosTopic({
      ros,
      name: topicDef.name,
      messageType: topicDef.type
    })

    rosTopic.subscribe((msg: any) => {
      const now = BigInt(Date.now()) * 1_000_000n // ms → ns
      addMessageEvent({
        topic: topicDef.name,
        schemaName: topicDef.type,
        receiveTime: { sec: Number(now / 1_000_000_000n), nsec: Number(now % 1_000_000_000n) },
        message: msg,
        sizeInBytes: 0
      })
    })

    tfSubscriptions.push(rosTopic)
  }

  console.log('[ROS3D] TF 订阅已启动:', tfTopics.map((t) => t.name).join(', '))
}

function unsubscribeTfTopics() {
  // 仅在连接状态正常时尝试取消订阅
  const ros = getRos()
  const isConnected = ros && ros.isConnected

  for (const sub of tfSubscriptions) {
    try {
      if (isConnected) {
        sub.unsubscribe()
      } else {
        // 如果已断开，直接销毁订阅对象（清理本地监听器），不再向后端发送取消订阅请求
        sub.removeAllListeners()
      }
    } catch (e) {
      console.warn('[ROS3D] Error unsubscribing:', e)
    }
  }
  tfSubscriptions = []
}

// 监听连接状态变化 → 自动订阅/取消 TF
watch(status, (newStatus) => {
  if (newStatus === 'connected') {
    subscribeTfTopics()
  } else {
    unsubscribeTfTopics()
  }
})

// ---------- 连接状态显示 ----------
const statusConfig = computed(() => {
  switch (status.value) {
    case 'connected':
      return {
        color: '#a6e3a1',
        label: t('threeDee.connected'),
        icon: 'vi-carbon:checkmark-filled'
      }
    case 'connecting':
      return { color: '#f9e2af', label: t('threeDee.connecting'), icon: 'vi-carbon:in-progress' }
    case 'error':
      return {
        color: '#f38ba8',
        label: `${t('threeDee.error')}: ${errorMessage.value || t('threeDee.disconnected')}`,
        icon: 'vi-carbon:warning-alt-filled'
      }
    default:
      return { color: '#6c7086', label: t('threeDee.disconnected'), icon: 'vi-carbon:subtract' }
  }
})

// ---------- 连接/断开按钮 ----------
function handleConnectionToggle() {
  if (status.value === 'connected' || status.value === 'connecting') {
    disconnect()
  } else {
    connect()
  }
}

// ---------- 设置树同步 ----------
function refreshSettingsTree() {
  const tree = getSettingsTree()
  if (tree) {
    updateSettingsTree(props.panelId, {
      actionHandler: (action) => handleSettingsAction(action),
      nodes: tree
    })
  }
}

// settingsTree 版本变化时同步到面板设置系统
watch(settingsTreeVersion, refreshSettingsTree)

// ---------- 生命周期 ----------
onMounted(() => {
  registerPanel(props.panelId, 'ROS3DViewer')

  // 挂载 Renderer + Three.js
  nextTick(() => {
    if (canvasContainer.value) {
      mountRenderer(canvasContainer.value)
      // 首次生成设置树
      refreshSettingsTree()
    }
  })

  // 自动连接
  if (autoConnect.value) {
    connect()
  }
})

onBeforeUnmount(() => {
  unsubscribeTfTopics()
  disconnect()
  disposeRenderer()
  unregisterPanel(props.panelId)
})
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
        :title="
          status === 'connected' ? t('threeDee.clickToDisconnect') : t('threeDee.clickToConnect')
        "
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
      <span>{{ t('threeDee.initializing') }}</span>
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
