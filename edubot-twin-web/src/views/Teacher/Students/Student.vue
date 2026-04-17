<script setup lang="tsx">
import { ContentWrap } from '@/components/ContentWrap'
import { Table } from '@/components/Table'
import { ref, reactive, unref } from 'vue'
import { useTable } from '@/hooks/web/useTable'
import { CrudSchema, useCrudSchemas } from '@/hooks/web/useCrudSchemas'
import { getStudentListApi, deleteStudentApi } from '@/api/teacher'
import type { StudentInfo } from '@/api/teacher/types'
import { ElMessage, ElMessageBox, ElButton, ElInput, ElForm, ElFormItem, ElTag } from 'element-plus'
import Write from './components/Write.vue'
import ImportDialog from './components/ImportDialog.vue'
import { Dialog } from '@/components/Dialog'

// ─── 搜索表单状态 ─────────────────────────────────────────────
const searchForm = reactive({
  keyword: ''
})

// ─── 表格 Hook ────────────────────────────────────────────────
const { tableRegister, tableState, tableMethods } = useTable({
  fetchDataApi: async () => {
    const { pageSize, currentPage } = tableState
    const res = await getStudentListApi({
      pageIndex: unref(currentPage),
      pageSize: unref(pageSize),
      keyword: searchForm.keyword || undefined
    })
    return {
      list: res.data?.list || [],
      total: res.data?.total || 0
    }
  }
})

const { dataList, loading, currentPage, pageSize, total } = tableState
const roleLabelMap: Record<string, string> = {
  admin: '管理员',
  teacher: '教师',
  student: '学生'
}
const { getList, getElTableExpose } = tableMethods

// ─── 搜索 / 重置 ─────────────────────────────────────────────
const handleSearch = () => {
  currentPage.value = 1
  getList()
}

const handleReset = () => {
  searchForm.keyword = ''
  currentPage.value = 1
  getList()
}

// ─── 表格列定义 ───────────────────────────────────────────────
const crudSchemas = reactive<CrudSchema[]>([
  {
    field: 'selection',
    table: { type: 'selection' }
  },
  {
    field: 'id',
    label: 'ID',
    table: { width: 80 }
  },
  {
    field: 'username',
    label: '用户名'
  },
  {
    field: 'real_name',
    label: '姓名'
  },
  {
    field: 'email',
    label: '邮箱',
    table: {
      slots: {
        default: (data: any) => data.row.email || '-'
      }
    }
  },
  {
    field: 'role_code',
    label: '角色',
    table: {
      width: 120,
      slots: {
        default: (data: { row: StudentInfo }) =>
          roleLabelMap[data.row.role_code] || data.row.role_code || '-'
      }
    }
  },
  {
    field: 'role_id',
    label: '角色ID',
    table: {
      width: 100,
      slots: {
        default: (data: { row: StudentInfo }) => data.row.role_id || '-'
      }
    }
  },
  {
    field: 'is_active',
    label: '状态',
    table: {
      width: 100,
      slots: {
        default: (data: any) => (
          <ElTag type={data.row.is_active ? 'success' : 'info'}>
            {data.row.is_active ? '启用' : '禁用'}
          </ElTag>
        )
      }
    }
  },
  {
    field: 'action',
    label: '操作',
    table: {
      width: 160,
      slots: {
        default: (data: any) => (
          <>
            <ElButton link type="primary" onClick={() => editAction(data.row)}>
              编辑
            </ElButton>
            <ElButton link type="danger" onClick={() => delData(data.row)}>
              删除
            </ElButton>
          </>
        )
      }
    }
  }
])

const { allSchemas } = useCrudSchemas(crudSchemas)

// ─── 对话框状态 ────────────────────────────────────────────────
const dialogVisible = ref(false)
const dialogTitle = ref('')
const actionType = ref('')
const currentRow = ref()

const AddAction = () => {
  dialogTitle.value = '新增用户'
  actionType.value = 'add'
  currentRow.value = undefined
  dialogVisible.value = true
}

// ─── 单删 ─────────────────────────────────────────────────────
const delData = async (row: any) => {
  await ElMessageBox.confirm('确认删除该用户吗？删除后将同步清理其关联容器！', '警告', {
    confirmButtonText: '确定删除',
    cancelButtonText: '取消',
    type: 'warning'
  })
  await deleteStudentApi(row.id)
  ElMessage.success('删除成功')
  getList()
}

// ─── 批量删除 ─────────────────────────────────────────────────
const batchDelete = async () => {
  const elTableRef = await getElTableExpose()
  const selectedRows = elTableRef?.getSelectionRows() || []
  if (!selectedRows.length) {
    ElMessage.warning('请先选择要删除的用户')
    return
  }
  await ElMessageBox.confirm(
    `确认批量删除 ${selectedRows.length} 名用户吗？删除后将同步清理关联容器！`,
    '批量删除确认',
    {
      confirmButtonText: '确定删除',
      cancelButtonText: '取消',
      type: 'warning'
    }
  )
  let successCount = 0
  for (const row of selectedRows) {
    try {
      await deleteStudentApi(row.id)
      successCount++
    } catch (e) {
      ElMessage.error(`删除用户 ${row.username} 失败`)
    }
  }
  if (successCount > 0) {
    ElMessage.success(`成功删除 ${successCount} 名用户`)
  }
  getList()
}

// ─── 编辑 ─────────────────────────────────────────────────────
const editAction = (row: any) => {
  dialogTitle.value = '编辑用户'
  actionType.value = 'edit'
  currentRow.value = row
  dialogVisible.value = true
}

const onSubmit = () => {
  dialogVisible.value = false
  getList()
}

// ─── 批量导入 ─────────────────────────────────────────────────
const importDialogVisible = ref(false)
</script>

<template>
  <ContentWrap>
    <!-- 搜索表单 -->
    <ElForm :model="searchForm" inline class="mb-16px">
      <ElFormItem label="搜索">
        <ElInput
          v-model="searchForm.keyword"
          placeholder="输入用户名或姓名"
          clearable
          style="width: 240px"
          @keyup.enter="handleSearch"
          @clear="handleReset"
        />
      </ElFormItem>
      <ElFormItem>
        <ElButton type="primary" @click="handleSearch">查询</ElButton>
        <ElButton @click="handleReset">重置</ElButton>
      </ElFormItem>
    </ElForm>

    <!-- 工具栏 -->
    <div class="mb-10px flex items-center gap-10px">
      <ElButton type="primary" @click="AddAction">新增用户</ElButton>
      <ElButton type="success" @click="importDialogVisible = true">批量导入</ElButton>
      <ElButton type="danger" @click="batchDelete">批量删除</ElButton>
    </div>

    <!-- 数据表格 -->
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

  <!-- 批量导入对话框 -->
  <ImportDialog v-model="importDialogVisible" @done="getList" />

  <!-- 新增/编辑对话框 -->
  <Dialog v-model="dialogVisible" :title="dialogTitle">
    <Write
      v-if="dialogVisible"
      :current-row="currentRow"
      :action-type="actionType"
      @close="dialogVisible = false"
      @submit="onSubmit"
    />
  </Dialog>
</template>
