import { ref, reactive } from 'vue'
import type { FileReadData } from '@/api/files/types'
import type { FilesApiClient } from '@/api/files'
import { ElMessage } from 'element-plus'

type WorkspaceFileData = FileReadData & { extension?: string }

function extractExtension(path: string): string {
  const fileName = path.split('/').pop() ?? ''
  const dotIndex = fileName.lastIndexOf('.')
  if (dotIndex <= 0) return ''
  return fileName.slice(dotIndex)
}

export function useWorkspacePreview(getFilesApi: () => FilesApiClient) {
  const previewPath = ref<string | null>(null)
  const activePath = ref<string | null>(null)
  const pinnedTabs = ref<string[]>([])

  // 使用 reactive 对象代替 ref<Map>
  // 原因：Vue 3 无法追踪 Map.set()/get()/has() 的变化，
  //       但可以追踪 reactive 对象的属性增删（Object.keys 变化）
  const dirtyMap = reactive<Record<string, boolean>>({})
  const fileCache = reactive<Record<string, WorkspaceFileData>>({})

  const loading = ref(false)

  // 打开文件
  async function openFile(path: string, asPreview: boolean = true) {
    let fileData = fileCache[path]

    if (!fileData) {
      loading.value = true
      try {
        const res = await getFilesApi().readFile(path)
        if (res.code === 0 && res.data) {
          fileData = {
            ...res.data,
            path,
            extension: extractExtension(res.data.path || path)
          }
          fileCache[path] = fileData
        } else {
          throw new Error('Load failed')
        }
      } catch (e: any) {
        ElMessage.error(`读取文件失败: ${e.message ?? e}`)
        return
      } finally {
        loading.value = false
      }
    }

    if (asPreview && !pinnedTabs.value.includes(path)) {
      previewPath.value = path
    } else {
      if (previewPath.value === path) {
        previewPath.value = null
      }
      if (!pinnedTabs.value.includes(path)) {
        pinnedTabs.value.push(path)
      }
    }

    activePath.value = path
  }

  // 保存文件
  async function saveActiveFile(content: string) {
    if (!activePath.value) return
    const path = activePath.value
    const fileData = fileCache[path]
    if (!fileData) return

    try {
      const res = await getFilesApi().saveFile({
        path,
        content,
        encoding: fileData.encoding || 'utf-8'
      })
      if (res.code === 0) {
        fileData.content = content
        fileCache[path] = fileData
        dirtyMap[path] = false
        ElMessage.success('保存成功')
      }
    } catch (e: any) {
      ElMessage.error(`保存失败: ${e.message ?? e}`)
    }
  }

  // 标记 Dirty
  function markDirty(path: string, dirty: boolean) {
    dirtyMap[path] = dirty
    if (dirty && previewPath.value === path) {
      previewPath.value = null
      if (!pinnedTabs.value.includes(path)) {
        pinnedTabs.value.push(path)
      }
    }
  }

  // 关闭标签页
  function closeTab(path: string) {
    if (previewPath.value === path) {
      previewPath.value = null
    } else {
      const idx = pinnedTabs.value.indexOf(path)
      if (idx !== -1) {
        pinnedTabs.value.splice(idx, 1)
      }
    }

    delete fileCache[path]
    delete dirtyMap[path]

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

  return {
    previewPath,
    activePath,
    pinnedTabs,
    dirtyMap,
    fileCache,
    loading,
    openFile,
    saveActiveFile,
    markDirty,
    closeTab
  }
}
