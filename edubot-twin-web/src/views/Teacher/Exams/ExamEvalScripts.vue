<script setup lang="tsx">
/**
 * 测评脚本包管理页 — /teacher/exams/eval-scripts
 *
 * 功能：脚本包列表 + 新建 + 删除 + 文件管理 + 入口校验状态
 */
import { ContentWrap } from '@/components/ContentWrap'
import { Dialog } from '@/components/Dialog'
import { Table } from '@/components/Table'
import { useTable } from '@/hooks/web/useTable'
import { CrudSchema, useCrudSchemas } from '@/hooks/web/useCrudSchemas'
import {
  getExamEvalScriptListApi,
  createExamEvalScriptApi,
  deleteExamEvalScriptApi,
  listExamEvalScriptFilesApi,
  uploadExamEvalScriptFileApi,
  deleteExamEvalScriptFileApi
} from '@/api/exam/evalScripts'
import type { ExamEvalScriptListItem, EvalScriptValidateStatus } from '@/api/exam/types'
import type { BundleFileItem } from '@/api/experiment/types'
import {
  ElButton,
  ElDialog,
  ElEmpty,
  ElForm,
  ElFormItem,
  ElInput,
  ElMessage,
  ElMessageBox,
  ElTag
} from 'element-plus'
import { reactive, ref, unref } from 'vue'

function formatSize(bytes: number): string {
  if (bytes < 1024) return bytes + ' B'
  if (bytes < 1024 * 1024) return (bytes / 1024).toFixed(1) + ' KB'
  return (bytes / 1024 / 1024).toFixed(1) + ' MB'
}

const validateStatusMap: Record<
  EvalScriptValidateStatus,
  { label: string; type: '' | 'success' | 'warning' | 'danger' | 'info' }
> = {
  pending: { label: '待验证', type: 'info' },
  valid: { label: '✓ 有效', type: 'success' },
  invalid: { label: '✗ 无效', type: 'danger' }
}

// ─── 脚本包列表 ──────────────────────────────────────────────────────────────

const { tableRegister, tableState, tableMethods } = useTable({
  fetchDataApi: async () => {
    const { pageSize, currentPage } = tableState
    const res = await getExamEvalScriptListApi({
      page: unref(currentPage),
      page_size: unref(pageSize)
    })
    return {
      list: res.data?.items || [],
      total: res.data?.total || 0
    }
  }
})

const { dataList, loading, currentPage, pageSize, total } = tableState
const { getList } = tableMethods

const crudSchemas = reactive<CrudSchema[]>([
  { field: 'id', label: 'ID', table: { width: 70 } },
  { field: 'name', label: '脚本包名' },
  {
    field: 'entry_point',
    label: '入口脚本',
    table: { width: 140 }
  },
  {
    field: 'validate_status',
    label: '校验状态',
    table: {
      width: 100,
      slots: {
        default: (data: { row: ExamEvalScriptListItem }) => {
          const status = validateStatusMap[data.row.validate_status]
          return (
            <ElTag type={status?.type || 'info'} size="small">
              {status?.label || data.row.validate_status}
            </ElTag>
          )
        }
      }
    }
  },
  {
    field: 'file_count',
    label: '文件数',
    table: { width: 80 }
  },
  {
    field: 'total_size_bytes',
    label: '大小',
    table: {
      width: 100,
      slots: {
        default: (data: { row: ExamEvalScriptListItem }) => formatSize(data.row.total_size_bytes)
      }
    }
  },
  {
    field: 'created_at',
    label: '创建时间',
    table: {
      width: 120,
      slots: {
        default: (data: { row: ExamEvalScriptListItem }) =>
          data.row.created_at?.substring(0, 10) || '-'
      }
    }
  },
  {
    field: 'action',
    label: '操作',
    table: {
      width: 200,
      slots: {
        default: (data: { row: ExamEvalScriptListItem }) => (
          <div class="flex gap-6px flex-wrap">
            <ElButton link type="primary" onClick={() => openFileBrowser(data.row)}>
              文件管理
            </ElButton>
            <ElButton link type="danger" onClick={() => handleDelete(data.row)}>
              删除
            </ElButton>
          </div>
        )
      }
    }
  }
])

