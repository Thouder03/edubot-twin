# CEO 审查报告：容器安全加固与终端优化

**审查日期**：2026-03-31  
**审查模式**：HOLD SCOPE（范围锁定，做对为优先）  
**文档版本**：v1.0  
**原始计划**：[SDD-第8期：容器安全加固与终端优化](./SDD-第8期：容器安全加固与终端优化.md)

---

## 执行摘要

本次 CEO 级别审查对《SDD-第8期：容器安全加固与终端优化》进行了全面评估。审查模式为 HOLD SCOPE，重点在于确保安全方案**做对**，而非做大。

发现并修正了 SDD 中的 **2 处设计错误**，识别了 **1 个关键实现缺口**，并对 3 项技术决策进行了风险权衡后确认。

**关键成果**：
- ✅ 修正 SDD 错误：去掉危险的 `/opt/ros` / `/usr` 宿主机挂载
- ✅ 新增关键修复：workspace `chown 1000:1000`（SDD 遗漏）
- ✅ 风险降级决策：`cap_drop ALL` 后置，优先保证 Gazebo 可用性
- ✅ 精简网络隔离：做 Docker 自定义网络，不做 iptables
- ✅ 指定 ensure_network 调用位置（SDD 未说明）

---

## 一、战略定位

### 1.1 问题定义

当前学生容器以**镜像默认用户**（大概率为 root）运行，无任何 Capability 限制，无网络隔离。学生可在容器内进行以 root 权限执行任意命令，风险覆盖：

- 写入 `/usr/bin/` 等系统目录（理论上可改镜像环境）
- 容器内 fork 炸弹耗尽宿主机资源
- 同学容器互访（无网络隔离）

本期目标：**在不破坏 Gazebo/ROS 功能的前提下，建立最基础的安全隔离底线**。

### 1.2 核心约束

```
功能可用 > 安全加固强度
```

这是毕设演示环境，不是生产级多租户平台。安全配置一旦导致 Gazebo 无法渲染，答辩就失败了。所有决策均在此约束下做出。

### 1.3 12 个月理想状态

```
现状                     本期                    12 个月目标
─────────────────   →   ───────────────────  →  ────────────────────
root 用户裸跑             uid 1000 + 网络隔离      cap_drop + read_only
无网络隔离               edubot_network           iptables 精细过滤
容器间可互访             同网络 ICC 关闭           完全隔离容器网络
无工作区权限检查          chown 1000:1000          SELinux/AppArmor profile
```

---

## 二、SDD 问题修正

### 2.1 [严重错误] Volume 只读挂载设计错误

**SDD 原文**（容器创建参数 §3.1）：
```
卷挂载: {
    '/opt/ros': { 绑定: '/opt/ros', 模式: 'ro' },
    '/usr':     { 绑定: '/usr',     模式: 'ro' }
}
```

**问题所在**：Docker Volume 挂载是将**宿主机目录**覆盖容器内对应目录，不是限制容器自身目录的读写权限。

- 宿主机 `/usr` 覆盖容器内 `/usr` = OS 版本不同、二进制不兼容 = 容器立即崩溃
- 宿主机未必有 `/opt/ros`，该目录是容器镜像自带的
- 这两行挂载会把 gzweb 镜像的运行环境直接破坏

**修正决策**：**删除这两行挂载配置。**

正确的系统目录只读保护方案是 `read_only=True`（整个 rootfs 只读），但该方案本期不做（需要额外调试 ROS 临时目录可写挂载）。本期依赖 `user=1000:1000` 实现非 root 访问控制。

### 2.2 [实现缺口] workspace 所有权未设置

**SDD 遗漏**：SDD 在第七期引入了 Volume 挂载 `/home/student/workspace`，但没有说明目录所有者。实际情况：`create_student_workspace()` 由 uvicorn 进程（通常以 root 运行）创建目录，目录 owner 是 root。

加入 `user="1000:1000"` 后，容器内 uid 1000 对该目录没有写权限，学生打开终端后无法保存任何文件。

**修正决策**：在 `create_student_workspace()` 中，目录创建完成后递归 `chown(1000, 1000)`。

### 2.3 [实现遗漏] ensure_network 调用位置未指定

SDD 定义了 `create_edubot_network()` 的逻辑，但没有说明在哪里调用。

**修正决策**：在 `app/main.py` 的 `lifespan()` 上下文管理器中，`yield` 之前调用 `await ensure_edubot_network()`。注意：`main.py` 已使用 `lifespan` 模式，不能再用废弃的 `@app.on_event("startup")`。

---

## 三、技术决策

### 3.1 决策：不做 cap_drop ALL

**背景**：SDD 提议 `cap_drop=['ALL']` + 添加 4 个必要 Capability。

