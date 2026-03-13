// SPDX-License-Identifier: MPL-2.0
// Ported from lichtblick/renderables/OccupancyGrids.ts
// Adaptations:
//  - Adjusted import paths to local core/ structure
//  - Chinese comments for local consistency

import * as THREE from 'three'

import { SettingsTreeAction, SettingsTreeFields } from '../core/lichtblick-shim'
import type { RosValue } from '../core/lichtblick-shim'
import type { AnyRendererSubscription, IRenderer } from '../core/IRenderer'
import { BaseUserData, Renderable } from '../core/Renderable'
import {
  PartialMessage,
  PartialMessageEvent,
  SceneExtension,
  onlyLastByTopicMessage
} from '../core/SceneExtension'
import type { SettingsTreeEntry } from '../core/SettingsManager'
import { rgbaToCssString, SRGBToLinear, stringToRgba } from '../core/color'
import {
  normalizeHeader,
  normalizePose,
  normalizeInt8Array,
  normalizeTime
} from '../core/normalizeMessages'
import { ColorRGBA, OccupancyGrid, OCCUPANCY_GRID_DATATYPES } from '../core/ros'
import { BaseSettings } from '../core/settings'

// ─────────────────────────────────────────────────────────────────────────────
// 类型定义
// ─────────────────────────────────────────────────────────────────────────────

type ColorModes = 'custom' | 'costmap' | 'map' | 'raw'

export type LayerSettingsOccupancyGrid = BaseSettings & {
  frameLocked: boolean
  minColor: string
  maxColor: string
  unknownColor: string
  invalidColor: string
  colorMode: ColorModes
  alpha: number
}

const INVALID_OCCUPANCY_GRID = 'INVALID_OCCUPANCY_GRID'

// ─────────────────────────────────────────────────────────────────────────────
// 默认值
// ─────────────────────────────────────────────────────────────────────────────

const DEFAULT_MIN_COLOR = { r: 1, g: 1, b: 1, a: 1 } // 白色
const DEFAULT_MAX_COLOR = { r: 0, g: 0, b: 0, a: 1 } // 黑色
const DEFAULT_UNKNOWN_COLOR = { r: 0.5, g: 0.5, b: 0.5, a: 1 } // 灰色
const DEFAULT_INVALID_COLOR = { r: 1, g: 0, b: 1, a: 1 } // 品红
const DEFAULT_ALPHA = 1.0

const DEFAULT_MIN_COLOR_STR = rgbaToCssString(DEFAULT_MIN_COLOR)
const DEFAULT_MAX_COLOR_STR = rgbaToCssString(DEFAULT_MAX_COLOR)
const DEFAULT_UNKNOWN_COLOR_STR = rgbaToCssString(DEFAULT_UNKNOWN_COLOR)
const DEFAULT_INVALID_COLOR_STR = rgbaToCssString(DEFAULT_INVALID_COLOR)

const DEFAULT_SETTINGS: LayerSettingsOccupancyGrid = {
  visible: false,
  frameLocked: false,
  colorMode: 'custom',
  minColor: DEFAULT_MIN_COLOR_STR,
  maxColor: DEFAULT_MAX_COLOR_STR,
  unknownColor: DEFAULT_UNKNOWN_COLOR_STR,
  invalidColor: DEFAULT_INVALID_COLOR_STR,
  alpha: DEFAULT_ALPHA
}

// ─────────────────────────────────────────────────────────────────────────────
// UserData
// ─────────────────────────────────────────────────────────────────────────────

export type OccupancyGridUserData = BaseUserData & {
  settings: LayerSettingsOccupancyGrid
  topic: string
  occupancyGrid: OccupancyGrid
  mesh: THREE.Mesh
  texture: THREE.DataTexture
  material: THREE.MeshBasicMaterial
  pickingMaterial: THREE.ShaderMaterial
}

// ─────────────────────────────────────────────────────────────────────────────
// OccupancyGridRenderable
// ─────────────────────────────────────────────────────────────────────────────

export class OccupancyGridRenderable extends Renderable<OccupancyGridUserData> {
  public override dispose(): void {
    this.userData.texture.dispose()
    this.userData.material.dispose()
    this.userData.pickingMaterial.dispose()
  }

  public override details(): Record<string, RosValue> {
    return this.userData.occupancyGrid as unknown as Record<string, RosValue>
  }
}

