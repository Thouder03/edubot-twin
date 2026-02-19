import { RenderableMarker } from './markers/RenderableMarker'
import { MarkerPool } from './markers/MarkerPool'
import { MISSING_TRANSFORM, missingTransformMessage } from '../core/SceneExtension'
import type { IRenderer } from '../core/IRenderer'
import { BaseUserData, Renderable } from '../core/Renderable'
import { Marker, MarkerAction, MarkerType } from '../core/ros'
import { BaseSettings } from '../core/settings'
import { updatePose } from '../core/updatePose'

export type LayerSettingsMarker = BaseSettings & {
  color: string | undefined
  showOutlines: boolean | undefined
  selectedIdVariable: string | undefined
  namespaces: Record<string, LayerSettingsMarkerNamespace>
}

export type LayerSettingsMarkerNamespace = BaseSettings

const INVALID_CUBE_LIST = 'INVALID_CUBE_LIST'
const INVALID_LINE_LIST = 'INVALID_LINE_LIST'
const INVALID_LINE_STRIP = 'INVALID_LINE_STRIP'
const INVALID_MARKER_ACTION = 'INVALID_MARKER_ACTION'
const INVALID_MARKER_TYPE = 'INVALID_MARKER_TYPE'
const INVALID_POINTS_LIST = 'INVALID_POINTS_LIST'
const INVALID_SPHERE_LIST = 'INVALID_SPHERE_LIST'

const DEFAULT_NAMESPACE_SETTINGS: LayerSettingsMarkerNamespace = { visible: true }

export type MarkerTopicUserData = BaseUserData & {
  topic: string
  settings: LayerSettingsMarker
}

type PartialMarkerSettings = Partial<LayerSettingsMarker> | undefined

export class MarkersNamespace {
  public namespace: string
  public markersById = new Map<number, RenderableMarker>()
  public settings: LayerSettingsMarkerNamespace

  public constructor(topic: string, namespace: string, renderer: IRenderer) {
    this.namespace = namespace
    const topicSettings = renderer.config.topics[topic] as PartialMarkerSettings
    const userSettings = topicSettings?.namespaces?.[namespace]
    this.settings = { ...DEFAULT_NAMESPACE_SETTINGS, ...userSettings }
  }
}

function getMarkerId(topic: string, ns: string, id: number): string {
  return `${topic}:${ns ? ns + ':' : ''}${id}`.replace(/\s/g, '_')
}

export class TopicMarkers extends Renderable<MarkerTopicUserData> {
  public override pickable = false
  public namespaces = new Map<string, MarkersNamespace>()
  #pool: MarkerPool

  public constructor(
    topic: string,
    renderer: IRenderer,
    userData: MarkerTopicUserData,
    pool: MarkerPool
  ) {
    super(topic, renderer, userData)
    this.#pool = pool
  }

  public override dispose(): void {
    for (const ns of this.namespaces.values()) {
      for (const marker of ns.markersById.values()) {
        this.#pool.release(marker)
      }
    }
    this.children.length = 0
    this.namespaces.clear()
  }

  public addMarkerMessage(marker: Marker, receiveTime: bigint): void {
    switch (marker.action) {
      case MarkerAction.ADD:
      // fallthrough: ADD and MODIFY = 0 share the same enum value
      case MarkerAction.DELETE:
        if (marker.action === MarkerAction.DELETE) {
          this.#deleteMarker(marker.ns, marker.id)
          return
        }
        this.#addOrUpdateMarker(marker, receiveTime)
        break
      case MarkerAction.DELETEALL:
        this.#deleteAllMarkers(marker.ns)
        break
      default:
        this.renderer.settings.errors.addToTopic(
          this.userData.topic,
          INVALID_MARKER_ACTION,
          `Invalid marker action ${marker.action}`
        )
    }
  }

  public update(): void {
    for (const ns of this.namespaces.values()) {
      for (const renderable of ns.markersById.values()) {
        renderable.update(renderable.userData.originalMarker, renderable.userData.receiveTime)
      }
    }
  }

  public startFrame(currentTime: bigint, renderFrameId: string, fixedFrameId: string): void {
    this.visible = this.userData.settings.visible
    if (!this.visible) {
      this.renderer.settings.errors.clearTopic(this.userData.topic)
      return
    }

    for (const ns of this.namespaces.values()) {
      for (const renderable of ns.markersById.values()) {
        renderable.visible = ns.settings.visible
        if (!renderable.visible) continue

        const marker = renderable.userData.marker
        const receiveTime = renderable.userData.receiveTime
        const expiresIn = renderable.userData.expiresIn

        // 检查是否过期
        if (expiresIn != undefined) {
          if (currentTime > receiveTime + expiresIn) {
            this.#deleteMarker(ns.namespace, marker.id)
            continue
          }
        }

        const frameId = this.renderer.normalizeFrameId(marker.header.frame_id)
        const srcTime = marker.frame_locked ? currentTime : renderable.userData.messageTime
        const updated = updatePose(
          renderable,
          this.renderer.transformTree,
          renderFrameId,
          fixedFrameId,
          frameId,
          currentTime,
          srcTime
        )
        renderable.visible = updated
        if (!updated) {
          const message = missingTransformMessage(renderFrameId, fixedFrameId, frameId)
          this.renderer.settings.errors.addToTopic(this.userData.topic, MISSING_TRANSFORM, message)
        } else {
          this.renderer.settings.errors.removeFromTopic(this.userData.topic, MISSING_TRANSFORM)
        }
      }
    }
  }

