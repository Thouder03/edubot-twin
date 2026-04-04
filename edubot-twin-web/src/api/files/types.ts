// 文件管理 API — TypeScript 类型定义

export interface FileItem {
  name: string
  path: string // 相对于 workspace 的路径
  size: number // 字节
  modified: number // Unix ms 时间戳
  extension: string // 如 ".py"、".launch"
}

export interface DirectoryItem {
  name: string
  path: string // 相对于 workspace 的路径
  file_count: number
}

export interface FileListData {
  path: string
  files: FileItem[]
  directories: DirectoryItem[]
}

export interface FileReadData {
  content: string
  encoding: string
  name: string
  path: string
  size: number
}

export interface FileUploadData {
  filename: string
  path: string
  size: number
}

export interface FileSaveRequest {
  path: string
  content: string
  encoding?: string
}

export interface MkdirRequest {
  path: string
}

export interface FileRenameRequest {
  path: string
  new_name: string
}

export interface FileMoveRequest {
  source_paths: string[]
  target_dir: string
}

export interface FileCopyRequest {
  source_paths: string[]
  target_dir: string
}

export interface BatchDeleteRequest {
  paths: string[]
}

export interface ExtractRequest {
  path: string
  target_dir?: string
}

export interface ExtractData {
  source: string
  target_dir: string
}

export interface CompressRequest {
  paths: string[]
  archive_name: string
  format: 'zip' | 'tar.gz'
  target_dir?: string
}

export interface CompressData {
  archive_path: string
}

// Tree Node（用于前端展示与组件交互）
export interface TreeNode {
  key: string
  label: string
  name: string // 文件/目录名
  type: 'file' | 'directory'
  path: string
  parentPath: string // 父目录路径
  extension?: string
  size?: number
  mtime?: number // 修改时间

  // 树的状态
  children?: TreeNode[]
  isLeaf?: boolean

  // 领域状态扩展 (UI State)
  isSelected?: boolean
  isExpanded?: boolean
  isLoading?: boolean
  isRenaming?: boolean
  isCreatingTemp?: boolean
  childrenLoaded?: boolean

  // 拖拽控制扩展 (he-tree 引擎)
  canDrag?: boolean
  canDrop?: boolean
}
