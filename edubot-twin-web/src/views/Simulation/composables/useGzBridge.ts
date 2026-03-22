/**
 * useGzBridge - GzWeb iframe 通信状态管理 composable
 *
 * 模块级单例：状态在所有调用者之间共享
 * - GzWebViewer 调用 initialize/dispose 管理 iframe 生命周期
 * - SimControlBar 读取状态、调用指令方法
 *
 * 心跳: 5s 间隔 / 3s 超时
 */
import { ref, readonly, computed, type Ref } from 'vue'
import type { GzCommand, GzEvent, GzConnectionStatus } from '../panels/GzWebViewer/types'

// ════════════════════════════════════════════
// 模块级单例状态
// ════════════════════════════════════════════

const _iframe = ref<HTMLIFrameElement | null>(null)
const _connectionStatus = ref<GzConnectionStatus>('disconnected')
const _isPaused = ref<boolean>(true)
const _simTime = ref('00:00:00.000')
const _realTime = ref('00:00:00.000')
const _isBridgeReady = ref(false)

// 心跳内部状态
let _heartbeatTimer: ReturnType<typeof setInterval> | null = null
let _pongTimer: ReturnType<typeof setTimeout> | null = null
let _messageHandler: ((event: MessageEvent) => void) | null = null

const HEARTBEAT_INTERVAL = 5000 // 5 秒
const PONG_TIMEOUT = 3000 // 3 秒

// ════════════════════════════════════════════
// 内部方法
// ════════════════════════════════════════════

/** 安全地发送指令到 iframe */
function _sendCommand(command: GzCommand): void {
  if (_iframe.value?.contentWindow && _isBridgeReady.value) {
    _iframe.value.contentWindow.postMessage(command, '*')
  }
}

/** 处理从 iframe 收到的 postMessage 事件 */
function _handleMessage(event: MessageEvent): void {
  const msg = event.data as GzEvent
  if (!msg || typeof msg.type !== 'string' || !msg.type.startsWith('gz:')) return

  switch (msg.type) {
    case 'gz:ready':
      _isBridgeReady.value = true
      _connectionStatus.value = 'connecting'
      _startHeartbeat()
      break

    case 'gz:connection':
      _connectionStatus.value = msg.payload.connected ? 'connected' : 'error'
      break

    case 'gz:paused':
      _isPaused.value = msg.payload.paused
      break

    case 'gz:simTime':
      _simTime.value = msg.payload.simTime
      break

    case 'gz:realTime':
      _realTime.value = msg.payload.realTime
      break

    case 'gz:pong':
      // 收到 pong，清除超时计时器
      if (_pongTimer !== null) {
        clearTimeout(_pongTimer)
        _pongTimer = null
      }
      // 用 pong 中的 connected 状态更新
      if (msg.payload.connected && _connectionStatus.value !== 'connected') {
        _connectionStatus.value = 'connected'
      }
      break
  }
}

/** 启动心跳定时器 */
function _startHeartbeat(): void {
  _stopHeartbeat()
  _heartbeatTimer = setInterval(() => {
    if (_isBridgeReady.value) {
      _sendCommand({ type: 'gz:ping', payload: {} as Record<string, never> })
      // 设置 pong 超时
      _pongTimer = setTimeout(() => {
        _connectionStatus.value = 'error'
      }, PONG_TIMEOUT)
    }
  }, HEARTBEAT_INTERVAL)
}

/** 停止心跳定时器 */
function _stopHeartbeat(): void {
  if (_heartbeatTimer !== null) {
    clearInterval(_heartbeatTimer)
    _heartbeatTimer = null
  }
  if (_pongTimer !== null) {
    clearTimeout(_pongTimer)
    _pongTimer = null
  }
}

/** 重置所有状态 */
function _resetState(): void {
  _connectionStatus.value = 'disconnected'
  _isPaused.value = true
  _simTime.value = '00:00:00.000'
  _realTime.value = '00:00:00.000'
  _isBridgeReady.value = false
}

// ════════════════════════════════════════════
// 公开 Composable
// ════════════════════════════════════════════

export function useGzBridge() {
  // ── 生命周期管理（由 GzWebViewer 调用）──

  /** 初始化: 绑定 iframe 并开始监听 postMessage */
  const initialize = (iframeElement: HTMLIFrameElement): void => {
    _iframe.value = iframeElement
    _messageHandler = _handleMessage
    window.addEventListener('message', _messageHandler)
  }

  /** 销毁: 清理所有监听器和定时器 */
  const dispose = (): void => {
    _stopHeartbeat()
    if (_messageHandler) {
      window.removeEventListener('message', _messageHandler)
      _messageHandler = null
    }
    _iframe.value = null
    _resetState()
  }

  // ── 指令方法（由 SimControlBar 或设置面板调用）──

  const sendCommand = (command: GzCommand): void => _sendCommand(command)

  const togglePause = (): void => {
    _sendCommand({ type: 'gz:pause', payload: { paused: !_isPaused.value } })
  }

  const pause = (): void => {
    _sendCommand({ type: 'gz:pause', payload: { paused: true } })
  }

  const resume = (): void => {
    _sendCommand({ type: 'gz:pause', payload: { paused: false } })
  }

  const resetWorld = (): void => {
    _sendCommand({ type: 'gz:reset', payload: { resetType: 'world' } })
  }

  const resetModels = (): void => {
    _sendCommand({ type: 'gz:reset', payload: { resetType: 'model' } })
  }

  const resetView = (): void => {
    _sendCommand({ type: 'gz:resetView', payload: {} as Record<string, never> })
  }

  const showGrid = (visible: boolean): void => {
    _sendCommand({ type: 'gz:showGrid', payload: { visible } })
  }

  const showCollisions = (visible: boolean): void => {
    _sendCommand({ type: 'gz:showCollisions', payload: { visible } })
  }

  const showOrbitIndicator = (visible: boolean): void => {
    _sendCommand({ type: 'gz:showOrbitIndicator', payload: { visible } })
  }

  return {
    // ── 只读状态 ──
    connectionStatus: readonly(_connectionStatus) as Ref<GzConnectionStatus>,
    isPaused: readonly(_isPaused),
    simTime: readonly(_simTime),
    realTime: readonly(_realTime),
    isBridgeReady: readonly(_isBridgeReady),
    isConnected: computed(() => _connectionStatus.value === 'connected'),

    // ── 生命周期 ──
    initialize,
    dispose,

    // ── 指令方法 ──
    sendCommand,
    togglePause,
    pause,
    resume,
    resetWorld,
    resetModels,
    resetView,
    showGrid,
    showCollisions,
    showOrbitIndicator
  }
}
