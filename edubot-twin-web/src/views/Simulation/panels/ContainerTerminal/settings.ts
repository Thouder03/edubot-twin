/**
 * ContainerTerminal 面板设置
 */
import type { SettingsTreeNodes, SettingsTreeAction } from '../../types/settings'

export interface ContainerTerminalConfig {
  fontSize: number
  theme: 'dark' | 'light'
}

export const DEFAULT_CONFIG: ContainerTerminalConfig = {
  fontSize: 14,
  theme: 'dark'
}

export function buildNodes(config: ContainerTerminalConfig): SettingsTreeNodes {
  return {
    appearance: {
      label: '外观',
      fields: {
        fontSize: {
          label: '字体大小 (px)',
          input: 'number',
          value: config.fontSize,
          min: 10,
          max: 24,
          step: 1
        },
        theme: {
          label: '主题',
          input: 'select',
          value: config.theme,
          options: [
            { label: '深色', value: 'dark' },
            { label: '浅色', value: 'light' }
          ]
        }
      }
    }
  }
}

export function applyAction(
  config: ContainerTerminalConfig,
  action: SettingsTreeAction
): ContainerTerminalConfig {
  if (action.action !== 'update') return config
  const next = { ...config }
  const field = action.payload.path[
    action.payload.path.length - 1
  ] as keyof ContainerTerminalConfig
  if (field in next) {
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    ;(next as any)[field] = action.payload.value
  }
  return next
}
