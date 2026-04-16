<script setup lang="ts">
/**
 * ExamReviewList - 考试结果复核列表页（第15期 S3）
 *
 * 功能：
 * - 每学生每考试只展示客观分最高的尝试
 * - 默认"未复核优先"排序
 * - 支持按考试/复核状态筛选、多种排序方式
 * - 点击"复核/查看"跳转到 ExamAttemptReview.vue
 */
import { ref, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import {
  ElButton,
  ElTable,
  ElTableColumn,
  ElTag,
  ElPagination,
  ElSelect,
  ElOption
} from 'element-plus'
import { ContentWrap } from '@/components/ContentWrap'
import { getExamReviewListApi, type ExamReviewListItem } from '@/api/exam/attemptManager'
import { getExamListApi } from '@/api/exam'
import type { ExamListItem } from '@/api/exam/types'

const router = useRouter()

// ─── 考试下拉选项 ─────────────────────────────────────────────────────────────
const examOptions = ref<ExamListItem[]>([])
async function loadExamOptions() {
  const res = await getExamListApi({ page: 1, page_size: 200 })
  examOptions.value = res.data?.items ?? []
}

// ─── 筛选 & 排序状态 ──────────────────────────────────────────────────────────
const filterExamId = ref<number | undefined>(undefined)
const filterReviewStatus = ref('')
const sort = ref('review_pending_first')
const page = ref(1)
const pageSize = ref(20)

// ─── 列表状态 ─────────────────────────────────────────────────────────────────
const loading = ref(false)
const items = ref<ExamReviewListItem[]>([])
const total = ref(0)

async function load() {
  loading.value = true
  try {
    const params: Record<string, unknown> = {
      page: page.value,
      page_size: pageSize.value,
      sort: sort.value
    }
    if (filterExamId.value !== undefined) params.exam_id = filterExamId.value
    if (filterReviewStatus.value) params.review_status = filterReviewStatus.value

    const res = await getExamReviewListApi(params as Parameters<typeof getExamReviewListApi>[0])
    items.value = res.data?.items ?? []
    total.value = res.data?.total ?? 0
  } finally {
    loading.value = false
  }
}

function onSearch() {
  page.value = 1
  load()
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

function goReview(row: ExamReviewListItem) {
  router.push(`/teacher/exams/attempts/${row.attempt_id}/review`)
}

// ─── 辅助 ─────────────────────────────────────────────────────────────────────
const REVIEW_LABEL: Record<string, string> = { pending: '待复核', reviewed: '已复核' }
const REVIEW_TYPE: Record<string, 'warning' | 'success'> = {
  pending: 'warning',
  reviewed: 'success'
}

function formatDate(iso: string | null): string {
  if (!iso) return '-'
  return new Date(iso).toLocaleString('zh-CN', { hour12: false })
}

onMounted(() => {
  loadExamOptions()
  load()
})
</script>

<template>
  <ContentWrap title="考试结果复核列表">
    <!-- 筛选栏 -->
    <div class="flex gap-3 mb-4 flex-wrap">
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
        v-model="filterReviewStatus"
        placeholder="复核状态：全部"
        clearable
        style="width: 160px"
        @change="onSearch"
      >
        <ElOption label="待复核" value="pending" />
        <ElOption label="已复核" value="reviewed" />
      </ElSelect>

      <ElSelect v-model="sort" style="width: 160px" @change="onSearch">
        <ElOption label="未复核优先" value="review_pending_first" />
        <ElOption label="客观分从高到低" value="score_desc" />
        <ElOption label="客观分从低到高" value="score_asc" />
        <ElOption label="最新创建在前" value="created_at_desc" />
      </ElSelect>

      <ElButton type="primary" @click="onSearch">查询</ElButton>
    </div>

    <!-- 表格 -->
    <ElTable v-loading="loading" :data="items" border row-key="attempt_id">
      <ElTableColumn label="学生姓名" min-width="90">
        <template #default="{ row }">
          {{ row.student.real_name || row.student.username }}
        </template>
      </ElTableColumn>
      <ElTableColumn label="账号" prop="student.username" min-width="90" />
      <ElTableColumn label="考试名称" prop="exam_name" min-width="140" show-overflow-tooltip />
      <ElTableColumn label="客观分" width="90" align="right">
        <template #default="{ row }">
          {{ row.objective_score ?? '-' }}
        </template>
      </ElTableColumn>
      <ElTableColumn label="最终分" width="90" align="right">
        <template #default="{ row }">
          {{ row.final_score ?? '-' }}
        </template>
      </ElTableColumn>
      <ElTableColumn label="Pass" width="70" align="center">
        <template #default="{ row }">
          <span v-if="row.pass === true">✅</span>
          <span v-else-if="row.pass === false">❌</span>
          <span v-else>-</span>
        </template>
      </ElTableColumn>
      <ElTableColumn label="复核状态" width="110" align="center">
        <template #default="{ row }">
          <ElTag :type="REVIEW_TYPE[row.review_status] ?? 'info'" size="small">
            {{ REVIEW_LABEL[row.review_status] ?? row.review_status }}
          </ElTag>
        </template>
      </ElTableColumn>
      <ElTableColumn label="创建时间" min-width="160">
        <template #default="{ row }">{{ formatDate(row.created_at) }}</template>
      </ElTableColumn>
      <ElTableColumn label="操作" width="90" fixed="right">
        <template #default="{ row }">
          <ElButton
            :type="row.review_status === 'pending' ? 'primary' : 'default'"
            link
            size="small"
            @click="goReview(row)"
          >
            {{ row.review_status === 'reviewed' ? '查看' : '复核' }}
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
