// SPDX-License-Identifier: MPL-2.0
// Poses SceneExtension — 渲染 geometry_msgs/PoseStamped 和 PoseWithCovarianceStamped

import * as THREE from 'three'

import { SettingsTreeAction } from '../core/lichtblick-shim'
import type { AnyRendererSubscription, IRenderer } from '../core/IRenderer'
import { Renderable, BaseUserData } from '../core/Renderable'
import {
  PartialMessage,
  PartialMessageEvent,
  SceneExtension,
  onlyLastByTopicMessage
} from '../core/SceneExtension'
import type { SettingsTreeEntry } from '../core/SettingsManager'
import { makeRgba, rgbaToCssString, stringToRgba } from '../core/color'
import { normalizeHeader, normalizePose, normalizeMatrix6 } from '../core/normalizeMessages'
import {
  Marker,
  MarkerType,
  MarkerAction,
  PoseStamped,
  PoseWithCovarianceStamped,
  PoseWithCovariance,
  ColorRGBA,
  POSE_STAMPED_DATATYPES,
  POSE_WITH_COVARIANCE_STAMPED_DATATYPES,
  TIME_ZERO
} from '../core/ros'
import { BaseSettings, fieldSize, fieldScaleVec3 } from '../core/settings'
import { makePose } from '../core/transforms'
import type { RosValue } from '../core/lichtblick-shim'
import { Axis, AXIS_LENGTH } from './Axis'
import { RenderableArrow } from './markers/RenderableArrow'
import { RenderableSphere } from './markers/RenderableSphere'

// ============================================================
// 类型定义
// ============================================================

type DisplayType = 'axis' | 'arrow'

export type LayerSettingsPose = BaseSettings & {
  type: DisplayType
  axisScale: number
  arrowScale: [number, number, number]
  color: string
  showCovariance: boolean
  covarianceColor: string
}

export type PoseUserData = BaseUserData & {
  settings: LayerSettingsPose
  topic: string
  poseMessage: PoseStamped | PoseWithCovarianceStamped
  originalMessage: Record<string, RosValue>
  axis?: Axis
  arrow?: RenderableArrow
  sphere?: RenderableSphere
}

// ============================================================
// 默认值
// ============================================================

const DEFAULT_TYPE: DisplayType = 'axis'
const DEFAULT_AXIS_SCALE = AXIS_LENGTH
const DEFAULT_ARROW_SCALE: THREE.Vector3Tuple = [1, 0.15, 0.15]
const DEFAULT_COLOR = { r: 124 / 255, g: 107 / 255, b: 1, a: 1 }
const DEFAULT_SHOW_COVARIANCE = true
const DEFAULT_COVARIANCE_COLOR = { r: 198 / 255, g: 107 / 255, b: 1, a: 0.25 }

const DEFAULT_COLOR_STR = rgbaToCssString(DEFAULT_COLOR)
const DEFAULT_COVARIANCE_COLOR_STR = rgbaToCssString(DEFAULT_COVARIANCE_COLOR)

const DEFAULT_SETTINGS: LayerSettingsPose = {
  type: DEFAULT_TYPE,
  visible: false,
  axisScale: DEFAULT_AXIS_SCALE,
  arrowScale: DEFAULT_ARROW_SCALE,
  color: DEFAULT_COLOR_STR,
  showCovariance: DEFAULT_SHOW_COVARIANCE,
  covarianceColor: DEFAULT_COVARIANCE_COLOR_STR
}

// ============================================================
// PoseRenderable — 单个 Topic 的可渲染对象
// ============================================================

export class PoseRenderable extends Renderable<PoseUserData> {
  public override dispose(): void {
    this.userData.axis?.dispose()
    this.userData.arrow?.dispose()
    this.userData.sphere?.dispose()
    super.dispose()
  }

  public override details(): Record<string, RosValue> {
    return this.userData.originalMessage
  }
}

// ============================================================
// Poses — SceneExtension 主类
// ============================================================

export class Poses extends SceneExtension<PoseRenderable> {
  public static extensionId = 'foxglove.Poses'

