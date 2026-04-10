<script setup lang="ts">
import { useDesign } from '@/hooks/web/useDesign'
import {
  ElCard,
  ElRow,
  ElCol,
  ElSkeleton,
  ElLoading,
  ElMessage,
  ElSelect,
  ElOption
} from 'element-plus'
import { BaseButton } from '@/components/Button'
import { ref, onMounted, computed } from 'vue'
import { useRouter } from 'vue-router'
import { getStudentHomeDataApi } from '@/api/student'
import {
  distributeSimulationFilesApi,
  getAvailableExperimentsApi,
  getSimulationTaskApi,
  startSimulationApi
} from '@/api/experiment'
import type {
  StudentAvailableVersionItem,
  StudentSimulationTaskResponse
} from '@/api/experiment/types'
import { ElMessageBox } from 'element-plus'

const { getPrefixCls } = useDesign()
const prefixCls = getPrefixCls('student-home')
const router = useRouter()

// 加载状态
const loading = ref(true)

// 待完成考试数据
const pendingExams = ref(0)

// 未读消息数据
const unreadMessages = ref(0)

const availableVersions = ref<StudentAvailableVersionItem[]>([])
const selectedVersionId = ref<string>('')

const selectedVersion = computed(() => {
  const id = Number(selectedVersionId.value)
  if (!id) return null
  return availableVersions.value.find((item) => item.version_id === id) || null
})

// 获取学生首页数据
const getHomeData = async () => {
  try {
    const res = await getStudentHomeDataApi()
    if (res?.data) {
      pendingExams.value = res.data.pendingExams
      unreadMessages.value = res.data.unreadMessages
    }
  } catch (error) {
    console.error('获取学生首页数据失败:', error)
  }
}

