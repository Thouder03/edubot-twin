/**
 * 测评脚本包 API（第11期）
 */
import request from '@/axios'
import type {
  BundleFileListResponse,
  BundleFileReadResponse,
  BundleFileSaveResponse,
  BundleFileUploadResponse
} from '@/api/experiment/types'
import type {
  ExamEvalScriptCreateRequest,
  ExamEvalScriptListResponse,
  ExamEvalScriptResponse
} from './types'

const BASE = '/api/v1/teachers/exam-eval-scripts'

export const getExamEvalScriptListApi = (params?: {
  page?: number
  page_size?: number
  keyword?: string
}): Promise<IResponse<ExamEvalScriptListResponse>> => {
  return request.get({ url: BASE, params })
}

export const createExamEvalScriptApi = (
  data: ExamEvalScriptCreateRequest
): Promise<IResponse<ExamEvalScriptResponse>> => {
  return request.post({ url: BASE, data })
}

export const getExamEvalScriptDetailApi = (
  id: number
): Promise<IResponse<ExamEvalScriptResponse>> => {
  return request.get({ url: `${BASE}/${id}` })
}

export const patchExamEvalScriptApi = (
  id: number,
  data: Partial<ExamEvalScriptCreateRequest>
): Promise<IResponse<ExamEvalScriptResponse>> => {
  return request.patch({ url: `${BASE}/${id}`, data })
}

export const deleteExamEvalScriptApi = (id: number): Promise<IResponse<null>> => {
  return request.delete({ url: `${BASE}/${id}` })
}

// ─── Files 子协议 ─────────────────────────────────────────────────────────────

export const listExamEvalScriptFilesApi = (
  id: number,
  path?: string
): Promise<IResponse<BundleFileListResponse>> => {
  return request.get({ url: `${BASE}/${id}/files`, params: path ? { path } : undefined })
}

export const uploadExamEvalScriptFileApi = (
  id: number,
  formData: FormData
): Promise<IResponse<BundleFileUploadResponse>> => {
  return request.post({
    url: `${BASE}/${id}/files/upload`,
    data: formData,
    headers: { 'Content-Type': 'multipart/form-data' }
  })
}

export const readExamEvalScriptFileApi = (
  id: number,
  path: string
): Promise<IResponse<BundleFileReadResponse>> => {
  return request.get({ url: `${BASE}/${id}/files/read`, params: { path } })
}

export const saveExamEvalScriptFileApi = (
  id: number,
  path: string,
  content: string,
  modifiedAt?: number
): Promise<IResponse<BundleFileSaveResponse>> => {
  return request.post({
    url: `${BASE}/${id}/files/save`,
    data: { path, content, ...(modifiedAt !== undefined ? { modified_at: modifiedAt } : {}) }
  })
}

export const deleteExamEvalScriptFileApi = (id: number, path: string): Promise<IResponse<null>> => {
  return request.delete({ url: `${BASE}/${id}/files/delete`, params: { path } })
}