  public constructor(renderer: IRenderer, name: string = Poses.extensionId) {
    super(name, renderer)
    renderer.on('topicsChanged', this.#handleTopicsChanged)
  }

  public override dispose(): void {
    this.renderer.off('topicsChanged', this.#handleTopicsChanged)
    super.dispose()
  }

  #handleTopicsChanged = (): void => {
    this.updateSettingsTree()
  }

  // --- 订阅 ---

  public override getSubscriptions(): readonly AnyRendererSubscription[] {
    return [
      {
        type: 'schema',
        schemaNames: POSE_STAMPED_DATATYPES,
        subscription: { handler: this.#handlePoseStamped, filterQueue: onlyLastByTopicMessage }
      },
      {
        type: 'schema',
        schemaNames: POSE_WITH_COVARIANCE_STAMPED_DATATYPES,
        subscription: {
          handler: this.#handlePoseWithCovariance,
          filterQueue: onlyLastByTopicMessage
        }
      }
    ]
  }

  // --- 设置树节点 ---

  public override settingsNodes(): SettingsTreeEntry[] {
    const configTopics = this.renderer.config.topics
    const entries: SettingsTreeEntry[] = []

    const topicNames = new Set<string>()
    for (const topic of this.renderer.topics ?? []) {
      if (POSE_STAMPED_DATATYPES.has(topic.schemaName)) {
        topicNames.add(topic.name)
      } else if (POSE_WITH_COVARIANCE_STAMPED_DATATYPES.has(topic.schemaName)) {
        topicNames.add(topic.name)
      }
    }
    for (const name of this.renderables.keys()) {
      topicNames.add(name)
    }

    for (const topicName of topicNames) {
      const config = (configTopics[topicName] ?? {}) as Partial<LayerSettingsPose>
      const displayType = config.type ?? DEFAULT_TYPE

      const topicMeta = this.renderer.topicsByName?.get(topicName)
      const isPoseWithCov =
        topicMeta != null && POSE_WITH_COVARIANCE_STAMPED_DATATYPES.has(topicMeta.schemaName)

      const fields: Record<string, import('../core/lichtblick-shim').SettingsTreeField> = {
        type: {
          label: '显示类型',
          input: 'select',
          options: [
            { label: '坐标轴', value: 'axis' },
            { label: '箭头', value: 'arrow' }
          ],
          value: displayType
        }
      }

      if (displayType === 'axis') {
        fields['axisScale'] = fieldSize('缩放', config.axisScale, DEFAULT_AXIS_SCALE)
      } else {
        fields['arrowScale'] = fieldScaleVec3('缩放', config.arrowScale ?? DEFAULT_ARROW_SCALE)
        fields['color'] = {
          label: '颜色',
          input: 'rgba',
          value: config.color ?? DEFAULT_COLOR_STR
        }
      }

      if (isPoseWithCov) {
        const showCovariance = config.showCovariance ?? DEFAULT_SHOW_COVARIANCE
        fields['showCovariance'] = {
          label: '显示协方差',
          input: 'boolean',
          value: showCovariance
        }
        if (showCovariance) {
          fields['covarianceColor'] = {
            label: '协方差颜色',
            input: 'rgba',
            value: config.covarianceColor ?? DEFAULT_COVARIANCE_COLOR_STR
          }
        }
      }

      entries.push({
        path: ['topics', topicName],
        node: {
          label: topicName,
          icon: 'Flag',
          fields,
          visible: config.visible ?? DEFAULT_SETTINGS.visible,
          handler: this.handleSettingsAction
        }
      })
    }

    return entries
  }

  // --- 设置操作处理 ---

  public override handleSettingsAction = (action: SettingsTreeAction): void => {
    const path = action.payload.path
    if (action.action !== 'update' || !path) return

    // path 长度 2：可见性切换（眼睛图标）
    if (path.length === 2) {
      const topicName = path[1]!
      this.saveSetting([...path, 'visible'] as string[], action.payload.value)
      this.updateSettingsTree()
      const renderable = this.renderables.get(topicName)
      if (renderable) {
        this.#applySettings(renderable)
      }
      return
    }

    // path 长度 3：字段更新
    if (path.length !== 3) return
    this.saveSetting(path as string[], action.payload.value)
    this.updateSettingsTree()

    const topicName = path[1]!
    const renderable = this.renderables.get(topicName)
    if (renderable) {
      this.#applySettings(renderable)
    }
  }

  // --- 消息处理 ---

  #handlePoseStamped = (messageEvent: PartialMessageEvent<PoseStamped>): void => {
    const poseMessage = normalizePoseStamped(messageEvent.message)
    const receiveTime = toNanoSec(messageEvent.receiveTime)
    this.#addPose(
      messageEvent.topic,
      poseMessage,
      messageEvent.message as Record<string, RosValue>,
      receiveTime
    )
  }

