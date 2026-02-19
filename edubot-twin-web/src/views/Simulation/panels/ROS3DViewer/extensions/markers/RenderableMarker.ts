// SPDX-License-Identifier: MPL-2.0
// RenderableMarker — 所有 Marker 渲染类的基类（移植自 lichtblick）

import * as THREE from 'three'

import type { RosValue } from '../../core/lichtblick-shim'
import type { IRenderer } from '../../core/IRenderer'
import { Renderable, BaseUserData, SELECTED_ID_VARIABLE } from '../../core/Renderable'
import { makeRgba, stringToRgba, rgbToThreeColor } from '../../core/color'
import { Marker } from '../../core/ros'

export type LayerSettingsMarker = {
  visible: boolean
  color: string | undefined
  showOutlines: boolean | undefined
  selectedIdVariable: string | undefined
  namespaces?: Record<string, { visible: boolean }>
}

const tempColor = new THREE.Color()
const tempColor2 = new THREE.Color()
const tempTuple4: THREE.Vector4Tuple = [0, 0, 0, 0]

export type MarkerUserData = BaseUserData & {
  topic: string
  /** marker used for rendering (may have color override applied) */
  marker: Marker
  /** original marker received from topic, used for inspection */
  originalMarker: Marker
  /** nanoseconds until this marker expires, or undefined for no expiry */
  expiresIn: bigint | undefined
}

export function getMarkerId(topic: string, ns: string, id: number): string {
  return `${topic}:${ns ? ns + ':' : ''}${id}`.replace(/\s/g, '_')
}

function toNanoSec(time: { sec: number; nsec: number }): bigint {
  return BigInt(time.sec) * 1_000_000_000n + BigInt(time.nsec)
}

export class RenderableMarker extends Renderable<MarkerUserData> {
  public constructor(
    topic: string,
    marker: Marker,
    receiveTime: bigint | undefined,
    renderer: IRenderer
  ) {
    const name = getMarkerId(topic, marker.ns, marker.id)
    const hasLifetime = marker.lifetime.sec !== 0 || marker.lifetime.nsec !== 0

    super(name, renderer, {
      receiveTime: receiveTime ?? 0n,
      messageTime: toNanoSec(marker.header.stamp),
      frameId: renderer.normalizeFrameId(marker.header.frame_id),
      pose: marker.pose,
      settingsPath: ['topics', topic],
      settings: { visible: true },
      topic,
      marker,
      originalMarker: marker,
      expiresIn: hasLifetime ? toNanoSec(marker.lifetime) : undefined
    })
  }

  public override idFromMessage(): number | string | undefined {
    return this.userData.marker.id
  }

  public override selectedIdVariable(): string | undefined {
    const settings = this.getSettings()
    return settings?.selectedIdVariable ?? SELECTED_ID_VARIABLE
  }

  public getSettings(): LayerSettingsMarker | undefined {
    return this.renderer.config.topics[this.userData.topic] as LayerSettingsMarker | undefined
  }

  public override details(): Record<string, RosValue> {
    return this.userData.originalMarker as unknown as Record<string, RosValue>
  }

  public update(marker: Marker, receiveTime: bigint | undefined): void {
    const hasLifetime = marker.lifetime.sec !== 0 || marker.lifetime.nsec !== 0

    if (receiveTime != undefined) {
      this.userData.receiveTime = receiveTime
    }
    this.userData.messageTime = toNanoSec(marker.header.stamp)
    this.userData.frameId = this.renderer.normalizeFrameId(marker.header.frame_id)
    this.userData.pose = marker.pose
    this.userData.marker = this.#renderMarker(marker)
    this.userData.originalMarker = marker
    this.userData.expiresIn = hasLifetime ? toNanoSec(marker.lifetime) : undefined
  }

  /** Convert sRGB per-point colors to linear, with fallback to base marker color */
  protected _markerColorsToLinear(
    marker: Marker,
    pointsLength: number,
    callback: (color: THREE.Vector4Tuple, i: number) => void
  ): void {
    rgbToThreeColor(tempColor, marker.color)

    for (let i = 0; i < pointsLength; i++) {
      const srgb = marker.colors[i]
      if (srgb) {
        rgbToThreeColor(tempColor2, srgb)
        tempTuple4[0] = tempColor2.r
        tempTuple4[1] = tempColor2.g
        tempTuple4[2] = tempColor2.b
        tempTuple4[3] = srgb.a
      } else {
        tempTuple4[0] = tempColor.r
        tempTuple4[1] = tempColor.g
        tempTuple4[2] = tempColor.b
        tempTuple4[3] = marker.color.a
      }
      callback(tempTuple4, i)
    }
  }

  /** Apply topic-level color override if configured */
  #renderMarker(marker: Marker): Marker {
    const settings = this.renderer.config.topics[this.userData.topic] as
      | Partial<LayerSettingsMarker>
      | undefined
    const colorStr = settings?.color
    if (colorStr == undefined) return marker

    const color = stringToRgba(makeRgba(), colorStr)
    return { ...marker, color, colors: [] }
  }
}
