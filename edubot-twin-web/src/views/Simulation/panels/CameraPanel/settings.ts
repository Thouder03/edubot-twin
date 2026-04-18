import type { SettingsTreeAction, SettingsTreeNodes } from '../../types/settings'

export interface CameraConfig {
  topic: string
  throttleMs: number
  staleTimeoutMs: number
}

export const DEFAULT_CONFIG: CameraConfig = {
  topic: '/image_raw/compressed',
  throttleMs: 33,
  staleTimeoutMs: 1500
}

export function buildNodes(config: CameraConfig): SettingsTreeNodes {
  return {
    general: {
      label: '基础设置',
      fields: {
        topic: {
          label: '图像 Topic',
          input: 'string',
          value: config.topic,
          placeholder: '/image_raw/compressed'
        }
      }
    },
    performance: {
      label: '性能参数',
      fields: {
        throttleMs: {
          label: '最小帧间隔 (ms)',
          input: 'number',
          value: config.throttleMs,
          min: 16,
          max: 200,
          step: 1
        },
        staleTimeoutMs: {
          label: '无帧归零阈值 (ms)',
          input: 'number',
          value: config.staleTimeoutMs,
          min: 500,
          max: 5000,
          step: 100
        }
      }
    }
  }
}

export function applyAction(config: CameraConfig, action: SettingsTreeAction): CameraConfig {
  if (action.action !== 'update') return config
  const next = { ...config }
  const field = action.payload.path[action.payload.path.length - 1] as keyof CameraConfig
  if (field in next) {
    ;(next as any)[field] = action.payload.value
  }
  return next
}
