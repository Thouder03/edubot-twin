// SPDX-FileCopyrightText: Copyright (C) 2023-2025 Bayerische Motoren Werke Aktiengesellschaft (BMW AG)<lichtblick@bmwgroup.com>
// SPDX-License-Identifier: MPL-2.0
//
// Ported from lichtblick/renderables/PointClouds.ts
// Adaptations:
//  - ROS1/PointCloud2 only (removed Foxglove PointCloud schema)
//  - Replaced lodash groupBy with native Map
//  - Replaced @lichtblick/rostime toNanoSec with local bigint arithmetic
//  - Retained Stixel (vertical bar) visualization
//  - Adjusted import paths to local core/ structure

import * as THREE from 'three'

import { SettingsTreeAction, MessageEvent } from '../core/lichtblick-shim'
import type { RosValue } from '../core/lichtblick-shim'
import {
  DEFAULT_POINT_SETTINGS,
  LayerSettingsPointExtension,
  pointSettingsNode,
  PointsRenderable,
  RenderObjectHistory,
  createPickingMaterial,
  createInstancePickingMaterial,
  createGeometry,
  pointCloudMaterial,
  pointCloudColorEncoding,
  POINT_CLOUD_REQUIRED_FIELDS
} from '../core/pointExtensionUtils'
import {
  colorHasTransparency,
  getColorConverter,
  autoSelectColorSettings,
  colorFieldComputedPrefix,
  NEEDS_MIN_MAX
} from '../core/colorMode'
import { DynamicBufferGeometry } from '../core/DynamicBufferGeometry'
import type { AnyRendererSubscription, IRenderer } from '../core/IRenderer'
import { BaseUserData, Renderable } from '../core/Renderable'
import { PartialMessage, PartialMessageEvent, SceneExtension } from '../core/SceneExtension'
import type { SettingsTreeEntry, SettingsTreeNodeWithActionHandler } from '../core/SettingsManager'
import { normalizeHeader, normalizePose, normalizeByteArray } from '../core/normalizeMessages'
import {
  ColorRGBA,
  PointCloud2,
  PointField,
  PointFieldType,
  POINTCLOUD_DATATYPES as ROS_POINTCLOUD_DATATYPES
} from '../core/ros'
import type { Pose } from '../core/transforms'
import { FieldReader, getReader, isSupportedField } from './pointClouds/fieldReaders'

// ─────────────────────────────────────────────────────────────────────────────
// 类型定义
// ─────────────────────────────────────────────────────────────────────────────

type LayerSettingsPointClouds = LayerSettingsPointExtension & {
  stixelsEnabled: boolean
}

const DEFAULT_SETTINGS: LayerSettingsPointClouds = {
  ...DEFAULT_POINT_SETTINGS,
  stixelsEnabled: false
}

type PointCloudFieldReaders = {
  xReader: FieldReader
  yReader: FieldReader
  zReader: FieldReader
  packedColorReader: FieldReader
  redReader: FieldReader
  greenReader: FieldReader
  blueReader: FieldReader
  alphaReader: FieldReader
}

const INVALID_POINTCLOUD = 'INVALID_POINTCLOUD'

// ─────────────────────────────────────────────────────────────────────────────
// 临时变量（避免 GC 压力）
// ─────────────────────────────────────────────────────────────────────────────

const tempColor: ColorRGBA = { r: 0, g: 0, b: 0, a: 0 }
const tempMinMaxColor: [number, number] = [0, 0]
const tempFieldReaders: PointCloudFieldReaders = {
  xReader: zeroReader,
  yReader: zeroReader,
  zReader: zeroReader,
  packedColorReader: zeroReader,
  redReader: zeroReader,
  greenReader: zeroReader,
  blueReader: zeroReader,
  alphaReader: zeroReader
}

// ─────────────────────────────────────────────────────────────────────────────
// PointCloudHistoryUserData
// ─────────────────────────────────────────────────────────────────────────────

type PointCloudHistoryUserData = BaseUserData & {
  settings: LayerSettingsPointClouds
  topic: string
  latestPointCloud: PointCloud2
  latestOriginalMessage: Record<string, RosValue> | undefined
  material: THREE.PointsMaterial
  pickingMaterial: THREE.ShaderMaterial
  instancePickingMaterial: THREE.ShaderMaterial
  stixelMaterial: THREE.LineBasicMaterial
}

type PointCloudUserData = BaseUserData & {
  pointCloud: PointCloud2
  originalMessage: Record<string, RosValue> | undefined
}

