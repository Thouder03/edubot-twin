import request from '@/axios'
import type { StudentCreate, StudentUpdate } from './types'

export const getStudentListApi = (params?: any) => {
  return request.get({ url: '/api/v1/teachers/students', params })
}

export const getStudentApi = (id: number) => {
  return request.get({ url: `/api/v1/teachers/students/${id}` })
}

export const createStudentApi = (data: StudentCreate) => {
  return request.post({ url: '/api/v1/teachers/students', data })
}

export const updateStudentApi = (id: number, data: StudentUpdate) => {
  return request.put({ url: `/api/v1/teachers/students/${id}`, data })
}

export const deleteStudentApi = (id: number) => {
  return request.delete({ url: `/api/v1/teachers/students/${id}` })
}
