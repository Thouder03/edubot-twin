import request from '@/axios'
import type {
  BundleFileListResponse,
  BundleFileReadResponse,
  BundleFileSaveResponse,
  BundleFileUploadResponse,
  DryRunStartResponse,
  EnvBundleCreateRequest,
  EnvBundleDetail,
  EnvBundleListItem,
  ExperimentCreateRequest,
  ExperimentDetailResponse,
  ExperimentListResponse,
  ExperimentPublishLogListResponse,
  ExperimentPublishRequest,
  ExperimentPublishResponse,
  ExperimentVersionCreateRequest,
  ExperimentVersionPublishStatusRequest,
  ExperimentVersionPublishStatusResponse,
  ExperimentVersionResponse,
  ExperimentVersionUpdateRequest,
  ExperimentVersionValidateResponse,
  FileBundleCreateRequest,
  FileBundleDetail,
  FileBundleListItem,
  FileBundleListResponse,
  FileBundlePatchResponse,
  StudentAvailableVersionItem,
  StudentSimulationStartRequest,
  StudentSimulationStartResponse,
  StudentSimulationTaskResponse
} from './types'

export const getExperimentListApi = (params?: {
  page?: number
  page_size?: number
  keyword?: string
  status?: string
  sort_by?: string
  sort_order?: 'asc' | 'desc'
}): Promise<IResponse<ExperimentListResponse>> => {
  return request.get({ url: '/api/v1/teachers/experiments', params })
}

export const createExperimentApi = (data: ExperimentCreateRequest): Promise<IResponse<any>> => {
  return request.post({ url: '/api/v1/teachers/experiments', data })
}

export const getExperimentDetailApi = (
  experimentId: number
): Promise<IResponse<ExperimentDetailResponse>> => {
  return request.get({ url: `/api/v1/teachers/experiments/${experimentId}` })
}

export const createExperimentVersionApi = (
  experimentId: number,
  data: ExperimentVersionCreateRequest
): Promise<IResponse<ExperimentVersionResponse>> => {
  return request.post({ url: `/api/v1/teachers/experiments/${experimentId}/versions`, data })
}

export const updateExperimentVersionApi = (
  experimentId: number,
  versionId: number,
  data: ExperimentVersionUpdateRequest
): Promise<IResponse<ExperimentVersionResponse>> => {
  return request.put({
    url: `/api/v1/teachers/experiments/${experimentId}/versions/${versionId}`,
    data
  })
}

export const publishExperimentVersionApi = (
  experimentId: number,
  versionId: number,
  data: ExperimentPublishRequest
): Promise<IResponse<ExperimentPublishResponse>> => {
  return request.post({
    url: `/api/v1/teachers/experiments/${experimentId}/versions/${versionId}/publish`,
    data
  })
}

export const updateExperimentVersionPublishStatusApi = (
  experimentId: number,
  versionId: number,
  data: ExperimentVersionPublishStatusRequest
): Promise<IResponse<ExperimentVersionPublishStatusResponse>> => {
  return request.patch({
    url: `/api/v1/teachers/experiments/${experimentId}/versions/${versionId}/publish-status`,
    data
  })
}

export const deleteExperimentVersionApi = (
  experimentId: number,
  versionId: number
): Promise<IResponse<null>> => {
  return request.delete({
    url: `/api/v1/teachers/experiments/${experimentId}/versions/${versionId}`
  })
}

export const validateExperimentVersionApi = (
  experimentId: number,
  versionId: number
): Promise<IResponse<ExperimentVersionValidateResponse>> => {
  return request.post({
    url: `/api/v1/teachers/experiments/${experimentId}/versions/${versionId}/validate`
  })
}

export const getExperimentPublishLogsApi = (
  experimentId: number
): Promise<IResponse<ExperimentPublishLogListResponse>> => {
  return request.get({ url: `/api/v1/teachers/experiments/${experimentId}/publish-logs` })
}

export const getAvailableExperimentsApi = (): Promise<IResponse<StudentAvailableVersionItem[]>> => {
  return request.get({ url: '/api/v1/students/experiments/available' })
}

export const startSimulationApi = (
  data: StudentSimulationStartRequest
): Promise<IResponse<StudentSimulationStartResponse>> => {
  return request.post({ url: '/api/v1/students/simulation/start', data })
}

export const getSimulationTaskApi = (
  taskId: string
): Promise<IResponse<StudentSimulationTaskResponse>> => {
  return request.get({ url: `/api/v1/students/tasks/${taskId}` })
}

// ─── 文件包（FileBundle）API ──────────────────────────────────────────────────

export const createFileBundleApi = (
  data: FileBundleCreateRequest
): Promise<IResponse<FileBundleListItem>> => {
  return request.post({ url: '/api/v1/teachers/file-bundles', data })
}

export const getFileBundleListApi = (params?: {
  page?: number
  page_size?: number
  keyword?: string
}): Promise<IResponse<FileBundleListResponse>> => {
  return request.get({ url: '/api/v1/teachers/file-bundles', params })
}

export const getFileBundleDetailApi = (bundleId: number): Promise<IResponse<FileBundleDetail>> => {
  return request.get({ url: `/api/v1/teachers/file-bundles/${bundleId}` })
}

export const patchFileBundleApi = (
  bundleId: number,
  data: { name: string }
): Promise<IResponse<FileBundlePatchResponse>> => {
  return request.patch({ url: `/api/v1/teachers/file-bundles/${bundleId}`, data })
}

