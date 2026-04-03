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
  ElOption,
  ElSelect,
  ElTag
} from 'element-plus'
import { reactive, ref, unref } from 'vue'
import { useRouter } from 'vue-router'

const router = useRouter()

const searchForm = reactive({
  keyword: '',
  status: ''
})

const { tableRegister, tableState, tableMethods } = useTable({
  fetchDataApi: async () => {
    const { pageSize, currentPage } = tableState
    const res = await getExperimentListApi({
      page: unref(currentPage),
      page_size: unref(pageSize),
      keyword: searchForm.keyword || undefined,
      status: searchForm.status || undefined
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

const crudSchemas = reactive<CrudSchema[]>([
  {
    field: 'experiment_id',
    label: 'ID',
    table: { width: 90 }
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
      width: 110,
      slots: {
        default: (data: { row: ExperimentListItem }) => (
          <ElTag type={statusTagTypeMap[data.row.status] || 'info'}>
            {statusLabelMap[data.row.status] || data.row.status}
          </ElTag>
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
      width: 140,
      slots: {
        default: (data: { row: ExperimentListItem }) => (
          <ElButton
            link
            type="primary"
            onClick={() => router.push(`/teacher/experiments/${data.row.experiment_id}`)}
          >
            详情管理
          </ElButton>
        )
      }
    }
  }
])

const { allSchemas } = useCrudSchemas(crudSchemas)

const createDialogVisible = ref(false)
const createForm = reactive({
  name: '',
  code: '',
  description: ''
})

const handleSearch = () => {
  currentPage.value = 1
  getList()
}

const handleReset = () => {
  searchForm.keyword = ''
  searchForm.status = ''
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
