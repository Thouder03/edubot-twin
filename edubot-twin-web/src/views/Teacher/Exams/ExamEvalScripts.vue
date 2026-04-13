<script setup lang="ts">
/**
 * 测评脚本包管理页 — /teacher/exams/eval-scripts
 *
 * 基于 BundleWorkspaceTemplate 的三栏布局：
 *   左侧：脚本包列表 ↔ 文件树 + 基本设置（entry_point、description）
 *   右侧：Monaco 编辑器（EditorWorkbench）
 *
 * 注意：保存/上传脚本文件后 validate_status 会自动更新（后端根据 entry_point
 * 是否存在自动刷新），因此 refreshListOnSave = true。
 */
import { nextTick, onBeforeUnmount, ref } from 'vue'
import BundleWorkspaceTemplate from './components/BundleWorkspaceTemplate.vue'
import {
  getExamEvalScriptListApi,
  createExamEvalScriptApi,
  deleteExamEvalScriptApi,
  patchExamEvalScriptApi
} from '@/api/exam/evalScripts'
import type { ExamEvalScriptListItem, EvalScriptValidateStatus } from '@/api/exam/types'
import {
  ElButton,
  ElDialog,
  ElForm,
  ElFormItem,
  ElInput,
  ElMessage,
  ElMessageBox,
  ElTag
} from 'element-plus'

const validateStatusMap: Record<
  EvalScriptValidateStatus,
  { label: string; type: '' | 'success' | 'warning' | 'danger' | 'info' }
> = {
  pending: { label: '待验证', type: 'info' },
  valid: { label: '✓ 有效', type: 'success' },
  invalid: { label: '✗ 无效', type: 'danger' }
}

// ─── 列表加载 ────────────────────────────────────────────────────────────────

const scripts = ref<ExamEvalScriptListItem[]>([])
const listLoading = ref(false)

async function refreshList() {
  listLoading.value = true
  try {
    const res = await getExamEvalScriptListApi({ page: 1, page_size: 200 })
    scripts.value = res.data?.items || []
    // 同步设置表单到当前选中项的最新数据
    if (selectedScript.value) {
      const updated = scripts.value.find((s) => s.id === selectedScript.value!.id)
      if (updated) {
        selectedScript.value = updated
        settingsForm.value.entry_point = updated.entry_point
        settingsForm.value.description = updated.description || ''
      }
    }
  } finally {
    listLoading.value = false
  }
}

refreshList()

// ─── API 前缀 ────────────────────────────────────────────────────────────────

const buildApiPrefix = (item: ExamEvalScriptListItem) =>
  `/api/v1/teachers/exam-eval-scripts/${item.id}/files`

// ─── 设置表单（entry_point + description） ──────────────────────────────────

const selectedScript = ref<ExamEvalScriptListItem | null>(null)
const settingsForm = ref({ entry_point: 'evaluate.sh', description: '' })
const savingSettings = ref(false)

function handleSelect(item: ExamEvalScriptListItem) {
  selectedScript.value = item
  settingsForm.value.entry_point = item.entry_point
  settingsForm.value.description = item.description || ''
}

async function handleSaveSettings() {
  if (!selectedScript.value) return
  savingSettings.value = true
  try {
    await patchExamEvalScriptApi(selectedScript.value.id, {
      entry_point: settingsForm.value.entry_point.trim() || 'evaluate.sh',
      description: settingsForm.value.description.trim() || undefined
    })
    ElMessage.success('基本设置已保存，已重新校验入口文件')
    await refreshList()
  } catch (e: unknown) {
    const err = e as { response?: { data?: { detail?: string } } }
    ElMessage.error('保存失败：' + (err?.response?.data?.detail || ''))
  } finally {
    savingSettings.value = false
  }
}

// ─── 新建脚本包 ─────────────────────────────────────────────────────────────

const createDialogVisible = ref(false)
const createForm = ref({ name: '', description: '', entry_point: 'evaluate.sh' })

const openCreateDialog = () => {
  createForm.value = { name: '', description: '', entry_point: 'evaluate.sh' }
  createDialogVisible.value = true
}

const submitCreate = async () => {
  if (!createForm.value.name.trim()) {
    ElMessage.warning('请填写脚本包名称')
    return
  }
  try {
    await createExamEvalScriptApi({
      name: createForm.value.name.trim(),
      description: createForm.value.description.trim() || undefined,
      entry_point: createForm.value.entry_point.trim() || 'evaluate.sh'
    })
    ElMessage.success('脚本包创建成功，请上传脚本文件')
    createDialogVisible.value = false
    await refreshList()
  } catch (e: unknown) {
    const err = e as { response?: { data?: { detail?: string } } }
    ElMessage.error('创建失败：' + (err?.response?.data?.detail || ''))
  }
}

// ─── 右键菜单 ────────────────────────────────────────────────────────────────

