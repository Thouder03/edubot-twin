import request from '@/axios'
import type {
  ExperimentCreateRequest,
  ExperimentDetailResponse,
  ExperimentListResponse,
  ExperimentPublishLogListResponse,
  ExperimentPublishRequest,
  ExperimentPublishResponse,
  ExperimentVersionCreateRequest,
  ExperimentVersionResponse,
  ExperimentVersionUpdateRequest,
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
