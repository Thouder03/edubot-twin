/**
 * GzWebViewer 设置定义
 */
import type { SettingsTreeNodes, SettingsTreeAction } from '../../types/settings'

/** 默认配置 */
export interface GzWebViewerConfig {
  gzwebUrl: string
  autoConnect: boolean
  showOriginAxes: boolean
  showGrid: boolean
  showCollisions: boolean
  showOrbitIndicator: boolean
}

export const defaultConfig: GzWebViewerConfig = {
  gzwebUrl: 'http://192.168.40.129:8080',
  autoConnect: true,
  showOriginAxes: false,
  showGrid: true,
  showCollisions: false,
  showOrbitIndicator: false
}

/** 根据当前配置构建设置树 */
export function buildSettingsTree(config: GzWebViewerConfig): SettingsTreeNodes {
  return {
    connection: {
      label: '连接设置',
      fields: {
        gzwebUrl: {
          label: 'GzWeb URL',
          input: 'string',
          value: config.gzwebUrl,
          placeholder: 'http://host:port'
        },
        autoConnect: {
          label: '自动连接',
          input: 'boolean',
          value: config.autoConnect
        }
      }
    },
    display: {
      label: '显示设置',
      fields: {
        showOriginAxes: {
          label: '显示坐标系',
          input: 'boolean',
          value: config.showOriginAxes
        },
        showGrid: {
          label: '显示地面网格',
          input: 'boolean',
          value: config.showGrid
        },
        showCollisions: {
          label: '显示碰撞体',
          input: 'boolean',
          value: config.showCollisions
        },
        showOrbitIndicator: {
          label: '显示轨道指示器',
          input: 'boolean',
          value: config.showOrbitIndicator
        }
      }
    }
  }
}

/** 处理设置变更 */
export function createActionHandler(
  config: GzWebViewerConfig,
  saveConfig: (newConfig: GzWebViewerConfig) => void
) {
  return (action: SettingsTreeAction) => {
    if (action.action !== 'update') return
    const { path, value } = action.payload
    const fieldKey = path[1] as keyof GzWebViewerConfig
    if (fieldKey in config) {
      saveConfig({ ...config, [fieldKey]: value })
    }
  }
}
