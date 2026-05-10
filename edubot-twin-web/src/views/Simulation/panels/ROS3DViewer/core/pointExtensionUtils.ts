// SPDX-FileCopyrightText: Copyright (C) 2023-2025 Bayerische Motoren Werke Aktiengesellschaft (BMW AG)<lichtblick@bmwgroup.com>
// SPDX-License-Identifier: MPL-2.0

// This Source Code Form is subject to the terms of the Mozilla Public
// License, v2.0. If a copy of the MPL was not distributed with this
// file, You can obtain one at http://mozilla.org/MPL/2.0/
//
// Ported from lichtblick/renderables/pointExtensionUtils.ts
// Adaptations: removed i18next, removed PointCloud datatype checks.
//              LaserScanMaterial forward-import removed to avoid circular dependency.

import * as THREE from 'three'

import type { SettingsTreeNode, Topic } from './lichtblick-shim'
import { DynamicBufferGeometry } from './DynamicBufferGeometry'
import type { IRenderer } from './IRenderer'
import { BaseUserData, Renderable } from './Renderable'
import { rgbaToCssString } from './color'
import { MISSING_TRANSFORM, missingTransformMessage } from './SceneExtension'
import { BaseSettings } from './settings'
import { MAX_DURATION } from './transforms'
import { updatePose } from './updatePose'
import {
  colorHasTransparency,
  ColorModeSettings,
  colorModeSettingsFields,
  FS_SRGB_TO_LINEAR
} from './colorMode'

// ─────────────────────────────────────────────────────────────────────────────
// Settings types
// ─────────────────────────────────────────────────────────────────────────────

export type LayerSettingsPointExtension = BaseSettings &
  ColorModeSettings & {
    pointSize: number
    pointShape: 'circle' | 'square'
    decayTime: number
  }

const DEFAULT_POINT_SIZE = 3.5
const DEFAULT_POINT_SHAPE = 'circle'
const DEFAULT_COLOR_MAP = 'turbo'
const DEFAULT_FLAT_COLOR = { r: 1, g: 1, b: 1, a: 1 }
const DEFAULT_MIN_COLOR = { r: 100 / 255, g: 47 / 255, b: 105 / 255, a: 1 }
const DEFAULT_MAX_COLOR = { r: 227 / 255, g: 177 / 255, b: 135 / 255, a: 1 }

/** 用于 LaserScans、VelodyneScans、PointClouds 的默认点云设置 */
export const DEFAULT_POINT_SETTINGS: LayerSettingsPointExtension = {
  visible: false,
  frameLocked: false,
  pointSize: DEFAULT_POINT_SIZE,
  pointShape: DEFAULT_POINT_SHAPE,
  decayTime: 0,
  colorMode: 'flat',
  flatColor: rgbaToCssString(DEFAULT_FLAT_COLOR),
  colorField: undefined,
  gradient: [rgbaToCssString(DEFAULT_MIN_COLOR), rgbaToCssString(DEFAULT_MAX_COLOR)],
  colorMap: DEFAULT_COLOR_MAP,
  explicitAlpha: 1,
  minValue: undefined,
  maxValue: undefined
}

export const POINT_CLOUD_REQUIRED_FIELDS = ['x', 'y', 'z']

// ─────────────────────────────────────────────────────────────────────────────
// Settings node builder
// ─────────────────────────────────────────────────────────────────────────────

/**
 * 为点云/激光雷达 topic 构建 Settings Tree 节点
 */
export function pointSettingsNode(
  _topic: Topic,
  messageFields: string[],
  config: Partial<LayerSettingsPointExtension>,
  defaultSettings: LayerSettingsPointExtension = DEFAULT_POINT_SETTINGS
): SettingsTreeNode {
  const pointSize = config.pointSize
  const pointShape = config.pointShape ?? 'circle'
  const decayTime = config.decayTime

  const colorModeFields = colorModeSettingsFields({
    msgFields: messageFields,
    config,
    defaults: defaultSettings,
    modifiers: {
      supportsPackedRgbModes: false,
      supportsRgbaFieldsMode: false
    }
  })

  const node: SettingsTreeNode = {
    visible: config.visible ?? defaultSettings.visible,
    fields: {
      pointSize: {
        label: '点大小',
        input: 'number' as const,
        step: 1,
        precision: 2,
        value: pointSize !== undefined ? pointSize : defaultSettings.pointSize,
        min: 0
      },
      pointShape: {
        label: '点形状',
        input: 'select' as const,
        options: [
          { label: '圆形', value: 'circle' },
          { label: '方形', value: 'square' }
        ],
        value: pointShape !== undefined ? pointShape : defaultSettings.pointShape
      },
      decayTime: {
        label: '衰减时间',
        input: 'number' as const,
        step: 0.5,
        placeholder: '0 秒（不衰减）',
        min: 0,
        precision: 3,
        value: decayTime !== undefined ? decayTime : defaultSettings.decayTime
      },
      ...colorModeFields
    }
  }

  return node
}

// ─────────────────────────────────────────────────────────────────────────────
// Geometry builder
// ─────────────────────────────────────────────────────────────────────────────

