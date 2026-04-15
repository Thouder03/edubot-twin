<script setup lang="ts">
/**
 * ExamHeader - 考试模式顶栏（SDD §8.2）
 *
 * 替换普通 SimulationHeader，显示：
 *   考试名称 | 模式 | 倒计时 | 状态 | 剩余尝试 | 操作按钮
 */
import { computed, ref, onBeforeUnmount, watch } from 'vue'
import {
  ElButton,
  ElTag,
  ElDropdown,
  ElDropdownMenu,
  ElDropdownItem,
  ElDialog,
  ElMessage,
  ElSwitch
} from 'element-plus'
import { Icon } from '@/components/Icon'
import type { ExamRunInfo, AttemptDetail, ExamAttemptStatus } from '@/api/exam/attempts'
import { getAttemptSidecarLogsApi } from '@/api/exam/attempts'
import { availablePanels } from '../config/predefined-layouts'
import SimControlBar from './SimControlBar.vue'
import { confirmExit } from '../composables/useExitConfirm'

const props = defineProps<{
  examRunInfo: ExamRunInfo | null
  attempt: AttemptDetail | null
  starting: boolean
  aborting: boolean
}>()

const emit = defineEmits<{
  (e: 'start'): void
  (e: 'abort'): void
  (e: 'back', mode: 'temporary' | 'stopAndExit'): void
  (e: 'view-result'): void
  (e: 'addPanel', type: string, title: string): void
}>()

function handleBack() {
  confirmExit((mode) => emit('back', mode), '退出考试')
}

const isRunning = computed(() => props.attempt?.status === 'running')

// ─── 倒计时 ───────────────────────────────────────────────────────────────────
const countdownDisplay = ref('--:--')
const countdownPercent = ref(100)
let countdownTimer: ReturnType<typeof setInterval> | null = null

function startCountdown() {
  if (countdownTimer) clearInterval(countdownTimer)
  countdownTimer = setInterval(updateCountdown, 1000)
  updateCountdown()
}

function stopCountdown() {
  if (countdownTimer) {
    clearInterval(countdownTimer)
    countdownTimer = null
  }
}

function updateCountdown() {
  if (!props.examRunInfo || !props.attempt?.started_at) {
    countdownDisplay.value = '--:--'
    return
  }
  let startedStr = props.attempt.started_at
  if (!startedStr.endsWith('Z') && !startedStr.includes('+')) {
    startedStr += 'Z'
  }
  const elapsed = Date.now() - new Date(startedStr).getTime()
  const remaining = Math.max(0, props.examRunInfo.time_limit_ms - elapsed)
  const totalMs = props.examRunInfo.time_limit_ms

  const secs = Math.floor(remaining / 1000)
  const m = Math.floor(secs / 60)
  const s = secs % 60
  countdownDisplay.value = `${String(m).padStart(2, '0')}:${String(s).padStart(2, '0')}`
  countdownPercent.value = Math.round((remaining / totalMs) * 100)
}

watch(
  () => props.attempt?.started_at,
  (val) => {
    if (val && props.attempt?.status === 'running') {
      startCountdown()
    } else {
      stopCountdown()
    }
  },
  { immediate: true }
)

watch(
  () => props.attempt?.status,
  (status) => {
    if (status !== 'running') stopCountdown()
  }
)

onBeforeUnmount(() => stopCountdown())

// ─── 状态文字 ─────────────────────────────────────────────────────────────────
const statusLabel = computed<string>(() => {
  switch (props.attempt?.status as ExamAttemptStatus | undefined) {
    case undefined:
    case null:
      return '调试中'
    case 'pending':
      return '准备中'
    case 'running':
      return '评测中'
    case 'scoring':
      return '计分中'
    case 'completed':
      return '已完成'
    case 'aborted':
      return '已放弃'
    case 'error':
      return '评测异常'
    default:
      return '未知'
  }
})

const statusTagType = computed<'success' | 'warning' | 'info' | 'danger'>(() => {
  switch (props.attempt?.status as ExamAttemptStatus | undefined) {
    case 'completed':
      return 'success'
    case 'running':
      return 'warning'
    case 'error':
    case 'aborted':
      return 'danger'
    default:
      return 'info'
  }
})

const countdownWarning = computed(() => countdownPercent.value < 20)

// ─── 容器日志弹窗 ─────────────────────────────────────────────────────────────
const showLogsDialog = ref(false)
const logsContent = ref('')
const loadingLogs = ref(false)

const autoRefreshLogs = ref(false)
let logsRefreshTimer: ReturnType<typeof setInterval> | null = null