// ─────────────────────────────────────────────────────────────────────────────
// PointCloudRenderable — 单帧点云（继承 PointsRenderable）
// ─────────────────────────────────────────────────────────────────────────────

class PointCloudRenderable extends PointsRenderable<PointCloudUserData> {
  public override details(): Record<string, RosValue> {
    return this.userData.originalMessage ?? {}
  }

  public override instanceDetails(instanceId: number): Record<string, RosValue> | undefined {
    const pointCloud = this.userData.pointCloud
    const data = pointCloud.data
    const stride = pointCloud.point_step
    const view = new DataView(data.buffer, data.byteOffset, data.byteLength)
    const details: Record<string, RosValue> = {}

    for (const field of pointCloud.fields) {
      const pointOffset = instanceId * stride
      const reader = getReader(field, stride)
      if (reader) {
        details[field.name] = reader(view, pointOffset)
      }
    }

    return details
  }
}

// ─────────────────────────────────────────────────────────────────────────────
// StixelsRenderable — 竖棒可视化
// ─────────────────────────────────────────────────────────────────────────────

class StixelsRenderable extends Renderable<BaseUserData, /*TRenderer=*/ undefined> {
  #stixels: THREE.LineSegments<DynamicBufferGeometry, THREE.LineBasicMaterial>
  public readonly geometry: DynamicBufferGeometry

  public constructor(
    name: string,
    userData: BaseUserData,
    geometry: DynamicBufferGeometry,
    material: THREE.LineBasicMaterial
  ) {
    super(name, undefined, userData)
    this.geometry = geometry
    const stixels = new THREE.LineSegments<DynamicBufferGeometry, THREE.LineBasicMaterial>(
      geometry,
      material
    )
    stixels.frustumCulled = false
    stixels.name = `${userData.topic}:PointCloud:stixels`
    this.#stixels = stixels
    this.add(stixels)
  }

  public override dispose(): void {
    this.#stixels.geometry.dispose()
  }

  public updateMaterial(material: THREE.LineBasicMaterial): void {
    this.#stixels.material = material
  }
}

// ─────────────────────────────────────────────────────────────────────────────
// PointCloudHistoryRenderable — 管理多帧历史（decayTime 支持）
// ─────────────────────────────────────────────────────────────────────────────

export class PointCloudHistoryRenderable extends Renderable<PointCloudHistoryUserData> {
  public override pickable = false // Picking 由子 Renderable 处理
  #pointsHistory: RenderObjectHistory<PointCloudRenderable>
  #stixelsHistory: RenderObjectHistory<StixelsRenderable>

