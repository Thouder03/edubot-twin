// SPDX-FileCopyrightText: Copyright (C) 2023-2025 Bayerische Motoren Werke Aktiengesellschaft (BMW AG)<lichtblick@bmwgroup.com>
// SPDX-License-Identifier: MPL-2.0

// This Source Code Form is subject to the terms of the Mozilla Public
// License, v2.0. If a copy of the MPL was not distributed with this
// file, You can obtain one at http://mozilla.org/MPL/2.0/
//
// Ported from lichtblick/renderables/LaserScans.ts
// Adaptations:
//  - Removed foxglove LaserScan schema support (ROS1/ROS2 only)
//  - LaserScanInstancePickingMaterial not wired (retained as stub for future use)
//  - Adapted import paths to local core/ structure

import * as THREE from 'three'

import { MessageEvent, RosValue, Time } from '../core/lichtblick-shim'
import type { SettingsTreeAction } from '../core/lichtblick-shim'
import {
  DEFAULT_POINT_SETTINGS,
  LayerSettingsPointExtension,
  pointSettingsNode,
  PointsRenderable,
  RenderObjectHistory,
  createPickingMaterial
} from '../core/pointExtensionUtils'
import { colorHasTransparency, getColorConverter } from '../core/colorMode'
import { DynamicBufferGeometry } from '../core/DynamicBufferGeometry'
import type { AnyRendererSubscription, IRenderer } from '../core/IRenderer'
import { BaseUserData, Renderable } from '../core/Renderable'
import { PartialMessage, PartialMessageEvent, SceneExtension } from '../core/SceneExtension'
import type { SettingsTreeEntry } from '../core/SettingsManager'
import { LASERSCAN_DATATYPES, LaserScan as RosLaserScan } from '../core/ros'
import { normalizeFloat32Array, normalizeTime } from '../core/normalizeMessages'
import type { Pose } from '../core/transforms'

// ─────────────────────────────────────────────────────────────────────────────
// Helpers
// ─────────────────────────────────────────────────────────────────────────────

/** 创建单位位姿（position=0, orientation=identity） */
function emptyPose(): Pose {
  return {
    position: { x: 0, y: 0, z: 0 },
    orientation: { x: 0, y: 0, z: 0, w: 1 }
  }
}

// ─────────────────────────────────────────────────────────────────────────────
// Types
// ─────────────────────────────────────────────────────────────────────────────

type LayerSettingsLaserScan = LayerSettingsPointExtension

const DEFAULT_SETTINGS = DEFAULT_POINT_SETTINGS

/** 归一化后的 LaserScan 中间表示 */
type NormalizedLaserScan = {
  timestamp: Time
  frame_id: string
  pose: Pose
  start_angle: number // angle_min (rad)
  end_angle: number // angle_max (rad)
  range_min: number
  range_max: number
  ranges: Float32Array
  intensities: Float32Array
}

type LaserScanHistoryUserData = BaseUserData & {
  settings: LayerSettingsLaserScan
  topic: string
  latestLaserScan: NormalizedLaserScan
  latestOriginalMessage: Record<string, RosValue> | undefined
}

type LaserScanUserData = BaseUserData & {
  laserScan: NormalizedLaserScan
  originalMessage: Record<string, RosValue> | undefined
}

const LASERSCAN_FIELDS = ['range', 'intensity']
const VEC3_ZERO = new THREE.Vector3()
const tempColor = { r: 0, g: 0, b: 0, a: 0 }

// ─────────────────────────────────────────────────────────────────────────────
// Geometry factory
// ─────────────────────────────────────────────────────────────────────────────

/**
 * 创建 LaserScan 专用 DynamicBufferGeometry。
 *
 * "position" attribute 存储 range 值（itemSize=1），而非 xyz 坐标。
 * 角度在顶点着色器中通过 gl_VertexID 实时计算，避免 CPU 极坐标转换。
 */
function createLaserScanGeometry(topic: string, usage: THREE.Usage): DynamicBufferGeometry {
  const geometry = new DynamicBufferGeometry(usage)
  geometry.name = `${topic}:LaserScan:geometry`
  geometry.createAttribute('position', Float32Array, 1) // range 值，非 xyz
  geometry.createAttribute('color', Uint8Array, 4, true) // RGBA 颜色
  return geometry
}

