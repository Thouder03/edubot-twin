// SPDX-License-Identifier: MPL-2.0
// RenderableSphereList — SPHERE_LIST marker (type=7)
// 使用 InstancedMesh 高效渲染大量球体

import * as THREE from 'three'

import { RenderableMarker } from './RenderableMarker'
import { makeStandardInstancedMaterial, markerHasTransparency } from './materials'
import type { IRenderer } from '../../core/IRenderer'
import { sphereSubdivisions } from '../../core/lod'
import { Marker } from '../../core/ros'

const tempColor = new THREE.Color()
const tempMatrix = new THREE.Matrix4()
const tempQuaternion = new THREE.Quaternion()

export class RenderableSphereList extends RenderableMarker {
  #mesh: THREE.InstancedMesh<THREE.SphereGeometry, THREE.MeshStandardMaterial>
  #count = 0

  public constructor(
    topic: string,
    marker: Marker,
    receiveTime: bigint | undefined,
    renderer: IRenderer
  ) {
    super(topic, marker, receiveTime, renderer)

    const geometry = renderer.sharedGeometry.getGeometry(
      `RenderableSphereList-${renderer.maxLod}`,
      () => {
        const subdivisions = sphereSubdivisions(renderer.maxLod)
        const g = new THREE.SphereGeometry(0.5, subdivisions, subdivisions)
        g.computeBoundingSphere()
        return g
      }
    )

    const count = Math.max(1, marker.points.length)
    this.#mesh = new THREE.InstancedMesh(geometry, makeStandardInstancedMaterial(marker), count)
    this.#mesh.castShadow = true
    this.#mesh.receiveShadow = true
    this.#mesh.frustumCulled = false
    this.add(this.#mesh)

    this.update(marker, receiveTime)
  }

  public override dispose(): void {
    this.#mesh.material.dispose()
    super.dispose()
  }

  public override update(newMarker: Marker, receiveTime: bigint | undefined): void {
    const prevMarker = this.userData.marker
    super.update(newMarker, receiveTime)
    const marker = this.userData.marker

    const pointsLength = marker.points.length
    const transparent = markerHasTransparency(marker)

    if (transparent !== markerHasTransparency(prevMarker)) {
      this.#mesh.material.transparent = transparent
      this.#mesh.material.depthWrite = !transparent
      this.#mesh.material.needsUpdate = true
    }

    if (pointsLength > this.#count) {
      this.remove(this.#mesh)
      this.#mesh.dispose()
      const geometry = this.#mesh.geometry
      this.#mesh = new THREE.InstancedMesh(geometry, this.#mesh.material, pointsLength)
      this.#mesh.castShadow = true
      this.#mesh.receiveShadow = true
      this.#mesh.frustumCulled = false
      this.add(this.#mesh)
    }

    this.#mesh.count = pointsLength
    this.#count = pointsLength

    const scale = marker.scale
    this._markerColorsToLinear(marker, pointsLength, (color, i) => {
      const p = marker.points[i]!
      tempMatrix.compose(
        new THREE.Vector3(p.x, p.y, p.z),
        tempQuaternion.identity(),
        new THREE.Vector3(scale.x, scale.y, scale.z)
      )
      this.#mesh.setMatrixAt(i, tempMatrix)

      tempColor.setRGB(color[0], color[1], color[2])
      this.#mesh.setColorAt(i, tempColor)
    })

    this.#mesh.instanceMatrix.needsUpdate = true
    if (this.#mesh.instanceColor) this.#mesh.instanceColor.needsUpdate = true
  }
}
