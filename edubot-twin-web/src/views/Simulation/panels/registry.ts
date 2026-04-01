import { markRaw, type Component as VueComponent } from 'vue'

import ROS3DViewer from './ROS3DViewer/index.vue'
import GzWebViewer from './GzWebViewer/index.vue'
import KeyboardControl from './KeyboardControl/index.vue'
import ContainerTerminal from './ContainerTerminal/index.vue'
import WorkspacePanel from './WorkspacePanel/index.vue'
import RosoutPanel from './RosoutPanel/index.vue'
import CameraPanel from './CameraPanel/index.vue'

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
  },
  KeyboardControl: {
    component: markRaw(KeyboardControl),
    label: '键盘控制'
  },
  ContainerTerminal: {
    component: markRaw(ContainerTerminal),
    label: '容器终端'
  },
  WorkspacePanel: {
    component: markRaw(WorkspacePanel),
    label: '文件管理 / 代码编辑'
  },
  RosoutPanel: {
    component: markRaw(RosoutPanel),
    label: 'ROS 日志'
  },
  CameraPanel: {
    component: markRaw(CameraPanel),
    label: '摄像头监控'
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
