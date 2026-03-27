<script setup lang="tsx">
import { ContentWrap } from '@/components/ContentWrap'
import { Table } from '@/components/Table'
import { ref, reactive, unref } from 'vue'
import { useTable } from '@/hooks/web/useTable'
import { CrudSchema, useCrudSchemas } from '@/hooks/web/useCrudSchemas'
import { getStudentListApi, deleteStudentApi } from '@/api/student'
import { ElMessage, ElMessageBox, ElButton } from 'element-plus'
import Write from './components/Write.vue'
import { Dialog } from '@/components/Dialog'

const { tableRegister, tableState, tableMethods } = useTable({
  fetchDataApi: async () => {
    const { pageSize, currentPage } = tableState
    const res = await getStudentListApi({
      skip: (unref(currentPage) - 1) * unref(pageSize),
      limit: unref(pageSize)
    })
    return {
      list: res.data || [],
      total: res.data?.length || 0
    }
  }
})

const { dataList, loading, currentPage, pageSize } = tableState
const { getList, getElTableExpose } = tableMethods

const crudSchemas = reactive<CrudSchema[]>([
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
    label: '邮箱'
  },
  {
    field: 'is_active',
    label: '状态',
    table: {
      slots: {
        default: (data: any) => {
          return data.row.is_active ? '启用' : '禁用'
        }
      }
    }
  },
  {
    field: 'action',
    label: '操作',
    table: {
      width: 200,
      slots: {
        default: (data: any) => {
          return (
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
  }
])

const { allSchemas } = useCrudSchemas(crudSchemas)

const dialogVisible = ref(false)
const dialogTitle = ref('')
const actionType = ref('')
const currentRow = ref()

const AddAction = () => {
  dialogTitle.value = '新增学生'
  actionType.value = 'add'
  currentRow.value = undefined
  dialogVisible.value = true
}

const delData = async (row: any) => {
  await ElMessageBox.confirm('确认删除该学生吗？', '提示', {
    confirmButtonText: '确定',
    cancelButtonText: '取消',
    type: 'warning'
  })
  await deleteStudentApi(row.id)
  ElMessage.success('删除成功')
  getList()
}

const editAction = (row: any) => {
  dialogTitle.value = '编辑学生'
  actionType.value = 'edit'
  currentRow.value = row
  dialogVisible.value = true
}

const onSubmit = () => {
  dialogVisible.value = false
  getList()
}
</script>

<template>
  <ContentWrap>
    <div class="mb-10px">
      <ElButton type="primary" @click="AddAction">新增学生</ElButton>
    </div>
    <Table
      v-model:current-page="currentPage"
      v-model:page-size="pageSize"
      :columns="allSchemas.tableColumns"
      :data="dataList"
      :loading="loading"
      @register="tableRegister"
    />
  </ContentWrap>

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
