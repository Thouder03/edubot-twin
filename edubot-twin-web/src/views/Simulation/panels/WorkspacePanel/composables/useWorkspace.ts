// useWorkspace.ts — Workspace 领域聚合外观 (Facade)

import { type Ref, ref } from 'vue'
import { useWorkspaceTreeState } from './useWorkspaceTreeState'
import { useWorkspaceSelection } from './useWorkspaceSelection'
import { useWorkspaceClipboard } from './useWorkspaceClipboard'
import { useWorkspacePreview } from './useWorkspacePreview'
import { useWorkspaceCommands } from './useWorkspaceCommands'

export function useWorkspace(rootFileMode: Ref<boolean> = ref(false)) {
  const treeState = useWorkspaceTreeState(rootFileMode)
  const selectionState = useWorkspaceSelection()
  const clipboardState = useWorkspaceClipboard()
  const previewState = useWorkspacePreview()

  const commands = useWorkspaceCommands(treeState, selectionState, clipboardState)

  return {
    ...treeState,
    ...selectionState,
    ...clipboardState,
    ...previewState,
    ...commands
  }
}
