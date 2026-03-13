// SPDX-FileCopyrightText: Copyright (C) 2023-2025 Bayerische Motoren Werke Aktiengesellschaft (BMW AG)<lichtblick@bmwgroup.com>
// SPDX-License-Identifier: MPL-2.0

// This Source Code Form is subject to the terms of the Mozilla Public
// License, v2.0. If a copy of the MPL was not distributed with this
// file, You can obtain one at http://mozilla.org/MPL/2.0/
//
// Ported from lichtblick/renderables/colorMode.ts
// Adaptations: removed i18next dependency (use Chinese labels), adapted imports.

import * as THREE from 'three'

import type { SettingsTreeFields, SettingsTreeNode } from './lichtblick-shim'
import { rgbaGradient, rgbaToLinear, SRGBToLinear, stringToRgba } from './color'
import { clamp } from './math'
import type { ColorRGBA } from './ros'
import { BaseSettings } from './settings'

export type ColorConverter = (output: ColorRGBA, colorValue: number) => void

const tempColor1 = { r: 0, g: 0, b: 0, a: 0 }
const tempColor2 = { r: 0, g: 0, b: 0, a: 0 }
export const NEEDS_MIN_MAX = ['gradient', 'colormap']

export const colorFieldComputedPrefix = '_auto_'

export interface ColorModeSettings {
  colorMode: 'flat' | 'gradient' | 'colormap' | 'rgb' | 'rgba' | 'rgba-fields'
  flatColor: string
  colorField?: string
  gradient: [string, string]
  colorMap: 'turbo' | 'rainbow'
  explicitAlpha: number
  minValue?: number
  maxValue?: number
}

export function getColorConverter<
  Settings extends ColorModeSettings & {
    readonly colorMode: Exclude<ColorModeSettings['colorMode'], 'rgba-fields'>
  }
>(settings: Settings, minValue: number, maxValue: number): ColorConverter {
  switch (settings.colorMode) {
    case 'flat': {
      const flatColor = stringToRgba(tempColor1, settings.flatColor)
      rgbaToLinear(flatColor, flatColor)
      return (output: ColorRGBA, _colorValue: number) => {
        output.r = flatColor.r
        output.g = flatColor.g
        output.b = flatColor.b
        output.a = flatColor.a
      }
    }
    case 'gradient': {
      const valueDelta = Math.max(maxValue - minValue, Number.EPSILON)
      const minColor = stringToRgba(tempColor1, settings.gradient[0])
      const maxColor = stringToRgba(tempColor2, settings.gradient[1])
      rgbaToLinear(minColor, minColor)
      rgbaToLinear(maxColor, maxColor)
      return (output: ColorRGBA, colorValue: number) => {
        const frac = Math.max(0, Math.min((colorValue - minValue) / valueDelta, 1))
        rgbaGradient(output, minColor, maxColor, frac)
      }
    }
    case 'colormap': {
      const valueDelta = Math.max(maxValue - minValue, Number.EPSILON)
      switch (settings.colorMap) {
        case 'turbo':
          return (output: ColorRGBA, colorValue: number) => {
            const frac = Math.max(0, Math.min((colorValue - minValue) / valueDelta, 1))
            turboLinearCached(output, frac)
            output.a = settings.explicitAlpha
          }
        case 'rainbow':
          return (output: ColorRGBA, colorValue: number) => {
            const frac = Math.max(0, Math.min((colorValue - minValue) / valueDelta, 1))
            rainbowLinear(output, frac)
            output.a = settings.explicitAlpha
          }
      }
      throw new Error(`Unrecognized color map: ${settings.colorMap}`)
    }
    case 'rgb':
      return (output: ColorRGBA, colorValue: number) => {
        getColorBgra(output, colorValue)
        output.a = settings.explicitAlpha
      }
    case 'rgba':
      return getColorBgra
  }
}

// 0xaarrggbb — matches rviz behavior
function getColorBgra(output: ColorRGBA, colorValue: number): void {
  const num = colorValue >>> 0
  output.a = ((num & 0xff000000) >>> 24) / 255
  output.r = ((num & 0x00ff0000) >>> 16) / 255
  output.g = ((num & 0x0000ff00) >>> 8) / 255
  output.b = ((num & 0x000000ff) >>> 0) / 255
}

// taken from http://docs.ros.org/jade/api/rviz/html/c++/point__cloud__transformers_8cpp_source.html line 47
function rainbowLinear(output: ColorRGBA, pct: number): void {
  const h = (1.0 - clamp(pct, 0, 1)) * 5.0 + 1.0
  const i = Math.floor(h)
  let f = h % 1
  if (i % 2 < 1) {
    f = 1.0 - f
  }
  const n = SRGBToLinear(1.0 - f)
  if (i <= 1) {
    output.r = n
    output.g = 0
    output.b = 1
  } else if (i === 2) {
    output.r = 0
    output.g = n
    output.b = 1
  } else if (i === 3) {
    output.r = 0
    output.g = 1
    output.b = n
  } else if (i === 4) {
    output.r = n
    output.g = 1
    output.b = 0
  } else {
    output.r = 1
    output.g = n
    output.b = 0
  }
  output.a = 1
}

