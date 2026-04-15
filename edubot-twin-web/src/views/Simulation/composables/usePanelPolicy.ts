/**
 * usePanelPolicy - 考试面板策略过滤（第13期 SDD §7）
 *
 * 根据 attempt 的 `attempt_panel_policy_json` 快照，动态过滤 panelRegistry：
 * - 禁用的面板直接从 componentMap 中删除（安全：防学生 DevTools 取消隐藏）
 * - 提供 `isExamLocked` 计算属性（running/scoring 状态下锁定面板输入）
 *
 * panel_policy 字段 → 影响的 panelRegistry key：
 *   terminal_enabled=false   → ContainerTerminal
 *   file_tree_enabled=false  → WorkspacePanel
 *   editor_enabled=false     → WorkspacePanel
 *   ros_log_enabled=false    → RosoutPanel
 *   ros3d_enabled=false      → ROS3DViewer
 *   keyboard_control_enabled=false → KeyboardControl
 */

import { computed, type Ref, type Component as VueComponent } from 'vue'
import type { AttemptDetail } from '@/api/exam/attempts'
import { panelRegistry, buildComponentMap } from '../panels/registry'

interface PanelPolicy {
  terminal_enabled?: boolean
  file_tree_enabled?: boolean
  editor_enabled?: boolean
  ros_log_enabled?: boolean
  ros3d_enabled?: boolean
  keyboard_control_enabled?: boolean
  manual_restart_enabled?: boolean
  allow_debug_during_exam?: boolean
  [key: string]: unknown
}

const POLICY_KEY_TO_PANEL: Record<string, string> = {
  terminal_enabled: 'ContainerTerminal',
  file_tree_enabled: 'WorkspacePanel',
  editor_enabled: 'WorkspacePanel',
  ros_log_enabled: 'RosoutPanel',
  ros3d_enabled: 'ROS3DViewer',
  keyboard_control_enabled: 'KeyboardControl'
}

export function usePanelPolicy(
  isExamMode: Ref<boolean>,
  attempt: Ref<AttemptDetail | null>,
  panelPolicyJson: Ref<Record<string, unknown>>
) {
  /**
   * 根据 panel_policy 过滤后的 componentMap（供 GLayout 使用）
   * 非考试模式时返回完整 map
   */
  const filteredComponentMap = computed<Record<string, VueComponent>>(() => {
    const fullMap = buildComponentMap()
    if (!isExamMode.value) return fullMap

    const policy = panelPolicyJson.value as PanelPolicy

    // 收集所有被明确 disable 的面板 key
    const disabledKeys = new Set<string>()
    for (const [policyKey, panelKey] of Object.entries(POLICY_KEY_TO_PANEL)) {
      const val = policy[policyKey]
      // undefined / true → 保留；false → 禁用
      if (val === false) {
        disabledKeys.add(panelKey)
      }
    }

    const filtered: Record<string, VueComponent> = {}
    for (const [key, component] of Object.entries(fullMap)) {
      if (!disabledKeys.has(key)) {
        filtered[key] = component
      }
    }
    return filtered
  })

  /**
   * 过滤后的 panelRegistry（供 SimulationHeader "添加面板" 菜单使用）
   */
  const filteredPanelRegistry = computed(() => {
    if (!isExamMode.value) return panelRegistry

    const allowedKeys = new Set(Object.keys(filteredComponentMap.value))
    const filtered: typeof panelRegistry = {}
    for (const [key, entry] of Object.entries(panelRegistry)) {
      if (allowedKeys.has(key)) filtered[key] = entry
    }
    return filtered
  })

  /**
   * 考试进行中锁定：running / scoring 状态下各面板进入受限模式
   * - WorkspacePanel → Monaco readOnly
   * - ContainerTerminal → 根据 allow_debug_during_exam 决定是否禁用输入
   */
  const isExamLocked = computed<boolean>(
    () =>
      isExamMode.value &&
      attempt.value !== null &&
      ['running', 'scoring'].includes(attempt.value.status)
  )

  /**
   * 考试进行中是否允许终端调试（由 allow_debug_during_exam 控制）
   */
  const allowDebugDuringExam = computed<boolean>(
    () => !!(panelPolicyJson.value as PanelPolicy).allow_debug_during_exam
  )

  /**
   * 顶栏"手动重启"按钮是否显示（manual_restart_enabled）
   */
  const manualRestartEnabled = computed<boolean>(() => {
    if (!isExamMode.value) return true
    const val = (panelPolicyJson.value as PanelPolicy).manual_restart_enabled
    return val !== false
  })

  return {
    filteredComponentMap,
    filteredPanelRegistry,
    isExamLocked,
    allowDebugDuringExam,
    manualRestartEnabled
  }
}
