import { ref } from 'vue'

export function useWorkspaceSelection() {
  const selectedPaths = ref<Set<string>>(new Set())
  const lastSelectedPath = ref<string | null>(null)

  /** 多选模式开关：开启后每次点击都叠加到选区（相当于常驻 Ctrl 键） */
  const multiSelectMode = ref(false)

  function toggleMultiSelectMode() {
    multiSelectMode.value = !multiSelectMode.value
    // 关闭时若选区超过 1 个，只保留最后一个
    if (!multiSelectMode.value && selectedPaths.value.size > 1) {
      const last = lastSelectedPath.value
      selectedPaths.value = last ? new Set([last]) : new Set()
    }
  }

  /**
   * 切换选中状态，支持三种模式：
   * - 普通点击：清除旧选区，单选当前项
   * - Ctrl/Meta 点击（multi=true）或多选模式：切换当前项，保留其余选项
   * - Shift 点击（shift=true）：从上次点击位置到当前位置范围批量选中
   *
   * @param path       被点击节点的路径
   * @param multi      是否 Ctrl/Meta 点击
   * @param shift      是否 Shift 点击
   * @param flatPaths  当前可见的扁平节点路径列表（Shift 范围选所需）
   */
  function toggleSelection(
    path: string,
    multi: boolean = false,
    shift: boolean = false,
    flatPaths: string[] = []
  ) {
    // 多选模式下，普通点击等同于 Ctrl 点击
    const effectiveMulti = multi || multiSelectMode.value

    if (shift && lastSelectedPath.value && flatPaths.length > 0) {
      // Shift 范围选：找到锚点 lastSelectedPath 和当前节点在 flatPaths 中的索引
      const anchorIdx = flatPaths.indexOf(lastSelectedPath.value)
      const currentIdx = flatPaths.indexOf(path)

      if (anchorIdx !== -1 && currentIdx !== -1) {
        const start = Math.min(anchorIdx, currentIdx)
        const end = Math.max(anchorIdx, currentIdx)
        const rangeSet = new Set<string>(flatPaths.slice(start, end + 1))

        if (effectiveMulti) {
          // Ctrl+Shift / 多选模式+Shift：在已有选区基础上叠加范围
          rangeSet.forEach((p) => selectedPaths.value.add(p))
        } else {
          // 纯 Shift：替换为范围内节点
          selectedPaths.value = rangeSet
        }
        // Shift 选中时不更新 lastSelectedPath，保持锚点
        return
      }
    }

    if (effectiveMulti) {
      // Ctrl/Meta / 多选模式：切换单个项目
      if (selectedPaths.value.has(path)) {
        selectedPaths.value.delete(path)
      } else {
        selectedPaths.value.add(path)
      }
    } else {
      // 普通点击：单选
      selectedPaths.value = new Set([path])
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
      selectedPaths.value = new Set([path])
      lastSelectedPath.value = path
    }
  }

  return {
    selectedPaths,
    lastSelectedPath,
    multiSelectMode,
    toggleMultiSelectMode,
    toggleSelection,
    clearSelection,
    determineContextMenuSelection
  }
}
