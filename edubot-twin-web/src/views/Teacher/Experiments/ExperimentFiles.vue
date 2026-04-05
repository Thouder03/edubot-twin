<script setup lang="ts">
/**
 * 实验文件管理页 — /teacher/experiments/files
 *
 * 左侧：文件包列表（单击选中 / 双击进入文件树）+ 右键菜单 重命名/删除
 * 右侧：Monaco 编辑器（点击文件树中的文件打开编辑）
 *
 * 状态 A：文件包列表视图（初始状态）
 * 状态 B：文件树视图（双击进入后，顶部有「← 返回列表」）
 */
import { ContentWrap } from '@/components/ContentWrap'
import MonacoEditor from '@/components/Monaco/MonacoEditor.vue'
import {
  createFileBundleApi,
  deleteFileBundleApi,
  getFileBundleListApi,
  patchFileBundleApi
} from '@/api/experiment'
import type { BundleFileItem, FileBundleListItem } from '@/api/experiment/types'
import { useFileOperations } from '@/composables/useFileOperations'
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

// ─── 单击选中 ─────────────────────────────────────────────────────────────────

const handleBundleClick = (bundle: FileBundleListItem) => {
  selectedBundle.value = bundle
}

// ─── 双击进入文件树 ───────────────────────────────────────────────────────────

const fileApiPrefix = computed(() =>
  selectedBundle.value
    ? `/api/v1/teachers/file-bundles/${selectedBundle.value.bundle_id}/files`
    : ''
)

const {
  fileList,
  loading: fileLoading,
  fileContent,
  openedFilePath,
  hasUnsavedChanges,
  listFiles,
  readFile,
  saveFile,
  deleteFile,
  confirmLeave
} = useFileOperations(fileApiPrefix)

const handleBundleDblClick = async (bundle: FileBundleListItem) => {
  selectedBundle.value = bundle
  viewMode.value = 'tree'
  await listFiles()
}

// ─── 返回文件包列表 ──────────────────────────────────────────────────────────

const handleBackToList = async () => {
  const ok = await confirmLeave()
  if (!ok) return
  viewMode.value = 'list'
  openedFilePath.value = undefined
  fileContent.value = ''
}

// ─── 文件树交互 ───────────────────────────────────────────────────────────────

const treeFileList = ref<BundleFileItem[]>([])

watch(fileList, (val) => {
  treeFileList.value = val
})

const handleFileClick = async (item: BundleFileItem) => {
  if (item.type === 'dir') return
  const ok = await confirmLeave()
  if (!ok) return
  const path = item.name
  await readFile(path)
}

const handleDeleteFile = (item: BundleFileItem) => {
  deleteFile(item.name).then(() => listFiles())
}

// ─── 编辑器 ──────────────────────────────────────────────────────────────────

const editorContent = computed({
  get: () => fileContent.value,
  set: (val) => {
    fileContent.value = val
    hasUnsavedChanges.value = true
  }
})

const handleSave = async () => {
  if (!openedFilePath.value) return
  await saveFile(openedFilePath.value, fileContent.value)
}

// ─── 上传 ─────────────────────────────────────────────────────────────────────

const uploadInputRef = ref<HTMLInputElement | null>(null)

const triggerUpload = () => {
  uploadInputRef.value?.click()
}

const handleFileInputChange = async (e: Event) => {
  const target = e.target as HTMLInputElement
  const file = target.files?.[0]
  if (!file || !selectedBundle.value) return

  const formData = new FormData()
  formData.append('file', file)
  try {
    const res = await fetch(
      `/api/v1/teachers/file-bundles/${selectedBundle.value.bundle_id}/files/upload`,
      {
        method: 'POST',
        body: formData,
        headers: { Authorization: `Bearer ${localStorage.getItem('token') ?? ''}` }
      }
    )
    if (res.ok) {
      ElMessage.success(`"${file.name}" 上传成功`)
      await listFiles()
    } else {
      ElMessage.error('上传失败')
    }
  } catch {
    ElMessage.error('上传失败')
  } finally {
    target.value = ''
  }
}

// ─── 右键菜单 ─────────────────────────────────────────────────────────────────

const ctxMenu = ref({ visible: false, x: 0, y: 0, bundle: null as FileBundleListItem | null })

const showCtxMenu = (e: MouseEvent, bundle: FileBundleListItem) => {
  e.preventDefault()
  ctxMenu.value = { visible: true, x: e.clientX, y: e.clientY, bundle }
}

const hideCtxMenu = () => {
  ctxMenu.value.visible = false
}

// 使用全局点击关闭菜单
onBeforeUnmount(() => document.removeEventListener('click', hideCtxMenu))
nextTick(() => document.addEventListener('click', hideCtxMenu))

// ─── 重命名 ──────────────────────────────────────────────────────────────────

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

// ─── 路由离开前确认 ───────────────────────────────────────────────────────────

onBeforeRouteLeave(async (_to, _from, next) => {
  const ok = await confirmLeave()
  next(ok ? undefined : false)
})

