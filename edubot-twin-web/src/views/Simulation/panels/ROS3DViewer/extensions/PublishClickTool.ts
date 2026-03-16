// SPDX-License-Identifier: MPL-2.0
// PublishClickTool — 3D 视图点击发布 ROS 消息的交互工具
// 移植自 lichtblick/renderables/PublishClickTool.ts

import * as THREE from 'three'

import type { IRenderer } from '../core/IRenderer'
import { Renderable } from '../core/Renderable'
import { SceneExtension } from '../core/SceneExtension'
import { Marker, MarkerAction, MarkerType, TIME_ZERO } from '../core/ros'
import { makePose } from '../core/transforms'
import { RenderableArrow } from './markers/RenderableArrow'
import { RenderableSphere } from './markers/RenderableSphere'

// ============================================================
// 类型定义
// ============================================================

export type PublishClickType = 'pose_estimate' | 'pose' | 'point'
export type PublishClickState = 'idle' | 'place-first-point' | 'place-second-point'

export interface PublishClickEventMap extends THREE.Object3DEventMap {
  'foxglove.publish-start': object
  'foxglove.publish-end': object
  'foxglove.publish-type-change': object
  'foxglove.publish-submit':
    | { publishClickType: 'point'; point: { x: number; y: number; z: number } }
    | {
        publishClickType: 'pose' | 'pose_estimate'
        pose: {
          position: { x: number; y: number; z: number }
          orientation: { x: number; y: number; z: number; w: number }
        }
      }
}

// ============================================================
// 辅助函数：创建预览用的虚拟 Marker
// ============================================================

const UNIT_X = new THREE.Vector3(1, 0, 0)
const tempVec3 = new THREE.Vector3()

function makeArrowMarker(type: PublishClickType): Marker {
  return {
    header: { frame_id: '', stamp: { sec: 0, nsec: 0 } },
    ns: '',
    id: 0,
    type: MarkerType.ARROW,
    action: MarkerAction.ADD,
    pose: makePose(),
    scale: { x: 2, y: 0.25, z: 0.25 },
    color: type === 'pose_estimate' ? { r: 0, g: 1, b: 1, a: 1 } : { r: 1, g: 0, b: 1, a: 1 },
    lifetime: TIME_ZERO,
    frame_locked: true,
    points: [],
    colors: [],
    text: '',
    mesh_resource: '',
    mesh_use_embedded_materials: false
  }
}

function makeSphereMarker(): Marker {
  return {
    header: { frame_id: '', stamp: { sec: 0, nsec: 0 } },
    ns: '',
    id: 0,
    type: MarkerType.SPHERE,
    action: MarkerAction.ADD,
    pose: makePose(),
    scale: { x: 0.25, y: 0.25, z: 0.25 },
    color: { r: 1, g: 1, b: 0, a: 1 },
    lifetime: TIME_ZERO,
    frame_locked: true,
    points: [],
    colors: [],
    text: '',
    mesh_resource: '',
    mesh_use_embedded_materials: false
  }
}

// ============================================================
// PublishClickTool — SceneExtension
// ============================================================

export class PublishClickTool extends SceneExtension<Renderable, PublishClickEventMap> {
  public static extensionId = 'foxglove.PublishClickTool'

  #sphere: RenderableSphere
  #arrow: RenderableArrow

  public publishClickType: PublishClickType = 'point'
  public state: PublishClickState = 'idle'

  #point1?: THREE.Vector3
  #point2?: THREE.Vector3

  public constructor(renderer: IRenderer) {
    super(PublishClickTool.extensionId, renderer)

    // 从配置中恢复初始类型，避免初始化状态与设置面板不一致
    this.publishClickType = this.renderer.config.publish?.type ?? 'point'

    this.#sphere = new RenderableSphere('', makeSphereMarker(), undefined, this.renderer)
    this.#arrow = new RenderableArrow(
      '',
      makeArrowMarker(this.publishClickType),
      undefined,
      this.renderer
    )

    this.#sphere.visible = false
    this.#sphere.mesh.userData.picking = false
    this.#arrow.visible = false
    this.#arrow.shaftMesh.userData.picking = false
    this.#arrow.headMesh.userData.picking = false

