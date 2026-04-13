<script setup lang="ts">
/**
 * AttemptDetailDialog - 运行记录详情弹窗（教师端，SDD §8.6）
 *
 * 显示：学生信息、考试信息、状态/时间、result_json 原文（Monaco 只读）、生命周期事件列表
 */
import { ref, watch } from 'vue'
import {
  ElButton,
  ElDescriptions,
  ElDescriptionsItem,
  ElDialog,
  ElDivider,
  ElTag,
  ElTable,
  ElTableColumn,
  ElEmpty
} from 'element-plus'
import MonacoEditor from '@/components/Monaco/MonacoEditor.vue'
import { useWorkspaceSettings } from '@/composables/useWorkspaceSettings'
import { getAttemptFullApi, getAttemptEventsApi } from '@/api/exam/attempts'
import type { TeacherAttemptFull, EvidenceEvent } from '@/api/exam/attempts'

const props = defineProps<{
  visible: boolean
  attemptId: number | null
}>()

const emit = defineEmits<{
  (e: 'update:visible', v: boolean): void
}>()

const { settings: monacoSettings } = useWorkspaceSettings()

const loading = ref(false)
const attempt = ref<TeacherAttemptFull | null>(null)
const events = ref<EvidenceEvent[]>([])
const resultJsonStr = ref('')

const STATUS_LABEL: Record<string, string> = {
  pending: '准备中',
  running: '评测中',
  scoring: '计分中',
  completed: '已完成',
  aborted: '已放弃',
  error: '评测异常'
}
const STATUS_TYPE: Record<string, 'success' | 'warning' | 'info' | 'danger'> = {
  completed: 'success',
  running: 'warning',
  error: 'danger',
  aborted: 'danger',
  pending: 'info',
  scoring: 'info'
}

function formatDuration(ms: number | null): string {
  if (ms == null) return '-'
  const s = Math.round(ms / 1000)
  return s < 60 ? `${s}s` : `${Math.floor(s / 60)}m ${s % 60}s`
}

function formatTs(iso: string | null): string {
  if (!iso) return '-'
  return new Date(iso).toLocaleString('zh-CN', { hour12: false })
}

function formatEventTime(ms: number): string {
  return new Date(ms).toLocaleTimeString('zh-CN', { hour12: false })
}

async function load() {
  if (!props.attemptId) return
  loading.value = true
  try {
    const [detailRes, eventsRes] = await Promise.all([
      getAttemptFullApi(props.attemptId),
      getAttemptEventsApi(props.attemptId)
    ])
    attempt.value = detailRes.data ?? null
    events.value = eventsRes.data?.items ?? []
    resultJsonStr.value = attempt.value?.result_json
      ? JSON.stringify(attempt.value.result_json, null, 2)
      : ''
  } catch {
    attempt.value = null
    events.value = []
  } finally {
    loading.value = false
  }
}

watch(
  () => props.visible,
  (v) => {
    if (v) load()
    else {
      attempt.value = null
      events.value = []
    }
  }
)
</script>

<template>
  <ElDialog
    :model-value="props.visible"
    title="运行记录详情"
    width="780px"
    top="5vh"
    :close-on-click-modal="false"
    @update:model-value="emit('update:visible', $event)"
  >
    <div v-loading="loading" class="detail-body">
      <template v-if="attempt">
        <!-- 基础信息 -->
        <ElDescriptions :column="3" border size="small" class="mb-16px">
          <ElDescriptionsItem label="学生">
            {{ attempt.student.real_name || attempt.student.username }}
          </ElDescriptionsItem>
          <ElDescriptionsItem label="考试">
            {{ attempt.exam.name }}
          </ElDescriptionsItem>
          <ElDescriptionsItem label="模式">
            {{ attempt.attempt_exam_mode }}
          </ElDescriptionsItem>
          <ElDescriptionsItem label="状态">
            <ElTag :type="STATUS_TYPE[attempt.status]" size="small">
              {{ STATUS_LABEL[attempt.status] ?? attempt.status }}
            </ElTag>
          </ElDescriptionsItem>
          <ElDescriptionsItem label="客观分">
            {{ attempt.objective_score ?? '-' }}
          </ElDescriptionsItem>
          <ElDescriptionsItem label="通过">
            <ElTag
              v-if="attempt.pass != null"
              :type="attempt.pass ? 'success' : 'danger'"
              size="small"
            >
              {{ attempt.pass ? '✅ 是' : '❌ 否' }}
            </ElTag>
            <span v-else>-</span>
          </ElDescriptionsItem>
          <ElDescriptionsItem label="开始时间">{{
            formatTs(attempt.started_at)
          }}</ElDescriptionsItem>
          <ElDescriptionsItem label="结束时间">{{ formatTs(attempt.ended_at) }}</ElDescriptionsItem>
          <ElDescriptionsItem label="用时">{{
            formatDuration(attempt.duration_ms)
          }}</ElDescriptionsItem>
          <ElDescriptionsItem v-if="attempt.error_code" label="错误码" :span="3">
            <code class="error-code">{{ attempt.error_code }}</code>
            <span v-if="attempt.error_message" class="error-msg">
              — {{ attempt.error_message }}</span
            >
          </ElDescriptionsItem>
          <ElDescriptionsItem v-if="attempt.summary" label="评语" :span="3">
            {{ attempt.summary }}
          </ElDescriptionsItem>
        </ElDescriptions>

        <!-- result_json 原文 -->
        <ElDivider content-position="left">result_json 原文</ElDivider>
        <div v-if="resultJsonStr" class="monaco-wrap">
          <MonacoEditor
            v-model="resultJsonStr"
            language="json"
            :readonly="true"
            :settings="monacoSettings"
          />
        </div>
        <ElEmpty v-else description="暂无评测结果" :image-size="60" />

        <!-- 生命周期事件 -->
        <ElDivider content-position="left">生命周期事件（{{ events.length }}）</ElDivider>
        <ElTable :data="events" size="small" max-height="240" stripe>
          <ElTableColumn label="#" prop="sequence_no" width="48" />
          <ElTableColumn label="时间" width="100">
            <template #default="{ row }">{{ formatEventTime(row.event_time_ms) }}</template>
          </ElTableColumn>
          <ElTableColumn label="事件类型" prop="event_type" min-width="180" />
          <ElTableColumn label="来源" prop="source" width="80" />
          <ElTableColumn label="Payload" min-width="200">
            <template #default="{ row }">
              <span class="payload-text">{{ JSON.stringify(row.payload_json) }}</span>
            </template>
          </ElTableColumn>
        </ElTable>
      </template>

      <ElEmpty v-else-if="!loading" description="暂无数据" :image-size="80" />
    </div>

    <template #footer>
      <ElButton @click="emit('update:visible', false)">关闭</ElButton>
    </template>
  </ElDialog>
</template>

<style lang="less" scoped>
.detail-body {
  min-height: 200px;
}

.monaco-wrap {
  height: 200px;
  border: 1px solid var(--el-border-color-lighter);
  border-radius: 4px;
  overflow: hidden;
  margin-bottom: 8px;
}

.error-code {
  background: rgba(245, 108, 108, 0.1);
  padding: 1px 6px;
  border-radius: 3px;
  font-family: monospace;
  font-size: 12px;
  color: #f56c6c;
}

.error-msg {
  font-size: 12px;
  color: #909399;
}

.payload-text {
  font-size: 11px;
  font-family: monospace;
  color: #606266;
  word-break: break-all;
}
</style>