// ─────────────────────────────────────────────────────────────────────────────
// OccupancyGrids — SceneExtension 主类
// ─────────────────────────────────────────────────────────────────────────────

export class OccupancyGrids extends SceneExtension<OccupancyGridRenderable> {
  public static extensionId = 'foxglove.OccupancyGrids'

  public constructor(renderer: IRenderer, name: string = OccupancyGrids.extensionId) {
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
        schemaNames: OCCUPANCY_GRID_DATATYPES,
        subscription: {
          handler: this.#handleOccupancyGrid as (messageEvent: unknown) => void,
          // onlyLastByTopicMessage 与 RendererSubscription<unknown> 的泛型不直接兼容，需要 cast
          filterQueue: onlyLastByTopicMessage as any
        }
      }
    ]
  }

  // --- 设置树节点 ---

  public override settingsNodes(): SettingsTreeEntry[] {
    const configTopics = this.renderer.config.topics
    const entries: SettingsTreeEntry[] = []

    // 合并来源：实时 topics 列表 + 已有 renderable（断线时保留）
    const topicNames = new Set<string>()
    const topicsByName = this.renderer.topicsByName

    for (const topic of this.renderer.topics ?? []) {
      if (OCCUPANCY_GRID_DATATYPES.has(topic.schemaName)) {
        topicNames.add(topic.name)
      }
    }

    for (const name of Object.keys(configTopics)) {
      const topicMeta = topicsByName?.get(name)
      if (topicMeta) {
        if (OCCUPANCY_GRID_DATATYPES.has(topicMeta.schemaName)) {
          topicNames.add(name)
        }
      } else if (topicsByName == null) {
        // 断线：只保留有 renderable 的话题
        if (this.renderables.has(name)) {
          topicNames.add(name)
        }
      }
    }

    let topicOrder = 0
    for (const topicName of topicNames) {
      const configWithDefaults = {
        ...DEFAULT_SETTINGS,
        ...(configTopics[topicName] ?? {})
      } as LayerSettingsOccupancyGrid

      let fields: SettingsTreeFields = {
        colorMode: {
          label: '颜色模式',
          input: 'select',
          value: configWithDefaults.colorMode,
          options: [
            { label: '自定义', value: 'custom' },
            { label: 'RViz 地图', value: 'map' },
            { label: 'RViz 代价地图', value: 'costmap' },
            { label: '原始灰度', value: 'raw' }
          ]
        }
      }

      if (configWithDefaults.colorMode === 'custom') {
        const customFields: SettingsTreeFields = {
          minColor: {
            label: '最小值颜色',
            input: 'rgba',
            value: configWithDefaults.minColor
          },
          maxColor: {
            label: '最大值颜色',
            input: 'rgba',
            value: configWithDefaults.maxColor
          },
          unknownColor: {
            label: '未知区域颜色',
            input: 'rgba',
            value: configWithDefaults.unknownColor
          },
          invalidColor: {
            label: '无效值颜色',
            input: 'rgba',
            value: configWithDefaults.invalidColor
          }
        }
        fields = { ...fields, ...customFields }
      } else {
        const paletteFields: SettingsTreeFields = {
          alpha: {
            label: '透明度',
            input: 'number',
            value: configWithDefaults.alpha,
            min: 0.0,
            max: 1.0,
            step: 0.1,
            placeholder: '1.0'
          }
        }
        fields = { ...fields, ...paletteFields }
      }

      fields.frameLocked = {
        label: '锁定坐标系',
        input: 'boolean',
        value: configWithDefaults.frameLocked
      }

      entries.push({
        path: ['topics', topicName],
        node: {
          label: topicName,
          icon: 'Cells',
          fields,
          visible: configWithDefaults.visible,
          order: topicOrder++,
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

    // path 长度 2：['topics', topicName] → 可见性切换
    if (path.length === 2) {
      const topicName = path[1]!
      this.saveSetting([...path, 'visible'] as string[], action.payload.value)
      this.updateSettingsTree()
      const renderable = this.renderables.get(topicName)
      if (renderable) {
        const settings = this.renderer.config.topics[topicName] as
          | Partial<LayerSettingsOccupancyGrid>
          | undefined
        const prevTransparent = occupancyGridHasTransparency(renderable.userData.settings)
        renderable.userData.settings = { ...DEFAULT_SETTINGS, ...settings }
        const newTransparent = occupancyGridHasTransparency(renderable.userData.settings)
        if (prevTransparent !== newTransparent) {
          renderable.userData.material.transparent = newTransparent
          renderable.userData.material.depthWrite = !newTransparent
          renderable.userData.material.needsUpdate = true
        }
        this.#updateOccupancyGridRenderable(
          renderable,
          renderable.userData.occupancyGrid,
          renderable.userData.receiveTime
        )
      }
      return
    }

    // path 长度 3：['topics', topicName, field] → 字段更新
    if (path.length !== 3) return

    this.saveSetting(path as string[], action.payload.value)

    const topicName = path[1]!
    const renderable = this.renderables.get(topicName)
    if (renderable) {
      const prevTransparent = occupancyGridHasTransparency(renderable.userData.settings)
      const settings = this.renderer.config.topics[topicName] as
        | Partial<LayerSettingsOccupancyGrid>
        | undefined
      renderable.userData.settings = { ...DEFAULT_SETTINGS, ...settings }

      const newTransparent = occupancyGridHasTransparency(renderable.userData.settings)
      if (prevTransparent !== newTransparent) {
        renderable.userData.material.transparent = newTransparent
        renderable.userData.material.depthWrite = !newTransparent
        renderable.userData.material.needsUpdate = true
      }

      this.#updateOccupancyGridRenderable(
        renderable,
        renderable.userData.occupancyGrid,
        renderable.userData.receiveTime
      )
    }
  }

  // --- 消息处理 ---

  #handleOccupancyGrid = (messageEvent: PartialMessageEvent<OccupancyGrid>): void => {
    const topic = messageEvent.topic
    const occupancyGrid = normalizeOccupancyGrid(messageEvent.message)
    const receiveTime =
      BigInt(messageEvent.receiveTime.sec) * 1_000_000_000n + BigInt(messageEvent.receiveTime.nsec)

    let renderable = this.renderables.get(topic)
    if (!renderable) {
      const userSettings = this.renderer.config.topics[topic] as
        | Partial<LayerSettingsOccupancyGrid>
        | undefined
      const settings: LayerSettingsOccupancyGrid = { ...DEFAULT_SETTINGS, ...userSettings }

      // 首次收到消息时默认 visible=false
      const isFirstTime = userSettings?.colorMode == undefined
      if (isFirstTime) {
        settings.visible = false
        this.renderer.updateConfig((draft) => {
          draft.topics[topic] = { visible: false } as any
        })
      }

      const texture = createTexture(occupancyGrid)
      const geometry = this.renderer.sharedGeometry.getGeometry(
        this.constructor.name,
        createGeometry
      )
      const mesh = createMesh(topic, geometry, texture, settings)
      const material = mesh.material as THREE.MeshBasicMaterial
      const pickingMaterial = mesh.userData['pickingMaterial'] as THREE.ShaderMaterial

      renderable = new OccupancyGridRenderable(topic, this.renderer, {
        receiveTime,
        messageTime:
          BigInt(occupancyGrid.header.stamp.sec) * 1_000_000_000n +
          BigInt(occupancyGrid.header.stamp.nsec),
        frameId: this.renderer.normalizeFrameId(occupancyGrid.header.frame_id),
        pose: occupancyGrid.info.origin,
        settingsPath: ['topics', topic],
        settings,
        topic,
        occupancyGrid,
        mesh,
        texture,
        material,
        pickingMaterial
      })
      renderable.add(mesh)

      this.add(renderable)
      this.renderables.set(topic, renderable)
      this.updateSettingsTree()
    }

    this.#updateOccupancyGridRenderable(renderable, occupancyGrid, receiveTime)
  }

  // --- 更新 Renderable ---

  #updateOccupancyGridRenderable(
    renderable: OccupancyGridRenderable,
    occupancyGrid: OccupancyGrid,
    receiveTime: bigint
  ): void {
    renderable.userData.occupancyGrid = occupancyGrid
    renderable.userData.pose = occupancyGrid.info.origin
    renderable.userData.receiveTime = receiveTime
    renderable.userData.messageTime =
      BigInt(occupancyGrid.header.stamp.sec) * 1_000_000_000n +
      BigInt(occupancyGrid.header.stamp.nsec)
    renderable.userData.frameId = this.renderer.normalizeFrameId(occupancyGrid.header.frame_id)

    const size = occupancyGrid.info.width * occupancyGrid.info.height
    if (occupancyGrid.data.length !== size) {
      const msg = `OccupancyGrid 数据长度 (${occupancyGrid.data.length}) 不等于 width ${occupancyGrid.info.width} * height ${occupancyGrid.info.height}`
      this.renderer.settings.errors.addToTopic(
        renderable.userData.topic,
        INVALID_OCCUPANCY_GRID,
        msg
      )
      return
    }

    let texture = renderable.userData.texture
    const width = occupancyGrid.info.width
    const height = occupancyGrid.info.height
    const resolution = occupancyGrid.info.resolution

    if (width !== texture.image.width || height !== texture.image.height) {
      // 尺寸变了，重新创建纹理
      texture.dispose()
      texture = createTexture(occupancyGrid)
      renderable.userData.texture = texture
      renderable.userData.material.map = texture
    }

    // 更新纹理像素数据
    updateTexture(texture, occupancyGrid, renderable.userData.settings)

    // 根据分辨率还原真实物理尺寸
    renderable.scale.set(resolution * width, resolution * height, 1)
  }
}

