<script setup lang="ts">
/**
 * 实验文件管理页 — /teacher/experiments/files
 *
 * 状态 A：文件包列表视图（初始状态）
 * 状态 B：文件树视图（双击进入后，完整复用学生端 FileTree.vue 右键菜单）
 *
 * SDD §15.4：文件树完全复用 WorkspacePanel 的文件树组件（FileTree.vue），
 * 通过 useBundleWorkspace 适配不同 API 后端地址。
 */
import { ContentWrap } from '@/components/ContentWrap'
import MonacoEditor from '@/components/Monaco/MonacoEditor.vue'
import FileTree from '@/views/Simulation/panels/WorkspacePanel/FileTree.vue'
import {
  createFileBundleApi,
  deleteFileBundleApi,
  getFileBundleListApi,
  patchFileBundleApi,
  readFileBundleFileApi,
  saveFileBundleFileApi
} from '@/api/experiment'
import type { FileBundleListItem } from '@/api/experiment/types'
import { useBundleWorkspace } from './composables/useBundleWorkspace'
import {
  ElButton,
  ElDialog,
  ElEmpty,
  ElForm,
  ElFormItem,
  ElInput,
  ElMessage,
  ElMessageBox,
  ElScrollbar,
  ElSkeleton,
  ElTag,
  ElTooltip
} from 'element-plus'
import { computed, ref, watch, onBeforeUnmount, nextTick } from 'vue'
import { onBeforeRouteLeave } from 'vue-router'

// ─── 视图状态 ─────────────────────────────────────────────────────────────────

type ViewMode = 'list' | 'tree'
const viewMode = ref<ViewMode>('list')

// ─── 文件包列表 ───────────────────────────────────────────────────────────────

const bundles = ref<FileBundleListItem[]>([])
const bundlesLoading = ref(false)
const selectedBundle = ref<FileBundleListItem | null>(null)

const fetchBundles = async () => {
  bundlesLoading.value = true
  try {
    const res = await getFileBundleListApi({ page: 1, page_size: 100 })
    bundles.value = res.data?.list ?? []
  } finally {
    bundlesLoading.value = false
  }
}

fetchBundles()

// ─── 文件包 API 前缀 ──────────────────────────────────────────────────────────

const fileApiPrefix = computed(() =>
  selectedBundle.value
    ? `/api/v1/teachers/file-bundles/${selectedBundle.value.bundle_id}/files`
    : ''
)

// ─── useBundleWorkspace（完全兼容 FileTree.vue 接口）─────────────────────────

const workspace = useBundleWorkspace(fileApiPrefix)

// 当切换文件包时重载树
watch(fileApiPrefix, async (newPrefix) => {
  if (newPrefix && viewMode.value === 'tree') {
    await workspace.loadTree()
  }
})

// ─── 单击选中 ─────────────────────────────────────────────────────────────────

const handleBundleClick = (bundle: FileBundleListItem) => {
  selectedBundle.value = bundle
}

// ─── 双击进入文件树 ───────────────────────────────────────────────────────────

const handleBundleDblClick = async (bundle: FileBundleListItem) => {
  if (hasUnsavedChanges.value) {
    const ok = await confirmLeave()
    if (!ok) return
  }
  selectedBundle.value = bundle
  viewMode.value = 'tree'
  workspace.clearSelection()
  openedFilePath.value = ''
  fileContent.value = ''
  hasUnsavedChanges.value = false
  await workspace.loadTree()
}

// ─── 返回文件包列表 ──────────────────────────────────────────────────────────

const handleBackToList = async () => {
  const ok = await confirmLeave()
  if (!ok) return
  viewMode.value = 'list'
  openedFilePath.value = ''
  fileContent.value = ''
  hasUnsavedChanges.value = false
}

// ─── 编辑器状态 ───────────────────────────────────────────────────────────────

const openedFilePath = ref('')
const fileContent = ref('')
const hasUnsavedChanges = ref(false)

const editorContent = computed({
  get: () => fileContent.value,
  set: (val) => {
    fileContent.value = val
    hasUnsavedChanges.value = true
  }
})

// ─── 点击文件树节点打开文件 ───────────────────────────────────────────────────

