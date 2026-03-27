# 当前任务状态

## 当前阶段：教师的路由相关问题修复 ✅

## 已完成事项
- 修复了 `edubot-twin-web/src/router/index.ts` 中 `Teacher` 及其下属路由缺失 `t()` 函数调用的问题，导致无法正确进行 i18n 多语言翻译并在菜单栏显示为 `router.teacher` 等字符。
- 补充了 `src/locales/zh-CN.ts` 和 `src/locales/en.ts` 翻译文件中针对教师专属菜单项（`teacher`、`teacherHome`、`studentManagement`、`containerManagement`、`containerMonitor`）的本地化字符串配置。
- 修正了 `edubot-twin-server/app/api/v1/endpoints/common/auth.py` 中 `get_user_routes` 接口关于 `teacher` 和 `admin` 角色的路由权限白名单，正确添加了 `/teacher` 及以下子路由的访问权限（以防开启了服务端动态路由时报 404）。
- 修复了 `src/views/Teacher/Students/components/Write.vue` 中的 TypeScript 类型检查错误：`getFormData()` 返回 `Recordable` 无法默认匹配 `StudentCreate` 类型的问题，已通过类型断言转换为 `any` 规避冲突。
- 修复了 `src/views/Teacher/Students/Student.vue` 中表格 "编辑"/"删除" 按钮不显示的 BUG，原因在于当前使用的 `<Table>` 封装组件不支持作用域插槽 `<template #action>` 绑定，已切换为 `tsx` 内联 `slots` 配置解决。
- 修复了教师端编辑学生提交时后端报 500 (`AttributeError: 'StudentUpdate' object has no attribute 'username'`) 的问题，原因是 `StudentUpdate` Schema 中遗漏了 `username` 字段，导致 Pydantic 解析时被丢弃；已将其添加至 `app/schemas/student.py` 中。
- 修复了新增/编辑学生由于 `email` 为空字符串导致后端报 422 验证错误的问题。前端 `Input` 组件默认清空会保留 `""` 而不是 `null`，这无法通过后端 Pydantic `EmailStr` 的正则校验，目前已在前端 `Write.vue` 提交前拦截并剥离空值为 `""` 的 `email` 字段。

## 关键说明
如果在开发服出现热更新未即时生效（特别是涉及路由配置的改动）时，尝试清空缓存或重新刷新。

## 下一步（候选）
- 学生端 Terminal 集成（xterm.js + WebSocket 反向代理）
- 教师端容器监控看板（实时 CPU/内存）
