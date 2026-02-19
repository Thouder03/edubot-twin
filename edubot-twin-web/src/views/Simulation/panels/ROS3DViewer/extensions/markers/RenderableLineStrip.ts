// SPDX-License-Identifier: MPL-2.0
// RenderableLineStrip — LINE_STRIP marker (type=4)
// 将连续点渲染为 THREE.Line

import * as THREE from 'three'

import { RenderableMarker } from './RenderableMarker'
import { markerHasTransparency } from './materials'
import type { IRenderer } from '../../core/IRenderer'
import { Marker } from '../../core/ros'

export class RenderableLineStrip extends RenderableMarker {
  #geometry: THREE.BufferGeometry
  #line: THREE.Line
  #positionBuffer = new Float32Array()
  #colorBuffer = new Float32Array()

  public constructor(
    topic: string,
    marker: Marker,
    receiveTime: bigint | undefined,
    renderer: IRenderer
  ) {
    super(topic, marker, receiveTime, renderer)

    this.#geometry = new THREE.BufferGeometry()
    const transparent = markerHasTransparency(marker)
    const material = new THREE.LineBasicMaterial({
      vertexColors: true,
      transparent,
      depthWrite: !transparent
    })
    this.#line = new THREE.Line(this.#geometry, material)
    this.#line.frustumCulled = false
    this.add(this.#line)

    this.update(marker, receiveTime)
  }

  public override dispose(): void {
    ;(this.#line.material as THREE.Material).dispose()
    this.#geometry.dispose()
    super.dispose()
  }

  public override update(newMarker: Marker, receiveTime: bigint | undefined): void {
    const prevMarker = this.userData.marker
    super.update(newMarker, receiveTime)
    const marker = this.userData.marker

    const pointsLength = marker.points.length

    if (pointsLength === 0) {
      this.#line.visible = false
      return
    }
    this.#line.visible = true

    const transparent = markerHasTransparency(marker)
    const mat = this.#line.material as THREE.LineBasicMaterial
    if (transparent !== markerHasTransparency(prevMarker)) {
      mat.transparent = transparent
      mat.depthWrite = !transparent
      mat.needsUpdate = true
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
    this.#geometry.setAttribute(
      'position',
      new THREE.BufferAttribute(buf.subarray(0, pointsLength * 3), 3)
    )
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
    this.#geometry.setAttribute(
      'color',
      new THREE.BufferAttribute(buf.subarray(0, pointsLength * 3), 3)
    )
    this.#geometry.getAttribute('position').needsUpdate = true
  }
}