// ─────────────────────────────────────────────────────────────────────────────
// 工厂函数
// ─────────────────────────────────────────────────────────────────────────────

function createGeometry(): THREE.PlaneGeometry {
  const geometry = new THREE.PlaneGeometry(1, 1, 1, 1)
  // 将原点平移到左下角，与 ROS 地图坐标系约定一致
  geometry.translate(0.5, 0.5, 0)
  geometry.computeBoundingSphere()
  return geometry
}

function createTexture(occupancyGrid: OccupancyGrid): THREE.DataTexture {
  const width = occupancyGrid.info.width
  const height = occupancyGrid.info.height
  const size = width * height
  const rgba = new Uint8ClampedArray(size * 4)
  const texture = new THREE.DataTexture(
    rgba,
    width,
    height,
    THREE.RGBAFormat,
    THREE.UnsignedByteType,
    THREE.UVMapping,
    THREE.ClampToEdgeWrapping,
    THREE.ClampToEdgeWrapping,
    THREE.NearestFilter,
    THREE.LinearFilter,
    1,
    THREE.LinearSRGBColorSpace // OccupancyGrid 使用线性 sRGB 灰度值
  )
  texture.generateMipmaps = false
  return texture
}

function createMesh(
  topic: string,
  geometry: THREE.PlaneGeometry,
  texture: THREE.DataTexture,
  settings: LayerSettingsOccupancyGrid
): THREE.Mesh {
  const pickingMaterial = createPickingMaterial(texture)
  const material = createMaterial(texture, topic, settings)
  const mesh = new THREE.Mesh(geometry, material)
  mesh.castShadow = true
  mesh.receiveShadow = true
  mesh.userData['pickingMaterial'] = pickingMaterial
  return mesh
}

