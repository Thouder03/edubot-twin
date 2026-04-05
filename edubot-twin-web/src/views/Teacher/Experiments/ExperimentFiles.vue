<script setup lang="ts">
/**
 * 实验文件管理页 — /teacher/experiments/files
 *
 * 左侧：文件包列表（单击选中 / 双击进入文件树）+ 右键菜单
 * 右侧：EditorWorkbench.vue（完整复用学生端编辑器，含标签页+Ctrl+S）
 *
 * SDD §15.4：文件树和编辑器均完整复用 WorkspacePanel 组件。
 */
import { ContentWrap } from '@/components/ContentWrap'
import FileTree from '@/views/Simulation/panels/WorkspacePanel/FileTree.vue'
import EditorWorkbench from '@/views/Simulation/panels/WorkspacePanel/EditorWorkbench.vue'
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
import { useBundleEditorState } from './composables/useBundleEditorState'
import { useWorkspaceSettings } from '@/composables/useWorkspaceSettings'
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
import { computed, nextTick, onBeforeUnmount, ref, watch } from 'vue'
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

// ─── 文件树（完整复用 FileTree.vue + 右键菜单）────────────────────────────────

const workspace = useBundleWorkspace(fileApiPrefix)

watch(fileApiPrefix, async (newPrefix) => {
  if (newPrefix && viewMode.value === 'tree') {
    await workspace.loadTree()
  }
})

// ─── 编辑器状态（完整复用 EditorWorkbench.vue + 标签页逻辑）─────────────────

const { settings } = useWorkspaceSettings()

const editor = useBundleEditorState(
  // readFn：读取文件内容
  async (path: string) => {
    const res = await readFileBundleFileApi(selectedBundle.value!.bundle_id, path)
    return {
      content: res.data?.content ?? '',
      modifiedAt: res.data?.modified_at !== undefined ? Number(res.data.modified_at) : undefined
    }
  },
  // saveFn：保存文件内容（transparently pass modifiedAt for conflict detection）
  async (path: string, content: string, modifiedAt?: number) => {
    await saveFileBundleFileApi(selectedBundle.value!.bundle_id, path, content, modifiedAt)
    return {}
  }
)

// ─── 单击选中 ─────────────────────────────────────────────────────────────────

const handleBundleClick = (bundle: FileBundleListItem) => {
  selectedBundle.value = bundle
}

// ─── 双击进入文件树 ───────────────────────────────────────────────────────────

const handleBundleDblClick = async (bundle: FileBundleListItem) => {
  if (editor.hasAnyUnsavedChanges()) {
    const ok = await confirmLeave()
    if (!ok) return
  }
  selectedBundle.value = bundle
  viewMode.value = 'tree'
  workspace.clearSelection()
  await workspace.loadTree()
}

// ─── 返回文件包列表 ──────────────────────────────────────────────────────────

const handleBackToList = async () => {
  const ok = await confirmLeave()
  if (!ok) return
  viewMode.value = 'list'
  // 关闭所有标签页并清除缓存
  const allPaths = [
    ...editor.pinnedTabs.value,
    ...(editor.previewPath.value ? [editor.previewPath.value] : [])
  ]
  allPaths.forEach((p) => editor.closeTab(p))
}

// ─── 点击文件树节点 ───────────────────────────────────────────────────────────

const handleSelectFile = async (path: string) => {
  // 目录节点不打开编辑器
  const node = workspace.findNodeByPath(workspace.treeData.value, path)
  if (!node || node.type === 'directory') return
  // 单击 = preview 模式（斜体标签，可被下一次单击替换）
  await editor.openFile(path, true)
}

// ─── 离开确认 ─────────────────────────────────────────────────────────────────

const confirmLeave = async (): Promise<boolean> => {
  const dirtyPaths = editor.getDirtyPaths()
  if (dirtyPaths.length === 0) return true

  const fileNames = dirtyPaths.map((p) => p.split('/').pop()).join('、')
  try {
    const action = await ElMessageBox.confirm(
      `以下文件有未保存的修改：${fileNames}，是否保存后继续？`,
      '未保存修改',
      {
        confirmButtonText: '全部保存后继续',
        cancelButtonText: '放弃修改并继续',
        distinguishCancelAndClose: true,
        type: 'warning'
      }
    )
    if (action === 'confirm') {
      for (const path of dirtyPaths) {
        const cached = editor.fileCache[path]
        const content = cached?.content ?? ''
        await saveFileBundleFileApi(
          selectedBundle.value!.bundle_id,
          path,
          content,
          cached?.modifiedAt
        )
      }
    }
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
const triggerUpload = () => uploadInputRef.value?.click()
const handleFileInputChange = async (e: Event) => {
  const target = e.target as HTMLInputElement
  const file = target.files?.[0]
  if (!file) return
  await workspace.uploadExternalCommand(file, '.')
  target.value = ''
}

// ─── 文件包列表右键菜单 ──────────────────────────────────────────────────────

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
      ElMessage.info(`此更改影响 ${res.data.affected_versions.length} 个版本的关联`)
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
    ElMessage.error(
      detail === 'BUNDLE_IN_USE'
        ? '该文件包被版本引用，请先解除关联后再删除'
        : '删除失败：' + (detail || '')
    )
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
            <template v-else>
              <div class="bundle-hint text-12px color-#909399">
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
        </template>

        <!-- 状态 B：文件树视图 -->
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

      <!-- ─── 右侧面板：EditorWorkbench（完整复用学生端编辑器）─── -->
      <div class="exp-files-right">
        <!-- 列表视图：摘要 -->
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

        <!-- 文件树视图：EditorWorkbench（标签页 + Ctrl+S 快捷键） -->
        <EditorWorkbench
          v-else
          :preview-path="editor.previewPath.value"
          :active-path="editor.activePath.value"
          :pinned-tabs="editor.pinnedTabs.value"
          :file-cache="editor.fileCache"
          :dirty-map="editor.dirtyMap"
          :settings="settings"
          @content-change="editor.handleContentChange($event)"
          @save="editor.saveActiveFile($event)"
          @select-tab="editor.handleSelectTab($event, false)"
          @close-tab="editor.closeTab($event)"
        />
      </div>
    </div>

    <!-- 状态栏 -->
    <div class="exp-files-statusbar">
      <template v-if="viewMode === 'list'">共 {{ bundles.length }} 个文件包</template>
      <template v-else>
        {{ selectedBundle?.name }}
        <span v-if="editor.activePath.value"> | 当前文件：{{ editor.activePath.value }}</span>
        <span v-if="editor.getDirtyPaths().length > 0" class="statusbar-dirty">
          ● {{ editor.getDirtyPaths().length }} 个文件未保存
        </span>
      </template>
    </div>
  </ContentWrap>

  <!-- 文件包列表右键菜单 -->
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

  <!-- 新建文件包 -->
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

  <!-- 重命名文件包 -->
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

.exp-files-statusbar {
  margin-top: 8px;
  padding: 6px 12px;
  background: var(--el-fill-color-lighter);
  border-radius: 4px;
  font-size: 12px;
  color: var(--el-text-color-secondary);
}

.statusbar-dirty {
  color: var(--el-color-warning);
  margin-left: 8px;
}

// 文件包列表右键菜单
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
