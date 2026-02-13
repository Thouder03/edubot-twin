import request from '@/axios'
import type { StudentHomeData } from './types'

// 获取学生首页数据
export const getStudentHomeDataApi = (): Promise<IResponse<StudentHomeData>> => {
  return request.get({ url: '/mock/student/home' })
}
