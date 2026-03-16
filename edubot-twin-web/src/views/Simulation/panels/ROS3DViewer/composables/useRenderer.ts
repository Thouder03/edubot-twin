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

export function useRenderer() {
  const renderer = shallowRef<Renderer | null>(null)
  const sceneReady = ref(false)
  const settingsTreeVersion = ref(0)

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

    // 相机移动时触发重新渲染
    r.on('cameraMove', () => {
      r.queueAnimationFrame()
    })

    // 设置默认颜色方案
    r.setColorScheme('dark', '#1e1e2e')

    renderer.value = r
    sceneReady.value = true
  }

  /**
   * 销毁 Renderer 和 canvas
   */
  function dispose() {
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
   */
  function addMessageEvent(messageEvent: MessageEvent) {
    renderer.value?.addMessageEvent(messageEvent)
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
    handleSettingsAction
  }
}
