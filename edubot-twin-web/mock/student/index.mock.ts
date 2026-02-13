import { SUCCESS_CODE } from '@/constants'

const timeout = 1000

export default [
  // 获取学生首页数据
  {
    url: '/mock/student/home',
    method: 'get',
    timeout,
    response: () => {
      return {
        code: SUCCESS_CODE,
        data: {
          pendingExams: 3, // 模拟待完成考试数量
          unreadMessages: 5 // 模拟未读消息数量
        }
      }
    }
  }
]
