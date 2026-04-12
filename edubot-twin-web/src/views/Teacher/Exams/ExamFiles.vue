<script setup lang="ts">
/**
 * 考试文件快照管理页 — /teacher/exams/files
 *
 * 基于 BundleWorkspaceTemplate 的三栏布局：
 *   左侧：快照列表 ↔ 文件树 + 基本设置
 *   右侧：Monaco 编辑器（EditorWorkbench）
 */
import { nextTick, onBeforeUnmount, ref } from 'vue'
import BundleWorkspaceTemplate from './components/BundleWorkspaceTemplate.vue'
import {
  getExamFileSnapshotListApi,
  createExamFileSnapshotApi,
  copyExamFileSnapshotApi,
  deleteExamFileSnapshotApi,
  patchExamFileSnapshotApi
} from '@/api/exam/fileSnapshots'
import { getFileBundleListApi } from '@/api/experiment'
import type { ExamFileSnapshotListItem } from '@/api/exam/types'
import type { FileBundleListItem } from '@/api/experiment/types'
import {
  ElButton,
  ElDialog,
  ElForm,
  ElFormItem,
  ElInput,
  ElMessage,
  ElMessageBox,
  ElOption,
  ElSelect
} from 'element-plus'

// ─── 列表加载 ────────────────────────────────────────────────────────────────

const snapshots = ref<ExamFileSnapshotListItem[]>([])
const listLoading = ref(false)

async function refreshList() {
  listLoading.value = true
  try {
    const res = await getExamFileSnapshotListApi({ page: 1, page_size: 200 })
    snapshots.value = res.data?.items || []
  } finally {
    listLoading.value = false
  }
}

refreshList()

// ─── API 前缀 ────────────────────────────────────────────────────────────────

const buildApiPrefix = (item: ExamFileSnapshotListItem) =>
  `/api/v1/teachers/exam-file-snapshots/${item.id}/files`

// ─── 新建空快照 ─────────────────────────────────────────────────────────────

const createDialogVisible = ref(false)
const createName = ref('')

const openCreateDialog = () => {
  createName.value = ''
  createDialogVisible.value = true
}

const submitCreate = async () => {
  if (!createName.value.trim()) {
    ElMessage.warning('请填写快照名称')
    return
  }
  try {
    await createExamFileSnapshotApi({ name: createName.value.trim() })
    ElMessage.success('快照创建成功')
    createDialogVisible.value = false
    await refreshList()
  } catch (e: unknown) {
    const err = e as { response?: { data?: { detail?: string } } }
    ElMessage.error('创建失败：' + (err?.response?.data?.detail || ''))
  }
}

// ─── 从实验文件包复制 ───────────────────────────────────────────────────────

const copyDialogVisible = ref(false)
const copyForm = ref({ source_file_bundle_id: undefined as number | undefined, name: '' })
const fileBundleOptions = ref<FileBundleListItem[]>([])
const copyLoading = ref(false)

const openCopyDialog = async () => {
  copyForm.value = { source_file_bundle_id: undefined, name: '' }
  copyDialogVisible.value = true
  try {
    const res = await getFileBundleListApi({ page: 1, page_size: 200 })
    fileBundleOptions.value = res.data?.list || []
  } catch {
    ElMessage.error('加载实验文件包列表失败')
  }
}

const submitCopy = async () => {
  if (!copyForm.value.source_file_bundle_id || !copyForm.value.name.trim()) {
    ElMessage.warning('请选择源文件包并填写快照名')
    return
  }
  copyLoading.value = true
  try {
    await copyExamFileSnapshotApi({
      source_file_bundle_id: copyForm.value.source_file_bundle_id,
      name: copyForm.value.name.trim()
    })
    ElMessage.success('快照复制完成')
    copyDialogVisible.value = false
    await refreshList()
  } catch (e: unknown) {
    const err = e as { response?: { data?: { detail?: string } } }
    ElMessage.error('复制失败：' + (err?.response?.data?.detail || ''))
  } finally {
    copyLoading.value = false
  }
}

// ─── 右键菜单 ────────────────────────────────────────────────────────────────

interface CtxMenuState {
  visible: boolean
  x: number
  y: number
  item: ExamFileSnapshotListItem | null
}
const ctxMenu = ref<CtxMenuState>({ visible: false, x: 0, y: 0, item: null })

const showCtxMenu = (e: MouseEvent, item: ExamFileSnapshotListItem) => {
  e.preventDefault()
  ctxMenu.value = { visible: true, x: e.clientX, y: e.clientY, item }
}
const hideCtxMenu = () => {
  ctxMenu.value.visible = false
}
onBeforeUnmount(() => document.removeEventListener('click', hideCtxMenu))
nextTick(() => document.addEventListener('click', hideCtxMenu))

const renameDialogVisible = ref(false)
const renameInput = ref('')
const renameId = ref<number | null>(null)

const handleRename = (item: ExamFileSnapshotListItem) => {
  hideCtxMenu()
  renameId.value = item.id
  renameInput.value = item.name
  renameDialogVisible.value = true
}

const submitRename = async () => {
  if (!renameId.value || !renameInput.value.trim()) return
  try {
    await patchExamFileSnapshotApi(renameId.value, { name: renameInput.value.trim() })
    ElMessage.success('重命名成功')
    renameDialogVisible.value = false
    await refreshList()
  } catch (e: unknown) {
    const err = e as { response?: { data?: { detail?: string } } }
    ElMessage.error('重命名失败：' + (err?.response?.data?.detail || ''))
  }
}

