<template>
  <el-dialog
    v-model="visible"
    :title="filename"
    width="800px"
    top="6vh"
    destroy-on-close
    class="artifact-preview-dialog"
  >
    <div v-if="loading" class="preview-loading">
      <el-skeleton :rows="8" animated />
    </div>
    <div v-else-if="error" class="preview-error">
      <el-result icon="error" :title="error" />
    </div>
    <template v-else-if="content">
      <!-- 图片预览 -->
      <div v-if="content.encoding === 'base64'" class="preview-image">
        <img :src="`data:${content.mime};base64,${content.content}`" :alt="filename" />
      </div>
      <!-- 文本 / JSON 预览 -->
      <div v-else class="preview-text">
        <pre class="code-block">{{ content.content }}</pre>
      </div>
    </template>

    <template #footer>
      <el-button @click="visible = false">关闭</el-button>
    </template>
  </el-dialog>
</template>

<script setup lang="ts">
import { ref, watch } from 'vue'
import { ElMessage } from 'element-plus'
import type { ArtifactFileContent } from '@/api/exam/attempts'
import { getArtifactFileApi } from '@/api/exam/attempts'

const props = defineProps<{
  attemptId: number | null
  filename: string
  modelValue: boolean
}>()

const emit = defineEmits<{
  (e: 'update:modelValue', v: boolean): void
}>()

const visible = ref(false)
const loading = ref(false)
const error = ref<string | null>(null)
const content = ref<ArtifactFileContent | null>(null)

watch(
  () => props.modelValue,
  async (v) => {
    visible.value = v
    if (v && props.attemptId && props.filename) {
      await loadFile()
    }
  }
)

watch(visible, (v) => {
  if (!v) emit('update:modelValue', false)
})

async function loadFile() {
  loading.value = true
  error.value = null
  content.value = null
  try {
    const res = await getArtifactFileApi(props.attemptId!, props.filename)
    content.value = res.data ?? null
  } catch (e: unknown) {
    const err = e as { response?: { data?: { detail?: { message?: string } } } }
    const msg = err?.response?.data?.detail?.message
    if (msg?.includes('过大')) {
      error.value = '文件超出 5MB 预览限制，请下载查看'
    } else if (msg?.includes('不存在')) {
      error.value = '文件已清理或不存在'
    } else {
      error.value = '预览加载失败'
    }
    ElMessage.warning(error.value!)
  } finally {
    loading.value = false
  }
}
</script>

<style scoped>
.preview-loading,
.preview-error {
  padding: 24px 0;
}
.preview-image {
  text-align: center;
  max-height: 60vh;
  overflow: auto;
}
.preview-image img {
  max-width: 100%;
  max-height: 55vh;
  object-fit: contain;
}
.preview-text {
  max-height: 60vh;
  overflow: auto;
}
.code-block {
  margin: 0;
  padding: 12px;
  font-size: 12px;
  font-family: 'Fira Code', 'JetBrains Mono', monospace;
  background: var(--el-fill-color-darker);
  border-radius: 4px;
  white-space: pre-wrap;
  word-break: break-all;
}
</style>
