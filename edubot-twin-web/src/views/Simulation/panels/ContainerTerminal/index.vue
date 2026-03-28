<script setup lang="ts">
/**
 * ContainerTerminal - 容器终端面板
 *
 * - xterm.js + FitAddon 实现 Web 终端
 * - WebSocket 连接 /api/v1/students/terminal/ws?token=xxx
 * - 容器非 running 时：显示禁用遮罩
 * - 断连后显示重连按钮
 */
import { ref, computed, inject, onMounted, onBeforeUnmount, watch, nextTick, type Ref } from 'vue'
import { Terminal } from 'xterm'
import 'xterm/css/xterm.css'
import { FitAddon } from '@xterm/addon-fit'
import { usePanelConfig } from '../../composables/usePanelConfig'
import { usePanelState } from '../../stores/panelState'
import { DEFAULT_CONFIG, buildNodes, applyAction } from './settings'
import { useUserStore } from '@/store/modules/user'
import type { ContainerStatus } from '@/api/container/types'

// ---------- Props ----------
const props = defineProps<{ panelId: string }>()

// ---------- 设置接入 ----------
const { config } = usePanelConfig(props.panelId, DEFAULT_CONFIG, buildNodes, applyAction)
const { registerPanel, unregisterPanel } = usePanelState()

// ---------- 容器状态联动 ----------
const containerStatus = inject<Ref<ContainerStatus | null>>('containerStatus', ref(null))
const isRunning = computed(() => containerStatus.value === 'running')

const statusText = computed(() => {
  const s = containerStatus.value
  if (!s) return '容器状态未知，请稍候...'
  const map: Record<ContainerStatus, string> = {
    running: '运行中',
    stopped: '容器已停止，请返回首页重启后使用',
    creating: '容器启动中，请稍候...',
    removing: '容器删除中',
    error: '容器异常，请联系管理员'
  }
  return map[s] ?? s
})

// ---------- 用户 Token ----------
const userStore = useUserStore()

// ---------- xterm 相关 ----------
const terminalEl = ref<HTMLElement | null>(null)
let terminal: Terminal | null = null
let fitAddon: FitAddon | null = null
let resizeObserver: ResizeObserver | null = null

// ---------- WebSocket ----------
let ws: WebSocket | null = null
const wsConnected = ref(false)
const wsError = ref('')

const TERMINAL_WS_PATH = '/api/v1/students/terminal/ws'

function getWsUrl(): string {
  const token = userStore.getToken
  const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:'
  const host = window.location.host
  return `${protocol}//${host}${TERMINAL_WS_PATH}?token=${encodeURIComponent(token ?? '')}`
}

function connectWs() {
  if (ws) {
    ws.close()
    ws = null
  }
  wsError.value = ''

  const url = getWsUrl()
  ws = new WebSocket(url)
  ws.binaryType = 'arraybuffer'

  ws.onopen = () => {
    wsConnected.value = true
    terminal?.write('\r\n\x1b[32m[终端已连接]\x1b[0m\r\n')
  }

  ws.onmessage = (event) => {
    if (!terminal) return
    if (event.data instanceof ArrayBuffer) {
      terminal.write(new Uint8Array(event.data))
    } else {
      terminal.write(event.data)
    }
  }

  ws.onerror = () => {
    wsConnected.value = false
    wsError.value = '终端连接失败'
    terminal?.write('\r\n\x1b[31m[连接错误]\x1b[0m\r\n')
  }

  ws.onclose = (e) => {
    wsConnected.value = false
    if (e.code !== 1000) {
      wsError.value = `已断开 (${e.code})`
      terminal?.write('\r\n\x1b[33m[连接已断开，点击重连按钮重试]\x1b[0m\r\n')
    }
  }
}

function reconnect() {
  wsError.value = ''
  terminal?.clear()
  connectWs()
}

// ---------- xterm 主题 ----------
const DARK_THEME = {
  background: '#1e1e2e',
  foreground: '#cdd6f4',
  cursor: '#f5e0dc',
  selectionBackground: '#585b70',
  black: '#45475a',
  red: '#f38ba8',
  green: '#a6e3a1',
  yellow: '#f9e2af',
  blue: '#89b4fa',
  magenta: '#f5c2e7',
  cyan: '#89dceb',
  white: '#bac2de',
  brightBlack: '#585b70',
  brightRed: '#f38ba8',
  brightGreen: '#a6e3a1',
  brightYellow: '#f9e2af',
  brightBlue: '#89b4fa',
  brightMagenta: '#f5c2e7',
  brightCyan: '#89dceb',
  brightWhite: '#a6adc8'
}

const LIGHT_THEME = {
  background: '#eff1f5',
  foreground: '#4c4f69',
  cursor: '#dc8a78',
  selectionBackground: '#acb0be',
  black: '#5c5f77',
  red: '#d20f39',
  green: '#40a02b',
  yellow: '#df8e1d',
  blue: '#1e66f5',
  magenta: '#ea76cb',
  cyan: '#179299',
  white: '#bcc0cc'
}

