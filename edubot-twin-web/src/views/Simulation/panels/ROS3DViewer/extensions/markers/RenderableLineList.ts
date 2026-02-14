// SPDX-License-Identifier: MPL-2.0
// RenderableLineList — renders LINE_LIST markers as Three.js LineSegments

import * as THREE from 'three'
import type { IRenderer } from '../../core/IRenderer'
import type { Marker } from '../../core/ros'

/**
 * A renderable that displays `LINE_LIST` type markers using Three.js LineSegments.
 */
export class RenderableLineList extends THREE.Object3D {
  readonly #renderer: IRenderer
  #lineSegments: THREE.LineSegments | null = null
  #worldUnits: boolean

  public constructor(
    name: string,
    marker: Marker,
    _receiveTime: bigint | undefined,
    renderer: IRenderer,
    options?: { worldUnits?: boolean }
  ) {
    super()
    this.name = name
    this.#renderer = renderer
    this.#worldUnits = options?.worldUnits ?? false
    this.update(marker, _receiveTime)
  }

  public update(marker: Marker, _receiveTime: bigint | undefined): void {
    // Clean up previous geometry
    if (this.#lineSegments) {
      this.remove(this.#lineSegments)
      this.#lineSegments.geometry.dispose()
      ;(this.#lineSegments.material as THREE.Material).dispose()
      this.#lineSegments = null
    }

    const points = marker.points
    if (!points || points.length < 2) return

    // Build position buffer from marker points
    const positions = new Float32Array(points.length * 3)
    for (let i = 0; i < points.length; i++) {
      const p = points[i]!
      positions[i * 3 + 0] = p.x
      positions[i * 3 + 1] = p.y
      positions[i * 3 + 2] = p.z
    }

    const geometry = new THREE.BufferGeometry()
    geometry.setAttribute('position', new THREE.BufferAttribute(positions, 3))

    // Use per-vertex colors if available, otherwise use marker color
    let material: THREE.LineBasicMaterial
    if (marker.colors && marker.colors.length >= points.length) {
      const colors = new Float32Array(points.length * 3)
      for (let i = 0; i < points.length; i++) {
        const c = marker.colors[i]!
        colors[i * 3 + 0] = c.r
        colors[i * 3 + 1] = c.g
        colors[i * 3 + 2] = c.b
      }
      geometry.setAttribute('color', new THREE.BufferAttribute(colors, 3))
      material = new THREE.LineBasicMaterial({
        vertexColors: true,
        linewidth: this.#worldUnits ? (marker.scale?.x ?? 1) : 1,
        transparent: true,
        opacity: marker.color?.a ?? 1.0,
        depthWrite: false
      })
    } else {
      const color = marker.color
        ? new THREE.Color(marker.color.r, marker.color.g, marker.color.b)
        : new THREE.Color(0.5, 0.5, 0.5)
      material = new THREE.LineBasicMaterial({
        color,
        linewidth: this.#worldUnits ? (marker.scale?.x ?? 1) : 1,
        transparent: true,
        opacity: marker.color?.a ?? 1.0,
        depthWrite: false
      })
    }

    this.#lineSegments = new THREE.LineSegments(geometry, material)
    this.#lineSegments.frustumCulled = false
    this.add(this.#lineSegments)

    void this.#renderer
  }

  public dispose(): void {
    if (this.#lineSegments) {
      this.#lineSegments.geometry.dispose()
      ;(this.#lineSegments.material as THREE.Material).dispose()
      this.remove(this.#lineSegments)
      this.#lineSegments = null
    }
  }
}
