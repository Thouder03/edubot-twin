/**
 * usePanelConfig — 通用面板配置 Composable
 *
 * 等价于 lichtblick 的 PanelExtensionAdapter，封装：
 *   - 配置持久化（localStorage，等价于 context.initialState / context.saveState）
 *   - 设置树注册（等价于 context.updatePanelSettingsEditor）
 *
 * 用法（新面板标准接入方式）：
 *
 *   import { usePanelConfig } from '../../composables/usePanelConfig'
 *   import { DEFAULT_CONFIG, buildNodes, applyAction } from './settings'
 *
 *   const { config } = usePanelConfig(props.panelId, DEFAULT_CONFIG, buildNodes, applyAction)
 *
 * settings.ts 只需导出三样东西：
 *   - DEFAULT_CONFIG: T
 *   - buildNodes(config: T): SettingsTreeNodes
 *   - applyAction(config: T, action: SettingsTreeAction): T
 */
import { ref, computed, watch } from 'vue'
import type { Ref } from 'vue'
import { usePanelState } from '../stores/panelState'
import type { SettingsTreeNodes, SettingsTreeAction } from '../types/settings'

export function usePanelConfig<T extends object>(
  panelId: string,
  defaultConfig: T,
  buildNodes: (config: T) => SettingsTreeNodes,
  applyAction: (config: T, action: SettingsTreeAction) => T
): { config: Ref<T> } {
  const storageKey = `panel-config:${panelId}`
  const { updateSettingsTree } = usePanelState()

  // 1. 从 localStorage 恢复（等价于 context.initialState）
  let saved: Partial<T> = {}
  try {
    const raw = localStorage.getItem(storageKey)
    if (raw) saved = JSON.parse(raw) as Partial<T>
  } catch {
    console.warn(`[usePanelConfig] 读取配置失败 (${storageKey})，使用默认值`)
  }
  const config = ref<T>({ ...defaultConfig, ...saved }) as Ref<T>

  // 2. 配置变化时持久化（等价于 context.saveState）
  watch(
    config,
    (val) => {
      try {
        localStorage.setItem(storageKey, JSON.stringify(val))
      } catch (e) {
        console.warn(`[usePanelConfig] 保存配置失败 (${storageKey}):`, e)
      }
    },
    { deep: true }
  )

  // 3. 注册设置树（等价于 context.updatePanelSettingsEditor）
  const nodes = computed(() => buildNodes(config.value))
  watch(
    nodes,
    (n) => {
      updateSettingsTree(panelId, {
        actionHandler: (action: SettingsTreeAction) => {
          config.value = applyAction(config.value, action)
        },
        nodes: n
      })
    },
    { immediate: true }
  )

  return { config }
}
