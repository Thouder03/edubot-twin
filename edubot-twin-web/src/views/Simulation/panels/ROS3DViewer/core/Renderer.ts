// SPDX-License-Identifier: MPL-2.0
// Adapted from Lichtblick Renderer.ts — simplified for EduBot

import EventEmitter from 'eventemitter3'
import { produce } from 'immer'
import * as THREE from 'three'

import {
  ObjectPool,
  Logger,
  Immutable,
  MessageEvent,
  ParameterValue,
  SettingsIcon,
  SettingsTreeAction,
  SettingsTreeNodeActionItem,
  SettingsTreeNodes,
  Topic,
  VariableValue,
  HUDItemManager,
  HUDItem,
  LabelPool,
  ICameraHandler,
  CameraModelsMap,
  RosTime,
  toNanoSec,
  palette,
  Asset,
  t
} from './lichtblick-shim'

import {
  IRenderer,
  InstancedLineMaterial,
  RendererConfig,
  RendererEvents,
  RendererSubscription,
  TestOptions
} from './IRenderer'
import { Input } from './Input'
import { DEFAULT_MESH_UP_AXIS, ModelCache } from './ModelCache'
import { Picker } from './Picker'
import { SceneExtension } from './SceneExtension'
import { SceneExtensionConfig } from './SceneExtensionConfig'
import { ScreenOverlay } from './ScreenOverlay'
import { SettingsManager } from './SettingsManager'
import { SharedGeometry } from './SharedGeometry'
import { CameraState } from './camera'
import { DARK_OUTLINE, LIGHT_OUTLINE, stringToRgb } from './color'
import { FRAME_TRANSFORMS_DATATYPES, FRAME_TRANSFORM_DATATYPES } from './foxglove'
import { DetailLevel } from './lod'
import {
  normalizeFrameTransform,
  normalizeFrameTransforms,
  normalizeTFMessage,
  normalizeTransformStamped
} from './normalizeMessages'
import { CameraStateSettings } from './CameraStateSettings'
import { Quaternion, TF_DATATYPES, TRANSFORM_STAMPED_DATATYPES, Vector3 } from './ros'
import { SelectEntry } from './settings'
import { AddTransformResult, CoordinateFrame, TransformTree, Transform } from './transforms'
import { InterfaceMode } from './types'
import { PublishClickTool } from '../extensions/PublishClickTool'

const log = Logger.getLogger('Renderer')

/** Menu item entry and callback for the "Custom Layers" menu */
export type CustomLayerAction = {
  action: SettingsTreeNodeActionItem
  handler: (instanceId: string) => void
}

const LIGHT_BACKDROP = new THREE.Color(palette.light.background?.default)
const DARK_BACKDROP = new THREE.Color(palette.dark.background?.default)

const FOLLOW_TF_PATH = ['general', 'followTf']
const CYCLE_DETECTED = 'CYCLE_DETECTED'

const RENDERER_ID = 'foxglove.Renderer'

const tempColor = new THREE.Color()
const tempVec2 = new THREE.Vector2()

/**
 * An extensible 3D renderer attached to a `HTMLCanvasElement`.
 * Simplified from Lichtblick, removing ImageMode/MeasurementTool.
 */
export class Renderer extends EventEmitter<RendererEvents> implements IRenderer {
  public readonly interfaceMode: InterfaceMode = '3d'
  #canvas: HTMLCanvasElement
  public readonly gl: THREE.WebGLRenderer
  public maxLod = DetailLevel.High

  public customCameraModels: CameraModelsMap = new Map()

  public debugPicking: boolean
  public config: Immutable<RendererConfig>
  public settings: SettingsManager
  public topics: ReadonlyArray<Topic> | undefined
  public topicsByName: ReadonlyMap<string, Topic> | undefined
  public parameters: ReadonlyMap<string, ParameterValue> | undefined
  public variables: ReadonlyMap<string, VariableValue> = new Map()
  public sceneExtensions = new Map<string, SceneExtension>()
  public schemaSubscriptions = new Map<string, RendererSubscription[]>()
  public topicSubscriptions = new Map<string, RendererSubscription[]>()

