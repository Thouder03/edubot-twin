<script setup lang="ts">
/**
 * 考试环境快照管理页 — /teacher/exams/envs
 *
 * 基于 BundleWorkspaceTemplate 的三栏布局：
 *   左侧：快照列表 ↔ 文件树 + 基本设置
 *   右侧：Monaco 编辑器（EditorWorkbench）
 */
import { nextTick, onBeforeUnmount, ref } from 'vue'
import BundleWorkspaceTemplate from './components/BundleWorkspaceTemplate.vue'
import {
  getExamEnvSnapshotListApi,
  createExamEnvSnapshotApi,
  copyExamEnvSnapshotApi,
  deleteExamEnvSnapshotApi,
  patchExamEnvSnapshotApi
} from '@/api/exam/envSnapshots'
import { getEnvBundleListApi } from '@/api/experiment'
import type { ExamEnvSnapshotListItem } from '@/api/exam/types'
import type { EnvBundleListItem } from '@/api/experiment/types'
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

const snapshots = ref<ExamEnvSnapshotListItem[]>([])
const listLoading = ref(false)

async function refreshList() {
  listLoading.value = true
  try {
    const res = await getExamEnvSnapshotListApi({ page: 1, page_size: 200 })
    snapshots.value = res.data?.items || []
  } finally {
    listLoading.value = false
  }
}

refreshList()

// ─── API 前缀 ────────────────────────────────────────────────────────────────

const buildApiPrefix = (item: ExamEnvSnapshotListItem) =>
  `/api/v1/teachers/exam-env-snapshots/${item.id}/files`

// ─── 基本设置（双向绑定到当前选中项） ───────────────────────────────────────

const settingsForm = ref({ container_target_dir: '/home/ubuntu20/catkin_ws' })
const selectedSnapshot = ref<ExamEnvSnapshotListItem | null>(null)
const savingSettings = ref(false)

function handleSelect(item: ExamEnvSnapshotListItem) {
  selectedSnapshot.value = item
  settingsForm.value.container_target_dir = item.container_target_dir
}

async function handleSaveSettings() {
  if (!selectedSnapshot.value) return
  savingSettings.value = true
  try {
    await patchExamEnvSnapshotApi(selectedSnapshot.value.id, {
      container_target_dir: settingsForm.value.container_target_dir
    })
    ElMessage.success('基本设置已保存')
    await refreshList()
  } catch (e: unknown) {
    const err = e as { response?: { data?: { detail?: string } } }
    ElMessage.error('保存失败：' + (err?.response?.data?.detail || ''))
  } finally {
    savingSettings.value = false
  }
}

// ─── 新建空快照 ─────────────────────────────────────────────────────────────

const createDialogVisible = ref(false)
const createForm = ref({ name: '', container_target_dir: '/home/ubuntu20/catkin_ws' })

const openCreateDialog = () => {
  createForm.value = { name: '', container_target_dir: '/home/ubuntu20/catkin_ws' }
  createDialogVisible.value = true
}

const submitCreate = async () => {
  if (!createForm.value.name.trim()) {
    ElMessage.warning('请填写快照名称')
    return
  }
  try {
    await createExamEnvSnapshotApi({
      name: createForm.value.name.trim(),
      container_target_dir: createForm.value.container_target_dir
    })
    ElMessage.success('快照创建成功')
    createDialogVisible.value = false
    await refreshList()
  } catch (e: unknown) {
    const err = e as { response?: { data?: { detail?: string } } }
    ElMessage.error('创建失败：' + (err?.response?.data?.detail || ''))
  }
}

// ─── 从实验环境复制 ─────────────────────────────────────────────────────────

const copyDialogVisible = ref(false)
const copyForm = ref({ source_env_bundle_id: undefined as number | undefined, name: '' })
const envBundleOptions = ref<EnvBundleListItem[]>([])
const copyLoading = ref(false)

const openCopyDialog = async () => {
  copyForm.value = { source_env_bundle_id: undefined, name: '' }
  copyDialogVisible.value = true
  try {
    const res = await getEnvBundleListApi({ page: 1, page_size: 200 })
    envBundleOptions.value = res.data?.list || []
  } catch {
    ElMessage.error('加载实验环境列表失败')
  }
}

