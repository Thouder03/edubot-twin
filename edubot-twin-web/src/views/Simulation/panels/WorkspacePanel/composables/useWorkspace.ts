// useWorkspace.ts — Workspace 领域聚合外观 (Facade)

import { type Ref, ref } from 'vue'
import { createFilesApiClient, FILES_API_BASE } from '@/api/files'
import { useWorkspaceTreeState } from './useWorkspaceTreeState'
import { useWorkspaceSelection } from './useWorkspaceSelection'
import { useWorkspaceClipboard } from './useWorkspaceClipboard'
import { useWorkspacePreview } from './useWorkspacePreview'
import { useWorkspaceCommands } from './useWorkspaceCommands'

/**
 * @param fileApiBase     当前文件 API base URL（响应式），切换时自动生效
 * @param defaultRootPath 初始加载路径（响应式）
 */
export function useWorkspace(
  fileApiBase: Ref<string> = ref(FILES_API_BASE),
  defaultRootPath: Ref<string> = ref('.')
) {
  // 延迟 getter：每次调用方法时都从当前 fileApiBase 解析最新 client
  const getFilesApi = () => createFilesApiClient(fileApiBase.value)

  const treeState = useWorkspaceTreeState(fileApiBase, defaultRootPath)
  const selectionState = useWorkspaceSelection()
  const clipboardState = useWorkspaceClipboard()
  const previewState = useWorkspacePreview(getFilesApi)
  const commands = useWorkspaceCommands(treeState, selectionState, clipboardState, getFilesApi)

  return {
    ...treeState,
    ...selectionState,
    ...clipboardState,
    ...previewState,
    ...commands,
    getFilesApi
  }
}
