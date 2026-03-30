import { ElMessage, ElMessageBox } from 'element-plus'
import { batchDeleteFiles, mkdir, uploadFile, renameFile, moveFiles, copyFiles } from '@/api/files'
// 导入其他组合式函数状态（由调用方注入或者这里直接构建命令工厂）

function getParentDir(path: string): string {
  const normalizedPath = path.replace(/\/+$/, '')
  const slashIndex = normalizedPath.lastIndexOf('/')
  if (slashIndex === -1) return '.'
  return normalizedPath.slice(0, slashIndex) || '.'
}

async function refreshMovedDirectories(treeState: any) {
  await treeState.refreshExpandedDirectories()
}

async function refreshDirectoryIfNotRoot(treeState: any, path: string) {
  if (path === '.') return
  await treeState.refreshNode(path)
}

function removeNodeByPath(nodes: any[], path: string): boolean {
  for (let i = 0; i < nodes.length; i += 1) {
    const node = nodes[i]
    if (node.path === path) {
      nodes.splice(i, 1)
      return true
    }
    if (Array.isArray(node.children) && node.children.length > 0) {
      const removed = removeNodeByPath(node.children, path)
      if (removed) return true
    }
  }
  return false
}

function removeNodesByPaths(treeState: any, paths: string[]) {
  for (const path of paths) {
    removeNodeByPath(treeState.treeData.value, path)
  }
  treeState.touchTreeData?.()
}

function getBaseName(path: string): string {
  const normalizedPath = path.replace(/\/+$/, '')
  const slashIndex = normalizedPath.lastIndexOf('/')
  if (slashIndex === -1) return normalizedPath
  return normalizedPath.slice(slashIndex + 1)
}

function joinPath(dir: string, name: string): string {
  return dir === '.' ? name : `${dir}/${name}`
}

function updateNodePathAndChildren(node: any, oldPrefix: string, newPrefix: string) {
  if (!node?.path || !String(node.path).startsWith(oldPrefix)) return

  const suffix = String(node.path).slice(oldPrefix.length)
  const nextPath = `${newPrefix}${suffix}`
  node.path = nextPath
  node.key = nextPath
  node.parentPath = getParentDir(nextPath)

  if (Array.isArray(node.children)) {
    node.children.forEach((child) => updateNodePathAndChildren(child, oldPrefix, newPrefix))
  }
}

function applyMovedPathUpdates(
  treeState: any,
  movedPairs: Array<{ sourcePath: string; nextPath: string }>
) {
  for (const { sourcePath, nextPath } of movedPairs) {
    const node = treeState.findNodeByPath(treeState.treeData.value, sourcePath)
    if (!node) continue
    updateNodePathAndChildren(node, sourcePath, nextPath)
  }
}

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
        const failedSet = new Set<string>((res.data?.failed ?? []).map((item: any) => item.path))
        const deletedPaths: string[] = Array.isArray(res.data?.deleted)
          ? res.data.deleted
          : paths.filter((path) => !failedSet.has(path))

        removeNodesByPaths(treeState, deletedPaths)

        const refreshParents = new Set<string>(deletedPaths.map((path) => getParentDir(path)))
        for (const path of refreshParents) {
          await refreshDirectoryIfNotRoot(treeState, path)
        }

        if (res.data?.failed?.length) {
          ElMessage.warning(`部分删除失败: ${res.data.failed.length} 个项目`)
        } else {
          ElMessage.success('删除成功')
        }
      }
    } catch (e: any) {
      ElMessage.error(`删除失败: ${e.message ?? e}`)
    }

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

  async function mkdirCommand(path: string) {
    try {
      const res = await mkdir({ path })
      if (res.code === 0) {
        ElMessage.success('新建目录成功')
        await treeState.refreshExpandedDirectories()
      }
    } catch (e: any) {
      ElMessage.error(`新建目录失败: ${e.response?.data?.detail ?? e.message ?? e}`)
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
        const nextPath = res.data?.new_path || joinPath(getParentDir(path), newName)
        treeState.remapExpandedPaths?.(path, nextPath)
        ElMessage.success(`重命名成功`)
        await treeState.refreshExpandedDirectories()
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

    const sourcePaths: string[] = [...cb.paths]
    const isCopy = cb.mode === 'copy'
    const apiCall = isCopy ? copyFiles : moveFiles
    const movedPairs: Array<{ sourcePath: string; nextPath: string }> = []

    try {
      const res = await apiCall({ source_paths: sourcePaths, target_dir: targetDir })
      if (res.code === 0) {
        if (!isCopy) {
          const successPaths: string[] = Array.isArray(res.data?.success) ? res.data.success : []
          const failedPaths = new Set<string>(
            (res.data?.failed ?? []).map((item: any) => item.path)
          )

          let successIndex = 0

          for (const sourcePath of sourcePaths) {
            if (failedPaths.has(sourcePath)) continue
            const nextPath =
              successPaths[successIndex] || joinPath(targetDir, getBaseName(sourcePath))
            successIndex += 1
            movedPairs.push({ sourcePath, nextPath })
          }

          applyMovedPathUpdates(treeState, movedPairs)
        }

        if (res.data?.failed?.length) {
          ElMessage.warning(`部分操作失败: ${res.data.failed.length} 个项目`)
        } else {
          ElMessage.success('粘贴成功')
          if (!isCopy) {
            // 如果是剪切且全成功，清空剪贴板
            clipboardState.clearClipboard()
          }
        }
        if (isCopy) {
          await refreshDirectoryIfNotRoot(treeState, targetDir)
          treeState.touchTreeData?.()
        } else {
          movedPairs.forEach(({ sourcePath, nextPath }) => {
            treeState.remapExpandedPaths?.(sourcePath, nextPath)
          })
          await refreshMovedDirectories(treeState)
        }
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
        const successPaths: string[] = Array.isArray(res.data?.success) ? res.data.success : []
        const failedPaths = new Set<string>((res.data?.failed ?? []).map((item: any) => item.path))

        const movedPairs: Array<{ sourcePath: string; nextPath: string }> = []
        let successIndex = 0

        for (const sourcePath of sourcePaths) {
          if (failedPaths.has(sourcePath)) continue
          const nextPath =
            successPaths[successIndex] || joinPath(targetDir, getBaseName(sourcePath))
          successIndex += 1
          movedPairs.push({ sourcePath, nextPath })
        }

        applyMovedPathUpdates(treeState, movedPairs)

        if (res.data?.failed?.length) {
          ElMessage.warning(`部分拖拽移动失败: ${res.data.failed.length} 个项目`)
        } else {
          ElMessage.success('移动成功')
        }
        movedPairs.forEach(({ sourcePath, nextPath }) => {
          treeState.remapExpandedPaths?.(sourcePath, nextPath)
        })
        await refreshMovedDirectories(treeState)
      }
    } catch (e: any) {
      ElMessage.error(`移动失败: ${e.response?.data?.detail ?? e.message ?? e}`)
      await refreshMovedDirectories(treeState)
    }
  }

  // 更多命令...（移动等留在后续实施）

  return {
    deleteCommand,
    uploadExternalCommand,
    mkdirCommand,
    startRenameCommand,
    cancelRenameCommand,
    renameCommand,
    copyCommand,
    cutCommand,
    pasteCommand,
    moveCommand
  }
}
