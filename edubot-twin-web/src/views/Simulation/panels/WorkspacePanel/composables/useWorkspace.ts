// useWorkspace.ts — Workspace 领域聚合外观 (Facade)

import { useWorkspaceTreeState } from './useWorkspaceTreeState'
import { useWorkspaceSelection } from './useWorkspaceSelection'
import { useWorkspaceClipboard } from './useWorkspaceClipboard'
import { useWorkspacePreview } from './useWorkspacePreview'
import { useWorkspaceCommands } from './useWorkspaceCommands'

export function useWorkspace() {
  const treeState = useWorkspaceTreeState()
  const selectionState = useWorkspaceSelection()
  const clipboardState = useWorkspaceClipboard()
  const previewState = useWorkspacePreview()

  const commands = useWorkspaceCommands(treeState, selectionState, previewState, clipboardState)

  return {
    ...treeState,
    ...selectionState,
    ...clipboardState,
    ...previewState,
    ...commands
  }
}
