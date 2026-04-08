import { ref, type Ref } from 'vue'
import type { TreeNode } from '@/api/files/types'
import type { FileListData } from '@/api/files/types'
import { createFilesApiClient, FILES_API_BASE } from '@/api/files'
import { ElMessage } from 'element-plus'

/**
 * useWorkspaceTreeState
 *
 * @param fileApiBase  当前文件 API 的 base URL（可响应式切换）
 *                     - FILES_API_BASE: 服务器端学生工作区（相对路径）
 *                     - CONTAINER_FILES_API_BASE: 学生容器 Sidecar
 *                     - SHADOW_CONTAINER_FILES_API_BASE: Shadow Dry-Run 容器 Sidecar
 * @param defaultRootPath  初始加载路径，不同 base 有不同约定
 *                         - 服务器端工作区: '.'
 *                         - 容器 Sidecar: '/' 或 '/home/student'
 */
export function useWorkspaceTreeState(
  fileApiBase: Ref<string> = ref(FILES_API_BASE),
  defaultRootPath: Ref<string> = ref('.')
) {
  /** 根据当前 base 调用文件列表 API */
  async function fetchFileList(path: string): Promise<{ code: number; data: FileListData }> {
    const client = createFilesApiClient(fileApiBase.value)
    return client.listFiles(path) as Promise<{ code: number; data: FileListData }>
  }

  const treeData = ref<TreeNode[]>([])
  const loading = ref(false)
  const currentPath = ref(defaultRootPath.value)
  const expandedPaths = ref<Set<string>>(new Set())
  let loadTreeRequestSeq = 0

  // 将后端数据转换为 TreeNode
  function buildTreeNodes(
    directories: any[],
    files: any[],
    parentPath: string,
    expandedPathSet: Set<string> = new Set()
  ): TreeNode[] {
    const nodes: TreeNode[] = []

    for (const dir of directories) {
      nodes.push({
        key: dir.path,
        label: dir.name,
        name: dir.name,
        type: 'directory',
        path: dir.path,
        parentPath,
        isLeaf: false,
        children: [],
        childrenLoaded: false,
        isExpanded: expandedPathSet.has(dir.path)
      })
    }

    for (const file of files) {
      nodes.push({
        key: file.path,
        label: file.name,
        name: file.name,
        type: 'file',
        path: file.path,
        parentPath,
        extension: file.extension,
        size: file.size,
        mtime: file.modified,
        isLeaf: true
      })
    }

    return nodes
  }

  // 加载根目录（切换 base 或手动刷新时调用）
  async function loadTree(path?: string, expandedPathSet: Set<string> = getExpandedPathSet()) {
    const rootPath = path ?? defaultRootPath.value
    const reqSeq = ++loadTreeRequestSeq
    loading.value = true
    try {
      const res = await fetchFileList(rootPath)
      if (reqSeq !== loadTreeRequestSeq) {
        return
      }
      if (res.code === 0 && res.data) {
        treeData.value = buildTreeNodes(
          res.data.directories,
          res.data.files,
          rootPath,
          expandedPathSet
        )
        currentPath.value = rootPath
      }
    } catch (e: any) {
      if (reqSeq === loadTreeRequestSeq) {
        ElMessage.error(`加载文件列表失败: ${e.message ?? e}`)
      }
    } finally {
      if (reqSeq === loadTreeRequestSeq) {
        loading.value = false
      }
    }
  }

  // 根据路径查找节点
  function findNodeByPath(nodes: TreeNode[], path: string): TreeNode | null {
    for (const node of nodes) {
      if (node.path === path) return node
      if (node.children?.length) {
        const found = findNodeByPath(node.children, path)
        if (found) return found
      }
    }
    return null
  }

  // 展开并加载子节点
  async function toggleNodeExpand(node: TreeNode) {
    if (node.type !== 'directory') return

    node.isExpanded = !node.isExpanded

    if (node.isExpanded) {
      expandedPaths.value.add(node.path)
      if (!node.childrenLoaded) {
        node.isLoading = true
        try {
          const res = await fetchFileList(node.path)
          if (res.code === 0 && res.data) {
            node.children = buildTreeNodes(
              res.data.directories,
              res.data.files,
              node.path,
              getExpandedPathSet()
            )
            node.childrenLoaded = true
          }
        } catch (e) {
          console.error('Failed to load sub-directory', e)
        } finally {
          node.isLoading = false
        }
      }
    } else {
      expandedPaths.value.delete(node.path)
    }
  }

  function touchTreeData() {
    treeData.value = [...treeData.value]
  }

  function collectExpandedDirectoryPaths(nodes: TreeNode[]): string[] {
    const paths: string[] = []
    const walk = (items: TreeNode[]) => {
      for (const node of items) {
        if (node.type === 'directory' && node.isExpanded) {
          paths.push(node.path)
        }
        if (Array.isArray(node.children) && node.children.length > 0) {
          walk(node.children)
        }
      }
    }
    walk(nodes)
    return paths
  }

  function getExpandedPathSet(): Set<string> {
    const paths = collectExpandedDirectoryPaths(treeData.value)
    expandedPaths.value.forEach((path) => paths.push(path))
    return new Set(paths)
  }

  function getExpandedDirectoryPathsSorted(
    paths: Iterable<string> = getExpandedPathSet()
  ): string[] {
    return [...paths].sort((a, b) => a.split('/').length - b.split('/').length)
  }

  function remapExpandedPaths(oldPrefix: string, newPrefix: string) {
    if (!oldPrefix || oldPrefix === newPrefix) return
    const nextExpandedPaths = new Set<string>()
    getExpandedPathSet().forEach((path) => {
      if (path === oldPrefix || path.startsWith(`${oldPrefix}/`)) {
        nextExpandedPaths.add(`${newPrefix}${path.slice(oldPrefix.length)}`)
        return
      }
      nextExpandedPaths.add(path)
    })
    expandedPaths.value = nextExpandedPaths
  }

  async function refreshExpandedDirectories() {
    const expandedPathSet = getExpandedPathSet()
    await refreshNode(currentPath.value, expandedPathSet)
    const paths = getExpandedDirectoryPathsSorted(expandedPathSet).filter(
      (path) => path !== currentPath.value && path !== '.'
    )
    for (const path of paths) {
      await refreshNode(path, expandedPathSet)
    }
  }

  // 局部刷新特定目录
  async function refreshNode(path: string, expandedPathSet: Set<string> = getExpandedPathSet()) {
    if (path === '.' || path === currentPath.value) {
      await loadTree(path, expandedPathSet)
      touchTreeData()
      return
    }

    const node = findNodeByPath(treeData.value, path)
    if (node && node.type === 'directory') {
      node.isLoading = true
      try {
        const res = await fetchFileList(node.path)
        if (res.code === 0 && res.data) {
          node.children = buildTreeNodes(
            res.data.directories,
            res.data.files,
            node.path,
            expandedPathSet
          )
          node.childrenLoaded = true
          touchTreeData()
        }
      } catch (_e) {
        // error handled
      } finally {
        node.isLoading = false
      }
    }
  }

  // 开始重命名
  function startRename(path: string) {
    const node = findNodeByPath(treeData.value, path)
    if (node) node.isRenaming = true
  }

  // 完成重命名
  function completeRename(path: string, newName?: string) {
    const node = findNodeByPath(treeData.value, path)
    if (node) {
      if (newName) {
        node.name = newName
        node.label = newName
      }
      node.isRenaming = false
    }
  }

  return {
    treeData,
    loading,
    currentPath,
    expandedPaths,
    loadTree,
    toggleNodeExpand,
    refreshNode,
    refreshExpandedDirectories,
    remapExpandedPaths,
    touchTreeData,
    findNodeByPath,
    startRename,
    completeRename
  }
}
