/**
 * 教师端成绩预览 API（第16期）
 *
 * GET /teachers/grade-preview → GradePreviewListResponse
 */

import request from '@/axios'

// ─── 类型定义 ────────────────────────────────────────────────────────────────

export interface GradePreviewStudentInfo {
  student_id: number
  username: string
  real_name: string | null
}

export interface GradePreviewItem {
  attempt_id: number
  exam_id: number
  exam_name: string
  student: GradePreviewStudentInfo
  status: string
  objective_score: number | null
  manual_score: number | null
  final_score: number | null
  pass: boolean | null
  summary: string | null
  teacher_comment: string | null
  review_status: string
  result_json_display: Record<string, unknown> | null
  custom_fields: Record<string, unknown> | null
  started_at: string | null
  ended_at: string | null
  duration_ms: number | null
  created_at: string
}

export interface GradePreviewListResponse {
  items: GradePreviewItem[]
  total: number
  page: number
  page_size: number
}

export interface GradePreviewQueryParams {
  exam_id?: number
  student_id?: number
  page?: number
  page_size?: number
}

// ─── API 函数 ────────────────────────────────────────────────────────────────

export const getGradePreviewApi = (
  params?: GradePreviewQueryParams
): Promise<IResponse<GradePreviewListResponse>> =>
  request.get({ url: '/api/v1/teachers/grade-preview', params })
