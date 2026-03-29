import { ref } from 'vue'

export interface ClipboardState {
  mode: 'copy' | 'cut'
  paths: string[]
  ts: number
}

export function useWorkspaceClipboard() {
  const clipboard = ref<ClipboardState | null>(null)

  function setClipboard(mode: 'copy' | 'cut', paths: string[]) {
    if (!paths.length) return
    clipboard.value = {
      mode,
      paths,
      ts: Date.now()
    }
  }

  function clearClipboard() {
    clipboard.value = null
  }

  return {
    clipboard,
    setClipboard,
    clearClipboard
  }
}
