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
  startup_script_ref?: string
  file_bundle_id?: number
  is_visible?: boolean
}

export interface ExperimentVersionResponse {
  version_id: number
  experiment_id: number
  version_name: string
  is_visible: boolean
  environment_key: string
  image_name: string
  launch_file_path: string
  launch_args_template: Record<string, string>
  startup_script_ref?: string
  file_bundle_id?: number
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
