// SPDX-License-Identifier: MPL-2.0
// Markers SceneExtension — 订阅 visualization_msgs/Marker(Array) 并渲染

import * as _ from 'lodash-es'

import { SettingsTreeAction, SettingsTreeNodes } from '../core/lichtblick-shim'
import { LayerSettingsMarker, LayerSettingsMarkerNamespace, TopicMarkers } from './TopicMarkers'
import type { AnyRendererSubscription, IRenderer } from '../core/IRenderer'
import { PartialMessage, PartialMessageEvent, SceneExtension } from '../core/SceneExtension'
import type { SettingsTreeEntry } from '../core/SettingsManager'
import {
  normalizeColorRGBA,
  normalizeColorRGBAs,
  normalizeHeader,
  normalizePose,
  normalizeTime,
  normalizeVector3,
  normalizeVector3s
} from '../core/normalizeMessages'
import { Marker, MarkerArray, MARKER_ARRAY_DATATYPES, MARKER_DATATYPES } from '../core/ros'
import { makePose } from '../core/transforms'
import { MarkerPool } from './markers/MarkerPool'
import { useI18n } from '@/hooks/web/useI18n'

const { t } = useI18n()

const DEFAULT_SETTINGS: LayerSettingsMarker = {
  visible: false,
  showOutlines: true,
  color: undefined,
  selectedIdVariable: undefined,
  namespaces: {}
}

export class Markers extends SceneExtension<TopicMarkers> {
  public static extensionId = 'foxglove.Markers'

  // 每个 Markers extension 内部共享一个 MarkerPool
  readonly #pool: MarkerPool

