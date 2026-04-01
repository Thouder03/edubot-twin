import type { LayoutConfig } from 'golden-layout'

/**
 * 预设布局配置
 * componentType 必须与 GLayout.vue 中 componentMap 的 key 一致
 */

// 默认左右等分
export const defaultLayout: LayoutConfig = {
  root: {
    type: 'row',
    content: [
      {
        type: 'component',
        componentType: 'ROS3DViewer',
        title: 'ROS 3D 视图'
      },
      {
        type: 'component',
        componentType: 'GzWebViewer',
        title: 'Gazebo 仿真'
      }
    ]
  }
}

// 左宽右窄 (67:33)
export const leftWideLayout: LayoutConfig = {
  root: {
    type: 'row',
    content: [
      {
        type: 'component',
        componentType: 'ROS3DViewer',
        title: 'ROS 3D 视图',
        size: '67%'
      },
      {
        type: 'component',
        componentType: 'GzWebViewer',
        title: 'Gazebo 仿真',
        size: '33%'
      }
    ]
  }
}

// 右宽左窄 (33:67)
export const rightWideLayout: LayoutConfig = {
  root: {
    type: 'row',
    content: [
      {
        type: 'component',
        componentType: 'ROS3DViewer',
        title: 'ROS 3D 视图',
        size: '33%'
      },
      {
        type: 'component',
        componentType: 'GzWebViewer',
        title: 'Gazebo 仿真',
        size: '67%'
      }
    ]
  }
}

// 三栏布局（ROS 3D 左侧 + 右侧上下分 GzWeb + 预留）
export const threeColumnLayout: LayoutConfig = {
  root: {
    type: 'row',
    content: [
      {
        type: 'component',
        componentType: 'ROS3DViewer',
        title: 'ROS 3D 视图',
        size: '50%'
      },
      {
        type: 'column',
        size: '50%',
        content: [
          {
            type: 'component',
            componentType: 'GzWebViewer',
            title: 'Gazebo 仿真'
          },
          {
            type: 'component',
            componentType: 'GzWebViewer',
            title: 'Gazebo 仿真 2'
          }
        ]
      }
    ]
  }
}

// 嵌套布局演示（成组缩放）
// [ A ] [ B C ] -> 拖动 A|BC 分割线时，B 和 C 等比例缩放
export const nestedLayout: LayoutConfig = {
  root: {
    type: 'row',
    content: [
      {
        type: 'component',
        componentType: 'ROS3DViewer',
        title: 'ROS 3D 视图 (A)',
        size: '50%'
      },
      {
        type: 'row', // B 和 C 被包裹在一个 Row 中
        size: '50%',
        content: [
          {
            type: 'component',
            componentType: 'GzWebViewer',
            title: 'Gazebo (B)',
            size: '50%'
          },
          {
            type: 'component',
            componentType: 'GzWebViewer',
            title: 'Gazebo (C)',
            size: '50%'
          }
        ]
      }
    ]
  }
}

// 四面板全功能布局（ROS 3D + GzWeb + 键盘控制 + 终端）
export const fullWorkbenchLayout: LayoutConfig = {
  root: {
    type: 'row',
    content: [
      {
        type: 'column',
        size: '50%',
        content: [
          {
            type: 'component',
            componentType: 'ROS3DViewer',
            title: 'ROS 3D 视图'
          },
          {
            type: 'component',
            componentType: 'KeyboardControl',
            title: '键盘控制',
            size: '30%'
          }
        ]
      },
      {
        type: 'column',
        size: '50%',
        content: [
          {
            type: 'component',
            componentType: 'GzWebViewer',
            title: 'Gazebo 仿真'
          },
          {
            type: 'component',
            componentType: 'ContainerTerminal',
            title: '容器终端',
            size: '30%'
          }
        ]
      }
    ]
  }
}

// 所有预设布局
export const layoutPresets = [
  { key: 'default', label: '左右等分', config: defaultLayout },
  { key: 'leftWide', label: '左侧宽', config: leftWideLayout },
  { key: 'rightWide', label: '右侧宽', config: rightWideLayout },
  { key: 'threeColumn', label: '三栏布局', config: threeColumnLayout },
  { key: 'nested', label: '成组缩放演示', config: nestedLayout },
  { key: 'fullWorkbench', label: '全功能工作台', config: fullWorkbenchLayout }
] as const

// 可动态添加的面板类型
export const availablePanels = [
  { type: 'ROS3DViewer', label: 'ROS 3D 视图' },
  { type: 'GzWebViewer', label: 'Gazebo 仿真' },
  { type: 'KeyboardControl', label: '键盘控制' },
  { type: 'ContainerTerminal', label: '容器终端' },
  { type: 'WorkspacePanel', label: '文件管理 / 代码编辑' },
  { type: 'RosoutPanel', label: 'ROS 日志' },
  { type: 'CameraPanel', label: '摄像头监控' }
] as const
