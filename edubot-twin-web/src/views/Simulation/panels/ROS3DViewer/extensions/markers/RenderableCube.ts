// SPDX-License-Identifier: MPL-2.0
// RenderableCube — Cube marker (type=1)

import * as THREE from 'three'

import { RenderableMarker } from './RenderableMarker'
import { makeStandardMaterial } from './materials'
import type { IRenderer } from '../../core/IRenderer'
import { rgbToThreeColor } from '../../core/color'
import { Marker } from '../../core/ros'

export class RenderableCube extends RenderableMarker {
  #mesh: THREE.Mesh<THREE.BoxGeometry, THREE.MeshStandardMaterial>
  #outline: THREE.LineSegments

  public constructor(
    topic: string,
    marker: Marker,
    receiveTime: bigint | undefined,
    renderer: IRenderer
  ) {
    super(topic, marker, receiveTime, renderer)

    const cubeGeometry = renderer.sharedGeometry.getGeometry(
      `${this.constructor.name}-cube`,
      createGeometry
    )
    const cubeEdgesGeometry = renderer.sharedGeometry.getGeometry(
      `${this.constructor.name}-cube-edges`,
      () => {
        const eg = new THREE.EdgesGeometry(cubeGeometry, 40)
        eg.computeBoundingSphere()
        return eg
      }
    )

    this.#mesh = new THREE.Mesh(cubeGeometry, makeStandardMaterial(marker.color))
    this.#mesh.castShadow = true
    this.#mesh.receiveShadow = true
    this.add(this.#mesh)

    this.#outline = new THREE.LineSegments(cubeEdgesGeometry, renderer.outlineMaterial)
    this.#outline.userData.picking = false
    this.#mesh.add(this.#outline)

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

    this.#outline.visible = this.getSettings()?.showOutlines ?? true
    rgbToThreeColor(this.#mesh.material.color, marker.color)
    this.#mesh.material.opacity = marker.color.a
    this.scale.set(marker.scale.x, marker.scale.y, marker.scale.z)
  }
}

function createGeometry(): THREE.BoxGeometry {
  const g = new THREE.BoxGeometry(1, 1, 1)
  g.computeBoundingSphere()
  return g
}
