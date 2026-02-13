/**
 * useRosConnection - ROS WebSocket 连接管理
 *
 * 职责:
 * 1. 使用 ROSLIB.Ros 建立/断开 WebSocket 连接
 * 2. 维护响应式连接状态
 * 3. URL 变更时自动重连
 */
import { ref, watch, type Ref } from 'vue'
import { Ros } from 'roslib'

export type RosConnectionStatus = 'disconnected' | 'connecting' | 'connected' | 'error'

export function useRosConnection(rosUrl: Ref<string>) {
  const status = ref<RosConnectionStatus>('disconnected')
  const errorMessage = ref<string>('')

  let ros: Ros | null = null

  /** 获取当前 ros 实例（用于 Topic 订阅） */
  function getRos(): Ros | null {
    return ros
  }

  /** 建立连接 */
  function connect() {
    // 先断开旧连接
    disconnect()

    const url = rosUrl.value
    if (!url) {
      status.value = 'disconnected'
      return
    }

    status.value = 'connecting'
    errorMessage.value = ''

    ros = new Ros()

    ros.on('connection', () => {
      status.value = 'connected'
      errorMessage.value = ''
      console.log(`[ROS] 已连接: ${url}`)
    })

    ros.on('close', () => {
      status.value = 'disconnected'
      console.log(`[ROS] 连接关闭: ${url}`)
    })

    ros.on('error', (error: Error) => {
      status.value = 'error'
      errorMessage.value = error.message || '连接失败'
      console.warn(`[ROS] 连接错误: ${url}`, error)
    })

    try {
      ros.connect(url)
    } catch (e) {
      status.value = 'error'
      errorMessage.value = (e as Error).message || '连接异常'
    }
  }

  /** 断开连接 */
  function disconnect() {
    if (ros) {
      try {
        ros.close()
      } catch {
        /* 忽略关闭时的异常 */
      }
      ros = null
    }
    status.value = 'disconnected'
    errorMessage.value = ''
  }

  // URL 变更时自动重连
  watch(rosUrl, (newUrl, oldUrl) => {
    if (newUrl !== oldUrl) {
      connect()
    }
  })

  return {
    status,
    errorMessage,
    getRos,
    connect,
    disconnect
  }
}
