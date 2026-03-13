// SPDX-FileCopyrightText: Copyright (C) 2023-2025 Bayerische Motoren Werke Aktiengesellschaft (BMW AG)<lichtblick@bmwgroup.com>
// SPDX-License-Identifier: MPL-2.0
//
// Ported from lichtblick/renderables/pointClouds/fieldReaders.ts
// Adaptations:
//  - Removed @foxglove/schemas NumericType (ROS1-only, PointFieldType only)

import { PointField, PointFieldType } from '../../core/ros'

export type FieldReader = (view: DataView, pointOffset: number) => number

function int8Reader(fieldOffset: number, normalize: boolean): FieldReader {
  return (view: DataView, pointOffset: number) => {
    const value = view.getInt8(pointOffset + fieldOffset)
    if (normalize) {
      return Math.max(value / 0x7f, -1)
    }
    return value
  }
}

function uint8Reader(fieldOffset: number, normalize: boolean): FieldReader {
  return (view: DataView, pointOffset: number) => {
    const value = view.getUint8(pointOffset + fieldOffset)
    if (normalize) {
      return value / 0xff
    }
    return value
  }
}

function int16Reader(fieldOffset: number, normalize: boolean): FieldReader {
  return (view: DataView, pointOffset: number) => {
    const value = view.getInt16(pointOffset + fieldOffset, true)
    if (normalize) {
      return Math.max(value / 0x7fff, -1)
    }
    return value
  }
}

function uint16Reader(fieldOffset: number, normalize: boolean): FieldReader {
  return (view: DataView, pointOffset: number) => {
    const value = view.getUint16(pointOffset + fieldOffset, true)
    if (normalize) {
      return value / 0xffff
    }
    return value
  }
}

function int32Reader(fieldOffset: number, normalize: boolean): FieldReader {
  return (view: DataView, pointOffset: number) => {
    const value = view.getInt32(pointOffset + fieldOffset, true)
    if (normalize) {
      return Math.max(value / 0x7fffffff, -1)
    }
    return value
  }
}

function uint32Reader(fieldOffset: number, normalize: boolean): FieldReader {
  return (view: DataView, pointOffset: number) => {
    const value = view.getUint32(pointOffset + fieldOffset, true)
    if (normalize) {
      return value / 0xffffffff
    }
    return value
  }
}

function float32Reader(fieldOffset: number): FieldReader {
  return (view: DataView, pointOffset: number) => view.getFloat32(pointOffset + fieldOffset, true)
}

function float64Reader(fieldOffset: number): FieldReader {
  return (view: DataView, pointOffset: number) => view.getFloat64(pointOffset + fieldOffset, true)
}

export function isSupportedField(field: PointField): boolean {
  // Only PointFields with count === 1 are supported
  if ('count' in field && (field as any).count !== 1) {
    return false
  }
  return true
}

export function getReader(
  field: PointField,
  stride: number,
  /** @see https://www.khronos.org/opengl/wiki/Normalized_Integer */
  normalize = false,
  forceType?: PointFieldType
): FieldReader | undefined {
  if (!isSupportedField(field)) {
    return undefined
  }

  const type = forceType ?? field.datatype
  switch (type) {
    case PointFieldType.INT8:
      return field.offset + 1 <= stride ? int8Reader(field.offset, normalize) : undefined
    case PointFieldType.UINT8:
      return field.offset + 1 <= stride ? uint8Reader(field.offset, normalize) : undefined
    case PointFieldType.INT16:
      return field.offset + 2 <= stride ? int16Reader(field.offset, normalize) : undefined
    case PointFieldType.UINT16:
      return field.offset + 2 <= stride ? uint16Reader(field.offset, normalize) : undefined
    case PointFieldType.INT32:
      return field.offset + 4 <= stride ? int32Reader(field.offset, normalize) : undefined
    case PointFieldType.UINT32:
      return field.offset + 4 <= stride ? uint32Reader(field.offset, normalize) : undefined
    case PointFieldType.FLOAT32:
      return field.offset + 4 <= stride ? float32Reader(field.offset) : undefined
    case PointFieldType.FLOAT64:
      return field.offset + 8 <= stride ? float64Reader(field.offset) : undefined
    default:
      return undefined
  }
}
