<script setup lang="ts">
/**
 * TeacherGradePreview - 教师端成绩预览列表页（第16期）
 *
 * 路由：/teacher/exams/grade-preview
 * 功能：横向比较多学生成绩，行内可展开查看完整 result_json（含 custom_fields）
 */
import { ref, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import {
  ElButton,
  ElSwitch,
  ElSelect,
  ElOption,
  ElTable,
  ElTableColumn,
  ElTag,
  ElPagination
} from 'element-plus'
import { ContentWrap } from '@/components/ContentWrap'
import {
  getGradePreviewApi,
  type GradePreviewItem,
  type GradePreviewQueryParams
} from '@/api/exam/gradePreview'
import { getExamListApi } from '@/api/exam'
import type { ExamListItem } from '@/api/exam/types'
import GradeResultExpand from './components/GradeResultExpand.vue'

const router = useRouter()

// ─── 考试下拉选项 ─────────────────────────────────────────────────────────────
const examOptions = ref<ExamListItem[]>([])
async function loadExamOptions() {
  const res = await getExamListApi({ page: 1, page_size: 200 })
  examOptions.value = res.data?.items ?? []
}

// ─── 筛选状态 ─────────────────────────────────────────────────────────────────
const filterExamId = ref<number | undefined>(undefined)
const filterStudentId = ref<number | undefined>(undefined)
const bestOnly = ref(true)
const page = ref(1)
const pageSize = ref(20)

// ─── 列表状态 ─────────────────────────────────────────────────────────────────
const loading = ref(false)
const items = ref<GradePreviewItem[]>([])
const total = ref(0)

async function load() {
  loading.value = true
  try {
    const params: Record<string, unknown> = {
      page: page.value,
      page_size: pageSize.value,
      best_only: bestOnly.value
    }
    if (filterExamId.value !== undefined) params.exam_id = filterExamId.value
    if (filterStudentId.value !== undefined) params.student_id = filterStudentId.value
    const res = await getGradePreviewApi(params as GradePreviewQueryParams)
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

function goReview(row: GradePreviewItem) {
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
  <ContentWrap title="成绩预览">
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

      <div class="flex items-center gap-2 ml-2">
        <ElSwitch v-model="bestOnly" @change="onSearch" />
        <span class="text-13px text-#606266">只显示考试最高客观成绩</span>
      </div>

      <ElButton type="primary" @click="onSearch">查询</ElButton>
    </div>

    <!-- 表格（行内展开） -->
    <ElTable v-loading="loading" :data="items" border row-key="attempt_id">
      <ElTableColumn type="expand">
        <template #default="{ row }">
          <GradeResultExpand :row="row" />
        </template>
      </ElTableColumn>

      <ElTableColumn label="学生" min-width="100">
        <template #default="{ row }">
          {{ row.student.real_name || row.student.username }}
        </template>
      </ElTableColumn>
      <ElTableColumn label="账号" prop="student.username" min-width="90" />
      <ElTableColumn label="考试" prop="exam_name" min-width="140" show-overflow-tooltip />
      <ElTableColumn label="客观分" width="90" align="right">
        <template #default="{ row }">{{ row.objective_score ?? '-' }}</template>
      </ElTableColumn>
      <ElTableColumn label="教师评分" width="90" align="right">
        <template #default="{ row }">{{ row.manual_score ?? '-' }}</template>
      </ElTableColumn>
      <ElTableColumn label="最终分" width="90" align="right">
        <template #default="{ row }">{{ row.final_score ?? '-' }}</template>
      </ElTableColumn>
      <ElTableColumn label="Pass" width="70" align="center">
        <template #default="{ row }">
          <span v-if="row.pass === true">✅</span>
          <span v-else-if="row.pass === false">❌</span>
          <span v-else>-</span>
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
      <ElTableColumn label="评语摘要" min-width="160" show-overflow-tooltip>
        <template #default="{ row }">
          <span class="text-#606266">{{ row.teacher_comment || row.summary || '-' }}</span>
        </template>
      </ElTableColumn>
      <ElTableColumn label="完成时间" min-width="150">
        <template #default="{ row }">{{ formatDate(row.ended_at) }}</template>
      </ElTableColumn>
      <ElTableColumn label="操作" width="80" fixed="right">
        <template #default="{ row }">
          <ElButton link size="small" type="primary" @click="goReview(row)">详情</ElButton>
        </template>
      </ElTableColumn>
    </ElTable>

    <!-- 分页 -->
    <div class="flex justify-end mt-4">
      <ElPagination
        v-model:current-page="page"
        v-model:page-size="pageSize"
        :total="total"
        :page-sizes="[10, 20, 50, 100]"
        layout="total, sizes, prev, pager, next"
        @current-change="onPageChange"
        @size-change="onSizeChange"
      />
    </div>
  </ContentWrap>
</template>
