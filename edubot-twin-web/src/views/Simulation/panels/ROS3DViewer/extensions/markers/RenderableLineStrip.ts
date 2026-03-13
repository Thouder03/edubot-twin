// SPDX-License-Identifier: MPL-2.0
// RenderableLineStrip — LINE_STRIP marker (type=4)
// 将连续点渲染为 THREE.Line

import * as THREE from 'three'
import { Line2 } from 'three/examples/jsm/lines/Line2'
import { LineGeometry } from 'three/examples/jsm/lines/LineGeometry'
import { LineMaterial } from 'three/examples/jsm/lines/LineMaterial'

import { RenderableMarker } from './RenderableMarker'
import { markerHasTransparency } from './materials'
import type { IRenderer } from '../../core/IRenderer'
import { Marker } from '../../core/ros'

export class RenderableLineStrip extends RenderableMarker {
  #geometry: LineGeometry
  #line: Line2
  #positionBuffer: number[] = []
  #colorBuffer: number[] = []

  public constructor(
    topic: string,
    marker: Marker,
    receiveTime: bigint | undefined,
    renderer: IRenderer
  ) {
    super(topic, marker, receiveTime, renderer)

    this.#geometry = new LineGeometry()
    const transparent = markerHasTransparency(marker)
    const lineWidth = marker.scale?.x ?? 0.1

    const material = new LineMaterial({
      color: 0xffffff,
      linewidth: lineWidth, // in world units if worldUnits=true, else in pixels
      vertexColors: true,
      dashed: false,
      alphaToCoverage: true,
      worldUnits: true,
      transparent,
      depthWrite: !transparent
    })

    this.#line = new Line2(this.#geometry, material)
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
    const mat = this.#line.material as LineMaterial
    const lineWidth = marker.scale?.x ?? 0.1

    // 更新线宽
    if (mat.linewidth !== lineWidth) {
      mat.linewidth = lineWidth
      mat.needsUpdate = true
    }

    if (transparent !== markerHasTransparency(prevMarker)) {
      mat.transparent = transparent
      mat.depthWrite = !transparent
      mat.needsUpdate = true
    }

    this.#setPositions(marker, pointsLength)
    this.#setColors(marker, pointsLength)
  }

  #setPositions(marker: Marker, pointsLength: number): void {
    const buf = this.#positionBuffer
    buf.length = pointsLength * 3
    for (let i = 0; i < pointsLength; i++) {
      const p = marker.points[i]!
      buf[i * 3 + 0] = p.x
      buf[i * 3 + 1] = p.y
      buf[i * 3 + 2] = p.z
    }
    this.#geometry.setPositions(buf)
  }

  #setColors(marker: Marker, pointsLength: number): void {
    const buf = this.#colorBuffer
    buf.length = pointsLength * 3
    this._markerColorsToLinear(marker, pointsLength, (color, i) => {
      buf[i * 3 + 0] = color[0]
      buf[i * 3 + 1] = color[1]
      buf[i * 3 + 2] = color[2]
    })
    this.#geometry.setColors(buf)
  }
}
