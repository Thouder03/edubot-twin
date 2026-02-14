/**
 * 设置树类型定义
 * 仿 lichtblick/Foxglove 的 SettingsTree 模式
 *
 * 每个面板通过 buildSettingsTree(config) 生成设置节点描述,
 * PanelSettings 组件根据描述动态渲染 Element Plus 表单控件
 */

/** 单个字段 */
export interface SettingsTreeField {
  label: string
  input: 'string' | 'number' | 'boolean' | 'select' | 'rgb' | 'vec3'
  value: any
  placeholder?: string
  help?: string
  disabled?: boolean
  error?: string
  /** input='select' 时使用 */
  options?: Array<{ label: string; value: any }>
  /** input='number' 时使用 */
  min?: number
  max?: number
  step?: number
  /** input='vec3' 时使用 */
  labels?: string[]
  precision?: number
}

/** 一组字段 */
export interface SettingsTreeNode {
  label?: string
  fields: Record<string, SettingsTreeField>
  /** 是否可折叠（默认 true） */
  collapsible?: boolean
  /** 默认展开状态（默认 false） */
  defaultExpanded?: boolean
  /** 分组图标 */
  icon?: string
}

/** 完整设置节点映射 */
export type SettingsTreeNodes = Record<string, SettingsTreeNode | undefined>

/** 设置变更动作 */
export interface SettingsTreeAction {
  action: 'update'
  payload: {
    /** 路径: [groupKey, fieldKey] */
    path: string[]
    value: any
    input: string
  }
}

/** 完整设置树: 节点描述 + 动作处理器 */
export interface SettingsTree {
  actionHandler: (action: SettingsTreeAction) => void
  nodes: SettingsTreeNodes
}