const getAvailableVersions = async () => {
  try {
    const res = await getAvailableExperimentsApi()
    availableVersions.value = res?.data || []
    if (!selectedVersionId.value && availableVersions.value.length > 0) {
      selectedVersionId.value = String(availableVersions.value[0].version_id)
    }
  } catch (error) {
    console.error('获取实验版本失败:', error)
    ElMessage.error('获取实验版本失败，请稍后重试')
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

function openSimulationPage(version: StudentAvailableVersionItem) {
  const url = router.resolve({
    name: 'Simulation',
    query: {
      experiment_name: version.experiment_name,
      version_name: version.version_name,
      environment_key: version.environment_key,
      experiment_id: String(version.experiment_id),
      version_id: String(version.version_id)
    }
  }).href

  const newWin = window.open(url, '_blank')
  if (!newWin) {
    ElMessage.warning('新标签页被浏览器拦截，将在当前标签页跳转')
    router.push({
      name: 'Simulation',
      query: {
        experiment_name: version.experiment_name,
        version_name: version.version_name,
        environment_key: version.environment_key,
        experiment_id: String(version.experiment_id),
        version_id: String(version.version_id)
      }
    })
  }
}

// ─── 阶段文案映射（SDD §15.1）────────────────────────────────────────────────

const stageTextMap: Record<string, string> = {
  PREPARING_CONFIG: '正在准备配置...',
  STOPPING_OLD_CONTAINER: '正在清理旧环境...',
  CREATING_NEW_CONTAINER: '正在创建仿真容器...',
  CHECKING_GZWEB: '等待 Gazebo 仿真引擎启动...',
  CHECKING_ROSBRIDGE: '等待 ROS 通信桥启动...',
  VALIDATING_MANIFEST: '正在校验实验文件清单...',
  DISTRIBUTING_FILES: '正在分发实验文件到容器...',
  SETTING_PERMISSIONS: '正在设置实验目录权限...',
  SUCCEEDED: '仿真环境就绪，正在打开...',
  FAILED: '启动失败'
}

async function pollTaskUntilDone(
  taskId: string,
  loadingInstance: ReturnType<typeof ElLoading.service>
): Promise<StudentSimulationTaskResponse> {
  const maxRounds = 90
  const intervalMs = 2000

  for (let i = 0; i < maxRounds; i++) {
    const res = await getSimulationTaskApi(taskId)
    const task = res.data
    if (!task) {
      throw new Error('task response empty')
    }

    // 按 current_stage 更新文案（SDD §15.1）
    const stage = (task as any).current_stage as string | undefined
    if (stage && stageTextMap[stage]) {
      loadingInstance.setText(stageTextMap[stage])
    }

    if (task.task_status === 'SUCCEEDED' || task.task_status === 'FAILED') {
      return task
    }

    await new Promise((resolve) => setTimeout(resolve, intervalMs))
  }

  throw new Error('task timeout')
}

const handleStartSimulation = async () => {
  const version = selectedVersion.value
  if (!version) {
    ElMessage.warning('请先选择实验版本')
    return
  }

  const loadingInstance = ElLoading.service({
    text: '正在启动仿真环境...',
    background: 'rgba(0,0,0,0.8)'
  })

  try {
    const startRes = await startSimulationApi({
      version_id: version.version_id
    })

    const startData = startRes.data
    if (startData?.task_id) {
      loadingInstance.setText('正在准备配置...')
      const task = await pollTaskUntilDone(startData.task_id, loadingInstance)
      if (task.task_status === 'FAILED') {
        loadingInstance.close()
        // FAILED 时弹出错误弹窗含重试按钮（SDD §15.1）
        await ElMessageBox.confirm(
          task.error_message || '仿真环境启动失败，请检查配置后重试',
          '启动失败',
          {
            confirmButtonText: '重试',
            cancelButtonText: '关闭',
            type: 'error'
          }
        )
          .then(() => handleStartSimulation())
          .catch(() => {})
        return
      }
    }

    loadingInstance.setText('正在分发实验文件...')
    const distRes = await distributeSimulationFilesApi({
      version_id: version.version_id,
      selected_paths: [],
      mode: 'pull'
    })
    const distData = distRes.data
    if (distData?.task_id) {
      const distTask = await pollTaskUntilDone(distData.task_id, loadingInstance)
      if (distTask.task_status === 'FAILED') {
        loadingInstance.close()
        await ElMessageBox.confirm(
          distTask.error_message || '实验文件分发失败，请重试',
          '文件分发失败',
          {
            confirmButtonText: '重试',
            cancelButtonText: '关闭',
            type: 'error'
          }
        )
          .then(() => handleStartSimulation())
          .catch(() => {})
        return
      }
    }

    // SUCCEEDED：延迟 500ms 后跳转（SDD §15.1）
    loadingInstance.setText('仿真环境就绪，正在打开...')
    await new Promise((resolve) => setTimeout(resolve, 500))
    openSimulationPage(version)
  } catch (e: any) {
    const detail = e?.response?.data?.detail
    if (detail === 'EXPERIMENT_VERSION_NOT_FOUND') {
      ElMessage.error('实验版本不存在或未发布，请重新选择')
      await getAvailableVersions()
      return
    }

    if (detail === 'CONTAINER_REBUILD_IN_PROGRESS') {
      ElMessage.warning('已有重建任务进行中，请稍后重试')
      return
    }

    if (detail === 'NO_FILE_BUNDLE_ATTACHED') {
      ElMessage.error('该实验版本未绑定文件包，请联系教师配置')
      return
    }

    if (detail === 'FILE_BUNDLE_NOT_VALID') {
      ElMessage.error('实验文件包未通过校验，请联系教师修复')
      return
    }

    if (e?.response?.status === 503) {
      ElMessage.error('服务器资源已满，请稍后再试')
      return
    }

    ElMessage.error('启动失败，请稍后重试')
  } finally {
    loadingInstance.close()
  }
}

const handleStartExam = () => {
  console.log('TODO: 开始考试/测试逻辑')
}

onMounted(async () => {
  loading.value = true
  try {
    await Promise.all([getHomeData(), getAvailableVersions()])
  } finally {
    loading.value = false
  }
})
</script>

<template>
  <div :class="prefixCls">
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

    <div class="action-buttons">
      <ElSelect
        v-model="selectedVersionId"
        placeholder="请选择实验版本"
        style="width: 360px"
        :disabled="loading"
      >
        <ElOption
          v-for="item in availableVersions"
          :key="item.version_id"
          :value="String(item.version_id)"
          :label="`${item.experiment_name} / ${item.version_name} (${item.environment_key})`"
        />
      </ElSelect>

      <BaseButton type="primary" size="large" @click="handleStartSimulation">开始仿真</BaseButton>
      <BaseButton type="success" size="large" @click="handleStartExam">开始考试/测试</BaseButton>
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
      min-width: 160px;
      padding: 12px 24px;
    }
  }
}
</style>
