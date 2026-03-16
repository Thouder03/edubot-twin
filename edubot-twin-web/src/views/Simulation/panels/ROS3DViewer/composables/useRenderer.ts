/**
 * useRenderer — Renderer 生命周期管理 Composable
 *
 * 职责:
 * 1. 创建 / 销毁 Renderer 实例
 * 2. 将 RendererConfig 与 Vue 响应式状态同步
 * 3. 监听 Renderer 事件 → 更新 Vue 状态
 * 4. 暴露消息/主题 API 给外部
 */
import { ref, shallowRef, onBeforeUnmount } from 'vue'
import { Renderer } from '../core/Renderer'
import type { RendererConfig } from '../core/IRenderer'
import type { SceneExtensionConfig } from '../core/SceneExtensionConfig'
import type { MessageEvent, Topic } from '../core/lichtblick-shim'
import type { CameraState } from '../core/camera'
import { SceneSettings } from '../extensions/SceneSettings'
import { Grids } from '../extensions/Grids'
import { FrameAxes } from '../extensions/FrameAxes'
import { Markers } from '../extensions/Markers'
import { LaserScans } from '../extensions/LaserScans'
import { Polygons } from '../extensions/Polygons'
import { OccupancyGrids } from '../extensions/OccupancyGrids'
import { PointClouds } from '../extensions/PointClouds'
import { Poses } from '../extensions/Poses'
import { PoseArrays } from '../extensions/PoseArrays'
import { PublishSettings } from '../extensions/PublishSettings'
import type { PublishClickType } from '../extensions/PublishClickTool'

/** 默认 RendererConfig */
function defaultRendererConfig(): RendererConfig {
  return {
    cameraState: {
      perspective: true,
      distance: 20,
      phi: 60,
      thetaOffset: 45,
      fovy: 45,
      near: 0.5,
      far: 5000,
      target: [0, 0, 0],
      targetOffset: [0, 0, 0],
      targetOrientation: [0, 0, 0, 1]
    },
    followMode: 'follow-pose',
    followTf: undefined,
    scene: {
      backgroundColor: '#1e1e2e',
      labelScaleFactor: 1,
      ignoreColladaUpAxis: false,
      meshUpAxis: undefined,
      transforms: {
        enablePreloading: false,
        editable: false
      },
      enableStats: false
    },
    transforms: {},
    topics: {},
    layers: {
      // 默认显示一个 Grid 层
      'default-grid': {
        layerId: 'foxglove.Grid',
        label: 'Grid',
        visible: true,
        frameLocked: true,
        size: 10,
        divisions: 10,
        lineWidth: 1,
        color: '#4a4a6acc',
        position: [0, 0, 0],
        rotation: [0, 0, 0],
        order: 1
      } as any
    },
    connection: {
      rosUrl: 'ws://localhost:9090',
      autoConnect: false
    }
  }
}

/** 创建内置扩展注册表 */
function createExtensionConfig(): SceneExtensionConfig {
  return {
    extensionsById: {
      [SceneSettings.extensionId]: {
        init: (renderer) => new SceneSettings(renderer)
      },
      [Grids.extensionId]: {
        init: (renderer) => new Grids(renderer)
      },
      [FrameAxes.extensionId]: {
        init: (renderer) => new FrameAxes(renderer, {})
      },
      [Markers.extensionId]: {
        init: (renderer) => new Markers(renderer)
      },
      [LaserScans.extensionId]: {
        init: (renderer) => new LaserScans(renderer)
      },
      [Polygons.extensionId]: {
        init: (renderer) => new Polygons(renderer)
      },
      [OccupancyGrids.extensionId]: {
        init: (renderer) => new OccupancyGrids(renderer)
      },
      [PointClouds.extensionId]: {
        init: (renderer) => new PointClouds(renderer)
      },
      [Poses.extensionId]: {
        init: (renderer) => new Poses(renderer)
      },
      [PoseArrays.extensionId]: {
        init: (renderer) => new PoseArrays(renderer)
      },
      [PublishSettings.extensionId]: {
        init: (renderer) => new PublishSettings(renderer)
      }
    }
  }
}

// ============================================================
// 配置持久化（参照 lichtblick 的 initialState / saveState 模式）
// ============================================================

const STORAGE_KEY = 'ros3d-renderer-config'

