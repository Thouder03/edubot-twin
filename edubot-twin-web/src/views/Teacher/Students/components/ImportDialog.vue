<script setup lang="ts">
import { ref } from 'vue'
import {
  ElButton,
  ElStep,
  ElSteps,
  ElTable,
  ElTableColumn,
  ElTag,
  ElUpload,
  ElMessage,
  type UploadFile
} from 'element-plus'
import { importStudentsApi } from '@/api/teacher'
import type { StudentImportResult } from '@/api/teacher/types'

defineProps<{ modelValue: boolean }>()
const emit = defineEmits<{
  (e: 'update:modelValue', val: boolean): void
  (e: 'done'): void
}>()

// ─── 步骤 ────────────────────────────────────────────────────
const step = ref<1 | 2 | 3>(1)

// ─── Step 1：文件选择 ────────────────────────────────────────
const selectedFile = ref<File | null>(null)

interface PreviewRow {
  row: number
  username: string
  password: string
  real_name: string
  email: string
  role_code: string
}
const previewRows = ref<PreviewRow[]>([])

function onFileChange(uploadFile: UploadFile) {
  const file = uploadFile.raw
  if (!file) return
  selectedFile.value = file
  parseCSV(file)
}

function parseCSV(file: File) {
  const reader = new FileReader()
  reader.onload = (e) => {
    const text = (e.target?.result as string).replace(/^\uFEFF/, '') // 去 BOM
    const lines = text.split(/\r?\n/).filter((l) => l.trim())
    if (lines.length < 2) {
      ElMessage.warning('CSV 文件内容为空或缺少数据行')
      return
    }
    const headers = lines[0].split(',').map((h) => h.trim())
    const usernameIdx = headers.indexOf('username')
    if (usernameIdx === -1) {
      ElMessage.error('CSV 缺少必填列：username')
      return
    }
    const passwordIdx = headers.indexOf('password')
    const realNameIdx = headers.indexOf('real_name')
    const emailIdx = headers.indexOf('email')
    const roleIdx = headers.indexOf('role_code')

    previewRows.value = lines.slice(1).map((line, i) => {
      const cols = line.split(',').map((c) => c.trim())
      const username = cols[usernameIdx] || ''
      const password = (passwordIdx >= 0 ? cols[passwordIdx] : '') || username
      return {
        row: i + 1,
        username,
        password,
        real_name: realNameIdx >= 0 ? cols[realNameIdx] || '' : '',
        email: emailIdx >= 0 ? cols[emailIdx] || '' : '',
        role_code: (roleIdx >= 0 ? cols[roleIdx] : '') || 'student'
      }
    })
    step.value = 2
  }
  reader.readAsText(file, 'UTF-8')
}

// ─── Step 2：预览 ────────────────────────────────────────────
const importing = ref(false)
const result = ref<StudentImportResult | null>(null)

async function confirmImport() {
  if (!selectedFile.value) return
  importing.value = true
  try {
    const res = await importStudentsApi(selectedFile.value)
    result.value = res.data
    step.value = 3
  } catch {
    // 拦截器已展示错误
  } finally {
    importing.value = false
  }
}

// ─── Step 3：结果 ────────────────────────────────────────────
function handleDone() {
  emit('done')
  emit('update:modelValue', false)
  // 重置状态
  step.value = 1
  selectedFile.value = null
  previewRows.value = []
  result.value = null
}

// ─── 关闭对话框 ──────────────────────────────────────────────
function handleClose() {
  emit('update:modelValue', false)
  step.value = 1
  selectedFile.value = null
  previewRows.value = []
  result.value = null
}

// ─── 模板下载 ────────────────────────────────────────────────
function downloadTemplate() {
  const content =
    'username,password,real_name,email,role_code\nstudent001,,张三,zhang@example.com,student\nstudent002,mypass,李四,,student\nstudent003\n'
  const blob = new Blob(['\uFEFF' + content], { type: 'text/csv;charset=utf-8;' })
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = 'students_template.csv'
  a.click()
  URL.revokeObjectURL(url)
}

