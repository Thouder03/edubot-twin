/**
 * useBundleWorkspace.ts
 *
 * 适配教师端 Bundle（文件包/环境包）的 workspace composable。
 * 提供与学生端 useWorkspace() 完全相同的外观接口，
 * 以便直接复用 FileTree.vue / FileTreeContainer.vue / WorkspaceContextMenu.vue。
 *
 * 与 useWorkspace 的核心差异：
 *   - 所有文件操作 API 通过 `apiPrefix` 参数路由到对应的 bundle 端点
 *   - 支持 protectedPaths（如 startup.sh 禁止删除）
 *
 * @param apiPrefix - 例如 '/api/v1/teachers/file-bundles/123/files'
 *                         或 '/api/v1/teachers/env-bundles/456/files'
 * @param protectedPaths - 禁止删除的文件名/路径集合（如 ['startup.sh']）
 */
import { ref, type Ref } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import request from '@/axios'
import { useUserStoreWithOut } from '@/store/modules/user'

// ─── 本地工具函数 ────────────────────────────────────────────────────────────

function getParentDir(path: string): string {
  const normalized = path.replace(/\/+$/, '')
  const idx = normalized.lastIndexOf('/')
  if (idx === -1) return '.'
  return normalized.slice(0, idx) || '.'
}

function getBaseName(path: string): string {
  const normalized = path.replace(/\/+$/, '')
  const idx = normalized.lastIndexOf('/')
  return idx === -1 ? normalized : normalized.slice(idx + 1)
}

function joinPath(dir: string, name: string): string {
  return dir === '.' ? name : `${dir}/${name}`
}

// ─── 本地 listFiles（调用 bundle API）────────────────────────────────────────

async function bundleListFiles(apiPrefix: string, path?: string) {
  const url = apiPrefix
  const params = path && path !== '.' ? { path } : undefined
  const res: any = await request.get({ url, params })
  // 后端返回 { items: [{name, type, size, modified_at}] }
  // 适配为 { directories: [], files: [] }
  const items: Array<{ name: string; type: 'file' | 'dir'; size?: number; modified_at?: string }> =
    res?.data?.items ?? []
  const directories = items
    .filter((i) => i.type === 'dir')
    .map((i) => ({
      name: i.name,
      path: path && path !== '.' ? `${path}/${i.name}` : i.name
    }))
  const files = items
    .filter((i) => i.type === 'file')
    .map((i) => ({
      name: i.name,
      path: path && path !== '.' ? `${path}/${i.name}` : i.name,
      extension: i.name.includes('.') ? i.name.split('.').pop() : '',
      size: i.size,
      modified: i.modified_at
    }))
  return { directories, files }
}

// ─── TreeNode 构造 ────────────────────────────────────────────────────────────