// ─────────────────────────────────────────────────────────────────────────────
// LaserScanRenderable — 单帧
// ─────────────────────────────────────────────────────────────────────────────

class LaserScanRenderable extends PointsRenderable<LaserScanUserData> {
  #material: LaserScanMaterial
  #pickingMaterial: THREE.ShaderMaterial

  public constructor(name: string, userData: LaserScanUserData, geometry: DynamicBufferGeometry) {
    const material = new LaserScanMaterial()
    const pickingMaterial = createPickingMaterial(DEFAULT_SETTINGS)
    // 实例拾取暂未实现，复用物体级 picking material 占位
    super(name, userData, geometry, material, pickingMaterial, pickingMaterial)
    this.#material = material
    this.#pickingMaterial = pickingMaterial
  }

  public override details(): Record<string, RosValue> {
    return (this.userData.originalMessage ?? {}) as Record<string, RosValue>
  }

  public override instanceDetails(instanceId: number): Record<string, RosValue> | undefined {
    const { ranges, intensities } = this.userData.laserScan
    const range = instanceId >= 0 && instanceId < ranges.length ? ranges[instanceId] : undefined
    const intensity =
      instanceId >= 0 && instanceId < intensities.length ? intensities[instanceId] : undefined
    return { range: range as RosValue, intensity: intensity as RosValue }
  }

  public updateUniforms(settings: LayerSettingsLaserScan, laserScan: NormalizedLaserScan): void {
    this.#material.updateUniforms(settings, laserScan)
    this.#pickingMaterial.uniforms['pointSize']!.value = Math.max(settings.pointSize, 8)
  }

  public setPixelRatio(pixelRatio: number): void {
    this.#material.setPixelRatio(pixelRatio)
  }

  public override dispose(): void {
    super.dispose()
    this.#material.dispose()
    this.#pickingMaterial.dispose()
  }
}

// ─────────────────────────────────────────────────────────────────────────────
// LaserScanHistoryRenderable — 持有历史帧
// ─────────────────────────────────────────────────────────────────────────────

class LaserScanHistoryRenderable extends Renderable<LaserScanHistoryUserData> {
  public override pickable = false // 拾取委托给子 LaserScanRenderable
  #pointsHistory: RenderObjectHistory<LaserScanRenderable>