  public constructor(topic: string, renderer: IRenderer, userData: PointCloudHistoryUserData) {
    super(topic, renderer, userData)

    const isDecay = userData.settings.decayTime > 0
    const geometry = createGeometry(topic, isDecay ? THREE.StaticDrawUsage : THREE.DynamicDrawUsage)

    const points = new PointCloudRenderable(
      topic,
      {
        receiveTime: -1n,
        messageTime: -1n,
        frameId: '',
        pose: userData.latestPointCloud.header
          ? normalizePose(undefined)
          : normalizePose(undefined),
        settingsPath: [],
        settings: { visible: false },
        topic,
        pointCloud: userData.latestPointCloud,
        originalMessage: userData.latestOriginalMessage
      },
      geometry,
      userData.material,
      userData.pickingMaterial,
      userData.instancePickingMaterial
    )
    this.#pointsHistory = new RenderObjectHistory({
      initial: {
        messageTime: userData.messageTime,
        receiveTime: userData.receiveTime,
        renderable: points
      },
      parentRenderable: this,
      renderer
    })
    this.add(points)

    const stixelGeometry = createStixelGeometry(
      topic,
      isDecay ? THREE.StaticDrawUsage : THREE.DynamicDrawUsage
    )
    const stixels = new StixelsRenderable(
      topic,
      {
        receiveTime: -1n,
        messageTime: -1n,
        frameId: '',
        pose: normalizePose(undefined),
        settingsPath: [],
        settings: { visible: false },
        topic
      },
      stixelGeometry,
      userData.stixelMaterial
    )
    this.#stixelsHistory = new RenderObjectHistory({
      initial: {
        messageTime: userData.messageTime,
        receiveTime: userData.receiveTime,
        renderable: stixels
      },
      parentRenderable: this,
      renderer
    })
    this.add(stixels)
  }

  public override dispose(): void {
    this.userData.latestOriginalMessage = undefined
    this.userData.material.dispose()
    this.userData.pickingMaterial.dispose()
    this.userData.instancePickingMaterial.dispose()
    this.userData.stixelMaterial.dispose()
    this.#pointsHistory.dispose()
    this.#stixelsHistory.dispose()
    super.dispose()
  }

  public updatePointCloud(
    this: PointCloudHistoryRenderable,
    pointCloud: PointCloud2,
    originalMessage: Record<string, RosValue> | undefined,
    settings: LayerSettingsPointClouds,
    receiveTime: bigint
  ): void {
    const stamp = pointCloud.header.stamp
    const messageTime = BigInt(stamp.sec) * 1_000_000_000n + BigInt(stamp.nsec)
    this.userData.receiveTime = receiveTime
    this.userData.messageTime = messageTime
    this.userData.frameId = this.renderer.normalizeFrameId(pointCloud.header.frame_id)
    this.userData.latestPointCloud = pointCloud
    this.userData.latestOriginalMessage = originalMessage

    const prevSettings = this.userData.settings
    const prevIsDecay = prevSettings.decayTime > 0
    this.userData.settings = settings

    let material = this.userData.material
    let stixelMaterial = this.userData.stixelMaterial
    const needsRebuild =
      colorHasTransparency(settings) !== material.transparent ||
      pointCloudColorEncoding(settings) !== pointCloudColorEncoding(prevSettings) ||
      settings.pointShape !== prevSettings.pointShape

    const pointsHistory = this.#pointsHistory
    const stixelsHistory = this.#stixelsHistory

    if (needsRebuild) {
      material.dispose()
      material = pointCloudMaterial(settings)
      this.userData.material = material
      pointsHistory.forEach((entry) => {
        entry.renderable.updateMaterial(material)
      })

      stixelMaterial.dispose()
      stixelMaterial = createStixelMaterial(settings)
      this.userData.stixelMaterial = stixelMaterial
      stixelsHistory.forEach((entry) => {
        entry.renderable.updateMaterial(stixelMaterial)
      })
    } else {
      material.size = settings.pointSize
    }

    const stixelsEnabledChanged = prevSettings.stixelsEnabled !== settings.stixelsEnabled
    if (!settings.stixelsEnabled && stixelsEnabledChanged) {
      stixelsHistory.clearHistory()
    }

    if (!this.#validatePointCloud(pointCloud)) {
      return
    }

    if (!this.#getPointCloudFieldReaders(tempFieldReaders, pointCloud, settings)) {
      return
    }

    const latestPointsEntry = pointsHistory.latest()
    latestPointsEntry.receiveTime = receiveTime
    latestPointsEntry.messageTime = messageTime
    latestPointsEntry.renderable.userData.pose = emptyPose()
    latestPointsEntry.renderable.userData.pointCloud = pointCloud
    latestPointsEntry.renderable.userData.originalMessage = originalMessage

    const pointCount = Math.trunc(pointCloud.data.length / pointCloud.point_step)
    const latestPoints = latestPointsEntry.renderable
    latestPointsEntry.renderable.geometry.resize(pointCount)
    const positionAttribute = latestPoints.geometry.attributes['position']!
    const colorAttribute = latestPoints.geometry.attributes['color']!

    const latestStixelEntry = stixelsHistory.latest()

    const isDecay = settings.decayTime > 0
    if (!isDecay && prevIsDecay !== isDecay) {
      latestPointsEntry.renderable.geometry.setUsage(THREE.DynamicDrawUsage)
      latestStixelEntry.renderable.geometry.setUsage(THREE.DynamicDrawUsage)
    }

    latestStixelEntry.receiveTime = receiveTime
    latestStixelEntry.messageTime = messageTime
    latestStixelEntry.renderable.userData.pose = latestPointsEntry.renderable.userData.pose
    if (settings.stixelsEnabled) {
      latestStixelEntry.renderable.geometry.resize(pointCount * 2)
    } else {
      latestStixelEntry.renderable.geometry.resize(0)
    }
    const stixelPositionAttribute = latestStixelEntry.renderable.geometry.attributes['position']!
    const stixelColorAttribute = latestStixelEntry.renderable.geometry.attributes['color']!

    this.#updatePointCloudBuffers(
      pointCloud,
      tempFieldReaders,
      pointCount,
      settings,
      positionAttribute,
      colorAttribute,
      stixelPositionAttribute,
      stixelColorAttribute
    )

    if (pointCount > 0) {
      latestPoints.geometry.computeBoundingSphere()
      if (settings.stixelsEnabled) {
        latestStixelEntry.renderable.geometry.computeBoundingSphere()
      }
    } else {
      latestPoints.geometry.boundingSphere = new THREE.Sphere()
      if (settings.stixelsEnabled) {
        latestStixelEntry.renderable.geometry.boundingSphere = new THREE.Sphere()
      }
    }
  }

  public startFrame(currentTime: bigint, renderFrameId: string, fixedFrameId: string): void {
    this.#pointsHistory.updateHistoryFromCurrentTime(currentTime)
    this.#pointsHistory.updatePoses(currentTime, renderFrameId, fixedFrameId)
    if (this.userData.settings.stixelsEnabled) {
      this.#stixelsHistory.updateHistoryFromCurrentTime(currentTime)
      this.#stixelsHistory.updatePoses(currentTime, renderFrameId, fixedFrameId)
    }
  }

  public pushHistory(
    this: PointCloudHistoryRenderable,
    pointCloud: PointCloud2,
    originalMessage: Record<string, RosValue> | undefined,
    settings: LayerSettingsPointClouds,
    receiveTime: bigint
  ): void {
    const stamp = pointCloud.header.stamp
    const messageTime = BigInt(stamp.sec) * 1_000_000_000n + BigInt(stamp.nsec)
    const pointsHistory = this.#pointsHistory
    const stixelsHistory = this.#stixelsHistory
    const material = this.userData.material
    const stixelMaterial = this.userData.stixelMaterial
    const topic = this.userData.topic

    const geometry = createGeometry(topic, THREE.StaticDrawUsage)
    const points = new PointCloudRenderable(
      topic,
      {
        receiveTime: -1n,
        messageTime: -1n,
        frameId: '',
        pose: emptyPose(),
        settingsPath: [],
        settings: { visible: false },
        topic,
        pointCloud,
        originalMessage
      },
      geometry,
      material,
      this.userData.pickingMaterial,
      this.userData.instancePickingMaterial
    )
    pointsHistory.addHistoryEntry({ receiveTime, messageTime, renderable: points })
    this.add(points)

    if (settings.stixelsEnabled) {
      const stixelGeometry = createStixelGeometry(topic, THREE.StaticDrawUsage)
      const stixels = new StixelsRenderable(
        topic,
        {
          receiveTime: -1n,
          messageTime: -1n,
          frameId: '',
          pose: emptyPose(),
          settingsPath: [],
          settings: { visible: false },
          topic
        },
        stixelGeometry,
        stixelMaterial
      )
      stixelsHistory.addHistoryEntry({ receiveTime, messageTime, renderable: stixels })
      this.add(stixels)
    }
  }

  #invalidError(message: string): void {
    this.renderer.settings.errors.addToTopic(this.userData.topic, INVALID_POINTCLOUD, message)
    const lastEntry = this.#pointsHistory.latest()
    lastEntry.renderable.geometry.resize(0)
  }

  #validatePointCloud(pointCloud: PointCloud2): boolean {
    const data = pointCloud.data

    if (pointCloud.is_bigendian) {
      this.#invalidError('PointCloud2 is_bigendian=true is not supported')
      return false
    }

    if (pointCloud.point_step === 0) {
      this.#invalidError('PointCloud2 point_step=0 is invalid')
      return false
    }

    if (data.length % pointCloud.point_step !== 0) {
      this.#invalidError(
        `PointCloud2 data length ${data.length} is not a multiple of point_step ${pointCloud.point_step}`
      )
      return false
    }

    if (pointCloud.fields.length === 0) {
      this.#invalidError('PointCloud2 has no fields')
      return false
    }

    return true
  }

  #getPointCloudFieldReaders(
    output: PointCloudFieldReaders,
    pointCloud: PointCloud2,
    settings: LayerSettingsPointClouds
  ): boolean {
    let xReader: FieldReader | undefined
    let yReader: FieldReader | undefined
    let zReader: FieldReader | undefined
    let packedColorReader: FieldReader | undefined
    let redReader: FieldReader | undefined
    let greenReader: FieldReader | undefined
    let blueReader: FieldReader | undefined
    let alphaReader: FieldReader | undefined

    const stride = pointCloud.point_step

    let minBytesPerPoint = 0

    for (const field of pointCloud.fields) {
      if (!isSupportedField(field)) continue
      const type = field.datatype

      if (field.offset < 0) {
        this.#invalidError(
          `PointCloud field "${field.name}" has invalid offset ${field.offset}. Must be >= 0`
        )
        return false
      }

      if (field.name === 'x') {
        xReader = getReader(field, stride)
        if (!xReader) {
          this.#invalidError(
            `PointCloud field "x" is invalid. type=${pointFieldTypeName(type)}, offset=${field.offset}, stride=${stride}`
          )
          return false
        }
      } else if (field.name === 'y') {
        yReader = getReader(field, stride)
        if (!yReader) {
          this.#invalidError(
            `PointCloud field "y" is invalid. type=${pointFieldTypeName(type)}, offset=${field.offset}, stride=${stride}`
          )
          return false
        }
      } else if (field.name === 'z') {
        zReader = getReader(field, stride)
        if (!zReader) {
          this.#invalidError(
            `PointCloud field "z" is invalid. type=${pointFieldTypeName(type)}, offset=${field.offset}, stride=${stride}`
          )
          return false
        }
      } else if (field.name === 'red') {
        redReader = getReader(field, stride, /*normalize*/ true)
      } else if (field.name === 'green') {
        greenReader = getReader(field, stride, /*normalize*/ true)
      } else if (field.name === 'blue') {
        blueReader = getReader(field, stride, /*normalize*/ true)
      } else if (field.name === 'alpha') {
        alphaReader = getReader(field, stride, /*normalize*/ true)
      }

      const byteWidth = pointFieldWidth(type)
      minBytesPerPoint = Math.max(minBytesPerPoint, field.offset + byteWidth)

      if (field.name === settings.colorField) {
        // 若颜色模式为 rgb/rgba 且字段宽度 >= 4 字节，强制按 UINT32 解包颜色
        const forceType =
          (settings.colorMode === 'rgb' || settings.colorMode === 'rgba') && byteWidth >= 4
            ? PointFieldType.UINT32
            : undefined
        packedColorReader = getReader(field, stride, /*normalize*/ false, forceType)
        if (!packedColorReader) {
          this.#invalidError(
            `PointCloud field "${field.name}" is invalid. type=${pointFieldTypeName(type)}, offset=${field.offset}, stride=${stride}`
          )
          return false
        }
      }
    }

    // 距离作为颜色字段（computed mode）
    if (settings.colorField === colorFieldComputedPrefix + 'distance') {
      packedColorReader = (view: DataView, pointOffset: number) => {
        return Math.hypot(
          xReader?.(view, pointOffset) ?? 0,
          yReader?.(view, pointOffset) ?? 0,
          zReader?.(view, pointOffset) ?? 0
        )
      }
    }

    if (minBytesPerPoint > stride) {
      this.#invalidError(
        `PointCloud stride ${stride} is less than minimum bytes per point ${minBytesPerPoint}`
      )
      return false
    }

    const posReaderCount = (xReader ? 1 : 0) + (yReader ? 1 : 0) + (zReader ? 1 : 0)
    if (posReaderCount < 2) {
      this.#invalidError('PointCloud must contain at least two of x/y/z fields')
      return false
    }

    output.xReader = xReader ?? zeroReader
    output.yReader = yReader ?? zeroReader
    output.zReader = zReader ?? zeroReader
    output.packedColorReader = packedColorReader ?? xReader ?? yReader ?? zReader ?? zeroReader
    output.redReader = redReader ?? zeroReader
    output.greenReader = greenReader ?? zeroReader
    output.blueReader = blueReader ?? zeroReader
    output.alphaReader = alphaReader ?? zeroReader
    return true
  }

  #minMaxColorValues(
    output: [number, number],
    colorReader: FieldReader,
    view: DataView,
    pointCount: number,
    pointStep: number,
    settings: LayerSettingsPointClouds
  ): void {
    let minColorValue = settings.minValue ?? Number.POSITIVE_INFINITY
    let maxColorValue = settings.maxValue ?? Number.NEGATIVE_INFINITY
    if (
      NEEDS_MIN_MAX.includes(settings.colorMode) &&
      (settings.minValue == undefined || settings.maxValue == undefined)
    ) {
      for (let i = 0; i < pointCount; i++) {
        const pointOffset = i * pointStep
        const colorValue = colorReader(view, pointOffset)
        minColorValue = Math.min(minColorValue, colorValue)
        maxColorValue = Math.max(maxColorValue, colorValue)
      }
      minColorValue = settings.minValue ?? minColorValue
      maxColorValue = settings.maxValue ?? maxColorValue
    }
    output[0] = minColorValue
    output[1] = maxColorValue
  }

  #updatePointCloudBuffers(
    pointCloud: PointCloud2,
    readers: PointCloudFieldReaders,
    pointCount: number,
    settings: LayerSettingsPointClouds,
    positionAttribute: THREE.BufferAttribute,
    colorAttribute: THREE.BufferAttribute,
    stixelPositionAttribute: THREE.BufferAttribute,
    stixelColorAttribute: THREE.BufferAttribute
  ): void {
    const data = pointCloud.data
    const view = new DataView(data.buffer, data.byteOffset, data.byteLength)
    const pointStep = pointCloud.point_step
    const {
      xReader,
      yReader,
      zReader,
      packedColorReader,
      redReader,
      greenReader,
      blueReader,
      alphaReader
    } = readers

    // 更新位置属性
    for (let i = 0; i < pointCount; i++) {
      const pointOffset = i * pointStep
      const x = xReader(view, pointOffset)
      const y = yReader(view, pointOffset)
      const z = zReader(view, pointOffset)
      positionAttribute.setXYZ(i, x, y, z)
      if (settings.stixelsEnabled) {
        stixelPositionAttribute.setXYZ(i * 2, x, y, z)
        stixelPositionAttribute.setXYZ(i * 2 + 1, x, y, 0)
      }
    }

    // 更新颜色属性
    if (settings.colorMode === 'rgba-fields') {
      for (let i = 0; i < pointCount; i++) {
        const pointOffset = i * pointStep
        const r = redReader(view, pointOffset)
        const g = greenReader(view, pointOffset)
        const b = blueReader(view, pointOffset)
        const a = alphaReader(view, pointOffset)
        colorAttribute.setXYZW(i, r * 255, g * 255, b * 255, a * 255)
        if (settings.stixelsEnabled) {
          stixelColorAttribute.setXYZW(i * 2, r * 255, g * 255, b * 255, a * 255)
          stixelColorAttribute.setXYZW(i * 2 + 1, r * 255, g * 255, b * 255, a * 255)
        }
      }
    } else {
      this.#minMaxColorValues(
        tempMinMaxColor,
        packedColorReader,
        view,
        pointCount,
        pointStep,
        settings
      )
      const [minColorValue, maxColorValue] = tempMinMaxColor

      const colorConverter = getColorConverter(
        settings as typeof settings & { colorMode: typeof settings.colorMode },
        minColorValue,
        maxColorValue
      )

      for (let i = 0; i < pointCount; i++) {
        const pointOffset = i * pointStep
        const colorValue = packedColorReader(view, pointOffset)
        colorConverter(tempColor, colorValue)
        colorAttribute.setXYZW(
          i,
          tempColor.r * 255,
          tempColor.g * 255,
          tempColor.b * 255,
          tempColor.a * 255
        )
        if (settings.stixelsEnabled) {
          stixelColorAttribute.setXYZW(
            i * 2,
            tempColor.r * 255,
            tempColor.g * 255,
            tempColor.b * 255,
            tempColor.a * 255
          )
          stixelColorAttribute.setXYZW(
            i * 2 + 1,
            tempColor.r * 255,
            tempColor.g * 255,
            tempColor.b * 255,
            tempColor.a * 255
          )
        }
      }
    }

    positionAttribute.needsUpdate = true
    colorAttribute.needsUpdate = true
    stixelPositionAttribute.needsUpdate = true
  }
}

