// SPDX-License-Identifier: MPL-2.0
// Stub: marker materials — will be fully implemented when Markers extension is integrated

import * as THREE from 'three'

/**
 * Creates a ShaderMaterial used for picking lines in the GPU picker pass.
 */
export function makeLinePickingMaterial(
  _lineSize: number,
  _options?: { resolution?: THREE.Vector2; worldUnits?: boolean }
): THREE.ShaderMaterial {
  return new THREE.ShaderMaterial({
    vertexShader: `
      void main() {
        gl_Position = projectionMatrix * modelViewMatrix * vec4(position, 1.0);
      }
    `,
    fragmentShader: `
      void main() {
        gl_FragColor = vec4(1.0, 0.0, 0.0, 1.0);
      }
    `,
    side: THREE.DoubleSide,
    depthTest: true,
    depthWrite: true
  })
}