const handleSelectFile = async (path: string) => {
  // 目录节点不打开编辑器
  const node = workspace.findNodeByPath(workspace.treeData.value, path)
  if (!node || node.type === 'directory') return

  if (hasUnsavedChanges.value) {
    const ok = await confirmLeave()
    if (!ok) return
  }

  try {
    const res = await readFileBundleFileApi(selectedBundle.value!.bundle_id, path)
    openedFilePath.value = path
    fileContent.value = res.data?.content ?? ''
    hasUnsavedChanges.value = false
  } catch (e: any) {
    ElMessage.error('打开文件失败：' + (e?.response?.data?.detail ?? e.message ?? ''))
  }
}

// ─── 保存文件 ─────────────────────────────────────────────────────────────────

const handleSave = async () => {
  if (!openedFilePath.value || !selectedBundle.value) return
  try {
    await saveFileBundleFileApi(
      selectedBundle.value.bundle_id,
      openedFilePath.value,
      fileContent.value
    )
    ElMessage.success('保存成功')
    hasUnsavedChanges.value = false
  } catch (e: any) {
    const detail = e?.response?.data?.detail
    if (detail === 'FILE_SAVE_CONFLICT') {
      ElMessage.error('文件已被其他操作更新，请刷新后重试')
    } else {
      ElMessage.error('保存失败：' + (detail ?? e.message ?? ''))
    }
  }
}

// ─── 离开确认 ─────────────────────────────────────────────────────────────────

const confirmLeave = async (): Promise<boolean> => {
  if (!hasUnsavedChanges.value) return true
  try {
    await ElMessageBox.confirm('当前文件有未保存的修改，是否保存后继续？', '未保存修改', {
      confirmButtonText: '保存后继续',
      cancelButtonText: '放弃修改',
      distinguishCancelAndClose: true,
      type: 'warning'
    })
    await handleSave()
    return true
  } catch (action) {
    if (action === 'cancel') return true // 放弃修改
    return false // 关闭弹窗（不离开）
  }
}

onBeforeRouteLeave(async (_to, _from, next) => {
  const ok = await confirmLeave()
  next(ok ? undefined : false)
})

// ─── 上传 ─────────────────────────────────────────────────────────────────────

const uploadInputRef = ref<HTMLInputElement | null>(null)

const triggerUpload = () => {
  uploadInputRef.value?.click()
}

const handleFileInputChange = async (e: Event) => {
  const target = e.target as HTMLInputElement
  const file = target.files?.[0]
  if (!file || !selectedBundle.value) return
  await workspace.uploadExternalCommand(file, '.')
  target.value = ''
}

// ─── 文件包列表右键菜单（重命名/删除） ───────────────────────────────────────

const ctxMenu = ref({ visible: false, x: 0, y: 0, bundle: null as FileBundleListItem | null })

const showCtxMenu = (e: MouseEvent, bundle: FileBundleListItem) => {
  e.preventDefault()
  ctxMenu.value = { visible: true, x: e.clientX, y: e.clientY, bundle }
}

const hideCtxMenu = () => {
  ctxMenu.value.visible = false
}

onBeforeUnmount(() => document.removeEventListener('click', hideCtxMenu))
nextTick(() => document.addEventListener('click', hideCtxMenu))

// ─── 重命名文件包 ─────────────────────────────────────────────────────────────

const renameDialogVisible = ref(false)
const renameBundleId = ref<number | null>(null)
const renameInput = ref('')

const handleRename = (bundle: FileBundleListItem) => {
  hideCtxMenu()
  renameBundleId.value = bundle.bundle_id
  renameInput.value = bundle.name
  renameDialogVisible.value = true
}

const submitRename = async () => {
  if (!renameBundleId.value || !renameInput.value.trim()) return
  try {
    const res = await patchFileBundleApi(renameBundleId.value, { name: renameInput.value.trim() })
    ElMessage.success('重命名成功')
    if (res.data?.affected_versions?.length) {
      ElMessage.info(
        `此更改影响 ${res.data.affected_versions.length} 个版本的文件包关联名称（bundle_id 不变）`
      )
    }
    renameDialogVisible.value = false
    await fetchBundles()
  } catch (e: any) {
    ElMessage.error('重命名失败：' + (e?.response?.data?.detail || ''))
  }
}

// ─── 删除文件包 ──────────────────────────────────────────────────────────────

