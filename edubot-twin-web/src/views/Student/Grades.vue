<script setup lang="ts">
/**
 * Grades - 学生端成绩预览列表页（第16期）
 *
 * 路由：/student/grades
 * 功能：展示当前学生所有已完成考试的最高分摘要，点击行跳转成绩详情页
 */
import { ref, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import {
  ElTable,
  ElTableColumn,
  ElTag,
  ElTooltip,
  ElEmpty,
} from 'element-plus'
import { ContentWrap } from '@/components/ContentWrap'
import { getMyGradeSummaryApi, type StudentGradeSummaryItem } from '@/api/student/grades'

const router = useRouter()

const loading = ref(false)
const items = ref<StudentGradeSummaryItem[]>([])

async function load() {
  loading.value = true
  try {
    const res = await getMyGradeSummaryApi()
    items.value = res.data ?? []
  } finally {
    loading.value = false
  }
}

function goDetail(row: StudentGradeSummaryItem) {
  router.push(`/student/grades/${row.exam_id}`)
}

function formatDate(iso: string | null): string {
  if (!iso) return '-'
  return new Date(iso).toLocaleDateString('zh-CN')
}

function truncate(text: string | null, len = 100): string {
  if (!text) return '-'
  return text.length > len ? text.slice(0, len) + '…' : text
}

const STATUS_LABEL: Record<string, string> = {
  completed: '已完成',
  reviewed: '已复核',
}

onMounted(load)
</script>

<template>
  <ContentWrap title="我的成绩">
    <div v-loading="loading">
      <ElEmpty
        v-if="!loading && items.length === 0"
        description="暂无成绩，完成考试后在此查看"
        class="py-12"
      />

      <ElTable
        v-else
        :data="items"
        border
        row-key="exam_id"
        row-class-name="cursor-pointer"
        @row-click="goDetail"
      >
        <ElTableColumn label="考试名称" prop="exam_name" min-width="160" show-overflow-tooltip />
        <ElTableColumn label="最高分" width="90" align="right">
          <template #default="{ row }">
            {{ row.objective_score ?? '-' }}
          </template>
        </ElTableColumn>
        <ElTableColumn label="教师评分" width="90" align="right">
          <template #default="{ row }">
            {{ row.manual_score ?? '-' }}
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
        <ElTableColumn label="评测评语" min-width="180">
          <template #default="{ row }">
            <ElTooltip
              v-if="row.summary && row.summary.length > 100"
              :content="row.summary"
              placement="top"
              :show-after="300"
            >
              <span class="text-#606266 cursor-pointer">{{ truncate(row.summary) }}</span>
            </ElTooltip>
            <span v-else class="text-#606266">{{ row.summary || '-' }}</span>
            <!-- 教师评语标记 -->
            <ElTooltip
              v-if="row.teacher_comment"
              content="教师有评语，点击查看"
              placement="top"
            >
              <span class="ml-1 text-#409eff cursor-pointer">📝</span>
            </ElTooltip>
          </template>
        </ElTableColumn>
        <ElTableColumn label="状态" width="90" align="center">
          <template #default="{ row }">
            <ElTag type="success" size="small">
              {{ STATUS_LABEL[row.status] ?? row.status }}
            </ElTag>
          </template>
        </ElTableColumn>
        <ElTableColumn label="完成时间" width="110" align="center">
          <template #default="{ row }">{{ formatDate(row.ended_at) }}</template>
        </ElTableColumn>
      </ElTable>

      <div v-if="items.length > 0" class="text-center text-13px text-#909399 mt-3">
        点击任意行查看该考试的所有尝试详情
      </div>
    </div>
  </ContentWrap>
</template>

<style scoped>
:deep(.cursor-pointer) {
  cursor: pointer;
}
:deep(.cursor-pointer:hover td) {
  background: #f5f7fa !important;
}
</style>
