<script setup lang="tsx">
import { ContentWrap } from '@/components/ContentWrap'
import { Dialog } from '@/components/Dialog'
import { Table } from '@/components/Table'
import { useTable } from '@/hooks/web/useTable'
import { CrudSchema, useCrudSchemas } from '@/hooks/web/useCrudSchemas'
import {
  getExamListApi,
  createExamApi,
  deleteExamApi,
  archiveExamApi,
  republishExamApi
} from '@/api/exam'
import type { ExamListItem } from '@/api/exam/types'
import {
  ElButton,
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
import { useRouter } from 'vue-router'

const router = useRouter()

const searchForm = reactive({
  keyword: '',
  status: '',
  exam_mode: ''
})

const { tableRegister, tableState, tableMethods } = useTable({
  fetchDataApi: async () => {
    const { pageSize, currentPage } = tableState
    const res = await getExamListApi({
      page: unref(currentPage),
      page_size: unref(pageSize),
      keyword: searchForm.keyword || undefined,
      status: searchForm.status || undefined,
      exam_mode: searchForm.exam_mode || undefined
    })
    return {
      list: res.data?.items || [],
      total: res.data?.total || 0
    }
  }
})

const { dataList, loading, currentPage, pageSize, total } = tableState
const { getList } = tableMethods

const statusTagTypeMap: Record<string, '' | 'success' | 'warning' | 'info' | 'danger'> = {
  draft: 'warning',
  published: 'success',
  archived: 'info'
}

const statusLabelMap: Record<string, string> = {
  draft: '草稿',
  published: '已发布',
  archived: '已归档'
}

const modeLabelMap: Record<string, string> = {
  result_run: '结果型',
  process_run: '过程型',
  multi_stage_run: '多阶段'
}

// ─── 操作 ──────────────────────────────────────────────────────────────────────

const handleArchive = async (row: ExamListItem) => {
  await ElMessageBox.confirm(`确认将考试「${row.name}」归档吗？归档后学生将不可见。`, '归档确认', {
    confirmButtonText: '归档',
    cancelButtonText: '取消',
    type: 'warning'
  })
  try {
    await archiveExamApi(row.id)
    ElMessage.success('考试已归档')
    getList()
  } catch (e: unknown) {
    const err = e as { response?: { data?: { detail?: string } } }
    ElMessage.error('归档失败：' + (err?.response?.data?.detail || ''))
  }
}

const handleRepublish = async (row: ExamListItem) => {
  try {
    await republishExamApi(row.id)
    ElMessage.success('考试已重新发布')
    getList()
  } catch (e: unknown) {
    const err = e as { response?: { data?: { detail?: string } } }
    ElMessage.error('重新发布失败：' + (err?.response?.data?.detail || ''))
  }
}

const handleDelete = async (row: ExamListItem) => {
  await ElMessageBox.confirm(
    `确认删除考试「${row.name}」吗？此操作不可撤销。仅草稿或归档状态的考试可删除。`,
    '删除确认',
    { confirmButtonText: '确认删除', cancelButtonText: '取消', type: 'warning' }
  )
  try {
    await deleteExamApi(row.id)
    ElMessage.success('考试已删除')
    getList()
  } catch (e: unknown) {
    const err = e as { response?: { data?: { detail?: string } } }
    const detail = err?.response?.data?.detail
    if (
      detail === 'EXAM_DELETE_REQUIRES_ARCHIVED' ||
      detail === 'EXAM_DELETE_REQUIRES_ARCHIVED_OR_DRAFT'
    ) {
      ElMessage.error('仅草稿或归档状态的考试可删除，请先归档')
    } else {
      ElMessage.error('删除失败：' + (detail || '未知错误'))
    }
  }
}

// ─── 表格列定义 ──────────────────────────────────────────────────────────────

const crudSchemas = reactive<CrudSchema[]>([
  { field: 'id', label: 'ID', table: { width: 70 } },
  { field: 'name', label: '考试名称' },
  { field: 'code', label: '编码', table: { width: 140 } },
  {
    field: 'exam_mode',
    label: '模式',
    table: {
      width: 100,
      slots: {
        default: (data: { row: ExamListItem }) =>
          modeLabelMap[data.row.exam_mode] || data.row.exam_mode
      }
    }
  },
  {
    field: 'status',
    label: '状态',
    table: {
      width: 100,
      slots: {
        default: (data: { row: ExamListItem }) => (
          <ElTag type={statusTagTypeMap[data.row.status] || 'info'} size="small">
            {statusLabelMap[data.row.status] || data.row.status}
          </ElTag>
        )
      }
    }
  },
  {
    field: 'created_at',
    label: '创建时间',
    table: {
      width: 180,
      slots: {
        default: (data: { row: ExamListItem }) => data.row.created_at?.substring(0, 10) || '-'
      }
    }
  },
  {
    field: 'action',
    label: '操作',
    table: {
      width: 240,
      slots: {
        default: (data: { row: ExamListItem }) => (
          <div class="flex gap-6px flex-wrap">
            <ElButton
              link
              type="primary"
              onClick={() => router.push(`/teacher/exams/${data.row.id}/detail`)}
            >
              详情
            </ElButton>
            {data.row.status === 'published' && (
              <ElButton link type="warning" onClick={() => handleArchive(data.row)}>
                归档
              </ElButton>
            )}
            {data.row.status === 'archived' && (
              <ElButton link type="success" onClick={() => handleRepublish(data.row)}>
                重新发布
              </ElButton>
            )}
            {(data.row.status === 'archived' || data.row.status === 'draft') && (
              <ElButton link type="danger" onClick={() => handleDelete(data.row)}>
                删除
              </ElButton>
            )}
          </div>
        )
      }
    }
  }
])

const { allSchemas } = useCrudSchemas(crudSchemas)

// ─── 新建考试 ─────────────────────────────────────────────────────────────────

const createDialogVisible = ref(false)
const createForm = reactive({
  name: '',
  code: '',
  description: '',
  exam_mode: 'result_run' as 'result_run' | 'process_run' | 'multi_stage_run'
})

const handleSearch = () => {
  currentPage.value = 1
  getList()
}

const handleReset = () => {
  searchForm.keyword = ''
  searchForm.status = ''
  searchForm.exam_mode = ''
  currentPage.value = 1
  getList()
}

const resetCreateForm = () => {
  createForm.name = ''
  createForm.code = ''
  createForm.description = ''
  createForm.exam_mode = 'result_run'
}

const openCreateDialog = () => {
  resetCreateForm()
  createDialogVisible.value = true
}

const submitCreate = async () => {
  if (!createForm.name.trim() || !createForm.code.trim()) {
    ElMessage.warning('请填写考试名称和编码')
    return
  }
  try {
    const res = await createExamApi({
      name: createForm.name.trim(),
      code: createForm.code.trim(),
      description: createForm.description.trim() || undefined,
      exam_mode: createForm.exam_mode
    })
    ElMessage.success('考试创建成功')
    createDialogVisible.value = false
    // 跳转详情页
    if (res.data?.id) {
      router.push(`/teacher/exams/${res.data.id}/detail`)
    } else {
      getList()
    }
  } catch (e: unknown) {
    const err = e as { response?: { data?: { detail?: string } } }
    const detail = err?.response?.data?.detail
    if (detail === 'EXAM_CODE_DUPLICATED') {
      ElMessage.error('编码已存在，请使用其他编码')
    } else {
      ElMessage.error('创建失败：' + (detail || '未知错误'))
    }
  }
}
</script>

<template>
  <ContentWrap>
    <ElForm :model="searchForm" inline class="mb-16px">
      <ElFormItem label="关键字">
        <ElInput
          v-model="searchForm.keyword"
          placeholder="考试名称 / 编码"
          clearable
          style="width: 220px"
          @keyup.enter="handleSearch"
        />
      </ElFormItem>
      <ElFormItem label="状态">
        <ElSelect v-model="searchForm.status" clearable placeholder="全部" style="width: 120px">
          <ElOption label="草稿" value="draft" />
          <ElOption label="已发布" value="published" />
          <ElOption label="已归档" value="archived" />
        </ElSelect>
      </ElFormItem>
      <ElFormItem label="模式">
        <ElSelect v-model="searchForm.exam_mode" clearable placeholder="全部" style="width: 120px">
          <ElOption label="结果型" value="result_run" />
          <ElOption label="过程型" value="process_run" />
          <ElOption label="多阶段" value="multi_stage_run" />
        </ElSelect>
      </ElFormItem>
      <ElFormItem>
        <ElButton type="primary" @click="handleSearch">查询</ElButton>
        <ElButton @click="handleReset">重置</ElButton>
      </ElFormItem>
    </ElForm>

    <div class="mb-10px">
      <ElButton type="primary" @click="openCreateDialog">新建考试</ElButton>
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

  <Dialog v-model="createDialogVisible" title="新建考试" width="520px">
    <ElForm label-width="100px">
      <ElFormItem label="考试名称" required>
        <ElInput v-model="createForm.name" placeholder="例如：自动导航考试" />
      </ElFormItem>
      <ElFormItem label="考试编码" required>
        <ElInput v-model="createForm.code" placeholder="例如：nav01" />
      </ElFormItem>
      <ElFormItem label="考试模式" required>
        <ElSelect v-model="createForm.exam_mode" style="width: 100%">
          <ElOption label="结果型自动评测" value="result_run" />
          <ElOption label="过程型操作评测" value="process_run" />
          <ElOption label="多阶段编排评测" value="multi_stage_run" />
        </ElSelect>
      </ElFormItem>
      <ElFormItem label="描述">
        <ElInput v-model="createForm.description" type="textarea" :rows="3" />
      </ElFormItem>
      <ElFormItem>
        <ElButton type="primary" @click="submitCreate">保存</ElButton>
        <ElButton @click="createDialogVisible = false">取消</ElButton>
      </ElFormItem>
    </ElForm>
  </Dialog>
</template>
