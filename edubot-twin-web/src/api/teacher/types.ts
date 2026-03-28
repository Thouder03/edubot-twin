// src/api/teacher/types.ts
// 教师端统一类型定义（对应 SDD 第五期 §7）

// ─── 学生管理 ────────────────────────────────────────────────

/** 学生信息 */
export interface StudentInfo {
  id: number
  username: string
  real_name: string | null
  email: string | null
  is_active: boolean
  created_at: string
  updated_at: string
}

/** 学生列表分页响应 */
export interface StudentListResponse {
  total: number
  list: StudentInfo[]
}

/** 创建学生请求 */
export interface StudentCreateRequest {
  username: string
  password: string
  real_name: string
  email?: string
}

/** 更新学生请求 */
export interface StudentUpdateRequest {
  real_name?: string
  email?: string
  password?: string
}

// ─── 容器监控 ────────────────────────────────────────────────

/** 容器运行状态枚举 */
export type ContainerStatus = 'creating' | 'running' | 'stopped' | 'error' | 'removing'

/** 容器监控信息（含实时性能数据） */
export interface ContainerMonitorInfo {
  id: number
  container_id: string | null
  student_id: number
  student_name: string
  student_username: string
  purpose: string
  status: ContainerStatus
  image_name: string
  cpu_percent: number
  memory_mb: number
  memory_limit_mb: number
  uptime_seconds: number
  created_at: string
  last_heartbeat_at: string | null
}

/** 容器监控列表响应 */
export interface ContainerMonitorListResponse {
  total: number
  list: ContainerMonitorInfo[]
}
