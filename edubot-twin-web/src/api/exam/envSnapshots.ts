/**
 * 考试环境快照 API（第11期）
 */
import request from '@/axios'
import type {
  BundleFileListResponse,
  BundleFileReadResponse,
  BundleFileSaveResponse,
  BundleFileUploadResponse
} from '@/api/experiment/types'
import type {
  ExamEnvSnapshotCopyRequest,
  ExamEnvSnapshotCreateRequest,
  ExamEnvSnapshotListResponse,
  ExamEnvSnapshotResponse
} from './types'

const BASE = '/api/v1/teachers/exam-env-snapshots'

export const getExamEnvSnapshotListApi = (params?: {
  page?: number
  page_size?: number
  keyword?: string
}): Promise<IResponse<ExamEnvSnapshotListResponse>> => {
  return request.get({ url: BASE, params })
}

export const createExamEnvSnapshotApi = (
  data: ExamEnvSnapshotCreateRequest
): Promise<IResponse<ExamEnvSnapshotResponse>> => {
  return request.post({ url: BASE, data })
}

export const copyExamEnvSnapshotApi = (
  data: ExamEnvSnapshotCopyRequest
): Promise<IResponse<ExamEnvSnapshotResponse>> => {
  return request.post({ url: `${BASE}/copy`, data })
}

export const getExamEnvSnapshotDetailApi = (
  id: number
): Promise<IResponse<ExamEnvSnapshotResponse>> => {
  return request.get({ url: `${BASE}/${id}` })
}

export const patchExamEnvSnapshotApi = (
  id: number,
  data: Partial<ExamEnvSnapshotCreateRequest>
): Promise<IResponse<ExamEnvSnapshotResponse>> => {
  return request.patch({ url: `${BASE}/${id}`, data })
}

export const deleteExamEnvSnapshotApi = (id: number): Promise<IResponse<null>> => {
  return request.delete({ url: `${BASE}/${id}` })
}

// ─── Files 子协议 ─────────────────────────────────────────────────────────────

export const listExamEnvSnapshotFilesApi = (
  id: number,
  path?: string
): Promise<IResponse<BundleFileListResponse>> => {
  return request.get({ url: `${BASE}/${id}/files`, params: path ? { path } : undefined })
}

export const uploadExamEnvSnapshotFileApi = (
  id: number,
  formData: FormData
): Promise<IResponse<BundleFileUploadResponse>> => {
  return request.post({
    url: `${BASE}/${id}/files/upload`,
    data: formData,
    headers: { 'Content-Type': 'multipart/form-data' }
  })
}

export const readExamEnvSnapshotFileApi = (
  id: number,
  path: string
): Promise<IResponse<BundleFileReadResponse>> => {
  return request.get({ url: `${BASE}/${id}/files/read`, params: { path } })
}

export const saveExamEnvSnapshotFileApi = (
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

export const deleteExamEnvSnapshotFileApi = (
  id: number,
  path: string
): Promise<IResponse<null>> => {
  return request.delete({ url: `${BASE}/${id}/files/delete`, params: { path } })
}