  public hud: HUDItemManager
  public hudItems: HUDItem[] = []
  #customLayerActions = new Map<string, CustomLayerAction>()
  #scene: THREE.Scene
  #dirLight: THREE.DirectionalLight
  #hemiLight: THREE.HemisphereLight
  public input: Input
  public readonly outlineMaterial = new THREE.LineBasicMaterial({ dithering: true })
  public readonly instancedOutlineMaterial = new InstancedLineMaterial({ dithering: true })

  public cameraHandler: ICameraHandler

  public ros = false

  /** 点击发布工具（供 PublishSettings 和外部 UI 使用） */
  public publishClickTool!: PublishClickTool

  #picker: Picker
  #selectionBackdropScene: THREE.Scene
  #selectionBackdrop: ScreenOverlay
  public colorScheme: 'dark' | 'light' = 'light'
  public modelCache: ModelCache

  #transformPool = new ObjectPool(Transform.Empty)
  public transformTree = new TransformTree(this.#transformPool)

  public coordinateFrameList: SelectEntry[] = []
  public currentTime = 0n
  public fixedFrameId: string | undefined
  public followFrameId: string | undefined

  public labelPool = new LabelPool()
  public sharedGeometry = new SharedGeometry()

  #pickingEnabled = false
  #rendering = false
  #animationFrame?: number
  #cameraSyncError: undefined | string
  #devicePixelRatioMediaQuery?: MediaQueryList

  public readonly displayTemporaryError?: (str: string) => void
  public readonly testOptions: TestOptions

  public constructor(args: {
    canvas: HTMLCanvasElement
    config: Immutable<RendererConfig>
    sceneExtensionConfig: SceneExtensionConfig
    displayTemporaryError?: (message: string) => void
    testOptions?: TestOptions
  }) {
    super()
    this.displayTemporaryError = args.displayTemporaryError
    THREE.Object3D.DEFAULT_UP = new THREE.Vector3(0, 0, 1)

    const canvas = (this.#canvas = args.canvas)
    const config = (this.config = args.config)
    this.testOptions = args.testOptions ?? {}
    this.debugPicking = this.testOptions.debugPicking ?? false

    this.hud = new HUDItemManager(() => {
      this.hudItems = this.hud.getHUDItems()
      this.emit('hudItemsChanged', this)
    })

    this.settings = new SettingsManager(baseSettingsTree())
    this.settings.on('update', () => this.emit('settingsTreeChange', this))
    this.settings.setNodesForKey(RENDERER_ID, [])
    this.updateCustomLayersCount()

    this.gl = new THREE.WebGLRenderer({
      canvas,
      alpha: true,
      antialias: true
    })
    if (!this.gl.capabilities.isWebGL2) {
      throw new Error('WebGL2 is not supported')
    }
    this.gl.toneMapping = THREE.NoToneMapping
    this.gl.autoClear = false
    this.gl.info.autoReset = false
    this.gl.shadowMap.enabled = false
    this.gl.shadowMap.type = THREE.VSMShadowMap
    this.gl.sortObjects = true
    this.gl.setPixelRatio(window.devicePixelRatio)

    let width = canvas.width
    let height = canvas.height
    if (canvas.parentElement) {
      width = canvas.parentElement.clientWidth
      height = canvas.parentElement.clientHeight
      this.gl.setSize(width, height)
    }

    this.modelCache = new ModelCache({
      ignoreColladaUpAxis: config.scene.ignoreColladaUpAxis ?? false,
      meshUpAxis: config.scene.meshUpAxis ?? DEFAULT_MESH_UP_AXIS,
      edgeMaterial: this.outlineMaterial,
      fetchAsset: async (url: string): Promise<Asset> => {
        const response = await fetch(url)
        const data = new Uint8Array(await response.arrayBuffer())
        return { uri: url, data }
      }
    })

    this.#scene = new THREE.Scene()

    this.#dirLight = new THREE.DirectionalLight(0xffffff, Math.PI)
    this.#dirLight.position.set(1, 1, 1)
    this.#dirLight.castShadow = true
    this.#dirLight.layers.enableAll()

    this.#dirLight.shadow.mapSize.width = 2048
    this.#dirLight.shadow.mapSize.height = 2048
    this.#dirLight.shadow.camera.near = 0.5
    this.#dirLight.shadow.camera.far = 500
    this.#dirLight.shadow.bias = -0.00001

    this.#hemiLight = new THREE.HemisphereLight(0xffffff, 0xffffff, 0.5 * Math.PI)
    this.#hemiLight.layers.enableAll()

    this.#scene.add(this.#dirLight)
    this.#scene.add(this.#hemiLight)

    this.input = new Input(canvas, () => this.cameraHandler.getActiveCamera())
    this.input.on('resize', (size) => this.#resizeHandler(size))
    this.input.on('click', (cursorCoords) => this.#clickHandler(cursorCoords))

    this.#picker = new Picker(this.gl, this.#scene)

    this.#selectionBackdrop = new ScreenOverlay(this as unknown as IRenderer)
    this.#selectionBackdropScene = new THREE.Scene()
    this.#selectionBackdropScene.add(this.#selectionBackdrop)

    const renderSize = this.gl.getDrawingBufferSize(tempVec2)
    const aspect = renderSize.width / renderSize.height

    // Always 3D mode — use CameraStateSettings
    this.cameraHandler = new CameraStateSettings(this as unknown as IRenderer, this.#canvas, aspect)
    this.#addSceneExtension(this.cameraHandler as unknown as SceneExtension)

    // 先初始化 PublishClickTool，确保后续所有依赖它的扩展（如 PublishSettings）构造时可用
    this.publishClickTool = new PublishClickTool(this as unknown as IRenderer)
    this.#addSceneExtension(this.publishClickTool)

    // Register all scene extensions from config
    const { extensionsById } = args.sceneExtensionConfig
    for (const extensionItem of Object.values(extensionsById)) {
      this.#addSceneExtension(extensionItem.init(this as unknown as IRenderer))
    }

    log.debug(
      `Renderer initialized with extensions: ${Array.from(this.sceneExtensions.keys()).join(', ')}`
    )

    this.#addTransformSubscriptions()
    this.#addSubscriptionsFromSceneExtensions()

    this.#watchDevicePixelRatio()
    this.setCameraState(config.cameraState)
    this.animationFrame()
  }

  // --- IRenderer: setFollowFrameId ---

  public setFollowFrameId(frameId: string | undefined): void {
    if (this.followFrameId === frameId) return
    this.followFrameId = frameId
    if (frameId) {
      const frame = this.transformTree.frame(frameId)
      if (frame) {
        this.fixedFrameId = frame.root().id as string | undefined
      }
    }
    this.updateConfig((draft) => {
      draft.followTf = frameId
    })
    this.emit('transformTreeUpdated', this)
  }

  #onDevicePixelRatioChange = () => {
    this.#resizeHandler(this.input.canvasSize)
    this.#watchDevicePixelRatio()
  }

  #watchDevicePixelRatio() {
    this.#devicePixelRatioMediaQuery = window.matchMedia(
      `(resolution: ${window.devicePixelRatio}dppx)`
    )
    this.#devicePixelRatioMediaQuery.addEventListener('change', this.#onDevicePixelRatioChange, {
      once: true
    })
  }

