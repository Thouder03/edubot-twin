/**
 * 考试定义 API（第11期）
 */
import request from '@/axios'
import type { ExamCreateRequest, ExamListResponse, ExamResponse, ExamUpdateRequest } from './types'

const BASE = '/api/v1/teachers/exams'

export const getExamListApi = (params?: {
  page?: number
  page_size?: number
  keyword?: string
  status?: string
  exam_mode?: string
}): Promise<IResponse<ExamListResponse>> => {
  return request.get({ url: BASE, params })
}

export const createExamApi = (data: ExamCreateRequest): Promise<IResponse<ExamResponse>> => {
  return request.post({ url: BASE, data })
}

export const getExamDetailApi = (examId: number): Promise<IResponse<ExamResponse>> => {
  return request.get({ url: `${BASE}/${examId}` })
}

export const updateExamApi = (
  examId: number,
  data: ExamUpdateRequest
): Promise<IResponse<ExamResponse>> => {
  return request.patch({ url: `${BASE}/${examId}`, data })
}

export const deleteExamApi = (examId: number): Promise<IResponse<null>> => {
  return request.delete({ url: `${BASE}/${examId}` })
}

export const publishExamApi = (examId: number): Promise<IResponse<ExamResponse>> => {
  return request.post({ url: `${BASE}/${examId}/publish` })
}

export const archiveExamApi = (examId: number): Promise<IResponse<ExamResponse>> => {
  return request.post({ url: `${BASE}/${examId}/archive` })
}

export const republishExamApi = (examId: number): Promise<IResponse<ExamResponse>> => {
  return request.post({ url: `${BASE}/${examId}/republish` })
}
