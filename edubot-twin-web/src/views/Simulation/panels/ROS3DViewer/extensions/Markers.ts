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
  }

  public override dispose(): void {
    this.#pool.dispose()
    super.dispose()
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

    for (const topicName of Object.keys(configTopics)) {
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
            input: 'string' as const,
            value: config.selectedIdVariable
          }
        },
        visible: config.visible ?? DEFAULT_SETTINGS.visible,
        handler: this.handleSettingsAction,
        children: undefined as SettingsTreeNodes | undefined
      }

      // 命名空间子项
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
    for (const renderable of this.renderables.values()) {
      renderable.startFrame(currentTime, renderFrameId, fixedFrameId)
    }
  }

  public override handleSettingsAction = (action: SettingsTreeAction): void => {
    const path = action.payload.path
    if (action.action !== 'update' || !path || path.length !== 3) return

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