  public constructor(topic: string, renderer: IRenderer, userData: LaserScanHistoryUserData) {
    super(topic, renderer, userData)

    const isDecay = userData.settings.decayTime > 0
    const geometry = createLaserScanGeometry(
      topic,
      isDecay ? THREE.DynamicDrawUsage : THREE.StaticDrawUsage
    )
    const points = new LaserScanRenderable(
      topic,
      {
        receiveTime: -1n,
        messageTime: -1n,
        frameId: '',
        pose: emptyPose(),
        settingsPath: [],
        settings: { visible: false },
        topic,
        laserScan: userData.latestLaserScan,
        originalMessage: userData.latestOriginalMessage
      },
      geometry
    )

    this.#pointsHistory = new RenderObjectHistory({
      initial: {
        messageTime: userData.receiveTime,
        receiveTime: userData.receiveTime,
        renderable: points
      },
      parentRenderable: this,
      renderer
    })
    this.add(points)
  }

  public override dispose(): void {
    this.userData.latestOriginalMessage = undefined
    this.#pointsHistory.dispose()
    super.dispose()
  }

  /** 更新当前帧数据，若 decayTime > 0 则入队新历史帧 */
  public updateLaserScan(
    laserScan: NormalizedLaserScan,
    originalMessage: Record<string, RosValue> | undefined,
    settings: LayerSettingsLaserScan,
    receiveTime: bigint,
    renderer: IRenderer
  ): void {
    const messageTime =
      BigInt(laserScan.timestamp.sec) * 1_000_000_000n + BigInt(laserScan.timestamp.nsec)

    this.userData.receiveTime = receiveTime
    this.userData.messageTime = messageTime
    this.userData.frameId = renderer.normalizeFrameId(laserScan.frame_id)
    this.userData.latestLaserScan = laserScan
    this.userData.latestOriginalMessage = originalMessage
    this.userData.settings = settings

    // colorField 校验：若 undefined 则 fallback 到 'range'（首帧 config 可能尚未持久化）
    const colorField: 'range' | 'intensity' =
      settings.colorField === 'intensity' ? 'intensity' : 'range'
    const { intensities, ranges } = laserScan

    const topic = this.userData.topic
    const isDecay = settings.decayTime > 0

    if (isDecay) {
      // 衰减模式：每帧创建独立 geometry
      const geometry = createLaserScanGeometry(topic, THREE.StaticDrawUsage)
      const points = new LaserScanRenderable(
        topic,
        {
          receiveTime: -1n,
          messageTime: -1n,
          frameId: '',
          pose: laserScan.pose,
          settingsPath: [],
          settings: { visible: false },
          topic,
          laserScan,
          originalMessage
        },
        geometry
      )
      this.#pointsHistory.addHistoryEntry({ receiveTime, messageTime, renderable: points })
      this.add(points)
    }

    const latestEntry = this.#pointsHistory.latest()
    latestEntry.receiveTime = receiveTime
    latestEntry.messageTime = messageTime
    latestEntry.renderable.userData.pose = laserScan.pose
    latestEntry.renderable.userData.laserScan = laserScan
    latestEntry.renderable.userData.originalMessage = originalMessage

    // 更新 geometry
    const geometry = latestEntry.renderable.geometry
    geometry.resize(ranges.length)
    const rangeAttr = geometry.attributes['position']!
    const colorAttr = geometry.attributes['color']!
    rangeAttr.set(ranges)

    // 更新 material uniforms
    latestEntry.renderable.updateUniforms(settings, laserScan)

    // 计算颜色值域
    let minColorValue = settings.minValue ?? Number.POSITIVE_INFINITY
    let maxColorValue = settings.maxValue ?? Number.NEGATIVE_INFINITY
    let maxRange = 0

    for (let i = 0; i < ranges.length; i++) {
      const range = ranges[i]!
      if (Number.isFinite(range)) {
        maxRange = Math.max(maxRange, range)
      }
      if (settings.minValue == undefined || settings.maxValue == undefined) {
        const colorValue = colorField === 'range' ? range : intensities[i]
        if (colorValue != undefined && Number.isFinite(colorValue)) {
          minColorValue = Math.min(minColorValue, colorValue)
          maxColorValue = Math.max(maxColorValue, colorValue)
        }
      }
    }

    if (settings.minValue == undefined || settings.maxValue == undefined) {
      // 用户没有手动指定时，使用自动计算值
      minColorValue = settings.minValue ?? minColorValue
      maxColorValue = settings.maxValue ?? maxColorValue
    }

    // 始终手动分配 boundingSphere
    // 因为自定义的 geometry 只有 1 维 position (存放 range)，Three.js 自动计算时会产生 NaN 的报错
    latestEntry.renderable.geometry.boundingSphere ??= new THREE.Sphere()
    latestEntry.renderable.geometry.boundingSphere.set(VEC3_ZERO, maxRange)
    latestEntry.renderable.frustumCulled = true

    // colorMode 为 rgba-fields 时 LaserScan 不支持，跳过颜色赋值
    if (settings.colorMode === 'rgba-fields') {
      rangeAttr.needsUpdate = true
      colorAttr.needsUpdate = true
      return
    }

    // 构建颜色转换器并逐点写入颜色 attribute
    const colorConverter = getColorConverter(
      settings as typeof settings & {
        colorMode: Exclude<typeof settings.colorMode, 'rgba-fields'>
      },
      minColorValue,
      maxColorValue
    )
    for (let i = 0; i < ranges.length; i++) {
      const colorValue = colorField === 'range' ? ranges[i]! : (intensities[i] ?? 0)
      colorConverter(tempColor, colorValue)
      // Uint8Array attribute 的 setXYZW 传入 0-1 浮点，Three.js 会乘 255
      colorAttr.setXYZW(i, tempColor.r, tempColor.g, tempColor.b, tempColor.a)
    }

    rangeAttr.needsUpdate = true
    colorAttr.needsUpdate = true
  }

  public invalidateLastEntry(): void {
    this.#pointsHistory.latest().renderable.geometry.resize(0)
  }

  public startFrame(currentTime: bigint, renderFrameId: string, fixedFrameId: string): void {
    this.#pointsHistory.updateHistoryFromCurrentTime(currentTime)
    this.#pointsHistory.updatePoses(currentTime, renderFrameId, fixedFrameId)
    const pixelRatio = this.renderer!.getPixelRatio()
    this.#pointsHistory.forEach((entry) => {
      entry.renderable.setPixelRatio(pixelRatio)
    })
  }
}