function createMaterial(
  texture: THREE.DataTexture,
  topic: string,
  settings: LayerSettingsOccupancyGrid
): THREE.MeshBasicMaterial {
  const transparent = occupancyGridHasTransparency(settings)
  return new THREE.MeshBasicMaterial({
    name: `${topic}:Material`,
    alphaTest: 1e-4, // 完全透明的像素跳过渲染
    depthWrite: !transparent,
    map: texture,
    side: THREE.DoubleSide,
    transparent
  })
}

function createPickingMaterial(texture: THREE.DataTexture): THREE.ShaderMaterial {
  return new THREE.ShaderMaterial({
    vertexShader: /* glsl */ `
      varying vec2 vUv;
      void main() {
        vUv = uv;
        gl_Position = projectionMatrix * modelViewMatrix * vec4(position, 1.0);
      }
    `,
    fragmentShader: /* glsl */ `
      uniform sampler2D map;
      uniform vec4 objectId;
      varying vec2 vUv;
      void main() {
        vec4 color = texture2D(map, vUv);
        if (color.a == 0.0) {
          discard;
        }
        gl_FragColor = objectId;
      }
    `,
    side: THREE.DoubleSide,
    uniforms: {
      map: { value: texture },
      objectId: { value: [NaN, NaN, NaN, NaN] }
    }
  })
}

// ─────────────────────────────────────────────────────────────────────────────
// 纹理更新（核心着色逻辑）
// ─────────────────────────────────────────────────────────────────────────────

const tempColor = { r: 0, g: 0, b: 0, a: 0 }
const tempUnknownColor = { r: 0, g: 0, b: 0, a: 0 }
const tempInvalidColor = { r: 0, g: 0, b: 0, a: 0 }
const tempMinColor = { r: 0, g: 0, b: 0, a: 0 }
const tempMaxColor = { r: 0, g: 0, b: 0, a: 0 }