const handleDeleteBundle = async (bundle: FileBundleListItem) => {
  hideCtxMenu()
  await ElMessageBox.confirm(
    `确认删除文件包「${bundle.name}」吗？若有版本正在引用此文件包将无法删除。`,
    '删除确认',
    { confirmButtonText: '确认删除', cancelButtonText: '取消', type: 'warning' }
  )
  try {
    await deleteFileBundleApi(bundle.bundle_id)
    ElMessage.success('文件包已删除')
    if (selectedBundle.value?.bundle_id === bundle.bundle_id) {
      selectedBundle.value = null
      viewMode.value = 'list'
    }
    await fetchBundles()
  } catch (e: any) {
    const detail = e?.response?.data?.detail
    if (detail === 'BUNDLE_IN_USE') {
      ElMessage.error('该文件包被版本引用，请先解除关联后再删除')
    } else {
      ElMessage.error('删除失败：' + (detail || ''))
    }
  }
}

// ─── 新建文件包 ──────────────────────────────────────────────────────────────

const createDialogVisible = ref(false)
const createName = ref('')

const openCreateDialog = () => {
  createName.value = ''
  createDialogVisible.value = true
}

const submitCreateBundle = async () => {
  if (!createName.value.trim()) {
    ElMessage.warning('请输入文件包名称')
    return
  }
  try {
    await createFileBundleApi({ name: createName.value.trim() })
    ElMessage.success('文件包创建成功')
    createDialogVisible.value = false
    await fetchBundles()
  } catch (e: any) {
    ElMessage.error('创建失败：' + (e?.response?.data?.detail || ''))
  }
}

// ─── 工具函数 ─────────────────────────────────────────────────────────────────

