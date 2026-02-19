// SPDX-License-Identifier: MPL-2.0
// Marker materials — 本项目简化版（无 LineMaterialWithAlphaVertex 依赖）

import * as THREE from 'three'
import type { ColorRGBA, Marker, MarkerType as MarkerTypeEnum } from '../../core/ros'
import { MarkerType } from '../../core/ros'

export type LineOptions = {
  resolution?: THREE.Vector2
  worldUnits?: boolean
}

/**
 * 判断 marker 是否含有透明度
 */
export function markerHasTransparency(marker: Marker): boolean {
  switch (marker.type as MarkerTypeEnum) {
    case MarkerType.ARROW:
    case MarkerType.CUBE:
    case MarkerType.SPHERE:
    case MarkerType.CYLINDER:
    case MarkerType.TEXT_VIEW_FACING:
    case MarkerType.MESH_RESOURCE:
      return marker.color.a < 1.0
    default:
      for (const color of marker.colors) {
        if (color.a < 1.0) return true
      }
      return marker.colors.length >= marker.points.length ? false : marker.color.a < 1.0
  }
}

/**
 * 通用 MeshStandardMaterial — 用于实体 marker（Arrow/Cube/Sphere/Cylinder）
 */
export function makeStandardMaterial(color: ColorRGBA): THREE.MeshStandardMaterial {
  return new THREE.MeshStandardMaterial({
    color: new THREE.Color(color.r, color.g, color.b).convertSRGBToLinear(),
    metalness: 0,
    roughness: 1,
    dithering: true,
    opacity: color.a,
    transparent: color.a < 1,
    depthWrite: color.a === 1
  })
}

/**
 * 顶点色 MeshStandardMaterial — 用于 TriangleList
 */
export function makeStandardVertexColorMaterial(marker: Marker): THREE.MeshStandardMaterial {
  const transparent = markerHasTransparency(marker)
  return new THREE.MeshStandardMaterial({
    metalness: 0,
    roughness: 1,
    dithering: true,
    vertexColors: true,
    side: THREE.DoubleSide,
    opacity: 1,
    transparent,
    depthWrite: !transparent
  })
}

/**
 * Instanced MeshStandardMaterial — 用于 CubeList / SphereList
 */
export function makeStandardInstancedMaterial(marker: Marker): THREE.MeshStandardMaterial {
  const transparent = markerHasTransparency(marker)
  return new THREE.MeshStandardMaterial({
    metalness: 0,
    roughness: 1,
    dithering: true,
    opacity: 1,
    transparent,
    depthWrite: !transparent
  })
}

/**
 * 折线材质（简化版，使用 THREE.LineBasicMaterial 代替 LineMaterialWithAlphaVertex）
 */
export function makeLineMaterial(marker: Marker, _options?: LineOptions): THREE.LineBasicMaterial {
  const transparent = markerHasTransparency(marker)
  const color = marker.color
  return new THREE.LineBasicMaterial({
    color: new THREE.Color(color.r, color.g, color.b).convertSRGBToLinear(),
    opacity: color.a,
    transparent,
    depthWrite: !transparent,
    vertexColors: marker.colors.length > 0
  })
}

/**
 * 点精灵材质 — 用于 POINTS marker
 */
export function makePointsMaterial(marker: Marker): THREE.PointsMaterial {
  const transparent = markerHasTransparency(marker)
  return new THREE.PointsMaterial({
    vertexColors: true,
    size: marker.scale.x,
    sizeAttenuation: true,
    transparent,
    depthWrite: !transparent
  })
}

/**
 * Picking stub（本项目不使用 GPU picking，保留接口兼容性）
 */
export function makeLinePickingMaterial(
  _lineSize: number,
  _options?: LineOptions
): THREE.ShaderMaterial {
  return new THREE.ShaderMaterial({
    vertexShader: `void main() { gl_Position = projectionMatrix * modelViewMatrix * vec4(position, 1.0); }`,
    fragmentShader: `uniform vec4 objectId; void main() { gl_FragColor = objectId; }`,
    uniforms: { objectId: { value: [NaN, NaN, NaN, NaN] } },
    clipping: true,
    depthTest: true,
    depthWrite: true
  })
}

/**
 * Prepass 占位（本项目不做深度预通道）
 */
export function makeLinePrepassMaterial(
  marker: Marker,
  options?: LineOptions
): THREE.LineBasicMaterial {
  return makeLineMaterial(marker, options)
}
