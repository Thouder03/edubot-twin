// SPDX-License-Identifier: MPL-2.0
// RenderableMeshResource — MESH_RESOURCE marker (type=10)
// 加载外部 mesh 文件（.dae / .stl / .obj）并渲染

import * as THREE from 'three'

import { RenderableMarker } from './RenderableMarker'
import { makeStandardMaterial } from './materials'
import type { IRenderer } from '../../core/IRenderer'
import { rgbToThreeColor } from '../../core/color'
import { Marker } from '../../core/ros'

const _tempColor = new THREE.Color()

export class RenderableMeshResource extends RenderableMarker {
  #loadedUrl = ''
  #group: THREE.Group

  public constructor(
    topic: string,
    marker: Marker,
    receiveTime: bigint | undefined,
    renderer: IRenderer
  ) {
    super(topic, marker, receiveTime, renderer)

    this.#group = new THREE.Group()
    this.add(this.#group)

    this.update(marker, receiveTime, true)
  }

  public override dispose(): void {
    this.#group.traverse((obj) => {
      if (obj instanceof THREE.Mesh) {
        if (Array.isArray(obj.material)) {
          obj.material.forEach((m) => m.dispose())
        } else {
          obj.material.dispose()
        }
        obj.geometry.dispose()
      }
    })
    super.dispose()
  }

  public override update(
    newMarker: Marker,
    receiveTime: bigint | undefined,
    forceReload = false
  ): void {
    super.update(newMarker, receiveTime)
    const marker = this.userData.marker

    this.scale.set(marker.scale.x, marker.scale.y, marker.scale.z)

    // Reload mesh if URL changed or forced
    if (marker.mesh_resource !== this.#loadedUrl || forceReload) {
      this.#loadedUrl = marker.mesh_resource
      this.#loadMesh(marker)
    } else {
      // Update material colors
      this.#updateColors(marker)
    }
  }

  async #loadMesh(marker: Marker): Promise<void> {
    // Clear previous group children
    this.#group.remove(...this.#group.children)

    const url = marker.mesh_resource
    if (!url) return

    try {
      // We delegate to renderer's ModelCache if available, else use a placeholder box
      let cachedObj: THREE.Object3D | undefined
      if ((this.renderer as any).modelCache) {
        cachedObj = await (this.renderer as any).modelCache.load(url)
      }

      if (!cachedObj) {
        // Fallback: placeholder box
        const geo = new THREE.BoxGeometry(0.1, 0.1, 0.1)
        const mat = makeStandardMaterial(marker.color)
        cachedObj = new THREE.Mesh(geo, mat)
      }

      const cloned = cachedObj.clone(true)
      if (!marker.mesh_use_embedded_materials) {
        cloned.traverse((obj) => {
          if (obj instanceof THREE.Mesh) {
            obj.material = makeStandardMaterial(marker.color)
          }
        })
      }
      this.#group.add(cloned)
    } catch (e) {
      console.warn('[RenderableMeshResource] Failed to load mesh:', url, e)
    }
  }

  #updateColors(marker: Marker): void {
    if (marker.mesh_use_embedded_materials) return

    rgbToThreeColor(_tempColor, marker.color)
    this.#group.traverse((obj) => {
      if (obj instanceof THREE.Mesh) {
        const mat = obj.material as THREE.MeshStandardMaterial
        if (mat.isMeshStandardMaterial) {
          mat.color.set(_tempColor)
          mat.opacity = marker.color.a
          mat.transparent = marker.color.a < 1
          mat.needsUpdate = true
        }
      }
    })
  }
}
