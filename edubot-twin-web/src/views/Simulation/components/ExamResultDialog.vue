<script setup lang="ts">
/**
 * ExamResultDialog - 考试结果摘要对话框（SDD §8.4）
 * 在 attempt.status 变为 completed / error / aborted 时展示
 */
import { computed } from 'vue'
import { ElButton, ElDescriptions, ElDescriptionsItem, ElDialog, ElTag } from 'element-plus'
import type { AttemptDetail } from '@/api/exam/attempts'

const props = defineProps<{
  visible: boolean
  attempt: AttemptDetail | null
}>()

const emit = defineEmits<{
  (e: 'update:visible', v: boolean): void
  (e: 'close'): void
  (e: 'retake'): void
}>()

const isCompleted = computed(() => props.attempt?.status === 'completed')
const isError = computed(
  () => props.attempt?.status === 'error' || props.attempt?.status === 'aborted'
)

const statusLabel = computed(() => {
  switch (props.attempt?.status) {
    case 'completed':
      return '🎉 考试完成'
    case 'aborted':
      return '⛔ 考试已放弃'
    case 'error':
      return '❌ 评测异常'
    default:
      return '考试结束'
  }
})

const metrics = computed(() => props.attempt?.result_json?.metrics ?? null)

function formatDuration(ms: number | null): string {
  if (ms == null) return '-'
  const s = Math.round(ms / 1000)
  return s < 60 ? `${s}s` : `${Math.floor(s / 60)}m ${s % 60}s`
}
</script>

<template>
  <ElDialog
    :model-value="props.visible"
    :title="statusLabel"
    width="500px"
    @update:model-value="emit('update:visible', $event)"
  >
    <div v-if="props.attempt" class="result-body">
      <!-- 完成状态：显示分数 -->
      <template v-if="isCompleted">
        <div class="score-row">
          <span class="score-label">客观分</span>
          <span class="score-value">{{ props.attempt.objective_score ?? '-' }}</span>
        </div>
        <div class="pass-row">
          <span class="pass-label">通过</span>
          <ElTag :type="props.attempt.pass ? 'success' : 'danger'" size="large">
            {{ props.attempt.pass ? '✅ 是' : '❌ 否' }}
          </ElTag>
        </div>

        <div v-if="props.attempt.summary" class="summary-block">
          <div class="summary-title">评语</div>
          <div class="summary-text">{{ props.attempt.summary }}</div>
        </div>

        <!-- 详细指标 -->
        <div v-if="metrics" class="metrics-block">
          <div class="metrics-title">详细指标</div>
          <ElDescriptions :column="2" border size="small">
            <ElDescriptionsItem v-if="metrics.elapsed_seconds != null" label="耗时">
              {{ metrics.elapsed_seconds.toFixed(1) }}s
            </ElDescriptionsItem>
            <ElDescriptionsItem v-if="metrics.collision_count != null" label="碰撞次数">
              {{ metrics.collision_count }}
            </ElDescriptionsItem>
            <ElDescriptionsItem v-if="metrics.goal_reached != null" label="目标到达">
              {{ metrics.goal_reached ? '✅' : '❌' }}
            </ElDescriptionsItem>
            <ElDescriptionsItem v-if="metrics.path_length != null" label="路径长度">
              {{ metrics.path_length.toFixed(2) }}m
            </ElDescriptionsItem>
          </ElDescriptions>
        </div>

        <div class="duration-row"> 用时：{{ formatDuration(props.attempt.duration_ms) }} </div>
      </template>

      <!-- 错误/放弃状态 -->
      <template v-else-if="isError">
        <div class="error-block">
          <div class="error-code" v-if="props.attempt.error_code">
            错误码：<code>{{ props.attempt.error_code }}</code>
          </div>
          <div class="error-msg" v-if="props.attempt.error_message">
            {{ props.attempt.error_message }}
          </div>
          <div v-else-if="props.attempt.status === 'aborted'" class="error-msg"> 考试已放弃 </div>
        </div>
      </template>
    </div>

    <template #footer>
      <ElButton @click="emit('retake')">重新考试</ElButton>
      <ElButton type="primary" @click="emit('close')">关闭</ElButton>
    </template>
  </ElDialog>
</template>

<style lang="less" scoped>
.result-body {
  .score-row {
    display: flex;
    align-items: baseline;
    gap: 12px;
    margin-bottom: 12px;

    .score-label {
      font-size: 14px;
      color: #909399;
    }
    .score-value {
      font-size: 36px;
      font-weight: bold;
      color: #409eff;
    }
  }

  .pass-row {
    display: flex;
    align-items: center;
    gap: 10px;
    margin-bottom: 16px;
    font-size: 14px;

    .pass-label {
      color: #909399;
    }
  }

  .summary-block {
    margin-bottom: 16px;
    padding: 10px 14px;
    background: var(--el-fill-color-light);
    border-radius: 6px;

    .summary-title {
      font-size: 12px;
      color: #909399;
      margin-bottom: 6px;
    }
    .summary-text {
      font-size: 14px;
      line-height: 1.6;
      color: #e5e5e5;
    }
  }

  .metrics-block {
    margin-bottom: 12px;

    .metrics-title {
      font-size: 13px;
      color: #606266;
      margin-bottom: 8px;
      font-weight: 500;
    }
  }

  .duration-row {
    font-size: 13px;
    color: #909399;
    text-align: right;
  }

  .error-block {
    padding: 12px 16px;
    background: rgba(245, 108, 108, 0.1);
    border-left: 3px solid #f56c6c;
    border-radius: 4px;

    .error-code {
      font-size: 13px;
      color: #606266;
      margin-bottom: 6px;

      code {
        background: rgba(0, 0, 0, 0.05);
        padding: 1px 6px;
        border-radius: 3px;
        font-family: monospace;
      }
    }

    .error-msg {
      font-size: 14px;
      color: #f56c6c;
    }
  }
}
</style>