// ─── 文件大小格式化 ──────────────────────────────────────────────────────────

const formatSize = (bytes: number) => {
  if (bytes < 1024) return `${bytes} B`
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`
  return `${(bytes / 1024 / 1024).toFixed(1)} MB`
}

const getFileIcon = (item: BundleFileItem) => {
  if (item.type === 'dir') return '📁'
  const ext = item.name.split('.').pop() ?? ''
  const map: Record<string, string> = {
    py: '🐍',
    launch: '🚀',
    yaml: '📋',
    yml: '📋',
    sh: '⚙️',
    md: '📝',
    txt: '📄',
    json: '{}',
    cpp: '⚡',
    c: '⚡',
    h: '📎',
    zip: '🗜️',
    tar: '🗜️',
    gz: '🗜️'
  }
  return map[ext] ?? '📄'
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
          <ElSkeleton v-if="bundlesLoading" :rows="5" animated />
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
              💡 单击选中，<strong>双击</strong>进入文件树
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
          <ElScrollbar class="file-tree-scroll">
            <div v-if="fileLoading" class="pa-16px">
              <ElSkeleton :rows="4" animated />
            </div>
            <div v-else-if="treeFileList.length === 0" class="pa-16px text-center color-#909399">
              文件包为空，请上传文件
            </div>
            <div v-else>
              <div
                v-for="item in treeFileList"
                :key="item.name"
                :class="[
                  'file-tree-item',
                  openedFilePath === item.name && 'file-tree-item--active',
                  item.type === 'dir' && 'file-tree-item--dir'
                ]"
                @click="handleFileClick(item)"
              >
                <span class="file-tree-item__icon">{{ getFileIcon(item) }}</span>
                <span class="file-tree-item__name">{{ item.name }}</span>
                <ElButton
                  v-if="item.type === 'file'"
                  link
                  type="danger"
                  size="small"
                  class="file-tree-item__del"
                  @click.stop="handleDeleteFile(item)"
                >
                  删除
                </ElButton>
              </div>
            </div>
          </ElScrollbar>
        </template>
      </div>

      <!-- ─── 右侧面板 ─── -->
      <div class="exp-files-right">
        <!-- 未进入文件树时的提示 -->
        <div v-if="viewMode === 'list'" class="right-placeholder">
          <div v-if="!selectedBundle" class="color-#bbb text-14px"> 请先选择一个文件包 </div>
          <div v-else class="bundle-summary">
            <div class="bundle-summary__name">📦 {{ selectedBundle.name }}</div>
            <div class="bundle-summary__meta">
              <ElTag type="info">{{ selectedBundle.file_count }} 个文件</ElTag>
              <ElTag type="info" class="ml-8px">
                {{ formatSize(selectedBundle.total_size_bytes) }}
              </ElTag>
            </div>
            <div class="mt-16px color-#909399 text-13px"> 双击文件包名称可进入文件树编辑 </div>
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
              <MonacoEditor
                v-model="editorContent"
                :language="
                  openedFilePath?.endsWith('.py')
                    ? 'python'
                    : openedFilePath?.endsWith('.launch')
                      ? 'xml'
                      : openedFilePath?.endsWith('.yaml') || openedFilePath?.endsWith('.yml')
                        ? 'yaml'
                        : openedFilePath?.endsWith('.sh')
                          ? 'shell'
                          : openedFilePath?.endsWith('.json')
                            ? 'json'
                            : 'plaintext'
                "
              />
            </div>
          </template>
        </div>
      </div>
    </div>

    <!-- 状态栏 -->
    <div class="exp-files-statusbar">
      <template v-if="viewMode === 'list'"> 共 {{ bundles.length }} 个文件包 </template>
      <template v-else>
        {{ selectedBundle?.name }} | 文件数：{{ treeFileList.length }}
        <span v-if="openedFilePath"> | 当前文件：{{ openedFilePath }}</span>
      </template>
    </div>
  </ContentWrap>

  <!-- 右键菜单 -->
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

  <!-- 重命名对话框 -->
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
  grid-template-columns: 260px 1fr;
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

  &__name {
    flex: 1;
    font-size: 13px;
    font-weight: 500;
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
  }
}

.file-tree-scroll {
  flex: 1;
}

.file-tree-item {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 7px 14px;
  cursor: pointer;
  font-size: 13px;
  border-bottom: 1px solid var(--el-border-color-lighter);
  transition: background 0.15s;

  &:hover {
    background: var(--el-fill-color-light);

    .file-tree-item__del {
      opacity: 1;
    }
  }

  &--active {
    background: var(--el-color-primary-light-9);
  }

  &--dir {
    font-weight: 500;
    color: var(--el-color-primary);
  }

  &__icon {
    font-size: 16px;
  }

  &__name {
    flex: 1;
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
  }

  &__del {
    opacity: 0;
    transition: opacity 0.15s;
    flex-shrink: 0;
  }
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

// 右键菜单
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