function stopAutoRefreshLogs() {
  if (logsRefreshTimer) {
    clearInterval(logsRefreshTimer)
    logsRefreshTimer = null
  }
}

watch(autoRefreshLogs, (val) => {
  if (val) {
    logsRefreshTimer = setInterval(() => handleViewLogs(true), 2000)
  } else {
    stopAutoRefreshLogs()
  }
})

watch(showLogsDialog, (val) => {
  if (!val) {
    autoRefreshLogs.value = false
    stopAutoRefreshLogs()
  }
})

async function handleViewLogs(silent = false) {
  if (!props.attempt?.attempt_id) return
  showLogsDialog.value = true
  if (!silent) {
    loadingLogs.value = true
    logsContent.value = '正在加载日志...'
  }
  try {
    const res = await getAttemptSidecarLogsApi(props.attempt.attempt_id)
    logsContent.value = res.data?.logs || '暂无日志输出'
  } catch (e) {
    if (!silent) logsContent.value = '加载日志失败或容器尚未启动'
  } finally {
    if (!silent) loadingLogs.value = false
  }
}
</script>

<template>
  <div class="exam-header">
    <!-- 左区：考试信息 -->
    <div class="exam-header__left">
      <span class="exam-header__icon">📝</span>
      <div class="exam-header__info">
        <div class="exam-header__name">{{ props.examRunInfo?.name ?? '加载中…' }}</div>
        <div class="exam-header__meta">
          <ElTag size="small" type="info">{{ props.examRunInfo?.exam_mode ?? '-' }}</ElTag>
          <span class="divider">|</span>
          <ElTag size="small" :type="statusTagType">{{ statusLabel }}</ElTag>
          <span class="divider">|</span>
          <span class="attempts-info">
            剩余 {{ props.examRunInfo?.remaining_attempts ?? '-' }} 次
          </span>
        </div>
      </div>
    </div>

    <!-- 中区：考试运行中显示倒计时，其余时间显示仿真控制栏 -->
    <div class="exam-header__center">
      <template v-if="isRunning">
        <div class="countdown" :class="{ warning: countdownWarning }">
          <span class="countdown__icon">⏱</span>
          <span class="countdown__time">{{ countdownDisplay }}</span>
        </div>
      </template>
      <template v-else>
        <SimControlBar />
      </template>
    </div>

    <!-- 右区：添加面板 + 操作按钮 -->
    <div class="exam-header__right">
      <!-- 添加面板 -->
      <ElDropdown
        trigger="click"
        @command="
          (cmd: string) => {
            const panel = availablePanels.find((p) => p.type === cmd)
            if (panel) emit('addPanel', panel.type, panel.label)
          }
        "
      >
        <ElButton text class="header-action-btn">
          <Icon icon="vi-carbon:add" :size="16" class="mr-4px" />
          添加面板
        </ElButton>
        <template #dropdown>
          <ElDropdownMenu>
            <ElDropdownItem
              v-for="panel in availablePanels"
              :key="panel.type"
              :command="panel.type"
            >
              {{ panel.label }}
            </ElDropdownItem>
          </ElDropdownMenu>
        </template>
      </ElDropdown>

      <!-- 无 attempt：调试中 -->
      <template v-if="!props.attempt">
        <ElButton type="primary" :loading="props.starting" @click="emit('start')">
          ▶ 开始考试
        </ElButton>
        <ElButton @click="handleBack()">🚪 退出考试</ElButton>
      </template>

      <!-- pending：准备中 -->
      <template v-else-if="props.attempt.status === 'pending'">
        <ElButton type="primary" loading disabled>准备中…</ElButton>
        <ElButton @click="handleBack()">🚪 退出</ElButton>
      </template>

      <!-- running：评测中 -->
      <template v-else-if="props.attempt.status === 'running'">
        <ElButton class="header-action-btn" plain @click="() => handleViewLogs(false)">
          📄 日志
        </ElButton>
        <ElButton type="warning" loading disabled>🔄 评测中</ElButton>
        <ElButton type="danger" plain :loading="props.aborting" @click="emit('abort')">
          ⛔ 放弃
        </ElButton>
      </template>

      <!-- scoring：计分中 -->
      <template v-else-if="props.attempt.status === 'scoring'">
        <ElButton class="header-action-btn" plain @click="() => handleViewLogs(false)">
          📄 日志
        </ElButton>
        <ElButton type="info" loading disabled>📊 计分中…</ElButton>
      </template>

      <!-- completed：已完成 -->
      <template v-else-if="props.attempt.status === 'completed'">
        <ElButton type="success" @click="emit('view-result')">📋 查看结果</ElButton>
        <ElButton @click="handleBack()">← 返回</ElButton>
      </template>

      <!-- error / aborted -->
      <template v-else>
        <ElButton class="header-action-btn" plain @click="() => handleViewLogs(false)">
          📄 日志
        </ElButton>
        <ElButton type="danger" plain @click="emit('view-result')">❌ 查看详情</ElButton>
        <ElButton @click="handleBack()">← 返回</ElButton>
      </template>
    </div>

    <!-- 容器日志弹窗 -->
    <ElDialog
      v-model="showLogsDialog"
      title="评测容器引擎日志 (Sidecar)"
      width="700px"
      draggable
      :modal="false"
      :close-on-click-modal="false"
      destroy-on-close
    >
      <div v-loading="loadingLogs" class="logs-container">
        <pre class="logs-content">{{ logsContent }}</pre>
      </div>
      <template #footer>
        <div
          style="display: flex; align-items: center; justify-content: space-between; width: 100%"
        >
          <ElSwitch v-model="autoRefreshLogs" active-text="自动刷新(2s)" />
          <div>
            <ElButton @click="showLogsDialog = false">关闭</ElButton>
            <ElButton type="primary" :loading="loadingLogs" @click="handleViewLogs(false)">
              刷新
            </ElButton>
          </div>
        </div>
      </template>
    </ElDialog>
  </div>
