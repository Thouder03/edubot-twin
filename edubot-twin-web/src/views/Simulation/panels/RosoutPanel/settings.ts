import type { SettingsTreeAction, SettingsTreeNodes } from '../../types/settings'

export interface RosoutConfig {
  topic: string
  maxLogs: number
  minLevel: number
  autoScroll: boolean
}

export const DEFAULT_CONFIG: RosoutConfig = {
  topic: '/rosout',
  maxLogs: 500,
  minLevel: 1,
  autoScroll: true
}

export function buildNodes(config: RosoutConfig): SettingsTreeNodes {
  return {
    general: {
      label: '基础设置',
      fields: {
        topic: {
          label: '日志 Topic',
          input: 'string',
          value: config.topic,
          placeholder: '/rosout'
        },
        maxLogs: {
          label: '最大保留条数',
          input: 'number',
          value: config.maxLogs,
          min: 100,
          max: 2000,
          step: 100
        },
        minLevel: {
          label: '最小日志级别',
          input: 'select',
          value: config.minLevel,
          options: [
            { label: 'DEBUG', value: 1 },
            { label: 'INFO', value: 2 },
            { label: 'WARN', value: 4 },
            { label: 'ERROR', value: 8 },
            { label: 'FATAL', value: 16 }
          ]
        },
        autoScroll: {
          label: '自动滚动',
          input: 'boolean',
          value: config.autoScroll
        }
      }
    }
  }
}

export function applyAction(config: RosoutConfig, action: SettingsTreeAction): RosoutConfig {
  if (action.action !== 'update') return config
  const next = { ...config }
  const field = action.payload.path[action.payload.path.length - 1] as keyof RosoutConfig
  if (field in next) {
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    ;(next as any)[field] = action.payload.value
  }
  return next
}
