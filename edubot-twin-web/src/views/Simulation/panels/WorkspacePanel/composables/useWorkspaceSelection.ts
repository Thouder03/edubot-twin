import { ref } from 'vue'

export function useWorkspaceSelection() {
  const selectedPaths = ref<Set<string>>(new Set())
  const lastSelectedPath = ref<string | null>(null)

  function toggleSelection(path: string, multiple: boolean = false) {
    if (!multiple) {
      selectedPaths.value.clear()
      selectedPaths.value.add(path)
    } else {
      if (selectedPaths.value.has(path)) {
        selectedPaths.value.delete(path)
      } else {
        selectedPaths.value.add(path)
      }
    }
    lastSelectedPath.value = path
  }

  function clearSelection() {
    selectedPaths.value.clear()
    lastSelectedPath.value = null
  }

  function determineContextMenuSelection(path: string) {
    // 右键点击时，如果项不在选中列表中，则变成单选该项
    if (!selectedPaths.value.has(path)) {
      clearSelection()
      selectedPaths.value.add(path)
      lastSelectedPath.value = path
    }
  }

  return {
    selectedPaths,
    lastSelectedPath,
    toggleSelection,
    clearSelection,
    determineContextMenuSelection
  }
}
