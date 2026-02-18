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
  input:
    | 'string'
    | 'number'
    | 'boolean'
    | 'select'
    | 'rgb'
    | 'rgba'
    | 'vec2'
    | 'vec3'
    | 'autocomplete'
  value: any
  placeholder?: string
  help?: string
  /** 是否禁用 */
  disabled?: boolean
  /** 是否只读（只展示，不可编辑） */
  readonly?: boolean
  error?: string
  /** input='select' | 'autocomplete' 时使用 */
  options?: Array<{ label: string; value: any }>
  /** input='number' 时使用 */
  min?: number
  max?: number
  step?: number
  /** input='vec2' | 'vec3' 时使用 */
  labels?: string[]
  precision?: number
}

/** 一组字段 */
export interface SettingsTreeNode {
  label?: string
  fields?: Record<string, SettingsTreeField>
  /** 是否可折叠（默认 true） */
  collapsible?: boolean
  /** 默认展开状态（默认 false） */
  defaultExpanded?: boolean
  /** 分组图标 */
  icon?: string
  /** 子节点（嵌套分组） */
  children?: SettingsTreeNodes
  /**
   * 节点可见性。undefined 表示不支持可见性切换；
   * true/false 表示当前显示/隐藏状态，悬浮时会显示眼睛图标。
   */
  visible?: boolean
  /** 节点错误信息 */
  error?: string
}

/** 完整设置节点映射 */
export type SettingsTreeNodes = Record<string, SettingsTreeNode | undefined>

/** 设置变更动作 */
export type SettingsTreeAction =
  | {
      action: 'update'
      payload: {
        /** 路径: [groupKey, fieldKey] */
        path: string[]
        value: any
        input: string
      }
    }
  | {
      /** 节点级别的自定义动作（如 show-all / hide-all） */
      action: 'perform-node-action'
      payload: {
        id: string
        path?: string[]
      }
    }

/** 完整设置树: 节点描述 + 动作处理器 */
export interface SettingsTree {
  actionHandler: (action: SettingsTreeAction) => void
  nodes: SettingsTreeNodes
}
