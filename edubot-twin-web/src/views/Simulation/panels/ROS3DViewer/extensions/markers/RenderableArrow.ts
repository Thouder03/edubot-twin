// SPDX-License-Identifier: MPL-2.0
// RenderableArrow — Arrow marker (type=0)

import * as THREE from 'three'
import { clamp } from 'three/src/math/MathUtils.js'

import { RenderableMarker } from './RenderableMarker'
import { makeStandardMaterial } from './materials'
import type { IRenderer } from '../../core/IRenderer'
import { rgbToThreeColor } from '../../core/color'
import { arrowHeadSubdivisions, arrowShaftSubdivisions } from '../../core/lod'
import { getRotationTo } from '../../core/math'
import { Marker } from '../../core/ros'

const SHAFT_LENGTH = 0.77
const SHAFT_DIAMETER = 1.0
const HEAD_LENGTH = 0.23
const HEAD_DIAMETER = 2.0
const HEAD_LENGTH_PROPORTION = 0.23

const UNIT_X = new THREE.Vector3(1, 0, 0)
const tempStart = new THREE.Vector3()
const tempEnd = new THREE.Vector3()
const tempDirection = new THREE.Vector3()

export class RenderableArrow extends RenderableMarker {
  public shaftMesh: THREE.Mesh<THREE.CylinderGeometry, THREE.MeshStandardMaterial>
  public headMesh: THREE.Mesh<THREE.ConeGeometry, THREE.MeshStandardMaterial>
  #shaftOutline: THREE.LineSegments
  #headOutline: THREE.LineSegments

  public constructor(
    topic: string,
    marker: Marker,
    receiveTime: bigint | undefined,
    renderer: IRenderer
  ) {
    super(topic, marker, receiveTime, renderer)

    const shaftGeometry = renderer.sharedGeometry.getGeometry(
      `${this.constructor.name}-shaft-${renderer.maxLod}`,
      () => createShaftGeometry(renderer.maxLod)
    )
    const headGeometry = renderer.sharedGeometry.getGeometry(
      `${this.constructor.name}-head-${renderer.maxLod}`,
      () => createHeadGeometry(renderer.maxLod)
    )
    const shaftEdgesGeometry = renderer.sharedGeometry.getGeometry(
      `${this.constructor.name}-shaft-edges-${renderer.maxLod}`,
      () => new THREE.EdgesGeometry(shaftGeometry, 40)
    )
    const headEdgesGeometry = renderer.sharedGeometry.getGeometry(
      `${this.constructor.name}-head-edges-${renderer.maxLod}`,
      () => {
        const g = new THREE.EdgesGeometry(headGeometry, 40)
        g.computeBoundingSphere()
        return g
      }
    )

    this.shaftMesh = new THREE.Mesh(shaftGeometry, makeStandardMaterial(marker.color))
    this.shaftMesh.castShadow = true
    this.shaftMesh.receiveShadow = true
    this.add(this.shaftMesh)

    this.headMesh = new THREE.Mesh(headGeometry, makeStandardMaterial(marker.color))
    this.headMesh.castShadow = true
    this.headMesh.receiveShadow = true
    this.add(this.headMesh)

    this.#shaftOutline = new THREE.LineSegments(shaftEdgesGeometry, renderer.outlineMaterial)
    this.#shaftOutline.userData.picking = false
    this.shaftMesh.add(this.#shaftOutline)

    this.#headOutline = new THREE.LineSegments(headEdgesGeometry, renderer.outlineMaterial)
    this.#headOutline.userData.picking = false
    this.headMesh.add(this.#headOutline)

    this.update(marker, receiveTime)
  }

  public override dispose(): void {
    this.shaftMesh.material.dispose()
    this.headMesh.material.dispose()
    super.dispose()
  }

  public override update(newMarker: Marker, receiveTime: bigint | undefined): void {
    super.update(newMarker, receiveTime)
    const marker = this.userData.marker

    const transparent = marker.color.a < 1
    if (transparent !== this.shaftMesh.material.transparent) {
      this.shaftMesh.material.transparent = transparent
      this.shaftMesh.material.depthWrite = !transparent
      this.shaftMesh.material.needsUpdate = true
      this.headMesh.material.transparent = transparent
      this.headMesh.material.depthWrite = !transparent
      this.headMesh.material.needsUpdate = true
    }

    rgbToThreeColor(this.shaftMesh.material.color, marker.color)
    this.shaftMesh.material.opacity = marker.color.a
    this.headMesh.material.color.set(this.shaftMesh.material.color)
    this.headMesh.material.opacity = marker.color.a

    const settings = this.getSettings()
    this.#shaftOutline.visible = settings?.showOutlines ?? true
    this.#headOutline.visible = settings?.showOutlines ?? true

    if (marker.points.length === 2) {
      const pointA = marker.points[0]!
      const pointB = marker.points[1]!
      tempStart.set(pointA.x, pointA.y, pointA.z)
      tempEnd.set(pointB.x, pointB.y, pointB.z)
      tempDirection.subVectors(tempEnd, tempStart)
      const distance = tempDirection.length()

      let headLength = HEAD_LENGTH_PROPORTION * distance
      if (marker.scale.z !== 0) {
        headLength = clamp(marker.scale.z, 0, distance)
      }
      const shaftLength = distance - headLength
      const shaftDiameter = marker.scale.x
      const headDiameter = marker.scale.y

      this.shaftMesh.scale.set(shaftLength, shaftDiameter, shaftDiameter)
      this.headMesh.scale.set(headLength, headDiameter, headDiameter)
      this.scale.set(1, 1, 1)
      this.shaftMesh.position.set(pointA.x, pointA.y, pointA.z)
      this.shaftMesh.position.addScaledVector(tempDirection, 0.5 * (shaftLength / distance))
      this.headMesh.position.set(pointB.x, pointB.y, pointB.z)
      this.headMesh.position.addScaledVector(tempDirection, -0.5 * (headLength / distance))

      const rotation = getRotationTo(UNIT_X, tempDirection)
      this.shaftMesh.setRotationFromQuaternion(rotation)
      this.headMesh.rotation.copy(this.shaftMesh.rotation)
    } else {
      this.shaftMesh.scale.set(SHAFT_LENGTH, SHAFT_DIAMETER, SHAFT_DIAMETER)
      this.headMesh.scale.set(HEAD_LENGTH, HEAD_DIAMETER, HEAD_DIAMETER)
      this.scale.set(marker.scale.x, marker.scale.y, marker.scale.z)

      const halfShaft = SHAFT_LENGTH / 2
      const halfHead = HEAD_LENGTH / 2
      this.shaftMesh.position.set(halfShaft, 0, 0)
      this.headMesh.position.set(halfShaft * 2 + halfHead, 0, 0)
      this.shaftMesh.rotation.set(0, 0, 0)
      this.headMesh.rotation.set(0, 0, 0)
    }
  }
}

function createShaftGeometry(lod: import('../../core/lod').DetailLevel): THREE.CylinderGeometry {
  const subdivs = arrowShaftSubdivisions(lod)
  const g = new THREE.CylinderGeometry(0.5, 0.5, 1, subdivs, 1, false)
  g.rotateZ(-Math.PI / 2)
  g.computeBoundingSphere()
  return g
}

function createHeadGeometry(lod: import('../../core/lod').DetailLevel): THREE.ConeGeometry {
  const subdivs = arrowHeadSubdivisions(lod)
  const g = new THREE.ConeGeometry(0.5, 1, subdivs, 1, false)
  g.rotateZ(-Math.PI / 2)
  g.computeBoundingSphere()
  return g
}