  #handlePoseWithCovariance = (
    messageEvent: PartialMessageEvent<PoseWithCovarianceStamped>
  ): void => {
    const poseMessage = normalizePoseWithCovarianceStamped(messageEvent.message)
    const receiveTime = toNanoSec(messageEvent.receiveTime)
    this.#addPose(
      messageEvent.topic,
      poseMessage,
      messageEvent.message as Record<string, RosValue>,
      receiveTime
    )
  }

  #addPose(
    topic: string,
    poseMessage: PoseStamped | PoseWithCovarianceStamped,
    originalMessage: Record<string, RosValue>,
    receiveTime: bigint
  ): void {
    let renderable = this.renderables.get(topic)
    if (!renderable) {
      const userSettings = this.renderer.config.topics[topic] as
        | Partial<LayerSettingsPose>
        | undefined
      const settings = { ...DEFAULT_SETTINGS, ...userSettings }

      renderable = new PoseRenderable(topic, this.renderer, {
        receiveTime,
        messageTime: toNanoSec(poseMessage.header.stamp),
        frameId: this.renderer.normalizeFrameId(poseMessage.header.frame_id),
        pose: makePose(),
        settingsPath: ['topics', topic],
        settings,
        topic,
        poseMessage,
        originalMessage,
        axis: undefined,
        arrow: undefined,
        sphere: undefined
      })

      this.add(renderable)
      this.renderables.set(topic, renderable)
      this.updateSettingsTree()
    }

    this.#updatePoseRenderable(renderable, poseMessage, originalMessage, receiveTime)
  }

  // --- 更新 Renderable ---

  #applySettings(renderable: PoseRenderable): void {
    const settings = this.renderer.config.topics[renderable.userData.topic] as
      | Partial<LayerSettingsPose>
      | undefined
    this.#updatePoseRenderable(
      renderable,
      renderable.userData.poseMessage,
      renderable.userData.originalMessage,
      renderable.userData.receiveTime,
      { ...DEFAULT_SETTINGS, ...settings }
    )
  }

  #updatePoseRenderable(
    renderable: PoseRenderable,
    poseMessage: PoseStamped | PoseWithCovarianceStamped,
    originalMessage: Record<string, RosValue>,
    receiveTime: bigint,
    settings?: LayerSettingsPose
  ): void {
    const s = settings ?? renderable.userData.settings

    renderable.userData.receiveTime = receiveTime
    renderable.userData.messageTime = toNanoSec(poseMessage.header.stamp)
    renderable.userData.frameId = this.renderer.normalizeFrameId(poseMessage.header.frame_id)
    renderable.userData.poseMessage = poseMessage
    renderable.userData.originalMessage = originalMessage

    // 默认协方差球体隐藏
    if (renderable.userData.sphere) {
      renderable.userData.sphere.visible = false
    }

    const prevSettings = renderable.userData.settings
    const needRebuild =
      s.type !== prevSettings.type ||
      s.axisScale !== prevSettings.axisScale ||
      !arrayEqual(s.arrowScale, prevSettings.arrowScale) ||
      s.color !== prevSettings.color ||
      (!renderable.userData.arrow && !renderable.userData.axis)

    renderable.userData.settings = s

    if (needRebuild) {
      if (s.type === 'axis') {
        // 切换到 axis：移除 arrow
        if (renderable.userData.arrow) {
          renderable.remove(renderable.userData.arrow)
          renderable.userData.arrow.dispose()
          renderable.userData.arrow = undefined
        }
        if (!renderable.userData.axis) {
          const axis = new Axis(renderable.userData.topic, this.renderer)
          renderable.userData.axis = axis
          renderable.add(axis)
        }
        const scale = s.axisScale * (1 / AXIS_LENGTH)
        renderable.userData.axis!.scale.set(scale, scale, scale)
      } else {
        // 切换到 arrow：移除 axis
        if (renderable.userData.axis) {
          renderable.remove(renderable.userData.axis)
          renderable.userData.axis.dispose()
          renderable.userData.axis = undefined
        }
        const color = stringToRgba(makeRgba(), s.color)
        const arrowMarker = createArrowMarker(s.arrowScale, color)
        if (!renderable.userData.arrow) {
          const arrow = new RenderableArrow(
            renderable.userData.topic,
            arrowMarker,
            undefined,
            this.renderer
          )
          renderable.userData.arrow = arrow
          renderable.add(arrow)
        }
        renderable.userData.arrow!.update(arrowMarker, undefined)
      }
    }

    // 设置 pose
    if ('covariance' in poseMessage.pose) {
      renderable.userData.pose = (poseMessage as PoseWithCovarianceStamped).pose.pose
      const sphereMarker = createSphereMarker(poseMessage as PoseWithCovarianceStamped, s)
      if (sphereMarker) {
        if (!renderable.userData.sphere) {
          renderable.userData.sphere = new RenderableSphere(
            renderable.userData.topic,
            sphereMarker,
            undefined,
            this.renderer
          )
          renderable.add(renderable.userData.sphere)
        }
        renderable.userData.sphere.visible = s.showCovariance
        renderable.userData.sphere.update(sphereMarker, undefined)
      }
    } else {
      renderable.userData.pose = (poseMessage as PoseStamped).pose
    }
  }
}