  public constructor(renderer: IRenderer, name: string = Markers.extensionId) {
    super(name, renderer)
    this.#pool = new MarkerPool(renderer)

    // topic 列表更新时（如连接 ROS 后查询到新 topic）重刷设置树
    renderer.on('topicsChanged', this.#handleTopicsChanged)
  }

  public override dispose(): void {
    this.renderer.off('topicsChanged', this.#handleTopicsChanged)
    this.#pool.dispose()
    super.dispose()
  }

  #handleTopicsChanged = (): void => {
    this.updateSettingsTree()
  }

  public override getSubscriptions(): readonly AnyRendererSubscription[] {
    return [
      {
        type: 'schema',
        schemaNames: MARKER_ARRAY_DATATYPES,
        subscription: { handler: this.#handleMarkerArray }
      },
      {
        type: 'schema',
        schemaNames: MARKER_DATATYPES,
        subscription: { handler: this.#handleMarker }
      }
    ]
  }

  public override settingsNodes(): SettingsTreeEntry[] {
    const configTopics = this.renderer.config.topics
    const entries: SettingsTreeEntry[] = []

    // 合并两个来源（都需校验 schema）：
    // 1. renderer.topics — ROS 已发布、schema 匹配 marker 的 topic
    // 2. config.topics  — 已接收过消息，且 schema 仍匹配 marker（断线状态下无 topicMeta 时也允许）
    const ALL_MARKER_SCHEMAS = new Set([...MARKER_DATATYPES, ...MARKER_ARRAY_DATATYPES])
    const topicsByName = this.renderer.topicsByName
    const topicNames = new Set<string>()

    // 来源 1：从实时 topics 列表筛选
    for (const topic of this.renderer.topics ?? []) {
      if (ALL_MARKER_SCHEMAS.has(topic.schemaName)) {
        topicNames.add(topic.name)
      }
    }

    // 来源 2：从 config.topics 筛选
    // - 已连接（topicsByName 可用）：只加入 schema 确认匹配的话题
    // - 断线（topicsByName 为 null）：只保留有 renderable（已收到过消息）的 Marker 话题
    for (const name of Object.keys(configTopics)) {
      const topicMeta = topicsByName?.get(name)
      if (topicMeta) {
        // 已连接：按 schema 严格过滤
        if (ALL_MARKER_SCHEMAS.has(topicMeta.schemaName)) {
          topicNames.add(name)
        }
      } else if (topicsByName != null) {
        // 已连接但话题消失（断开发布者）：跳过
      } else {
        // 断线状态：只保留之前确实收到过消息的话题（有 renderable）
        if (this.renderables.has(name)) {
          topicNames.add(name)
        }
      }
    }

    for (const topicName of topicNames) {
      const config = (configTopics[topicName] ?? {}) as Partial<LayerSettingsMarker>
      const topicMarkers = this.renderables.get(topicName)

      const node = {
        label: topicName,
        icon: 'Shapes' as const,
        fields: {
          color: { label: '颜色覆盖', input: 'rgba' as const, value: config.color },
          showOutlines: {
            label: '显示轮廓',
            input: 'boolean' as const,
            value: config.showOutlines ?? DEFAULT_SETTINGS.showOutlines
          },
          selectedIdVariable: {
            label: '选中ID变量',
            help: t('settings.selectionVariableHelp'),
            input: 'string' as const,
            value: config.selectedIdVariable
          }
        },
        visible: config.visible ?? DEFAULT_SETTINGS.visible,
        handler: this.handleSettingsAction,
        children: undefined as SettingsTreeNodes | undefined
      }

      // 命名空间子项（仅已收到消息的 topic 才有）
      const namespaces = Array.from(topicMarkers?.namespaces.values() ?? []).sort((a, b) =>
        a.namespace.localeCompare(b.namespace)
      )
      if (namespaces.length > 1 || (namespaces.length === 1 && namespaces[0]!.namespace !== '')) {
        node.children = {}
        for (const ns of namespaces) {
          const child = {
            label: ns.namespace !== '' ? ns.namespace : '""',
            icon: 'Shapes' as const,
            visible: ns.settings.visible,
            defaultExpansionState: (namespaces.length > 1 ? 'collapsed' : 'expanded') as
              | 'collapsed'
              | 'expanded',
            handler: this.#handleSettingsActionNamespace
          }
          node.children[`ns:${ns.namespace}`] = child
        }
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
    for (const [topicName, renderable] of this.renderables) {
      // 根据 visible 设置控制 Three.js 对象的可见性
      const settings = this.renderer.config.topics[topicName] as
        | Partial<LayerSettingsMarker>
        | undefined
      renderable.visible = settings?.visible ?? DEFAULT_SETTINGS.visible
      if (renderable.visible) {
        renderable.startFrame(currentTime, renderFrameId, fixedFrameId)
      }
    }
  }

  public override handleSettingsAction = (action: SettingsTreeAction): void => {
    const path = action.payload.path
    if (action.action !== 'update' || !path) return

    // path 长度 2: ['topics', topicName] → 节点级可见性切换（眼睛图标）
    if (path.length === 2) {
      const topicName = path[1]!
      // 保存 visible 到 config（path 补上 'visible' 字段）
      this.saveSetting([...path, 'visible'] as string[], action.payload.value)
      // 刷新设置树以更新眼睛状态
      this.updateSettingsTree()
      // 如已有渲染实例，同步 settings
      const topicMarkers = this.renderables.get(topicName)
      if (topicMarkers) {
        const settings = this.renderer.config.topics[topicName] as
          | Partial<LayerSettingsMarker>
          | undefined
        topicMarkers.userData.settings = { ...DEFAULT_SETTINGS, ...settings }
        topicMarkers.update()
      }
      return
    }

    // path 长度 3: ['topics', topicName, fieldName] → 字段更新
    if (path.length !== 3) return

    this.saveSetting(path as string[], action.payload.value)

    const topicName = path[1]!
    const topicMarkers = this.renderables.get(topicName)
    if (topicMarkers) {
      const settings = this.renderer.config.topics[topicName] as
        | Partial<LayerSettingsMarker>
        | undefined
      topicMarkers.userData.settings = { ...DEFAULT_SETTINGS, ...settings }
      topicMarkers.update()
    }
  }

  #handleSettingsActionNamespace = (action: SettingsTreeAction): void => {
    const path = action.payload.path
    if (action.action !== 'update' || !path || path.length !== 4) return

    const topicName = path[1]!
    const namespaceKey = path[2]!
    const fieldName = path[3]!
    const namespace = namespaceKey.slice(3) // 去掉 'ns:' 前缀

    this.renderer.updateConfig((draft) => {
      const actualPath = ['topics', topicName, 'namespaces', namespace, fieldName]
      _.set(draft, actualPath, action.payload.value)
    })

    const renderable = this.renderables.get(topicName)
    if (renderable) {
      const settings = this.renderer.config.topics[topicName] as
        | Partial<LayerSettingsMarker>
        | undefined
      const ns = renderable.namespaces.get(namespace)
      if (ns) {
        const nsSettings = settings?.namespaces?.[namespace] as
          | Partial<LayerSettingsMarkerNamespace>
          | undefined
        ns.settings = { ...ns.settings, ...nsSettings }
      }
    }

    this.updateSettingsTree()
  }

  #handleMarkerArray = (messageEvent: PartialMessageEvent<MarkerArray>): void => {
    const topic = messageEvent.topic
    const markerArray = messageEvent.message
    const receiveTime =
      BigInt(messageEvent.receiveTime.sec) * 1_000_000_000n + BigInt(messageEvent.receiveTime.nsec)

    for (const markerMsg of markerArray.markers ?? []) {
      if (markerMsg) {
        const marker = normalizeMarker(markerMsg)
        this.#addMarker(topic, marker, receiveTime)
      }
    }
  }

  #handleMarker = (messageEvent: PartialMessageEvent<Marker>): void => {
    const topic = messageEvent.topic
    const marker = normalizeMarker(messageEvent.message)
    const receiveTime =
      BigInt(messageEvent.receiveTime.sec) * 1_000_000_000n + BigInt(messageEvent.receiveTime.nsec)
    this.#addMarker(topic, marker, receiveTime)
  }

  #addMarker(topic: string, marker: Marker, receiveTime: bigint): void {
    const topicMarkers = this.#getTopicMarkers(topic, marker, receiveTime)
    const prevNsCount = topicMarkers.namespaces.size
    topicMarkers.addMarkerMessage(marker, receiveTime)

    if (prevNsCount !== topicMarkers.namespaces.size) {
      this.updateSettingsTree()
    }
  }

  #getTopicMarkers(topic: string, marker: Marker, receiveTime: bigint): TopicMarkers {
    let topicMarkers = this.renderables.get(topic)
    if (!topicMarkers) {
      const userSettings = this.renderer.config.topics[topic] as
        | Partial<LayerSettingsMarker>
        | undefined

      topicMarkers = new TopicMarkers(
        topic,
        this.renderer,
        {
          receiveTime,
          messageTime:
            BigInt(marker.header.stamp.sec) * 1_000_000_000n + BigInt(marker.header.stamp.nsec),
          frameId: this.renderer.normalizeFrameId(marker.header.frame_id),
          pose: makePose(),
          settingsPath: ['topics', topic],
          settings: { ...DEFAULT_SETTINGS, ...userSettings },
          topic
        },
        this.#pool
      )
      this.renderables.set(topic, topicMarkers)
      this.add(topicMarkers)
    }
    return topicMarkers
  }
}

function normalizeMarker(marker: PartialMessage<Marker>): Marker {
  return {
    header: normalizeHeader(marker.header),
    ns: marker.ns ?? '',
    id: marker.id ?? 0,
    type: marker.type ?? 0,
    action: marker.action ?? 0,
    pose: normalizePose(marker.pose),
    scale: normalizeVector3(marker.scale),
    color: normalizeColorRGBA(marker.color),
    lifetime: normalizeTime(marker.lifetime),
    frame_locked: marker.frame_locked ?? false,
    points: normalizeVector3s(marker.points),
    colors: normalizeColorRGBAs(marker.colors),
    text: marker.text ?? '',
    mesh_resource: marker.mesh_resource ?? '',
    mesh_use_embedded_materials: marker.mesh_use_embedded_materials ?? false
  }
}
