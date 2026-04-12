/**
 * 考试域 TypeScript 类型定义（第11期）
 */

// ─── 考试模式枚举 ────────────────────────────────────────────────────────────
export type ExamMode = 'result_run' | 'process_run' | 'multi_stage_run'
export type ExamStatusType = 'draft' | 'published' | 'archived'
export type EvalScriptValidateStatus = 'pending' | 'valid' | 'invalid'

// ─── 考试定义 ────────────────────────────────────────────────────────────────

export interface ExamCreateRequest {
  name: string
  code: string
  description?: string
  exam_mode: ExamMode
}

export interface ExamUpdateRequest {
  name?: string
  description?: string
  exam_mode?: ExamMode
  env_snapshot_id?: number | null
  file_snapshot_id?: number | null
  eval_script_id?: number | null
  runtime_policy?: Record<string, unknown>
  panel_policy?: Record<string, unknown>
  scoring_policy?: Record<string, unknown>
  sidecar_policy?: Record<string, unknown>
  teacher_comment_template?: string
  updated_at?: string
}

export interface ExamResponse {
  id: number
  name: string
  code: string
  description: string | null
  exam_mode: ExamMode
  status: ExamStatusType
  env_snapshot_id: number | null
  file_snapshot_id: number | null
  eval_script_id: number | null
  runtime_policy_json: Record<string, unknown>
  panel_policy_json: Record<string, unknown>
  scoring_policy_json: Record<string, unknown>
  sidecar_policy_json: Record<string, unknown>
  teacher_comment_template: string | null
  created_by: number
  created_at: string
  updated_at: string
  published_at: string | null
}

export interface ExamListItem {
  id: number
  name: string
  code: string
  exam_mode: ExamMode
  status: ExamStatusType
  env_snapshot_id: number | null
  file_snapshot_id: number | null
  eval_script_id: number | null
  created_at: string
  published_at: string | null
}

export interface ExamListResponse {
  total: number
  items: ExamListItem[]
}

// ─── 考试环境快照 ────────────────────────────────────────────────────────────

export interface ExamEnvSnapshotCreateRequest {
  name: string
  container_target_dir?: string
}

export interface ExamEnvSnapshotCopyRequest {
  source_env_bundle_id: number
  name: string
}

export interface ExamEnvSnapshotResponse {
  id: number
  name: string
  source_env_bundle_id: number | null
  storage_root: string
  container_target_dir: string
  file_count: number
  total_size_bytes: number
  created_by: number
  created_at: string
  updated_at: string
}

export interface ExamEnvSnapshotListItem {
  id: number
  name: string
  container_target_dir: string
  file_count: number
  total_size_bytes: number
  created_at: string
}

export interface ExamEnvSnapshotListResponse {
  total: number
  items: ExamEnvSnapshotListItem[]
}

// ─── 考试文件快照 ────────────────────────────────────────────────────────────

export interface ExamFileSnapshotCreateRequest {
  name: string
}

export interface ExamFileSnapshotCopyRequest {
  source_file_bundle_id: number
  name: string
}

export interface ExamFileSnapshotResponse {
  id: number
  name: string
  source_file_bundle_id: number | null
  storage_root: string
  file_count: number
  total_size_bytes: number
  file_manifest: Array<{ relative_path: string; chmod_mode: string }>
  created_by: number
  created_at: string
  updated_at: string
}

export interface ExamFileSnapshotListItem {
  id: number
  name: string
  file_count: number
  total_size_bytes: number
  created_at: string
}

export interface ExamFileSnapshotListResponse {
  total: number
  items: ExamFileSnapshotListItem[]
}

// ─── 测评脚本包 ──────────────────────────────────────────────────────────────

export interface ExamEvalScriptCreateRequest {
  name: string
  description?: string
  entry_point?: string
}

export interface ExamEvalScriptResponse {
  id: number
  name: string
  description: string | null
  storage_root: string
  entry_point: string
  file_count: number
  total_size_bytes: number
  validate_status: EvalScriptValidateStatus
  created_by: number
  created_at: string
  updated_at: string
}

export interface ExamEvalScriptListItem {
  id: number
  name: string
  description: string | null
  entry_point: string
  file_count: number
  total_size_bytes: number
  validate_status: EvalScriptValidateStatus
  created_at: string
}

export interface ExamEvalScriptListResponse {
  total: number
  items: ExamEvalScriptListItem[]
}
