<script setup lang="tsx">
import { ContentWrap } from '@/components/ContentWrap'
import { Dialog } from '@/components/Dialog'
import { Table } from '@/components/Table'
import { useTable } from '@/hooks/web/useTable'
import { CrudSchema, useCrudSchemas } from '@/hooks/web/useCrudSchemas'
import { createExperimentApi, getExperimentListApi } from '@/api/experiment'
import type { ExperimentListItem } from '@/api/experiment/types'
import {
  ElButton,
  ElForm,
  ElFormItem,
  ElInput,
  ElMessage,
  ElMessageBox,
  ElOption,
  ElSelect,
  ElSwitch,
  ElTag
} from 'element-plus'
import { computed, reactive, ref, unref } from 'vue'
import { useRouter } from 'vue-router'
import request from '@/axios'

const router = useRouter()

const searchForm = reactive({
  keyword: '',
  status: '',
  sort_by: 'id',
  sort_order: 'asc' as 'asc' | 'desc'
})

const sortOptions = [
  { label: 'ID 升序（默认）', sort_by: 'id', sort_order: 'asc' },
  { label: 'ID 降序', sort_by: 'id', sort_order: 'desc' },
  { label: '名称 A→Z', sort_by: 'name', sort_order: 'asc' },
  { label: '名称 Z→A', sort_by: 'name', sort_order: 'desc' },
  { label: '最近更新', sort_by: 'updated_at', sort_order: 'desc' },
  { label: '最早更新', sort_by: 'updated_at', sort_order: 'asc' },
  { label: '最新创建', sort_by: 'created_at', sort_order: 'desc' },
  { label: '最早创建', sort_by: 'created_at', sort_order: 'asc' },
  { label: '状态 A→Z', sort_by: 'status', sort_order: 'asc' },
  { label: '状态 Z→A', sort_by: 'status', sort_order: 'desc' },
]

// 用于下拉框的合并 key
const sortKey = computed({
  get: () => `${searchForm.sort_by}:${searchForm.sort_order}`,
  set: (val: string) => {
    const opt = sortOptions.find((o) => `${o.sort_by}:${o.sort_order}` === val)
    if (opt) {
      searchForm.sort_by = opt.sort_by
      searchForm.sort_order = opt.sort_order as 'asc' | 'desc'
    }
  }
})

const { tableRegister, tableState, tableMethods } = useTable({
  fetchDataApi: async () => {
    const { pageSize, currentPage } = tableState
    const res = await getExperimentListApi({
      page: unref(currentPage),
      page_size: unref(pageSize),
      keyword: searchForm.keyword || undefined,
      status: searchForm.status || undefined,
      sort_by: searchForm.sort_by,
      sort_order: searchForm.sort_order
    })

    return {
      list: res.data?.list || [],
      total: res.data?.total || 0
    }
  }
})

const { dataList, loading, currentPage, pageSize, total } = tableState
const { getList } = tableMethods

const statusTagTypeMap: Record<string, '' | 'success' | 'warning' | 'info' | 'danger'> = {
  draft: 'warning',
  active: 'success',
  archived: 'info'
}

const statusLabelMap: Record<string, string> = {
  draft: '草稿',
  active: '启用',
  archived: '归档'
}

// ─── 实验状态切换 ─────────────────────────────────────────────────────────────

const handleStatusToggle = async (row: ExperimentListItem, newVal: boolean) => {
  const targetStatus = newVal ? 'active' : 'draft'
  try {
    await request.patch({
      url: `/api/v1/teachers/experiments/${row.experiment_id}/status`,
      data: { status: targetStatus }
    })
    ElMessage.success(`实验已${newVal ? '启用' : '取消启用'}`)
    getList()
  } catch (e: any) {
    ElMessage.error('状态切换失败：' + (e?.response?.data?.detail || '未知错误'))
    getList()
  }
}

const handleArchive = async (row: ExperimentListItem) => {
  await ElMessageBox.confirm(
    `确认将实验「${row.name}」归档吗？归档后学生将不可见，可再次恢复。`,
    '归档确认',
    { confirmButtonText: '归档', cancelButtonText: '取消', type: 'warning' }
  )
  try {
    await request.patch({
      url: `/api/v1/teachers/experiments/${row.experiment_id}/status`,
      data: { status: 'archived' }
    })
    ElMessage.success('实验已归档')
    getList()
  } catch (e: any) {
    ElMessage.error('归档失败：' + (e?.response?.data?.detail || ''))
  }
}

// ─── 实验删除 ─────────────────────────────────────────────────────────────────

const handleDelete = async (row: ExperimentListItem) => {
  await ElMessageBox.confirm(
    `确认删除实验「${row.name}」吗？此操作不可撤销。仅当所有版本均为草稿或无版本时才允许删除。`,
    '删除确认',
    { confirmButtonText: '确认删除', cancelButtonText: '取消', type: 'warning' }
  )
  try {
    await request.delete({ url: `/api/v1/teachers/experiments/${row.experiment_id}` })
    ElMessage.success('实验已删除')
    getList()
  } catch (e: any) {
    const detail = e?.response?.data?.detail
    if (detail === 'EXPERIMENT_HAS_NON_DRAFT_VERSIONS') {
      ElMessage.error('该实验下存在已发布版本，请先废弃或删除所有版本')
    } else {
      ElMessage.error('删除失败：' + (detail || '未知错误'))
    }
  }
}

