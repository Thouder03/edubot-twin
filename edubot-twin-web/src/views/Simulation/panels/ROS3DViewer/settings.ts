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
  autoConnect: boolean
  showGrid: boolean
  showAxes: boolean
  backgroundColor: string
  gridSize: number
  gridDivisions: number
}

export const defaultConfig: ROS3DViewerConfig = {
  rosUrl: 'ws://localhost:9090',
  fixedFrame: 'map',
  autoConnect: false,
  showGrid: true,
  showAxes: true,
  backgroundColor: '#1e1e2e',
  gridSize: 20,
  gridDivisions: 20
}

/** 根据当前配置构建设置树 */
export function buildSettingsTree(
  config: ROS3DViewerConfig,
  availableFrames?: string[]
): SettingsTreeNodes {
  // fixedFrame 选项：从 TF 帧列表动态生成
  const frameOptions =
    availableFrames && availableFrames.length > 0
      ? availableFrames.map((f) => ({ label: f, value: f }))
      : [
          { label: 'map', value: 'map' },
          { label: 'odom', value: 'odom' },
          { label: 'base_link', value: 'base_link' }
        ]

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
          input: 'select',
          value: config.fixedFrame,
          options: frameOptions
        },
        autoConnect: {
          label: '自动连接',
          input: 'boolean',
          value: config.autoConnect,
          help: '面板加载后自动连接 ROS'
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
        },
        gridSize: {
          label: '网格大小',
          input: 'number',
          value: config.gridSize,
          min: 1,
          max: 100,
          step: 1
        },
        gridDivisions: {
          label: '网格分段',
          input: 'number',
          value: config.gridDivisions,
          min: 1,
          max: 100,
          step: 1
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
