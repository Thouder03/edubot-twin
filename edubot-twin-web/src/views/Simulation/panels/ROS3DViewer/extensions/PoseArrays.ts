// SPDX-License-Identifier: MPL-2.0
// PoseArrays SceneExtension — 渲染 geometry_msgs/PoseArray 和 nav_msgs/Path

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
import { makeRgba, rgbaToCssString, stringToRgba, rgbaGradient } from '../core/color'
import { normalizeHeader, normalizePose } from '../core/normalizeMessages'
import {
  Marker,
  MarkerType,
  MarkerAction,
  PoseArray,
  NavPath,
  PoseStamped,
  ColorRGBA,
  POSE_ARRAY_DATATYPES,
  NAV_PATH_DATATYPES,
  TIME_ZERO
} from '../core/ros'
import {
  BaseSettings,
  fieldSize,
  fieldScaleVec3,
  fieldLineWidth,
  fieldGradient,
  TwoColors
} from '../core/settings'
import { makePose, Pose } from '../core/transforms'
import type { Topic } from '../core/lichtblick-shim'
import type { RosValue } from '../core/lichtblick-shim'
import { Axis, AXIS_LENGTH } from './Axis'
import { createArrowMarker } from './Poses'
import { RenderableArrow } from './markers/RenderableArrow'
import { RenderableLineStrip } from './markers/RenderableLineStrip'

// ============================================================
// 类型定义
// ============================================================

type GradientRgba = [ColorRGBA, ColorRGBA]
type DisplayType = 'axis' | 'arrow' | 'line'

export type LayerSettingsPoseArray = BaseSettings & {
  type: DisplayType
  axisScale: number
  arrowScale: [number, number, number]
  lineWidth: number
  gradient: TwoColors
}

export type PoseArrayUserData = BaseUserData & {
  settings: LayerSettingsPoseArray
  topic: string
  poseArrayMessage: PoseArray
  originalMessage: Record<string, RosValue>
  axes: Axis[]
  arrows: RenderableArrow[]
  lineStrip?: RenderableLineStrip
}

// ============================================================
// 默认值
// ============================================================

const DEFAULT_TYPE: DisplayType = 'axis'
const DEFAULT_AXIS_SCALE = AXIS_LENGTH
const DEFAULT_ARROW_SCALE: THREE.Vector3Tuple = [1, 0.15, 0.15]
const DEFAULT_LINE_WIDTH = 0.2
const DEFAULT_GRADIENT: GradientRgba = [
  { r: 124 / 255, g: 107 / 255, b: 1, a: 1 },
  { r: 124 / 255, g: 107 / 255, b: 1, a: 0.5 }
]

const DEFAULT_GRADIENT_STR: TwoColors = [
  rgbaToCssString(DEFAULT_GRADIENT[0]),
  rgbaToCssString(DEFAULT_GRADIENT[1])
]

const DEFAULT_SETTINGS: LayerSettingsPoseArray = {
  visible: false,
  type: DEFAULT_TYPE,
  axisScale: DEFAULT_AXIS_SCALE,
  arrowScale: DEFAULT_ARROW_SCALE,
  lineWidth: DEFAULT_LINE_WIDTH,
  gradient: DEFAULT_GRADIENT_STR
}

const COLOR_WHITE: ColorRGBA = { r: 1, g: 1, b: 1, a: 1 }

// 临时颜色对象（避免频繁 GC）
const tempColor1 = makeRgba()
const tempColor2 = makeRgba()
const tempColor3 = makeRgba()

// ============================================================
// PoseArrayRenderable — 单个 Topic 的可渲染对象
// ============================================================

export class PoseArrayRenderable extends Renderable<PoseArrayUserData> {
  public override dispose(): void {
    this.userData.axes.forEach((a) => a.dispose())
    this.userData.arrows.forEach((a) => a.dispose())
    this.userData.lineStrip?.dispose()
    super.dispose()
  }

  public override details(): Record<string, RosValue> {
    return this.userData.originalMessage
  }

  public removeArrows(): void {
    for (const arrow of this.userData.arrows) {
      this.remove(arrow)
      arrow.dispose()
    }
    this.userData.arrows.length = 0
  }

  public removeAxes(): void {
    for (const axis of this.userData.axes) {
      this.remove(axis)
      axis.dispose()
    }
    this.userData.axes.length = 0
  }

  public removeLineStrip(): void {
    if (this.userData.lineStrip) {
      this.remove(this.userData.lineStrip)
      this.userData.lineStrip.dispose()
      this.userData.lineStrip = undefined
    }
  }
}

