// SPDX-License-Identifier: MPL-2.0
// RenderableTriangleList — TRIANGLE_LIST marker (type=11)
// 前三点一个三角形，顶点色

import * as THREE from 'three'

import { RenderableMarker } from './RenderableMarker'
import { makeStandardVertexColorMaterial, markerHasTransparency } from './materials'
import type { IRenderer } from '../../core/IRenderer'
import { Marker } from '../../core/ros'

export class RenderableTriangleList extends RenderableMarker {
  #mesh: THREE.Mesh<THREE.BufferGeometry, THREE.MeshStandardMaterial>
  #positionBuffer = new Float32Array()
  #colorBuffer = new Float32Array()

  public constructor(
    topic: string,
    marker: Marker,
    receiveTime: bigint | undefined,
    renderer: IRenderer
  ) {
    super(topic, marker, receiveTime, renderer)

    const geometry = new THREE.BufferGeometry()
    this.#mesh = new THREE.Mesh(geometry, makeStandardVertexColorMaterial(marker))
    this.#mesh.castShadow = true
    this.#mesh.receiveShadow = true
    this.#mesh.frustumCulled = false
    this.add(this.#mesh)

    this.update(marker, receiveTime)
  }

  public override dispose(): void {
    this.#mesh.material.dispose()
    this.#mesh.geometry.dispose()
    super.dispose()
  }

  public override update(newMarker: Marker, receiveTime: bigint | undefined): void {
    const prevMarker = this.userData.marker
    super.update(newMarker, receiveTime)
    const marker = this.userData.marker

    // TRIANGLE_LIST: every 3 points = 1 triangle
    let pointsLength = marker.points.length
    const remainder = pointsLength % 3
    if (remainder !== 0) pointsLength -= remainder

    const transparent = markerHasTransparency(marker)
    if (transparent !== markerHasTransparency(prevMarker)) {
      this.#mesh.material.transparent = transparent
      this.#mesh.material.depthWrite = !transparent
      this.#mesh.material.needsUpdate = true
    }

    this.#setPositions(marker, pointsLength)
    this.#setColors(marker, pointsLength)
  }

  #setPositions(marker: Marker, pointsLength: number): void {
    if (3 * pointsLength > this.#positionBuffer.length) {
      this.#positionBuffer = new Float32Array(3 * pointsLength)
    }
    const buf = this.#positionBuffer
    for (let i = 0; i < pointsLength; i++) {
      const p = marker.points[i]!
      buf[i * 3 + 0] = p.x
      buf[i * 3 + 1] = p.y
      buf[i * 3 + 2] = p.z
    }
    this.#mesh.geometry.setAttribute(
      'position',
      new THREE.BufferAttribute(buf.subarray(0, pointsLength * 3), 3)
    )
    this.#mesh.geometry.computeVertexNormals()
  }

  #setColors(marker: Marker, pointsLength: number): void {
    if (3 * pointsLength > this.#colorBuffer.length) {
      this.#colorBuffer = new Float32Array(3 * pointsLength)
    }
    const buf = this.#colorBuffer
    this._markerColorsToLinear(marker, pointsLength, (color, i) => {
      buf[i * 3 + 0] = color[0]
      buf[i * 3 + 1] = color[1]
      buf[i * 3 + 2] = color[2]
    })
    this.#mesh.geometry.setAttribute(
      'color',
      new THREE.BufferAttribute(buf.subarray(0, pointsLength * 3), 3)
    )
  }
}
