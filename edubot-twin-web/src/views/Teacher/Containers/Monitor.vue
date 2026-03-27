<script setup lang="ts">
import { ContentWrap } from '@/components/ContentWrap'
import { Table } from '@/components/Table'
import { ref, reactive, unref, onMounted, onUnmounted } from 'vue'
import { useTable } from '@/hooks/web/useTable'
import { CrudSchema, useCrudSchemas } from '@/hooks/web/useCrudSchemas'
import {
  getContainerMonitorListApi,
  batchStartContainersApi,
  batchStopContainersApi,
  batchDeleteContainersApi
} from '@/api/monitor'
import { ElMessage, ElMessageBox, ElButton } from 'element-plus'

const { tableRegister, tableState, tableMethods } = useTable({
  fetchDataApi: async () => {
    const res = await getContainerMonitorListApi()
    return {
      list: res.data || [],
      total: res.data?.length || 0
    }
  }
})

const { dataList, loading } = tableState
const { getList, getElTableExpose } = tableMethods

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
    field: 'student.username',
    label: '学生',
    table: {
      slots: {
        default: (data: any) => data.row.student?.username || '-'
      }
    }
  },
  {
    field: 'status',
    label: '状态',
    table: {
      slots: {
        default: (data: any) => {
          const statusMap: any = {
            running: '运行中',
            stopped: '已停止',
            creating: '创建中',
            error: '错误'
          }
          return statusMap[data.row.status] || data.row.status
        }
      }
    }
  },
  {
    field: 'cpu_limit',
    label: 'CPU限制'
  },
  {
    field: 'memory_limit',
    label: '内存(MB)'
  }
])

const { allSchemas } = useCrudSchemas(crudSchemas)

const pollingTimer = ref<any>(null)

const startPolling = () => {
  pollingTimer.value = setInterval(() => {
    if (document.visibilityState === 'visible') {
      getList()
    }
  }, 5000)
}

const stopPolling = () => {
  if (pollingTimer.value) {
    clearInterval(pollingTimer.value)
    pollingTimer.value = null
  }
}

onMounted(() => {
  getList()
  startPolling()
})

onUnmounted(() => {
  stopPolling()
})

const batchStart = async () => {
  const elTableRef = await getElTableExpose()
  const ids = elTableRef?.getSelectionRows().map((v: any) => v.id) || []
  if (!ids.length) {
    ElMessage.warning('请选择容器')
    return
  }
  await batchStartContainersApi(ids)
  ElMessage.success('批量启动成功')
  getList()
}

const batchStop = async () => {
  const elTableRef = await getElTableExpose()
  const ids = elTableRef?.getSelectionRows().map((v: any) => v.id) || []
  if (!ids.length) {
    ElMessage.warning('请选择容器')
    return
  }
  await batchStopContainersApi(ids)
  ElMessage.success('批量停止成功')
  getList()
}

const batchDelete = async () => {
  const elTableRef = await getElTableExpose()
  const ids = elTableRef?.getSelectionRows().map((v: any) => v.id) || []
  if (!ids.length) {
    ElMessage.warning('请选择容器')
    return
  }
  await ElMessageBox.confirm('确认删除选中的容器吗？', '提示', {
    confirmButtonText: '确定',
    cancelButtonText: '取消',
    type: 'warning'
  })
  await batchDeleteContainersApi(ids)
  ElMessage.success('批量删除成功')
  getList()
}
</script>

<template>
  <ContentWrap>
    <div class="mb-10px">
      <ElButton type="primary" @click="batchStart">批量启动</ElButton>
      <ElButton type="warning" @click="batchStop">批量停止</ElButton>
      <ElButton type="danger" @click="batchDelete">批量删除</ElButton>
      <ElButton @click="getList">刷新</ElButton>
    </div>
    <Table
      :columns="allSchemas.tableColumns"
      :data="dataList"
      :loading="loading"
      @register="tableRegister"
    />
  </ContentWrap>
</template>
