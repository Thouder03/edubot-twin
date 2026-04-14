/**
 * 考试运行记录 API（第12期）
 *
 * 学生端：
 *   GET  /students/exams/{id}                   → ExamRunInfo
 *   GET  /students/exams/{id}/my-attempts        → AttemptSummary[]
 *   POST /students/exam-attempts                 → 创建尝试
 *   POST /students/exam-attempts/{id}/start      → 开始考试
 *   GET  /students/exam-attempts/{id}            → 尝试详情
 *   POST /students/exam-attempts/{id}/abort      → 放弃考试
 *
 * 教师端：
 *   GET  /teachers/exams/{id}/attempts           → 单考试运行记录列表
 *   GET  /teachers/exam-attempts                 → 全局运行记录列表
 *   GET  /teachers/exam-attempts/{id}            → 完整详情
 *   GET  /teachers/exam-attempts/{id}/events     → 生命周期事件
 */

import request from '@/axios'

// ─── 类型定义 ────────────────────────────────────────────────────────────────

export type ExamAttemptStatus =
  | 'pending'
  | 'running'
  | 'scoring'
  | 'completed'
  | 'aborted'
  | 'error'

export interface RuntimePolicy {
  max_duration_ms: number
  max_attempts: number
  allow_debug_before_start: boolean
  [key: string]: unknown
}

export interface ExamRunInfo {
  exam_id: number
  name: string
  description: string | null
  exam_mode: 'result_run' | 'process_run' | 'multi_stage_run'
  runtime_policy: RuntimePolicy
  panel_policy: Record<string, unknown>
  time_limit_ms: number
  remaining_attempts: number
}

export interface ResultJsonMetrics {
  goal_reached?: boolean
  elapsed_seconds?: number
  collision_count?: number
  path_length?: number
  [key: string]: unknown
}

export interface ResultJson {
  status: string
  objective_score: number
  pass: boolean
  summary: string
  metrics?: ResultJsonMetrics
  artifacts?: Record<string, string>
  custom_fields?: Record<string, unknown>
  [key: string]: unknown
}

/** 学生端尝试详情（含完整 result_json） */
export interface AttemptDetail {
  attempt_id: number
  exam_id: number
  status: ExamAttemptStatus
  attempt_exam_mode: string
  started_at: string | null
  ended_at: string | null
  duration_ms: number | null
  objective_score: number | null
  pass: boolean | null
  summary: string | null
  result_json: ResultJson | null
  error_code: string | null
  error_message: string | null
  created_at: string
  updated_at: string
}

/** 学生端尝试列表摘要（不含完整 result_json） */
export interface AttemptSummary {
  attempt_id: number
  exam_id: number
  status: ExamAttemptStatus
  objective_score: number | null
  pass: boolean | null
  started_at: string | null
  ended_at: string | null
  duration_ms: number | null
  error_code: string | null
  created_at: string
}

export interface CreateAttemptResponse {
  attempt_id: number
  status: ExamAttemptStatus
}

/** 教师端学生信息 */
export interface AttemptStudentInfo {
  student_id: number
  username: string
  real_name: string | null
}

/** 教师端考试信息 */
export interface AttemptExamInfo {
  exam_id: number
  name: string
  exam_mode: string
}

/** 教师端列表条目 */
export interface TeacherAttemptListItem {
  attempt_id: number
  exam_id: number
  status: ExamAttemptStatus
  student: AttemptStudentInfo
  objective_score: number | null
  pass: boolean | null
  started_at: string | null
  ended_at: string | null
  duration_ms: number | null
  error_code: string | null
  review_status: string
  created_at: string
}

/** 教师端完整详情 */
export interface TeacherAttemptFull extends AttemptDetail {
  student: AttemptStudentInfo
  exam: AttemptExamInfo
  review_status: string
  teacher_comment: string | null
  artifact_index_json: Record<string, string>
  sidecar_container_id: string | null
}

/** 生命周期事件 */
export interface EvidenceEvent {
  id: number
  attempt_id: number
  event_type: string
  event_time_ms: number
  sequence_no: number
  source: string
  payload_json: Record<string, unknown>
  created_at: string
}

export interface AttemptListResponse {
  items: TeacherAttemptListItem[]
  total: number
  page: number
  page_size: number
}

