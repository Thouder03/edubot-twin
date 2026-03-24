<script setup lang="ts">
/**
 * GzWebViewer - Gazebo 仿真面板
 *
 * 不再自己创建 iframe 和管理通信。
 * 通过 useGzBridge 的 attachToContainer/detachFromContainer
 * 将页面级已创建的 iframe 移入/移出本面板的 DOM 容器。
 *
 * - 面板挂载时：从 API 获取分配的容器信息 → 更新 gzbridge URL → 将 iframe 移入容器
 * - 面板卸载时：将 iframe 移回 body（隐藏）→ 通信不中断
 *
 * 配置变更（showGrid / showCollisions / showOrbitIndicator）自动同步到 iframe。
 */
import { ref, onMounted, onBeforeUnmount, watch } from 'vue'
import { usePanelState } from '../../stores/panelState'
import { useGzBridge } from '../../composables/useGzBridge'
import { getMyContainerApi } from '@/api/container'
import {
  defaultConfig,
  buildSettingsTree,
  createActionHandler,
  type GzWebViewerConfig
} from './settings'

// ---------- Props ----------
interface Props {
  panelId: string
}

const props = defineProps<Props>()

// ---------- GzBridge 集成 ----------
const {
  connectionStatus,
  attachToContainer,
  detachFromContainer,
  showGrid,
  showCollisions,
  showOrbitIndicator,
  updateGzwebUrl
} = useGzBridge()

// ---------- 面板设置集成 ----------
const { registerPanel, unregisterPanel, updateSettingsTree } = usePanelState()
const config = ref<GzWebViewerConfig>({ ...defaultConfig })

// ---------- iframe 容器 ----------
const iframeContainer = ref<HTMLElement | null>(null)

// ---------- 设置面板同步 ----------
function saveConfig(newConfig: GzWebViewerConfig) {
  const oldConfig = config.value
  config.value = newConfig

  // 将显示设置变更同步到 iframe
  if (newConfig.showGrid !== oldConfig.showGrid) {
    showGrid(newConfig.showGrid)
  }
  if (newConfig.showCollisions !== oldConfig.showCollisions) {
    showCollisions(newConfig.showCollisions)
  }
  if (newConfig.showOrbitIndicator !== oldConfig.showOrbitIndicator) {
    showOrbitIndicator(newConfig.showOrbitIndicator)
  }
  // gzwebUrl 变更时，通知 bridge 更新 iframe src
  if (newConfig.gzwebUrl !== oldConfig.gzwebUrl) {
    updateGzwebUrl(newConfig.gzwebUrl)
  }

  refreshSettingsTree()
}

function refreshSettingsTree() {
  updateSettingsTree(props.panelId, {
    actionHandler: createActionHandler(config.value, saveConfig),
    nodes: buildSettingsTree(config.value)
  })
}

/**
 * 从容器 API 获取分配的 gzbridge URL，并更新 useGzBridge 的连接。
 *
 * 若 API 成功且返回 gzbridge_url：
 *   - 优先使用 API 返回地址（覆盖 settings 中的手动 URL）
 * 若 API 失败或无容器：
 *   - Fallback：沿用 settings 中配置的手动 gzwebUrl（不报错，仅控制台警告）
 *
 * TODO: studentId 临时硬编码为 1，后续从 JWT userStore 读取
 */
async function fetchAndApplyContainerUrl() {
  try {
    const TEMP_STUDENT_ID = 1 // TODO: 从 userStore.userInfo.id 读取
    const res = await getMyContainerApi(TEMP_STUDENT_ID)
    const gzUrl = res?.data?.gzbridge_url
    if (gzUrl) {
      console.info('[GzWebViewer] 从 API 获取 gzbridge URL:', gzUrl)
      // 同步到 config（让 settings 面板显示实际地址）
      config.value = { ...config.value, gzwebUrl: gzUrl }
      updateGzwebUrl(gzUrl)
      refreshSettingsTree()
    } else {
      console.warn('[GzWebViewer] API 未返回 gzbridge_url，使用手动配置:', config.value.gzwebUrl)
    }
  } catch (err) {
    console.warn('[GzWebViewer] 获取容器信息失败，使用手动配置:', err)
  }
}

// ---------- 生命周期 ----------
onMounted(async () => {
  registerPanel(props.panelId, 'GzWebViewer')
  refreshSettingsTree()

  // 先从 API 获取动态 URL（非阻塞，失败时 fallback 到手动配置）
  await fetchAndApplyContainerUrl()

  // 将 useGzBridge 管理的 iframe 移入本面板容器
  if (iframeContainer.value) {
    attachToContainer(iframeContainer.value)
  }
})

onBeforeUnmount(() => {
  // 将 iframe 移回 body（隐藏），通信不中断
  detachFromContainer()
  unregisterPanel(props.panelId)
})

// 监听 config 变更 → 更新设置树
watch(config, refreshSettingsTree, { deep: true })
</script>

<template>
  <div class="gzweb-viewer">
    <!-- iframe 容器：iframe 通过 attachToContainer 移入此 div -->
    <div ref="iframeContainer" class="gzweb-iframe-container"></div>
    <!-- 连接中遮罩层 -->
    <div v-if="connectionStatus !== 'connected'" class="gzweb-overlay">
      <div class="overlay-content">
        <div class="overlay-dot" :class="connectionStatus"></div>
        <span class="overlay-text">
          {{
            connectionStatus === 'connecting'
              ? '正在连接 Gazebo...'
              : connectionStatus === 'error'
                ? '连接失败'
                : '等待连接'
          }}
        </span>
      </div>
    </div>
  </div>
</template>

<style lang="less" scoped>
.gzweb-viewer {
  width: 100%;
  height: 100%;
  position: relative;
  background: #1e1e2e;
}

.gzweb-iframe-container {
  width: 100%;
  height: 100%;
}

// ── 连接中遮罩 ──
.gzweb-overlay {
  position: absolute;
  inset: 0;
  display: flex;
  align-items: center;
  justify-content: center;
  background: rgba(30, 30, 46, 0.85);
  z-index: 10;
}

.overlay-content {
  display: flex;
  align-items: center;
  gap: 10px;
}

.overlay-dot {
  width: 10px;
  height: 10px;
  border-radius: 50%;

  &.disconnected {
    background: #6c7086;
  }

  &.connecting {
    background: #f9e2af;
    animation: pulse 1.5s infinite;
  }

  &.error {
    background: #f38ba8;
  }
}

.overlay-text {
  color: #cdd6f4;
  font-size: 14px;
}

@keyframes pulse {
  0%,
  100% {
    opacity: 1;
  }
  50% {
    opacity: 0.4;
  }
}
</style>
