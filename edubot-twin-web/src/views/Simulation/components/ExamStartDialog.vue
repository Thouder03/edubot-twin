<script setup lang="ts">
/**
 * ExamStartDialog - 开始考试确认对话框（SDD §8.3）
 */
import { ElButton, ElDialog } from 'element-plus'
import type { ExamRunInfo } from '@/api/exam/attempts'

const props = defineProps<{
  visible: boolean
  examRunInfo: ExamRunInfo | null
  starting: boolean
}>()

const emit = defineEmits<{
  (e: 'update:visible', v: boolean): void
  (e: 'confirm'): void
  (e: 'cancel'): void
}>()

function formatMinutes(ms: number): string {
  return Math.ceil(ms / 60000) + ' 分钟'
}
</script>

<template>
  <ElDialog
    :model-value="props.visible"
    title="确认开始考试？"
    width="420px"
    :close-on-click-modal="false"
    :close-on-press-escape="!props.starting"
    @update:model-value="emit('update:visible', $event)"
  >
    <div v-if="props.examRunInfo" class="start-dialog-body">
      <div class="info-row">
        <span class="label">考试名称：</span>
        <span class="value font-bold">{{ props.examRunInfo.name }}</span>
      </div>
      <div class="info-row">
        <span class="label">时限：</span>
        <span class="value">{{ formatMinutes(props.examRunInfo.time_limit_ms) }}</span>
      </div>
      <div class="info-row">
        <span class="label">剩余尝试：</span>
        <span class="value">{{ props.examRunInfo.remaining_attempts }} 次</span>
      </div>
      <div class="warning-box">
        ⚠ 点击确认后，平台将冻结当前代码快照并自动运行评测脚本。本次尝试将计入剩余次数。
      </div>
    </div>

    <template #footer>
      <ElButton :disabled="props.starting" @click="emit('cancel')">取消</ElButton>
      <ElButton type="primary" :loading="props.starting" @click="emit('confirm')">
        确认开始考试
      </ElButton>
    </template>
  </ElDialog>
</template>

<style lang="less" scoped>
.start-dialog-body {
  .info-row {
    display: flex;
    align-items: center;
    margin-bottom: 10px;
    font-size: 14px;

    .label {
      color: #909399;
      width: 80px;
      flex-shrink: 0;
    }
    .value {
      color: #303133;
    }
  }

  .warning-box {
    margin-top: 16px;
    padding: 10px 14px;
    background: rgba(230, 162, 60, 0.12);
    border-left: 3px solid #e6a23c;
    border-radius: 4px;
    font-size: 13px;
    color: #b88230;
    line-height: 1.6;
  }
}
</style>
