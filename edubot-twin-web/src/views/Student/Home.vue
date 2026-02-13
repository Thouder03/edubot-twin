<script setup lang="ts">
import { useDesign } from '@/hooks/web/useDesign'
import { ElCard, ElRow, ElCol, ElSkeleton } from 'element-plus'
import { BaseButton } from '@/components/Button'
import { ref, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import { getStudentHomeDataApi } from '@/api/student'

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

// 开始仿真：在新标签页打开仿真工作台
const handleStartSimulation = () => {
  const url = router.resolve({ name: 'Simulation' }).href
  window.open(url, '_blank')
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
    transform: translate(-50%, -50%);
    display: flex;
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
