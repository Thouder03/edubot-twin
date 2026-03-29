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

// Tree Node（用于 el-tree 展示）
export interface TreeNode {
  key: string
  label: string
  type: 'file' | 'directory'
  path: string
  extension?: string
  size?: number
  children?: TreeNode[]
  isLeaf?: boolean
}