// ─── 表格列定义 ──────────────────────────────────────────────────────────────

const crudSchemas = reactive<CrudSchema[]>([
  {
    field: 'experiment_id',
    label: 'ID',
    table: { width: 80 }
  },
  {
    field: 'name',
    label: '实验名称'
  },
  {
    field: 'code',
    label: '实验编码'
  },
  {
    field: 'status',
    label: '状态',
    table: {
      width: 180,
      slots: {
        default: (data: { row: ExperimentListItem }) => (
          <div class="flex items-center gap-8px">
            <ElTag type={statusTagTypeMap[data.row.status] || 'info'} size="small">
              {statusLabelMap[data.row.status] || data.row.status}
            </ElTag>
            {data.row.status !== 'archived' && (
              <ElSwitch
                modelValue={data.row.status === 'active'}
                size="small"
                activeText="启用"
                inactiveText="草稿"
                onChange={(val: boolean) => handleStatusToggle(data.row, val)}
              />
            )}
          </div>
        )
      }
    }
  },
  {
    field: 'latest_version',
    label: '最新版本',
    table: {
      slots: {
        default: (data: { row: ExperimentListItem }) => data.row.latest_version || '-'
      }
    }
  },
  {
    field: 'published_at',
    label: '发布时间',
    table: {
      width: 180,
      slots: {
        default: (data: { row: ExperimentListItem }) => data.row.published_at || '-'
      }
    }
  },
  {
    field: 'action',
    label: '操作',
    table: {
      width: 200,
      slots: {
        default: (data: { row: ExperimentListItem }) => (
          <div class="flex gap-6px flex-wrap">
            <ElButton
              link
              type="primary"
              onClick={() => router.push(`/teacher/experiments/${data.row.experiment_id}/detail`)}
            >
              版本管理
            </ElButton>
            {data.row.status !== 'archived' && (
              <ElButton link type="warning" onClick={() => handleArchive(data.row)}>
                归档
              </ElButton>
            )}
            {data.row.status === 'archived' && (
              <ElButton link type="success" onClick={() => handleStatusToggle(data.row, true)}>
                恢复
              </ElButton>
            )}
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

// ─── 新建实验 ─────────────────────────────────────────────────────────────────

const createDialogVisible = ref(false)
const createForm = reactive({ name: '', code: '', description: '' })

const handleSearch = () => {
  currentPage.value = 1
  getList()
}

const handleReset = () => {
  searchForm.keyword = ''
  searchForm.status = ''
  searchForm.sort_by = 'id'
  searchForm.sort_order = 'asc'
  currentPage.value = 1
  getList()
}

const resetCreateForm = () => {
  createForm.name = ''
  createForm.code = ''
  createForm.description = ''
}

const openCreateDialog = () => {
  resetCreateForm()
  createDialogVisible.value = true
}

const submitCreateExperiment = async () => {
  if (!createForm.name.trim() || !createForm.code.trim()) {
    ElMessage.warning('请填写实验名称和实验编码')
    return
  }

  await createExperimentApi({
    name: createForm.name.trim(),
    code: createForm.code.trim(),
    description: createForm.description.trim() || undefined
  })

  ElMessage.success('实验创建成功')
  createDialogVisible.value = false
  getList()
}
</script>

<template>
  <ContentWrap>
    <ElForm :model="searchForm" inline class="mb-16px">
      <ElFormItem label="关键字">
        <ElInput
          v-model="searchForm.keyword"
          placeholder="实验名称 / 编码"
          clearable
          style="width: 220px"
          @keyup.enter="handleSearch"
        />
      </ElFormItem>
      <ElFormItem label="状态">
        <ElSelect v-model="searchForm.status" clearable placeholder="全部" style="width: 140px">
          <ElOption label="草稿" value="draft" />
          <ElOption label="启用" value="active" />
          <ElOption label="归档" value="archived" />
        </ElSelect>
      </ElFormItem>
      <ElFormItem label="排序">
        <ElSelect v-model="sortKey" style="width: 160px">
          <ElOption
            v-for="opt in sortOptions"
            :key="`${opt.sort_by}:${opt.sort_order}`"
            :label="opt.label"
            :value="`${opt.sort_by}:${opt.sort_order}`"
          />
        </ElSelect>
      </ElFormItem>
      <ElFormItem>
        <ElButton type="primary" @click="handleSearch">查询</ElButton>
        <ElButton @click="handleReset">重置</ElButton>
      </ElFormItem>
    </ElForm>

    <div class="mb-10px">
      <ElButton type="primary" @click="openCreateDialog">新增实验</ElButton>
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

  <Dialog v-model="createDialogVisible" title="新增实验" width="520px">
    <ElForm label-width="100px">
      <ElFormItem label="实验名称" required>
        <ElInput v-model="createForm.name" placeholder="例如：机器人导航" />
      </ElFormItem>
      <ElFormItem label="实验编码" required>
        <ElInput v-model="createForm.code" placeholder="例如：nav_basic" />
      </ElFormItem>
      <ElFormItem label="描述">
        <ElInput v-model="createForm.description" type="textarea" :rows="3" />
      </ElFormItem>
      <ElFormItem>
        <ElButton type="primary" @click="submitCreateExperiment">保存</ElButton>
        <ElButton @click="createDialogVisible = false">取消</ElButton>
      </ElFormItem>
    </ElForm>
  </Dialog>
</template>