// ─── 考试容器启动相关类型（12期补充） ────────────────────────────────────────

export interface ExamContainerStartRequest {
  exam_id: number
}

// ─── 学生端 API ──────────────────────────────────────────────────────────────

const STUDENT_BASE = '/api/v1/students'
const TEACHER_BASE = '/api/v1/teachers'

/** 已发布考试列表条目（学生首页选考试用） */
export interface PublishedExamItem {
  exam_id: number
  name: string
  code: string
  description: string | null
  exam_mode: 'result_run' | 'process_run' | 'multi_stage_run'
  time_limit_ms: number
  max_attempts: number
}

/** 获取可参加的已发布考试列表（学生首页） */
export const getPublishedExamsApi = (): Promise<IResponse<PublishedExamItem[]>> =>
  request.get({ url: `${STUDENT_BASE}/exams` })

/** 获取考试运行信息（学生进入考试页） */
export const getExamRunInfoApi = (examId: number): Promise<IResponse<ExamRunInfo>> =>
  request.get({ url: `${STUDENT_BASE}/exams/${examId}` })

/** 获取我对该考试的全部尝试 */
export const getMyAttemptsApi = (
  examId: number
): Promise<
  IResponse<{ items: AttemptSummary[]; total: number; page: number; page_size: number }>
> => request.get({ url: `${STUDENT_BASE}/exams/${examId}/my-attempts` })

/** 创建考试尝试（status=pending） */
export const createAttemptApi = (examId: number): Promise<IResponse<CreateAttemptResponse>> =>
  request.post({ url: `${STUDENT_BASE}/exam-attempts`, data: { exam_id: examId } })

/** 开始考试（触发 Sidecar 调度） */
export const startAttemptApi = (attemptId: number): Promise<IResponse<AttemptDetail>> =>
  request.post({ url: `${STUDENT_BASE}/exam-attempts/${attemptId}/start` })

/** 查询考试尝试详情（轮询用） */
export const getAttemptDetailApi = (attemptId: number): Promise<IResponse<AttemptDetail>> =>
  request.get({ url: `${STUDENT_BASE}/exam-attempts/${attemptId}` })

/** 学生主动放弃考试 */
export const abortAttemptApi = (
  attemptId: number,
  reason?: string
): Promise<IResponse<AttemptDetail>> =>
  request.post({
    url: `${STUDENT_BASE}/exam-attempts/${attemptId}/abort`,
    data: { reason: reason || null }
  })

// ─── 教师端 API ──────────────────────────────────────────────────────────────

/** 单考试运行记录列表 */
export const getExamAttemptsApi = (
  examId: number,
  params?: { page?: number; page_size?: number; student_id?: number; status?: string }
): Promise<IResponse<AttemptListResponse>> =>
  request.get({ url: `${TEACHER_BASE}/exams/${examId}/attempts`, params })

/** 全局运行记录列表 */
export const getAllAttemptsApi = (params?: {
  page?: number
  page_size?: number
  student_id?: number
  exam_id?: number
  status?: string
}): Promise<IResponse<AttemptListResponse>> =>
  request.get({ url: `${TEACHER_BASE}/exam-attempts`, params })

/** 运行记录完整详情 */
export const getAttemptFullApi = (attemptId: number): Promise<IResponse<TeacherAttemptFull>> =>
  request.get({ url: `${TEACHER_BASE}/exam-attempts/${attemptId}` })

/** 生命周期事件时间轴 */
export const getAttemptEventsApi = (
  attemptId: number
): Promise<IResponse<{ items: EvidenceEvent[] }>> =>
  request.get({ url: `${TEACHER_BASE}/exam-attempts/${attemptId}/events` })

// ─── 12期补充：考试容器启动 API ──────────────────────────────────────────────

import type { StudentSimulationStartResponse } from '@/api/experiment/types'

/**
 * 启动考试专用容器
 *
 * POST /api/v1/students/simulation/start-exam-container
 */
export const startExamContainerApi = (
  data: ExamContainerStartRequest
): Promise<IResponse<StudentSimulationStartResponse>> =>
  request.post({ url: `${STUDENT_BASE}/simulation/start-exam-container`, data })
