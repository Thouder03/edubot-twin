/**
 * 考试文件快照 API（第11期）
 */
import request from '@/axios'
import type {
  BundleFileListResponse,
  BundleFileReadResponse,
  BundleFileSaveResponse,
  BundleFileUploadResponse
} from '@/api/experiment/types'
import type {
  ExamFileSnapshotCopyRequest,
  ExamFileSnapshotCreateRequest,
  ExamFileSnapshotListResponse,
  ExamFileSnapshotResponse
} from './types'

const BASE = '/api/v1/teachers/exam-file-snapshots'

export const getExamFileSnapshotListApi = (params?: {
  page?: number
  page_size?: number
  keyword?: string
}): Promise<IResponse<ExamFileSnapshotListResponse>> => {
  return request.get({ url: BASE, params })
}

export const createExamFileSnapshotApi = (
  data: ExamFileSnapshotCreateRequest
): Promise<IResponse<ExamFileSnapshotResponse>> => {
  return request.post({ url: BASE, data })
}

export const copyExamFileSnapshotApi = (
  data: ExamFileSnapshotCopyRequest
): Promise<IResponse<ExamFileSnapshotResponse>> => {
  return request.post({ url: `${BASE}/copy`, data })
}

export const getExamFileSnapshotDetailApi = (
  id: number
): Promise<IResponse<ExamFileSnapshotResponse>> => {
  return request.get({ url: `${BASE}/${id}` })
}

export const patchExamFileSnapshotApi = (
  id: number,
  data: Partial<ExamFileSnapshotCreateRequest>
): Promise<IResponse<ExamFileSnapshotResponse>> => {
  return request.patch({ url: `${BASE}/${id}`, data })
}

export const deleteExamFileSnapshotApi = (id: number): Promise<IResponse<null>> => {
  return request.delete({ url: `${BASE}/${id}` })
}

// ─── Files 子协议 ─────────────────────────────────────────────────────────────

export const listExamFileSnapshotFilesApi = (
  id: number,
  path?: string
): Promise<IResponse<BundleFileListResponse>> => {
  return request.get({ url: `${BASE}/${id}/files`, params: path ? { path } : undefined })
}

export const uploadExamFileSnapshotFileApi = (
  id: number,
  formData: FormData
): Promise<IResponse<BundleFileUploadResponse>> => {
  return request.post({
    url: `${BASE}/${id}/files/upload`,
    data: formData,
    headers: { 'Content-Type': 'multipart/form-data' }
  })
}

export const readExamFileSnapshotFileApi = (
  id: number,
  path: string
): Promise<IResponse<BundleFileReadResponse>> => {
  return request.get({ url: `${BASE}/${id}/files/read`, params: { path } })
}

export const saveExamFileSnapshotFileApi = (
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

export const deleteExamFileSnapshotFileApi = (
  id: number,
  path: string
): Promise<IResponse<null>> => {
  return request.delete({ url: `${BASE}/${id}/files/delete`, params: { path } })
}
