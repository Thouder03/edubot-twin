/**
 * 考试管理增强 API（第15期）
 *
 * 教师端：
 *   GET  /teachers/exam-review-list          → 每学生每考试最高分视图
 *   POST /teachers/exam-attempts/delete-abnormal → 一键删除异常尝试
 */

import request from '@/axios'
import type { AttemptStudentInfo, ExamAttemptStatus } from './attempts'

const TEACHER_BASE = '/api/v1/teachers'

// ─── 类型定义 ────────────────────────────────────────────────────────────────

/** 复核列表条目（每学生每考试最高分，含 exam_name） */
export interface ExamReviewListItem {
  attempt_id: number
  exam_id: number
  exam_name: string
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

export interface ExamReviewListResponse {
  items: ExamReviewListItem[]
  total: number
  page: number
  page_size: number
}

export interface DeleteAbnormalRequest {
  exam_id?: number | null
}

export interface DeleteAbnormalResponse {
  deleted_ids: number[]
  count: number
}

// ─── API 函数 ────────────────────────────────────────────────────────────────

/** 获取考试结果复核列表 */
export const getExamReviewListApi = (params?: {
  exam_id?: number
  review_status?: string
  sort?: string
  page?: number
  page_size?: number
  best_only?: boolean
}): Promise<IResponse<ExamReviewListResponse>> =>
  request.get({ url: `${TEACHER_BASE}/exam-review-list`, params })

/** 一键删除异常尝试（error/aborted，含文件清理） */
export const deleteAbnormalAttemptsApi = (
  data: DeleteAbnormalRequest
): Promise<IResponse<DeleteAbnormalResponse>> =>
  request.post({ url: `${TEACHER_BASE}/exam-attempts/delete-abnormal`, data })
