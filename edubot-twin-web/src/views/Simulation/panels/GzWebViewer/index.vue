<script setup lang="ts">
/**
 * GzWebViewer - Gazebo 仿真面板
 *
 * 通过 iframe 嵌入 gzweb embed.html，使用 postMessage 双向通信。
 * 配置变更（showGrid / showCollisions / showOrbitIndicator）自动同步到 iframe。
 */
import { ref, computed, onMounted, onBeforeUnmount, watch } from 'vue'
import { usePanelState } from '../../stores/panelState'
import { useGzBridge } from '../../composables/useGzBridge'
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
const { connectionStatus, initialize, dispose, showGrid, showCollisions, showOrbitIndicator } =
  useGzBridge()

// ---------- 面板设置集成 ----------
const { registerPanel, unregisterPanel, updateSettingsTree } = usePanelState()
const config = ref<GzWebViewerConfig>({ ...defaultConfig })

// ---------- iframe ----------
const gzIframe = ref<HTMLIFrameElement | null>(null)

/**
 * 构造 iframe src URL
 * @param gzwebUrl gzbridge HTTP 服务地址
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

const iframeSrc = computed(() => buildIframeSrc(config.value.gzwebUrl))

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

  refreshSettingsTree()
}

function refreshSettingsTree() {
  updateSettingsTree(props.panelId, {
    actionHandler: createActionHandler(config.value, saveConfig),
    nodes: buildSettingsTree(config.value)
  })
}

// ---------- 生命周期 ----------
onMounted(() => {
  registerPanel(props.panelId, 'GzWebViewer')
  refreshSettingsTree()

  // 等待 iframe 渲染后初始化通信
  if (gzIframe.value) {
    initialize(gzIframe.value)
  }
})

onBeforeUnmount(() => {
  dispose()
  unregisterPanel(props.panelId)
})

// 监听 gzwebUrl 变更 → iframe 自动重新加载（src 是 computed）
// 监听 config 变更 → 更新设置树
watch(config, refreshSettingsTree, { deep: true })
</script>

<template>
  <div class="gzweb-viewer">
    <iframe
      ref="gzIframe"
      :src="iframeSrc"
      class="gzweb-iframe"
      allow="autoplay"
      sandbox="allow-scripts allow-same-origin"
    ></iframe>
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

.gzweb-iframe {
  width: 100%;
  height: 100%;
  border: none;
  display: block;
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
