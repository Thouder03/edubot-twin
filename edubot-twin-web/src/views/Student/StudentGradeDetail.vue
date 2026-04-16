<script setup lang="ts">
/**
 * StudentGradeDetail - 学生端考试成绩详情页（第16期）
 *
 * 路由：/student/grades/:exam_id
 * 功能：展示该考试所有尝试（含评语），提供"查看代码"入口
 */
import { ref, computed, onMounted } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ElButton, ElEmpty } from 'element-plus'
import { ContentWrap } from '@/components/ContentWrap'
import { getMyGradeDetailApi, type StudentAttemptGradeDetailItem } from '@/api/student/grades'
import StudentAttemptCard from './components/StudentAttemptCard.vue'

const route = useRoute()
const router = useRouter()

const examId = computed(() => Number(route.params.exam_id))

const loading = ref(false)
const attempts = ref<StudentAttemptGradeDetailItem[]>([])

async function load() {
  loading.value = true
  try {
    const res = await getMyGradeDetailApi(examId.value)
    attempts.value = res.data ?? []
  } finally {
    loading.value = false
  }
}

function goBack() {
  router.push('/student/grades')
}

function viewCode(attemptId: number) {
  router.push(`/student/grades/${examId.value}/attempt/${attemptId}/code`)
}

onMounted(load)
</script>

<template>
  <ContentWrap>
    <!-- 顶部导航 -->
    <div class="flex items-center gap-3 mb-6">
      <ElButton @click="goBack">← 返回</ElButton>
      <span class="text-18px font-600 color-#303133">考试成绩详情</span>
    </div>

    <div v-loading="loading">
      <ElEmpty
        v-if="!loading && attempts.length === 0"
        description="该考试暂无尝试记录"
        class="py-12"
      />

      <div v-else>
        <StudentAttemptCard
          v-for="(item, idx) in attempts"
          :key="item.attempt_id"
          :item="item"
          :exam-id="examId"
          :index="idx"
          @view-code="viewCode"
        />
      </div>
    </div>
  </ContentWrap>
</template>
