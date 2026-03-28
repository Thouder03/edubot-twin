/**
 * KeyboardControl 面板设置
 *
 * 配置项：线速度、角速度、发布 Topic
 */
import type { SettingsTreeNodes, SettingsTreeAction } from '../../types/settings'

export interface KeyboardControlConfig {
  linearSpeed: number
  angularSpeed: number
  cmdVelTopic: string
}

export const DEFAULT_CONFIG: KeyboardControlConfig = {
  linearSpeed: 0.5,
  angularSpeed: 0.5,
  cmdVelTopic: '/cmd_vel'
}

export function buildNodes(config: KeyboardControlConfig): SettingsTreeNodes {
  return {
    general: {
      label: '控制参数',
      fields: {
        linearSpeed: {
          label: '线速度 (m/s)',
          input: 'number',
          value: config.linearSpeed,
          min: 0.1,
          max: 3.0,
          step: 0.1
        },
        angularSpeed: {
          label: '角速度 (rad/s)',
          input: 'number',
          value: config.angularSpeed,
          min: 0.1,
          max: 3.0,
          step: 0.1
        },
        cmdVelTopic: {
          label: 'cmd_vel Topic',
          input: 'string',
          value: config.cmdVelTopic
        }
      }
    }
  }
}

export function applyAction(
  config: KeyboardControlConfig,
  action: SettingsTreeAction
): KeyboardControlConfig {
  if (action.action !== 'update') return config
  const next = { ...config }
  const field = action.payload.path[action.payload.path.length - 1] as keyof KeyboardControlConfig
  if (field in next) {
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    ;(next as any)[field] = action.payload.value
  }
  return next
}