// ─────────────────────────────────────────────────────────────────────────────
// PointClouds — SceneExtension 主类
// ─────────────────────────────────────────────────────────────────────────────

export class PointClouds extends SceneExtension<PointCloudHistoryRenderable> {
  public static extensionId = 'foxglove.PointClouds'
  #fieldsByTopic = new Map<string, string[]>()

  public constructor(renderer: IRenderer, name: string = PointClouds.extensionId) {
    super(name, renderer)
  }

  public override getSubscriptions(): readonly AnyRendererSubscription[] {
    return [
      {
        type: 'schema',
        schemaNames: ROS_POINTCLOUD_DATATYPES,
        subscription: {
          handler: this.#handleRosPointCloud as (messageEvent: unknown) => void,
          filterQueue: this.#processMessageQueue.bind(this) as any
        }
      }
    ]
  }

  // 按话题去重：若无 decayTime 只保留最后一帧
  #processMessageQueue<T>(msgs: MessageEvent<T>[]): MessageEvent<T>[] {
    if (msgs.length === 0) return msgs

    const msgsByTopic = new Map<string, MessageEvent<T>[]>()
    for (const msg of msgs) {
      let arr = msgsByTopic.get(msg.topic)
      if (!arr) {
        arr = []
        msgsByTopic.set(msg.topic, arr)
      }
      arr.push(msg)
    }

