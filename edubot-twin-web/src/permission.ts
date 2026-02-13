import router from './router'
import { useAppStoreWithOut } from '@/store/modules/app'
import type { RouteRecordRaw } from 'vue-router'
import { useTitle } from '@/hooks/web/useTitle'
import { useNProgress } from '@/hooks/web/useNProgress'
import { usePermissionStoreWithOut } from '@/store/modules/permission'
import { usePageLoading } from '@/hooks/web/usePageLoading'
import { NO_REDIRECT_WHITE_LIST } from '@/constants'
import { useUserStoreWithOut } from '@/store/modules/user'

const { start, done } = useNProgress()

const { loadStart, loadDone } = usePageLoading()

router.beforeEach(async (to, from, next) => {
  start()
  loadStart()
  const permissionStore = usePermissionStoreWithOut()
  const appStore = useAppStoreWithOut()
  const userStore = useUserStoreWithOut()
  if (userStore.getUserInfo) {
    if (to.path === '/login') {
      if (permissionStore.getAddRouters.length > 0) {
        const firstRoute = permissionStore.getAddRouters[0]
        if (firstRoute.children && firstRoute.children.length > 0) {
          next({ path: firstRoute.path + '/' + firstRoute.children[0].path, replace: true })
        } else {
          next({ path: firstRoute.path, replace: true })
        }
      } else {
        next({ path: '/' })
      }
    } else {
      if (permissionStore.getIsAddRouters) {
        if (to.path === '/') {
          if (permissionStore.getAddRouters.length > 0) {
            const firstRoute = permissionStore.getAddRouters[0]
            if (firstRoute.children && firstRoute.children.length > 0) {
              next({ path: firstRoute.path + '/' + firstRoute.children[0].path, replace: true })
            } else {
              next({ path: firstRoute.path, replace: true })
            }
          } else {
            next()
          }
          return
        }
        next()
        return
      }

      // 开发者可根据实际情况进行修改
      const roleRouters = userStore.getRoleRouters || []

      // 是否使用动态路由
      if (appStore.getDynamicRouter) {
        // 统一使用前端动态路由模式
        await permissionStore.generateRoutes('frontEnd', roleRouters as string[])
      } else {
        await permissionStore.generateRoutes('static')
      }

      permissionStore.getAddRouters.forEach((route) => {
        router.addRoute(route as unknown as RouteRecordRaw) // 动态添加可访问路由表
      })
      const redirectPath = from.query.redirect || to.path
      const redirect = decodeURIComponent(redirectPath as string)
      const nextData = to.path === redirect ? { ...to, replace: true } : { path: redirect }
      permissionStore.setIsAddRouters(true)
      next(nextData)
    }
  } else {
    // 没有用户信息，检查是否有 Token（实现"记住登录状态"）
    const token = userStore.getToken
    if (token && NO_REDIRECT_WHITE_LIST.indexOf(to.path) === -1) {
      // 有 Token，尝试自动登录
      try {
        const { getUserInfoByTokenApi, getUserRoutesApi } = await import('@/api/login')
        const userInfoRes = await getUserInfoByTokenApi(token)

        if (userInfoRes && userInfoRes.data) {
          // Token 有效，恢复用户信息
          userStore.setUserInfo(userInfoRes.data)

          // 获取路由权限
          const routesRes = await getUserRoutesApi({ role: userInfoRes.data.role })
          if (routesRes && routesRes.data) {
            userStore.setRoleRouters(routesRes.data)
            await permissionStore.generateRoutes('frontEnd', routesRes.data as string[])
            permissionStore.getAddRouters.forEach((route) => {
              router.addRoute(route as unknown as RouteRecordRaw)
            })
            permissionStore.setIsAddRouters(true)
            next({ ...to, replace: true })
            return
          }
        }
      } catch (error) {
        // Token 无效或过期，清除并跳转登录
        console.warn('Token 验证失败，需要重新登录', error)
        userStore.setToken('')
        userStore.setUserInfo(undefined)
      }
    }

    // 无 Token 或 Token 验证失败，跳转登录
    if (NO_REDIRECT_WHITE_LIST.indexOf(to.path) !== -1) {
      next()
    } else {
      next(`/login?redirect=${to.path}`) // 否则全部重定向到登录页
    }
  }
})

router.afterEach((to) => {
  useTitle(to?.meta?.title as string)
  done() // 结束Progress
  loadDone()
})
