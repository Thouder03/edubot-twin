/**
 * 学生端成绩 API（第16期）
 *
 * GET /students/my-grade-summary              → StudentGradeSummaryItem[]
 * GET /students/exams/{exam_id}/my-grade-detail → StudentAttemptGradeDetailItem[]
 */

import request from '@/axios'

// ─── 类型定义 ────────────────────────────────────────────────────────────────

export interface StudentGradeSummaryItem {
  exam_id: number
  exam_name: string
  exam_code: string
  best_attempt_id: number
  objective_score: number | null
  final_score: number | null
  pass: boolean | null
  summary: string | null
  teacher_comment: string | null
  status: string
  ended_at: string | null
}

export interface StudentAttemptGradeDetailItem {
  attempt_id: number
  status: string
  objective_score: number | null
  final_score: number | null
  pass: boolean | null
  summary: string | null
  teacher_comment: string | null
  custom_fields: Record<string, unknown> | null
  has_code_snapshot: boolean
  started_at: string | null
  ended_at: string | null
  duration_ms: number | null
  created_at: string
}

// ─── API 函数 ────────────────────────────────────────────────────────────────

export const getMyGradeSummaryApi = (): Promise<IResponse<StudentGradeSummaryItem[]>> =>
  request.get({ url: '/api/v1/students/my-grade-summary' })

export const getMyGradeDetailApi = (examId: number): Promise<IResponse<StudentAttemptGradeDetailItem[]>> =>
  request.get({ url: `/api/v1/students/exams/${examId}/my-grade-detail` })