// ============================================================
// 工具函数 — 创建虚拟 Marker
// ============================================================

export function createArrowMarker(arrowScale: [number, number, number], color: ColorRGBA): Marker {
  const [x, y, z] = arrowScale
  return {
    header: { frame_id: '', stamp: { sec: 0, nsec: 0 } },
    ns: '',
    id: 0,
    type: MarkerType.ARROW,
    action: MarkerAction.ADD,
    pose: makePose(),
    scale: { x, y, z },
    color,
    lifetime: TIME_ZERO,
    frame_locked: true,
    points: [],
    colors: [],
    text: '',
    mesh_resource: '',
    mesh_use_embedded_materials: false
  }
}

function createSphereMarker(
  poseMessage: PoseWithCovarianceStamped,
  settings: LayerSettingsPose
): Marker | undefined {
  // 提取 6x6 协方差矩阵中的位置方差（左上角对角线）
  const K = poseMessage.pose.covariance
  const scaleX = Math.sqrt(Math.abs(K[0]))
  const scaleY = Math.sqrt(Math.abs(K[7]))
  const scaleZ = Math.sqrt(Math.abs(K[14]))

  if (!isFinite(scaleX) || !isFinite(scaleY) || !isFinite(scaleZ)) {
    return undefined
  }

  return {
    header: poseMessage.header,
    ns: '',
    id: 1,
    type: MarkerType.SPHERE,
    action: MarkerAction.ADD,
    pose: makePose(),
    scale: { x: scaleX, y: scaleY, z: scaleZ },
    color: stringToRgba(makeRgba(), settings.covarianceColor),
    lifetime: TIME_ZERO,
    frame_locked: true,
    points: [],
    colors: [],
    text: '',
    mesh_resource: '',
    mesh_use_embedded_materials: false
  }
}

// ============================================================
// 归一化函数
// ============================================================

function normalizePoseStamped(msg: PartialMessage<PoseStamped>): PoseStamped {
  return {
    header: normalizeHeader(msg.header),
    pose: normalizePose(msg.pose)
  }
}

function normalizePoseWithCovariance(
  pose: PartialMessage<PoseWithCovariance> | undefined
): PoseWithCovariance {
  return {
    pose: normalizePose(pose?.pose),
    covariance: normalizeMatrix6(pose?.covariance as number[] | undefined)
  }
}

function normalizePoseWithCovarianceStamped(
  msg: PartialMessage<PoseWithCovarianceStamped>
): PoseWithCovarianceStamped {
  return {
    header: normalizeHeader(msg.header),
    pose: normalizePoseWithCovariance(msg.pose)
  }
}

// ============================================================
// 小工具
// ============================================================

function toNanoSec(time: { sec: number; nsec: number }): bigint {
  return BigInt(time.sec) * 1_000_000_000n + BigInt(time.nsec)
}

function arrayEqual(a: number[], b: number[]): boolean {
  if (a.length !== b.length) return false
  for (let i = 0; i < a.length; i++) {
    if (a[i] !== b[i]) return false
  }
  return true
}
