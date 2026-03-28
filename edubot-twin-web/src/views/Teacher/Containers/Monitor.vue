<script setup lang="tsx">
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
} from '@/api/teacher'
import type { ContainerStatus } from '@/api/teacher/types'
import { ElMessage, ElMessageBox, ElButton, ElTag, ElProgress } from 'element-plus'

// ─── 状态颜色映射 ─────────────────────────────────────────────
const statusConfig: Record<
  ContainerStatus,
  { label: string; type: 'success' | 'danger' | 'warning' | 'info' | 'primary' }
> = {
  running: { label: '运行中', type: 'success' },
  stopped: { label: '已停止', type: 'info' },
  creating: { label: '创建中', type: 'warning' },
  error: { label: '错误', type: 'danger' },
  removing: { label: '删除中', type: 'danger' }
}

// ─── 运行时长格式化 ───────────────────────────────────────────
const formatUptime = (seconds: number): string => {
  if (!seconds || seconds <= 0) return '-'
  const h = Math.floor(seconds / 3600)
  const m = Math.floor((seconds % 3600) / 60)
  const s = seconds % 60
  if (h > 0) return `${h}h ${m}m`
  if (m > 0) return `${m}m ${s}s`
  return `${s}s`
}

// ─── 表格 Hook ────────────────────────────────────────────────
const { tableRegister, tableState, tableMethods } = useTable({
  fetchDataApi: async () => {
    const { pageSize, currentPage } = tableState
    const res = await getContainerMonitorListApi({
      pageIndex: unref(currentPage),
      pageSize: unref(pageSize)
    })
    return {
      list: res.data?.list || [],
      total: res.data?.total || 0
    }
  }
})

const { dataList, loading, currentPage, pageSize, total } = tableState
const { getList, getElTableExpose } = tableMethods

// ─── 表格列定义 ───────────────────────────────────────────────
const crudSchemas = reactive<CrudSchema[]>([
  {
    field: 'selection',
    table: { type: 'selection' }
  },
  {
    field: 'id',
    label: 'ID',
    table: { width: 70 }
  },
  {
    field: 'student_username',
    label: '学生',
    table: {
      slots: {
        default: (data: any) => (
          <span>
            <span class="font-medium">{data.row.student_username || '-'}</span>
            {data.row.student_name && data.row.student_name !== data.row.student_username && (
              <span class="text-gray-400 text-12px ml-4px">({data.row.student_name})</span>
            )}
          </span>
        )
      }
    }
  },
  {
    field: 'purpose',
    label: '用途',
    table: {
      slots: {
        default: (data: any) => data.row.purpose || '-'
      }
    }
  },
  {
    field: 'status',
    label: '状态',
    table: {
      width: 110,
      slots: {
        default: (data: any) => {
          const cfg = statusConfig[data.row.status as ContainerStatus]
          return cfg ? (
            <ElTag type={cfg.type}>{cfg.label}</ElTag>
          ) : (
            <ElTag type="info">{data.row.status}</ElTag>
          )
        }
      }
    }
  },
  {
    field: 'cpu_percent',
    label: 'CPU 占用',
    table: {
      width: 160,
      slots: {
        default: (data: any) => {
          const val = data.row.cpu_percent ?? 0
          const color = val > 80 ? '#f56c6c' : val > 50 ? '#e6a23c' : '#67c23a'
          return data.row.status === 'running' ? (
            <div class="flex items-center gap-6px">
              <ElProgress
                percentage={Math.min(val, 100)}
                stroke-width={10}
                color={color}
                style="width: 100px; flex-shrink: 0"
                show-text={false}
              />
              <span class="text-12px">{val.toFixed(1)}%</span>
            </div>
          ) : (
            <span class="text-gray-300">-</span>
          )
        }
      }
    }
  },
  {
    field: 'memory_mb',
    label: '内存占用',
    table: {
      width: 170,
      slots: {
        default: (data: any) => {
          const used = data.row.memory_mb ?? 0
          const limit = data.row.memory_limit_mb ?? 2048
          const pct = limit > 0 ? Math.min((used / limit) * 100, 100) : 0
          const color = pct > 80 ? '#f56c6c' : pct > 60 ? '#e6a23c' : '#409eff'
          return data.row.status === 'running' ? (
            <div class="flex items-center gap-6px">
              <ElProgress
                percentage={pct}
                stroke-width={10}
                color={color}
                style="width: 90px; flex-shrink: 0"
                show-text={false}
              />
              <span class="text-12px">
                {used}
                <span class="text-gray-400">/{limit}MB</span>
              </span>
            </div>
          ) : (
            <span class="text-gray-300">-</span>
          )
        }
      }
    }
  },
  {
    field: 'uptime_seconds',
    label: '总运行时长',
    table: {
      width: 110,
      slots: {
        default: (data: any) =>
          data.row.status === 'running' ? (
            <span>{formatUptime(data.row.uptime_seconds)}</span>
          ) : (
            <span class="text-gray-300">-</span>
          )
      }
    }
  },
  {
    field: 'image_name',
    label: '镜像',
    table: {
      slots: {
        default: (data: any) => (
          <span class="text-12px text-gray-500">{data.row.image_name || '-'}</span>
        )
      }
    }
  }
])

const { allSchemas } = useCrudSchemas(crudSchemas)

// ─── 轮询（30 秒刷新，页面不可见时跳过）────────────────────────
const POLL_INTERVAL = 30_000
const pollingTimer = ref<ReturnType<typeof setInterval> | null>(null)

const startPolling = () => {
  pollingTimer.value = setInterval(() => {
    if (document.visibilityState === 'visible') {
      getList()
    }
  }, POLL_INTERVAL)
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

// ─── 批量操作 ─────────────────────────────────────────────────
const getSelectedIds = async (): Promise<number[]> => {
  const elTableRef = await getElTableExpose()
  return elTableRef?.getSelectionRows().map((v: any) => v.id) || []
}

const batchStart = async () => {
  const ids = await getSelectedIds()
  if (!ids.length) return ElMessage.warning('请选择容器')
  await batchStartContainersApi(ids)
  ElMessage.success('批量启动指令已发送')
  getList()
}

const batchStop = async () => {
  const ids = await getSelectedIds()
  if (!ids.length) return ElMessage.warning('请选择容器')
  await batchStopContainersApi(ids)
  ElMessage.success('批量停止指令已发送')
  getList()
}

const batchDelete = async () => {
  const ids = await getSelectedIds()
  if (!ids.length) return ElMessage.warning('请选择容器')
  await ElMessageBox.confirm('确认删除选中的容器吗？此操作不可逆！', '警告', {
    confirmButtonText: '确定删除',
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
    <!-- 工具栏 -->
    <div class="mb-16px flex items-center gap-10px">
      <ElButton type="primary" @click="batchStart">批量启动</ElButton>
      <ElButton type="warning" @click="batchStop">批量停止</ElButton>
      <ElButton type="danger" @click="batchDelete">批量删除</ElButton>
      <ElButton :loading="loading" @click="getList">刷新</ElButton>
      <span class="text-12px text-gray-400 ml-10px">每 30 秒自动刷新</span>
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
</template>