const submitCopy = async () => {
  if (!copyForm.value.source_env_bundle_id || !copyForm.value.name.trim()) {
    ElMessage.warning('请选择源环境包并填写快照名')
    return
  }
  copyLoading.value = true
  try {
    await copyExamEnvSnapshotApi({
      source_env_bundle_id: copyForm.value.source_env_bundle_id,
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

// ─── 右键菜单：重命名 / 删除 ────────────────────────────────────────────────

interface CtxMenuState {
  visible: boolean
  x: number
  y: number
  item: ExamEnvSnapshotListItem | null
}
const ctxMenu = ref<CtxMenuState>({ visible: false, x: 0, y: 0, item: null })

const showCtxMenu = (e: MouseEvent, item: ExamEnvSnapshotListItem) => {
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

const handleRename = (item: ExamEnvSnapshotListItem) => {
  hideCtxMenu()
  renameId.value = item.id
  renameInput.value = item.name
  renameDialogVisible.value = true
}

const submitRename = async () => {
  if (!renameId.value || !renameInput.value.trim()) return
  try {
    await patchExamEnvSnapshotApi(renameId.value, { name: renameInput.value.trim() })
    ElMessage.success('重命名成功')
    renameDialogVisible.value = false
    await refreshList()
  } catch (e: unknown) {
    const err = e as { response?: { data?: { detail?: string } } }
    ElMessage.error('重命名失败：' + (err?.response?.data?.detail || ''))
  }
}

const handleDelete = async (item: ExamEnvSnapshotListItem) => {
  hideCtxMenu()
  await ElMessageBox.confirm(`确认删除环境快照「${item.name}」吗？`, '删除确认', {
    type: 'warning'
  })
  try {
    await deleteExamEnvSnapshotApi(item.id)
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
    title="考试环境快照"
    :items="snapshots"
    :list-loading="listLoading"
    :build-api-prefix="buildApiPrefix"
    @refresh-list="refreshList"
    @select="handleSelect"
    @context-menu="showCtxMenu"
  >
    <!-- 标题栏右侧按钮 -->
    <template #header-extra="{ viewMode }">
      <template v-if="viewMode === 'list'">
        <ElButton type="primary" @click="openCreateDialog">新建空快照</ElButton>
        <ElButton type="success" @click="openCopyDialog">从实验环境复制</ElButton>
      </template>
    </template>

    <!-- 列表行自定义渲染 -->
    <template #list-item="{ item }">
      <span class="list-item__icon">🗂️</span>
      <div class="list-item__info">
        <div class="list-item__name">{{ item.name }}</div>
        <div class="list-item__meta">
          {{ item.container_target_dir }} · {{ item.file_count }} 文件 ·
          {{ formatSize(item.total_size_bytes) }}
        </div>
      </div>
    </template>

    <!-- 空列表 -->
    <template #list-empty>
      <div class="color-#606266 text-14px">
        暂无快照。<br />点击「新建空快照」或「从实验环境复制」创建，<br />
        然后<strong>双击</strong>进入文件树编辑。
      </div>
    </template>

    <!-- 基本设置面板 -->
    <template #settings-panel="{ selectedItem }">
      <ElForm :model="settingsForm" label-position="top" size="small">
        <ElFormItem label="容器挂载目录">
          <ElInput
            v-model="settingsForm.container_target_dir"
            placeholder="/home/ubuntu20/catkin_ws"
          />
        </ElFormItem>
        <ElFormItem label="统计">
          <div class="text-12px color-#909399">
            {{ selectedItem?.file_count || 0 }} 个文件 ·
            {{ formatSize(selectedItem?.total_size_bytes || 0) }}
          </div>
        </ElFormItem>
        <ElFormItem>
          <ElButton
            type="primary"
            size="small"
            :loading="savingSettings"
            @click="handleSaveSettings"
          >
            保存设置
          </ElButton>
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
  <ElDialog v-model="createDialogVisible" title="新建考试环境快照" width="480px">
    <ElForm label-width="110px">
      <ElFormItem label="快照名称" required>
        <ElInput v-model="createForm.name" placeholder="例如：期中考试环境" />
      </ElFormItem>
      <ElFormItem label="挂载目录">
        <ElInput v-model="createForm.container_target_dir" placeholder="/home/ubuntu20/catkin_ws" />
      </ElFormItem>
    </ElForm>
    <template #footer>
      <ElButton @click="createDialogVisible = false">取消</ElButton>
      <ElButton type="primary" @click="submitCreate">创建</ElButton>
    </template>
  </ElDialog>

  <!-- 从实验环境复制 -->
  <ElDialog v-model="copyDialogVisible" title="从实验环境复制" width="520px">
    <div class="mb-12px text-13px color-#909399">
      从已有的实验环境包复制全部文件到考试环境快照。复制完成后生命周期独立。
    </div>
    <ElForm label-width="110px">
      <ElFormItem label="源环境包" required>
        <ElSelect
          v-model="copyForm.source_env_bundle_id"
          placeholder="选择实验环境包"
          style="width: 100%"
          filterable
        >
          <ElOption
            v-for="b in envBundleOptions"
            :key="b.env_bundle_id"
            :label="b.name"
            :value="b.env_bundle_id"
          />
        </ElSelect>
      </ElFormItem>
      <ElFormItem label="新快照名" required>
        <ElInput v-model="copyForm.name" placeholder="例如：期中环境快照" />
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
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
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