</template>

<style lang="less" scoped>
.exam-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  height: 56px;
  padding: 0 20px;
  background: #1a1a2e;
  border-bottom: 1px solid rgba(64, 158, 255, 0.3);
  flex-shrink: 0;

  &__left {
    display: flex;
    align-items: center;
    gap: 12px;
    flex: 1;
    min-width: 0;
  }

  &__icon {
    font-size: 20px;
  }

  &__info {
    min-width: 0;
  }

  &__name {
    font-size: 15px;
    font-weight: 600;
    color: #e8eaf0;
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
  }

  &__meta {
    display: flex;
    align-items: center;
    gap: 6px;
    margin-top: 2px;
    font-size: 12px;

    .attempts-info {
      color: #a0a8c0;
      font-size: 12px;
    }
  }

  &__center {
    flex: 0 0 auto;
    padding: 0 24px;
  }

  &__right {
    display: flex;
    align-items: center;
    gap: 8px;
    flex: 0 0 auto;
  }
}

.header-action-btn {
  font-size: 13px;
  color: #bac2de;

  &:hover {
    color: #cdd6f4;
  }
}

.countdown {
  display: flex;
  align-items: center;
  gap: 6px;
  color: #a0d9f8;

  &__icon {
    font-size: 16px;
  }

  &__time {
    font-size: 22px;
    font-weight: 700;
    font-variant-numeric: tabular-nums;
    letter-spacing: 1px;
  }

  &.warning {
    color: #f56c6c;
    animation: blink 1s ease-in-out infinite alternate;
  }

  &--idle {
    color: #606880;

    .countdown__time {
      font-size: 14px;
      font-weight: 400;
    }
  }
}

.divider {
  color: #3a4060;
  margin: 0 2px;
}

@keyframes blink {
  from {
    opacity: 1;
  }
  to {
    opacity: 0.5;
  }
}

.logs-container {
  background: #1e1e2d;
  border-radius: 6px;
  padding: 12px;
  min-height: 200px;
  overflow-y: auto;
  border: 1px solid #3a4060;

  .logs-content {
    margin: 0;
    color: #a0d9f8;
    font-family: monospace;
    font-size: 13px;
    line-height: 1.5;
    white-space: pre-wrap;
    word-wrap: break-word;
  }
}
</style>

<style lang="less">
/* 全局控制容器日志弹窗的可缩放逻辑 */
.el-dialog:has(.logs-container) {
  resize: both;
  overflow: hidden;
  max-width: 90vw;
  max-height: 90vh;
  display: flex !important;
  flex-direction: column;

  /* 修复: 取消左右 auto 居中，改为固定左侧起点，使得调整大小时仅向右下延展 */
  margin-left: max(0px, calc(50vw - 350px)) !important;
  margin-right: auto !important;

  .el-dialog__body {
    flex: 1;
    overflow: hidden;
    display: flex;
    flex-direction: column;
    padding-bottom: 12px;

    .logs-container {
      flex: 1;
      max-height: none;
    }
  }
}
</style>
