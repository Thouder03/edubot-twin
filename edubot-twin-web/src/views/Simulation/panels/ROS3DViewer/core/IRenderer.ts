// SPDX-License-Identifier: MPL-2.0
// Adapted from Lichtblick IRenderer.ts — simplified for EduBot

import EventEmitter from 'eventemitter3'
import * as THREE from 'three'

import {
  Immutable,
  MessageEvent,
  ParameterValue,
  SettingsIcon,
  Topic,
  VariableValue,
  HUDItemManager,
  HUDItem,
  LabelPool,
  ICameraHandler
} from './lichtblick-shim'

import { Input } from './Input'
import { MeshUpAxis, ModelCache } from './ModelCache'
import { PickedRenderable } from './Picker'
import { SceneExtension } from './SceneExtension'
import { SettingsManager } from './SettingsManager'
import { SharedGeometry } from './SharedGeometry'
import { CameraState } from './camera'
import { DetailLevel } from './lod'
import { Quaternion, Vector3 } from './ros'
import { BaseSettings, CustomLayerSettings, SelectEntry } from './settings'
import { TransformTree } from './transforms'
import { InterfaceMode } from './types'

export type RendererEvents = {
  startFrame: (currentTime: bigint, renderer: IRenderer) => void
  endFrame: (currentTime: bigint, renderer: IRenderer) => void
  cameraMove: (renderer: IRenderer) => void
  renderablesClicked: (
    selections: PickedRenderable[],
    cursorCoords: { x: number; y: number },
    renderer: IRenderer
  ) => void
  selectedRenderable: (renderer: IRenderer, selection: PickedRenderable | undefined) => void
  parametersChange: (
    parameters: ReadonlyMap<string, ParameterValue> | undefined,
    renderer: IRenderer
  ) => void
  transformTreeUpdated: (renderer: IRenderer) => void
  settingsTreeChange: (renderer: IRenderer) => void
  configChange: (renderer: IRenderer) => void
  schemaSubscriptionsChanged: (renderer: IRenderer) => void
  topicSubscriptionsChanged: (renderer: IRenderer) => void
  topicsChanged: (renderer: IRenderer) => void
  resetViewChanged: (renderer: IRenderer) => void
  hudItemsChanged: (renderer: IRenderer) => void
}

export type FollowMode = 'follow-pose' | 'follow-position' | 'follow-none'

export type TestOptions = {
  onDownloadImage?: (blob: Blob, fileName: string) => void
  debugPicking?: boolean
}

export type RendererConfig = {
  cameraState: CameraState
  followTf: string | undefined
  followMode: FollowMode
  scene: {
    enableStats?: boolean
    backgroundColor?: string
    labelScaleFactor?: number
    ignoreColladaUpAxis?: boolean
    meshUpAxis?: MeshUpAxis
    transforms?: {
      editable?: boolean
      showLabel?: boolean
      labelSize?: number
      axisScale?: number
      lineWidth?: number
      lineColor?: string
      enablePreloading?: boolean
    }
    syncCamera?: boolean
    topicsVisible?: boolean
  }
  /** frameId -> settings */
  transforms: Record<string, Partial<BaseSettings> | undefined>
  /** topicName -> settings */
  topics: Record<string, Partial<BaseSettings> | undefined>
  /** instanceId -> settings */
  layers: Record<string, Partial<CustomLayerSettings> | undefined>
  /** 面板级连接配置（ROS WebSocket） */
  connection?: {
    rosUrl?: string
    autoConnect?: boolean
  }
}

export type RendererSubscription<T = unknown> = {
  preload?: boolean
  shouldSubscribe?: (topic: string) => boolean
  handler: (messageEvent: MessageEvent<T>) => void
  queue?: MessageEvent<T>[] | undefined
  filterQueue?: (queue: MessageEvent<T>[]) => MessageEvent<T>[]
}

export type AnyRendererSubscription = Immutable<
  | {
      type: 'schema'
      schemaNames: Set<string>
      subscription: RendererSubscription<unknown>
    }
  | {
      type: 'topic'
      topicName: string
      subscription: RendererSubscription<unknown>
    }
>

export class InstancedLineMaterial extends THREE.LineBasicMaterial {
  public constructor(...args: ConstructorParameters<typeof THREE.LineBasicMaterial>) {
    super(...args)
    this.defines ??= {}
    this.defines.USE_INSTANCING = true
  }
}

export interface IRenderer extends EventEmitter<RendererEvents> {
  readonly interfaceMode: InterfaceMode
  readonly gl: THREE.WebGLRenderer
  readonly testOptions: TestOptions
  maxLod: DetailLevel
  config: Immutable<RendererConfig>
  settings: SettingsManager
  hud: HUDItemManager
  debugPicking: boolean
  topics: ReadonlyArray<Topic> | undefined
  topicsByName: ReadonlyMap<string, Topic> | undefined
  parameters: ReadonlyMap<string, ParameterValue> | undefined
  variables: ReadonlyMap<string, VariableValue>
  sceneExtensions: Map<string, SceneExtension>
  schemaSubscriptions: Map<string, RendererSubscription[]>
  topicSubscriptions: Map<string, RendererSubscription[]>
  input: Input
  readonly outlineMaterial: THREE.LineBasicMaterial
  readonly instancedOutlineMaterial: InstancedLineMaterial
  cameraHandler: ICameraHandler
  ros: boolean
  colorScheme: 'dark' | 'light'
  modelCache: ModelCache
  transformTree: TransformTree
  coordinateFrameList: SelectEntry[]
  currentTime: bigint
  fixedFrameId: string | undefined
  readonly followFrameId: string | undefined
  labelPool: LabelPool
  sharedGeometry: SharedGeometry
  hudItems: HUDItem[]
  displayTemporaryError?: (message: string) => void

  dispose(): void
  cameraSyncError(): undefined | string
  setCameraSyncError(error: undefined | string): void
  getPixelRatio(): number
  setCurrentTime(newTimeNs: bigint): void
  handleSeek(oldTimeNs: bigint): void
  clear(args?: { clearTransforms?: boolean }): void
  updateConfig(updateHandler: (draft: RendererConfig) => void): void
  addCustomLayerAction(options: {
    layerId: string
    label: string
    icon?: SettingsIcon
    handler: (instanceId: string) => void
  }): void
  setColorScheme(colorScheme: 'dark' | 'light', backgroundColor: string | undefined): void
  setTopics(topics: ReadonlyArray<Topic> | undefined): void
  setParameters(parameters: ReadonlyMap<string, ParameterValue>): void
  updateCustomLayersCount(): void
  setCameraState(cameraState: CameraState): void
  getCameraState(): CameraState | undefined
  addMessageEvent(messageEvent: Readonly<MessageEvent>): void
  addTransform(
    frameId: string,
    parentFrameId: string,
    stampNs: bigint,
    translation: Vector3,
    rotation: Quaternion,
    receiveTime: bigint
  ): void
  setFollowFrameId(frameId: string | undefined): void
  animationFrame: () => void
  queueAnimationFrame: () => void
}
