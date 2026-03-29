import { ElMessage, ElMessageBox } from 'element-plus'
import { batchDeleteFiles, mkdir, uploadFile, renameFile, moveFiles, copyFiles } from '@/api/files'
// 导入其他组合式函数状态（由调用方注入或者这里直接构建命令工厂）

export function useWorkspaceCommands(
  treeState: any, 
  selectionState: any, 
  previewState: any, 
  clipboardState: any
) {
  
  async function deleteCommand(paths: string[]) {
    if (!paths.length) return
    
    try {
      await ElMessageBox.confirm(`确认删除选中的 ${paths.length} 个文件/目录？`, '删除确认', {
        type: 'error',
        confirmButtonText: '删除',
        cancelButtonText: '取消'
      })
    } catch {
      return
    }

    try {
      const res = await batchDeleteFiles({ paths })
      if (res.code === 0) {
        if (res.data?.failed?.length) {
          ElMessage.warning(`部分删除失败: ${res.data.failed.length} 个项目`)
        } else {
          ElMessage.success('删除成功')
        }
      }
    } catch (e: any) {
      ElMessage.error(`删除失败: ${e.message ?? e}`)
    }
    
    // 强制刷新根目录（或者优化为局部刷新）
    await treeState.refreshNode('.')
    selectionState.clearSelection()
  }

  async function uploadExternalCommand(file: File, targetPath: string) {
    try {
      const res = await uploadFile(file, targetPath)
      if (res.code === 0) {
        ElMessage.success(`上传成功`)
        await treeState.refreshNode(targetPath)
      }
    } catch (e: any) {
      ElMessage.error(`上传失败: ${e.message ?? e}`)
    }
  }

  async function startRenameCommand(path: string) {
    treeState.startRename(path)
  }

  async function cancelRenameCommand(path: string) {
    treeState.completeRename(path)
  }

  async function renameCommand(path: string, newName: string) {
    if (!newName) {
      treeState.completeRename(path)
      return
    }
    try {
      const res = await renameFile({ path, new_name: newName })
      if (res.code === 0) {
        ElMessage.success(`重命名成功`)
        // 直接刷新父目录或重新拉根目录
        await treeState.refreshNode('.')
      }
    } catch (e: any) {
      ElMessage.error(`重命名失败: ${e.response?.data?.detail ?? e.message ?? e}`)
    } finally {
      treeState.completeRename(path) // 清除 UI 的重命名状态输入框
    }
  }

  // 复制选项到剪贴板
  function copyCommand(paths: string[]) {
    if (!paths.length) return
    clipboardState.setClipboard('copy', paths)
    ElMessage.success(`已复制 ${paths.length} 个项目`)
  }

  // 剪切选项到剪贴板
  function cutCommand(paths: string[]) {
    if (!paths.length) return
    clipboardState.setClipboard('cut', paths)
    ElMessage.success(`已剪切 ${paths.length} 个项目`)
  }

  // 粘贴剪贴板内容到目标目录
  async function pasteCommand(targetDir: string) {
    const cb = clipboardState.clipboard.value
    if (!cb || !cb.paths.length) return

    const isCopy = cb.mode === 'copy'
    const apiCall = isCopy ? copyFiles : moveFiles

    try {
      const res = await apiCall({ source_paths: cb.paths, target_dir: targetDir })
      if (res.code === 0) {
        if (res.data?.failed?.length) {
          ElMessage.warning(`部分操作失败: ${res.data.failed.length} 个项目`)
        } else {
          ElMessage.success('粘贴成功')
          if (!isCopy) {
            // 如果是剪切且全成功，清空剪贴板
            clipboardState.clearClipboard()
          }
        }
        await treeState.refreshNode('.') // 刷新目录
      }
    } catch (e: any) {
      ElMessage.error(`粘贴失败: ${e.response?.data?.detail ?? e.message ?? e}`)
    }
  }

  // 直接调用后端的移动（如拖拽落入）
  async function moveCommand(sourcePaths: string[], targetDir: string) {
    if (!sourcePaths.length) return
    try {
      const res = await moveFiles({ source_paths: sourcePaths, target_dir: targetDir })
      if (res.code === 0) {
        if (res.data?.failed?.length) {
          ElMessage.warning(`部分拖拽移动失败: ${res.data.failed.length} 个项目`)
        } else {
          ElMessage.success('移动成功')
        }
        await treeState.refreshNode('.')
      }
    } catch (e: any) {
      ElMessage.error(`移动失败: ${e.response?.data?.detail ?? e.message ?? e}`)
      await treeState.refreshNode('.') // 还原前端由于 `@he-tree` 自动引发的乐观更新
    }
  }

  // 更多命令...（移动等留在后续实施）

  return {
    deleteCommand,
    uploadExternalCommand,
    startRenameCommand,
    cancelRenameCommand,
    renameCommand,
    copyCommand,
    cutCommand,
    pasteCommand,
    moveCommand
  }
}