// ============================================================
// PoseArrays — SceneExtension 主类
// ============================================================

export class PoseArrays extends SceneExtension<PoseArrayRenderable> {
  public static extensionId = 'foxglove.PoseArrays'

  public constructor(renderer: IRenderer, name: string = PoseArrays.extensionId) {
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
        schemaNames: POSE_ARRAY_DATATYPES,
        subscription: { handler: this.#handlePoseArray, filterQueue: onlyLastByTopicMessage }
      },
      {
        type: 'schema',
        schemaNames: NAV_PATH_DATATYPES,
        subscription: { handler: this.#handleNavPath, filterQueue: onlyLastByTopicMessage }
      }
    ]
  }

  // --- 设置树节点 ---

  public override settingsNodes(): SettingsTreeEntry[] {
    const configTopics = this.renderer.config.topics
    const entries: SettingsTreeEntry[] = []

    const topicNames = new Set<string>()
    for (const topic of this.renderer.topics ?? []) {
      if (POSE_ARRAY_DATATYPES.has(topic.schemaName) || NAV_PATH_DATATYPES.has(topic.schemaName)) {
        topicNames.add(topic.name)
      }
    }
    for (const name of this.renderables.keys()) {
      topicNames.add(name)
    }

    for (const topicName of topicNames) {
      const config = (configTopics[topicName] ?? {}) as Partial<LayerSettingsPoseArray>
      const topicMeta = this.renderer.topicsByName?.get(topicName)
      const displayType = config.type ?? getDefaultType(topicMeta)
      const gradient = config.gradient ?? DEFAULT_GRADIENT_STR

      const isNavPath = topicMeta != null && NAV_PATH_DATATYPES.has(topicMeta.schemaName)

      const fields: Record<string, import('../core/lichtblick-shim').SettingsTreeField> = {
        type: {
          label: '显示类型',
          input: 'select',
          options: [
            { label: '坐标轴', value: 'axis' },
            { label: '箭头', value: 'arrow' },
            { label: '轨迹线', value: 'line' }
          ],
          value: displayType
        }
      }

      switch (displayType) {
        case 'axis':
          fields['axisScale'] = fieldSize('缩放', config.axisScale, DEFAULT_AXIS_SCALE)
          break
        case 'arrow':
          fields['arrowScale'] = fieldScaleVec3('缩放', config.arrowScale ?? DEFAULT_ARROW_SCALE)
          break
        case 'line':
          fields['lineWidth'] = fieldLineWidth('线宽', config.lineWidth, DEFAULT_LINE_WIDTH)
          break
      }

      // axis 模式暂不支持渐变色，其他模式都支持
      if (displayType !== 'axis') {
        fields['gradient'] = fieldGradient('渐变色', gradient)
      }

      entries.push({
        path: ['topics', topicName],
        node: {
          label: topicName,
          icon: isNavPath ? 'Timeline' : 'Flag',
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

    // path 长度 2：可见性切换
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

  #handlePoseArray = (messageEvent: PartialMessageEvent<PoseArray>): void => {
    const poseArrayMessage = normalizePoseArray(messageEvent.message)
    const receiveTime = toNanoSec(messageEvent.receiveTime)
    this.#addPoseArray(
      messageEvent.topic,
      poseArrayMessage,
      messageEvent.message as Record<string, RosValue>,
      receiveTime
    )
  }

  #handleNavPath = (messageEvent: PartialMessageEvent<NavPath>): void => {
    const poseArrayMessage = normalizeNavPathToPoseArray(messageEvent.message)
    const receiveTime = toNanoSec(messageEvent.receiveTime)
    this.#addPoseArray(
      messageEvent.topic,
      poseArrayMessage,
      messageEvent.message as Record<string, RosValue>,
      receiveTime
    )
  }

  #addPoseArray(
    topic: string,
    poseArrayMessage: PoseArray,
    originalMessage: Record<string, RosValue>,
    receiveTime: bigint
  ): void {
    let renderable = this.renderables.get(topic)
    if (!renderable) {
      const userSettings = this.renderer.config.topics[topic] as
        | Partial<LayerSettingsPoseArray>
        | undefined
      const topicMeta = this.renderer.topicsByName?.get(topic)
      const defaultType = { type: getDefaultType(topicMeta) }
      const settings = { ...DEFAULT_SETTINGS, ...defaultType, ...userSettings }

      renderable = new PoseArrayRenderable(topic, this.renderer, {
        receiveTime,
        messageTime: toNanoSec(poseArrayMessage.header.stamp),
        frameId: this.renderer.normalizeFrameId(poseArrayMessage.header.frame_id),
        pose: makePose(),
        settingsPath: ['topics', topic],
        settings,
        topic,
        poseArrayMessage,
        originalMessage,
        axes: [],
        arrows: []
      })

      this.add(renderable)
      this.renderables.set(topic, renderable)
      this.updateSettingsTree()
    }

    this.#updatePoseArrayRenderable(renderable, poseArrayMessage, originalMessage, receiveTime)
  }

