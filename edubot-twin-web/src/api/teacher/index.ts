// src/api/teacher/index.ts
// 教师端 API 模块

import request from '@/axios'
import type {
  StudentCreateRequest,
  StudentUpdateRequest,
  StudentListResponse,
  StudentInfo,
  StudentImportResult,
  ContainerMonitorListResponse
} from './types'

// ─── 学生管理 API ────────────────────────────────────────────

/** 获取学生列表（支持分页 + 关键词搜索） */
export const getStudentListApi = (params?: {
  pageIndex?: number
  pageSize?: number
  keyword?: string
}): Promise<IResponse<StudentListResponse>> => {
  return request.get({ url: '/api/v1/teachers/students', params })
}

/** 获取学生详情 */
export const getStudentApi = (id: number): Promise<IResponse<StudentInfo>> => {
  return request.get({ url: `/api/v1/teachers/students/${id}` })
}

/** 创建学生 */
export const createStudentApi = (data: StudentCreateRequest): Promise<IResponse<StudentInfo>> => {
  return request.post({ url: '/api/v1/teachers/students', data })
}

/** 更新学生 */
export const updateStudentApi = (
  id: number,
  data: StudentUpdateRequest
): Promise<IResponse<StudentInfo>> => {
  return request.put({ url: `/api/v1/teachers/students/${id}`, data })
}

/** 删除单个学生 */
export const deleteStudentApi = (id: number): Promise<IResponse<any>> => {
  return request.delete({ url: `/api/v1/teachers/students/${id}` })
}

/** 批量导入学生（CSV 文件） */
export const importStudentsApi = (file: File): Promise<IResponse<StudentImportResult>> => {
  const formData = new FormData()
  formData.append('file', file)
  return request.post({
    url: '/api/v1/teachers/students/import',
    data: formData,
    headers: { 'Content-Type': 'multipart/form-data' }
  })
}

// ─── 容器监控 API ────────────────────────────────────────────

/** 获取容器运行监控列表（专用 monitor 端点） */
export const getContainerMonitorListApi = (params?: {
  pageIndex?: number
  pageSize?: number
}): Promise<IResponse<ContainerMonitorListResponse>> => {
  return request.get({ url: '/api/v1/teachers/containers/monitor', params })
}

/** 批量启动容器 */
export const batchStartContainersApi = (container_ids: number[]): Promise<IResponse<any>> => {
  return request.post({
    url: '/api/v1/teachers/containers/batch-start',
    data: { container_ids }
  })
}

/** 批量停止容器 */
export const batchStopContainersApi = (container_ids: number[]): Promise<IResponse<any>> => {
  return request.post({
    url: '/api/v1/teachers/containers/batch-stop',
    data: { container_ids }
  })
}

/** 批量删除容器 */
export const batchDeleteContainersApi = (container_ids: number[]): Promise<IResponse<any>> => {
  return request.post({
    url: '/api/v1/teachers/containers/batch-delete',
    data: { container_ids }
  })
}