const { allSchemas } = useCrudSchemas(crudSchemas)

// ─── 删除 ─────────────────────────────────────────────────────────────────────

const handleDelete = async (row: ExamEvalScriptListItem) => {
  await ElMessageBox.confirm(`确认删除脚本包「${row.name}」吗？`, '删除确认', {
    type: 'warning'
  })
  try {
    await deleteExamEvalScriptApi(row.id)
    ElMessage.success('已删除')
    getList()
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

// ─── 新建脚本包 ──────────────────────────────────────────────────────────────

const createDialogVisible = ref(false)
const createForm = reactive({
  name: '',
  description: '',
  entry_point: 'evaluate.sh'
})

const openCreateDialog = () => {
  createForm.name = ''
  createForm.description = ''
  createForm.entry_point = 'evaluate.sh'
  createDialogVisible.value = true
}

const submitCreate = async () => {
  if (!createForm.name.trim()) {
    ElMessage.warning('请填写脚本包名称')
    return
  }
  try {
    await createExamEvalScriptApi({
      name: createForm.name.trim(),
      description: createForm.description.trim() || undefined,
      entry_point: createForm.entry_point.trim() || 'evaluate.sh'
    })
    ElMessage.success('脚本包创建成功，请上传脚本文件')
    createDialogVisible.value = false
    getList()
  } catch (e: unknown) {
    const err = e as { response?: { data?: { detail?: string } } }
    ElMessage.error('创建失败：' + (err?.response?.data?.detail || ''))
  }
}

// ─── 文件浏览器 ──────────────────────────────────────────────────────────────

const fileBrowserVisible = ref(false)
const fileBrowserScript = ref<ExamEvalScriptListItem | null>(null)
const fileBrowserFiles = ref<BundleFileItem[]>([])
const fileBrowserPath = ref('')
const fileBrowserLoading = ref(false)

const openFileBrowser = async (row: ExamEvalScriptListItem) => {
  fileBrowserScript.value = row
  fileBrowserPath.value = ''
  fileBrowserVisible.value = true
  await loadFiles('')
}

const loadFiles = async (path: string) => {
  if (!fileBrowserScript.value) return
  fileBrowserLoading.value = true
  try {
    const res = await listExamEvalScriptFilesApi(fileBrowserScript.value.id, path || undefined)
    fileBrowserFiles.value = res.data?.items || []
    fileBrowserPath.value = path
  } catch {
    ElMessage.error('加载目录失败')
  } finally {
    fileBrowserLoading.value = false
  }
}

const handleFileClick = (file: BundleFileItem) => {
  if (file.type === 'dir') {
    const newPath = fileBrowserPath.value ? `${fileBrowserPath.value}/${file.name}` : file.name
    loadFiles(newPath)
  }
}

const handleGoUp = () => {
  const parts = fileBrowserPath.value.split('/')
  parts.pop()
  loadFiles(parts.join('/'))
}

const handleUploadFile = async (e: Event) => {
  const target = e.target as HTMLInputElement
  const file = target.files?.[0]
  if (!file || !fileBrowserScript.value) return
  const formData = new FormData()
  formData.append('file', file)
  if (fileBrowserPath.value) formData.append('path', fileBrowserPath.value)
  try {
    await uploadExamEvalScriptFileApi(fileBrowserScript.value.id, formData)
    ElMessage.success('上传成功')
    loadFiles(fileBrowserPath.value)
    getList() // 刷新列表以获取新的 validate_status
  } catch (e: unknown) {
    const err = e as { response?: { data?: { detail?: string } } }
    ElMessage.error('上传失败：' + (err?.response?.data?.detail || ''))
  }
  target.value = ''
}

const handleDeleteFile = async (file: BundleFileItem) => {
  if (!fileBrowserScript.value) return
  const fullPath = fileBrowserPath.value ? `${fileBrowserPath.value}/${file.name}` : file.name
  await ElMessageBox.confirm(`确认删除 ${file.name}？`, '删除', { type: 'warning' })
  try {
    await deleteExamEvalScriptFileApi(fileBrowserScript.value.id, fullPath)
    ElMessage.success('已删除')
    loadFiles(fileBrowserPath.value)
    getList()
  } catch (e: unknown) {
    const err = e as { response?: { data?: { detail?: string } } }
    ElMessage.error('删除失败：' + (err?.response?.data?.detail || ''))
  }
}

const uploadInputRef = ref<HTMLInputElement | null>(null)
</script>

<template>
  <ContentWrap>
    <div class="flex items-center justify-between mb-16px">
      <div class="text-18px font-600">测评脚本管理</div>
      <ElButton type="primary" @click="openCreateDialog">新建脚本包</ElButton>
    </div>

    <div class="mb-12px text-13px color-#909399">
      💡 上传测评脚本后，系统会自动校验入口文件（entry_point）是否存在。
      脚本包被考试引用前须确保<ElTag type="success" size="small">✓ 有效</ElTag>
    </div>

    <Table
      v-model:current-page="currentPage"
      v-model:page-size="pageSize"
      :columns="allSchemas.tableColumns"
      :data="dataList"
      :loading="loading"
      :pagination="{ total: unref(total) }"
      @register="tableRegister"
    />
  </ContentWrap>

  <!-- 新建脚本包 -->
  <Dialog v-model="createDialogVisible" title="新建测评脚本包" width="480px">
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
      <ElFormItem>
        <ElButton type="primary" @click="submitCreate">创建</ElButton>
        <ElButton @click="createDialogVisible = false">取消</ElButton>
      </ElFormItem>
    </ElForm>
  </Dialog>

  <!-- 文件浏览器 -->
  <ElDialog
    v-model="fileBrowserVisible"
    :title="`文件管理 - ${fileBrowserScript?.name || ''}`"
    width="700px"
    top="5vh"
  >
    <div class="flex items-center gap-8px mb-12px">
      <ElButton size="small" :disabled="!fileBrowserPath" @click="handleGoUp"> ↑ 上级 </ElButton>
      <ElTag type="info">{{ fileBrowserPath || '/' }}</ElTag>
      <div class="flex-1"></div>
      <ElButton size="small" type="primary" @click="uploadInputRef?.click()"> 上传文件 </ElButton>
      <input ref="uploadInputRef" type="file" style="display: none" @change="handleUploadFile" />
    </div>

    <div v-loading="fileBrowserLoading" style="min-height: 200px">
      <ElEmpty v-if="fileBrowserFiles.length === 0" description="空目录，请上传脚本文件" />
      <div v-else>
        <div
          v-for="f in fileBrowserFiles"
          :key="f.name"
          class="file-item flex items-center justify-between"
        >
          <div class="flex items-center gap-8px cursor-pointer" @click="handleFileClick(f)">
            <span>{{ f.type === 'dir' ? '📁' : '📄' }}</span>
            <span>{{ f.name }}</span>
            <ElTag
              v-if="f.name === fileBrowserScript?.entry_point && f.type === 'file'"
              type="success"
              size="small"
            >
              入口
            </ElTag>
            <span v-if="f.size !== undefined" class="text-12px color-#999">
              ({{ formatSize(f.size) }})
            </span>
          </div>
          <ElButton
            v-if="f.type === 'file'"
            link
            type="danger"
            size="small"
            @click.stop="handleDeleteFile(f)"
          >
            删除
          </ElButton>
        </div>
      </div>
    </div>
  </ElDialog>
</template>

<style scoped>
.file-item {
  padding: 8px 12px;
  border-bottom: 1px solid var(--el-border-color-lighter);
  transition: background 0.2s;
}

.file-item:hover {
  background: var(--el-fill-color-light);
}
</style>
