<script setup lang="ts">
/**
 * StudentAttemptCard - 单次考试尝试卡片（第16期）
 *
 * 展示：分数、评测脚本评语、教师评语、自定义字段、查看代码按钮
 */
import { ElButton, ElTag } from 'element-plus'
import type { StudentAttemptGradeDetailItem } from '@/api/student/grades'
import MetricsKvTable from '@/components/Grade/MetricsKvTable.vue'

defineProps<{
  item: StudentAttemptGradeDetailItem
  examId: number
  index: number
}>()

const emit = defineEmits<{
  viewCode: [attemptId: number]
}>()

const STATUS_LABEL: Record<string, string> = {
  pending: '待开始',
  running: '进行中',
  scoring: '评测中',
  completed: '已完成',
  reviewed: '已复核',
  error: '评测异常',
  aborted: '已放弃',
}
const STATUS_TYPE: Record<string, 'success' | 'warning' | 'danger' | 'info'> = {
  completed: 'success',
  reviewed: 'success',
  error: 'danger',
  aborted: 'info',
  running: 'warning',
  scoring: 'warning',
  pending: 'info',
}

function formatDate(iso: string | null): string {
  if (!iso) return '-'
  return new Date(iso).toLocaleString('zh-CN', { hour12: false })
}

function formatDuration(ms: number | null): string {
  if (ms == null) return '-'
  return `${Math.round(ms / 1000)}s`
}
</script>

<template>
  <div class="attempt-card">
    <!-- 卡片头部 -->
    <div class="attempt-card__header">
      <span class="attempt-card__title">尝试 #{{ index + 1 }}</span>
      <span class="attempt-card__time">（{{ formatDate(item.created_at) }}）</span>
      <ElTag :type="STATUS_TYPE[item.status] ?? 'info'" size="small" class="ml-2">
        {{ STATUS_LABEL[item.status] ?? item.status }}
      </ElTag>
    </div>

    <!-- 分数行 -->
    <div class="attempt-card__scores">
      <span>客观分：<strong>{{ item.objective_score ?? '-' }}</strong></span>
      <span class="ml-4">教师评分：<strong>{{ item.manual_score ?? '-' }}</strong></span>
      <span class="ml-4">最终分：<strong>{{ item.final_score ?? '-' }}</strong></span>
      <span class="ml-4">
        Pass：
        <span v-if="item.pass === true">✅</span>
        <span v-else-if="item.pass === false">❌</span>
        <span v-else>-</span>
      </span>
      <span class="ml-4">耗时：{{ formatDuration(item.duration_ms) }}</span>
    </div>

    <!-- 评测脚本评语 -->
    <div class="attempt-card__section">
      <div class="attempt-card__section-title">📝 评测脚本评语</div>
      <div class="attempt-card__comment">
        {{ item.summary || '（无评测评语）' }}
      </div>
    </div>

    <!-- 教师评语 -->
    <div class="attempt-card__section">
      <div class="attempt-card__section-title">👨‍🏫 教师评语</div>
      <div class="attempt-card__comment" :class="{ 'text-#909399': !item.teacher_comment }">
        {{ item.teacher_comment || '暂无教师评语' }}
      </div>
    </div>

    <!-- 指标 -->
    <div v-if="item.metrics" class="attempt-card__section">
      <div class="attempt-card__section-title">📈 指标</div>
      <div class="attempt-card__comment attempt-card__comment--metrics">
        <MetricsKvTable :metrics="item.metrics" />
      </div>
    </div>

    <!-- 自定义字段 -->
    <div
      v-if="item.custom_fields && Object.keys(item.custom_fields).length > 0"
      class="attempt-card__section"
    >
      <div class="attempt-card__section-title">📋 自定义字段</div>
      <div class="attempt-card__comment attempt-card__comment--metrics">
        <MetricsKvTable :metrics="item.custom_fields" />
      </div>
    </div>

    <!-- 底部操作 -->
    <div class="attempt-card__footer">
      <ElButton
        v-if="item.has_code_snapshot"
        size="small"
        type="primary"
        plain
        @click="emit('viewCode', item.attempt_id)"
      >
        📂 查看提交代码
      </ElButton>
    </div>
  </div>
</template>

<style scoped>
.attempt-card {
  border: 1px solid #e4e7ed;
  border-radius: 8px;
  padding: 16px 20px;
  background: #fff;
  margin-bottom: 16px;
}
.attempt-card__header {
  display: flex;
  align-items: center;
  margin-bottom: 10px;
}
.attempt-card__title {
  font-weight: 600;
  font-size: 15px;
  color: #303133;
}
.attempt-card__time {
  font-size: 13px;
  color: #909399;
  margin-left: 4px;
}
.attempt-card__scores {
  font-size: 14px;
  color: #606266;
  margin-bottom: 12px;
}
.attempt-card__scores strong {
  color: #303133;
}
.attempt-card__section {
  margin-bottom: 10px;
}
.attempt-card__section-title {
  font-size: 13px;
  font-weight: 600;
  color: #606266;
  margin-bottom: 4px;
}
.attempt-card__comment {
  font-size: 13px;
  color: #303133;
  line-height: 1.6;
  background: #f8f9fa;
  border-radius: 4px;
  padding: 8px 12px;
}
.attempt-card__comment--metrics {
  background: transparent;
  padding: 4px 0;
}
.attempt-card__footer {
  display: flex;
  justify-content: flex-end;
  margin-top: 12px;
  padding-top: 10px;
  border-top: 1px solid #f0f2f5;
}
</style>
