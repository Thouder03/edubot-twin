export interface ExperimentCreateRequest {
  name: string
  code: string
  description?: string
}

export interface ExperimentVersionCreateRequest {
  version_name: string
  environment_key: string
  image_name?: string
  launch_file_path: string
  launch_args_template: Record<string, string>
  file_bundle_id?: number
  env_bundle_id?: number
}

export interface ExperimentVersionUpdateRequest {
  version_name: string
  environment_key: string
  image_name?: string
  launch_file_path: string
  launch_args_template: Record<string, string>
  file_bundle_id?: number
  env_bundle_id?: number
}

export interface ExperimentVersionResponse {
  version_id: number
  experiment_id: number
  version_name: string
  environment_key: string
  image_name: string
  launch_file_path: string
  launch_args_template: Record<string, string>
  file_bundle_id?: number
  env_bundle_id?: number
  publish_status: 'draft' | 'published' | 'deprecated'
  published_at?: string
  created_at: string
  updated_at: string
}

export interface ExperimentListItem {
  experiment_id: number
  name: string
  code: string
  status: 'draft' | 'active' | 'archived'
  latest_version?: string
  published_at?: string
}

export interface ExperimentListResponse {
  total: number
  list: ExperimentListItem[]
}

export interface ExperimentPublishRequest {
  publish_note?: string
}

export interface ExperimentPublishResponse {
  publish_id: number
  published_at: string
  operator: number
}

export interface ExperimentPublishLogItem {
  publish_id: number
  experiment_id: number
  version_id: number
  operator: number
  note?: string
  created_at: string
}

export interface ExperimentPublishLogListResponse {
  total: number
  list: ExperimentPublishLogItem[]
}

export interface ExperimentDetailResponse {
  base_info: {
    experiment_id: number
    name: string
    code: string
    description?: string
    status: 'draft' | 'active' | 'archived'
    created_by: number
    created_at: string
    updated_at: string
  }
  versions: ExperimentVersionResponse[]
  publish_logs: ExperimentPublishLogItem[]
}

export interface StudentAvailableVersionItem {
  version_id: number
  experiment_id: number
  experiment_name: string
  version_name: string
  environment_key: string
  summary?: string
}

export type SimulationTaskStatus = 'PENDING' | 'IN_PROGRESS' | 'SUCCEEDED' | 'FAILED'

export interface SimulationTaskStageStatusItem {
  stage: string
  status: SimulationTaskStatus
  elapsed_ms: number
}

export interface StudentSimulationTaskResponse {
  task_id: string
  task_status: SimulationTaskStatus
  elapsed_ms: number
  retryable: boolean
  error_code?: string
  error_message?: string
  stage_statuses: SimulationTaskStageStatusItem[]
}

export interface StudentSimulationStartRequest {
  version_id: number
  force_recreate?: boolean
}

export interface StudentSimulationStartResponse {
  task_id?: string | null
  container_status: string
  experiment_context: {
    experiment_id: number
    version_id: number
    environment_key: string
  }
}

// ─── 文件包（FileBundle）相关类型 ────────────────────────────────────────────

export interface FileBundleCreateRequest {
  name: string
}

export interface FileBundleListItem {
  bundle_id: number
  name: string
  file_count: number
  total_size_bytes: number
  created_at: string
}

export interface FileBundleListResponse {
  total: number
  list: FileBundleListItem[]
}

export interface FileBundleDetail extends FileBundleListItem {
  storage_root: string
  file_manifest: Array<{ relative_path: string; chmod_mode: string }>
}

export interface FileBundleAffectedVersionItem {
  version_id: number
  experiment_name: string
  version_name: string
}

export interface FileBundlePatchResponse {
  bundle_id: number
  name: string
  affected_versions: FileBundleAffectedVersionItem[]
}

export interface BundleFileItem {
  name: string
  type: 'file' | 'dir'
  size?: number
  modified_at?: string
}

export interface BundleFileListResponse {
  items: BundleFileItem[]
}

export interface BundleFileReadResponse {
  content: string
  encoding: string
  modified_at?: number // 文件修改时间戳（Unix timestamp，用于冲突检测）
}

export interface BundleFileSaveResponse {
  modified_at: number // 保存后的新 mtime，用于后续冲突检测
}

export interface BundleFileUploadResponse {
  file_count: number
  total_size_bytes: number
}

// ─── 环境包（EnvBundle）相关类型 ────────────────────────────────────────────

export interface EnvBundleCreateRequest {
  name: string
  container_target_dir: string
  access_level: 'readonly' | 'readwrite' | 'hidden'
}

export interface EnvBundleListItem {
  env_bundle_id: number
  name: string
  container_target_dir: string
  created_at: string
}

export interface EnvBundleListResponse {
  total: number
  list: EnvBundleListItem[]
}

export interface EnvBundleDetail extends EnvBundleListItem {
  access_level: 'readonly' | 'readwrite' | 'hidden'
  file_count: number
  total_size_bytes: number
  storage_root: string
}

export interface DryRunStartResponse {
  container_id: string
  simulation_url: string
  rosbridge_url: string
}

// ─── 版本验证相关类型（SDD §6.3 / §15.3）────────────────────────────────────

export interface ExperimentVersionIssue {
  field: string
  code: string
  severity: 'blocking' | 'warning'
  message: string
}

export interface ExperimentVersionValidateResponse {
  valid: boolean
  issues: ExperimentVersionIssue[]
}

// ─── 版本发布状态变更请求（SDD §6.3）─────────────────────────────────────────

export interface ExperimentVersionPublishStatusRequest {
  publish_status: 'draft' | 'published' | 'deprecated'
  publish_note?: string
}

export interface ExperimentVersionPublishStatusResponse {
  version_id: number
  publish_status: 'draft' | 'published' | 'deprecated'
  updated_at: string
}

// ─── 当前仿真任务阶段（SDD §7.4，扩展 CHECKING_GZWEB / CHECKING_ROSBRIDGE）──

export type SimulationTaskStage =
  | 'PREPARING_CONFIG'
  | 'STOPPING_OLD_CONTAINER'
  | 'CREATING_NEW_CONTAINER'
  | 'CHECKING_GZWEB'
  | 'CHECKING_ROSBRIDGE'
  | 'SUCCEEDED'
  | 'FAILED'