// Turbo colormap — adapted from https://gist.github.com/mikhailov-work/0d177465a8151eb6ede1768d51d476c7
const kRedVec4 = new THREE.Vector4(0.13572138, 4.6153926, -42.66032258, 132.13108234)
const kGreenVec4 = new THREE.Vector4(0.09140261, 2.19418839, 4.84296658, -14.18503333)
const kBlueVec4 = new THREE.Vector4(0.1066733, 12.64194608, -60.58204836, 110.36276771)
const kRedVec2 = new THREE.Vector2(-152.94239396, 59.28637943)
const kGreenVec2 = new THREE.Vector2(4.27729857, 2.82956604)
const kBlueVec2 = new THREE.Vector2(-89.90310912, 27.34824973)
const _v4 = new THREE.Vector4()
const _v2 = new THREE.Vector2()

function turboLinear(output: ColorRGBA, pct: number): void {
  const x = clamp(pct, 0.0, 1.0) * 0.99 + 0.01
  _v4.set(1, x, x * x, x * x * x)
  _v2.set(_v4.z, _v4.w)
  _v2.multiplyScalar(_v4.z)
  output.r = SRGBToLinear(clamp(_v4.dot(kRedVec4) + _v2.dot(kRedVec2), 0, 1))
  output.g = SRGBToLinear(clamp(_v4.dot(kGreenVec4) + _v2.dot(kGreenVec2), 0, 1))
  output.b = SRGBToLinear(clamp(_v4.dot(kBlueVec4) + _v2.dot(kBlueVec2), 0, 1))
  output.a = 1
}

// One-time lookup table for turbo (65535 entries)
let TurboLookup: Float32Array | undefined
const TURBO_LOOKUP_SIZE = 65535

function turboLinearCached(output: ColorRGBA, pct: number): void {
  if (!TurboLookup) {
    TurboLookup = new Float32Array(TURBO_LOOKUP_SIZE * 3)
    const tempColor = { r: 0, g: 0, b: 0, a: 0 }
    for (let i = 0; i < TURBO_LOOKUP_SIZE; i++) {
      turboLinear(tempColor, i / (TURBO_LOOKUP_SIZE - 1))
      const offset = i * 3
      TurboLookup[offset + 0] = tempColor.r
      TurboLookup[offset + 1] = tempColor.g
      TurboLookup[offset + 2] = tempColor.b
    }
  }

  const offset = Math.trunc(pct * (TURBO_LOOKUP_SIZE - 1)) * 3
  output.r = TurboLookup[offset + 0]!
  output.g = TurboLookup[offset + 1]!
  output.b = TurboLookup[offset + 2]!
  output.a = 1
}

export const RGBA_PACKED_FIELDS = new Set<string>(['rgb', 'rgba'])
export const INTENSITY_FIELDS = new Set<string>(['intensity', 'i'])

/** 根据消息字段自动选择最优颜色模式 */
export function autoSelectColorSettings<Settings extends ColorModeSettings>(
  output: Settings,
  fields: string[],
  {
    supportsPackedRgbModes,
    supportsRgbaFieldsMode
  }: { supportsPackedRgbModes: boolean; supportsRgbaFieldsMode?: boolean }
): void {
  const bestField = bestColorByField(fields, { supportsPackedRgbModes })
  if (!bestField) return

  output.colorField = bestField
  switch (bestField.toLowerCase()) {
    case 'rgb':
      output.colorMode = 'rgb'
      break
    case 'rgba':
      output.colorMode = 'rgba'
      break
    default:
      output.colorMode = 'colormap'
      output.colorMap = 'turbo'
      break
  }

  if (supportsRgbaFieldsMode === true && hasSeparateRgbaFields(fields)) {
    output.colorMode = 'rgba-fields'
  }
}

function bestColorByField(
  fields: string[],
  { supportsPackedRgbModes }: { supportsPackedRgbModes: boolean }
): string | undefined {
  if (supportsPackedRgbModes) {
    for (const field of fields) {
      if (RGBA_PACKED_FIELDS.has(field.toLowerCase())) return field
    }
  }
  for (const field of fields) {
    if (INTENSITY_FIELDS.has(field.toLowerCase())) return field
  }
  return fields.find((field) => field === 'z') ?? fields[0]
}

function hasSeparateRgbaFields(fields: string[]): boolean {
  let r = false,
    g = false,
    b = false,
    a = false
  for (const field of fields) {
    switch (field) {
      case 'red':
        r = true
        break
      case 'green':
        g = true
        break
      case 'blue':
        b = true
        break
      case 'alpha':
        a = true
        break
    }
  }
  return r && g && b && a
}

/**
 * 生成颜色模式相关的 Settings Tree 字段
 * 注意：使用中文 label，去掉 i18next 依赖
 */