**风险**：gzweb 镜像原始配置是 `privileged: true`，Gazebo GPU 渲染（`/dev/dri`）可能需要 `SYS_NICE` 等额外 Capability。如果 Gazebo 启动失败，答辩演示失败。

**决策**：本期不做 `cap_drop`，只做 `user=1000:1000` + `no-new-privileges`。

**理由**：`cap_drop` 调试成本高（需要逐个 cap 测试），而 `user + no-new-privileges` 已覆盖绝大多数安全隔离需求。cap_drop 作为安全增强迭代后置。

**后置条件**：毕设答辩后，若 Gazebo 在非特权模式下稳定运行超过 30 分钟，再逐步引入 `cap_drop`。

### 3.2 决策：做 Docker 自定义网络，不做 iptables

**背景**：SDD 提议 `edubot_network` 自定义网络 + 宿主机 iptables 规则。

**风险评估**：
- iptables 规则需要 root 权限管理，配错可能阻断 ROS/Gazebo 网络通信
- 防火墙规则随系统重启可能失效，需要持久化管理
- 规则调试难度高，排查成本大

**决策**：只做 `edubot_network`，设置 `enable_icc=false`（容器间隔离），不做 iptables。

**效果**：同一批学生容器无法互 ping，符合毕设安全要求。容器仍可访问公网，可接受。

### 3.3 决策：devices 保留 /dev/dri

对齐原始 `gzweb/docker-compose.yml`，保留 `devices=["/dev/dri:/dev/dri:rwm"]`，保证 GPU 渲染能力。SDD 在参数对齐章节有明确要求，本期执行。

---

## 四、最终实施范围

### 4.1 本期实施内容

| 改动 | 文件 | 优先级 | 说明 |
|------|------|--------|------|
| 新增 `EDUBOT_NETWORK` 常量 + `ensure_edubot_network()` | `container_manager.py` | P0 | 幂等建网 |
| `create_student_workspace()` 加 `chown 1000:1000` | `container_manager.py` | P0 | 关键缺口修复 |
| `create_container()` 加安全参数 | `container_manager.py` | P0 | 核心安全配置 |
| `lifespan()` 中调用 `ensure_edubot_network` | `main.py` | P0 | 启动时建网 |
| `docker exec` 加 `-u student -w /home/student/workspace` | `terminal.py` | P0 | 终端优化 |

**新增安全参数汇总**（`create_container()` 新增）：
```python
user="1000:1000",
privileged=False,
security_opt=["no-new-privileges:true"],
network=EDUBOT_NETWORK,
shm_size="512m",
devices=["/dev/dri:/dev/dri:rwm"],
```

### 4.2 不在本期范围

| 功能 | 原因 | 后置建议 |
|------|------|---------|
| `cap_drop ALL` | Gazebo GPU 渲染兼容性风险 | 答辩后验证，第 10 期迭代 |
| `read_only=True` 根文件系统 | 需调试 ROS 临时目录可写挂载 | 与 cap_drop 同批次 |
| iptables 网络过滤规则 | 运营复杂度过高，配错风险大 | 生产部署阶段考虑 |
| 极端命令兜底拦截 | 容器层已足够，终端透传是核心体验 | 不推荐引入 |

---

## 五、关键风险

### 5.1 patch_cmd 与 uid 1000 兼容性（中风险）

容器启动脚本中有如下"临时方案"：
```bash
sed -i '/rosbridge_websocket.launch/,...' /home/ubuntu20/catkin_ws/.../launch_file
```

加入 `user="1000:1000"` 后，该命令以 uid 1000 运行。若 launch 文件的 owner 是 root 或其他 uid，`sed -i` 会报 `Permission denied`，容器启动失败。

**验证方法**：创建容器后立即检查 `container.logs()`，若出现 `Permission denied` 则命中此风险。

**临时修复**：在 patch_cmd 前加 `chmod 666 {launch_file} || true`，或在镜像构建时预先设置文件所有权。

### 5.2 Gazebo 以 uid 1000 能否正常启动（低-中风险）

Gazebo 启动时可能尝试写入 `/root`、`/.gazebo` 等目录。非 root 运行时行为未经验证。

**验证方法**：创建容器后在浏览器打开 GzWeb 面板，确认场景可正常渲染，连续运行 30 分钟无崩溃。

### 5.3 chown 需要宿主机 root 权限（已知，可接受）

`os.chown(path, 1000, 1000)` 需要 uvicorn 进程具有 root 权限或 `CAP_CHOWN`。开发环境以 root 运行 uvicorn 是常见做法，生产环境需要通过 `sudo` 或专用服务账号处理。

当前 `PermissionError` 时会打印 WARNING 日志并继续——这是**静默失败**，容器仍会创建但工作区不可写。建议后续迭代改为抛出异常拒绝创建。

---