  public dispose(): void {
    log.warn('Disposing renderer')
    this.#devicePixelRatioMediaQuery?.removeEventListener('change', this.#onDevicePixelRatioChange)
    this.removeAllListeners()
    this.settings.removeAllListeners()
    this.input.removeAllListeners()

    for (const extension of this.sceneExtensions.values()) {
      extension.dispose()
    }
    this.sceneExtensions.clear()
    this.sharedGeometry.dispose()
    this.modelCache.dispose()
    this.labelPool.dispose()
    this.#picker.dispose()
    this.input.dispose()
    this.gl.dispose()
  }

  public cameraSyncError(): undefined | string {
    return this.#cameraSyncError
  }

  public setCameraSyncError(error: undefined | string): void {
    this.#cameraSyncError = error
    this.cameraHandler.updateSettingsTree()
  }

  public getPixelRatio(): number {
    return this.gl.getPixelRatio()
  }

  public setCurrentTime(newTimeNs: bigint): void {
    this.currentTime = newTimeNs
  }

  public handleSeek(oldTimeNs: bigint): void {
    const movedBack = this.currentTime < oldTimeNs
    this.clear({ clearTransforms: movedBack })
  }

  public clear(
    { clearTransforms }: { clearTransforms?: boolean } = { clearTransforms: false }
  ): void {
    if (clearTransforms === true) {
      this.#clearTransformTree()
    }
    this.settings.errors.clear()
    this.hud.removeAll()

    for (const extension of this.sceneExtensions.values()) {
      extension.removeAllRenderables()
    }
    this.queueAnimationFrame()
  }

