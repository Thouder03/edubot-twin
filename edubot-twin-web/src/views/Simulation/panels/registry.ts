/**
 * 面板注册表
 *
 * 统一管理所有面板组件和设置构建器。
 * 扩展新面板只需:
 * 1. 创建 panels/XxxPanel/index.vue + settings.ts
 * 2. 在此文件 import 并注册
 */
import { markRaw, type Component as VueComponent } from 'vue'

import ROS3DViewer from './ROS3DViewer/index.vue'
import GzWebViewer from './GzWebViewer/index.vue'

export interface PanelRegistryEntry {
  /** Vue 组件 */
  component: VueComponent
  /** 面板中文标签 */
  label: string
}

/** 面板注册表: key = componentType (与 GL LayoutConfig 中的 componentType 一致) */
export const panelRegistry: Record<string, PanelRegistryEntry> = {
  ROS3DViewer: {
    component: markRaw(ROS3DViewer),
    label: 'ROS 3D 视图'
  },
  GzWebViewer: {
    component: markRaw(GzWebViewer),
    label: 'Gazebo 仿真'
  }
}

/**
 * 构建 GL 用的 componentMap
 * PanelSettings 在 GLayout 中单独注册(因为它不是用户可添加的面板)
 */
export function buildComponentMap(): Record<string, VueComponent> {
  const map: Record<string, VueComponent> = {}
  for (const [key, entry] of Object.entries(panelRegistry)) {
    map[key] = entry.component
  }
  return map
}