function buildTreeNodes(
  directories: any[],
  files: any[],
  parentPath: string,
  expandedPathSet: Set<string> = new Set()
): any[] {
  const nodes: any[] = []
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

// ─── 主 Composable ────────────────────────────────────────────────────────────

export function useBundleWorkspace(apiPrefixRef: Ref<string>, protectedPathNames: string[] = []) {
  // ── Tree State ──────────────────────────────────────────────────────────────
  const treeData = ref<any[]>([])
  const loading = ref(false)
  const currentPath = ref('.')
  const expandedPaths = ref<Set<string>>(new Set())

  function collectExpandedDirectoryPaths(nodes: any[]): string[] {
    const paths: string[] = []
    const walk = (items: any[]) => {
      for (const node of items) {
        if (node.type === 'directory' && node.isExpanded) paths.push(node.path)
        if (Array.isArray(node.children) && node.children.length > 0) walk(node.children)
      }
    }
    walk(nodes)
    return paths
  }

  function getExpandedPathSet(): Set<string> {
    const paths = collectExpandedDirectoryPaths(treeData.value)
    expandedPaths.value.forEach((p) => paths.push(p))
    return new Set(paths)
  }

  function touchTreeData() {
    treeData.value = [...treeData.value]
  }

  function findNodeByPath(nodes: any[], path: string): any | null {
    for (const node of nodes) {
      if (node.path === path) return node
      if (node.children?.length) {
        const found = findNodeByPath(node.children, path)
        if (found) return found
      }
    }
    return null
  }

  async function loadTree(path = '.', expandedPathSet: Set<string> = getExpandedPathSet()) {
    loading.value = true
    try {
      const data = await bundleListFiles(apiPrefixRef.value, path)
      treeData.value = buildTreeNodes(data.directories, data.files, path, expandedPathSet)
      currentPath.value = path
    } catch (e: any) {
      ElMessage.error(`加载文件列表失败: ${e.message ?? e}`)
    } finally {
      loading.value = false
    }
  }

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
        const data = await bundleListFiles(apiPrefixRef.value, node.path)
        node.children = buildTreeNodes(data.directories, data.files, node.path, expandedPathSet)
        node.childrenLoaded = true
        touchTreeData()
      } catch {
        // 静默
      } finally {
        node.isLoading = false
      }
    }
  }

  async function refreshExpandedDirectories() {
    const set = getExpandedPathSet()
    await refreshNode('.', set)
    const sorted = [...set]
      .filter((p) => p !== '.')
      .sort((a, b) => a.split('/').length - b.split('/').length)
    for (const p of sorted) {
      await refreshNode(p, set)
    }
  }

  function remapExpandedPaths(oldPrefix: string, newPrefix: string) {
    if (!oldPrefix || oldPrefix === newPrefix) return
    const next = new Set<string>()
    getExpandedPathSet().forEach((p) => {
      if (p === oldPrefix || p.startsWith(`${oldPrefix}/`)) {
        next.add(`${newPrefix}${p.slice(oldPrefix.length)}`)
      } else {
        next.add(p)
      }
    })
    expandedPaths.value = next
  }

  function startRename(path: string) {
    const node = findNodeByPath(treeData.value, path)
    if (node) node.isRenaming = true
  }

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

  // ── Selection State ─────────────────────────────────────────────────────────
  const selectedPaths = ref<Set<string>>(new Set())
  const lastSelectedPath = ref<string | null>(null)
  const multiSelectMode = ref(false)

  function toggleMultiSelectMode() {
    multiSelectMode.value = !multiSelectMode.value
    if (!multiSelectMode.value && selectedPaths.value.size > 1) {
      const last = lastSelectedPath.value
      selectedPaths.value = last ? new Set([last]) : new Set()
    }
  }

  function toggleSelection(path: string, multi = false, shift = false, flatPaths: string[] = []) {
    const effectiveMulti = multi || multiSelectMode.value
    if (shift && lastSelectedPath.value && flatPaths.length > 0) {
      const anchorIdx = flatPaths.indexOf(lastSelectedPath.value)
      const currentIdx = flatPaths.indexOf(path)
      if (anchorIdx !== -1 && currentIdx !== -1) {
        const start = Math.min(anchorIdx, currentIdx)
        const end = Math.max(anchorIdx, currentIdx)
        const rangeSet = new Set<string>(flatPaths.slice(start, end + 1))
        if (effectiveMulti) {
          rangeSet.forEach((p) => selectedPaths.value.add(p))
        } else {
          selectedPaths.value = rangeSet
        }
        return
      }
    }
    if (effectiveMulti) {
      if (selectedPaths.value.has(path)) {
        selectedPaths.value.delete(path)
      } else {
        selectedPaths.value.add(path)
      }
    } else {
      selectedPaths.value = new Set([path])
    }
    lastSelectedPath.value = path
  }

  function clearSelection() {
    selectedPaths.value.clear()
    lastSelectedPath.value = null
  }

  function determineContextMenuSelection(path: string) {
    if (!selectedPaths.value.has(path)) {
      selectedPaths.value = new Set([path])
      lastSelectedPath.value = path
    }
  }

  // ── Clipboard State ─────────────────────────────────────────────────────────
  const clipboard = ref<{ mode: 'copy' | 'cut'; paths: string[] } | null>(null)

  function setClipboard(mode: 'copy' | 'cut', paths: string[]) {
    clipboard.value = { mode, paths }
  }

  function clearClipboard() {
    clipboard.value = null
  }

  // ── Commands ─────────────────────────────────────────────────────────────────

  async function deleteCommand(paths: string[]) {
    if (!paths.length) return

    // 检查受保护的文件
    const protectedFile = paths.find((p) => protectedPathNames.includes(getBaseName(p)))
    if (protectedFile) {
      ElMessage.error(`启动脚本不可删除`)
      return
    }

    try {
      await ElMessageBox.confirm(`确认删除选中的 ${paths.length} 个文件/目录？`, '删除确认', {
        type: 'error',
        confirmButtonText: '删除',
        cancelButtonText: '取消'
      })
    } catch {
      return
    }

    const prefix = apiPrefixRef.value
    let hasError = false
    for (const path of paths) {
      try {
        await request.delete({ url: `${prefix}/delete`, params: { path } })
      } catch (e: any) {
        const detail = e?.response?.data?.detail
        if (detail === 'STARTUP_SCRIPT_PROTECTED') {
          ElMessage.error('启动脚本不可删除')
        } else {
          ElMessage.error(`删除失败: ${detail ?? e.message ?? e}`)
          hasError = true
        }
      }
    }

    if (!hasError) ElMessage.success('删除成功')
    clearSelection()
    await refreshExpandedDirectories()
  }

  async function uploadExternalCommand(file: File, targetPath: string) {
    const prefix = apiPrefixRef.value
    const userStore = useUserStoreWithOut()
    const token = userStore.getToken ?? ''

    const formData = new FormData()
    formData.append('file', file)
    if (targetPath && targetPath !== '.') {
      formData.append('path', targetPath)
    }

    try {
      const res: any = await fetch(`${prefix}/upload`, {
        method: 'POST',
        body: formData,
        headers: { Authorization: `Bearer ${token}` }
      })
      if (res.ok) {
        ElMessage.success(`上传成功`)
        await refreshNode(targetPath === '.' ? '.' : targetPath)
      } else {
        ElMessage.error('上传失败')
      }
    } catch (e: any) {
      ElMessage.error(`上传失败: ${e.message ?? e}`)
    }
  }

  async function mkdirCommand(path: string) {
    const prefix = apiPrefixRef.value
    try {
      await request.post({ url: `${prefix}/mkdir`, data: { path } })
      ElMessage.success('新建目录成功')
      await refreshExpandedDirectories()
    } catch (e: any) {
      ElMessage.error(`新建目录失败: ${e?.response?.data?.detail ?? e.message ?? e}`)
    }
  }

  async function startRenameCommand(path: string) {
    startRename(path)
  }

  async function cancelRenameCommand(path: string) {
    completeRename(path)
  }

  async function renameCommand(path: string, newName: string) {
    if (!newName) {
      completeRename(path)
      return
    }
    const prefix = apiPrefixRef.value
    try {
      await request.post({ url: `${prefix}/rename`, data: { path, new_name: newName } })
      const nextPath = joinPath(getParentDir(path), newName)
      remapExpandedPaths(path, nextPath)
      ElMessage.success('重命名成功')
      await refreshExpandedDirectories()
    } catch (e: any) {
      ElMessage.error(`重命名失败: ${e?.response?.data?.detail ?? e.message ?? e}`)
    } finally {
      completeRename(path)
    }
  }

  function copyCommand(paths: string[]) {
    if (!paths.length) return
    setClipboard('copy', paths)
    ElMessage.success(`已复制 ${paths.length} 个项目`)
  }

  function cutCommand(paths: string[]) {
    if (!paths.length) return
    setClipboard('cut', paths)
    ElMessage.success(`已剪切 ${paths.length} 个项目`)
  }

  async function pasteCommand(targetDir: string) {
    const cb = clipboard.value
    if (!cb?.paths.length) return
    const prefix = apiPrefixRef.value
    const isCopy = cb.mode === 'copy'
    const endpoint = isCopy ? `${prefix}/copy` : `${prefix}/move`
    try {
      await request.post({
        url: endpoint,
        data: { source_paths: cb.paths, target_dir: targetDir }
      })
      ElMessage.success('粘贴成功')
      if (!isCopy) clearClipboard()
      await refreshExpandedDirectories()
    } catch (e: any) {
      ElMessage.error(`粘贴失败: ${e?.response?.data?.detail ?? e.message ?? e}`)
    }
  }

  async function moveCommand(sourcePaths: string[], targetDir: string) {
    if (!sourcePaths.length) return
    const prefix = apiPrefixRef.value
    try {
      await request.post({
        url: `${prefix}/move`,
        data: { source_paths: sourcePaths, target_dir: targetDir }
      })
      ElMessage.success('移动成功')
      await refreshExpandedDirectories()
    } catch (e: any) {
      ElMessage.error(`移动失败: ${e?.response?.data?.detail ?? e.message ?? e}`)
    }
  }

  async function extractCommand(path: string) {
    if (!path) return
    const prefix = apiPrefixRef.value
    try {
      await request.post({ url: `${prefix}/extract`, data: { path } })
      ElMessage.success('解压成功')
      await refreshExpandedDirectories()
    } catch (e: any) {
      ElMessage.error(`解压失败: ${e?.response?.data?.detail ?? e.message ?? e}`)
    }
  }

  async function compressCommand(paths: string[]) {
    if (!paths.length) return
    let format: 'zip' | 'tar.gz' = 'zip'
    try {
      const { value: selectedFormat } = await ElMessageBox.prompt(
        '请选择压缩格式（zip 或 tar.gz）',
        '压缩文件',
        {
          confirmButtonText: '下一步',
          cancelButtonText: '取消',
          inputValue: 'zip',
          inputValidator: (v: string) =>
            v !== 'zip' && v !== 'tar.gz' ? '请输入 zip 或 tar.gz' : true
        }
      )
      format = selectedFormat === 'tar.gz' ? 'tar.gz' : 'zip'
    } catch {
      return
    }
    const firstName = paths[0].split('/').pop() ?? 'archive'
    const ext = format === 'zip' ? '.zip' : '.tar.gz'
    const defaultName = paths.length === 1 ? `${firstName}${ext}` : `archive${ext}`
    let archiveName: string
    try {
      const { value } = await ElMessageBox.prompt('输入压缩包文件名', '压缩文件', {
        confirmButtonText: '确定',
        cancelButtonText: '取消',
        inputValue: defaultName,
        inputValidator: (v: string) => (!v.trim() ? '文件名不能为空' : true)
      })
      archiveName = value.trim()
    } catch {
      return
    }
    if (format === 'zip' && !archiveName.endsWith('.zip')) archiveName += '.zip'
    if (format === 'tar.gz' && !archiveName.endsWith('.tar.gz')) archiveName += '.tar.gz'

    const prefix = apiPrefixRef.value
    try {
      await request.post({
        url: `${prefix}/compress`,
        data: { paths, archive_name: archiveName, format }
      })
      ElMessage.success('压缩成功')
      await refreshExpandedDirectories()
    } catch (e: any) {
      ElMessage.error(`压缩失败: ${e?.response?.data?.detail ?? e.message ?? e}`)
    }
  }

  async function downloadCommand(paths: string[]) {
    if (!paths.length) return
    const userStore = useUserStoreWithOut()
    const token = userStore.getToken ?? ''
    const tokenKey = userStore.getTokenKey ?? 'Authorization'
    const prefix = apiPrefixRef.value

    if (paths.length === 1) {
      const url = `${prefix}/download?path=${encodeURIComponent(paths[0])}`
      const a = document.createElement('a')
      a.href = url
      a.setAttribute(tokenKey, `Bearer ${token}`)
      a.download = getBaseName(paths[0])
      document.body.appendChild(a)
      a.click()
      document.body.removeChild(a)
    } else {
      ElMessage.info('批量下载请使用压缩后下载')
    }
  }

  // ── 对外暴露（与 useWorkspace 完全兼容的接口）──────────────────────────────

  return {
    // Tree State
    treeData,
    loading,
    currentPath,
    expandedPaths,
    loadTree,
    refreshNode,
    refreshExpandedDirectories,
    remapExpandedPaths,
    touchTreeData,
    findNodeByPath,
    startRename,
    completeRename,

    // Selection State
    selectedPaths,
    lastSelectedPath,
    multiSelectMode,
    toggleMultiSelectMode,
    toggleSelection,
    clearSelection,
    determineContextMenuSelection,

    // Clipboard State
    clipboard,
    setClipboard,
    clearClipboard,

    // Commands（WorkspaceContextMenu.vue 所需）
    deleteCommand,
    uploadExternalCommand,
    mkdirCommand,
    startRenameCommand,
    cancelRenameCommand,
    renameCommand,
    copyCommand,
    cutCommand,
    pasteCommand,
    moveCommand,
    extractCommand,
    compressCommand,
    downloadCommand
  }
}