/** 从 localStorage 读取已保存的配置 */
function loadSavedConfig(): Partial<RendererConfig> {
  try {
    const raw = localStorage.getItem(STORAGE_KEY)
    if (!raw) return {}
    return JSON.parse(raw) as Partial<RendererConfig>
  } catch {
    console.warn('[ROS3D] 读取持久化配置失败，使用默认值')
    return {}
  }
}

/**
 * 将已保存的配置与默认值深度合并
 * 等效于 lichtblick 的 _.merge(DEFAULT_CAMERA_STATE, partialConfig.cameraState)
 */
function mergeWithDefaults(
  defaults: RendererConfig,
  saved: Partial<RendererConfig>
): RendererConfig {
  return {
    ...defaults,
    ...saved,
    cameraState: { ...defaults.cameraState, ...(saved.cameraState ?? {}) },
    scene: { ...defaults.scene, ...(saved.scene ?? {}) },
    transforms: { ...defaults.transforms, ...(saved.transforms ?? {}) },
    topics: { ...defaults.topics, ...(saved.topics ?? {}) },
    layers: { ...defaults.layers, ...(saved.layers ?? {}) },
    connection: { ...defaults.connection, ...(saved.connection ?? {}) }
  }
}

/**
 * 防抖保存（500ms 延迟）
 * 等效于 lichtblick 的 useDebouncedCallback(saveState, 100, { maxWait: 1000 })
 */
let _saveTimer: ReturnType<typeof setTimeout> | null = null
function debouncedSave(config: Readonly<RendererConfig>): void {
  if (_saveTimer !== null) clearTimeout(_saveTimer)
  _saveTimer = setTimeout(() => {
    try {
      localStorage.setItem(STORAGE_KEY, JSON.stringify(config))
    } catch (e) {
      console.warn('[ROS3D] 配置保存失败:', e)
    }
    _saveTimer = null
  }, 500)
}

// ============================================================
// 发布回调类型
// ============================================================

export type OnPublishCallback = (
  topic: string,
  messageType: string,
  message: Record<string, unknown>
) => void

