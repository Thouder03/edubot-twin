import { computed, inject, onBeforeUnmount, onMounted, ref, watch, type Ref } from 'vue'
import { Ros, Topic } from 'roslib'
import { usePanelConfig } from '../../../composables/usePanelConfig'
import { usePanelState } from '../../../stores/panelState'
import { DEFAULT_CONFIG, applyAction, buildNodes } from '../settings'
import type { ContainerStatus } from '@/api/container/types'
import { getContainerStatusText } from '../../../constants/containerStatus'

interface CompressedImageMessage {
  format?: string
  data?: string
}

export function useCamera(panelId: string) {
  const containerRosUrl = inject<Ref<string | null>>('containerRosUrl', ref(null))
  const containerStatus = inject<Ref<ContainerStatus | null>>('containerStatus', ref(null))

  const isRunning = computed(() => containerStatus.value === 'running')
  const statusText = computed(() => getContainerStatusText(containerStatus.value))

  const { config } = usePanelConfig(panelId, DEFAULT_CONFIG, buildNodes, applyAction)
  const { registerPanel, unregisterPanel } = usePanelState()

  const imageSrc = ref('')
  const paused = ref(false)
  const rosConnected = ref(false)
  const fps = ref(0)

  let ros: Ros | null = null
  let topicSub: Topic | null = null
  let fpsResetTimer: ReturnType<typeof setInterval> | null = null
  let frameCount = 0
  let lastFpsUpdate = 0
  let lastFrameTime = 0

  function mimeFromFormat(format?: string): string {
    const raw = (format || '').toLowerCase()
    if (raw.includes('png')) return 'png'
    if (raw.includes('jpeg') || raw.includes('jpg')) return 'jpeg'
    return 'jpeg'
  }

  function handleMessage(message: CompressedImageMessage) {
    if (!message.data) return
    if (paused.value) return

    const now = performance.now()
    if (now - lastFrameTime < config.value.throttleMs) return
    lastFrameTime = now

    const mime = mimeFromFormat(message.format)
    imageSrc.value = `data:image/${mime};base64,${message.data}`

    frameCount += 1
    if (now - lastFpsUpdate >= 1000) {
      fps.value = frameCount
      frameCount = 0
      lastFpsUpdate = now
    }
  }

  function subscribeTopic() {
    if (!ros || !isRunning.value) return

    topicSub?.unsubscribe()
    topicSub = new Topic({
      ros,
      name: config.value.topic,
      messageType: 'sensor_msgs/CompressedImage'
    })
    topicSub.subscribe((message: CompressedImageMessage) => {
      handleMessage(message)
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
      console.warn('[CameraPanel] ROS 连接失败:', e)
    }
  }

  function screenshot() {
    if (!imageSrc.value) return
    const a = document.createElement('a')
    a.href = imageSrc.value
    a.download = `camera_${Date.now()}.jpg`
    a.click()
  }

  function reconnect() {
    connectRos()
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
      fps.value = 0
      frameCount = 0
    }
  })

  onMounted(() => {
    registerPanel(panelId, 'CameraPanel')
    connectRos()
    fpsResetTimer = setInterval(() => {
      if (performance.now() - lastFrameTime > config.value.staleTimeoutMs) {
        fps.value = 0
        frameCount = 0
      }
    }, 1000)
  })

  onBeforeUnmount(() => {
    topicSub?.unsubscribe()
    topicSub = null
    ros?.close()
    ros = null
    if (fpsResetTimer) {
      clearInterval(fpsResetTimer)
      fpsResetTimer = null
    }
    unregisterPanel(panelId)
  })

  return {
    config,
    imageSrc,
    paused,
    rosConnected,
    fps,
    isRunning,
    statusText,
    screenshot,
    reconnect
  }
}
