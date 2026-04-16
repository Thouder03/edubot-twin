<script setup lang="ts">
/**
 * 教师端：查看学生提交代码（只读）（第14期）
 *
 * 复用 BundleWorkspaceTemplate，传入只读标志，
 * 后端只提供 list/read/download 三个端点，无写操作。
 */
import { computed } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ElButton, ElTag } from 'element-plus'
import BundleWorkspaceTemplate from './components/BundleWorkspaceTemplate.vue'

const route = useRoute()
const router = useRouter()

const attemptId = computed(() => Number(route.params.attempt_id))

// ─── 构造虚拟"单条目"列表，直接跳入文件树模式 ─────────────────────────────
// BundleWorkspaceTemplate 支持 items 列表 + buildApiPrefix；
// 这里我们给一个只有一条的伪 item，让模板直接显示该 attempt 的文件树
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
  `/api/v1/teachers/exam-attempts/${item.id}/submission/files`
</script>

<template>
  <div class="exam-submission-view">
    <!-- 顶部导航 -->
    <div class="submission-header">
      <ElButton @click="router.back()">← 返回复核</ElButton>
      <div class="submission-header__title">
        <span class="font-bold text-16px">学生提交代码</span>
        <ElTag type="info" size="small" class="ml-8px">只读</ElTag>
        <span class="text-13px color-#909399 ml-8px">Attempt #{{ attemptId }}</span>
      </div>
    </div>

    <!-- 文件浏览器（只读模板） -->
    <div class="submission-body">
      <BundleWorkspaceTemplate
        :items="items"
        :list-loading="false"
        :build-api-prefix="buildApiPrefix"
        :protected-paths="[]"
        :readonly="true"
        :auto-enter-first="true"
        title="提交代码"
      >
        <!-- 覆盖 tree-header slot：只写文字说明，不显示上传 -->
        <template #tree-header>
          <span class="text-12px color-#909399">只读模式 — 仅支持预览与下载</span>
        </template>
      </BundleWorkspaceTemplate>
    </div>
  </div>
</template>

<style lang="less" scoped>
.exam-submission-view {
  display: flex;
  flex-direction: column;
  height: 100vh;
  background: var(--el-bg-color-page);
}

.submission-header {
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

.submission-body {
  flex: 1;
  overflow: hidden;

  // 让 ContentWrap 铺满剩余空间
  :deep(.content-wrap) {
    height: 100%;
    overflow: hidden;
  }
}
</style>
