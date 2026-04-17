<script setup lang="ts">
import { ContentWrap } from '@/components/ContentWrap'
import { ref, onMounted } from 'vue'
import { ElForm, ElFormItem, ElInputNumber, ElButton, ElMessage } from 'element-plus'
import { getContainerDefaultConfigApi, updateContainerDefaultConfigApi } from '@/api/teacher'
import type { ContainerDefaultConfigUpdate } from '@/api/teacher/types'

const loading = ref(false)
const saving = ref(false)

const form = ref<ContainerDefaultConfigUpdate>({
  cpu_limit: 2.0,
  memory_limit_mb: 1024,
  shm_size_mb: 512
})

async function loadConfig() {
  loading.value = true
  try {
    const res = await getContainerDefaultConfigApi()
    if (res.code === 0 && res.data) {
      form.value = {
        cpu_limit: res.data.cpu_limit,
        memory_limit_mb: res.data.memory_limit_mb,
        shm_size_mb: res.data.shm_size_mb
      }
    }
  } finally {
    loading.value = false
  }
}

async function handleSave() {
  saving.value = true
  try {
    const res = await updateContainerDefaultConfigApi(form.value)
    if (res.code === 0) {
      ElMessage.success('配置已保存')
    }
  } finally {
    saving.value = false
  }
}

onMounted(loadConfig)
</script>

<template>
  <ContentWrap title="仿真容器配置" message="配置新建仿真容器时使用的全局默认资源参数">
    <ElForm
      v-loading="loading"
      label-width="140px"
      label-position="left"
      style="max-width: 520px; margin-top: 8px"
    >
      <ElFormItem label="CPU 核心数">
        <ElInputNumber
          v-model="form.cpu_limit"
          :min="0.1"
          :max="4.0"
          :step="0.5"
          :precision="1"
          controls-position="right"
          style="width: 180px"
        />
        <span style="margin-left: 8px; color: var(--el-text-color-secondary)">核心</span>
      </ElFormItem>

      <ElFormItem label="内存限额">
        <ElInputNumber
          v-model="form.memory_limit_mb"
          :min="256"
          :max="8192"
          :step="256"
          controls-position="right"
          style="width: 180px"
        />
        <span style="margin-left: 8px; color: var(--el-text-color-secondary)">MB</span>
      </ElFormItem>

      <ElFormItem label="共享内存">
        <ElInputNumber
          v-model="form.shm_size_mb"
          :min="128"
          :max="2048"
          :step="128"
          controls-position="right"
          style="width: 180px"
        />
        <span style="margin-left: 8px; color: var(--el-text-color-secondary)">MB</span>
      </ElFormItem>

      <ElFormItem>
        <ElButton type="primary" :loading="saving" @click="handleSave">保存配置</ElButton>
      </ElFormItem>
    </ElForm>
  </ContentWrap>
</template>
