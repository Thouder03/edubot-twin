// useWorkspace.ts — WorkspacePanel 文件 CRUD 状态管理
import { ref, computed } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { listFiles, readFile, saveFile, uploadFile, deleteFile, mkdir } from '@/api/files'
import type { FileItem, DirectoryItem, TreeNode, FileReadData } from '@/api/files/types'

export function useWorkspace() {
  // ─── 状态
  const treeData = ref<TreeNode[]>([])
  const currentFile = ref<(FileReadData & { path: string; isDirty: boolean }) | null>(null)
  const loading = ref(false)
  const saving = ref(false)
  const currentPath = ref('.') // 当前浏览的目录路径

  // ─── 构建树形节点
  function buildTreeNodes(directories: DirectoryItem[], files: FileItem[]): TreeNode[] {
    const nodes: TreeNode[] = []

    // 目录节点（先显示）
    for (const dir of directories) {
      nodes.push({
        key: dir.path,
        label: dir.name,
        type: 'directory',
        path: dir.path,
        isLeaf: false,
        children: [] // 懒加载
      })
    }

    // 文件节点
    for (const file of files) {
      nodes.push({
        key: file.path,
        label: file.name,
        type: 'file',
        path: file.path,
        extension: file.extension,
        size: file.size,
        isLeaf: true
      })
    }

    return nodes
  }

  // ─── 加载根目录
  async function loadTree(path = '.') {
    loading.value = true
    try {
      const res = await listFiles(path)
      if (res.code === 0 && res.data) {
        treeData.value = buildTreeNodes(res.data.directories, res.data.files)
        currentPath.value = path
      }
    } catch (e: any) {
      ElMessage.error(`加载文件列表失败: ${e.message ?? e}`)
    } finally {
      loading.value = false
    }
  }

  // ─── 懒加载子目录（供 el-tree load 回调）
  async function loadChildren(node: any, resolve: (children: TreeNode[]) => void) {
    if (node.level === 0) {
      resolve(treeData.value)
      return
    }

    try {
      const path = node.data?.path || '.'
      const res = await listFiles(path)
      if (res.code === 0 && res.data) {
        resolve(buildTreeNodes(res.data.directories, res.data.files))
      } else {
        resolve([])
      }
    } catch {
      resolve([])
    }
  }

  // ─── 打开文件
  async function openFile(filePath: string) {
    // 如有未保存提示
    if (currentFile.value?.isDirty) {
      try {
        await ElMessageBox.confirm('当前文件未保存，确认切换？', '提示', {
          type: 'warning',
          confirmButtonText: '不保存',
          cancelButtonText: '取消'
        })
      } catch {
        return
      }
    }

    loading.value = true
    try {
      const res = await readFile(filePath)
      if (res.code === 0 && res.data) {
        currentFile.value = { ...res.data, path: filePath, isDirty: false }
      }
    } catch (e: any) {
      ElMessage.error(`打开文件失败: ${e.message ?? e}`)
    } finally {
      loading.value = false
    }
  }

  // ─── 保存文件
  async function saveCurrentFile(content?: string) {
    if (!currentFile.value) return
    saving.value = true
    const saveContent = content ?? currentFile.value.content
    try {
      const res = await saveFile({
        path: currentFile.value.path,
        content: saveContent,
        encoding: currentFile.value.encoding ?? 'utf-8'
      })
      if (res.code === 0) {
        currentFile.value.content = saveContent
        currentFile.value.isDirty = false
        ElMessage.success('保存成功')
      }
    } catch (e: any) {
      ElMessage.error(`保存失败: ${e.message ?? e}`)
    } finally {
      saving.value = false
    }
  }

  // ─── 内容变化（标记为脏）
  function onContentChange(val: string) {
    if (currentFile.value) {
      currentFile.value.content = val
      currentFile.value.isDirty = true
    }
  }

  // ─── 上传文件
  async function handleUpload(file: File, targetPath: string) {
    try {
      const res = await uploadFile(file, targetPath)
      if (res.code === 0) {
        ElMessage.success(`上传成功: ${res.data?.filename}`)
        await loadTree(currentPath.value)
        return res.data
      }
    } catch (e: any) {
      ElMessage.error(`上传失败: ${e.message ?? e}`)
    }
    return null
  }

  // ─── 删除文件/目录
  async function handleDelete(path: string, name: string) {
    try {
      await ElMessageBox.confirm(`确认删除「${name}」？此操作不可恢复。`, '删除确认', {
        type: 'error',
        confirmButtonText: '删除',
        cancelButtonText: '取消'
      })
    } catch {
      return
    }

    try {
      const res = await deleteFile(path)
      if (res.code === 0) {
        ElMessage.success('删除成功')
        // 如果就是当前打开的文件，清空编辑器
        if (currentFile.value?.path === path) {
          currentFile.value = null
        }
        await loadTree(currentPath.value)
      }
    } catch (e: any) {
      ElMessage.error(`删除失败: ${e.message ?? e}`)
    }
  }

  // ─── 新建目录
  async function handleMkdir(dirPath: string) {
    try {
      const res = await mkdir({ path: dirPath })
      if (res.code === 0) {
        ElMessage.success('目录创建成功')
        await loadTree(currentPath.value)
      }
    } catch (e: any) {
      ElMessage.error(`创建目录失败: ${e.message ?? e}`)
    }
  }

  // ─── 当前文件扩展名（供 Monaco 语言检测）
  const currentFileExtension = computed(() => {
    if (!currentFile.value) return 'plaintext'
    const name = currentFile.value.name
    const dotIdx = name.lastIndexOf('.')
    return dotIdx !== -1 ? name.slice(dotIdx) : 'plaintext'
  })

  return {
    // 状态
    treeData,
    currentFile,
    loading,
    saving,
    currentPath,
    currentFileExtension,
    // 方法
    loadTree,
    loadChildren,
    openFile,
    saveCurrentFile,
    onContentChange,
    handleUpload,
    handleDelete,
    handleMkdir
  }
}
