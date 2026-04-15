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
import { getContainerStatusText } from '../../constants/containerStatus'

// ---------- Props ----------
const props = defineProps<{ panelId: string }>()

// ---------- 设置接入 ----------
const { config } = usePanelConfig(props.panelId, DEFAULT_CONFIG, buildNodes, applyAction)
const { registerPanel, unregisterPanel } = usePanelState()

// ---------- 容器状态联动 ----------
const containerStatus = inject<Ref<ContainerStatus | null>>('containerStatus', ref(null))
const isRunning = computed(() => containerStatus.value === 'running')

const statusText = computed(() => getContainerStatusText(containerStatus.value))

// ---------- 考试锁定（第13期 SDD §7.2）----------
// running/scoring 状态时，根据 allow_debug_during_exam 决定是否禁用终端输入
const isExamLocked = inject<Ref<boolean>>('isExamLocked', ref(false))
const allowDebugDuringExam = inject<Ref<boolean>>('allowDebugDuringExam', ref(true))
// 终端禁用条件：考试锁定且不允许调试
const isTerminalDisabled = computed(() => isExamLocked.value && !allowDebugDuringExam.value)

// ---------- 用户 Token ----------
const userStore = useUserStore()

// ---------- Dry Run / ROOT 模式 ----------
const isDryRunMode = computed(() => !!sessionStorage.getItem('simulation_token'))
const rootMode = ref(false)

function toggleRootMode() {
  rootMode.value = !rootMode.value
  // 重新连接 WebSocket（切换 root 参数）
  terminal?.clear()
  connectWs()
}

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

function getWsUrl(rootMode = false): string {
  // Dry Run 标签页中优先使用 Shadow 学生 JWT
  const simulationToken = sessionStorage.getItem('simulation_token')
  const token = simulationToken || userStore.getToken
  const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:'
  const host = window.location.host
  const rootParam = rootMode ? '&root=1' : ''
  return `${protocol}//${host}${TERMINAL_WS_PATH}?token=${encodeURIComponent(token ?? '')}${rootParam}`
}

function connectWs() {
  if (ws) {
    ws.close()
    ws = null
  }
  wsError.value = ''

  const url = getWsUrl(rootMode.value)
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

  // 用户输入 → 发到 ws（考试锁定时禁止输入）
  terminal.onData((data) => {
    if (isTerminalDisabled.value) return
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
        <!-- ROOT 切换（仅 Dry Run 模式可见）-->
        <button
          v-if="isDryRunMode"
          class="container-terminal__root-btn"
          :class="{ active: rootMode }"
          :title="rootMode ? '切换回普通用户' : '切换到 ROOT 用户'"
          @click="toggleRootMode"
        >
          {{ rootMode ? '🔴 ROOT' : '⚪ USER' }}
        </button>
      </div>

      <!-- 考试锁定提示条 -->
      <div v-if="isTerminalDisabled" class="container-terminal__exam-lock">
        🔒 考试进行中：终端输入已禁用
      </div>

      <!-- xterm 容器 -->
      <div
        ref="terminalEl"
        class="container-terminal__xterm"
        :class="{ 'is-locked': isTerminalDisabled }"
      ></div>
    </template>
  </div>
</template>

<style lang="less" scoped>
.container-terminal {
  position: relative;
  display: flex;
  width: 100%;
  height: 100%;
  overflow: hidden;
  background: #1e1e2e;
  flex-direction: column;

  &__overlay {
    position: absolute;
    z-index: 10;
    display: flex;
    background: rgb(30 30 46 / 92%);
    inset: 0;
    flex-direction: column;
    align-items: center;
    justify-content: center;
    gap: 12px;
  }

  &__overlay-icon {
    font-size: 32px;
    color: #f9e2af;
  }

  &__overlay-text {
    padding: 0 24px;
    font-size: 14px;
    color: #a6adc8;
    text-align: center;
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
    padding: 2px 10px;
    font-size: 11px;
    color: #89b4fa;
    cursor: pointer;
    background: rgb(137 180 250 / 10%);
    border: 1px solid #89b4fa;
    border-radius: 4px;
    transition: all 0.15s ease;

    &:hover {
      background: rgb(137 180 250 / 20%);
    }
  }

  &__root-btn {
    margin-left: auto;
    padding: 2px 8px;
    font-size: 11px;
    cursor: pointer;
    background: rgb(249 114 114 / 10%);
    border: 1px solid #585b70;
    border-radius: 4px;
    color: #a6adc8;
    transition: all 0.15s ease;

    &.active {
      background: rgb(249 114 114 / 20%);
      border-color: #f38ba8;
      color: #f38ba8;
    }

    &:hover {
      background: rgb(249 114 114 / 25%);
    }
  }

  &__xterm {
    padding: 4px;
    overflow: hidden;
    flex: 1;

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

.container-terminal__exam-lock {
  padding: 4px 12px;
  font-size: 12px;
  background: rgba(245, 108, 108, 0.15);
  color: #f56c6c;
  border-bottom: 1px solid rgba(245, 108, 108, 0.3);
  text-align: center;
}

.container-terminal__xterm.is-locked {
  opacity: 0.8;
  cursor: not-allowed;
}
</style>
