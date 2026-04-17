<script setup lang="ts">
/**
 * ExamAttemptsManager - 考试尝试管理页（第15期 S1）
 *
 * 功能：
 * - 分页列表：exam / status 筛选、批量勾选删除
 * - 一键删除全局/当前考试的所有异常尝试（error/aborted）
 * - 点击"复核"跳转到 ExamAttemptReview.vue
 */
import { ref, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import {
  ElButton,
  ElSwitch,
  ElTable,
  ElTableColumn,
  ElTag,
  ElPagination,
  ElSelect,
  ElOption,
  ElMessage,
  ElMessageBox
} from 'element-plus'
import { ContentWrap } from '@/components/ContentWrap'
import {
  getAllAttemptsApi,
  batchDeleteAttemptsApi,
  type TeacherAttemptListItem
} from '@/api/exam/attempts'
import { deleteAbnormalAttemptsApi } from '@/api/exam/attemptManager'
import { getExamListApi } from '@/api/exam'
import type { ExamListItem } from '@/api/exam/types'

const router = useRouter()

// ─── 考试下拉选项 ─────────────────────────────────────────────────────────────
const examOptions = ref<ExamListItem[]>([])
async function loadExamOptions() {
  const res = await getExamListApi({ page: 1, page_size: 200 })
  examOptions.value = res.data?.items ?? []
}

// ─── 筛选状态 ─────────────────────────────────────────────────────────────────
const filterExamId = ref<number | undefined>(undefined)
const filterStatus = ref('')
const bestOnly = ref(false)
const page = ref(1)
const pageSize = ref(20)

// ─── 列表状态 ─────────────────────────────────────────────────────────────────
const loading = ref(false)
const items = ref<TeacherAttemptListItem[]>([])
const total = ref(0)
const selected = ref<TeacherAttemptListItem[]>([])

async function load() {
  loading.value = true
  try {
    const params: Record<string, unknown> = {
      page: page.value,
      page_size: pageSize.value,
      best_only: bestOnly.value
    }
    if (filterExamId.value !== undefined) params.exam_id = filterExamId.value
    if (filterStatus.value) params.status = filterStatus.value

    const res = await getAllAttemptsApi(params as Parameters<typeof getAllAttemptsApi>[0])
    items.value = res.data?.items ?? []
    total.value = res.data?.total ?? 0
  } finally {
    loading.value = false
  }
}

function onPageChange(p: number) {
  page.value = p
  load()
}

function onSizeChange(s: number) {
  pageSize.value = s
  page.value = 1
  load()
}

function onSearch() {
  page.value = 1
  load()
}

function onSelectionChange(rows: TeacherAttemptListItem[]) {
  selected.value = rows
}

// ─── 批量删除 ─────────────────────────────────────────────────────────────────
const batchDeleteLoading = ref(false)

async function handleBatchDelete() {
  if (!selected.value.length) return
  await ElMessageBox.confirm(
    `确认删除选中的 ${selected.value.length} 条尝试记录（含 artifacts / submission 文件）？此操作不可逆。`,
    '批量删除确认',
    { confirmButtonText: '删除', cancelButtonText: '取消', type: 'warning' }
  )
  batchDeleteLoading.value = true
  try {
    await batchDeleteAttemptsApi({ attempt_ids: selected.value.map((a) => a.attempt_id) })
    ElMessage.success(`已删除 ${selected.value.length} 条记录`)
    selected.value = []
    load()
  } catch {
    ElMessage.error('删除失败，请重试')
  } finally {
    batchDeleteLoading.value = false
  }
}

// ─── 一键删除异常尝试 ─────────────────────────────────────────────────────────
const abnormalDeleteLoading = ref(false)

async function handleDeleteAbnormal() {
  const scopeText = filterExamId.value ? `当前考试（id=${filterExamId.value}）` : '全部考试'
  await ElMessageBox.confirm(
    `将删除${scopeText}下所有 error 和 aborted 状态的尝试（含 artifacts / submission 文件），此操作不可逆。是否继续？`,
    '删除异常尝试确认',
    { confirmButtonText: '删除', cancelButtonText: '取消', type: 'error' }
  )
  abnormalDeleteLoading.value = true
  try {
    const res = await deleteAbnormalAttemptsApi({ exam_id: filterExamId.value ?? undefined })
    ElMessage.success(`已删除 ${res.data?.count ?? 0} 条异常尝试`)
    load()
  } catch {
    ElMessage.error('操作失败，请重试')
  } finally {
    abnormalDeleteLoading.value = false
  }
}

// ─── 单条删除（复用批量接口） ──────────────────────────────────────────────────
async function handleSingleDelete(row: TeacherAttemptListItem) {
  await ElMessageBox.confirm(`确认删除该尝试记录（id=${row.attempt_id}）？`, '删除确认', {
    confirmButtonText: '删除',
    cancelButtonText: '取消',
    type: 'warning'
  })
  await batchDeleteAttemptsApi({ attempt_ids: [row.attempt_id] })
  ElMessage.success('已删除')
  load()
}

// ─── 跳转复核页 ───────────────────────────────────────────────────────────────
function goReview(row: TeacherAttemptListItem) {
  router.push(`/teacher/exams/attempts/${row.attempt_id}/review`)
}

// ─── 辅助 ─────────────────────────────────────────────────────────────────────
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
const REVIEW_LABEL: Record<string, string> = { pending: '待复核', reviewed: '已复核' }
const REVIEW_TYPE: Record<string, 'warning' | 'success' | 'info'> = {
  pending: 'warning',
  reviewed: 'success'
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

onMounted(() => {
  loadExamOptions()
  load()
})
</script>

<template>
  <ContentWrap title="考试尝试管理">
    <!-- 筛选栏 -->
    <div class="flex gap-3 mb-4 flex-wrap items-center">
      <ElSelect
        v-model="filterExamId"
        placeholder="考试：全部"
        clearable
        style="width: 200px"
        @change="onSearch"
      >
        <ElOption v-for="e in examOptions" :key="e.id" :label="e.name" :value="e.id" />
      </ElSelect>

      <ElSelect
        v-model="filterStatus"
        placeholder="状态：全部"
        clearable
        style="width: 160px"
        @change="onSearch"
      >
        <ElOption label="已完成" value="completed" />
        <ElOption label="已放弃" value="aborted" />
        <ElOption label="评测异常" value="error" />
        <ElOption label="评测中" value="running" />
        <ElOption label="准备中" value="pending" />
      </ElSelect>

      <div class="flex items-center gap-2 ml-2">
        <ElSwitch v-model="bestOnly" @change="onSearch" />
        <span class="text-13px text-#606266">只显示考试最高客观成绩</span>
      </div>

      <ElButton type="primary" @click="onSearch">查询</ElButton>
    </div>

    <!-- 操作栏 -->
    <div class="flex gap-3 mb-4">
      <ElButton
        type="danger"
        plain
        :disabled="!selected.length"
        :loading="batchDeleteLoading"
        @click="handleBatchDelete"
      >
        批量删除（{{ selected.length }}）
      </ElButton>
      <ElButton type="warning" :loading="abnormalDeleteLoading" @click="handleDeleteAbnormal">
        ⚠ 一键删除异常尝试
      </ElButton>
    </div>

    <!-- 表格 -->
    <ElTable v-loading="loading" :data="items" border @selection-change="onSelectionChange">
      <ElTableColumn type="selection" width="48" />
      <ElTableColumn label="学生姓名" min-width="90">
        <template #default="{ row }">
          {{ row.student.real_name || row.student.username }}
        </template>
      </ElTableColumn>
      <ElTableColumn label="账号" prop="student.username" min-width="90" />
      <ElTableColumn label="考试名称" min-width="140" show-overflow-tooltip>
        <template #default="{ row }">
          {{ examOptions.find((e) => e.id === row.exam_id)?.name ?? `#${row.exam_id}` }}
        </template>
      </ElTableColumn>
      <ElTableColumn label="状态" width="110" align="center">
        <template #default="{ row }">
          <ElTag :type="STATUS_TYPE[row.status] ?? 'info'">
            {{ STATUS_LABEL[row.status] ?? row.status }}
          </ElTag>
        </template>
      </ElTableColumn>
      <ElTableColumn label="客观分" width="80" align="right">
        <template #default="{ row }">
          {{ row.objective_score ?? '-' }}
        </template>
      </ElTableColumn>
      <ElTableColumn label="教师评分" width="80" align="right">
        <template #default="{ row }">
          {{ row.manual_score ?? '-' }}
        </template>
      </ElTableColumn>
      <ElTableColumn label="最终分" width="80" align="right">
        <template #default="{ row }">
          {{ row.final_score ?? '-' }}
        </template>
      </ElTableColumn>
      <ElTableColumn label="复核状态" width="100" align="center">
        <template #default="{ row }">
          <ElTag
            v-if="row.review_status && row.review_status !== 'not_required'"
            :type="REVIEW_TYPE[row.review_status] ?? 'info'"
            size="small"
          >
            {{ REVIEW_LABEL[row.review_status] ?? row.review_status }}
          </ElTag>
          <span v-else>-</span>
        </template>
      </ElTableColumn>
      <ElTableColumn label="耗时" width="90">
        <template #default="{ row }">{{ formatDuration(row.duration_ms) }}</template>
      </ElTableColumn>
      <ElTableColumn label="创建时间" min-width="160">
        <template #default="{ row }">{{ formatDate(row.created_at) }}</template>
      </ElTableColumn>
      <ElTableColumn label="操作" width="120" fixed="right">
        <template #default="{ row }">
          <ElButton
            v-if="row.status === 'completed' || row.status === 'reviewed'"
            type="primary"
            link
            size="small"
            @click="goReview(row)"
          >
            复核
          </ElButton>
          <ElButton v-else type="danger" link size="small" @click="handleSingleDelete(row)">
            删除
          </ElButton>
        </template>
      </ElTableColumn>
    </ElTable>

    <!-- 分页 -->
    <div class="flex justify-end mt-4">
      <ElPagination
        v-model:current-page="page"
        v-model:page-size="pageSize"
        :total="total"
        :page-sizes="[10, 20, 50]"
        layout="total, sizes, prev, pager, next"
        @current-change="onPageChange"
        @size-change="onSizeChange"
      />
    </div>
  </ContentWrap>
</template>