function updateTexture(
  texture: THREE.DataTexture,
  occupancyGrid: OccupancyGrid,
  settings: LayerSettingsOccupancyGrid
): void {
  const size = occupancyGrid.info.width * occupancyGrid.info.height
  const rgba = texture.image.data as Uint8ClampedArray

  stringToRgba(tempMinColor, settings.minColor)
  stringToRgba(tempMaxColor, settings.maxColor)
  stringToRgba(tempUnknownColor, settings.unknownColor)
  stringToRgba(tempInvalidColor, settings.invalidColor)

  // 转换为线性 sRGB Uint8
  srgbToLinearUint8(tempMinColor)
  srgbToLinearUint8(tempMaxColor)
  srgbToLinearUint8(tempUnknownColor)
  srgbToLinearUint8(tempInvalidColor)

  const data = occupancyGrid.data
  for (let i = 0; i < size; i++) {
    const value = (data[i]! | 0) as number
    const offset = i * 4

    if (settings.colorMode === 'custom') {
      if (value === -1) {
        // 未知区域 (-1)
        rgba[offset + 0] = tempUnknownColor.r
        rgba[offset + 1] = tempUnknownColor.g
        rgba[offset + 2] = tempUnknownColor.b
        rgba[offset + 3] = tempUnknownColor.a
      } else if (value >= 0 && value <= 100) {
        // 有效占据率 [0-100]，minColor → maxColor 线性插值
        const frac = value / 100
        rgba[offset + 0] = tempMinColor.r + (tempMaxColor.r - tempMinColor.r) * frac
        rgba[offset + 1] = tempMinColor.g + (tempMaxColor.g - tempMinColor.g) * frac
        rgba[offset + 2] = tempMinColor.b + (tempMaxColor.b - tempMinColor.b) * frac
        rgba[offset + 3] = tempMinColor.a + (tempMaxColor.a - tempMinColor.a) * frac
      } else {
        // 无效值 (<-1 or >100)
        rgba[offset + 0] = tempInvalidColor.r
        rgba[offset + 1] = tempInvalidColor.g
        rgba[offset + 2] = tempInvalidColor.b
        rgba[offset + 3] = tempInvalidColor.a
      }
    } else {
      // 调色板模式：使用预计算的 256 色 LUT
      paletteColorCached(tempColor, value, settings.colorMode)
      rgba[offset + 0] = tempColor.r
      rgba[offset + 1] = tempColor.g
      rgba[offset + 2] = tempColor.b
      rgba[offset + 3] = tempColor.a * settings.alpha
    }
  }

  texture.needsUpdate = true
}

// ─────────────────────────────────────────────────────────────────────────────
// 调色板 LUT（缓存懒初始化）
// ─────────────────────────────────────────────────────────────────────────────

let costmapPalette: [number, number, number, number][] | undefined
let mapPalette: [number, number, number, number][] | undefined
let rawPalette: [number, number, number, number][] | undefined

function paletteColorCached(
  output: ColorRGBA,
  value: number,
  mode: 'costmap' | 'map' | 'raw'
): void {
  const unsignedValue = value >= 0 ? value : value + 256
  if (unsignedValue < 0 || unsignedValue > 255) {
    output.r = output.g = output.b = output.a = 0
    return
  }

  let palette: [number, number, number, number][]
  switch (mode) {
    case 'costmap':
      costmapPalette ??= createCostmapPalette()
      palette = costmapPalette
      break
    case 'map':
      mapPalette ??= createMapPalette()
      palette = mapPalette
      break
    case 'raw':
    default:
      rawPalette ??= createRawPalette()
      palette = rawPalette
  }

  const colorRaw = palette[Math.trunc(unsignedValue)]!
  output.r = colorRaw[0]
  output.g = colorRaw[1]
  output.b = colorRaw[2]
  output.a = colorRaw[3]
}

/**
 * 仿 RViz 标准灰度地图调色板
 * https://github.com/ros-visualization/rviz/blob/1f622b8c95b8e188841b5505db2f97394d3e9c6c/src/rviz/default_plugin/map_display.cpp#L284
 */
