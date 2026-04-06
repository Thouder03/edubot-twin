/**
 * 容器 API 类型定义
 *
 * 与后端 app/schemas/container.py 保持一致
 */

/** 容器状态枚举 */
export type ContainerStatus = 'creating' | 'running' | 'stopping' | 'stopped' | 'error' | 'removing'

/** 容器完整信息（教师端 / 创建响应） */
export interface ContainerResponse {
  id: number
  container_id: string | null
  student_id: number
  status: ContainerStatus
  image_name: string
  gzbridge_port: number | null
  rosbridge_port: number | null
  gzbridge_url: string | null
  rosbridge_url: string | null
  error_message: string | null
  created_at: string
  updated_at: string
  current_version_id: number | null
}

/** 容器简要状态（学生端查询响应） */
export interface ContainerStatusResponse {
  id: number
  status: ContainerStatus
  gzbridge_url: string | null
  rosbridge_url: string | null
  current_version_id: number | null
}

/** 创建容器请求体 */
export interface ContainerCreate {
  student_id: number
  image_name?: string
}

/** 页面退出时停止容器的请求体（Token in body，供 sendBeacon 使用） */
export interface StopOnExitRequest {
  token: string
}
