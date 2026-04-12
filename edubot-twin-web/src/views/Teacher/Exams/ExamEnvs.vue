<script setup lang="tsx">
/**
 * 考试环境快照管理页 — /teacher/exams/envs
 *
 * 功能：快照列表 + 新建空快照 + 从实验环境複製 + 删除 + 文件管理
 * 复用 BundleFileService 的 files 子协议进行文件操作。
 */
import { ContentWrap } from '@/components/ContentWrap'
import { Dialog } from '@/components/Dialog'
import { Table } from '@/components/Table'
import { useTable } from '@/hooks/web/useTable'
import { CrudSchema, useCrudSchemas } from '@/hooks/web/useCrudSchemas'
import {
  getExamEnvSnapshotListApi,
  createExamEnvSnapshotApi,
  copyExamEnvSnapshotApi,
  deleteExamEnvSnapshotApi,
  listExamEnvSnapshotFilesApi,
  uploadExamEnvSnapshotFileApi,
  deleteExamEnvSnapshotFileApi
} from '@/api/exam/envSnapshots'
import { getEnvBundleListApi } from '@/api/experiment'
import type { ExamEnvSnapshotListItem } from '@/api/exam/types'
import type { EnvBundleListItem, BundleFileItem } from '@/api/experiment/types'
import {
  ElButton,
  ElDialog,
  ElEmpty,
  ElForm,
  ElFormItem,
  ElInput,
  ElMessage,
  ElMessageBox,
  ElOption,
  ElSelect,
  ElTag
} from 'element-plus'
import { reactive, ref, unref } from 'vue'

function formatSize(bytes: number): string {
  if (bytes < 1024) return bytes + ' B'
  if (bytes < 1024 * 1024) return (bytes / 1024).toFixed(1) + ' KB'
  return (bytes / 1024 / 1024).toFixed(1) + ' MB'
}

// ─── 快照列表 ─────────────────────────────────────────────────────────────────