  #clearTransformTree = () => {
    this.transformTree.clear()
  }

  #addSceneExtension(extension: SceneExtension): void {
    if (this.sceneExtensions.has(extension.extensionId)) {
      throw new Error(`Attempted to add duplicate extensionId "${extension.extensionId}"`)
    }
    this.sceneExtensions.set(extension.extensionId, extension)
    this.#scene.add(extension)
  }

  public updateConfig(updateHandler: (draft: RendererConfig) => void): void {
    this.config = produce(this.config, updateHandler)
    this.emit('configChange', this)
  }

  #addTransformSubscriptions(): void {
    const config = this.config
    const preloadTransforms = config.scene.transforms?.enablePreloading ?? false
    this.#addSchemaSubscriptions(FRAME_TRANSFORM_DATATYPES, {
      handler: this.#handleFrameTransform,
      preload: preloadTransforms
    })
    this.#addSchemaSubscriptions(FRAME_TRANSFORMS_DATATYPES, {
      handler: this.#handleFrameTransforms,
      preload: preloadTransforms
    })
    this.#addSchemaSubscriptions(TF_DATATYPES, {
      handler: this.#handleTFMessage,
      preload: preloadTransforms
    })
    this.#addSchemaSubscriptions(TRANSFORM_STAMPED_DATATYPES, {
      handler: this.#handleTransformStamped,
      preload: preloadTransforms
    })
  }

  #addSubscriptionsFromSceneExtensions(filterFn?: (extension: SceneExtension) => boolean): void {
    const filteredExtensions = filterFn
      ? Array.from(this.sceneExtensions.values()).filter(filterFn)
      : this.sceneExtensions.values()
    for (const extension of filteredExtensions) {
      const subscriptions = extension.getSubscriptions()
      for (const subscription of subscriptions) {
        switch (subscription.type) {
          case 'schema':
            this.#addSchemaSubscriptions(
              subscription.schemaNames,
              subscription.subscription as RendererSubscription
            )
            break
          case 'topic':
            this.#addTopicSubscription(
              subscription.topicName,
              subscription.subscription as RendererSubscription
            )
            break
        }
      }
    }
  }

  #addSchemaSubscriptions<T>(
    schemaNames: Iterable<string>,
    subscription: RendererSubscription<T>
  ): void {
    for (const schemaName of schemaNames) {
      let handlers = this.schemaSubscriptions.get(schemaName)
      if (!handlers) {
        handlers = []
        this.schemaSubscriptions.set(schemaName, handlers)
      }
      handlers.push(subscription as RendererSubscription)
    }
    this.emit('schemaSubscriptionsChanged', this)
  }

  #addTopicSubscription<T>(topic: string, subscription: RendererSubscription<T>): void {
    let handlers = this.topicSubscriptions.get(topic)
    if (!handlers) {
      handlers = []
      this.topicSubscriptions.set(topic, handlers)
    }
    handlers.push(subscription as RendererSubscription)
    this.emit('topicSubscriptionsChanged', this)
  }

  public addCustomLayerAction(options: {
    layerId: string
    label: string
    icon?: SettingsIcon
    handler: (instanceId: string) => void
  }): void {
    const handler = options.handler
    const action: SettingsTreeNodeActionItem = {
      type: 'action',
      id: `add-${options.layerId}`,
      label: options.label,
      icon: options.icon
    }
    this.#customLayerActions.set(options.layerId, { action, handler })
    this.updateCustomLayersCount()
  }

  public updateCustomLayersCount(): void {
    const layerCount = Object.keys(this.config.layers).length
    const actions = Array.from(this.#customLayerActions.values(), (entry) => entry.action)
    this.settings.setNodesForKey(RENDERER_ID, [
      {
        path: ['topics'],
        node: {
          label: t('threeDee:topics'),
          children: this.settings.tree()['topics']?.children
        }
      },
      {
        path: ['layers'],
        node: {
          label: `${t('threeDee:customLayers')}${layerCount > 0 ? ` (${layerCount})` : ''}`,
          children: this.settings.tree()['layers']?.children,
          actions
        }
      }
    ])
  }

  public addMessageEvent(messageEvent: Readonly<MessageEvent>): void {
    const { schemaName, topic } = messageEvent

    // Schema-based handlers
    const schemaHandlers = this.schemaSubscriptions.get(schemaName)
    if (schemaHandlers) {
      for (const handler of schemaHandlers) {
        const shouldSubscribe = handler.shouldSubscribe
        if (!shouldSubscribe || shouldSubscribe(topic)) {
          if (handler.preload) {
            handler.queue ??= []
            handler.queue.push(messageEvent)
          } else {
            handler.handler(messageEvent)
          }
        }
      }
    }

    // Topic-based handlers
    const topicHandlers = this.topicSubscriptions.get(topic)
    if (topicHandlers) {
      for (const handler of topicHandlers) {
        const shouldSubscribe = handler.shouldSubscribe
        if (!shouldSubscribe || shouldSubscribe(topic)) {
          if (handler.preload) {
            handler.queue ??= []
            handler.queue.push(messageEvent)
          } else {
            handler.handler(messageEvent)
          }
        }
      }
    }
  }

  /** Set topics from the data source */
  public setTopics(topics: ReadonlyArray<Topic> | undefined): void {
    this.topics = topics
    if (topics) {
      this.topicsByName = new Map(topics.map((t) => [t.name, t]))
    }
    this.emit('topicsChanged', this)

    // Rebuild the settings nodes for all scene extensions
    for (const extension of this.sceneExtensions.values()) {
      this.settings.setNodesForKey(extension.extensionId, extension.settingsNodes())
    }
  }

  /** Set parameters from the data source */
  public setParameters(parameters: ReadonlyMap<string, ParameterValue>): void {
    this.parameters = parameters
    this.emit('parametersChange', parameters, this)
  }

  /** Set variables */
  public setVariables(variables: ReadonlyMap<string, VariableValue>): void {
    this.variables = variables
  }

  public setColorScheme(colorScheme: 'dark' | 'light', backgroundColor?: string): void {
    this.colorScheme = colorScheme

    const bgColor = backgroundColor
      ? (stringToRgb(tempColor, backgroundColor) ??
        tempColor.set(colorScheme === 'dark' ? DARK_BACKDROP : LIGHT_BACKDROP))
      : colorScheme === 'dark'
        ? DARK_BACKDROP
        : LIGHT_BACKDROP

    this.#scene.background = bgColor.clone()
    this.outlineMaterial.color.set(colorScheme === 'dark' ? DARK_OUTLINE : LIGHT_OUTLINE)
    this.instancedOutlineMaterial.color.set(colorScheme === 'dark' ? DARK_OUTLINE : LIGHT_OUTLINE)

    this.queueAnimationFrame()
  }

  /** Set the camera state */
  public setCameraState(cameraState: CameraState): void {
    // Delegate to camera handler
    ;(this.cameraHandler as CameraStateSettings).setCameraState?.(cameraState)
  }

  public getCameraState(): CameraState | undefined {
    return (this.cameraHandler as CameraStateSettings).getCameraState?.()
  }

  /** Add a single transform to the transform tree */
  public addTransform(
    frameId: string,
    parentFrameId: string,
    stampNs: bigint,
    translation: Vector3,
    rotation: Quaternion,
    _receiveTime: bigint
  ): void {
    const normalizedFrameId = this.ros ? normalizeFrameId(frameId) : frameId
    const normalizedParentId = this.ros ? normalizeFrameId(parentFrameId) : parentFrameId

    const transform = this.#transformPool.acquire()
    transform.setPositionRotation(
      [translation.x, translation.y, translation.z],
      [rotation.x, rotation.y, rotation.z, rotation.w]
    )

    const result = this.transformTree.addTransform(
      normalizedFrameId,
      normalizedParentId,
      stampNs,
      transform
    )

    if (result === AddTransformResult.CYCLE_DETECTED) {
      this.settings.errors.add(
        FOLLOW_TF_PATH,
        CYCLE_DETECTED,
        `Cycle detected: ${normalizedFrameId} → ${normalizedParentId}`
      )
    } else if (result === AddTransformResult.UPDATED) {
      this.coordinateFrameList = this.transformTree.frameList()
      this.emit('transformTreeUpdated', this)

      if (!this.followFrameId) {
        const defaultFollowFrame = this.transformTree.getDefaultFollowFrameId()
        if (defaultFollowFrame) {
          this.followFrameId = defaultFollowFrame
          this.fixedFrameId = this.transformTree.frame(defaultFollowFrame)?.root().id as
            | string
            | undefined
        }
      }
    }
  }

  // --- Render Loop ---

  public queueAnimationFrame(): void {
    if (!this.#animationFrame) {
      this.#animationFrame = requestAnimationFrame(() => this.animationFrame())
    }
  }

  public animationFrame = (): void => {
    this.#animationFrame = undefined
    if (this.#rendering) return
    this.#rendering = true

    try {
      this.#frameHandler()
    } finally {
      this.#rendering = false
    }
  }

  #frameHandler(): void {
    const camera = this.cameraHandler.getActiveCamera()
    const renderFrameId = this.followFrameId ?? CoordinateFrame.FALLBACK_FRAME_ID
    const fixedFrameId = this.fixedFrameId ?? CoordinateFrame.FALLBACK_FRAME_ID

    // Call startFrame on all extensions
    for (const extension of this.sceneExtensions.values()) {
      try {
        extension.startFrame(this.currentTime, renderFrameId, fixedFrameId)
      } catch (err) {
        log.error(`Error in ${extension.extensionId}.startFrame():`, err)
      }
    }

    // Render the main scene
    this.gl.getDrawingBufferSize(tempVec2)
    this.gl.clear()
    this.gl.render(this.#scene, camera)
    this.gl.info.reset()
  }

  #resizeHandler(size: THREE.Vector2): void {
    const resolution = window.devicePixelRatio
    this.gl.setPixelRatio(resolution)
    this.gl.setSize(size.width, size.height)
    this.cameraHandler.handleResize(size.width, size.height, resolution)
    this.queueAnimationFrame()
  }

  #clickHandler(cursorCoords: THREE.Vector2): void {
    if (!this.#pickingEnabled) return

    const camera = this.cameraHandler.getActiveCamera()
    const objectId = this.#picker.pick(cursorCoords.x, cursorCoords.y, camera)

    if (objectId !== 0 && objectId !== 0xffffffff) {
      void objectId
      // Emit as number; consumers resolve to PickedRenderable
      this.emit('selectedRenderable', this, objectId as unknown as undefined)
    } else {
      this.emit('selectedRenderable', this, undefined)
    }
  }

  public enablePicking(enable: boolean): void {
    this.#pickingEnabled = enable
  }

  // --- TF Message Handlers ---

  #handleFrameTransform = (messageEvent: MessageEvent): void => {
    const msg = normalizeFrameTransform(messageEvent.message as Record<string, unknown>)
    if (!msg) return

    const stampNs = toNanoSec(msg.timestamp as RosTime)
    const receiveNs = toNanoSec(messageEvent.receiveTime as RosTime)
    this.addTransform(
      msg.child_frame_id,
      msg.parent_frame_id,
      stampNs,
      msg.translation,
      msg.rotation,
      receiveNs
    )
  }

  #handleFrameTransforms = (messageEvent: MessageEvent): void => {
    const msg = normalizeFrameTransforms(messageEvent.message as Record<string, unknown>)
    if (!msg) return

    for (const transform of msg.transforms) {
      const stampNs = toNanoSec(transform.timestamp as RosTime)
      const receiveNs = toNanoSec(messageEvent.receiveTime as RosTime)
      this.addTransform(
        transform.child_frame_id,
        transform.parent_frame_id,
        stampNs,
        transform.translation,
        transform.rotation,
        receiveNs
      )
    }
  }

  #handleTFMessage = (messageEvent: MessageEvent): void => {
    const msg = normalizeTFMessage(messageEvent.message as Record<string, unknown>)
    if (!msg) return

    for (const tf of msg.transforms) {
      const stampNs = toNanoSec(tf.header.stamp as RosTime)
      const receiveNs = toNanoSec(messageEvent.receiveTime as RosTime)
      this.addTransform(
        tf.child_frame_id,
        tf.header.frame_id,
        stampNs,
        tf.transform.translation,
        tf.transform.rotation,
        receiveNs
      )
    }
  }

  #handleTransformStamped = (messageEvent: MessageEvent): void => {
    const msg = normalizeTransformStamped(messageEvent.message as Record<string, unknown>)
    if (!msg) return

    const stampNs = toNanoSec(msg.header.stamp as RosTime)
    const receiveNs = toNanoSec(messageEvent.receiveTime as RosTime)
    this.addTransform(
      msg.child_frame_id,
      msg.header.frame_id,
      stampNs,
      msg.transform.translation,
      msg.transform.rotation,
      receiveNs
    )
  }

  // --- Settings Action Handler ---

  public handleSettingsAction = (action: SettingsTreeAction): void => {
    const path = action.payload.path
    if (!path) return

    // Check custom layer actions
    if (path[0] === 'layers' && action.action === 'perform-node-action') {
      const actionId = (action.payload as { id?: string }).id
      if (actionId) {
        for (const [, entry] of this.#customLayerActions) {
          if (entry.action.id === actionId) {
            const instanceId = `${entry.action.id}-${Date.now()}`
            entry.handler(instanceId)
            return
          }
        }
      }
    }

    // Delegate to settings manager which walks the tree and fires handlers
    this.settings.handleAction(action)
  }

  /** Normalize a ROS frame ID by removing any leading "/" prefix */
  public normalizeFrameId(frameId: string): string {
    return this.ros ? (frameId.startsWith('/') ? frameId.slice(1) : frameId) : frameId
  }
}

// --- Helper functions ---

/** Normalize a ROS frame ID by removing any leading "/" prefix */
function normalizeFrameId(frameId: string): string {
  return frameId.startsWith('/') ? frameId.slice(1) : frameId
}

/** Build the base settings tree */
function baseSettingsTree(): SettingsTreeNodes {
  return {
    general: {
      label: t('threeDee:frame'),
      icon: 'Settings',
      fields: {
        followTf: {
          label: t('threeDee:displayFrame'),
          input: 'autocomplete',
          value: ''
        }
      }
    }
  }
}