const ROLE_LABEL: Record<string, string> = {
  student: '学生',
  teacher: '教师',
  admin: '管理员'
}
</script>

<template>
  <el-dialog
    :model-value="modelValue"
    title="批量导入学生"
    width="680px"
    :close-on-click-modal="false"
    @update:model-value="handleClose"
    @close="handleClose"
  >
    <!-- 步骤条 -->
    <ElSteps :active="step - 1" finish-status="success" class="mb-24px">
      <ElStep title="上传文件" />
      <ElStep title="预览确认" />
      <ElStep title="导入结果" />
    </ElSteps>

    <!-- Step 1：上传 -->
    <template v-if="step === 1">
      <ElUpload
        drag
        accept=".csv"
        :auto-upload="false"
        :show-file-list="false"
        :on-change="onFileChange"
        class="mb-16px"
      >
        <div class="py-32px text-center">
          <div class="text-32px text-gray-400 mb-8px">⬆</div>
          <div class="text-14px text-gray-500">拖拽 CSV 文件到此，或 <em>点击上传</em></div>
          <div class="text-12px text-gray-400 mt-4px">仅支持 .csv 格式</div>
        </div>
      </ElUpload>
      <div class="flex items-center gap-8px text-12px text-gray-500">
        <span>CSV 列：username（必填）, password, real_name, email, role_code</span>
        <ElButton link type="primary" size="small" @click="downloadTemplate">下载模板</ElButton>
      </div>
    </template>

    <!-- Step 2：预览 -->
    <template v-else-if="step === 2">
      <div class="mb-12px flex items-center justify-between">
        <span class="text-14px text-gray-600"
          >共解析 <b>{{ previewRows.length }}</b> 条记录</span
        >
      </div>
      <ElTable :data="previewRows" max-height="320" border size="small">
        <ElTableColumn label="行" prop="row" width="50" />
        <ElTableColumn label="用户名" prop="username" min-width="100" />
        <ElTableColumn label="密码" prop="password" width="120" />
        <ElTableColumn label="姓名" prop="real_name" min-width="90">
          <template #default="{ row }">{{ row.real_name || '-' }}</template>
        </ElTableColumn>
        <ElTableColumn label="邮箱" prop="email" min-width="120">
          <template #default="{ row }">{{ row.email || '-' }}</template>
        </ElTableColumn>
        <ElTableColumn label="角色" width="80">
          <template #default="{ row }">{{ ROLE_LABEL[row.role_code] || row.role_code }}</template>
        </ElTableColumn>
      </ElTable>
    </template>

    <!-- Step 3：结果 -->
    <template v-else>
      <div class="mb-16px flex gap-24px text-15px">
        <span>
          <ElTag type="success" size="large">成功 {{ result?.success ?? 0 }} 条</ElTag>
        </span>
        <span>
          <ElTag :type="(result?.failed?.length ?? 0) > 0 ? 'danger' : 'info'" size="large">
            失败 {{ result?.failed?.length ?? 0 }} 条
          </ElTag>
        </span>
      </div>
      <ElTable
        v-if="(result?.failed?.length ?? 0) > 0"
        :data="result!.failed"
        border
        size="small"
        max-height="240"
      >
        <ElTableColumn label="行" prop="row" width="60" />
        <ElTableColumn label="用户名" prop="username" width="120" />
        <ElTableColumn label="错误原因" prop="error" min-width="180" />
      </ElTable>
    </template>

    <!-- 底部按钮 -->
    <template #footer>
      <template v-if="step === 2">
        <ElButton @click="step = 1">上一步</ElButton>
        <ElButton type="primary" :loading="importing" @click="confirmImport"> 确认导入 </ElButton>
      </template>
      <template v-else-if="step === 3">
        <ElButton type="primary" @click="handleDone">完成</ElButton>
      </template>
      <template v-else>
        <ElButton @click="handleClose">取消</ElButton>
      </template>
    </template>
  </el-dialog>
</template>