    this.add(this.#sphere)
    this.add(this.#arrow)

    this.#setState('idle')
  }

  public override dispose(): void {
    this.#arrow.dispose()
    this.#sphere.dispose()
    this.renderer.input.removeListener('click', this.#handleClick)
    this.renderer.input.removeListener('mousemove', this.#handleMouseMove)
    super.dispose()
  }

  // ============================================================
  // 公开 API
  // ============================================================

  public setPublishClickType(type: PublishClickType): void {
    this.publishClickType = type
    this.#arrow.update(makeArrowMarker(type), undefined)
    this.dispatchEvent({ type: 'foxglove.publish-type-change' })
  }

  public start(): void {
    this.#setState('place-first-point')
  }

  public stop(): void {
    this.#setState('idle')
  }

  // ============================================================
  // 状态机
  // ============================================================

  #setState(state: PublishClickState): void {
    this.state = state
    switch (state) {
      case 'idle':
        this.#point1 = this.#point2 = undefined
        this.renderer.input.removeListener('click', this.#handleClick)
        this.renderer.input.removeListener('mousemove', this.#handleMouseMove)
        this.dispatchEvent({ type: 'foxglove.publish-end' })
        break
      case 'place-first-point':
        this.renderer.input.addListener('click', this.#handleClick)
        this.renderer.input.addListener('mousemove', this.#handleMouseMove)
        this.dispatchEvent({ type: 'foxglove.publish-start' })
        break
      case 'place-second-point':
        break
    }
    this.#render()
  }

  // ============================================================
  // 输入处理
  // ============================================================

  #handleMouseMove = (
    _cursorCoords: THREE.Vector2,
    worldSpaceCursorCoords: THREE.Vector3 | undefined,
    _event: MouseEvent
  ): void => {
    if (!worldSpaceCursorCoords) return

    switch (this.state) {
      case 'idle':
        break
      case 'place-first-point':
        ;(this.#point1 ??= new THREE.Vector3()).copy(worldSpaceCursorCoords)
        break
      case 'place-second-point':
        ;(this.#point2 ??= new THREE.Vector3()).copy(worldSpaceCursorCoords)
        break
    }
    this.#render()
  }

  #handleClick = (
    _cursorCoords: THREE.Vector2,
    worldSpaceCursorCoords: THREE.Vector3 | undefined,
    _event: MouseEvent
  ): void => {
    if (!worldSpaceCursorCoords) return

    switch (this.state) {
      case 'idle':
        break

      case 'place-first-point':
        this.#point1 = worldSpaceCursorCoords.clone()
        if (this.publishClickType === 'point') {
          this.dispatchEvent({
            type: 'foxglove.publish-submit',
            publishClickType: 'point',
            point: { x: this.#point1.x, y: this.#point1.y, z: this.#point1.z }
          })
          this.#setState('idle')
        } else {
          this.#setState('place-second-point')
        }
        break

      case 'place-second-point':
        this.#point2 = worldSpaceCursorCoords.clone()
        if (this.#point1 && this.publishClickType !== 'point') {
          const p = this.#point1.clone()
          const q = new THREE.Quaternion().setFromUnitVectors(
            UNIT_X,
            tempVec3.subVectors(this.#point2, this.#point1).normalize()
          )
          this.dispatchEvent({
            type: 'foxglove.publish-submit',
            publishClickType: this.publishClickType,
            pose: {
              position: { x: p.x, y: p.y, z: p.z },
              orientation: { x: q.x, y: q.y, z: q.z, w: q.w }
            }
          })
        }
        this.#setState('idle')
        break
    }
    this.#render()
  }

  // ============================================================
  // 渲染预览
  // ============================================================

  #render(): void {
    if (this.publishClickType === 'point') {
      this.#arrow.visible = false
      if (this.#point1) {
        this.#sphere.visible = true
        this.#sphere.position.copy(this.#point1)
      } else {
        this.#sphere.visible = false
      }
    } else {
      this.#sphere.visible = false
      if (this.#point1) {
        this.#arrow.visible = true
        this.#arrow.position.copy(this.#point1)
        if (this.#point2) {
          this.#arrow.quaternion.setFromUnitVectors(
            UNIT_X,
            tempVec3.subVectors(this.#point2, this.#point1).normalize()
          )
        } else {
          this.#arrow.quaternion.set(0, 0, 0, 1)
        }
      } else {
        this.#arrow.visible = false
      }
    }
    this.renderer.queueAnimationFrame()
  }
}
