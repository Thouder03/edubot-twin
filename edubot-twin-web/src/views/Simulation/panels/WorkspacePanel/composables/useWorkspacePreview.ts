import { ref } from 'vue'
import type { FileReadData } from '@/api/files/types'
import { readFile, saveFile } from '@/api/files'
import { ElMessage } from 'element-plus'

export function useWorkspacePreview() {
  const previewPath = ref<string | null>(null)
  const activePath = ref<string | null>(null)
  const pinnedTabs = ref<string[]>([])
  
  // 维护脏状态和文件缓存
  const dirtyMap = ref<Map<string, boolean>>(new Map())
  const fileCache = ref<Map<string, FileReadData>>(new Map())
  
  const loading = ref(false)

  // 打开文件
  async function openFile(path: string, asPreview: boolean = true) {
    // 检查缓存
    let fileData = fileCache.value.get(path)
    
    if (!fileData) {
      loading.value = true
      try {
        const res = await readFile(path)
        if (res.code === 0 && res.data) {
          fileData = { ...res.data, path }
          fileCache.value.set(path, fileData)
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
    
    // 如果是以 preview 模式打开
    if (asPreview && !pinnedTabs.value.includes(path)) {
      previewPath.value = path
    } else {
      // 变更为 pinned
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
    const fileData = fileCache.value.get(path)
    if (!fileData) return
    
    try {
      const res = await saveFile({
        path,
        content,
        encoding: fileData.encoding || 'utf-8'
      })
      if (res.code === 0) {
        // 更新缓存和脏状态
        fileData.content = content
        fileCache.value.set(path, fileData)
        dirtyMap.value.set(path, false)
        ElMessage.success('保存成功')
      }
    } catch (e: any) {
      ElMessage.error(`保存失败: ${e.message ?? e}`)
    }
  }

  // 标记 Dirty
  function markDirty(path: string, dirty: boolean) {
    dirtyMap.value.set(path, dirty)
    // 自动固定
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

    // 清理缓存和脏状态
    fileCache.value.delete(path)
    dirtyMap.value.delete(path)

    // 如果关闭的是当前激活的 Tab，则需要重定向焦点
    if (activePath.value === path) {
      if (pinnedTabs.value.length > 0) {
        // 找最后一个 Pinned
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
