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
 * - GzWebViewer 调用 attachToContainer(el) 启动 CSS 定位同步
 * - GzWebViewer 卸载时调用 detachFromContainer() 停止同步并隐藏 iframe
 * - iframe 始终是 document.body 的子元素，从不做 DOM 移动（避免浏览器重新加载 iframe）
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

const _currentGzwebUrl = ref<string>('')

// 心跳内部状态
let _heartbeatTimer: ReturnType<typeof setInterval> | null = null
let _pongTimer: ReturnType<typeof setTimeout> | null = null
let _retryTimer: ReturnType<typeof setInterval> | null = null
let _messageHandler: ((event: MessageEvent) => void) | null = null

// CSS 定位同步状态
let _containerEl: HTMLElement | null = null
let _rafId: number | null = null

// 拖拽期间禁用 iframe 鼠标事件（防止 iframe 吞掉 GL 分割线的 mousemove）
let _onMouseDown: (() => void) | null = null
let _onMouseUp: (() => void) | null = null

const HEARTBEAT_INTERVAL = 5000 // 5 秒
const PONG_TIMEOUT = 3000 // 3 秒

/** iframe 隐藏时的样式（移到屏幕外） */
const HIDDEN_STYLE =
  'position:fixed;left:-9999px;top:-9999px;width:1px;height:1px;border:none;pointer-events:none;'

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
      if (msg.payload.connected) {
        _connectionStatus.value = 'connected'
        _stopRetry()
      } else {
        _connectionStatus.value = 'error'
        _startRetry()
      }
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
      if (msg.payload.connected) {
        if (_connectionStatus.value !== 'connected') {
          _connectionStatus.value = 'connected'
        }
        _stopRetry()
      } else {
        // pong 回来但 connected=false：Gazebo 后端已断开，iframe 仍运行
        // 必须在此处处理，否则 pong 超时被取消后状态永远卡在 connected
        _connectionStatus.value = 'error'
        _startRetry()
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
        _startRetry()
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

/** 停止自动重试定时器 */
function _stopRetry(): void {
  if (_retryTimer !== null) {
    clearInterval(_retryTimer)
    _retryTimer = null
  }
}

/**
 * 重新连接：重置桥接状态并重新加载 iframe src
 * 停止所有定时器后重置 src，触发完整 ready→connecting→connected 流程
 */
function _reconnect(): void {
  if (!_iframe.value) return
  _stopRetry()
  _stopHeartbeat()
  _isBridgeReady.value = false
  _connectionStatus.value = 'disconnected'
  // 先清空 src，再下一帧重新赋值，强制浏览器重新加载 iframe
  // 若直接设置相同 URL，浏览器会静默忽略，gz:ready 永远不会触发
  const src = _buildIframeSrc(_currentGzwebUrl.value)
  _iframe.value.src = ''
  requestAnimationFrame(() => {
    if (_iframe.value) _iframe.value.src = src
  })
}

/**
 * 启动自动重试定时器
 * 幂等：若已有定时器则不重复启动
 * @param interval 重试间隔毫秒数，默认 15000ms
 */
function _startRetry(interval = 15000): void {
  if (_retryTimer !== null) return
  _retryTimer = setInterval(() => {
    _reconnect()
  }, interval)
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

// ── CSS 定位同步 ──

/**
 * RAF 循环：将 iframe 的 position:fixed 对齐到容器 getBoundingClientRect()
 *
 * 当容器元素被从 DOM 中移除（如 GL 销毁面板）时自动停止同步并隐藏 iframe。
 */
function _syncPosition(): void {
  if (!_iframe.value || !_containerEl) return

  // 容器已脱离 DOM → 自动 detach
  if (!document.contains(_containerEl)) {
    _containerEl = null
    _iframe.value.style.cssText = HIDDEN_STYLE
    _isAttached.value = false
    _rafId = null
    return
  }

  const rect = _containerEl.getBoundingClientRect()
  const s = _iframe.value.style
  s.position = 'fixed'
  s.left = rect.left + 'px'
  s.top = rect.top + 'px'
  s.width = rect.width + 'px'
  s.height = rect.height + 'px'
  s.border = 'none'
  s.visibility = 'visible'
  // pointerEvents 不在此处设置，由 mousedown/mouseup 处理器控制
  s.zIndex = '1'

  _rafId = requestAnimationFrame(_syncPosition)
}

/** 启动 RAF 位置同步 */
function _startPositionSync(): void {
  _stopPositionSync()
  _rafId = requestAnimationFrame(_syncPosition)
}

/** 停止 RAF 位置同步 */
function _stopPositionSync(): void {
  if (_rafId !== null) {
    cancelAnimationFrame(_rafId)
    _rafId = null
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
   * iframe 以 position:fixed 移到屏幕外，始终是 body 的直接子元素。
   *
   * @param gzwebUrl gzbridge HTTP 服务地址 (如 "http://192.168.1.100:8080")
   */
  const initialize = (gzwebUrl: string): void => {
    // 防止重复初始化
    if (_iframe.value) return

    // 创建 iframe (始终挂在 body，永不做 DOM 移动)
    const el = document.createElement('iframe')
    _currentGzwebUrl.value = gzwebUrl
    el.src = _buildIframeSrc(gzwebUrl)
    el.style.cssText = HIDDEN_STYLE
    el.setAttribute('allow', 'autoplay')
    el.setAttribute('sandbox', 'allow-scripts allow-same-origin')
    document.body.appendChild(el)

    _iframe.value = el

    // 如果在初始化前已经有组件尝试 attach，则现在立即绑定
    if (_containerEl) {
      _startPositionSync()
      _isAttached.value = true
    } else {
      _isAttached.value = false
    }

    // 注册消息监听
    _messageHandler = _handleMessage
    window.addEventListener('message', _messageHandler)

    // 拖拽保护：mousedown 时禁用 iframe pointer-events，mouseup 时恢复
    // 防止 iframe 吞掉 GL 分割线/Tab 拖拽的 mousemove 事件
    _onMouseDown = () => {
      if (_iframe.value) _iframe.value.style.pointerEvents = 'none'
    }
    _onMouseUp = () => {
      if (_iframe.value && _isAttached.value) _iframe.value.style.pointerEvents = 'auto'
    }
    window.addEventListener('mousedown', _onMouseDown)
    window.addEventListener('mouseup', _onMouseUp)
  }

  /** 销毁: 移除 iframe、清理所有监听器和定时器 */
  const dispose = (): void => {
    _stopPositionSync()
    _stopHeartbeat()
    _stopRetry()
    if (_messageHandler) {
      window.removeEventListener('message', _messageHandler)
      _messageHandler = null
    }
    if (_onMouseDown) {
      window.removeEventListener('mousedown', _onMouseDown)
      _onMouseDown = null
    }
    if (_onMouseUp) {
      window.removeEventListener('mouseup', _onMouseUp)
      _onMouseUp = null
    }
    // 从 DOM 中移除 iframe
    if (_iframe.value) {
      _iframe.value.remove()
      _iframe.value = null
    }
    // 不清理 _containerEl，以便 reinitGzBridge 后仍能附着到现存的面板
    _resetState()
  }

  // ── 面板级集成（由 GzWebViewer 调用）──

  /**
   * 将 iframe 通过 CSS position:fixed 对齐到容器上方
   *
   * iframe 始终留在 body 中，不做 DOM 移动（防止浏览器重新加载 iframe）。
   * 通过 RAF 循环持续同步 iframe 位置和尺寸到容器的 getBoundingClientRect()。
   *
   * @param container GzWebViewer 面板内部用于承载 iframe 的容器元素（作为定位参考）
   */
  const attachToContainer = (container: HTMLElement): void => {
    _containerEl = container
    if (!_iframe.value) return

    _startPositionSync()
    _isAttached.value = true
  }

  /**
   * 取消 CSS 定位同步，隐藏 iframe
   *
   * GzWebViewer 面板关闭时调用。iframe 仍保持在 body 中，通信不中断。
   */
  const detachFromContainer = (): void => {
    _stopPositionSync()
    _containerEl = null
    if (_iframe.value) {
      _iframe.value.style.cssText = HIDDEN_STYLE
    }
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
      _currentGzwebUrl.value = gzwebUrl
      // 重置通信状态，iframe 重新加载后会重新走 ready → connecting → connected 流程
      _isBridgeReady.value = false
      _connectionStatus.value = 'disconnected'
      _stopHeartbeat()
      _iframe.value.src = newSrc
    }
  }

  return {
    // ── 只读状态 ──
    currentGzwebUrl: readonly(_currentGzwebUrl),
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
    updateGzwebUrl,
    reconnect: _reconnect
  }
}