## 六、测试验证清单

| 测试项 | 操作 | 预期结果 |
|--------|------|---------|
| 容器用户确认 | `docker exec <id> whoami` | `student` 或 `1000` |
| 工作区可写 | `echo test > ~/workspace/t.txt` | 成功 |
| 系统目录不可写 | `echo x > /usr/bin/test_sec` | `Permission denied` |
| 特权禁止 | `sudo su 2>&1` | `command not found` |
| 容器间隔离 | 从容器 A `ping` 容器 B | 不通 |
| 终端落点 | 打开前端终端 | 提示符：`student@edubot:~/workspace$` |
| Gazebo 可用 | 浏览器打开 GzWeb 面板 | 场景正常渲染 |
| ROS 正常 | `roslaunch` 命令 | 正常执行，无权限报错 |
| 网络建立幂等 | 重启后端服务两次 | 无报错，`edubot_network` 存在一个 |
| 工作区 chown | `ls -la /home/student/workspace` | owner 显示 `1000:1000` |

---

## 七、工作量估算

| 子任务 | 人工团队 | AI 辅助 |
|--------|----------|---------|
| `ensure_edubot_network()` + 常量 | 30 分钟 | 5 分钟 |
| `create_student_workspace()` chown | 15 分钟 | 3 分钟 |
| `create_container()` 安全参数 | 30 分钟 | 5 分钟 |
| `main.py` lifespan 集成 | 15 分钟 | 3 分钟 |
| `terminal.py` exec 参数优化 | 15 分钟 | 3 分钟 |
| 验证测试（手动） | 2 小时 | 30 分钟 |
| **总计** | **~4 小时** | **~50 分钟** |

**压缩比**：~5x（变更集中在 3 个文件，逻辑清晰）

---

## 八、后续规划

### 第 9 期或答辩后迭代

1. **cap_drop ALL 加固**：在确认 Gazebo 稳定后，逐步添加 `cap_drop=['ALL']` + 必要 cap_add，进一步缩小攻击面。
2. **chown 失败改为拒绝创建**：当前静默失败改为明确错误，避免假成功场景。
3. **read_only rootfs**：结合 cap_drop 一起调试，需要补全 `/tmp`、`/run`、`/var/run` 等可写挂载。

### 生产部署阶段

4. **iptables 精细过滤**：在正式部署时按白名单规则限制容器出站流量。
5. **AppArmor/SELinux profile**：为 edubot 容器定制安全配置文件。

---

## 九、审查总结

### 9.1 关键成果

✅ **SDD 错误修正**：删除危险的 `/opt/ros` / `/usr` 宿主机挂载，避免容器 OS 环境损坏  
✅ **关键缺口补全**：补充 workspace `chown 1000:1000`，SDD 遗漏的必要步骤  
✅ **风险权衡决策**：cap_drop 后置，保证 Gazebo 答辩演示稳定性优先  
✅ **实现路径精确**：指定 ensure_network 在 `lifespan()` 中调用，避免与废弃 API 冲突  
✅ **范围收敛合理**：iptables 不做，Docker 网络隔离足够覆盖本期需求

### 9.2 评分

| 维度 | SDD 原文 | 审查后 |
|------|---------|--------|
| 安全设计正确性 | 5/10（有设计错误） | 8/10 |
| 实现完整性 | 6/10（有关键缺口） | 9/10 |
| 风险控制 | 6/10（cap_drop 风险未评估） | 9/10 |
| 可交付性（毕设） | 6/10 | 9/10 |

**总评**：原 SDD 方向正确但有两处设计失误，审查后方案可直接落地实施。

---

## 附录

### A. 相关文档

- [SDD-第8期：容器安全加固与终端优化](./SDD-第8期：容器安全加固与终端优化.md) - 原始设计文档
- [SDD-第7期：文件管理与代码编辑模块](../SDD-第7期：文件管理与代码编辑模块.md) - 工作区 Volume 挂载来源
- [gzweb docker-compose.yml](../../../../gzweb/docker-compose.yml) - 容器参数对齐参考

### B. 审查方法论

本次审查采用 **CEO 审查框架（HOLD SCOPE 模式）**：

1. **前提挑战**：确认本期目标是"安全基线可用"而非"完整安全加固"
2. **设计错误扫描**：逐行对比 SDD 伪代码与实际 Docker SDK 行为
3. **实现缺口识别**：追踪第七期代码与第八期配置之间的兼容性问题
4. **风险权衡**：在"安全强度"与"Gazebo 可用性"之间做显式权衡
5. **范围锁定**：明确哪些功能后置，避免范围膨胀影响答辩准备

---

**文档状态**：已完成  
**下一步行动**：按批准计划实施，完成后执行测试验证清单  
**预计实施时间**：约 50 分钟（AI 辅助）