const handleDelete = async (item: ExamFileSnapshotListItem) => {
  hideCtxMenu()
  await ElMessageBox.confirm(`确认删除文件快照「${item.name}」吗？`, '删除确认', {
    type: 'warning'
  })
  try {
    await deleteExamFileSnapshotApi(item.id)
    ElMessage.success('已删除')
    await refreshList()
  } catch (e: unknown) {
    const err = e as { response?: { data?: { detail?: string } } }
    const detail = err?.response?.data?.detail
    if (detail === 'SNAPSHOT_IN_USE') {
      ElMessage.error('该快照被考试引用，请先解除关联')
    } else {
      ElMessage.error('删除失败：' + (detail || ''))
    }
  }
}

function formatSize(bytes: number): string {
  if (bytes < 1024) return bytes + ' B'
  if (bytes < 1024 * 1024) return (bytes / 1024).toFixed(1) + ' KB'
  return (bytes / 1024 / 1024).toFixed(1) + ' MB'
}
</script>

<template>
  <BundleWorkspaceTemplate
    title="考试文件快照"
    :items="snapshots"
    :list-loading="listLoading"
    :build-api-prefix="buildApiPrefix"
    @refresh-list="refreshList"
    @context-menu="showCtxMenu"
  >
    <template #header-extra="{ viewMode }">
      <template v-if="viewMode === 'list'">
        <ElButton type="primary" @click="openCreateDialog">新建空快照</ElButton>
        <ElButton type="success" @click="openCopyDialog">从实验文件复制</ElButton>
      </template>
    </template>

    <template #list-item="{ item }">
      <span class="list-item__icon">📂</span>
      <div class="list-item__info">
        <div class="list-item__name">{{ item.name }}</div>
        <div class="list-item__meta">
          {{ item.file_count }} 文件 · {{ formatSize(item.total_size_bytes) }}
        </div>
      </div>
    </template>

    <template #list-empty>
      <div class="color-#606266 text-14px">
        暂无快照。<br />点击「新建空快照」或「从实验文件复制」创建。
      </div>
    </template>

    <template #settings-panel="{ selectedItem }">
      <ElForm label-position="top" size="small">
        <ElFormItem label="统计">
          <div class="text-12px color-#909399">
            {{ selectedItem?.file_count || 0 }} 个文件 ·
            {{ formatSize(selectedItem?.total_size_bytes || 0) }}
          </div>
        </ElFormItem>
        <ElFormItem label="说明">
          <div class="text-11px color-#909399">
            文件快照没有额外的运行时设置，直接在文件树中编辑即可。
          </div>
        </ElFormItem>
      </ElForm>
    </template>
  </BundleWorkspaceTemplate>

  <!-- 右键菜单 -->
  <div
    v-if="ctxMenu.visible"
    class="ctx-menu"
    :style="{ left: ctxMenu.x + 'px', top: ctxMenu.y + 'px' }"
  >
    <div class="ctx-menu__item" @click="handleRename(ctxMenu.item!)">重命名</div>
    <div class="ctx-menu__item ctx-menu__item--danger" @click="handleDelete(ctxMenu.item!)">
      删除
    </div>
  </div>

  <!-- 新建空快照 -->
  <ElDialog v-model="createDialogVisible" title="新建考试文件快照" width="420px">
    <ElForm label-width="90px">
      <ElFormItem label="快照名称" required>
        <ElInput v-model="createName" placeholder="例如：期中考试文件" />
      </ElFormItem>
    </ElForm>
    <template #footer>
      <ElButton @click="createDialogVisible = false">取消</ElButton>
      <ElButton type="primary" @click="submitCreate">创建</ElButton>
    </template>
  </ElDialog>

  <!-- 从实验文件复制 -->
  <ElDialog v-model="copyDialogVisible" title="从实验文件包复制" width="520px">
    <div class="mb-12px text-13px color-#909399">
      从已有的实验文件包复制全部文件到考试文件快照。复制完成后生命周期独立。
    </div>
    <ElForm label-width="110px">
      <ElFormItem label="源文件包" required>
        <ElSelect
          v-model="copyForm.source_file_bundle_id"
          placeholder="选择实验文件包"
          style="width: 100%"
          filterable
        >
          <ElOption
            v-for="b in fileBundleOptions"
            :key="b.bundle_id"
            :label="`${b.name} (${b.file_count}文件)`"
            :value="b.bundle_id"
          />
        </ElSelect>
      </ElFormItem>
      <ElFormItem label="新快照名" required>
        <ElInput v-model="copyForm.name" placeholder="例如：期中文件快照" />
      </ElFormItem>
    </ElForm>
    <template #footer>
      <ElButton @click="copyDialogVisible = false">取消</ElButton>
      <ElButton type="primary" :loading="copyLoading" @click="submitCopy">开始复制</ElButton>
    </template>
  </ElDialog>

  <!-- 重命名 -->
  <ElDialog v-model="renameDialogVisible" title="重命名快照" width="420px">
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
.list-item__icon {
  font-size: 20px;
  flex-shrink: 0;
}
.list-item__info {
  flex: 1;
  min-width: 0;
}
.list-item__name {
  font-size: 14px;
  font-weight: 500;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.list-item__meta {
  font-size: 11px;
  color: var(--el-text-color-secondary);
  margin-top: 2px;
}

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
