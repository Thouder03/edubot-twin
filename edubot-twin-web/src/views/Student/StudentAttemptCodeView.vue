<script setup lang="ts">
/**
 * StudentAttemptCodeView - 学生端查看提交代码页（第16期）
 *
 * 路由：/student/grades/:exam_id/attempt/:attempt_id/code
 * 功能：只读查看自己当时提交的代码快照，复用 BundleWorkspaceTemplate (readonly=true)
 *
 * apiPrefix 指向学生端 submission 端点：
 *   /api/v1/students/exam-attempts/{id}/submission/files
 */
import { computed } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ElButton, ElTag } from 'element-plus'
import BundleWorkspaceTemplate from '@/views/Teacher/Exams/components/BundleWorkspaceTemplate.vue'

const route = useRoute()
const router = useRouter()

const examId = computed(() => Number(route.params.exam_id))
const attemptId = computed(() => Number(route.params.attempt_id))

interface SubmissionItem {
  id: number
  name: string
}

const items = computed<SubmissionItem[]>(() => [
  {
    id: attemptId.value,
    name: `提交代码 #${attemptId.value}`
  }
])

const buildApiPrefix = (item: SubmissionItem): string =>
  `/api/v1/students/exam-attempts/${item.id}/submission/files`

function goBack() {
  router.push(`/student/grades/${examId.value}`)
}
</script>

<template>
  <div class="student-code-view">
    <!-- 顶部导航 -->
    <div class="student-code-view__header">
      <ElButton @click="goBack">← 返回成绩详情</ElButton>
      <div class="student-code-view__title">
        <span class="font-bold text-16px">我的提交代码</span>
        <ElTag type="info" size="small" class="ml-8px">只读</ElTag>
        <span class="text-13px color-#909399 ml-8px">Attempt #{{ attemptId }}</span>
      </div>
    </div>

    <!-- 文件浏览器（只读） -->
    <div class="student-code-view__body">
      <BundleWorkspaceTemplate
        :items="items"
        :list-loading="false"
        :build-api-prefix="buildApiPrefix"
        :protected-paths="[]"
        :readonly="true"
        :auto-enter-first="true"
        title="提交代码"
      >
        <template #tree-header>
          <span class="text-12px color-#909399">只读模式 — 仅支持预览与下载</span>
        </template>
      </BundleWorkspaceTemplate>
    </div>
  </div>
</template>

<style lang="less" scoped>
.student-code-view {
  display: flex;
  flex-direction: column;
  height: 100vh;
  background: var(--el-bg-color-page);

  &__header {
    display: flex;
    align-items: center;
    gap: 16px;
    padding: 12px 20px;
    background: var(--el-bg-color);
    border-bottom: 1px solid var(--el-border-color-lighter);
    flex-shrink: 0;

    &__title {
      display: flex;
      align-items: center;
    }
  }

  &__body {
    flex: 1;
    overflow: hidden;

    :deep(.content-wrap) {
      height: 100%;
      overflow: hidden;
    }
  }
}
</style>
