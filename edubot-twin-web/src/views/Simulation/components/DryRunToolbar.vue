<script setup lang="ts">
/**
 * DryRunToolbar - Dry Run 专属悬浮工具栏
 *
 * 可自由拖拽，位置持久化到 localStorage。
 * 由 DryRunSimulation.vue 无条件渲染（无 v-if），始终可用。
 *
 * 功能：
 * - Docker Logs：获取容器最近 N 行日志，弹窗展示
 * - 运行失败回顾：展示容器状态、任务阶段信息
 */
import { ref } from 'vue'
import { ElDialog, ElButton, ElMessage, ElTag } from 'element-plus'
import { getDryRunDockerLogsApi, getDryRunFailureReviewApi } from '@/api/experiment'

// ready=false 表示 shadow_token 尚未就位（startDryRunApi 还未返回）
// 此时调用 API 会用教师 JWT，后端会返回「仅 Dry Run 可用」错误
const props = defineProps<{
  ready?: boolean
}>()

// ── 收起/展开 ──────────────────────────────────────────────
const collapsed = ref(false)

// ── 拖拽定位 + 位置记忆 ────────────────────────────────────
const STORAGE_KEY = 'dry-run-toolbar-pos'

function restorePosition(): { x: number; y: number } {
  try {
    const saved = localStorage.getItem(STORAGE_KEY)
    if (saved) {
      const parsed = JSON.parse(saved)
      if (typeof parsed.x === 'number' && typeof parsed.y === 'number') {
        // 确保恢复后位置在视口内
        return {
          x: Math.max(0, Math.min(window.innerWidth - 140, parsed.x)),
          y: Math.max(0, Math.min(window.innerHeight - 240, parsed.y))
        }
      }
    }
  } catch (_e) {
    // ignore parse errors, use default position
  }
  // 默认右下角
  return { x: window.innerWidth - 148, y: window.innerHeight - 250 }
}

const pos = ref<{ x: number; y: number }>(restorePosition())

function startDrag(e: MouseEvent) {
  e.preventDefault()
  const startX = e.clientX - pos.value.x
  const startY = e.clientY - pos.value.y

  const onMove = (ev: MouseEvent) => {
    pos.value = {
      x: Math.max(0, Math.min(window.innerWidth - 140, ev.clientX - startX)),
      y: Math.max(0, Math.min(window.innerHeight - 240, ev.clientY - startY))
    }
  }

  const onUp = () => {
    localStorage.setItem(STORAGE_KEY, JSON.stringify(pos.value))
    document.removeEventListener('mousemove', onMove)
    document.removeEventListener('mouseup', onUp)
  }

  document.addEventListener('mousemove', onMove)
  document.addEventListener('mouseup', onUp)
}

// ── Docker Logs ────────────────────────────────────────────
const logsDialogVisible = ref(false)
const logsContent = ref('')
const logsLoading = ref(false)

async function openDockerLogs() {
  if (!props.ready) {
    ElMessage.warning('正在初始化 Dry Run 环境，请稍候...')
    return
  }
  logsDialogVisible.value = true
  await fetchLogs()
}

async function fetchLogs() {
  logsLoading.value = true
  try {
    const res = await getDryRunDockerLogsApi(500)
    logsContent.value = res.data?.logs ?? '（无日志）'
  } catch (e: any) {
    ElMessage.error('获取日志失败：' + (e?.response?.data?.detail || e.message))
    logsContent.value = ''
  } finally {
    logsLoading.value = false
  }
}

// ── 运行失败回顾 ───────────────────────────────────────────
const reviewDialogVisible = ref(false)
const reviewData = ref<{
  container: Record<string, unknown>
  task: Record<string, unknown> | null
} | null>(null)
const reviewLoading = ref(false)

async function openFailureReview() {
  if (!props.ready) {
    ElMessage.warning('正在初始化 Dry Run 环境，请稍候...')
    return
  }
  reviewDialogVisible.value = true
  reviewLoading.value = true
  try {
    const res = await getDryRunFailureReviewApi()
    reviewData.value = res.data
  } catch (e: any) {
    ElMessage.error('获取诊断信息失败：' + (e?.response?.data?.detail || e.message))
    reviewData.value = null
  } finally {
    reviewLoading.value = false
  }
}

