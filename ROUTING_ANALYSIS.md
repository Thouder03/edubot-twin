# 前端动态路由机制分析 (Frontend Dynamic Routing Analysis)

## 1. 核心流程概览 (Core Flow)

前端采用 **服务端控制路由 (Backend-Driven Routing)** 的模式，即登录后由后端返回该用户可访问的完整路由表。

### 关键步骤：

1.  **用户登录**: 调用 `/api/v1/auth/login` 获取 token 和用户信息。
2.  **获取路由**: 登录成功后，立即调用 `getRole()`（在 `LoginForm.vue` 中）。
3.  **API 请求**: `getRole` 调用 `getAdminRoleApi` (`/mock/role/list`) 获取路由配置。
4.  **路由生成**:
    - 将获取到的路由数据存储到 `userStore.roleRouters`。
    - 调用 `permissionStore.generateRoutes('server', routers)`。
    - 使用 `router.addRoute` 动态添加到 Vue Router。
5.  **跳转**: 路由添加完成后，跳转到首页或重定向页面。

---

## 2. 关键文件分析 (Key Files Analysis)

### 2.1 登录组件 (`src/views/Login/components/LoginForm.vue`)

- **触发点**: `signIn` 方法。
- **逻辑**:
  ```typescript
  // 1. 登录
  const res = await loginApi(formData);
  userStore.setUserInfo(res.data);

  // 2. 获取动态路由 (默认开启 dynamicRouter)
  if (appStore.getDynamicRouter) {
    getRole(); // 内部调用 getAdminRoleApi -> permissionStore.generateRoutes
  }
  ```

### 2.2 权限 Store (`src/store/modules/permission.ts`)

- **核心动作**: `generateRoutes('server', routers)`
- **逻辑**: 调用 `utils/routerHelper.ts` 中的 `generateRoutesByServer` 将后端返回的 JSON 数据转换为 Vue 路由对象（解析 `component` 字符串为实际组件引用）。

### 2.3 路由守卫 (`src/permission.ts`)

- **作用**: 防止刷新页面后路由丢失。
- **逻辑**:
  - 检查 `userStore.getUserInfo` 是否存在。
  - 检查 `permissionStore.getIsAddRouters` 是否为 true。
  - 如果为 false (即刷新后)，会重新触发 `permissionStore.generateRoutes`（使用缓存的 `userStore.roleRouters`）并再次 `router.addRoute`。

### 2.4 路由辅助工具 (`src/utils/routerHelper.ts`)

- **`generateRoutesByServer`**:
  - 遍历后端返回的路由树。
  - 将 `component` 字段从字符串转换为实际组件：
    - `"Layout"` -> `Layout` 组件
    - `"dir/file"` -> `() => import('@/views/dir/file.vue')`

---

## 3. 后端数据结构要求 (Backend Response Structure)

由于使用了 `generateRoutesByServer`，后端 (`/mock/role/list` 或未来的真实接口) 必须返回符合 Vue Router 配置的 JSON 树形结构：

```json
[
  {
    "path": "/dashboard",
    "component": "Layout", // 对应 Layout 组件
    "redirect": "/dashboard/analysis",
    "name": "Dashboard",
    "meta": {
      "title": "router.dashboard",
      "icon": "vi-ant-design:dashboard-filled"
    },
    "children": [
      {
        "path": "analysis",
        "component": "Dashboard/Analysis", // 对应 src/views/Dashboard/Analysis.vue
        "name": "Analysis",
        "meta": {
          "title": "router.analysis"
        }
      }
    ]
  }
]
```

## 4. 结论 (Conclusion)

- **当前状态**: 登录逻辑中，获取用户信息是真实的 API (`/api/v1/auth/login`)，但获取路由表仍然是 Mock API (`/mock/role/list`)。
- **下一步建议**:
  1.  后端需要实现一个接口 (如 `/api/v1/auth/routes`)，返回上述 JSON 格式的路由表。
  2.  或者，修改前端逻辑为 **前端控制路由 (Frontend-Driven)**，即后端只返回角色列表 (`['admin']`)，前端根据角色筛选 `asyncRouterMap` (在 `src/router/index.ts` 中定义)。这通常更易维护，除非需要极高的动态配置能力（如在线配置菜单）。
