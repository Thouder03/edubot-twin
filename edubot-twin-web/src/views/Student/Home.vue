<script setup lang="ts">
import { useDesign } from '@/hooks/web/useDesign'
import { ElCard, ElRow, ElCol, ElSkeleton, ElLoading, ElMessage, ElMessageBox } from 'element-plus'
import { BaseButton } from '@/components/Button'
import { ref, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import { getStudentHomeDataApi } from '@/api/student'
import {
  getMyContainerApi,
  requestContainerApi,
  startMyContainerApi,
  destroyAndRecreateApi
} from '@/api/container'
import type { ContainerStatusResponse } from '@/api/container/types'

const { getPrefixCls } = useDesign()
const prefixCls = getPrefixCls('student-home')
const router = useRouter()

// 加载状态
const loading = ref(true)

// 待完成考试数据
const pendingExams = ref(0)

// 未读消息数据
const unreadMessages = ref(0)

// 获取学生首页数据
const getHomeData = async () => {
  try {
    const res = await getStudentHomeDataApi()
    if (res && res.data) {
      pendingExams.value = res.data.pendingExams
      unreadMessages.value = res.data.unreadMessages
    }
  } catch (error) {
    console.error('获取学生首页数据失败:', error)
  } finally {
    loading.value = false
  }
}

// TODO: 点击待完成考试卡片
const handleExamCardClick = () => {
  console.log('TODO: 跳转到待完成考试列表页面')
}

// TODO: 点击未读消息卡片
const handleMessageCardClick = () => {
  console.log('TODO: 跳转到未读消息列表页面')
}

// ---------- 仿真启动核心逻辑 ----------

/** 打开仿真工作台（新标签页） */
function openSimulationPage() {
  const url = router.resolve({ name: 'Simulation' }).href
  const newWin = window.open(url, '_blank')
  if (!newWin) {
    ElMessage.warning('新标签页被浏览器拦截，将在当前标签页跳转')
    router.push({ name: 'Simulation' })
  }
}

/**
 * 测试 WebSocket 连接是否真正可用
 */
function testWebSocketConnection(url: string, timeoutMs = 3000): Promise<boolean> {
  return new Promise((resolve) => {
    try {
      const ws = new WebSocket(url)
      let resolved = false
      const timer = setTimeout(() => {
        if (!resolved) {
          resolved = true
          ws.close()
          resolve(false)
        }
      }, timeoutMs)

      ws.onopen = () => {
        if (!resolved) {
          resolved = true
          clearTimeout(timer)
          ws.close()
          resolve(true)
        }
      }

      ws.onerror = () => {
        if (!resolved) {
          resolved = true
          clearTimeout(timer)
          ws.close()
          resolve(false)
        }
      }
    } catch {
      resolve(false)
    }
  })
}

/**
 * 轮询等待容器进入 running 状态并彻底就绪
 * @returns 容器信息（成功）或 null（超时/错误）
 */
async function waitForContainerRunning(
  maxWaitMs = 60_000,
  intervalMs = 2_000
): Promise<ContainerStatusResponse | null> {
  const deadline = Date.now() + maxWaitMs
  while (Date.now() < deadline) {
    try {
      const res = await getMyContainerApi()
      const data = res?.data
      if (data?.status === 'running') {
        // 后端说 running 了，还需要探测一下容器里的 ROSBridge WebSockets 服务是否真的起来了
        if (data.rosbridge_url && data.gzbridge_url) {
          const isReady =
            (await testWebSocketConnection(data.rosbridge_url)) &&
            (await testWebSocketConnection(data.gzbridge_url))
          if (isReady) {
            return data
          }
          // 不 ready 则继续等
        } else {
          // 如果没有 rosbridge_url 和 gzbridge_url 字段，那就强制等 2 秒当做缓冲然后返回
          await new Promise((r) => setTimeout(r, 2000))
          return data
        }
      }
      if (data?.status === 'error') return null
    } catch {
      // 可能 404，继续轮询
    }
    await new Promise((r) => setTimeout(r, intervalMs))
  }
  return null // 超时
}

/** 销毁旧容器、创建新容器并等待就绪 */
async function recreateAndWait(loadingInstance: ReturnType<typeof ElLoading.service>) {
  loadingInstance.setText('正在重建仿真环境...')
  try {
    await destroyAndRecreateApi()
  } catch (e: any) {
    const detail = e?.response?.data?.detail ?? '请求失败'
    if (detail.includes('503') || e?.response?.status === 503) {
      ElMessage.error('服务器资源已满，请稍后再试')
    } else {
      ElMessage.error(`启动失败：${detail}`)
    }
    return
  }

  loadingInstance.setText('等待仿真环境就绪（最多 60 秒）...')
  const container = await waitForContainerRunning()
  if (container) {
    openSimulationPage()
  } else {
    ElMessage.error('仿真环境启动超时或发生错误，请联系教师')
  }
}

/** 点击「开始仿真」按钮 */
const handleStartSimulation = async () => {
  const loadingInstance = ElLoading.service({
    text: '正在检查仿真环境...',
    background: 'rgba(0,0,0,0.5)'
  })

  try {
    let containerInfo: ContainerStatusResponse | null = null

    try {
      const res = await getMyContainerApi()
      containerInfo = res?.data ?? null
    } catch (e: any) {
      ElMessage.error('网络错误，请检查连接')
      return
    }

    // ── 情况 1：无容器（返回 null）──
    if (!containerInfo) {
      loadingInstance.setText('首次启动，正在创建仿真环境...')
      try {
        await requestContainerApi()
      } catch (e: any) {
        const status = e?.response?.status
        if (status === 503) {
          ElMessage.error('服务器资源已满，请稍后再试')
        } else {
          ElMessage.error('创建仿真环境失败，请联系教师')
        }
        return
      }

      loadingInstance.setText('等待仿真环境就绪（最多 60 秒）...')
      const ready = await waitForContainerRunning()
      if (ready) {
        openSimulationPage()
      } else {
        ElMessage.error('仿真环境启动超时，请联系教师')
      }
      return
    }

    const { status } = containerInfo

    // ── 情况 2：running ──
    if (status === 'running') {
      loadingInstance.close()
      try {
        await ElMessageBox.confirm('发现正在运行的仿真环境，是否继续使用？', '仿真环境', {
          confirmButtonText: '继续使用',
          cancelButtonText: '重新创建',
          type: 'info',
          distinguishCancelAndClose: true
        })
        // 点「继续使用」
        openSimulationPage()
      } catch (action) {
        if (action === 'cancel') {
          // 点「重新创建」
          const loadingInstance2 = ElLoading.service({
            text: '正在重建...',
            background: 'rgba(0,0,0,0.5)'
          })
          try {
            await recreateAndWait(loadingInstance2)
          } finally {
            loadingInstance2.close()
          }
        }
        // 点 X 关闭弹窗 → 不做任何操作
      }
      return
    }

    // ── 情况 3：stopped ──
    if (status === 'stopped') {
      loadingInstance.close()
      try {
        await ElMessageBox.confirm('发现上次的仿真环境（已暂停），是否恢复使用？', '仿真环境', {
          confirmButtonText: '恢复使用',
          cancelButtonText: '重新创建',
          type: 'warning',
          distinguishCancelAndClose: true
        })
        // 点「恢复使用」
        const loadingInstance2 = ElLoading.service({
          text: '正在启动仿真环境...',
          background: 'rgba(0,0,0,0.5)'
        })
        try {
          await startMyContainerApi()
          const ready = await waitForContainerRunning()
          if (ready) {
            openSimulationPage()
          } else {
            ElMessage.error('仿真环境启动超时，请联系教师')
          }
        } finally {
          loadingInstance2.close()
        }
      } catch (action) {
        if (action === 'cancel') {
          // 点「重新创建」
          const loadingInstance2 = ElLoading.service({
            text: '正在重建...',
            background: 'rgba(0,0,0,0.5)'
          })
          try {
            await recreateAndWait(loadingInstance2)
          } finally {
            loadingInstance2.close()
          }
        }
      }
      return
    }

    // ── 情况 4：error / creating（自动销毁重建）──
    await recreateAndWait(loadingInstance)
  } finally {
    loadingInstance.close()
  }
}

// TODO: 开始考试/测试按钮点击事件
const handleStartExam = () => {
  console.log('TODO: 开始考试/测试逻辑')
}

// 组件挂载时获取数据
onMounted(() => {
  getHomeData()
})
</script>

<template>
  <div :class="prefixCls">
    <!-- 状态卡片区域 -->
    <ElRow :gutter="20" class="status-cards">
      <ElCol :xs="24" :sm="12">
        <ElCard shadow="hover" class="status-card">
          <ElSkeleton :loading="loading" animated :rows="2">
            <template #default>
              <div :class="`${prefixCls}__item flex justify-between`" @click="handleExamCardClick">
                <div>
                  <div
                    :class="`${prefixCls}__item--icon ${prefixCls}__item--exam p-16px inline-block rounded-6px`"
                  >
                    <Icon icon="vi-carbon:task" :size="40" />
                  </div>
                </div>
                <div class="flex flex-col justify-between">
                  <div :class="`${prefixCls}__item--text text-16px text-gray-500 text-right`">
                    待完成考试
                  </div>
                  <div class="text-20px font-700 text-right">{{ pendingExams }}</div>
                </div>
              </div>
            </template>
          </ElSkeleton>
        </ElCard>
      </ElCol>
      <ElCol :xs="24" :sm="12">
        <ElCard shadow="hover" class="status-card">
          <ElSkeleton :loading="loading" animated :rows="2">
            <template #default>
              <div
                :class="`${prefixCls}__item flex justify-between`"
                @click="handleMessageCardClick"
              >
                <div>
                  <div
                    :class="`${prefixCls}__item--icon ${prefixCls}__item--message p-16px inline-block rounded-6px`"
                  >
                    <Icon icon="vi-carbon:email" :size="40" />
                  </div>
                </div>
                <div class="flex flex-col justify-between">
                  <div :class="`${prefixCls}__item--text text-16px text-gray-500 text-right`">
                    未读消息
                  </div>
                  <div class="text-20px font-700 text-right">{{ unreadMessages }}</div>
                </div>
              </div>
            </template>
          </ElSkeleton>
        </ElCard>
      </ElCol>
    </ElRow>

    <!-- 操作按钮区域 -->
    <div class="action-buttons">
      <BaseButton type="primary" size="large" @click="handleStartSimulation">
        开始仿真按键
      </BaseButton>
      <BaseButton type="success" size="large" @click="handleStartExam">
        开始考试/测试按键
      </BaseButton>
    </div>
  </div>
</template>

<style lang="less" scoped>
@prefix-cls: ~'@{adminNamespace}-student-home';

.@{prefix-cls} {
  min-height: 400px;

  .status-cards {
    margin-bottom: 60px;

    .status-card {
      cursor: pointer;
      transition: all 0.3s;

      &:hover {
        transform: translateY(-4px);
      }
    }
  }

  &__item {
    &--exam {
      color: #f4516c;
    }

    &--message {
      color: #36a3f7;
    }

    &:hover {
      :deep(.@{adminNamespace}-icon) {
        color: #fff !important;
      }

      .@{prefix-cls}__item--icon {
        transition: all 0.38s ease-out;
      }

      .@{prefix-cls}__item--exam {
        background: #f4516c;
      }

      .@{prefix-cls}__item--message {
        background: #36a3f7;
      }
    }
  }

  .action-buttons {
    position: absolute;
    top: 50%;
    left: 50%;
    display: flex;
    transform: translate(-50%, -50%);
    justify-content: center;
    align-items: center;
    gap: 20px;
    flex-wrap: wrap;

    .el-button {
      min-width: 180px;
      padding: 12px 30px;
    }
  }
}
</style>
