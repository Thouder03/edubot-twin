/**
 * 面板状态管理（响应式模块）
 *
 * 管理面板实例的注册、设置树、选中状态。
 * 在 GL 虚拟组件之间共享状态（通过 import 而非 provide/inject）。
 */
import { reactive, computed, markRaw } from 'vue'
import type { SettingsTree } from '../types/settings'

interface PanelInstance {
  panelId: string
  componentType: string
}

interface PanelStateData {
  /** 当前正在编辑设置的面板 ID */
  selectedPanelId: string | null
  /** 已注册的面板实例表 */
  panels: Record<string, PanelInstance>
  /** 每个面板实例注册的设置树 */
  settingsTrees: Record<string, SettingsTree>
}

const state = reactive<PanelStateData>({
  selectedPanelId: null,
  panels: {},
  settingsTrees: {}
})

/** 选中面板状态 composable */
export function usePanelState() {
  /** 注册面板实例 */
  function registerPanel(panelId: string, componentType: string) {
    state.panels[panelId] = { panelId, componentType }
  }

  /** 注销面板实例 */
  function unregisterPanel(panelId: string) {
    delete state.panels[panelId]
    delete state.settingsTrees[panelId]
    // 如果注销的是当前选中的面板，清空选中
    if (state.selectedPanelId === panelId) {
      state.selectedPanelId = null
    }
  }

  /** 注册/更新面板的设置树 */
  function updateSettingsTree(panelId: string, tree: SettingsTree) {
    state.settingsTrees[panelId] = markRaw(tree)
  }

  /** 选中某面板为设置目标 */
  function selectPanel(panelId: string) {
    state.selectedPanelId = panelId
  }

  /** 清空选中 */
  function clearSelection() {
    state.selectedPanelId = null
  }

  /** 当前选中面板的设置树 */
  const selectedSettingsTree = computed(() => {
    if (!state.selectedPanelId) return null
    return state.settingsTrees[state.selectedPanelId] ?? null
  })

  /** 当前选中面板的类型 */
  const selectedPanelType = computed(() => {
    if (!state.selectedPanelId) return null
    return state.panels[state.selectedPanelId]?.componentType ?? null
  })

  return {
    state,
    registerPanel,
    unregisterPanel,
    updateSettingsTree,
    selectPanel,
    clearSelection,
    selectedSettingsTree,
    selectedPanelType
  }
}
