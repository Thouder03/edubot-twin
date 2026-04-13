<script setup lang="ts">
/**
 * AttemptList - 运行记录列表面板（教师端，SDD §8.6）
 *
 * 显示该考试的所有学生尝试，点击行打开 AttemptDetailDialog。
 */
import { ref, watch, onMounted } from 'vue'
import {
  ElButton,
  ElTable,
  ElTableColumn,
  ElTag,
  ElPagination,
  ElEmpty,
  ElSelect,
  ElOption
} from 'element-plus'
import { getExamAttemptsApi } from '@/api/exam/attempts'
import type { TeacherAttemptListItem } from '@/api/exam/attempts'
import AttemptDetailDialog from './AttemptDetailDialog.vue'

const props = defineProps<{
  examId: number
}>()

const loading = ref(false)
const items = ref<TeacherAttemptListItem[]>([])
const total = ref(0)
const page = ref(1)
const pageSize = ref(20)
const statusFilter = ref('')

const selectedAttemptId = ref<number | null>(null)
const showDetail = ref(false)

const STATUS_LABEL: Record<string, string> = {
  pending: '准备中',
  running: '评测中',
  scoring: '计分中',
  completed: '已完成',
  aborted: '已放弃',
  error: '评测异常'
}
const STATUS_TYPE: Record<string, 'success' | 'warning' | 'info' | 'danger'> = {
  completed: 'success',
  running: 'warning',
  error: 'danger',
  aborted: 'danger',
  pending: 'info',
  scoring: 'info'
}

function formatDate(iso: string | null): string {
  if (!iso) return '-'
  return new Date(iso).toLocaleString('zh-CN', { hour12: false })
}

function formatDuration(ms: number | null): string {
  if (ms == null) return '-'
  const s = Math.round(ms / 1000)
  return s < 60 ? `${s}s` : `${Math.floor(s / 60)}m ${s % 60}s`
}

async function load() {
  loading.value = true
  try {
    const res = await getExamAttemptsApi(props.examId, {
      page: page.value,
      page_size: pageSize.value,
      status: statusFilter.value || undefined
    })
    items.value = res.data?.items ?? []
    total.value = res.data?.total ?? 0
  } catch {
    items.value = []
  } finally {
    loading.value = false
  }
}

function handleRowClick(row: TeacherAttemptListItem) {
  selectedAttemptId.value = row.attempt_id
  showDetail.value = true
}

watch([page, pageSize, statusFilter], load)
onMounted(load)
</script>

<template>
  <div class="attempt-list">
    <!-- 工具栏 -->
    <div class="attempt-list__toolbar">
      <ElSelect
        v-model="statusFilter"
        placeholder="全部状态"
        clearable
        size="small"
        style="width: 130px"
        @change="page = 1"
      >
        <ElOption v-for="(label, key) in STATUS_LABEL" :key="key" :label="label" :value="key" />
      </ElSelect>
      <ElButton size="small" @click="load">刷新</ElButton>
    </div>

    <!-- 表格 -->
    <ElTable
      v-loading="loading"
      :data="items"
      size="small"
      stripe
      highlight-current-row
      style="width: 100%"
      @row-click="handleRowClick"
    >
      <ElTableColumn label="ID" prop="attempt_id" width="70" />
      <ElTableColumn label="学生" min-width="100">
        <template #default="{ row }">
          {{ row.student.real_name || row.student.username }}
        </template>
      </ElTableColumn>
      <ElTableColumn label="状态" width="90">
        <template #default="{ row }">
          <ElTag :type="STATUS_TYPE[row.status]" size="small">
            {{ STATUS_LABEL[row.status] ?? row.status }}
          </ElTag>
        </template>
      </ElTableColumn>
      <ElTableColumn label="客观分" prop="objective_score" width="72">
        <template #default="{ row }">{{ row.objective_score ?? '-' }}</template>
      </ElTableColumn>
      <ElTableColumn label="通过" width="60">
        <template #default="{ row }">
          <span v-if="row.pass != null">{{ row.pass ? '✅' : '❌' }}</span>
          <span v-else>-</span>
        </template>
      </ElTableColumn>
      <ElTableColumn label="用时" width="72">
        <template #default="{ row }">{{ formatDuration(row.duration_ms) }}</template>
      </ElTableColumn>
      <ElTableColumn label="时间" min-width="150">
        <template #default="{ row }">{{ formatDate(row.created_at) }}</template>
      </ElTableColumn>
    </ElTable>

    <ElEmpty v-if="!loading && items.length === 0" description="暂无运行记录" :image-size="60" />

    <!-- 分页 -->
    <div v-if="total > pageSize" class="attempt-list__pagination">
      <ElPagination
        v-model:current-page="page"
        v-model:page-size="pageSize"
        :total="total"
        :page-sizes="[20, 50, 100]"
        layout="total, sizes, prev, pager, next"
        small
      />
    </div>

    <!-- 详情弹窗 -->
    <AttemptDetailDialog v-model:visible="showDetail" :attempt-id="selectedAttemptId" />
  </div>
</template>

<style lang="less" scoped>
.attempt-list {
  &__toolbar {
    display: flex;
    align-items: center;
    gap: 8px;
    margin-bottom: 10px;
  }

  &__pagination {
    margin-top: 10px;
    display: flex;
    justify-content: flex-end;
  }

  :deep(.el-table__row) {
    cursor: pointer;
  }
}
</style>
