import { computed, inject, nextTick, onBeforeUnmount, onMounted, ref, watch, type Ref } from 'vue'
import { Ros, Topic } from 'roslib'
import { usePanelConfig } from '../../../composables/usePanelConfig'
import { usePanelState } from '../../../stores/panelState'
import { DEFAULT_CONFIG, applyAction, buildNodes } from '../settings'
import type { ContainerStatus } from '@/api/container/types'

interface RosoutMessage {
  header?: {
    stamp?: {
      secs?: number
      nsecs?: number
    }
  }
  level?: number
  name?: string
  msg?: string
  file?: string
  line?: number
}

export interface RosoutLogEntry {
  id: string
  timestamp: Date
  level: number
  node: string
  message: string
  file?: string
  line?: number
}

export function useRosout(panelId: string, listRef: Ref<HTMLElement | null>) {
  const containerRosUrl = inject<Ref<string | null>>('containerRosUrl', ref(null))
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

  const { config } = usePanelConfig(panelId, DEFAULT_CONFIG, buildNodes, applyAction)
  const { registerPanel, unregisterPanel } = usePanelState()

  const logs = ref<RosoutLogEntry[]>([])
  const keyword = ref('')
  const paused = ref(false)
  const rosConnected = ref(false)

  let ros: Ros | null = null
  let topicSub: Topic | null = null
  let seq = 0

  const filteredLogs = computed(() => {
    const minLevel = config.value.minLevel
    const kw = keyword.value.trim().toLowerCase()
    return logs.value.filter((log) => {
      if (log.level < minLevel) return false
      if (!kw) return true
      return (
        log.message.toLowerCase().includes(kw) ||
        log.node.toLowerCase().includes(kw) ||
        (log.file?.toLowerCase().includes(kw) ?? false)
      )
    })
  })

  function normalizeLevel(level: number | undefined): number {
    const value = level ?? 2
    const valid = [1, 2, 4, 8, 16]
    return valid.includes(value) ? value : 2
  }

  function toDate(msg: RosoutMessage): Date {
    const secs = msg.header?.stamp?.secs
    const nsecs = msg.header?.stamp?.nsecs
    if (typeof secs === 'number' && typeof nsecs === 'number') {
      return new Date(secs * 1000 + Math.floor(nsecs / 1_000_000))
    }
    return new Date()
  }

  function appendLog(msg: RosoutMessage) {
    const entry: RosoutLogEntry = {
      id: `${Date.now()}-${seq++}`,
      timestamp: toDate(msg),
      level: normalizeLevel(msg.level),
      node: msg.name || 'unknown',
      message: msg.msg || '',
      file: msg.file,
      line: msg.line
    }

    logs.value.push(entry)
    while (logs.value.length > config.value.maxLogs) {
      logs.value.shift()
    }

    if (config.value.autoScroll) {
      nextTick(() => {
        const el = listRef.value
        if (el) {
          el.scrollTop = el.scrollHeight
        }
      })
    }
  }

  function subscribeTopic() {
    if (!ros || !isRunning.value) return

    topicSub?.unsubscribe()
    topicSub = new Topic({
      ros,
      name: config.value.topic,
      messageType: 'rosgraph_msgs/Log'
    })

    topicSub.subscribe((msg: RosoutMessage) => {
      if (paused.value) return
      appendLog(msg)
    })
  }

  function connectRos() {
    if (!containerRosUrl.value || !isRunning.value) return

    topicSub?.unsubscribe()
    topicSub = null
    ros?.close()
    ros = null

    try {
      ros = new Ros({ url: containerRosUrl.value })
      ros.on('connection', () => {
        rosConnected.value = true
        subscribeTopic()
      })
      ros.on('error', () => {
        rosConnected.value = false
      })
      ros.on('close', () => {
        rosConnected.value = false
      })
    } catch (e) {
      rosConnected.value = false
      console.warn('[RosoutPanel] ROS 连接失败:', e)
    }
  }

  function clearLogs() {
    logs.value = []
  }

  function exportLogs() {
    const pad = (n: number) => String(n).padStart(2, '0')
    const now = new Date()
    const filename = `rosout_${now.getFullYear()}${pad(now.getMonth() + 1)}${pad(now.getDate())}_${pad(now.getHours())}${pad(now.getMinutes())}${pad(now.getSeconds())}.log`

    const content = filteredLogs.value
      .map((item) => {
        return JSON.stringify({
          id: item.id,
          timestamp: item.timestamp.toISOString(),
          level: item.level,
          node: item.node,
          message: item.message,
          file: item.file,
          line: item.line
        })
      })
      .join('\n')

    const blob = new Blob([content], { type: 'text/plain;charset=utf-8' })
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = filename
    a.click()
    URL.revokeObjectURL(url)
  }

  watch(containerRosUrl, () => {
    connectRos()
  })

  watch(
    () => config.value.topic,
    () => {
      if (rosConnected.value) subscribeTopic()
    }
  )

  watch(isRunning, (running) => {
    if (running) {
      connectRos()
    } else {
      topicSub?.unsubscribe()
      topicSub = null
      ros?.close()
      ros = null
      rosConnected.value = false
    }
  })

  onMounted(() => {
    registerPanel(panelId, 'RosoutPanel')
    connectRos()
  })

  onBeforeUnmount(() => {
    topicSub?.unsubscribe()
    topicSub = null
    ros?.close()
    ros = null
    unregisterPanel(panelId)
  })

  return {
    config,
    logs,
    filteredLogs,
    keyword,
    paused,
    rosConnected,
    isRunning,
    statusText,
    clearLogs,
    exportLogs
  }
}