    const finalQueue: MessageEvent<T>[] = []
    for (const [topic, topicMsgs] of msgsByTopic) {
      const userSettings = this.renderer.config.topics[topic] as
        | Partial<LayerSettingsPointClouds>
        | undefined
      if ((userSettings?.decayTime ?? DEFAULT_SETTINGS.decayTime) > 0) {
        finalQueue.push(...topicMsgs)
        continue
      }
      const latestMsg = topicMsgs[topicMsgs.length - 1]
      if (latestMsg) {
        finalQueue.push(latestMsg)
      }
    }
    return finalQueue
  }

  // ─── 设置树 ───────────────────────────────────────────────────────────────

  public override settingsNodes(): SettingsTreeEntry[] {
    const configTopics = this.renderer.config.topics
    const handler = this.handleSettingsAction
    const entries: SettingsTreeEntry[] = []

    for (const topic of this.renderer.topics ?? []) {
      if (!ROS_POINTCLOUD_DATATYPES.has(topic.schemaName)) continue

      const config = (configTopics[topic.name] ?? {}) as Partial<LayerSettingsPointClouds>
      const messageFields = this.#fieldsByTopic.get(topic.name) ?? POINT_CLOUD_REQUIRED_FIELDS

      const node: SettingsTreeNodeWithActionHandler = pointSettingsNode(
        topic,
        messageFields,
        config
      )

      // 追加 Stixel 开关
      node.fields!['stixelsEnabled'] = {
        label: '竖棒视图 (Stixel)',
        input: 'boolean',
        value: config.stixelsEnabled ?? DEFAULT_SETTINGS.stixelsEnabled
      }
      node.handler = handler
      node.icon = 'Points'
      entries.push({ path: ['topics', topic.name], node })
    }

    return entries
  }

  // ─── 设置操作 ─────────────────────────────────────────────────────────────

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
        const prev = (draft.topics[topicName] ?? {}) as Partial<LayerSettingsPointClouds>
        draft.topics[topicName] = { ...prev, visible } as any
      })
      this.updateSettingsTree()
      return
    }

    // path 长度 = 3：['topics', topicName, field] → 字段更新
    if (path.length !== 3) return

    this.saveSetting(path as string[], action.payload.value)

    const renderable = this.renderables.get(topicName)
    if (!renderable) return

    const prevSettings = this.renderer.config.topics[topicName] as
      | Partial<LayerSettingsPointClouds>
      | undefined
    const settings = { ...DEFAULT_SETTINGS, ...prevSettings }
    renderable.userData.settings = settings

    renderable.updatePointCloud(
      renderable.userData.latestPointCloud,
      renderable.userData.latestOriginalMessage,
      settings,
      renderable.userData.receiveTime
    )
  }

  // ─── startFrame：手动管理 History pose 更新 ───────────────────────────────

  public override startFrame(
    currentTime: bigint,
    renderFrameId: string,
    fixedFrameId: string
  ): void {
    // 委托给 HistoryRenderable.startFrame() 处理子 History 的 pose 更新
    // 不 dispose 隐藏中的 renderable（否则重新开启时数据丢失）
    for (const renderable of this.renderables.values()) {
      renderable.visible = renderable.userData.settings.visible
      if (!renderable.visible) continue
      renderable.startFrame(currentTime, renderFrameId, fixedFrameId)
    }
  }

  // ─── 消息处理 ─────────────────────────────────────────────────────────────

  #handleRosPointCloud = (messageEvent: PartialMessageEvent<PointCloud2>): void => {
    const { topic, schemaName } = messageEvent
    const pointCloud = normalizePointCloud2(messageEvent.message)
    const stamp = pointCloud.header.stamp
    const receiveTime =
      BigInt(messageEvent.receiveTime.sec) * 1_000_000_000n + BigInt(messageEvent.receiveTime.nsec)
    const messageTime = BigInt(stamp.sec) * 1_000_000_000n + BigInt(stamp.nsec)
    const frameId = pointCloud.header.frame_id

    this.#handlePointCloud(
      topic,
      schemaName,
      pointCloud,
      receiveTime,
      messageTime,
      messageEvent.message as Record<string, RosValue>,
      frameId
    )
  }

  #handlePointCloud(
    topic: string,
    schemaName: string,
    pointCloud: PointCloud2,
    receiveTime: bigint,
    messageTime: bigint,
    originalMessage: Record<string, RosValue>,
    frameId: string
  ): void {
    // 调试日志：检查解析的点云数据是否为空
    if (pointCloud.data.length === 0) {
      console.warn(
        `[PointClouds] 收到话题 ${topic} 的点云为空 (length=0)，请检查 roslibjs 传来的 data 类型！`
      )
    }

    // 更新话题→字段名映射
    let fields = this.#fieldsByTopic.get(topic)
    const numSupportedFields = pointCloud.fields.reduce(
      (n, f) => n + (isSupportedField(f) ? 1 : 0),
      0
    )
    let fieldsUpdated = false
    if (fields?.length !== numSupportedFields) {
      fields = pointCloud.fields.filter(isSupportedField).map((f) => f.name)
      this.#fieldsByTopic.set(topic, fields)
      fieldsUpdated = true
      this.updateSettingsTree()
    }

    let renderable = this.renderables.get(topic)
    if (!renderable) {
      const userSettings = this.renderer.config.topics[topic] as
        | Partial<LayerSettingsPointClouds>
        | undefined
      const settings = { ...DEFAULT_SETTINGS, ...userSettings }

      // 首次收到消息时自动选择颜色字段
      if (settings.colorField == undefined && fieldsUpdated) {
        autoSelectColorSettings(settings, fields, {
          supportsPackedRgbModes: ROS_POINTCLOUD_DATATYPES.has(schemaName),
          supportsRgbaFieldsMode: false
        })
        this.renderer.updateConfig((draft) => {
          draft.topics[topic] = {
            ...userSettings,
            colorField: settings.colorField,
            colorMode: settings.colorMode,
            colorMap: settings.colorMap
          } as any
        })
        this.updateSettingsTree()
      }

      const material = pointCloudMaterial(settings)
      const pickingMaterial = createPickingMaterial(settings)
      const instancePickingMaterial = createInstancePickingMaterial(settings)
      const stixelMaterial = createStixelMaterial(settings)

      renderable = new PointCloudHistoryRenderable(topic, this.renderer, {
        receiveTime,
        messageTime,
        frameId: this.renderer.normalizeFrameId(frameId),
        pose: emptyPose(),
        settingsPath: ['topics', topic],
        settings,
        topic,
        latestPointCloud: pointCloud,
        latestOriginalMessage: originalMessage,
        material,
        pickingMaterial,
        instancePickingMaterial,
        stixelMaterial
      })

      this.add(renderable)
      this.renderables.set(topic, renderable)
    }

    const { settings } = renderable.userData

    if (settings.decayTime > 0) {
      renderable.pushHistory(pointCloud, originalMessage, settings, receiveTime)
    }

    renderable.updatePointCloud(pointCloud, originalMessage, settings, receiveTime)
  }
}