export const deleteFileBundleApi = (bundleId: number): Promise<IResponse<null>> => {
  return request.delete({ url: `/api/v1/teachers/file-bundles/${bundleId}` })
}

export const uploadFileToBundleApi = (
  bundleId: number,
  formData: FormData
): Promise<IResponse<BundleFileUploadResponse>> => {
  return request.post({
    url: `/api/v1/teachers/file-bundles/${bundleId}/files/upload`,
    data: formData,
    headers: { 'Content-Type': 'multipart/form-data' }
  })
}

export const listFileBundleFilesApi = (
  bundleId: number,
  path?: string
): Promise<IResponse<BundleFileListResponse>> => {
  return request.get({
    url: `/api/v1/teachers/file-bundles/${bundleId}/files`,
    params: path ? { path } : undefined
  })
}

export const readFileBundleFileApi = (
  bundleId: number,
  path: string
): Promise<IResponse<BundleFileReadResponse>> => {
  return request.get({
    url: `/api/v1/teachers/file-bundles/${bundleId}/files/read`,
    params: { path }
  })
}

export const saveFileBundleFileApi = (
  bundleId: number,
  path: string,
  content: string,
  modifiedAt?: number
): Promise<IResponse<BundleFileSaveResponse>> => {
  return request.post({
    url: `/api/v1/teachers/file-bundles/${bundleId}/files/save`,
    data: { path, content, ...(modifiedAt !== undefined ? { modified_at: modifiedAt } : {}) }
  })
}

export const deleteFileBundleFileApi = (
  bundleId: number,
  path: string
): Promise<IResponse<null>> => {
  return request.delete({
    url: `/api/v1/teachers/file-bundles/${bundleId}/files/delete`,
    params: { path }
  })
}

// ─── 环境包（EnvBundle）API ───────────────────────────────────────────────────

export const createEnvBundleApi = (
  data: EnvBundleCreateRequest
): Promise<IResponse<EnvBundleListItem>> => {
  return request.post({ url: '/api/v1/teachers/env-bundles', data })
}

export const getEnvBundleListApi = (params?: {
  page?: number
  page_size?: number
  keyword?: string
}): Promise<IResponse<{ total: number; list: EnvBundleListItem[] }>> => {
  return request.get({ url: '/api/v1/teachers/env-bundles', params })
}

export const getEnvBundleDetailApi = (envBundleId: number): Promise<IResponse<EnvBundleDetail>> => {
  return request.get({ url: `/api/v1/teachers/env-bundles/${envBundleId}` })
}

export const patchEnvBundleApi = (
  envBundleId: number,
  data: Partial<EnvBundleCreateRequest>
): Promise<IResponse<EnvBundleDetail>> => {
  return request.patch({ url: `/api/v1/teachers/env-bundles/${envBundleId}`, data })
}

export const deleteEnvBundleApi = (envBundleId: number): Promise<IResponse<null>> => {
  return request.delete({ url: `/api/v1/teachers/env-bundles/${envBundleId}` })
}

export const uploadFileToEnvBundleApi = (
  envBundleId: number,
  formData: FormData
): Promise<IResponse<BundleFileUploadResponse>> => {
  return request.post({
    url: `/api/v1/teachers/env-bundles/${envBundleId}/files/upload`,
    data: formData,
    headers: { 'Content-Type': 'multipart/form-data' }
  })
}

export const listEnvBundleFilesApi = (
  envBundleId: number,
  path?: string
): Promise<IResponse<BundleFileListResponse>> => {
  return request.get({
    url: `/api/v1/teachers/env-bundles/${envBundleId}/files`,
    params: path ? { path } : undefined
  })
}

export const readEnvBundleFileApi = (
  envBundleId: number,
  path: string
): Promise<IResponse<BundleFileReadResponse>> => {
  return request.get({
    url: `/api/v1/teachers/env-bundles/${envBundleId}/files/read`,
    params: { path }
  })
}

export const saveEnvBundleFileApi = (
  envBundleId: number,
  path: string,
  content: string,
  modifiedAt?: number
): Promise<IResponse<BundleFileSaveResponse>> => {
  return request.post({
    url: `/api/v1/teachers/env-bundles/${envBundleId}/files/save`,
    data: { path, content, ...(modifiedAt !== undefined ? { modified_at: modifiedAt } : {}) }
  })
}

export const deleteEnvBundleFileApi = (
  envBundleId: number,
  path: string
): Promise<IResponse<null>> => {
  return request.delete({
    url: `/api/v1/teachers/env-bundles/${envBundleId}/files/delete`,
    params: { path }
  })
}

export const getExperimentVersionsForDryRunApi = (): Promise<
  IResponse<
    { experiment_id: number; experiment_name: string; versions: ExperimentVersionResponse[] }[]
  >
> => {
  return request.get({ url: '/api/v1/teachers/experiments/versions-for-dry-run' })
}

export const startDryRunApi = (
  envBundleId: number,
  versionId: number
): Promise<IResponse<DryRunStartResponse>> => {
  return request.post({
    url: `/api/v1/teachers/env-bundles/${envBundleId}/dry-run`,
    data: { version_id: versionId }
  })
}

export const getDryRunDockerLogsApi = (lines = 500): Promise<IResponse<{ logs: string; lines_requested: number }>> => {
  return request.get({ url: '/api/v1/teachers/dry-run-tools/docker-logs', params: { lines } })
}

export const getDryRunFailureReviewApi = (): Promise<IResponse<{ container: Record<string, unknown>; task: Record<string, unknown> | null }>> => {
  return request.get({ url: '/api/v1/teachers/dry-run-tools/failure-review' })
}
