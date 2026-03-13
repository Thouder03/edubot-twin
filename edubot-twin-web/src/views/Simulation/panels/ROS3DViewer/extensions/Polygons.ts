// SPDX-License-Identifier: MPL-2.0
// Polygons SceneExtension — 订阅 geometry_msgs/PolygonStamped 并渲染为闭合折线

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
import { normalizeHeader, normalizeVector3s } from '../core/normalizeMessages'
import {
  Marker,
  MarkerAction,
  MarkerType,
  Polygon,
  PolygonStamped,
  POLYGON_STAMPED_DATATYPES,
  TIME_ZERO
} from '../core/ros'
import { BaseSettings } from '../core/settings'
import { makePose } from '../core/transforms'
import { RenderableLineStrip } from './markers/RenderableLineStrip'

// ============================================================
// 类型定义
// ============================================================

export type LayerSettingsPolygon = BaseSettings & {
  lineWidth: number
  color: string
}

export type PolygonUserData = BaseUserData & {
  settings: LayerSettingsPolygon
  topic: string
  polygonStamped: PolygonStamped
  lines: RenderableLineStrip | undefined
}

// ============================================================
// 默认值
// ============================================================

const DEFAULT_COLOR = { r: 124 / 255, g: 107 / 255, b: 1, a: 1 }
const DEFAULT_LINE_WIDTH = 0.1

const DEFAULT_COLOR_STR = rgbaToCssString(DEFAULT_COLOR)

const DEFAULT_SETTINGS: LayerSettingsPolygon = {
  visible: false,
  lineWidth: DEFAULT_LINE_WIDTH,
  color: DEFAULT_COLOR_STR
}

// ============================================================
// PolygonRenderable — 单个 topic 的可渲染对象
// ============================================================

export class PolygonRenderable extends Renderable<PolygonUserData> {
  public override dispose(): void {
    this.userData.lines?.dispose()
    super.dispose()
  }
}

// ============================================================
// Polygons — SceneExtension 主类
// ============================================================

export class Polygons extends SceneExtension<PolygonRenderable> {
  public static extensionId = 'foxglove.Polygons'