export function useRenderer(options?: { onPublish?: OnPublishCallback }) {
  const renderer = shallowRef<Renderer | null>(null)
  const sceneReady = ref(false)
  const settingsTreeVersion = ref(0)
  let maxRosTime = 0n

  // ── 时钟驱动器（对应 Lichtblick RosbridgePlayer 的 #emitTimer 机制）
  // clockTimeNs 是当前时间源（壁钟 或 /clock 仿真时间），单位 ns
  let clockTimeNs: bigint = BigInt(Date.now()) * 1_000_000n
  let useSimClock = false // 是否已切换到 /clock 仿真时间模式
  let clockTimer: ReturnType<typeof setInterval> | null = null

  /** 启动时钟定时器：每 100ms 推进一次 currentTime 并触发重渲染 */
  function startClock() {
    if (clockTimer != null) return
    clockTimer = setInterval(() => {
      if (!useSimClock) {
        // 壁钟模式：始终用 Date.now()
        clockTimeNs = BigInt(Date.now()) * 1_000_000n
      }
      // 不论何种时间源，都需要持续推进 renderer.currentTime
      renderer.value?.setCurrentTime(clockTimeNs)
      renderer.value?.queueAnimationFrame()
    }, 100)
  }

  /** 停止时钟定时器 */
  function stopClock() {
    if (clockTimer != null) {
      clearInterval(clockTimer)
      clockTimer = null
    }
    useSimClock = false
    clockTimeNs = BigInt(Date.now()) * 1_000_000n
  }

  /**
   * 挂载 Renderer 到目标 canvas 容器
   */
  function mount(container: HTMLElement) {
    if (renderer.value) {
      dispose()
    }

    // 创建 canvas
    const canvas = document.createElement('canvas')
    canvas.style.width = '100%'
    canvas.style.height = '100%'
    canvas.style.display = 'block'
    container.appendChild(canvas)

    // 加载持久化配置，与默认值合并（等效于 lichtblick 的 initialState 逻辑）
    const saved = loadSavedConfig()
    const config = mergeWithDefaults(defaultRendererConfig(), saved)

    const sceneExtensionConfig = createExtensionConfig()

    const r = new Renderer({
      canvas,
      config,
      sceneExtensionConfig
    })

    // 监听事件（使用 rAF 节流避免相机移动时的渲染风暴）
    let settingsUpdatePending = false
    r.on('settingsTreeChange', () => {
      if (!settingsUpdatePending) {
        settingsUpdatePending = true
        requestAnimationFrame(() => {
          settingsTreeVersion.value++
          settingsUpdatePending = false
        })
      }
    })

    // 监听 configChange 事件，防抖保存到 localStorage
    // 等效于 lichtblick 的 useRendererEvent('configChange', updateConfig) + throttledSave
    r.on('configChange', (changedRenderer) => {
      debouncedSave(changedRenderer.config as RendererConfig)
    })

    // 相机移动时触发重新渲染，并同步 cameraState 到 config（对等 Lichtblick ThreeDeeRender.tsx 第 209-233 行）
    // NOTE: getCameraState 在 follow-position/follow-none 模式下读取的是 OrbitControls 的局部偏移，
    //       setCameraState 重新应用是为了防止 non-follow-mode 下回放时出现闪烁（原注释中有说明）
    r.on('cameraMove', () => {
      const newCameraState = r.getCameraState()
      if (newCameraState) {
        // 与 Lichtblick 对等：先 setCameraState 再持久化，防止 non-follow-mode 播放闪烁
        r.setCameraState(newCameraState)
        // 将新 cameraState 写入 config 并防抖保存
        r.updateConfig((draft) => {
          draft.cameraState = newCameraState
        })
      }
      r.queueAnimationFrame()
    })

    // 设置默认颜色方案
    r.setColorScheme('dark', '#1e1e2e')

    renderer.value = r
    sceneReady.value = true

    // 渲染器就绪后立即启动时钟
    startClock()

    // 监听点击发布事件 → 通过外部回调发布 ROS 消息
    r.publishClickTool.addEventListener('foxglove.publish-submit', (event) => {
      const publish = r.config.publish
      if (!publish || !options?.onPublish) return

      const pub = options.onPublish
      const stamp = { secs: 0, nsecs: 0 }
      const frame_id = r.followFrameId ?? 'map'

      if (event.publishClickType === 'point') {
        pub(publish.pointTopic, 'geometry_msgs/PointStamped', {
          header: { stamp, frame_id },
          point: event.point
        })
      } else if (event.publishClickType === 'pose') {
        pub(publish.poseTopic, 'geometry_msgs/PoseStamped', {
          header: { stamp, frame_id },
          pose: event.pose
        })
      } else {
        // pose_estimate → geometry_msgs/PoseWithCovarianceStamped
        const {
          poseEstimateXDeviation: xDev,
          poseEstimateYDeviation: yDev,
          poseEstimateThetaDeviation: tDev
        } = publish
        // prettier-ignore
        const covariance = [
          xDev * xDev, 0, 0, 0, 0, 0,
          0, yDev * yDev, 0, 0, 0, 0,
          0, 0, 0, 0, 0, 0,
          0, 0, 0, 0, 0, 0,
          0, 0, 0, 0, 0, 0,
          0, 0, 0, 0, 0, tDev * tDev
        ]
        pub(publish.poseEstimateTopic, 'geometry_msgs/PoseWithCovarianceStamped', {
          header: { stamp, frame_id },
          pose: { pose: event.pose, covariance }
        })
      }
    })
  }

  /**
   * 销毁 Renderer 和 canvas
   */
  function dispose() {
    // 先停止时钟，再销毁 renderer
    stopClock()
    if (renderer.value) {
      const canvas = renderer.value.gl.domElement
      renderer.value.dispose()
      renderer.value = null
      sceneReady.value = false

      // 移除 canvas
      canvas.parentElement?.removeChild(canvas)
    }
  }

  /**
   * 添加消息事件（从 ROS 转发）
   *
   * 同时处理 /clock 消息以驱动仿真时钟模式（对应 Lichtblick RosbridgePlayer.#clockTime）。
   */
  function addMessageEvent(messageEvent: MessageEvent) {
    const msg = messageEvent.message as any

    // ── /clock 消息处理（优先级最高，切换到仿真时间模式）
    // rosgraph_msgs/Clock: { clock: { secs, nsecs } }
    if (messageEvent.topic === '/clock' && msg?.clock != null) {
      const c = msg.clock
      const sec = c.sec ?? c.secs ?? 0
      const nsec = c.nsec ?? c.nsecs ?? 0
      const simNs = BigInt(sec) * 1_000_000_000n + BigInt(nsec)
      if (!isNaN(sec)) {
        if (!useSimClock) {
          // 首次收到 /clock，切换到仿真时间模式
          console.info('[ROS3D] 检测到 /clock，切换到仿真时间模式')
          useSimClock = true
        }
        clockTimeNs = simNs
        renderer.value?.setCurrentTime(clockTimeNs)
      }
      // /clock 消息不需要走 schema 路由
      return
    }

    // ── 普通消息：提取 stamp 用于更新 maxRosTime（辅助 TF 时间对齐）
    let stamp: { sec?: number; secs?: number; nsec?: number; nsecs?: number } | undefined
    if (msg?.header?.stamp) {
      stamp = msg.header.stamp
    } else if (msg?.transforms?.[0]?.header?.stamp) {
      stamp = msg.transforms[0].header.stamp
    }

    if (stamp) {
      const sec = stamp.sec ?? stamp.secs
      const nsec = stamp.nsec ?? stamp.nsecs
      if (sec != null && nsec != null) {
        const timeNs = BigInt(sec) * 1_000_000_000n + BigInt(nsec)
        if (timeNs > maxRosTime) {
          maxRosTime = timeNs
        } else if (timeNs < maxRosTime - 1_000_000_000n) {
          // 时间大幅度倒流（如 Gazebo 重置），重置 maxRosTime
          maxRosTime = timeNs
        }
      }
    }

    // ── 关键修复：覆盖 receiveTime，使其与 clockTimeNs 在同一时间域
    // 调用方 (index.vue) 传入的 receiveTime 是 Date.now()（壁钟），
    // 但 currentTime 跟随 /clock（仿真时间），两者相差约 160000 倍，
    // 导致 decayTime 的比对 (receiveTime < currentTime - decayNs) 永远为 false。
    // 修复方式：统一用 clockTimeNs 作为 receiveTime，保证同尺度比对。
    const clockSec = Number(clockTimeNs / 1_000_000_000n)
    const clockNsec = Number(clockTimeNs % 1_000_000_000n)
    const normalizedEvent: MessageEvent = {
      ...messageEvent,
      receiveTime: { sec: clockSec, nsec: clockNsec }
    }

    renderer.value?.addMessageEvent(normalizedEvent)
    renderer.value?.queueAnimationFrame()
  }

  /**
   * 设置数据源 topics
   */
  function setTopics(topics: ReadonlyArray<Topic>) {
    renderer.value?.setTopics(topics)
  }

  /**
   * 设置当前时间
   */
  function setCurrentTime(timeNs: bigint) {
    renderer.value?.setCurrentTime(timeNs)
  }

  /**
   * 设置颜色方案
   */
  function setColorScheme(scheme: 'dark' | 'light', bg?: string) {
    renderer.value?.setColorScheme(scheme, bg)
  }

  /**
   * 获取相机状态
   */
  function getCameraState(): CameraState | undefined {
    return renderer.value?.getCameraState()
  }

  /**
   * 获取设置树（用于面板设置侧栏）
   */
  function getSettingsTree() {
    return renderer.value?.settings.tree()
  }

  /**
   * 处理设置 action
   */
  function handleSettingsAction(action: unknown) {
    renderer.value?.handleSettingsAction(action as any)
  }

  /**
   * 开始点击发布模式
   */
  function startPublish(type?: PublishClickType) {
    const r = renderer.value
    if (!r) return
    if (type) r.publishClickTool.setPublishClickType(type)
    r.publishClickTool.start()
  }

  /**
   * 停止点击发布模式
   */
  function stopPublish() {
    renderer.value?.publishClickTool.stop()
  }

  // 自动清理
  onBeforeUnmount(() => {
    dispose()
  })

  return {
    renderer,
    sceneReady,
    settingsTreeVersion,
    mount,
    dispose,
    addMessageEvent,
    setTopics,
    setCurrentTime,
    setColorScheme,
    getCameraState,
    getSettingsTree,
    handleSettingsAction,
    startPublish,
    stopPublish
  }
}