// ─────────────────────────────────────────────────────────────────────────────
// 工具函数
// ─────────────────────────────────────────────────────────────────────────────

function emptyPose(): Pose {
  return {
    position: { x: 0, y: 0, z: 0 },
    orientation: { x: 0, y: 0, z: 0, w: 1 }
  }
}

function zeroReader(): number {
  return 0
}

function pointFieldTypeName(type: PointFieldType): string {
  return PointFieldType[type as number] ?? `${type}`
}

function pointFieldWidth(type: PointFieldType): number {
  switch (type) {
    case PointFieldType.INT8:
    case PointFieldType.UINT8:
      return 1
    case PointFieldType.INT16:
    case PointFieldType.UINT16:
      return 2
    case PointFieldType.INT32:
    case PointFieldType.UINT32:
    case PointFieldType.FLOAT32:
      return 4
    case PointFieldType.FLOAT64:
      return 8
    default:
      return 0
  }
}

function normalizePointField(field: PartialMessage<PointField> | undefined): PointField {
  if (!field) {
    return { name: '', offset: 0, datatype: PointFieldType.UNKNOWN, count: 0 }
  }
  return {
    name: field.name ?? '',
    offset: field.offset ?? 0,
    datatype: field.datatype ?? PointFieldType.UNKNOWN,
    count: field.count ?? 0
  }
}

function normalizePointCloud2(message: PartialMessage<PointCloud2>): PointCloud2 {
  return {
    header: normalizeHeader(message.header),
    height: message.height ?? 0,
    width: message.width ?? 0,
    fields: message.fields?.map(normalizePointField) ?? [],
    is_bigendian: message.is_bigendian ?? false,
    point_step: message.point_step ?? 0,
    row_step: message.row_step ?? 0,
    data: normalizeByteArray(message.data),
    is_dense: message.is_dense ?? false
  }
}

export function createStixelMaterial(settings: LayerSettingsPointClouds): THREE.LineBasicMaterial {
  const transparent = colorHasTransparency(settings)
  return new THREE.LineBasicMaterial({
    vertexColors: true,
    transparent,
    depthWrite: true
  })
}

function createStixelGeometry(topic: string, usage: THREE.Usage): DynamicBufferGeometry {
  const geometry = new DynamicBufferGeometry(usage)
  geometry.name = `${topic}:PointCloud:stixelGeometry`
  geometry.createAttribute('position', Float32Array, 3)
  geometry.createAttribute('color', Uint8Array, 4, true)
  return geometry
}
