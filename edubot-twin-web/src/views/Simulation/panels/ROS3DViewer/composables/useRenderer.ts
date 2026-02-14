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
    layers: {}
  }
}

/** 创建内置扩展注册表 */
function createExtensionConfig(): SceneExtensionConfig {
  return {
    extensionsById: {
      [SceneSettings.extensionId]: {
        init: (renderer) => new SceneSettings(renderer)
      }
    }
  }
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

    const config = defaultRendererConfig()
    const sceneExtensionConfig = createExtensionConfig()

    const r = new Renderer({
      canvas,
      config,
      sceneExtensionConfig
    })

    // 监听事件
    r.on('settingsTreeChange', () => {
      settingsTreeVersion.value++
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
