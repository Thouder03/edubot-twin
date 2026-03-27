import request from '@/axios'
import type { StudentItem, StudentCreate, StudentUpdate } from './types'

export const getStudentListApi = (params?: any) => {
  return request.get({ url: '/teacher/students', params })
}

export const getStudentApi = (id: number) => {
  return request.get({ url: `/teacher/students/${id}` })
}

export const createStudentApi = (data: StudentCreate) => {
  return request.post({ url: '/teacher/students', data })
}

export const updateStudentApi = (id: number, data: StudentUpdate) => {
  return request.put({ url: `/teacher/students/${id}`, data })
}

export const deleteStudentApi = (id: number) => {
  return request.delete({ url: `/teacher/students/${id}` })
}
