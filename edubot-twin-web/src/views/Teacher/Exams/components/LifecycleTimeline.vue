<template>
  <div class="lifecycle-timeline">
    <div v-if="!events" class="loading-state">
      <el-skeleton :rows="4" animated />
    </div>
    <el-empty v-else-if="events.length === 0" description="暂无生命周期事件" :image-size="60" />
    <el-timeline v-else>
      <el-timeline-item
        v-for="event in events"
        :key="event.id"
        :timestamp="formatTime(event.event_time_ms)"
        :type="eventType(event.event_type)"
        :hollow="event.source !== 'backend'"
        placement="top"
      >
        <div class="event-content">
          <span class="event-type">{{ formatEventType(event.event_type) }}</span>
          <el-tag size="small" class="event-source-tag">{{ event.source }}</el-tag>
        </div>
        <div v-if="hasPayload(event)" class="event-payload">
          <pre class="payload-pre">{{ JSON.stringify(event.payload_json, null, 2) }}</pre>
        </div>
      </el-timeline-item>
    </el-timeline>
  </div>
</template>

<script setup lang="ts">
import type { EvidenceEvent } from '@/api/exam/attempts'

defineProps<{
  events: EvidenceEvent[] | null
}>()

function formatTime(ms: number): string {
  return new Date(ms).toLocaleString('zh-CN', {
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
    second: '2-digit'
  })
}

const EVENT_LABELS: Record<string, string> = {
  exam_attempt_created: '考试尝试创建',
  code_snapshot_started: '代码快照开始',
  code_snapshot_created: '代码快照完成',
  code_snapshot_failed: '代码快照失败',
  sidecar_container_created: 'Sidecar 容器创建',
  sidecar_start_failed: 'Sidecar 启动失败',
  sidecar_script_finished: '评测脚本完成',
  scoring_completed: '客观评分入库',
  invalid_result_json: 'result.json 格式错误',
  result_missing_fields: '结果字段缺失',
  timeout_reached: '超时终止',
  exam_aborted_by_student: '学生主动放弃',
  exam_attempt_finalized: '考试最终状态写入',
  system_warning: '系统警告',
  system_error: '系统错误',
  manual_score_submitted: '教师提交人工评分',
  teacher_override: '教师覆盖操作',
  final_score_calculated: '最终成绩核算'
}

function formatEventType(type: string): string {
  return EVENT_LABELS[type] ?? type
}

const ERROR_TYPES = new Set([
  'code_snapshot_failed',
  'sidecar_start_failed',
  'invalid_result_json',
  'result_missing_fields',
  'timeout_reached',
  'system_error'
])
const SUCCESS_TYPES = new Set([
  'scoring_completed',
  'final_score_calculated',
  'manual_score_submitted'
])
const WARNING_TYPES = new Set(['system_warning', 'exam_aborted_by_student', 'teacher_override'])

function eventType(type: string): 'danger' | 'success' | 'warning' | 'primary' | 'info' {
  if (ERROR_TYPES.has(type)) return 'danger'
  if (SUCCESS_TYPES.has(type)) return 'success'
  if (WARNING_TYPES.has(type)) return 'warning'
  return 'primary'
}

function hasPayload(event: EvidenceEvent): boolean {
  return Object.keys(event.payload_json).length > 0
}
</script>

<style scoped>
.lifecycle-timeline {
  padding: 4px 0;
}
.loading-state {
  padding: 16px 0;
}
.event-content {
  display: flex;
  align-items: center;
  gap: 8px;
}
.event-type {
  font-size: 13px;
  font-weight: 500;
}
.event-source-tag {
  font-size: 10px;
}
.event-payload {
  margin-top: 4px;
}
.payload-pre {
  margin: 0;
  padding: 6px 8px;
  font-size: 11px;
  font-family: monospace;
  background: var(--el-fill-color-darker);
  border-radius: 4px;
  white-space: pre-wrap;
  word-break: break-all;
  max-height: 120px;
  overflow: auto;
}
</style>