  // --- 更新 Renderable ---

  #applySettings(renderable: PoseArrayRenderable): void {
    const topicMeta = this.renderer.topicsByName?.get(renderable.userData.topic)
    const userSettings = this.renderer.config.topics[renderable.userData.topic] as
      | Partial<LayerSettingsPoseArray>
      | undefined
    const defaultType = { type: getDefaultType(topicMeta) }
    const settings = { ...DEFAULT_SETTINGS, ...defaultType, ...userSettings }

    this.#updatePoseArrayRenderable(
      renderable,
      renderable.userData.poseArrayMessage,
      renderable.userData.originalMessage,
      renderable.userData.receiveTime,
      settings
    )
  }

  #updatePoseArrayRenderable(
    renderable: PoseArrayRenderable,
    poseArrayMessage: PoseArray,
    originalMessage: Record<string, RosValue>,
    receiveTime: bigint,
    settings?: LayerSettingsPoseArray
  ): void {
    const s = settings ?? renderable.userData.settings

    renderable.userData.receiveTime = receiveTime
    renderable.userData.messageTime = toNanoSec(poseArrayMessage.header.stamp)
    renderable.userData.frameId = this.renderer.normalizeFrameId(poseArrayMessage.header.frame_id)
    renderable.userData.poseArrayMessage = poseArrayMessage
    renderable.userData.originalMessage = originalMessage

    const prevSettings = renderable.userData.settings
    const needRebuild =
      s.type !== prevSettings.type ||
      s.axisScale !== prevSettings.axisScale ||
      !arrayEqual(s.arrowScale, prevSettings.arrowScale) ||
      !arrayEqual(s.gradient, prevSettings.gradient) ||
      (renderable.userData.arrows.length === 0 && renderable.userData.axes.length === 0)

    renderable.userData.settings = s

    const colorStart = stringToRgba(tempColor1, s.gradient[0])
    const colorEnd = stringToRgba(tempColor2, s.gradient[1])

    if (needRebuild) {
      switch (s.type) {
        case 'axis':
          renderable.removeArrows()
          renderable.removeLineStrip()
          break
        case 'arrow':
          renderable.removeAxes()
          renderable.removeLineStrip()
          break
        case 'line': {
          renderable.removeArrows()
          renderable.removeAxes()

          const lineStripMarker = createLineStripMarker(
            poseArrayMessage,
            s.lineWidth,
            colorStart,
            colorEnd
          )
          if (!renderable.userData.lineStrip) {
            const lineStrip = new RenderableLineStrip(
              renderable.userData.topic,
              lineStripMarker,
              undefined,
              this.renderer
            )
            renderable.userData.lineStrip = lineStrip
            renderable.add(lineStrip)
          }
          renderable.userData.lineStrip!.update(lineStripMarker, undefined)
          break
        }
      }
    }

    // 根据类型更新各 Pose 的变换
    switch (s.type) {
      case 'axis':
        this.#createAxesToMatchPoses(renderable, poseArrayMessage)
        for (let i = 0; i < poseArrayMessage.poses.length; i++) {
          setObjectPose(renderable.userData.axes[i]!, poseArrayMessage.poses[i]!)
        }
        break

      case 'arrow':
        this.#createArrowsToMatchPoses(renderable, poseArrayMessage, colorStart, colorEnd)
        for (let i = 0; i < poseArrayMessage.poses.length; i++) {
          setObjectPose(renderable.userData.arrows[i]!, poseArrayMessage.poses[i]!)
        }
        break

      case 'line': {
        const lineStripMarker = createLineStripMarker(
          poseArrayMessage,
          s.lineWidth,
          colorStart,
          colorEnd
        )
        renderable.userData.lineStrip?.update(lineStripMarker, undefined)
        break
      }
    }
  }

  // --- 对象池管理 ---

  #createAxesToMatchPoses(renderable: PoseArrayRenderable, poseArray: PoseArray): void {
    const topic = renderable.userData.topic
    const scale = renderable.userData.settings.axisScale * (1 / AXIS_LENGTH)

    // 更新已有的 Axis
    const updateCount = Math.min(renderable.userData.axes.length, poseArray.poses.length)
    for (let i = 0; i < updateCount; i++) {
      const axis = renderable.userData.axes[i]!
      axis.visible = true
      axis.scale.set(scale, scale, scale)
    }

    // 新建不足的 Axis
    for (let i = renderable.userData.axes.length; i < poseArray.poses.length; i++) {
      const axis = new Axis(topic, this.renderer)
      axis.scale.set(scale, scale, scale)
      renderable.userData.axes.push(axis)
      renderable.add(axis)
    }

    // 隐藏多余的 Axis
    for (let i = poseArray.poses.length; i < renderable.userData.axes.length; i++) {
      renderable.userData.axes[i]!.visible = false
    }
  }

  #createArrowsToMatchPoses(
    renderable: PoseArrayRenderable,
    poseArray: PoseArray,
    colorStart: ColorRGBA,
    colorEnd: ColorRGBA
  ): void {
    const topic = renderable.userData.topic
    const { arrowScale } = renderable.userData.settings
    const total = poseArray.poses.length

    const arrowColorAt = (i: number): ColorRGBA =>
      rgbaGradient(tempColor3, colorStart, colorEnd, total > 1 ? i / (total - 1) : 0)

    // 更新已有的 Arrow
    const updateCount = Math.min(renderable.userData.arrows.length, total)
    for (let i = 0; i < updateCount; i++) {
      const arrowMarker = createArrowMarker(arrowScale, arrowColorAt(i))
      const arrow = renderable.userData.arrows[i]!
      arrow.visible = true
      arrow.update(arrowMarker, undefined)
    }

    // 新建不足的 Arrow
    for (let i = renderable.userData.arrows.length; i < total; i++) {
      const arrowMarker = createArrowMarker(arrowScale, arrowColorAt(i))
      const arrow = new RenderableArrow(topic, arrowMarker, undefined, this.renderer)
      renderable.userData.arrows.push(arrow)
      renderable.add(arrow)
    }

    // 隐藏多余的 Arrow
    for (let i = total; i < renderable.userData.arrows.length; i++) {
      renderable.userData.arrows[i]!.visible = false
    }
  }
}

