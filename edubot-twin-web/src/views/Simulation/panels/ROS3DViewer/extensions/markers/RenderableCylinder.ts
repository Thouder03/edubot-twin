// SPDX-License-Identifier: MPL-2.0
// RenderableCylinder — Cylinder marker (type=3)

import * as THREE from 'three'

import { RenderableMarker } from './RenderableMarker'
import { makeStandardMaterial } from './materials'
import type { IRenderer } from '../../core/IRenderer'
import { rgbToThreeColor } from '../../core/color'
import { cylinderSubdivisions } from '../../core/lod'
import { Marker } from '../../core/ros'

export class RenderableCylinder extends RenderableMarker {
  #mesh: THREE.Mesh<THREE.CylinderGeometry, THREE.MeshStandardMaterial>

  public constructor(
    topic: string,
    marker: Marker,
    receiveTime: bigint | undefined,
    renderer: IRenderer
  ) {
    super(topic, marker, receiveTime, renderer)

    const geometry = renderer.sharedGeometry.getGeometry(
      `${this.constructor.name}-${renderer.maxLod}`,
      () => {
        const subdivisions = cylinderSubdivisions(renderer.maxLod)
        const g = new THREE.CylinderGeometry(0.5, 0.5, 1, subdivisions, 1, false)
        g.computeBoundingSphere()
        return g
      }
    )
    this.#mesh = new THREE.Mesh(geometry, makeStandardMaterial(marker.color))
    this.#mesh.castShadow = true
    this.#mesh.receiveShadow = true
    this.add(this.#mesh)

    this.update(marker, receiveTime)
  }

  public override dispose(): void {
    this.#mesh.material.dispose()
    super.dispose()
  }

  public override update(newMarker: Marker, receiveTime: bigint | undefined): void {
    super.update(newMarker, receiveTime)
    const marker = this.userData.marker

    const transparent = marker.color.a < 1
    if (transparent !== this.#mesh.material.transparent) {
      this.#mesh.material.transparent = transparent
      this.#mesh.material.depthWrite = !transparent
      this.#mesh.material.needsUpdate = true
    }

    rgbToThreeColor(this.#mesh.material.color, marker.color)
    this.#mesh.material.opacity = marker.color.a
    // ROS Cylinder: scale.x=diameter_x, scale.y=diameter_y（圆截面用x代替直径）, scale.z=height
    this.scale.set(marker.scale.x, marker.scale.z, marker.scale.y)
  }
}
