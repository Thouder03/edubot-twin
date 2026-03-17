---
description: "添加新路由的操作指南及注意事项"
---

# 添加新路由操作指南

本项目采用**前端动态路由模式**，后端返回路径列表，前端匹配并加载路由。

---

## 添加新路由的 3 个步骤

### 1️⃣ 前端定义路由 (`src/router/index.ts`)

在 `asyncRouterMap` 中添加路由配置：

```typescript
export const asyncRouterMap: AppRouteRecordRaw[] = [
  {
    path: "/student",
    component: Layout,
    name: "Student",
    meta: {
      title: "router.student",
      icon: "carbon:user-avatar",
    },
    children: [
      // ✅ 新增子路由
      {
        path: "simulation", // 完整路径为 /student/simulation
        component: () => import("@/views/Student/Simulation.vue"),
        name: "StudentSimulation",
        meta: {
          title: "router.studentSimulation",
          icon: "carbon:3d-curve-auto-colon",
        },
      },
    ],
  },
];
```

### 2️⃣ 后端添加路径权限 (`app/api/v1/endpoints/common/auth.py`)

在 `get_user_routes` 函数中添加路径：

```python
@router.get("/routes", response_model=ApiResponse[list[str]])
async def get_user_routes(role: str):
    role_routes = {
        "student": [
            "/student",
            "/student/home",
            "/student/simulation"  # ✅ 新增路径
        ],
        "teacher": [...]
    }
    return ApiResponse(code=0, data=role_routes.get(role, []))
```

### 3️⃣ 创建页面组件 (`src/views/`)

```vue
<!-- src/views/Student/Simulation.vue -->
<template>
  <ContentWrap>
    <!-- 你的页面内容 -->
  </ContentWrap>
</template>

<script setup lang="ts">
// 页面逻辑
</script>
```

---

## ⚠️ 关键注意事项

### 1. 前后端路径必须完全匹配

```typescript
// ❌ 错误：路径不一致
// 前端: '/student/sim'
// 后端: ["/student/simulation"]

// ✅ 正确：路径完全一致
// 前端: '/student/simulation'
// 后端: ["/student/simulation"]
```

### 2. 父路由和子路由都要添加

```python
# ❌ 错误：只添加子路由
"student": ["/student/simulation"]  # 缺少父路由 /student

# ✅ 正确：父子路由都要有
"student": [
    "/student",          # 父路由
    "/student/simulation"  # 子路由
]
```

### 3. 根路径不要硬编码 redirect

```typescript
// ❌ 错误：硬编码会导致学生访问教师路由 404
{
  path: '/',
  redirect: '/dashboard/analysis'
}

// ✅ 正确：保持为空，在 permission.ts 中动态跳转
{
  path: '/',
  redirect: ''
}
```

### 4. meta 配置说明

```typescript
meta: {
  title: 'router.key',     // i18n 翻译 key（必填）
  icon: 'carbon:home',     // Iconify 图标（可选）
  hidden: true,            // 隐藏菜单但路由可访问
  affix: true,             // 固定在标签页，无法关闭
  noCache: true,           // 不缓存页面
  activeMenu: '/parent'    // 访问时高亮指定菜单
}
```

---

## 常见错误排查

### ❌ 登录后看不到新菜单

**检查清单**：

1. 后端 `/api/v1/auth/routes` 是否返回了新路径？
   ```bash
   curl "http://localhost:8000/api/v1/auth/routes?role=student"
   ```
2. 前端路径是否与后端完全一致？
3. `meta.hidden` 是否设置为 `true`？

### ❌ 访问新路由显示 404

**检查清单**：

1. 前端是否在 `asyncRouterMap` 中定义了该路由？
2. 后端是否返回了**父路由和子路由**？
3. 页面组件路径是否正确？

### ❌ 切换角色后路由混乱

**原因**：登出时未清空路由状态

**解决**：确保 `user.ts` 的 `reset()` 方法调用了：

```typescript
permissionStore.setIsAddRouters(false);
```

---

## 快速示例：添加"课程管理"页面

```typescript
// 1. router/index.ts
{
  path: '/student',
  children: [
    {
      path: 'courses',
      component: () => import('@/views/Student/Courses.vue'),
      name: 'StudentCourses',
      meta: { title: 'router.courses', icon: 'carbon:course' }
    }
  ]
}

// 2. auth.py
"student": ["/student", "/student/courses"]

// 3. 创建 src/views/Student/Courses.vue
```

---

## 调试技巧

```typescript
// 在浏览器控制台查看已注册路由
console.log(router.getRoutes().map((r) => r.path));

// 查看用户权限路由
console.log(userStore.getRoleRouters);
console.log(permissionStore.getAddRouters);
```
