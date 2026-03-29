import { SettingsTreeNodes, SettingsTreeAction } from '@/views/Simulation/types/settings'
import type { WorkspaceSettings } from '@/composables/useWorkspaceSettings'

export function buildSettingsTree(config: WorkspaceSettings): SettingsTreeNodes {
  return {
    editor: {
      label: '编辑器设置',
      defaultExpanded: true,
      fields: {
        fontSize: {
          label: '字体大小',
          input: 'number',
          value: config.fontSize,
          min: 10,
          max: 20,
          step: 1
        },
        theme: {
          label: '主题',
          input: 'select',
          value: config.theme,
          options: [
            { label: '深色 (vs-dark)', value: 'vs-dark' },
            { label: '浅色 (vs)', value: 'vs' },
            { label: '高对比 (hc-black)', value: 'hc-black' }
          ]
        },
        wordWrap: {
          label: '自动换行',
          input: 'select',
          value: config.wordWrap,
          options: [
            { label: '开', value: 'on' },
            { label: '关', value: 'off' }
          ]
        },
        minimap: {
          label: '显示小地图',
          input: 'boolean',
          value: config.minimap
        },
        tabSize: {
          label: 'Tab 大小',
          input: 'select',
          value: config.tabSize,
          options: [
            { label: '2 空格', value: 2 },
            { label: '4 空格', value: 4 }
          ]
        }
      },
      actions: [
        {
          type: 'action',
          id: 'reset',
          label: '恢复默认设置',
          icon: 'vi-ep:refresh'
        }
      ]
    }
  }
}

export function createActionHandler(
  saveConfig: (newConfig: Partial<WorkspaceSettings>) => void,
  resetSettings: () => void
) {
  return (action: SettingsTreeAction) => {
    if (action.action === 'update') {
      const { path, value } = action.payload
      const fieldKey = path[1] as keyof WorkspaceSettings
      if (fieldKey) {
        saveConfig({ [fieldKey]: value })
      }
    } else if (action.action === 'perform-node-action') {
      if (action.payload.id === 'reset') {
        resetSettings()
      }
    }
  }
}
