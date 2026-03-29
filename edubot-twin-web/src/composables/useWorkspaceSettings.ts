// useWorkspaceSettings — 工作区编辑器设置持久化
// 被 WorkspacePanel、FileManager、CodeEditor 三处共享同一份配置

import { useStorage } from '@vueuse/core'

export type EditorTheme = 'vs-dark' | 'vs' | 'hc-black'
export type WordWrap = 'on' | 'off'

export interface WorkspaceSettings {
  fontSize: number
  theme: EditorTheme
  wordWrap: WordWrap
  minimap: boolean
  tabSize: number
  autoSave: boolean
}

const SETTINGS_KEY = 'workspace_settings'

const DEFAULT_SETTINGS: WorkspaceSettings = {
  fontSize: 14,
  theme: 'vs-dark',
  wordWrap: 'on',
  minimap: true,
  tabSize: 4,
  autoSave: false
}

/** 工作区设置 composable，全局共享同一 localStorage key */
export function useWorkspaceSettings() {
  const settings = useStorage<WorkspaceSettings>(SETTINGS_KEY, DEFAULT_SETTINGS)

  /** 重置为默认值 */
  function resetSettings() {
    settings.value = { ...DEFAULT_SETTINGS }
  }

  return { settings, resetSettings }
}
