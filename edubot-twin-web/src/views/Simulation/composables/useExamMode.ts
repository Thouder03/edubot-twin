/**
 * useExamMode - 考试模式状态管理 Composable（第12期 SDD §8）
 *
 * 职责：
 * - 持有 examRunInfo、currentAttempt、状态轮询定时器
 * - 提供 startExam / abortExam 操作
 * - 封装 2s 轮询逻辑（running/scoring 状态下）
 *
 * 使用方式：
 *   const examMode = useExamMode(examId)   // examId = computed<number>()
 *   examMode.examRunInfo.value             // ExamRunInfo
 *   examMode.attempt.value                 // AttemptDetail | null
 *   examMode.startExam()                   // 创建 + 开始
 */

import { ref, computed, watch, onBeforeUnmount } from 'vue'
import { ElMessage } from 'element-plus'
import type { Ref } from 'vue'
import type { ExamRunInfo, AttemptDetail, ExamAttemptStatus } from '@/api/exam/attempts'
import {
  getExamRunInfoApi,
  createAttemptApi,
  startAttemptApi,
  getAttemptDetailApi,
  abortAttemptApi
} from '@/api/exam/attempts'

const POLL_INTERVAL = 2000 // 2s 轮询间隔

const TERMINAL_STATUSES: ExamAttemptStatus[] = ['completed', 'aborted', 'error']
const POLLING_STATUSES: ExamAttemptStatus[] = ['pending', 'running', 'scoring']

export function useExamMode(examId: Ref<number | null>) {
  const examRunInfo = ref<ExamRunInfo | null>(null)
  const attempt = ref<AttemptDetail | null>(null)
  const loading = ref(false)
  const starting = ref(false)
  const aborting = ref(false)
  const loadError = ref<string | null>(null)

  let pollTimer: ReturnType<typeof setInterval> | null = null

  // ─── 派生状态 ─────────────────────────────────────────────
  const attemptStatus = computed<ExamAttemptStatus | null>(() => attempt.value?.status ?? null)
  const isInProgress = computed(
    () => attemptStatus.value !== null && POLLING_STATUSES.includes(attemptStatus.value)
  )
  const isCompleted = computed(() => attemptStatus.value === 'completed')
  const isError = computed(
    () => attemptStatus.value === 'error' || attemptStatus.value === 'aborted'
  )

  /** 倒计时剩余毫秒（running 时计算） */
  const countdownMs = computed<number | null>(() => {
    if (!examRunInfo.value || !attempt.value?.started_at) return null
    let startedStr = attempt.value.started_at
    if (!startedStr.endsWith('Z') && !startedStr.includes('+')) {
      startedStr += 'Z'
    }
    const elapsed = Date.now() - new Date(startedStr).getTime()
    const remaining = examRunInfo.value.time_limit_ms - elapsed
    return Math.max(0, remaining)
  })

  // ─── 加载考试运行信息 ──────────────────────────────────────
  async function loadExamRunInfo() {
    if (!examId.value) return
    loading.value = true
    loadError.value = null
    try {
      const res = await getExamRunInfoApi(examId.value)
      examRunInfo.value = res.data ?? null
    } catch (e: unknown) {
      const err = e as {
        response?: { data?: { detail?: { error_code?: string; message?: string } } }
      }
      const detail = err?.response?.data?.detail
      const code = detail?.error_code
      if (code === 'EXAM_NOT_PUBLISHED') {
        loadError.value = '考试尚未发布'
      } else if (code === 'EXAM_MODE_NOT_SUPPORTED_YET') {
        loadError.value = '该考试模式暂未开放'
      } else {
        loadError.value = '考试信息加载失败'
      }
    } finally {
      loading.value = false
    }
  }

  // ─── 轮询 attempt 状态 ────────────────────────────────────
  function startPolling(attemptId: number) {
    stopPolling()
    pollTimer = setInterval(async () => {
      try {
        const res = await getAttemptDetailApi(attemptId)
        if (res.data) {
          attempt.value = res.data
          if (TERMINAL_STATUSES.includes(res.data.status)) {
            stopPolling()
          }
        }
      } catch {
        // 网络抖动，继续轮询
      }
    }, POLL_INTERVAL)
  }

  function stopPolling() {
    if (pollTimer) {
      clearInterval(pollTimer)
      pollTimer = null
    }
  }

  // ─── 创建并开始考试 ───────────────────────────────────────
  async function startExam(): Promise<boolean> {
    if (!examId.value) return false
    starting.value = true
    try {
      // Step 1: 创建 attempt
      const createRes = await createAttemptApi(examId.value)
      const attemptId = createRes.data?.attempt_id
      if (!attemptId) throw new Error('创建失败：未返回 attempt_id')

      // Step 2: 开始考试（触发 Sidecar）
      const startRes = await startAttemptApi(attemptId)
      attempt.value = startRes.data ?? null

      // Step 3: 启动轮询
      startPolling(attemptId)
      return true
    } catch (e: unknown) {
      const err = e as {
        response?: { data?: { detail?: { error_code?: string; message?: string } } }
      }
      const detail = err?.response?.data?.detail
      const code = detail?.error_code
      const MSG_MAP: Record<string, string> = {
        CONTAINER_NOT_RUNNING: '请先启动仿真容器再参加考试',
        ATTEMPT_IN_PROGRESS: '已有进行中的考试尝试',
        MAX_ATTEMPTS_EXCEEDED: '已达最大尝试次数',
        EXAM_NOT_PUBLISHED: '考试尚未发布',
        SNAPSHOT_FAILED: '代码快照失败，请联系管理员',
        SIDECAR_START_FAILED: '评测引擎启动失败，请联系管理员'
      }
      ElMessage.error(code ? (MSG_MAP[code] ?? `错误：${code}`) : '开始考试失败，请重试')
      return false
    } finally {
      starting.value = false
    }
  }

  // ─── 放弃考试 ─────────────────────────────────────────────
  async function abortExam(reason?: string): Promise<void> {
    if (!attempt.value) return
    aborting.value = true
    try {
      await abortAttemptApi(attempt.value.attempt_id, reason)
      attempt.value = null
      stopPolling()
    } catch {
      ElMessage.error('放弃考试失败')
    } finally {
      aborting.value = false
    }
  }

  // ─── 恢复进行中的 attempt ─────────────────────────────────
  /** 外部检测到 attempt_id（如页面刷新恢复），注入进来接管轮询 */
  function resumeAttempt(existingAttempt: AttemptDetail) {
    attempt.value = existingAttempt
    if (POLLING_STATUSES.includes(existingAttempt.status)) {
      startPolling(existingAttempt.attempt_id)
    }
  }

  // ─── 监听 examId 变化 ─────────────────────────────────────
  watch(
    examId,
    (newId) => {
      if (newId) {
        stopPolling()
        attempt.value = null
        loadExamRunInfo()
      } else {
        stopPolling()
        examRunInfo.value = null
        attempt.value = null
      }
    },
    { immediate: true }
  )

  onBeforeUnmount(() => {
    stopPolling()
  })

  return {
    // 状态
    examRunInfo,
    attempt,
    loading,
    starting,
    aborting,
    loadError,
    // 派生
    attemptStatus,
    isInProgress,
    isCompleted,
    isError,
    countdownMs,
    // 操作
    startExam,
    abortExam,
    resumeAttempt,
    stopPolling,
    loadExamRunInfo
  }
}

export type UseExamMode = ReturnType<typeof useExamMode>
