import { ref } from 'vue'
import type { TreeNode } from '@/api/files/types'
import { listFiles } from '@/api/files'
import { ElMessage } from 'element-plus'

export function useWorkspaceTreeState() {
  const treeData = ref<TreeNode[]>([])
  const loading = ref(false)
  const currentPath = ref('.')
  const expandedPaths = ref<Set<string>>(new Set())

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

  // 加载根目录
  async function loadTree(path = '.', expandedPathSet: Set<string> = new Set()) {
    loading.value = true
    try {
      const res = await listFiles(path)
      if (res.code === 0 && res.data) {
        treeData.value = buildTreeNodes(res.data.directories, res.data.files, path, expandedPathSet)
        currentPath.value = path
      }
    } catch (e: any) {
      ElMessage.error(`加载文件列表失败: ${e.message ?? e}`)
    } finally {
      loading.value = false
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
      // 处理懒加载
      if (!node.childrenLoaded) {
        node.isLoading = true
        try {
          const res = await listFiles(node.path)
          if (res.code === 0 && res.data) {
            node.children = buildTreeNodes(res.data.directories, res.data.files, node.path)
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

  function getExpandedDirectoryPathsSorted(): string[] {
    return collectExpandedDirectoryPaths(treeData.value).sort(
      (a, b) => a.split('/').length - b.split('/').length
    )
  }

  async function refreshExpandedDirectories() {
    const paths = getExpandedDirectoryPathsSorted()
    const expandedPathSet = new Set(paths)
    if (paths.length === 0) {
      await refreshNode('.', expandedPathSet)
      return
    }

    for (const path of paths) {
      await refreshNode(path, expandedPathSet)
    }
  }

  // 局部刷新特定目录
  async function refreshNode(path: string, expandedPathSet: Set<string> = new Set()) {
    if (path === '.' || path === currentPath.value) {
      await loadTree(path, expandedPathSet)
      touchTreeData()
      return
    }

    const node = findNodeByPath(treeData.value, path)

    if (node && node.type === 'directory') {
      node.isLoading = true
      try {
        const res = await listFiles(node.path)
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

  // 完成重命名 (取消或成功)
  function completeRename(path: string, newName?: string) {
    const node = findNodeByPath(treeData.value, path)
    if (node) {
      if (newName) {
        node.name = newName
        node.label = newName
        // 注：这里只更新了节点显示，它的 path 尚未更新。真实交互会通过刷新目录树或精确回写解决（Phase 3）。
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
    touchTreeData,
    findNodeByPath,
    startRename,
    completeRename
  }
}