  public constructor(renderer: IRenderer, name: string = Polygons.extensionId) {
    super(name, renderer)

    // topic 列表更新时重刷设置树（使新发布的 polygon topic 立即出现在面板中）
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
        schemaNames: POLYGON_STAMPED_DATATYPES,
        subscription: { handler: this.#handlePolygon, filterQueue: onlyLastByTopicMessage }
      }
    ]
  }

  // --- 设置树节点 ---

  public override settingsNodes(): SettingsTreeEntry[] {
    const configTopics = this.renderer.config.topics
    const entries: SettingsTreeEntry[] = []

    // 合并两个来源：
    // 1. renderer.topics — 实时可用的 polygon topic
    // 2. renderables     — 已接收过消息（断线状态下保留）
    const topicNames = new Set<string>()
    const topicsByName = this.renderer.topicsByName

    for (const topic of this.renderer.topics ?? []) {
      if (POLYGON_STAMPED_DATATYPES.has(topic.schemaName)) {
        topicNames.add(topic.name)
      }
    }

    for (const name of Object.keys(configTopics)) {
      const topicMeta = topicsByName?.get(name)
      if (topicMeta) {
        if (POLYGON_STAMPED_DATATYPES.has(topicMeta.schemaName)) {
          topicNames.add(name)
        }
      } else if (topicsByName == null) {
        // 断线：保留有 renderable 的 topic
        if (this.renderables.has(name)) {
          topicNames.add(name)
        }
      }
    }

    for (const topicName of topicNames) {
      const config = (configTopics[topicName] ?? {}) as Partial<LayerSettingsPolygon>

      entries.push({
        path: ['topics', topicName],
        node: {
          label: topicName,
          icon: 'Star',
          fields: {
            lineWidth: {
              label: '线宽',
              input: 'number',
              min: 0,
              placeholder: String(DEFAULT_LINE_WIDTH),
              step: 0.005,
              precision: 3,
              value: config.lineWidth
            },
            color: {
              label: '颜色',
              input: 'rgba',
              value: config.color ?? DEFAULT_COLOR_STR
            }
          },
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

    // path 长度 2：['topics', topicName] → 可见性切换（眼睛图标）
    if (path.length === 2) {
      const topicName = path[1]!
      this.saveSetting([...path, 'visible'] as string[], action.payload.value)
      this.updateSettingsTree()
      const renderable = this.renderables.get(topicName)
      if (renderable) {
        const settings = this.renderer.config.topics[topicName] as
          | Partial<LayerSettingsPolygon>
          | undefined
        renderable.userData.settings = { ...DEFAULT_SETTINGS, ...settings }
        this.#updatePolygonRenderable(
          renderable,
          renderable.userData.polygonStamped,
          renderable.userData.receiveTime
        )
      }
      return
    }

    // path 长度 3：['topics', topicName, fieldName] → 字段更新
    if (path.length !== 3) return

    this.saveSetting(path as string[], action.payload.value)

    const topicName = path[1]!
    const renderable = this.renderables.get(topicName)
    if (renderable) {
      const settings = this.renderer.config.topics[topicName] as
        | Partial<LayerSettingsPolygon>
        | undefined
      renderable.userData.settings = { ...DEFAULT_SETTINGS, ...settings }
      this.#updatePolygonRenderable(
        renderable,
        renderable.userData.polygonStamped,
        renderable.userData.receiveTime
      )
    }
  }

  // --- 消息处理 ---

  #handlePolygon = (messageEvent: PartialMessageEvent<PolygonStamped>): void => {
    const topic = messageEvent.topic
    const polygonStamped = normalizePolygonStamped(messageEvent.message)
    const receiveTime =
      BigInt(messageEvent.receiveTime.sec) * 1_000_000_000n + BigInt(messageEvent.receiveTime.nsec)

    let renderable = this.renderables.get(topic)
    if (!renderable) {
      const userSettings = this.renderer.config.topics[topic] as
        | Partial<LayerSettingsPolygon>
        | undefined
      const settings = { ...DEFAULT_SETTINGS, ...userSettings }
      renderable = new PolygonRenderable(topic, this.renderer, {
        receiveTime,
        messageTime:
          BigInt(polygonStamped.header.stamp.sec) * 1_000_000_000n +
          BigInt(polygonStamped.header.stamp.nsec),
        frameId: this.renderer.normalizeFrameId(polygonStamped.header.frame_id),
        pose: makePose(),
        settingsPath: ['topics', topic],
        settings,
        topic,
        polygonStamped,
        lines: undefined
      })

      this.add(renderable)
      this.renderables.set(topic, renderable)
      this.updateSettingsTree()
    }

    this.#updatePolygonRenderable(renderable, polygonStamped, receiveTime)
  }

  // --- 更新 Renderable ---

  #updatePolygonRenderable(
    renderable: PolygonRenderable,
    polygonStamped: PolygonStamped,
    receiveTime: bigint
  ): void {
    const settings = renderable.userData.settings

    renderable.userData.receiveTime = receiveTime
    renderable.userData.messageTime =
      BigInt(polygonStamped.header.stamp.sec) * 1_000_000_000n +
      BigInt(polygonStamped.header.stamp.nsec)
    renderable.userData.frameId = this.renderer.normalizeFrameId(polygonStamped.header.frame_id)
    renderable.userData.polygonStamped = polygonStamped

    const topic = renderable.userData.topic
    const linesMarker = createLineStripMarker(polygonStamped, settings)

    if (!renderable.userData.lines) {
      renderable.userData.lines = new RenderableLineStrip(
        topic,
        linesMarker,
        receiveTime,
        this.renderer
      )
      renderable.add(renderable.userData.lines)
    } else {
      renderable.userData.lines.update(linesMarker, receiveTime)
    }
  }
}

// ============================================================
// 辅助函数
// ============================================================

/**
 * 将 PolygonStamped 转换为 LINE_STRIP Marker。
 * 核心处理：将首点追加到末尾，保证多边形闭合。
 */
function createLineStripMarker(
  polygonStamped: PolygonStamped,
  settings: LayerSettingsPolygon
): Marker {
  // 复制所有点，并将首点压到末尾形成闭合环
  const points = [...polygonStamped.polygon.points]
  if (points.length > 0) {
    points.push(points[0]!)
  }

  const linesMarker: Marker = {
    header: polygonStamped.header,
    ns: '',
    id: 0,
    type: MarkerType.LINE_STRIP,
    action: MarkerAction.ADD,
    pose: makePose(),
    scale: { x: settings.lineWidth, y: 1, z: 1 },
    color: stringToRgba(makeRgba(), settings.color),
    lifetime: TIME_ZERO,
    frame_locked: true,
    points,
    colors: [],
    text: '',
    mesh_resource: '',
    mesh_use_embedded_materials: false
  }

  return linesMarker
}

function normalizePolygon(polygon: PartialMessage<Polygon> | undefined): Polygon {
  return {
    points: normalizeVector3s(polygon?.points)
  }
}

function normalizePolygonStamped(polygon: PartialMessage<PolygonStamped>): PolygonStamped {
  return {
    header: normalizeHeader(polygon.header),
    polygon: normalizePolygon(polygon.polygon)
  }
}