function statusType(status: string): 'success' | 'warning' | 'danger' | 'info' {
  const map: Record<string, 'success' | 'warning' | 'danger' | 'info'> = {
    running: 'success',
    stopped: 'warning',
    error: 'danger',
    creating: 'info',
    removing: 'info',
    SUCCEEDED: 'success',
    FAILED: 'danger',
    IN_PROGRESS: 'warning',
    PENDING: 'info'
  }
  return map[status] ?? 'info'
}
</script>

<template>
  <div
    class="dry-run-toolbar"
    :class="{ collapsed }"
    :style="{ left: pos.x + 'px', top: pos.y + 'px' }"
  >
    <!-- 标签行：拖拽手柄 -->
    <div class="toolbar-label" @mousedown="startDrag">🔬 Dry Run ⠿</div>

    <!-- 收起/展开切换 -->
    <button
      class="toolbar-toggle"
      :title="collapsed ? '展开工具栏' : '收起工具栏'"
      @click="collapsed = !collapsed"
    >
      {{ collapsed ? '+' : '−' }}
    </button>

    <template v-if="!collapsed">
      <button class="toolbar-btn" :disabled="logsLoading" @click="openDockerLogs">
        📋 Docker Logs
      </button>
      <button class="toolbar-btn" :disabled="reviewLoading" @click="openFailureReview">
        🔍 失败回顾
      </button>
    </template>
  </div>

  <!-- Docker Logs 弹窗 -->
  <ElDialog v-model="logsDialogVisible" title="Docker Logs" width="800px" destroy-on-close>
    <div class="logs-toolbar">
      <ElButton size="small" :loading="logsLoading" @click="fetchLogs">刷新</ElButton>
    </div>
    <pre v-if="logsContent" class="logs-content">{{ logsContent }}</pre>
    <div v-else-if="!logsLoading" class="logs-empty">暂无日志</div>
  </ElDialog>

  <!-- 运行失败回顾弹窗 -->
  <ElDialog v-model="reviewDialogVisible" title="运行失败回顾" width="600px" destroy-on-close>
    <div v-if="reviewLoading" class="review-loading">加载中...</div>
    <template v-else-if="reviewData">
      <!-- 容器状态 -->
      <div class="review-section">
        <div class="review-section-title">容器状态</div>
        <div class="review-row">
          <span class="review-key">状态</span>
          <ElTag :type="statusType(reviewData.container.status as string)" size="small">
            {{ reviewData.container.status }}
          </ElTag>
        </div>
        <div v-if="reviewData.container.error_message" class="review-row">
          <span class="review-key">错误信息</span>
          <span class="review-value error-text">{{ reviewData.container.error_message }}</span>
        </div>
        <div v-else-if="reviewData.container.status === 'error'" class="review-row">
          <span class="review-key">错误信息</span>
          <span class="review-value error-text">后端未返回错误详情，请查看 Docker Logs</span>
        </div>
        <div class="review-row">
          <span class="review-key">GzWeb 端口</span>
          <span class="review-value">{{ reviewData.container.gzbridge_port ?? '—' }}</span>
        </div>
        <div class="review-row">
          <span class="review-key">ROS 端口</span>
          <span class="review-value">{{ reviewData.container.rosbridge_port ?? '—' }}</span>
        </div>
      </div>

      <!-- 任务阶段 -->
      <div v-if="reviewData.task" class="review-section">
        <div class="review-section-title">任务详情</div>
        <div class="review-row">
          <span class="review-key">任务状态</span>
          <ElTag :type="statusType(reviewData.task.status as string)" size="small">
            {{ reviewData.task.status }}
          </ElTag>
        </div>
        <div class="review-row">
          <span class="review-key">当前阶段</span>
          <span class="review-value">{{ reviewData.task.current_stage }}</span>
        </div>
        <div v-if="reviewData.task.error_code" class="review-row">
          <span class="review-key">错误码</span>
          <span class="review-value error-text">{{ reviewData.task.error_code }}</span>
        </div>
        <div v-if="reviewData.task.error_message" class="review-row">
          <span class="review-key">错误信息</span>
          <span class="review-value error-text">{{ reviewData.task.error_message }}</span>
        </div>
        <div v-if="(reviewData.task.stage_statuses as any[])?.length" class="review-stages">
          <div class="review-key mb-8px">阶段明细</div>
          <div
            v-for="stage in reviewData.task.stage_statuses as any[]"
            :key="stage.stage"
            class="stage-row"
          >
            <ElTag :type="statusType(stage.status)" size="small" class="mr-8px">
              {{ stage.status }}
            </ElTag>
            <span class="stage-name">{{ stage.stage }}</span>
            <span v-if="stage.elapsed_ms" class="stage-ms">{{ stage.elapsed_ms }}ms</span>
          </div>
        </div>
      </div>
      <div v-else class="review-empty">暂无任务记录（通常表示失败发生在容器就绪前）</div>
    </template>
    <div v-else class="review-empty">暂无诊断数据</div>
  </ElDialog>
