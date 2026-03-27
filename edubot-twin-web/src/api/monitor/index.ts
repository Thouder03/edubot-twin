import request from '@/axios'

export const getContainerMonitorListApi = () => {
  return request.get({ url: '/api/v1/teachers/containers/' })
}

export const batchStartContainersApi = (container_ids: number[]) => {
  return request.post({ url: '/api/v1/teachers/containers/batch-start', data: { container_ids } })
}

export const batchStopContainersApi = (container_ids: number[]) => {
  return request.post({ url: '/api/v1/teachers/containers/batch-stop', data: { container_ids } })
}

export const batchDeleteContainersApi = (container_ids: number[]) => {
  return request.post({ url: '/api/v1/teachers/containers/batch-delete', data: { container_ids } })
}