const formatSize = (bytes: number) => {
  if (bytes < 1024) return `${bytes} B`
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`
  return `${(bytes / 1024 / 1024).toFixed(1)} MB`
}

// ─── 语言检测 ─────────────────────────────────────────────────────────────────

const detectLanguage = (path: string) => {
  if (path.endsWith('.py')) return 'python'
  if (path.endsWith('.launch')) return 'xml'
  if (path.endsWith('.yaml') || path.endsWith('.yml')) return 'yaml'
  if (path.endsWith('.sh')) return 'shell'
  if (path.endsWith('.json')) return 'json'
  if (path.endsWith('.cpp') || path.endsWith('.c') || path.endsWith('.h')) return 'cpp'
  return 'plaintext'
}
</script>

<template>
  <ContentWrap>
    <!-- 页面标题栏 -->
    <div class="mb-16px flex items-center justify-between">
      <div class="text-18px font-600">实验文件管理</div>
      <ElButton v-if="viewMode === 'list'" type="primary" @click="openCreateDialog">
        + 新建文件包
      </ElButton>
    </div>

    <!-- 主体：左右分栏 -->
    <div class="exp-files-layout">
      <!-- ─── 左侧面板 ─── -->
      <div class="exp-files-left">
        <!-- 状态 A：文件包列表视图 -->
        <template v-if="viewMode === 'list'">
          <ElSkeleton v-if="bundlesLoading" :rows="5" animated class="pa-12px" />
          <template v-else>
            <div v-if="bundles.length === 0" class="empty-hint">
              <ElEmpty description="暂无文件包">
                <template #description>
                  <div class="text-14px color-#606266">
                    暂无文件包。<br />
                    点击右上角「新建文件包」创建，<br />
                    然后<strong>双击</strong>进入文件树编辑。
                  </div>
                </template>
              </ElEmpty>
            </div>
            <div v-else class="bundle-hint text-12px color-#909399 mb-8px">
              💡 单击选中，<strong>双击</strong>进入文件树 | 右键可重命名/删除
            </div>
            <ElScrollbar class="bundle-list-scroll">
              <div
                v-for="bundle in bundles"
                :key="bundle.bundle_id"
                :class="[
                  'bundle-item',
                  selectedBundle?.bundle_id === bundle.bundle_id && 'bundle-item--selected'
                ]"
                @click="handleBundleClick(bundle)"
                @dblclick="handleBundleDblClick(bundle)"
                @contextmenu="showCtxMenu($event, bundle)"
              >
                <span class="bundle-item__icon">📦</span>
                <div class="bundle-item__info">
                  <div class="bundle-item__name">{{ bundle.name }}</div>
                  <div class="bundle-item__meta">
                    {{ bundle.file_count }} 个文件 · {{ formatSize(bundle.total_size_bytes) }}
                  </div>
                </div>
              </div>
            </ElScrollbar>
          </template>
        </template>

        <!-- 状态 B：文件树视图 — 完整复用 FileTree.vue（含右键菜单） -->
        <template v-if="viewMode === 'tree'">
          <div class="tree-header">
            <ElButton link @click="handleBackToList">← 返回列表</ElButton>
            <div class="tree-header__name">{{ selectedBundle?.name }}</div>
            <ElTooltip content="上传文件">
              <ElButton link type="primary" @click="triggerUpload">↑ 上传</ElButton>
            </ElTooltip>
            <input
              ref="uploadInputRef"
              type="file"
              style="display: none"
              @change="handleFileInputChange"
            />
          </div>
          <!-- FileTree.vue：与学生端完全一致，自带右键菜单 -->
          <div class="file-tree-wrap">
            <FileTree
              :tree-data="workspace.treeData.value"
              :loading="workspace.loading.value"
              :workspace="workspace"
              @select-file="handleSelectFile"
              @upload="(file, targetPath) => workspace.uploadExternalCommand(file, targetPath)"
            />
          </div>
        </template>
      </div>

      <!-- ─── 右侧面板 ─── -->
      <div class="exp-files-right">
        <!-- 未进入文件树时的提示 -->
        <div v-if="viewMode === 'list'" class="right-placeholder">
          <div v-if="!selectedBundle" class="color-#bbb text-14px">请先选择一个文件包</div>
          <div v-else class="bundle-summary">
            <div class="bundle-summary__name">📦 {{ selectedBundle.name }}</div>
            <div class="bundle-summary__meta">
              <ElTag type="info">{{ selectedBundle.file_count }} 个文件</ElTag>
              <ElTag type="info" class="ml-8px">{{
                formatSize(selectedBundle.total_size_bytes)
              }}</ElTag>
            </div>
            <div class="mt-16px color-#909399 text-13px">双击文件包名称可进入文件树编辑</div>
          </div>
        </div>

        <!-- 已进入文件树：Monaco 编辑器 -->
        <div v-else class="editor-area">
          <div v-if="!openedFilePath" class="editor-placeholder">
            点击左侧文件树中的文件以打开编辑
          </div>
          <template v-else>
            <div class="editor-toolbar">
              <span class="editor-toolbar__path">📄 {{ openedFilePath }}</span>
              <ElTag v-if="hasUnsavedChanges" type="warning" size="small">未保存</ElTag>
              <ElButton type="primary" size="small" @click="handleSave">保存</ElButton>
            </div>
            <div class="editor-body">
              <MonacoEditor v-model="editorContent" :language="detectLanguage(openedFilePath)" />
            </div>
          </template>
        </div>
      </div>
    </div>

    <!-- 状态栏 -->
    <div class="exp-files-statusbar">
      <template v-if="viewMode === 'list'">共 {{ bundles.length }} 个文件包</template>
      <template v-else>
        {{ selectedBundle?.name }} | 文件数：{{ workspace.treeData.value.length }}
        <span v-if="openedFilePath"> | 当前文件：{{ openedFilePath }}</span>
      </template>
    </div>
  </ContentWrap>

  <!-- 文件包列表右键菜单（仅在列表视图显示） -->
  <div
    v-if="ctxMenu.visible"
    class="ctx-menu"
    :style="{ left: ctxMenu.x + 'px', top: ctxMenu.y + 'px' }"
  >
    <div class="ctx-menu__item" @click="handleRename(ctxMenu.bundle!)">重命名</div>
    <div class="ctx-menu__item ctx-menu__item--danger" @click="handleDeleteBundle(ctxMenu.bundle!)">
      删除
    </div>
  </div>

  <!-- 新建文件包对话框 -->
  <ElDialog v-model="createDialogVisible" title="新建文件包" width="420px">
    <ElForm label-width="90px">
      <ElFormItem label="文件包名称" required>
        <ElInput
          v-model="createName"
          placeholder="例如：导航实验包"
          @keyup.enter="submitCreateBundle"
        />
      </ElFormItem>
    </ElForm>
    <template #footer>
      <ElButton @click="createDialogVisible = false">取消</ElButton>
      <ElButton type="primary" @click="submitCreateBundle">创建</ElButton>
    </template>
  </ElDialog>

  <!-- 重命名文件包对话框 -->
  <ElDialog v-model="renameDialogVisible" title="重命名文件包" width="420px">
    <ElForm label-width="90px">
      <ElFormItem label="新名称" required>
        <ElInput v-model="renameInput" placeholder="输入新名称" @keyup.enter="submitRename" />
      </ElFormItem>
    </ElForm>
    <template #footer>
      <ElButton @click="renameDialogVisible = false">取消</ElButton>
      <ElButton type="primary" @click="submitRename">确认</ElButton>
    </template>
  </ElDialog>
</template>

<style lang="less" scoped>
.exp-files-layout {
  display: grid;
  grid-template-columns: 280px 1fr;
  gap: 12px;
  height: calc(100vh - 260px);
  min-height: 500px;
}

.exp-files-left {
  border: 1px solid var(--el-border-color);
  border-radius: 6px;
  overflow: hidden;
  display: flex;
  flex-direction: column;
  background: var(--el-bg-color);
}

.exp-files-right {
  border: 1px solid var(--el-border-color);
  border-radius: 6px;
  overflow: hidden;
  display: flex;
  flex-direction: column;
  background: var(--el-bg-color);
}

.bundle-list-scroll {
  flex: 1;
}

.bundle-item {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 10px 14px;
  cursor: pointer;
  border-bottom: 1px solid var(--el-border-color-lighter);
  transition: background 0.2s;
  user-select: none;

  &:hover {
    background: var(--el-fill-color-light);
  }

  &--selected {
    background: var(--el-color-primary-light-9);
    border-left: 3px solid var(--el-color-primary);
  }

  &__icon {
    font-size: 20px;
  }

  &__info {
    flex: 1;
    min-width: 0;
  }

  &__name {
    font-size: 14px;
    font-weight: 500;
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
  }

  &__meta {
    font-size: 11px;
    color: var(--el-text-color-secondary);
    margin-top: 2px;
  }
}

.bundle-hint {
  padding: 8px 14px 4px;
}

.empty-hint {
  padding: 40px 20px;
  text-align: center;
}

.tree-header {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 8px 12px;
  border-bottom: 1px solid var(--el-border-color);
  background: var(--el-fill-color-lighter);
  flex-shrink: 0;

  &__name {
    flex: 1;
    font-size: 13px;
    font-weight: 500;
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
  }
}

/* FileTree.vue 需要占满剩余高度 */
.file-tree-wrap {
  flex: 1;
  overflow: hidden;
  position: relative;
}

.right-placeholder {
  display: flex;
  align-items: center;
  justify-content: center;
  height: 100%;
}

.bundle-summary {
  text-align: center;

  &__name {
    font-size: 18px;
    font-weight: 600;
    margin-bottom: 12px;
  }
}

.editor-area {
  display: flex;
  flex-direction: column;
  height: 100%;
}

.editor-placeholder {
  display: flex;
  align-items: center;
  justify-content: center;
  height: 100%;
  color: var(--el-text-color-secondary);
  font-size: 14px;
}

.editor-toolbar {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 8px 12px;
  border-bottom: 1px solid var(--el-border-color);
  background: var(--el-fill-color-lighter);
  flex-shrink: 0;

  &__path {
    flex: 1;
    font-size: 13px;
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
    color: var(--el-text-color-secondary);
  }
}

.editor-body {
  flex: 1;
  overflow: hidden;
}

.exp-files-statusbar {
  margin-top: 8px;
  padding: 6px 12px;
  background: var(--el-fill-color-lighter);
  border-radius: 4px;
  font-size: 12px;
  color: var(--el-text-color-secondary);
}

// 列表视图右键菜单（文件包重命名/删除）
.ctx-menu {
  position: fixed;
  z-index: 9999;
  background: var(--el-bg-color-overlay);
  border: 1px solid var(--el-border-color);
  border-radius: 6px;
  box-shadow: 0 4px 12px rgba(0, 0, 0, 0.15);
  min-width: 120px;
  overflow: hidden;

  &__item {
    padding: 9px 18px;
    font-size: 13px;
    cursor: pointer;
    transition: background 0.15s;

    &:hover {
      background: var(--el-fill-color-light);
    }

    &--danger {
      color: var(--el-color-danger);
    }
  }
}
</style>