// ─────────────────────────────────────────────────────────────────────────────
// LaserScans — SceneExtension
// ─────────────────────────────────────────────────────────────────────────────

export class LaserScans extends SceneExtension<LaserScanHistoryRenderable> {
  public static extensionId = 'foxglove.LaserScans'

  public constructor(renderer: IRenderer, name: string = LaserScans.extensionId) {
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

  public override getSubscriptions(): readonly AnyRendererSubscription[] {
    return [
      {
        type: 'schema',
        schemaNames: LASERSCAN_DATATYPES,
        subscription: {
          handler: this.#handleLaserScan as (messageEvent: MessageEvent<unknown>) => void,
          filterQueue: this.#filterQueue as (
            queue: MessageEvent<unknown>[]
          ) => MessageEvent<unknown>[]
        }
      }
    ]
  }

  /** 无衰减时每 topic 只保留最新一条消息，减少渲染压力 */
  #filterQueue = (msgs: MessageEvent<unknown>[]): MessageEvent<unknown>[] => {
    if (msgs.length === 0) return msgs

    const byTopic = new Map<string, MessageEvent<unknown>[]>()
    for (const msg of msgs) {
      let arr = byTopic.get(msg.topic)
      if (!arr) {
        arr = []
        byTopic.set(msg.topic, arr)
      }
      arr.push(msg)
    }