export function colorModeSettingsFields<Settings extends ColorModeSettings & BaseSettings>({
  msgFields,
  config,
  defaults,
  modifiers: { supportsPackedRgbModes, supportsRgbaFieldsMode, hideFlatColor, hideExplicitAlpha }
}: {
  msgFields?: string[]
  config: Partial<Settings>
  defaults: Pick<Settings, 'gradient'>
  modifiers: {
    supportsPackedRgbModes: boolean
    supportsRgbaFieldsMode: boolean
    hideFlatColor?: boolean
    hideExplicitAlpha?: boolean
  }
}): NonNullable<SettingsTreeNode['fields']> {
  const colorMode = config.colorMode ?? (hideFlatColor === true ? 'gradient' : 'flat')
  const flatColor = config.flatColor ?? '#ffffff'
  const gradient = config.gradient
  const colorMap = config.colorMap ?? 'turbo'
  const explicitAlpha = config.explicitAlpha ?? 1
  const minValue = config.minValue
  const maxValue = config.maxValue

  const fields: SettingsTreeFields = {}

  const colorModeOptions: { label: string; value: string }[] = [
    { label: '颜色映射', value: 'colormap' },
    { label: '渐变', value: 'gradient' }
  ]

  if (hideFlatColor !== true) {
    colorModeOptions.push({ label: '纯色', value: 'flat' })
  }
  if (msgFields && msgFields.length > 0) {
    if (supportsPackedRgbModes) {
      colorModeOptions.push(
        { label: 'BGR 打包', value: 'rgb' },
        { label: 'BGRA 打包', value: 'rgba' }
      )
    }
    if (supportsRgbaFieldsMode && hasSeparateRgbaFields(msgFields)) {
      colorModeOptions.push({ label: 'RGBA 分离字段', value: 'rgba-fields' })
    }
  }

  fields['colorMode'] = {
    label: '颜色模式',
    input: 'select' as const,
    value: colorMode,
    options: colorModeOptions
  }

  if (colorMode === 'flat') {
    fields['flatColor'] = { label: '纯色', input: 'rgba' as const, value: flatColor }
  } else if (colorMode !== 'rgba-fields') {
    if (msgFields) {
      const colorFieldOptions = msgFields.map((field) => ({ label: field, value: field }))
      colorFieldOptions.push({
        label: 'distance(auto)',
        value: colorFieldComputedPrefix + 'distance'
      })

      const colorField =
        config.colorField ?? bestColorByField(msgFields, { supportsPackedRgbModes })
      fields['colorField'] = {
        label: '着色字段',
        input: 'select' as const,
        options: colorFieldOptions,
        value: colorField
      }
    }

    switch (colorMode) {
      case 'gradient':
        fields['gradient'] = {
          label: '渐变',
          input: 'gradient' as const,
          value: gradient ?? defaults.gradient
        }
        break
      case 'colormap':
        fields['colorMap'] = {
          label: '调色板',
          input: 'select' as const,
          options: [
            { label: 'Turbo', value: 'turbo' },
            { label: 'Rainbow', value: 'rainbow' }
          ],
          value: colorMap
        }
        break
      default:
        break
    }

    if (hideExplicitAlpha !== true && (colorMode === 'colormap' || colorMode === 'rgb')) {
      fields['explicitAlpha'] = {
        label: '不透明度',
        input: 'number' as const,
        step: 0.1,
        placeholder: '1',
        precision: 3,
        min: 0,
        max: 1,
        value: explicitAlpha
      }
    }

    if (NEEDS_MIN_MAX.includes(colorMode)) {
      fields['minValue'] = {
        label: '最小值',
        input: 'number' as const,
        placeholder: '自动',
        precision: 4,
        value: minValue
      }
      fields['maxValue'] = {
        label: '最大值',
        input: 'number' as const,
        placeholder: '自动',
        precision: 4,
        value: maxValue
      }
    }
  }

  return fields
}

const _tempColor = { r: 0, g: 0, b: 0, a: 0 }
export function colorHasTransparency<Settings extends ColorModeSettings>(
  settings: Settings
): boolean {
  switch (settings.colorMode) {
    case 'flat':
      return stringToRgba(_tempColor, settings.flatColor).a < 1.0
    case 'gradient':
      return (
        stringToRgba(_tempColor, settings.gradient[0]).a < 1.0 ||
        stringToRgba(_tempColor, settings.gradient[1]).a < 1.0
      )
    case 'colormap':
    case 'rgb':
      return settings.explicitAlpha < 1.0
    case 'rgba':
    case 'rgba-fields':
      return true
  }
}

// Fragment shader chunk — sRGB 到 linear RGB 转换（供顶点着色器中使用）
export const FS_SRGB_TO_LINEAR = /* glsl */ `
vec3 sRGBToLinear(in vec3 value) {
  return vec3(mix(
    pow(value.rgb * 0.9478672986 + vec3(0.0521327014), vec3(2.4)),
    value.rgb * 0.0773993808,
    vec3(lessThanEqual(value.rgb, vec3(0.04045)))
  ));
}

vec4 sRGBToLinear(in vec4 value) {
  return vec4(sRGBToLinear(value.rgb), value.a);
}
`
