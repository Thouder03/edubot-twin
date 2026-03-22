/**
 * useGzBridge - GzWeb iframe 通信状态管理 composable
 *
 * 模块级单例：状态在所有调用者之间共享
 *
 * ── 页面级生命周期 ──
 * - Simulation.vue 在 onMounted 时调用 initialize(gzwebUrl) 创建隐藏 iframe 并启动通信
 * - Simulation.vue 在 onBeforeUnmount 时调用 dispose() 销毁 iframe 和清理定时器
 *
 * ── GzWebViewer 面板级集成 ──
 * - GzWebViewer 调用 attachToContainer(el) 把 iframe 移入可视容器
 * - GzWebViewer 卸载时调用 detachFromContainer() 把 iframe 移回 body (隐藏)
 * - GzWebViewer 面板关闭不影响通信，SimControlBar 仍可控制仿真
 *
 * ── SimControlBar ──
 * - 读取状态、调用指令方法
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

/** iframe 是否已 attach 到某个可视容器（即 GzWebViewer 面板） */
const _isAttached = ref(false)

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
  _isAttached.value = false
}

/**
 * 构造 iframe src URL
 * @param gzwebUrl gzbridge HTTP 服务地址 (如 "http://192.168.1.100:9001")
 */
function _buildIframeSrc(gzwebUrl: string): string {
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

// ════════════════════════════════════════════
// 公开 Composable
// ════════════════════════════════════════════

export function useGzBridge() {
  // ── 页面级生命周期（由 Simulation.vue 调用）──

  /**
   * 初始化: 创建隐藏 iframe 并开始监听 postMessage
   *
   * 在仿真页面 onMounted 时调用，不依赖 GzWebViewer 面板是否已挂载。
   * iframe 以 display:none 挂在 document.body 上，仍能正常加载和通信。
   *
   * @param gzwebUrl gzbridge HTTP 服务地址 (如 "http://192.168.1.100:8080")
   */
  const initialize = (gzwebUrl: string): void => {
    // 防止重复初始化
    if (_iframe.value) return

    // 创建隐藏 iframe
    const el = document.createElement('iframe')
    el.src = _buildIframeSrc(gzwebUrl)
    el.style.cssText = 'position:absolute;width:0;height:0;border:none;visibility:hidden;'
    el.setAttribute('allow', 'autoplay')
    el.setAttribute('sandbox', 'allow-scripts allow-same-origin')
    document.body.appendChild(el)

    _iframe.value = el
    _isAttached.value = false

    // 注册消息监听
    _messageHandler = _handleMessage
    window.addEventListener('message', _messageHandler)
  }

  /** 销毁: 移除 iframe、清理所有监听器和定时器 */
  const dispose = (): void => {
    _stopHeartbeat()
    if (_messageHandler) {
      window.removeEventListener('message', _messageHandler)
      _messageHandler = null
    }
    // 从 DOM 中移除 iframe
    if (_iframe.value) {
      _iframe.value.remove()
      _iframe.value = null
    }
    _resetState()
  }

  // ── 面板级集成（由 GzWebViewer 调用）──

  /**
   * 将已有的 iframe 移入可视容器（GzWebViewer 面板的 DOM 容器）
   *
   * 移入后 iframe 变为可见、占满容器空间，用户可以看到 3D 场景。
   *
   * @param container GzWebViewer 面板内部用于承载 iframe 的容器元素
   */
  const attachToContainer = (container: HTMLElement): void => {
    if (!_iframe.value) return

    // 从隐藏位置移到容器
    container.appendChild(_iframe.value)
    _iframe.value.style.cssText = 'width:100%;height:100%;border:none;display:block;'
    _isAttached.value = true
  }

  /**
   * 将 iframe 从可视容器中移出，回到 body 隐藏
   *
   * GzWebViewer 面板关闭时调用。iframe 仍保持活跃连接，通信不中断。
   */
  const detachFromContainer = (): void => {
    if (!_iframe.value) return

    // 移回 body 并隐藏
    document.body.appendChild(_iframe.value)
    _iframe.value.style.cssText =
      'position:absolute;width:0;height:0;border:none;visibility:hidden;'
    _isAttached.value = false
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

  /**
   * 更新 gzwebUrl，重新加载 iframe
   *
   * 当用户在设置面板中修改 gzwebUrl 时调用。
   */
  const updateGzwebUrl = (gzwebUrl: string): void => {
    if (!_iframe.value) return
    const newSrc = _buildIframeSrc(gzwebUrl)
    if (_iframe.value.src !== newSrc) {
      // 重置通信状态，iframe 重新加载后会重新走 ready → connecting → connected 流程
      _isBridgeReady.value = false
      _connectionStatus.value = 'disconnected'
      _stopHeartbeat()
      _iframe.value.src = newSrc
    }
  }

  return {
    // ── 只读状态 ──
    connectionStatus: readonly(_connectionStatus) as Ref<GzConnectionStatus>,
    isPaused: readonly(_isPaused),
    simTime: readonly(_simTime),
    realTime: readonly(_realTime),
    isBridgeReady: readonly(_isBridgeReady),
    isConnected: computed(() => _connectionStatus.value === 'connected'),
    isAttached: readonly(_isAttached),

    // ── 页面级生命周期 ──
    initialize,
    dispose,

    // ── 面板级集成 ──
    attachToContainer,
    detachFromContainer,

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
    showOrbitIndicator,
    updateGzwebUrl
  }
}