function createMapPalette(): [number, number, number, number][] {
  let index = 0
  const palette = new Array(256).fill([0, 0, 0, 0]) as [number, number, number, number][]

  // 0~100: 灰度梯度（白→黑）
  for (let i = 0; i <= 100; i++) {
    const v = Math.trunc(255 - (255 * i) / 100)
    palette[index++] = [v, v, v, 255]
  }

  // 101~127: 非法正值 → 绿色
  for (let i = 101; i <= 127; i++) {
    palette[index++] = [0, 255, 0, 255]
  }

  // 128~254: 非法负值 → 红/黄渐变
  for (let i = 128; i <= 254; i++) {
    palette[index++] = [255, Math.trunc((255 * (i - 128)) / (254 - 128)), 0, 255]
  }

  // 255 (即 int8 -1): 合法未知 → 蓝绿灰色
  palette[index++] = [112, 137, 134, 255]
  return palette
}

/**
 * 仿 RViz 代价地图调色板
 * https://github.com/ros-visualization/rviz/blob/1f622b8c95b8e188841b5505db2f97394d3e9c6c/src/rviz/default_plugin/map_display.cpp#L322
 */
function createCostmapPalette(): [number, number, number, number][] {
  let index = 0
  const palette = new Array(256).fill([0, 0, 0, 0]) as [number, number, number, number][]

  // 0: alpha=0（透明）
  palette[index++] = [0, 0, 0, 0]

  // 1~98: 蓝→红渐变
  for (let i = 1; i <= 98; i++) {
    const v = Math.trunc((255 * i) / 100)
    palette[index++] = [v, 0, 255 - v, 255]
  }

  // 99: 内接障碍 → 青色
  palette[index++] = [0, 255, 255, 255]

  // 100: 致命障碍 → 紫色
  palette[index++] = [255, 0, 255, 255]

  // 101~127: 非法正值 → 绿色
  for (let i = 101; i <= 127; i++) {
    palette[index++] = [0, 255, 0, 255]
  }

  // 128~254: 非法负值 → 红/黄渐变
  for (let i = 128; i <= 254; i++) {
    palette[index++] = [255, Math.trunc((255 * (i - 128)) / (254 - 128)), 0, 255]
  }

  // 255 (int8 -1): 合法未知 → 蓝绿灰色
  palette[index++] = [112, 137, 134, 255]
  return palette
}

/**
 * 原始灰度调色板（0~255 直接映射为灰度）
 * https://github.com/ros-visualization/rviz/blob/1f622b8c95b8e188841b5505db2f97394d3e9c6c/src/rviz/default_plugin/map_display.cpp#L377
 */
function createRawPalette(): [number, number, number, number][] {
  const palette = new Array(256).fill([0, 0, 0, 0]) as [number, number, number, number][]
  for (let i = 0; i < 256; i++) {
    palette[i] = [i, i, i, 255]
  }
  return palette
}

// ─────────────────────────────────────────────────────────────────────────────
// 工具函数
// ─────────────────────────────────────────────────────────────────────────────

function srgbToLinearUint8(color: ColorRGBA): void {
  color.r = Math.trunc(SRGBToLinear(color.r) * 255)
  color.g = Math.trunc(SRGBToLinear(color.g) * 255)
  color.b = Math.trunc(SRGBToLinear(color.b) * 255)
  color.a = Math.trunc(color.a * 255)
}

function occupancyGridHasTransparency(settings: LayerSettingsOccupancyGrid): boolean {
  if (settings.colorMode === 'custom') {
    stringToRgba(tempMinColor, settings.minColor)
    stringToRgba(tempMaxColor, settings.maxColor)
    stringToRgba(tempUnknownColor, settings.unknownColor)
    stringToRgba(tempInvalidColor, settings.invalidColor)
    return (
      tempMinColor.a < 1 || tempMaxColor.a < 1 || tempInvalidColor.a < 1 || tempUnknownColor.a < 1
    )
  } else {
    // palette 模式下 alpha 统一乘 settings.alpha，默认不透明但允许用户调
    return settings.alpha < 1
  }
}

function normalizeOccupancyGrid(message: PartialMessage<OccupancyGrid>): OccupancyGrid {
  const info = message.info ?? {}
  return {
    header: normalizeHeader(message.header),
    info: {
      map_load_time: normalizeTime((info as any).map_load_time),
      resolution: (info as any).resolution ?? 0,
      width: (info as any).width ?? 0,
      height: (info as any).height ?? 0,
      origin: normalizePose((info as any).origin)
    },
    data: normalizeInt8Array(message.data)
  }
}