interface CtxMenuState {
  visible: boolean
  x: number
  y: number
  item: ExamEvalScriptListItem | null
}
const ctxMenu = ref<CtxMenuState>({ visible: false, x: 0, y: 0, item: null })

const showCtxMenu = (e: MouseEvent, item: ExamEvalScriptListItem) => {
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

const handleRename = (item: ExamEvalScriptListItem) => {
  hideCtxMenu()
  renameId.value = item.id
  renameInput.value = item.name
  renameDialogVisible.value = true
}

const submitRename = async () => {
  if (!renameId.value || !renameInput.value.trim()) return
  try {
    await patchExamEvalScriptApi(renameId.value, { name: renameInput.value.trim() })
    ElMessage.success('重命名成功')
    renameDialogVisible.value = false
    await refreshList()
  } catch (e: unknown) {
    const err = e as { response?: { data?: { detail?: string } } }
    ElMessage.error('重命名失败：' + (err?.response?.data?.detail || ''))
  }
}

const handleDelete = async (item: ExamEvalScriptListItem) => {
  hideCtxMenu()
  await ElMessageBox.confirm(`确认删除脚本包「${item.name}」吗？`, '删除确认', {
    type: 'warning'
  })
  try {
    await deleteExamEvalScriptApi(item.id)
    ElMessage.success('已删除')
    await refreshList()
  } catch (e: unknown) {
    const err = e as { response?: { data?: { detail?: string } } }
    const detail = err?.response?.data?.detail
    if (detail === 'SNAPSHOT_IN_USE') {
      ElMessage.error('该脚本被考试引用，请先解除关联')
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
    title="测评脚本管理"
    :items="scripts"
    :list-loading="listLoading"
    :build-api-prefix="buildApiPrefix"
    :refresh-list-on-save="true"
    @refresh-list="refreshList"
    @select="handleSelect"
    @context-menu="showCtxMenu"
  >
    <template #header-extra="{ viewMode }">
      <ElButton v-if="viewMode === 'list'" type="primary" @click="openCreateDialog">
        新建脚本包
      </ElButton>
    </template>

    <template #list-item="{ item }">
      <span class="list-item__icon">🧪</span>
      <div class="list-item__info">
        <div class="list-item__name-line">
          <span class="list-item__name">{{ item.name }}</span>
          <ElTag :type="validateStatusMap[item.validate_status]?.type || 'info'" size="small">
            {{ validateStatusMap[item.validate_status]?.label || item.validate_status }}
          </ElTag>
        </div>
        <div class="list-item__meta">
          入口：{{ item.entry_point }} · {{ item.file_count }} 文件 ·
          {{ formatSize(item.total_size_bytes) }}
        </div>
      </div>
    </template>

    <template #list-empty>
      <div class="color-#606266 text-14px">
        暂无脚本包。<br />点击「新建脚本包」创建，<br />
        然后<strong>双击</strong>进入文件树编辑。
      </div>
    </template>

    <template #settings-panel="{ selectedItem }">
      <ElForm :model="settingsForm" label-position="top" size="small">
        <ElFormItem label="入口文件 (entry_point)">
          <ElInput v-model="settingsForm.entry_point" placeholder="evaluate.sh" />
        </ElFormItem>
        <ElFormItem label="描述">
          <ElInput
            v-model="settingsForm.description"
            type="textarea"
            :rows="2"
            placeholder="（可选）"
          />
        </ElFormItem>
        <ElFormItem label="校验状态">
          <ElTag
            v-if="selectedItem"
            :type="validateStatusMap[selectedItem.validate_status]?.type || 'info'"
            size="small"
          >
            {{
              validateStatusMap[selectedItem.validate_status]?.label || selectedItem.validate_status
            }}
          </ElTag>
          <div class="mt-4px text-11px color-#909399">
            保存入口或上传文件后系统将自动重新校验。
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

  <!-- 新建脚本包 -->
  <ElDialog v-model="createDialogVisible" title="新建测评脚本包" width="480px">
    <ElForm label-width="90px">
      <ElFormItem label="名称" required>
        <ElInput v-model="createForm.name" placeholder="例如：导航评测脚本" />
      </ElFormItem>
      <ElFormItem label="入口文件">
        <ElInput v-model="createForm.entry_point" placeholder="evaluate.sh" />
      </ElFormItem>
      <ElFormItem label="描述">
        <ElInput v-model="createForm.description" type="textarea" :rows="2" />
      </ElFormItem>
    </ElForm>
    <template #footer>
      <ElButton @click="createDialogVisible = false">取消</ElButton>
      <ElButton type="primary" @click="submitCreate">创建</ElButton>
    </template>
  </ElDialog>

  <!-- 重命名 -->
  <ElDialog v-model="renameDialogVisible" title="重命名脚本包" width="420px">
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
.list-item__name-line {
  display: flex;
  align-items: center;
  gap: 6px;
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
