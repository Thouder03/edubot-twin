/**
 * useBundleEditorState.ts
 *
 * 适配教师端 Bundle 文件读写的编辑器状态 composable。
 * 提供与 useWorkspacePreview() 完全相同的外观接口，
 * 以便直接复用 EditorWorkbench.vue（标签页 + 快捷键保存）。
 *
 * 与 useWorkspacePreview 的核心差异：
 *   - openFile() 通过 readFn 参数读取文件内容（教师端 bundle API）
 *   - saveActiveFile() 通过 saveFn 参数保存（教师端 bundle API）
 *   - 语言检测基于文件扩展名（vs 学生端用 MIME type）
 *
 * @param readFn  (path: string) => Promise<string>   读取文件内容
 * @param saveFn  (path: string, content: string) => Promise<void>  保存文件
 */
import { ref, reactive } from 'vue'
import { ElMessage } from 'element-plus'

// ─── 工具函数 ─────────────────────────────────────────────────────────────────

function detectLanguage(path: string): string {
  const name = path.split('/').pop() ?? ''
  const dotIdx = name.lastIndexOf('.')
  const ext = dotIdx > 0 ? name.slice(dotIdx + 1).toLowerCase() : ''
  const map: Record<string, string> = {
    py: 'python',
    launch: 'xml',
    urdf: 'xml',
    xacro: 'xml',
    yaml: 'yaml',
    yml: 'yaml',
    sh: 'shell',
    bash: 'shell',
    json: 'json',
    cpp: 'cpp',
    cc: 'cpp',
    cxx: 'cpp',
    c: 'c',
    h: 'c',
    hpp: 'cpp',
    md: 'markdown',
    txt: 'plaintext',
    cfg: 'ini',
    toml: 'ini'
  }
  return map[ext] ?? 'plaintext'
}

// ─── 主 Composable ────────────────────────────────────────────────────────────

export function useBundleEditorState(
  readFn: (path: string) => Promise<string>,
  saveFn: (path: string, content: string) => Promise<void>
) {
  const previewPath = ref<string | null>(null)
  const activePath = ref<string | null>(null)
  const pinnedTabs = ref<string[]>([])

  // reactive 确保 Vue 能追踪属性增删
  const dirtyMap = reactive<Record<string, boolean>>({})
  const fileCache = reactive<Record<string, { content: string; extension: string; path: string }>>(
    {}
  )

  const loading = ref(false)

  // ── 打开文件（单击 = preview，双击 = pinned）────────────────────────────────

  async function openFile(path: string, asPreview = true) {
    // 如果缓存中已有，直接激活不再重新读取
    if (!fileCache[path]) {
      loading.value = true
      try {
        const content = await readFn(path)
        fileCache[path] = {
          path,
          content,
          extension: detectLanguage(path)
        }
      } catch (e: any) {
        ElMessage.error(`读取文件失败: ${e?.response?.data?.detail ?? e.message ?? e}`)
        loading.value = false
        return
      } finally {
        loading.value = false
      }
    }

    if (asPreview && !pinnedTabs.value.includes(path)) {
      previewPath.value = path
    } else {
      if (previewPath.value === path) previewPath.value = null
      if (!pinnedTabs.value.includes(path)) pinnedTabs.value.push(path)
    }

    activePath.value = path
  }

  // ── Ctrl+S / @save 事件触发保存 ──────────────────────────────────────────

  async function saveActiveFile(content: string) {
    if (!activePath.value) return
    const path = activePath.value
    const cached = fileCache[path]
    if (!cached) return

    try {
      await saveFn(path, content)
      cached.content = content
      dirtyMap[path] = false
      ElMessage.success('保存成功')
    } catch (e: any) {
      const detail = e?.response?.data?.detail
      if (detail === 'FILE_SAVE_CONFLICT') {
        ElMessage.error('文件已被其他操作更新，请刷新后重试')
      } else if (detail === 'STARTUP_SCRIPT_PROTECTED') {
        ElMessage.error('启动脚本内容不可直接覆盖，请通过接口更新')
      } else {
        ElMessage.error(`保存失败: ${detail ?? e.message ?? e}`)
      }
    }
  }

  // ── 标记 Dirty（编辑后自动固定标签页）────────────────────────────────────

  function markDirty(path: string, dirty: boolean) {
    dirtyMap[path] = dirty
    if (dirty && previewPath.value === path) {
      previewPath.value = null
      if (!pinnedTabs.value.includes(path)) {
        pinnedTabs.value.push(path)
      }
    }
  }

  // ── 关闭标签页 ───────────────────────────────────────────────────────────

  function closeTab(path: string) {
    if (previewPath.value === path) {
      previewPath.value = null
    } else {
      const idx = pinnedTabs.value.indexOf(path)
      if (idx !== -1) pinnedTabs.value.splice(idx, 1)
    }

    delete fileCache[path]
    delete dirtyMap[path]

    // 切换焦点到最近的标签页
    if (activePath.value === path) {
      if (pinnedTabs.value.length > 0) {
        activePath.value = pinnedTabs.value[pinnedTabs.value.length - 1]
      } else if (previewPath.value) {
        activePath.value = previewPath.value
      } else {
        activePath.value = null
      }
    }
  }

  // ── 便捷方法：判断是否有未保存修改 ───────────────────────────────────────

  function hasAnyUnsavedChanges(): boolean {
    return Object.values(dirtyMap).some(Boolean)
  }

  function getDirtyPaths(): string[] {
    return Object.entries(dirtyMap)
      .filter(([, dirty]) => dirty)
      .map(([path]) => path)
  }

  // ── 切换到外部打开的文件路径（兼容旧系统单文件逻辑） ─────────────────────

  function handleSelectTab(path: string, asPreview?: boolean) {
    openFile(path, asPreview ?? false)
  }

  // ── 内容变更时更新缓存并标记脏 ──────────────────────────────────────────

  function handleContentChange(content: string) {
    if (!activePath.value) return
    const cached = fileCache[activePath.value]
    if (cached) {
      const isDirty = content !== cached.content
      markDirty(activePath.value, isDirty)
    }
  }

  return {
    // EditorWorkbench.vue props
    previewPath,
    activePath,
    pinnedTabs,
    dirtyMap,
    fileCache,
    loading,

    // EditorWorkbench.vue 事件处理方法
    openFile,
    saveActiveFile,
    markDirty,
    closeTab,
    handleSelectTab,
    handleContentChange,

    // 辅助方法
    hasAnyUnsavedChanges,
    getDirtyPaths
  }
}