/**
 * 创建一个带 position(range) 和 color 属性的 DynamicBufferGeometry
 */
export function createGeometry(topic: string, usage: THREE.Usage): DynamicBufferGeometry {
  const geometry = new DynamicBufferGeometry(usage)
  geometry.name = `${topic}:PointScans:geometry`
  geometry.createAttribute('position', Float32Array, 3)
  geometry.createAttribute('color', Uint8Array, 4, true)
  return geometry
}

// ─────────────────────────────────────────────────────────────────────────────
// Material helpers
// ─────────────────────────────────────────────────────────────────────────────

// Material 类型使用 THREE.Material 基类，避免与 LaserScans.ts 的循环依赖
// LaserScanRenderable 在自身 constructor 中传入具体的 LaserScanMaterial 实例
type Material = THREE.Material

export function pointCloudColorEncoding<T extends LayerSettingsPointExtension>(
  settings: T
): 'srgb' | 'linear' {
  switch (settings.colorMode) {
    case 'flat':
    case 'colormap':
    case 'gradient':
      return 'linear'
    case 'rgb':
    case 'rgba':
    case 'rgba-fields':
      return 'srgb'
  }
}

// Fragment shader chunk — render GL_POINT as circle
const FS_POINTCLOUD_CIRCLE = /* glsl */ `
vec2 cxy = 2.0 * gl_PointCoord - 1.0;
if (dot(cxy, cxy) > 1.0) { discard; }
`

// Fragment shader chunk — sRGB to linear for PointsMaterial
const FS_POINTCLOUD_SRGB_TO_LINEAR = /* glsl */ `
outgoingLight = sRGBToLinear(outgoingLight);
`

export function pointCloudMaterial<T extends LayerSettingsPointExtension>(
  settings: T
): THREE.PointsMaterial {
  const transparent = colorHasTransparency(settings)
  const encoding = pointCloudColorEncoding(settings)
  const scale = settings.pointSize
  const shape = settings.pointShape

  const material = new THREE.PointsMaterial({
    vertexColors: true,
    size: scale,
    sizeAttenuation: false,
    transparent,
    depthWrite: true
  })

  material.customProgramCacheKey = () => `${shape}-${encoding}`
  material.onBeforeCompile = (shader) => {
    const SEARCH = '#include <opaque_fragment>'
    if (shape === 'circle') {
      shader.fragmentShader = shader.fragmentShader.replace(SEARCH, FS_POINTCLOUD_CIRCLE + SEARCH)
    }
    if (encoding === 'srgb') {
      shader.fragmentShader =
        FS_SRGB_TO_LINEAR +
        shader.fragmentShader.replace(SEARCH, FS_POINTCLOUD_SRGB_TO_LINEAR + SEARCH)
    }
  }

  return material
}

/**
 * 物体级拾取 Material（识别点击的是哪个 topic 对象）
 */
export function createPickingMaterial<T extends LayerSettingsPointExtension>(
  settings: T
): THREE.ShaderMaterial {
  const MIN_PICKING_POINT_SIZE = 8
  const pointSize = Math.max(settings.pointSize, MIN_PICKING_POINT_SIZE)
  return new THREE.ShaderMaterial({
    vertexShader: /* glsl */ `
      uniform float pointSize;
      void main() {
        gl_Position = projectionMatrix * modelViewMatrix * vec4(position, 1.0);
        gl_PointSize = pointSize;
      }
    `,
    fragmentShader: /* glsl */ `
      uniform vec4 objectId;
      void main() {
        gl_FragColor = objectId;
      }
    `,
    side: THREE.DoubleSide,
    uniforms: { pointSize: { value: pointSize }, objectId: { value: [NaN, NaN, NaN, NaN] } }
  })
}

/**
 * 实例级拾取 Material（识别点击的是第几个点）
 * 当前未启用，保留供未来扩展
 */
export function createInstancePickingMaterial<T extends LayerSettingsPointExtension>(
  settings: T
): THREE.ShaderMaterial {
  const MIN_PICKING_POINT_SIZE = 8
  const pointSize = Math.max(settings.pointSize, MIN_PICKING_POINT_SIZE)
  return new THREE.ShaderMaterial({
    vertexShader: /* glsl */ `
      uniform float pointSize;
      varying vec4 objectId;
      void main() {
        objectId = vec4(
          float((gl_VertexID >> 24) & 255) / 255.0,
          float((gl_VertexID >> 16) & 255) / 255.0,
          float((gl_VertexID >> 8) & 255) / 255.0,
          float(gl_VertexID & 255) / 255.0);
        gl_Position = projectionMatrix * modelViewMatrix * vec4(position, 1.0);
        gl_PointSize = pointSize;
      }
    `,
    fragmentShader: /* glsl */ `
      varying vec4 objectId;
      void main() {
        gl_FragColor = objectId;
      }
    `,
    side: THREE.DoubleSide,
    uniforms: { pointSize: { value: pointSize } }
  })
}

// ─────────────────────────────────────────────────────────────────────────────
// PointsRenderable
// ─────────────────────────────────────────────────────────────────────────────