// ---------- xterm 初始化 ----------
function initTerminal() {
  if (!terminalEl.value) return
  const theme = config.value.theme === 'dark' ? DARK_THEME : LIGHT_THEME
  terminal = new Terminal({
    fontSize: config.value.fontSize,
    fontFamily: '"Cascadia Code", "Fira Code", "JetBrains Mono", monospace',
    theme,
    cursorBlink: true,
    scrollback: 1000,
    convertEol: true
  })
  fitAddon = new FitAddon()
  terminal.loadAddon(fitAddon)
  terminal.open(terminalEl.value)
  fitAddon.fit()

  // 用户输入 → 发到 ws
  terminal.onData((data) => {
    if (ws && ws.readyState === WebSocket.OPEN) {
      ws.send(data)
    }
  })

  // ResizeObserver 让终端自适应面板大小
  resizeObserver = new ResizeObserver(() => {
    fitAddon?.fit()
  })
  resizeObserver.observe(terminalEl.value)
}

// 监听配置变更应用到终端
watch(
  () => [config.value.fontSize, config.value.theme],
  () => {
    if (!terminal) return
    terminal.options.fontSize = config.value.fontSize
    terminal.options.theme = config.value.theme === 'dark' ? DARK_THEME : LIGHT_THEME
    fitAddon?.fit()
  }
)

// 容器变为 running 时自动连接
watch(isRunning, (running) => {
  if (running && !wsConnected.value) {
    nextTick(() => {
      if (!terminal) initTerminal()
      connectWs()
    })
  }
})

// ---------- 生命周期 ----------
onMounted(async () => {
  registerPanel(props.panelId, 'ContainerTerminal')
  if (isRunning.value) {
    await nextTick()
    initTerminal()
    connectWs()
  }
})

onBeforeUnmount(() => {
  ws?.close(1000)
  ws = null
  resizeObserver?.disconnect()
  terminal?.dispose()
  terminal = null
  fitAddon = null
  unregisterPanel(props.panelId)
})
</script>

<template>
  <div class="container-terminal">
    <!-- 容器未运行遮罩 -->
    <div v-if="!isRunning" class="container-terminal__overlay">
      <div class="container-terminal__overlay-icon">⚠</div>
      <div class="container-terminal__overlay-text">{{ statusText }}</div>
    </div>

    <!-- 终端区域 -->
    <template v-else>
      <!-- 状态栏 -->
      <div class="container-terminal__topbar">
        <span
          class="container-terminal__dot"
          :class="wsConnected ? 'container-terminal__dot--ok' : 'container-terminal__dot--off'"
        ></span>
        <span class="container-terminal__label">
          {{ wsConnected ? '终端已连接' : wsError || '连接中...' }}
        </span>
        <button v-if="!wsConnected" class="container-terminal__reconnect" @click="reconnect">
          重连
        </button>
      </div>

      <!-- xterm 容器 -->
      <div ref="terminalEl" class="container-terminal__xterm"></div>
    </template>
  </div>
</template>

<style lang="less" scoped>
.container-terminal {
  width: 100%;
  height: 100%;
  background: #1e1e2e;
  display: flex;
  flex-direction: column;
  position: relative;
  overflow: hidden;

  &__overlay {
    position: absolute;
    inset: 0;
    display: flex;
    flex-direction: column;
    align-items: center;
    justify-content: center;
    background: rgba(30, 30, 46, 0.92);
    gap: 12px;
    z-index: 10;
  }

  &__overlay-icon {
    font-size: 32px;
    color: #f9e2af;
  }

  &__overlay-text {
    color: #a6adc8;
    font-size: 14px;
    text-align: center;
    padding: 0 24px;
  }

  &__topbar {
    display: flex;
    align-items: center;
    gap: 8px;
    height: 28px;
    padding: 0 10px;
    background: #181825;
    border-bottom: 1px solid #313244;
    flex-shrink: 0;
  }

  &__dot {
    width: 8px;
    height: 8px;
    border-radius: 50%;
    flex-shrink: 0;

    &--ok {
      background: #a6e3a1;
    }

    &--off {
      background: #f38ba8;
      animation: blink 1.5s infinite;
    }
  }

  &__label {
    font-size: 12px;
    color: #a6adc8;
    flex: 1;
  }

  &__reconnect {
    font-size: 11px;
    padding: 2px 10px;
    border-radius: 4px;
    border: 1px solid #89b4fa;
    background: rgba(137, 180, 250, 0.1);
    color: #89b4fa;
    cursor: pointer;
    transition: all 0.15s ease;

    &:hover {
      background: rgba(137, 180, 250, 0.2);
    }
  }

  &__xterm {
    flex: 1;
    overflow: hidden;
    padding: 4px;

    // xterm.js 内部样式覆盖
    :deep(.xterm) {
      height: 100%;
    }

    :deep(.xterm-viewport) {
      overflow-y: auto;
    }
  }
}

@keyframes blink {
  0%,
  100% {
    opacity: 1;
  }
  50% {
    opacity: 0.3;
  }
}
</style>
