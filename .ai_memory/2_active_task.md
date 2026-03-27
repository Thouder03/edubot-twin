# 当前任务状态

## 当前阶段：教师的路由相关问题修复 ✅

## 已完成事项
- 修复了 `edubot-twin-web/src/router/index.ts` 中 `Teacher` 及其下属路由缺失 `t()` 函数调用的问题，导致无法正确进行 i18n 多语言翻译并在菜单栏显示为 `router.teacher` 等字符。
- 补充了 `src/locales/zh-CN.ts` 和 `src/locales/en.ts` 翻译文件中针对教师专属菜单项（`teacher`、`teacherHome`、`studentManagement`、`containerManagement`、`containerMonitor`）的本地化字符串配置。
- 修正了 `edubot-twin-server/app/api/v1/endpoints/common/auth.py` 中 `get_user_routes` 接口关于 `teacher` 和 `admin` 角色的路由权限白名单，正确添加了 `/teacher` 及以下子路由的访问权限（以防开启了服务端动态路由时报 404）。

## 关键说明
如果在开发服出现热更新未即时生效（特别是涉及路由配置的改动）时，尝试清空缓存或重新刷新。

## 下一步（候选）
- 学生端 Terminal 集成（xterm.js + WebSocket 反向代理）
- 教师端容器监控看板（实时 CPU/内存）
