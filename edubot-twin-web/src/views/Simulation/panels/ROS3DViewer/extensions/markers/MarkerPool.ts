// SPDX-License-Identifier: MPL-2.0
// MarkerPool — RenderableMarker 对象池（避免频繁 GC）

import { RenderableArrow } from './RenderableArrow'
import { RenderableCube } from './RenderableCube'
import { RenderableCubeList } from './RenderableCubeList'
import { RenderableCylinder } from './RenderableCylinder'
import { RenderableLineList } from './RenderableLineList'
import { RenderableLineStrip } from './RenderableLineStrip'
import { RenderableMarker, getMarkerId } from './RenderableMarker'
import { RenderableMeshResource } from './RenderableMeshResource'
import { RenderablePoints } from './RenderablePoints'
import { RenderableSphere } from './RenderableSphere'
import { RenderableSphereList } from './RenderableSphereList'
import { RenderableTextViewFacing } from './RenderableTextViewFacing'
import { RenderableTriangleList } from './RenderableTriangleList'
import type { IRenderer } from '../../core/IRenderer'
import { Marker, MarkerType } from '../../core/ros'

// 按类型映射构造函数
const CONSTRUCTORS: Record<
  MarkerType,
  new (
    topic: string,
    marker: Marker,
    receiveTime: bigint | undefined,
    renderer: IRenderer
  ) => RenderableMarker
> = {
  [MarkerType.ARROW]: RenderableArrow,
  [MarkerType.CUBE]: RenderableCube,
  [MarkerType.SPHERE]: RenderableSphere,
  [MarkerType.CYLINDER]: RenderableCylinder,
  [MarkerType.LINE_STRIP]: RenderableLineStrip,
  [MarkerType.LINE_LIST]: RenderableLineList,
  [MarkerType.CUBE_LIST]: RenderableCubeList,
  [MarkerType.SPHERE_LIST]: RenderableSphereList,
  [MarkerType.POINTS]: RenderablePoints,
  [MarkerType.TEXT_VIEW_FACING]: RenderableTextViewFacing,
  [MarkerType.MESH_RESOURCE]: RenderableMeshResource,
  [MarkerType.TRIANGLE_LIST]: RenderableTriangleList
}

/**
 * 对象池，按 MarkerType 分类缓存不再使用的 RenderableMarker 实例，
 * 避免频繁创建销毁 GPU 资源。
 */
export class MarkerPool {
  #renderablesByType = new Map<MarkerType, RenderableMarker[]>()

  public constructor(private renderer: IRenderer) {}

  /** 从池中取出（或新建）一个指定类型的 RenderableMarker */
  public acquire(
    type: MarkerType,
    topic: string,
    marker: Marker,
    receiveTime: bigint | undefined
  ): RenderableMarker {
    const renderables = this.#renderablesByType.get(type)
    if (renderables && renderables.length > 0) {
      const renderable = renderables.pop()!
      renderable.userData.settingsPath = ['topics', topic]
      renderable.userData.settings = { visible: true }
      renderable.userData.topic = topic
      renderable.name = getMarkerId(topic, marker.ns, marker.id)
      renderable.update(marker, receiveTime)
      return renderable
    }

    const Ctor = CONSTRUCTORS[type]
    if (!Ctor) {
      throw new Error(`[MarkerPool] 未知 MarkerType: ${type}`)
    }
    return new Ctor(topic, marker, receiveTime, this.renderer)
  }

  /** 将不再使用的 RenderableMarker 归还到池 */
  public release(renderable: RenderableMarker): void {
    const type = renderable.userData.marker.type as MarkerType
    const renderables = this.#renderablesByType.get(type)
    if (!renderables) {
      this.#renderablesByType.set(type, [renderable])
    } else {
      renderables.push(renderable)
    }
  }

  /** 销毁所有池中的对象 */
  public dispose(): void {
    for (const renderables of this.#renderablesByType.values()) {
      for (const renderable of renderables) {
        renderable.dispose()
      }
    }
    this.#renderablesByType.clear()
  }
}
