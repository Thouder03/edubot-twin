import request from '@/axios'
import type { ContainerCreate, ContainerResponse, ContainerStatusResponse } from './types'

// ───────────────────────────────────────────
// 学生端 API
// ───────────────────────────────────────────

/**
 * 获取指定学生的容器状态
 *
 * GET /api/v1/students/container/mine?student_id=xxx
 *
 * @param studentId 学生 ID（临时参数，后续改为从 JWT 自动解析）
 */
export const getMyContainerApi = (
  studentId: number
): Promise<IResponse<ContainerStatusResponse>> => {
  return request.get({ url: '/students/container/mine', params: { student_id: studentId } })
}

/**
 * 学生请求分配容器
 *
 * POST /api/v1/students/container/request?student_id=xxx
 *
 * 若已有容器则返回现有容器，否则自动创建新容器。
 *
 * @param studentId 学生 ID
 */
export const requestContainerApi = (studentId: number): Promise<IResponse<ContainerResponse>> => {
  return request.post({ url: '/students/container/request', params: { student_id: studentId } })
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
