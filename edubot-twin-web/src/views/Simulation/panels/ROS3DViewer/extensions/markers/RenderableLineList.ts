// SPDX-License-Identifier: MPL-2.0
// Stub: RenderableLineList — will be fully implemented when Markers extension is integrated

import * as THREE from 'three'
import type { IRenderer } from '../../core/IRenderer'
import type { Marker } from '../../core/ros'

/**
 * A renderable that displays `LINE_LIST` type markers.
 * Stub implementation — renders nothing but satisfies the type contract.
 */
export class RenderableLineList extends THREE.Object3D {
  readonly #renderer: IRenderer

  public constructor(
    name: string,
    _marker: Marker,
    _receiveTime: bigint | undefined,
    renderer: IRenderer,
    _options?: { worldUnits?: boolean }
  ) {
    super()
    this.name = name
    this.#renderer = renderer
  }

  public update(_marker: Marker, _receiveTime: bigint | undefined): void {
    // Stub — full implementation will generate Line2 geometry from marker data
    void this.#renderer
  }

  public dispose(): void {
    // Stub — full implementation will dispose geometries and materials
  }
}