// ============================================================
// 工具函数
// ============================================================

function getDefaultType(topic: Topic | undefined): DisplayType {
  return topic != null && NAV_PATH_DATATYPES.has(topic.schemaName) ? 'line' : DEFAULT_TYPE
}

function setObjectPose(object: THREE.Object3D, pose: Pose): void {
  const p = pose.position
  const q = pose.orientation
  object.position.set(p.x, p.y, p.z)
  object.quaternion.set(q.x, q.y, q.z, q.w)
  object.updateMatrix()
}

function createLineStripMarker(
  message: PoseArray,
  lineWidth: number,
  colorStart: ColorRGBA,
  colorEnd: ColorRGBA
): Marker {
  const total = message.poses.length
  const colors: ColorRGBA[] = []
  for (let i = 0; i < total; i++) {
    colors.push(rgbaGradient(makeRgba(), colorStart, colorEnd, total > 1 ? i / (total - 1) : 0))
  }

  return {
    header: message.header,
    ns: '',
    id: 0,
    type: MarkerType.LINE_STRIP,
    action: MarkerAction.ADD,
    pose: makePose(),
    scale: { x: lineWidth, y: 1, z: 1 },
    color: COLOR_WHITE,
    lifetime: TIME_ZERO,
    frame_locked: true,
    points: message.poses.map((pose) => pose.position),
    colors,
    text: '',
    mesh_resource: '',
    mesh_use_embedded_materials: false
  }
}

// ============================================================
// 归一化函数
// ============================================================

function normalizePoseArray(msg: PartialMessage<PoseArray>): PoseArray {
  return {
    header: normalizeHeader(msg.header),
    poses: msg.poses?.map((p) => normalizePose(p)) ?? []
  }
}

function normalizeNavPathToPoseArray(msg: PartialMessage<NavPath>): PoseArray {
  return {
    header: normalizeHeader(msg.header),
    poses: msg.poses?.map((p) => normalizePose((p as PartialMessage<PoseStamped>)?.pose)) ?? []
  }
}

function toNanoSec(time: { sec: number; nsec: number }): bigint {
  return BigInt(time.sec) * 1_000_000_000n + BigInt(time.nsec)
}

function arrayEqual(a: readonly (string | number)[], b: readonly (string | number)[]): boolean {
  if (a.length !== b.length) return false
  for (let i = 0; i < a.length; i++) {
    if (a[i] !== b[i]) return false
  }
  return true
}