    const out: MessageEvent<unknown>[] = []
    for (const [topic, topicMsgs] of byTopic) {
      const userSettings = this.renderer.config.topics[topic] as
        | Partial<LayerSettingsLaserScan>
        | undefined
      if ((userSettings?.decayTime ?? DEFAULT_SETTINGS.decayTime) > 0) {
        out.push(...topicMsgs)
        continue
      }
      const latest = topicMsgs[topicMsgs.length - 1]
      if (latest) out.push(latest)
    }
    return out
  }

  public override settingsNodes(): SettingsTreeEntry[] {
    const configTopics = this.renderer.config.topics
    const entries: SettingsTreeEntry[] = []

    // 收集所有 LaserScan topic（来源同 Markers 处理方案：schema 严格过滤 + 断线时保留 renderable）
    const topicsByName = this.renderer.topicsByName
    const topicNames = new Set<string>()

    // 来源 1：从实时 topics 列表筛选（已连接时立即可见）
    for (const topic of this.renderer.topics ?? []) {
      if (LASERSCAN_DATATYPES.has(topic.schemaName)) {
        topicNames.add(topic.name)
      }
    }

    // 来源 2：从 config.topics 筛选
    for (const name of Object.keys(configTopics)) {
      const topicMeta = topicsByName?.get(name)
      if (topicMeta) {
        if (LASERSCAN_DATATYPES.has(topicMeta.schemaName)) {
          topicNames.add(name)
        }
      } else if (topicsByName != null) {
        // 已连接但话题消失：跳过
      } else {
        // 断线状态：只保留有 renderable（已收到消息）的话题
        if (this.renderables.has(name)) {
          topicNames.add(name)
        }
      }
    }

    for (const topicName of topicNames) {
      const topicMeta = topicsByName?.get(topicName)
      const config = (configTopics[topicName] ?? {}) as Partial<LayerSettingsLaserScan>
      const node = {
        ...pointSettingsNode(
          topicMeta ?? { name: topicName, schemaName: 'sensor_msgs/LaserScan' },
          LASERSCAN_FIELDS,
          config
        ),
        icon: 'Radar' as const,
        handler: this.handleSettingsAction
      }
      entries.push({ path: ['topics', topicName], node })
    }
    return entries
  }

  public override startFrame(
    currentTime: bigint,
    renderFrameId: string,
    fixedFrameId: string
  ): void {
    // 委托给基类处理 visible 标志（不 dispose 隐藏中的渲染体）
    // 委托给 LaserScanHistoryRenderable.startFrame() 处理历史帧位姿更新
    for (const renderable of this.renderables.values()) {
      renderable.visible = renderable.userData.settings.visible
      if (!renderable.visible) continue
      renderable.startFrame(currentTime, renderFrameId, fixedFrameId)
    }
  }

  public override handleSettingsAction = (action: SettingsTreeAction): void => {
    const path = action.payload.path
    if (action.action !== 'update') return
    if (path == undefined || path.length < 2 || path[0] !== 'topics') return

    const topicName = path[1]!

    // path 长度 = 2：['topics', topicName] → 眼睛图标触发的 visible 切换
    if (path.length === 2) {
      const visible = action.payload.value as boolean
      const renderable = this.renderables.get(topicName)
      if (renderable) {
        renderable.userData.settings.visible = visible
        renderable.visible = visible
      }
      this.renderer.updateConfig((draft) => {
        const prev = (draft.topics[topicName] ?? {}) as Partial<LayerSettingsLaserScan>
        draft.topics[topicName] = { ...prev, visible } as any
      })
      this.updateSettingsTree()
      return
    }

    // path 长度 = 3：['topics', topicName, field] → 字段更新
    if (path.length !== 3) return

    this.saveSetting(path, action.payload.value)

    const renderable = this.renderables.get(topicName)
    if (!renderable) return

    // 从最新 config 重建 settings（saveSetting 已写入 config）
    const prevSettings = this.renderer.config.topics[topicName] as
      | Partial<LayerSettingsLaserScan>
      | undefined
    const settings: LayerSettingsLaserScan = { ...DEFAULT_SETTINGS, ...prevSettings }
    // 同步到 userData，保证 startFrame 使用最新的 visible 等字段
    renderable.userData.settings = settings

    renderable.updateLaserScan(
      renderable.userData.latestLaserScan,
      renderable.userData.latestOriginalMessage,
      settings,
      renderable.userData.receiveTime,
      this.renderer
    )
  }

  #handleLaserScan = (messageEvent: PartialMessageEvent<RosLaserScan>): void => {
    const topic = messageEvent.topic
    const laserScan = normalizeRosLaserScan(messageEvent.message)
    const receiveTime =
      BigInt(messageEvent.receiveTime.sec) * 1_000_000_000n + BigInt(messageEvent.receiveTime.nsec)

    let renderable = this.renderables.get(topic)
    if (!renderable) {
      const userSettings = this.renderer.config.topics[topic] as
        | Partial<LayerSettingsLaserScan>
        | undefined
      const settings: LayerSettingsLaserScan = { ...DEFAULT_SETTINGS, ...userSettings }

      // 首次发现话题时自动初始化：visible=false + colormap 颜色
      // DEFAULT_POINT_SETTINGS.visible=false
      const isFirstTime = userSettings?.colorField == undefined
      if (isFirstTime) {
        settings.visible = false
        settings.colorField = 'intensity'
        settings.colorMode = 'colormap'
        settings.colorMap = 'turbo'
        this.renderer.updateConfig((draft) => {
          draft.topics[topic] = {
            visible: false,
            colorField: 'intensity',
            colorMode: 'colormap',
            colorMap: 'turbo'
          } as any
        })
      } else if (settings.visible == undefined) {
        // 已持久化但没有 visible 字段，也默认关闭
        settings.visible = false
      }

      const messageTime =
        BigInt(laserScan.timestamp.sec) * 1_000_000_000n + BigInt(laserScan.timestamp.nsec)

      renderable = new LaserScanHistoryRenderable(topic, this.renderer, {
        receiveTime,
        messageTime,
        frameId: this.renderer.normalizeFrameId(laserScan.frame_id),
        pose: laserScan.pose,
        settingsPath: ['topics', topic],
        settings,
        topic,
        latestLaserScan: laserScan,
        latestOriginalMessage: messageEvent.message as Record<string, RosValue>
      })

      this.add(renderable)
      this.renderables.set(topic, renderable)
      this.updateSettingsTree()
    }

    renderable.updateLaserScan(
      laserScan,
      messageEvent.message as Record<string, RosValue>,
      renderable.userData.settings,
      receiveTime,
      this.renderer
    )
  }
}

// ─────────────────────────────────────────────────────────────────────────────
// LaserScanMaterial — GLSL3 自定义 Shader
// ─────────────────────────────────────────────────────────────────────────────

/**
 * LaserScan 渲染 Material。
 *
 * 核心：顶点着色器 GPU 端将极坐标转笛卡尔坐标，无需 CPU 预处理。
 *   angle = angleMin + angleIncrement * gl_VertexID
 *   pos   = (range * cos(angle), range * sin(angle), 0)
 *
 * "position" attribute 只存 range（itemSize=1），color attribute 由 CPU 预计算写入。
 * 范围过滤（rangeMin/rangeMax 之外的点）通过 gl_PointSize = 0 在 Shader 中剔除。
 */