</template>

<style scoped>
.dry-run-toolbar {
  position: fixed;
  /* left/top 由 :style 动态绑定，实现拖拽定位 */
  width: 130px; /* 固定宽度，防止展开/收起时内容宽度变化导致按钮位移 */
  display: flex;
  flex-direction: column;
  align-items: stretch; /* 按钮撑满宽度 */
  gap: 8px;
  z-index: 10000;
  user-select: none;
}

.toolbar-toggle {
  width: 100%;
  height: 32px;
  border-radius: 6px;
  background: #6c47d4;
  color: #fff;
  border: none;
  cursor: pointer;
  font-size: 13px;
  display: flex;
  align-items: center;
  justify-content: center;
  box-shadow: 0 2px 8px rgba(0, 0, 0, 0.4);
  transition: background 0.2s;
}
.toolbar-toggle:hover {
  background: #7e5ce4;
}

.toolbar-label {
  font-size: 12px;
  color: #bbb;
  letter-spacing: 0.5px;
  text-align: right;
  cursor: move;
  padding: 2px 4px;
  border-radius: 4px;
  transition: background 0.15s;

  &:hover {
    background: rgba(255, 255, 255, 0.06);
  }
}

.toolbar-btn {
  background: #2a2a3c;
  color: #d4d4f4;
  border: 1px solid #44446a;
  border-radius: 6px;
  padding: 6px 14px;
  font-size: 13px;
  cursor: pointer;
  white-space: nowrap;
  transition: background 0.2s;
}
.toolbar-btn:hover:not(:disabled) {
  background: #3a3a5c;
}
.toolbar-btn:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

/* Logs 弹窗内容 */
.logs-toolbar {
  margin-bottom: 8px;
}
.logs-content {
  background: #111;
  color: #d4d4d4;
  font-family: 'Consolas', 'Monaco', monospace;
  font-size: 12px;
  line-height: 1.6;
  padding: 12px;
  border-radius: 6px;
  max-height: 500px;
  overflow-y: auto;
  white-space: pre-wrap;
  word-break: break-all;
}
.logs-empty {
  color: #888;
  text-align: center;
  padding: 24px 0;
}

/* 失败回顾弹窗内容 */
.review-loading,
.review-empty {
  color: #888;
  text-align: center;
  padding: 24px 0;
}
.review-section {
  margin-bottom: 20px;
}
.review-section-title {
  font-weight: 600;
  font-size: 14px;
  margin-bottom: 10px;
  color: #a0a0c0;
  border-bottom: 1px solid #333;
  padding-bottom: 4px;
}
.review-row {
  display: flex;
  align-items: center;
  gap: 12px;
  margin-bottom: 8px;
}
.review-key {
  width: 90px;
  font-size: 12px;
  color: #888;
  flex-shrink: 0;
}
.review-value {
  font-size: 13px;
}
.error-text {
  color: #f87171;
}
.review-stages {
  margin-top: 8px;
}
.stage-row {
  display: flex;
  align-items: center;
  gap: 6px;
  margin-bottom: 6px;
  font-size: 12px;
}
.stage-name {
  flex: 1;
  color: #ccc;
}
.stage-ms {
  color: #888;
  font-size: 11px;
}
.mb-8px {
  margin-bottom: 8px;
}
.mr-8px {
  margin-right: 8px;
}
</style>
