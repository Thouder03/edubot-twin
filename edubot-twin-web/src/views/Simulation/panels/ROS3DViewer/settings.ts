/**
 * ROS3DViewer 设置定义
 *
 * 导出 defaultConfig 和 buildSettingsTree
 * 每当需要扩展设置时，只需修改此文件
 */
import type { SettingsTreeNodes, SettingsTreeAction } from '../../types/settings'

/** 默认配置 */
export interface ROS3DViewerConfig {
  rosUrl: string
  fixedFrame: string
  showGrid: boolean
  showAxes: boolean
  backgroundColor: string
}

export const defaultConfig: ROS3DViewerConfig = {
  rosUrl: 'ws://localhost:9090',
  fixedFrame: 'map',
  showGrid: true,
  showAxes: true,
  backgroundColor: '#1e1e2e'
}

/** 根据当前配置构建设置树 */
export function buildSettingsTree(config: ROS3DViewerConfig): SettingsTreeNodes {
  return {
    connection: {
      label: '连接设置',
      fields: {
        rosUrl: {
          label: 'ROS WebSocket URL',
          input: 'string',
          value: config.rosUrl,
          placeholder: 'ws://host:port'
        },
        fixedFrame: {
          label: 'Fixed Frame',
          input: 'string',
          value: config.fixedFrame,
          placeholder: 'map'
        }
      }
    },
    display: {
      label: '显示设置',
      fields: {
        showGrid: {
          label: '显示网格',
          input: 'boolean',
          value: config.showGrid
        },
        showAxes: {
          label: '显示坐标轴',
          input: 'boolean',
          value: config.showAxes
        },
        backgroundColor: {
          label: '背景色',
          input: 'rgb',
          value: config.backgroundColor
        }
      }
    }
  }
}

/** 处理设置变更 */
export function createActionHandler(
  config: ROS3DViewerConfig,
  saveConfig: (newConfig: ROS3DViewerConfig) => void
) {
  return (action: SettingsTreeAction) => {
    if (action.action !== 'update') return
    const { path, value } = action.payload
    // path = [groupKey, fieldKey]
    const fieldKey = path[1] as keyof ROS3DViewerConfig
    if (fieldKey in config) {
      saveConfig({ ...config, [fieldKey]: value })
    }
  }
}
