import request from '@/axios'
import type { ContainerCreate, ContainerResponse, ContainerStatusResponse } from './types'

// ───────────────────────────────────────────
// 学生端 API
// ───────────────────────────────────────────

/**
 * 获取当前学生的容器状态（JWT 自动鉴权）
 *
 * GET /api/v1/students/container/mine
 */
export const getMyContainerApi = (): Promise<IResponse<ContainerStatusResponse>> => {
  return request.get({ url: '/students/container/mine' })
}

/**
 * 学生请求分配容器（JWT 自动鉴权）
 *
 * POST /api/v1/students/container/request
 *
 * 若已有容器则返回现有容器，否则自动创建新容器。
 */
export const requestContainerApi = (): Promise<IResponse<ContainerResponse>> => {
  return request.post({ url: '/students/container/request' })
}

/**
 * 销毁当前容器并创建新容器（原子操作）
 *
 * POST /api/v1/students/container/destroy-and-recreate
 */
export const destroyAndRecreateApi = (): Promise<IResponse<ContainerResponse>> => {
  return request.post({ url: '/students/container/destroy-and-recreate' })
}

/**
 * 启动学生的已停止容器
 *
 * POST /api/v1/students/container/start
 */
export const startMyContainerApi = (): Promise<IResponse<ContainerStatusResponse>> => {
  return request.post({ url: '/students/container/start' })
}

// ───────────────────────────────────────────
// 教师端 API
// ───────────────────────────────────────────

/**
 * 获取所有容器列表
 *
 * GET /api/v1/teachers/containers/
 */
export const listContainersApi = (
  skip = 0,
  limit = 100
): Promise<IResponse<ContainerResponse[]>> => {
  return request.get({ url: '/teachers/containers/', params: { skip, limit } })
}

/**
 * 创建容器
 *
 * POST /api/v1/teachers/containers/
 */
export const createContainerApi = (
  data: ContainerCreate
): Promise<IResponse<ContainerResponse>> => {
  return request.post({ url: '/teachers/containers/', data })
}

/**
 * 获取容器详情
 *
 * GET /api/v1/teachers/containers/{id}
 */
export const getContainerApi = (id: number): Promise<IResponse<ContainerResponse>> => {
  return request.get({ url: `/teachers/containers/${id}` })
}

/**
 * 启动容器
 *
 * POST /api/v1/teachers/containers/{id}/start
 */
export const startContainerApi = (id: number): Promise<IResponse<ContainerResponse>> => {
  return request.post({ url: `/teachers/containers/${id}/start` })
}

/**
 * 停止容器
 *
 * POST /api/v1/teachers/containers/{id}/stop
 */
export const stopContainerApi = (id: number): Promise<IResponse<ContainerResponse>> => {
  return request.post({ url: `/teachers/containers/${id}/stop` })
}

/**
 * 删除容器
 *
 * DELETE /api/v1/teachers/containers/{id}
 */
export const deleteContainerApi = (id: number): Promise<IResponse<null>> => {
  return request.delete({ url: `/teachers/containers/${id}` })
}
