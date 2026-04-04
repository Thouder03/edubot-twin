// 文件管理 API 封装
// 基于项目约定的 service（非 axios 直调）

import axios from 'axios'
import service from '@/axios'
import { useUserStoreWithOut } from '@/store/modules/user'
import type {
  FileListData,
  FileReadData,
  FileUploadData,
  FileSaveRequest,
  MkdirRequest,
  FileRenameRequest,
  FileMoveRequest,
  FileCopyRequest,
  BatchDeleteRequest,
  ExtractRequest,
  ExtractData,
  CompressRequest,
  CompressData
} from './types'

const BASE = '/api/v1/students/files'

/** 获取文件/目录列表 */
export const listFiles = (path = '.'): Promise<IResponse<FileListData>> => {
  return service.get({ url: `${BASE}/list`, params: { path } })
}

/** 读取文件内容 */
export const readFile = (path: string): Promise<IResponse<FileReadData>> => {
  return service.get({ url: `${BASE}/read`, params: { path } })
}

/** 保存文件内容 */
export const saveFile = (
  data: FileSaveRequest
): Promise<IResponse<{ path: string; size: number }>> => {
  return service.post({ url: `${BASE}/save`, data })
}

/**
 * 上传文件
 *
 * 注意：不使用 service 封装，直接用 axios 原生发送 FormData。
 * 原因：service 封装会硬设 Content-Type: application/json，
 *      而 multipart/form-data 的 boundary 必须由 axios 自动生成，
 *      手动覆盖 Content-Type 会导致后端 422 Field required 错误。
 */
export const uploadFile = (file: File, targetPath = '.'): Promise<IResponse<FileUploadData>> => {
  const userStore = useUserStoreWithOut()
  const formData = new FormData()
  formData.append('file', file)
  formData.append('target_path', targetPath)

  return axios
    .post(`${BASE}/upload`, formData, {
      baseURL: import.meta.env.VITE_API_BASE_PATH,
      headers: {
        [userStore.getTokenKey ?? 'Authorization']: userStore.getToken
          ? `Bearer ${userStore.getToken}`
          : ''
        // 不设置 Content-Type，让 axios 自动补 multipart/form-data; boundary=...
      }
    })
    .then((res) => res.data)
}

/** 删除文件或目录 */
export const deleteFile = (path: string): Promise<IResponse<{ path: string }>> => {
  return service.delete({ url: `${BASE}/delete`, params: { path } })
}

/** 创建目录 */
export const mkdir = (data: MkdirRequest): Promise<IResponse<{ path: string }>> => {
  return service.post({ url: `${BASE}/mkdir`, data })
}

/** 重命名文件或目录 */
export const renameFile = (data: FileRenameRequest): Promise<IResponse<{ new_path: string }>> => {
  return service.post({ url: `${BASE}/rename`, data })
}

/** 移动文件或目录 */
export const moveFiles = (
  data: FileMoveRequest
): Promise<IResponse<{ success: string[]; failed: any[] }>> => {
  return service.post({ url: `${BASE}/move`, data })
}

/** 复制文件或目录 */
export const copyFiles = (
  data: FileCopyRequest
): Promise<IResponse<{ success: string[]; failed: any[] }>> => {
  return service.post({ url: `${BASE}/copy`, data })
}

/** 批量删除文件或目录 */
export const batchDeleteFiles = (
  data: BatchDeleteRequest
): Promise<IResponse<{ deleted: string[]; failed: any[] }>> => {
  return service.delete({ url: `${BASE}/batch-delete`, data })
}

/** 解压缩文件 */
export const extractFile = (data: ExtractRequest): Promise<IResponse<ExtractData>> => {
  return service.post({ url: `${BASE}/extract`, data })
}

/** 压缩文件/目录 */
export const compressFiles = (data: CompressRequest): Promise<IResponse<CompressData>> => {
  return service.post({ url: `${BASE}/compress`, data })
}

/**
 * 下载文件或目录（目录自动打包为 zip）
 * 使用原生 fetch 实现流式下载，触发浏览器下载行为
 */
export const downloadFile = async (
  path: string,
  token: string,
  tokenKey = 'Authorization'
): Promise<void> => {
  const params = new URLSearchParams({ path })
  const url = `${import.meta.env.VITE_API_BASE_PATH}${BASE}/download?${params}`
  const res = await fetch(url, {
    headers: { [tokenKey]: token ? `Bearer ${token}` : '' }
  })
  if (!res.ok) {
    const json = await res.json().catch(() => ({}))
    throw new Error(json?.detail ?? `下载失败 (${res.status})`)
  }
  const blob = await res.blob()
  // 从 Content-Disposition 取文件名
  const cd = res.headers.get('Content-Disposition') ?? ''
  const match = cd.match(/filename="?([^"\s]+)"?/)
  const filename = match?.[1] ?? path.split('/').pop() ?? 'download'
  triggerBlobDownload(blob, filename)
}

/**
 * 批量下载多个文件/目录（服务端打成 zip 后流式返回）
 */
export const downloadMultipleFiles = async (
  paths: string[],
  archiveName: string,
  token: string,
  tokenKey = 'Authorization'
): Promise<void> => {
  const url = `${import.meta.env.VITE_API_BASE_PATH}${BASE}/download-multiple`
  const res = await fetch(url, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      [tokenKey]: token ? `Bearer ${token}` : ''
    },
    body: JSON.stringify({ paths, archive_name: archiveName })
  })
  if (!res.ok) {
    const json = await res.json().catch(() => ({}))
    throw new Error(json?.detail ?? `下载失败 (${res.status})`)
  }
  const blob = await res.blob()
  const cd = res.headers.get('Content-Disposition') ?? ''
  const match = cd.match(/filename="?([^"\s]+)"?/)
  const filename = match?.[1] ?? archiveName
  triggerBlobDownload(blob, filename)
}

/** 触发浏览器下载 Blob */
function triggerBlobDownload(blob: Blob, filename: string) {
  const link = document.createElement('a')
  link.href = URL.createObjectURL(blob)
  link.download = filename
  link.click()
  URL.revokeObjectURL(link.href)
}