/**
 * 点云 Renderable 基类，封装 THREE.Points 和三套 Material 管理。
 * 继承此类来添加特定消息类型的点云渲染（如 LaserScan）。
 */
export class PointsRenderable<TUserData extends BaseUserData = BaseUserData> extends Renderable<
  TUserData,
  undefined
> {
  #points: THREE.Points<DynamicBufferGeometry, Material>
  public readonly geometry: DynamicBufferGeometry
  /** 开启后 Picker 会对此 Renderable 进行实例级拾取 */
  public override pickableInstances = true

  public constructor(
    name: string,
    userData: TUserData,
    geometry: DynamicBufferGeometry,
    material: Material,
    pickingMaterial: THREE.Material,
    instancePickingMaterial: THREE.Material
  ) {
    super(name, undefined, userData)
    this.geometry = geometry

    const points = new THREE.Points<DynamicBufferGeometry, Material>(geometry, material)
    points.frustumCulled = false
    points.name = `${userData.topic}:PointCloud:points`
    points.userData = {
      pickingMaterial,
      instancePickingMaterial,
      pose: userData.pose
    }
    this.#points = points
    this.add(points)
  }

  public override dispose(): void {
    this.#points.geometry.dispose()
  }

  public updateMaterial(material: Material): void {
    this.#points.material = material
  }
}

// ─────────────────────────────────────────────────────────────────────────────
// RenderObjectHistory
// ─────────────────────────────────────────────────────────────────────────────

type RenderObjectHistoryUserData = BaseUserData & {
  topic: string
  settings: LayerSettingsPointExtension
}

type DisposableObject = THREE.Object3D & { dispose(): void }

export type HistoryEntry<TRenderable extends DisposableObject> = {
  receiveTime: bigint
  messageTime: bigint
  renderable: TRenderable
}

/**
 * 管理点云对象的时间历史，实现 decayTime 衰减效果。
 *
 * - decayTime = 0 时：始终只保留最新一帧（即时清理历史）
 * - decayTime > 0 时：保留最近 N 秒内的所有帧（拖尾效果），过期帧自动 dispose
 *
 * 用于 LaserScans 和 PointClouds 的时间轴回放与实时衰减功能。
 */
export class RenderObjectHistory<TRenderable extends DisposableObject> {
  #history: HistoryEntry<TRenderable>[]
  #parentRenderable: Renderable<RenderObjectHistoryUserData>
  #renderer: IRenderer

  public constructor({
    initial,
    renderer,
    parentRenderable
  }: {
    initial: HistoryEntry<TRenderable>
    renderer: IRenderer
    parentRenderable: Renderable<RenderObjectHistoryUserData>
  }) {
    this.#history = [initial]
    this.#renderer = renderer
    this.#parentRenderable = parentRenderable
  }

  public addHistoryEntry(entry: HistoryEntry<TRenderable>): void {
    this.#history.push(entry)
  }

  public forEach(callback: (entry: HistoryEntry<TRenderable>) => void): void {
    this.#history.forEach(callback)
  }

  /** 移除超过 decayTime 时限的历史帧 */
  public updateHistoryFromCurrentTime(currentTime: bigint): void {
    const pointsHistory = this.#history
    const decayTime = this.#parentRenderable.userData.settings.decayTime
    const expireTime =
      decayTime > 0 ? currentTime - BigInt(Math.round(decayTime * 1e9)) : MAX_DURATION
    while (pointsHistory.length > 1 && pointsHistory[0]!.receiveTime < expireTime) {
      const entry = this.#history.shift()!
      this.#parentRenderable.remove(entry.renderable)
      entry.renderable.dispose()
    }
  }

  /** 对历史中每一帧更新坐标系位姿变换 */
  public updatePoses(currentTime: bigint, renderFrameId: string, fixedFrameId: string): void {
    let hadTfError = false
    for (const entry of this.#history) {
      const srcTime = entry.messageTime
      const frameId = this.#parentRenderable.userData.frameId
      const updated = updatePose(
        entry.renderable,
        this.#renderer.transformTree,
        renderFrameId,
        fixedFrameId,
        frameId,
        currentTime,
        srcTime
      )
      if (!updated && !hadTfError) {
        const message = missingTransformMessage(renderFrameId, fixedFrameId, frameId)
        this.#renderer.settings.errors.add(
          this.#parentRenderable.userData.settingsPath,
          MISSING_TRANSFORM,
          message
        )
        hadTfError = true
      }
    }
  }

  public latest(): HistoryEntry<TRenderable> {
    if (this.#history.length === 0) {
      throw new Error('RenderObjectHistory is empty')
    }
    return this.#history[this.#history.length - 1]!
  }

  /** 移除除最新帧外的所有历史帧（seek 时调用） */
  public clearHistory(): void {
    for (const entry of this.#history.splice(0, this.#history.length - 1)) {
      entry.renderable.dispose()
      this.#parentRenderable.remove(entry.renderable)
    }
  }

  public dispose(): void {
    for (const entry of this.#history) {
      entry.renderable.dispose()
    }
    this.#history.length = 0
  }
}
