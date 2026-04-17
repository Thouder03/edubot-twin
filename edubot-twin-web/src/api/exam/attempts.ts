/**
 * 考试运行记录 API（第12/13期）
 *
 * 学生端：
 *   GET  /students/exams/{id}                   → ExamRunInfo
 *   GET  /students/exams/{id}/my-attempts        → AttemptSummary[]
 *   POST /students/exam-attempts                 → 创建尝试
 *   POST /students/exam-attempts/{id}/start      → 开始考试
 *   GET  /students/exam-attempts/{id}            → 尝试详情
 *   POST /students/exam-attempts/{id}/abort      → 放弃考试
 *
 * 教师端（第12期）：
 *   GET  /teachers/exams/{id}/attempts           → 单考试运行记录列表
 *   GET  /teachers/exam-attempts                 → 全局运行记录列表
 *   GET  /teachers/exam-attempts/{id}            → 完整详情
 *   GET  /teachers/exam-attempts/{id}/events     → 生命周期事件
 *
 * 教师端（第13期复核）：
 *   GET  /teachers/exam-attempts/{id}/artifacts         → artifacts 目录树
 *   GET  /teachers/exam-attempts/{id}/artifacts/file    → 读取单文件
 *   POST /teachers/exam-attempts/{id}/manual-score      → 提交人工评分
 *   POST /teachers/exam-attempts/{id}/override          → 覆盖客观分/pass
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
  review_status: string | null
  manual_score: number | null
  final_score: number | null
  created_at: string
}

/** 教师端完整详情（第13期扩展：manual_score / final_score / breakdown_json） */
export interface TeacherAttemptFull extends AttemptDetail {
  student: AttemptStudentInfo
  exam: AttemptExamInfo
  review_status: string | null
  manual_score: number | null
  final_score: number | null
  breakdown_json: Record<string, unknown> | null
  teacher_comment: string | null
  artifact_index_json: Record<string, string>
  sidecar_container_id: string | null
  attempt_scoring_policy_json: Record<string, unknown>
  /** 第14期新增：学生代码快照路径（非 null 时显示"查看提交代码"按钮） */
  submission_snapshot_path: string | null
}

// ─── 第13期：复核相关类型 ─────────────────────────────────────────────────────

export interface ManualScoreBreakdown {
  operation_quality?: number | null
  path_rationality?: number | null
  recovery_ability?: number | null
  stability?: number | null
  extra_comment?: string | null
  [key: string]: unknown
}

export interface ManualScoreRequest {
  manual_score: number
  breakdown: ManualScoreBreakdown
  comment?: string | null
}

export interface OverrideRequest {
  objective_score?: number | null
  pass_flag?: boolean | null
  override_reason: string
}

/** artifacts 目录树响应 */
export interface ArtifactFileInfo {
  name: string
  size: number
  mime: string
  preview_type: 'text' | 'image' | 'download' | 'unsupported'
  too_large: boolean
}

export interface ArtifactsTreeResponse {
  artifact_index: Record<string, string>
  files: ArtifactFileInfo[]
  artifacts_available: boolean
}

/** 单文件预览响应 */
export interface ArtifactFileContent {
  content: string
  encoding: 'utf-8' | 'base64'
  mime: string
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

/** 获取 Sidecar 容器执行日志 */
export const getAttemptSidecarLogsApi = (
  attemptId: number,
  lines = 500
): Promise<IResponse<{ logs: string; lines_requested: number }>> =>
  request.get({
    url: `${STUDENT_BASE}/exam-attempts/${attemptId}/logs`,
    params: { lines }
  })

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
  best_only?: boolean
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

// ─── 第13期：复核 API ─────────────────────────────────────────────────────────

/** artifacts 目录树 */
export const getArtifactsTreeApi = (attemptId: number): Promise<IResponse<ArtifactsTreeResponse>> =>
  request.get({ url: `${TEACHER_BASE}/exam-attempts/${attemptId}/artifacts` })

/** 读取单个 artifact 文件 */
export const getArtifactFileApi = (
  attemptId: number,
  path: string
): Promise<IResponse<ArtifactFileContent>> =>
  request.get({
    url: `${TEACHER_BASE}/exam-attempts/${attemptId}/artifacts/file`,
    params: { path }
  })

/** 提交人工评分 */
export const submitManualScoreApi = (
  attemptId: number,
  data: ManualScoreRequest
): Promise<IResponse<TeacherAttemptFull>> =>
  request.post({ url: `${TEACHER_BASE}/exam-attempts/${attemptId}/manual-score`, data })

/** 批量删除考试尝试（含 artifacts/submissions） */
export const batchDeleteAttemptsApi = (data: {
  attempt_ids: number[]
}): Promise<IResponse<{ deleted_ids: number[] }>> =>
  request.post({ url: `${TEACHER_BASE}/exam-attempts/batch-delete`, data })

/** 覆盖客观分 / pass */
export const overrideScoresApi = (
  attemptId: number,
  data: OverrideRequest
): Promise<IResponse<TeacherAttemptFull>> =>
  request.post({ url: `${TEACHER_BASE}/exam-attempts/${attemptId}/override`, data })

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

// ─── 第14期：提交代码只读查看 API ────────────────────────────────────────────

export interface SubmissionFileItem {
  name: string
  relative_path: string
  type: 'file' | 'directory'
  size: number | null
  mime: string | null
}

export interface SubmissionFileContent {
  content: string
  encoding: 'utf-8' | 'base64'
  mime: string
  modified_at?: number
}

/** 列出学生提交代码文件树 */
export const listSubmissionFilesApi = (
  attemptId: number,
  path?: string
): Promise<IResponse<{ items: SubmissionFileItem[]; path: string }>> =>
  request.get({
    url: `${TEACHER_BASE}/exam-attempts/${attemptId}/submission/files`,
    params: path ? { path } : undefined
  })

/** 读取学生提交代码文件内容 */
export const readSubmissionFileApi = (
  attemptId: number,
  path: string
): Promise<IResponse<SubmissionFileContent>> =>
  request.get({
    url: `${TEACHER_BASE}/exam-attempts/${attemptId}/submission/files/read`,
    params: { path }
  })

/** 生成提交代码下载 URL（直接嵌 a[href]） */
export const getSubmissionDownloadUrl = (attemptId: number, path: string): string =>
  `/api/v1/teachers/exam-attempts/${attemptId}/submission/files/download?path=${encodeURIComponent(path)}`
