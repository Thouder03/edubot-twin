// SPDX-License-Identifier: MPL-2.0
// RenderableTextViewFacing — TEXT_VIEW_FACING marker (type=9)
// 使用 CSS2DRenderer 或 sprite 显示文字（简化：使用 CanvasTexture sprite）

import * as THREE from 'three'

import { RenderableMarker } from './RenderableMarker'

import type { IRenderer } from '../../core/IRenderer'
import { rgbToThreeColor } from '../../core/color'
import { Marker } from '../../core/ros'

const DPI = 2 // 渲染分辨率倍数（抗锯齿）
const FONT_SIZE_PX = 48

const _tempColor = new THREE.Color()

export class RenderableTextViewFacing extends RenderableMarker {
  #sprite: THREE.Sprite
  #canvas: HTMLCanvasElement
  #ctx: CanvasRenderingContext2D
  #texture: THREE.CanvasTexture
  #currentText = ''

  public constructor(
    topic: string,
    marker: Marker,
    receiveTime: bigint | undefined,
    renderer: IRenderer
  ) {
    super(topic, marker, receiveTime, renderer)

    this.#canvas = document.createElement('canvas')
    this.#canvas.width = 256 * DPI
    this.#canvas.height = 64 * DPI
    this.#ctx = this.#canvas.getContext('2d')!
    this.#texture = new THREE.CanvasTexture(this.#canvas)

    const material = new THREE.SpriteMaterial({
      map: this.#texture,
      transparent: true,
      depthTest: false
    })
    this.#sprite = new THREE.Sprite(material)
    this.#sprite.userData.picking = false
    this.add(this.#sprite)

    this.update(marker, receiveTime)
  }

  public override dispose(): void {
    this.#sprite.material.dispose()
    this.#texture.dispose()
    super.dispose()
  }

  public override update(newMarker: Marker, receiveTime: bigint | undefined): void {
    super.update(newMarker, receiveTime)
    const marker = this.userData.marker

    // 只在文字变化时重新绘制
    if (marker.text !== this.#currentText) {
      this.#currentText = marker.text
      this.#drawText(marker)
    }

    // 更新颜色和透明度
    rgbToThreeColor(_tempColor, marker.color)
    this.#sprite.material.color.set(_tempColor)
    this.#sprite.material.opacity = marker.color.a
    this.#sprite.material.needsUpdate = true

    // scale.z 为 ROS 文字高度（单位：m）
    const height = marker.scale.z || 0.1
    const aspect = this.#canvas.width / this.#canvas.height
    this.#sprite.scale.set(height * aspect, height, 1)
  }

  #drawText(marker: Marker): void {
    const ctx = this.#ctx
    const w = this.#canvas.width
    const h = this.#canvas.height
    ctx.clearRect(0, 0, w, h)

    const fontSize = FONT_SIZE_PX * DPI
    ctx.font = `bold ${fontSize}px sans-serif`
    ctx.textBaseline = 'middle'
    ctx.textAlign = 'center'
    ctx.fillStyle = `rgba(${Math.round(marker.color.r * 255)}, ${Math.round(marker.color.g * 255)}, ${Math.round(marker.color.b * 255)}, ${marker.color.a})`
    ctx.fillText(marker.text, w / 2, h / 2)

    this.#texture.needsUpdate = true
  }
}