export class LaserScanMaterial extends THREE.RawShaderMaterial {
  static readonly #MIN_PICKING_POINT_SIZE = 8

  public constructor({ picking = false }: { picking?: boolean } = {}) {
    super({
      glslVersion: THREE.GLSL3,
      vertexShader: /* glsl */ `
        precision highp float;
        precision highp int;
        uniform mat4 projectionMatrix, modelViewMatrix;

        uniform float pointSize;
        uniform float pixelRatio;
        uniform float angleMin, angleIncrement;
        uniform float rangeMin, rangeMax;

        // "position" attribute 存储 range（1维），Three.js 要求名字必须是 position
        in float position;
        in mediump vec4 color;
        out mediump vec4 vColor;

        void main() {
          // 超出范围的点通过 pointSize=0 剔除
          if (position < rangeMin || position > rangeMax) {
            gl_PointSize = 0.0;
            gl_Position = vec4(0.0);
            return;
          }
          vColor = color;
          float angle = angleMin + angleIncrement * float(gl_VertexID);
          vec4 pos = vec4(position * cos(angle), position * sin(angle), 0.0, 1.0);
          gl_Position = projectionMatrix * modelViewMatrix * pos;
          ${
            picking
              ? `gl_PointSize = pixelRatio * max(pointSize, ${LaserScanMaterial.#MIN_PICKING_POINT_SIZE.toFixed(1)});`
              : 'gl_PointSize = pixelRatio * pointSize;'
          }
        }
      `,
      fragmentShader: /* glsl */ `
        #ifdef GL_FRAGMENT_PRECISION_HIGH
          precision highp float;
        #else
          precision mediump float;
        #endif
        uniform bool isCircle;
        ${picking ? 'uniform vec4 objectId;' : 'in mediump vec4 vColor;'}
        out vec4 outColor;

        void main() {
          if (isCircle) {
            vec2 cxy = 2.0 * gl_PointCoord - 1.0;
            if (dot(cxy, cxy) > 1.0) { discard; }
          }
          ${picking ? 'outColor = objectId;' : 'outColor = vColor;'}
        }
      `
    })

    this.uniforms = {
      isCircle: { value: false },
      pointSize: { value: 1 },
      pixelRatio: { value: 1 },
      angleMin: { value: 0 },
      angleIncrement: { value: 0 },
      rangeMin: { value: 0 },
      rangeMax: { value: Infinity }
    }
    if (picking) {
      this.uniforms['objectId'] = { value: [NaN, NaN, NaN, NaN] }
    }
  }

  public updateUniforms(settings: LayerSettingsLaserScan, laserScan: NormalizedLaserScan): void {
    this.uniforms['isCircle']!.value = settings.pointShape === 'circle'
    this.uniforms['pointSize']!.value = settings.pointSize
    this.uniforms['angleMin']!.value = laserScan.start_angle
    const numRanges = laserScan.ranges.length
    this.uniforms['angleIncrement']!.value =
      numRanges > 1 ? (laserScan.end_angle - laserScan.start_angle) / (numRanges - 1) : 0
    this.uniforms['rangeMin']!.value = laserScan.range_min
    this.uniforms['rangeMax']!.value = laserScan.range_max
    this.uniformsNeedUpdate = true

    const transparent = colorHasTransparency(settings)
    if (transparent !== this.transparent) {
      this.transparent = transparent
      this.depthWrite = !this.transparent
      this.needsUpdate = true
    }
  }

  public setPixelRatio(pixelRatio: number): void {
    this.uniforms['pixelRatio']!.value = pixelRatio
  }
}

// ─────────────────────────────────────────────────────────────────────────────
// Normalization
// ─────────────────────────────────────────────────────────────────────────────

function normalizeRosLaserScan(message: PartialMessage<RosLaserScan>): NormalizedLaserScan {
  return {
    timestamp: normalizeTime(message.header?.stamp),
    frame_id: message.header?.frame_id ?? '',
    pose: emptyPose(),
    start_angle: message.angle_min ?? 0,
    end_angle: message.angle_max ?? 0,
    range_min: message.range_min ?? -Infinity,
    range_max: message.range_max ?? Infinity,
    ranges: normalizeFloat32Array(message.ranges),
    intensities: normalizeFloat32Array(message.intensities)
  }
}