  #addOrUpdateMarker(marker: Marker, receiveTime: bigint): void {
    let ns = this.namespaces.get(marker.ns)
    if (!ns) {
      ns = new MarkersNamespace(this.userData.topic, marker.ns, this.renderer)
      this.namespaces.set(marker.ns, ns)
    }

    let renderable = ns.markersById.get(marker.id)

    // 类型变化时删除旧的
    if (renderable && renderable.userData.marker.type !== marker.type) {
      this.#deleteMarker(marker.ns, marker.id)
      renderable = undefined
    }

    if (!renderable) {
      renderable = this.#createMarkerRenderable(marker, receiveTime)
      if (!renderable) return
      this.add(renderable)
      ns.markersById.set(marker.id, renderable)
    }

    renderable.update(marker, receiveTime)
  }

  #deleteMarker(ns: string, id: number): boolean {
    const namespace = this.namespaces.get(ns)
    if (namespace) {
      const renderable = namespace.markersById.get(id)
      if (renderable) {
        this.remove(renderable)
        this.#pool.release(renderable)
        namespace.markersById.delete(id)
        return true
      }
    }
    return false
  }

  #deleteAllMarkers(ns: string): void {
    const clearNamespace = (namespace: MarkersNamespace): void => {
      for (const renderable of namespace.markersById.values()) {
        this.remove(renderable)
        this.#pool.release(renderable)
      }
      namespace.markersById.clear()
    }

    if (ns.length === 0) {
      for (const namespace of this.namespaces.values()) {
        clearNamespace(namespace)
      }
    } else {
      const namespace = this.namespaces.get(ns)
      if (namespace) clearNamespace(namespace)
    }
  }

  #createMarkerRenderable(marker: Marker, receiveTime: bigint): RenderableMarker | undefined {
    const topic = this.userData.topic

    switch (marker.type) {
      case MarkerType.ARROW:
      case MarkerType.CUBE:
      case MarkerType.SPHERE:
      case MarkerType.CYLINDER:
      case MarkerType.TRIANGLE_LIST:
        return this.#pool.acquire(marker.type as MarkerType, topic, marker, receiveTime)

      case MarkerType.TEXT_VIEW_FACING:
      case MarkerType.MESH_RESOURCE:
        return this.#pool.acquire(marker.type as MarkerType, topic, marker, receiveTime)

      case MarkerType.LINE_STRIP:
        if (marker.points.length === 0) {
          this.renderer.settings.errors.addToTopic(
            topic,
            INVALID_LINE_STRIP,
            `LINE_STRIP marker ${getMarkerId(topic, marker.ns, marker.id)} has no points`
          )
          return undefined
        }
        if (marker.points.length === 1) {
          this.renderer.settings.errors.addToTopic(
            topic,
            INVALID_LINE_STRIP,
            `LINE_STRIP marker ${getMarkerId(topic, marker.ns, marker.id)} only has one point`
          )
          return undefined
        }
        return this.#pool.acquire(MarkerType.LINE_STRIP, topic, marker, receiveTime)

      case MarkerType.LINE_LIST:
        if (marker.points.length === 0) {
          this.renderer.settings.errors.addToTopic(
            topic,
            INVALID_LINE_LIST,
            `LINE_LIST marker ${getMarkerId(topic, marker.ns, marker.id)} has no points`
          )
          return undefined
        }
        if (marker.points.length % 2 !== 0) {
          this.renderer.settings.errors.addToTopic(
            topic,
            INVALID_LINE_LIST,
            `LINE_LIST marker ${getMarkerId(topic, marker.ns, marker.id)} has an odd number of points (${marker.points.length})`
          )
        }
        return this.#pool.acquire(MarkerType.LINE_LIST, topic, marker, receiveTime)

      case MarkerType.CUBE_LIST:
        if (marker.points.length === 0) {
          this.renderer.settings.errors.addToTopic(
            topic,
            INVALID_CUBE_LIST,
            `CUBE_LIST marker ${getMarkerId(topic, marker.ns, marker.id)} has no points`
          )
          return undefined
        }
        return this.#pool.acquire(MarkerType.CUBE_LIST, topic, marker, receiveTime)

      case MarkerType.SPHERE_LIST:
        if (marker.points.length === 0) {
          this.renderer.settings.errors.addToTopic(
            topic,
            INVALID_SPHERE_LIST,
            `SPHERE_LIST marker ${getMarkerId(topic, marker.ns, marker.id)} has no points`
          )
          return undefined
        }
        return this.#pool.acquire(MarkerType.SPHERE_LIST, topic, marker, receiveTime)

      case MarkerType.POINTS:
        if (marker.points.length === 0) {
          this.renderer.settings.errors.addToTopic(
            topic,
            INVALID_POINTS_LIST,
            `POINTS marker ${getMarkerId(topic, marker.ns, marker.id)} has no points`
          )
          return undefined
        }
        return this.#pool.acquire(MarkerType.POINTS, topic, marker, receiveTime)

      default: {
        this.renderer.settings.errors.addToTopic(
          topic,
          INVALID_MARKER_TYPE,
          `Marker ${getMarkerId(topic, marker.ns, marker.id)} has invalid type ${marker.type}`
        )
        return undefined
      }
    }
  }
}