const { tableRegister, tableState, tableMethods } = useTable({
  fetchDataApi: async () => {
    const { pageSize, currentPage } = tableState
    const res = await getExamEnvSnapshotListApi({
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
  { field: 'name', label: '快照名' },
  { field: 'container_target_dir', label: '挂载目录', table: { width: 200 } },
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
        default: (data: { row: ExamEnvSnapshotListItem }) => formatSize(data.row.total_size_bytes)
      }
    }
  },
  {
    field: 'created_at',
    label: '创建时间',
    table: {
      width: 120,
      slots: {
        default: (data: { row: ExamEnvSnapshotListItem }) =>
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
        default: (data: { row: ExamEnvSnapshotListItem }) => (
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

const handleDelete = async (row: ExamEnvSnapshotListItem) => {
  await ElMessageBox.confirm(`确认删除环境快照「${row.name}」吗？`, '删除确认', {
    type: 'warning'
  })
  try {
    await deleteExamEnvSnapshotApi(row.id)
    ElMessage.success('已删除')
    getList()
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

// ─── 新建空快照 ──────────────────────────────────────────────────────────────

const createDialogVisible = ref(false)
const createForm = reactive({
  name: '',
  container_target_dir: '/home/ubuntu20/catkin_ws'
})

const openCreateDialog = () => {
  createForm.name = ''
  createForm.container_target_dir = '/home/ubuntu20/catkin_ws'
  createDialogVisible.value = true
}

const submitCreate = async () => {
  if (!createForm.name.trim()) {
    ElMessage.warning('请填写快照名称')
    return
  }
  try {
    await createExamEnvSnapshotApi({
      name: createForm.name.trim(),
      container_target_dir: createForm.container_target_dir
    })
    ElMessage.success('快照创建成功')
    createDialogVisible.value = false
    getList()
  } catch (e: unknown) {
    const err = e as { response?: { data?: { detail?: string } } }
    ElMessage.error('创建失败：' + (err?.response?.data?.detail || ''))
  }
}

// ─── 从实验环境复制 ──────────────────────────────────────────────────────────

const copyDialogVisible = ref(false)
const copyForm = reactive({
  source_env_bundle_id: undefined as number | undefined,
  name: ''
})
const envBundleOptions = ref<EnvBundleListItem[]>([])
const copyLoading = ref(false)

const openCopyDialog = async () => {
  copyForm.source_env_bundle_id = undefined
  copyForm.name = ''
  copyDialogVisible.value = true
  try {
    const res = await getEnvBundleListApi({ page: 1, page_size: 200 })
    envBundleOptions.value = res.data?.list || []
  } catch {
    ElMessage.error('加载实验环境列表失败')
  }
}

const submitCopy = async () => {
  if (!copyForm.source_env_bundle_id || !copyForm.name.trim()) {
    ElMessage.warning('请选择源环境包并填写快照名')
    return
  }
  copyLoading.value = true
  try {
    await copyExamEnvSnapshotApi({
      source_env_bundle_id: copyForm.source_env_bundle_id,
      name: copyForm.name.trim()
    })
    ElMessage.success('快照复制完成')
    copyDialogVisible.value = false
    getList()
  } catch (e: unknown) {
    const err = e as { response?: { data?: { detail?: string } } }
    ElMessage.error('复制失败：' + (err?.response?.data?.detail || ''))
  } finally {
    copyLoading.value = false
  }
}

// ─── 文件浏览器 ──────────────────────────────────────────────────────────────

const fileBrowserVisible = ref(false)
const fileBrowserSnapshot = ref<ExamEnvSnapshotListItem | null>(null)
const fileBrowserFiles = ref<BundleFileItem[]>([])
const fileBrowserPath = ref('')
const fileBrowserLoading = ref(false)

const openFileBrowser = async (row: ExamEnvSnapshotListItem) => {
  fileBrowserSnapshot.value = row
  fileBrowserPath.value = ''
  fileBrowserVisible.value = true
  await loadFiles('')
}

const loadFiles = async (path: string) => {
  if (!fileBrowserSnapshot.value) return
  fileBrowserLoading.value = true
  try {
    const res = await listExamEnvSnapshotFilesApi(fileBrowserSnapshot.value.id, path || undefined)
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
  if (!file || !fileBrowserSnapshot.value) return
  const formData = new FormData()
  formData.append('file', file)
  if (fileBrowserPath.value) formData.append('path', fileBrowserPath.value)
  try {
    await uploadExamEnvSnapshotFileApi(fileBrowserSnapshot.value.id, formData)
    ElMessage.success('上传成功')
    loadFiles(fileBrowserPath.value)
    getList()
  } catch (e: unknown) {
    const err = e as { response?: { data?: { detail?: string } } }
    ElMessage.error('上传失败：' + (err?.response?.data?.detail || ''))
  }
  target.value = ''
}

const handleDeleteFile = async (file: BundleFileItem) => {
  if (!fileBrowserSnapshot.value) return
  const fullPath = fileBrowserPath.value ? `${fileBrowserPath.value}/${file.name}` : file.name
  await ElMessageBox.confirm(`确认删除 ${file.name}？`, '删除', { type: 'warning' })
  try {
    await deleteExamEnvSnapshotFileApi(fileBrowserSnapshot.value.id, fullPath)
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
      <div class="text-18px font-600">考试环境快照</div>
      <div class="flex gap-8px">
        <ElButton type="primary" @click="openCreateDialog">新建空快照</ElButton>
        <ElButton type="success" @click="openCopyDialog">从实验环境复制</ElButton>
      </div>
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

  <!-- 新建空快照 -->
  <Dialog v-model="createDialogVisible" title="新建考试环境快照" width="480px">
    <ElForm label-width="100px">
      <ElFormItem label="快照名称" required>
        <ElInput v-model="createForm.name" placeholder="例如：期中考试环境" />
      </ElFormItem>
      <ElFormItem label="挂载目录">
        <ElInput v-model="createForm.container_target_dir" placeholder="/home/ubuntu20/catkin_ws" />
      </ElFormItem>
      <ElFormItem>
        <ElButton type="primary" @click="submitCreate">创建</ElButton>
        <ElButton @click="createDialogVisible = false">取消</ElButton>
      </ElFormItem>
    </ElForm>
  </Dialog>

  <!-- 从实验环境复制 -->
  <Dialog v-model="copyDialogVisible" title="从实验环境复制" width="520px">
    <div class="mb-12px text-13px color-#909399">
      从已有的实验环境包复制全部文件到考试环境快照。复制完成后生命周期独立。
    </div>
    <ElForm label-width="100px">
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
      <ElFormItem>
        <ElButton type="primary" :loading="copyLoading" @click="submitCopy"> 开始复制 </ElButton>
        <ElButton @click="copyDialogVisible = false">取消</ElButton>
      </ElFormItem>
    </ElForm>
  </Dialog>

  <!-- 文件浏览器 -->
  <ElDialog
    v-model="fileBrowserVisible"
    :title="`文件管理 - ${fileBrowserSnapshot?.name || ''}`"
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
      <ElEmpty v-if="fileBrowserFiles.length === 0" description="空目录" />
      <div v-else>
        <div
          v-for="f in fileBrowserFiles"
          :key="f.name"
          class="file-item flex items-center justify-between"
        >
          <div class="flex items-center gap-8px cursor-pointer" @click="handleFileClick(f)">
            <span>{{ f.type === 'dir' ? '📁' : '📄' }}</span>
            <span>{{ f.name }}</span>
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
