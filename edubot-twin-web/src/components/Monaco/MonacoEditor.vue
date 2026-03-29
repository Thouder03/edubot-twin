<script setup lang="ts">
/**
 * MonacoEditor.vue — Monaco Editor 封装组件（CDN 懒加载方案）
 *
 * Props:
 *   - modelValue: 编辑器内容（v-model）
 *   - language:   语言标识（可选，由父组件传入或从文件名推断）
 *   - readonly:   是否只读
 *   - settings:   编辑器配置（字体、主题等）
 *
 * Emits:
 *   - update:modelValue: 内容变化
 *   - save: Ctrl+S 触发保存
 *   - ready: 编辑器初始化完成
 */
import { ref, watch, onMounted, onUnmounted, computed } from 'vue'
import { ElIcon } from 'element-plus'
import loader from '@monaco-editor/loader'
import type { WorkspaceSettings } from '@/composables/useWorkspaceSettings'

// ─── CDN 配置（也可切换为国内镜像）
loader.config({
  paths: {
    vs: 'https://cdn.jsdelivr.net/npm/monaco-editor@0.45.0/min/vs'
  }
})

// ─── Props
interface Props {
  modelValue?: string
  language?: string
  readonly?: boolean
  settings?: Partial<WorkspaceSettings>
  placeholder?: string
}

const props = withDefaults(defineProps<Props>(), {
  modelValue: '',
  language: 'plaintext',
  readonly: false,
  placeholder: '选择一个文件以开始编辑...'
})

// ─── Emits
const emit = defineEmits<{
  'update:modelValue': [value: string]
  save: [value: string]
  ready: []
}>()

// ─── 状态
const containerRef = ref<HTMLDivElement>()
let monacoInstance: any = null
let editorInstance: any = null
const isLoading = ref(true)
const loadError = ref('')

// ─── 语言映射
const LANGUAGE_MAP: Record<string, string> = {
  '.py': 'python',
  '.cpp': 'cpp',
  '.cc': 'cpp',
  '.cxx': 'cpp',
  '.c': 'c',
  '.h': 'cpp',
  '.hpp': 'cpp',
  '.js': 'javascript',
  '.ts': 'typescript',
  '.json': 'json',
  '.yaml': 'yaml',
  '.yml': 'yaml',
  '.xml': 'xml',
  '.launch': 'xml',
  '.urdf': 'xml',
  '.xacro': 'xml',
  '.sh': 'shell',
  '.bash': 'shell',
  '.md': 'markdown',
  '.txt': 'plaintext',
  '.cfg': 'ini',
  '.ini': 'ini',
  '.toml': 'markdown'
}

function detectLanguage(lang: string): string {
  // 先通过文件扩展名识别
  if (lang.startsWith('.')) {
    return LANGUAGE_MAP[lang] ?? 'plaintext'
  }
  return lang
}

const resolvedLanguage = computed(() => detectLanguage(props.language ?? 'plaintext'))

// ─── 编辑器选项
const editorOptions = computed(() => ({
  theme: props.settings?.theme ?? 'vs-dark',
  fontSize: props.settings?.fontSize ?? 14,
  wordWrap: props.settings?.wordWrap ?? 'on',
  minimap: { enabled: props.settings?.minimap ?? true },
  automaticLayout: true,
  scrollBeyondLastLine: false,
  tabSize: props.settings?.tabSize ?? 4,
  insertSpaces: true,
  readOnly: props.readonly,
  scrollbar: {
    useShadows: false,
    verticalScrollbarSize: 8,
    horizontalScrollbarSize: 8
  },
  padding: { top: 12, bottom: 12 }
}))

// ─── 初始化 Monaco
async function initMonaco() {
  if (!containerRef.value) return
  try {
    monacoInstance = await loader.init()

    editorInstance = monacoInstance.editor.create(containerRef.value, {
      value: props.modelValue,
      language: resolvedLanguage.value,
      ...editorOptions.value
    })

    // 内容变化
    editorInstance.onDidChangeModelContent(() => {
      const value = editorInstance.getValue()
      emit('update:modelValue', value)
    })

    // Ctrl+S 保存
    editorInstance.addCommand(monacoInstance.KeyMod.CtrlCmd | monacoInstance.KeyCode.KeyS, () => {
      emit('save', editorInstance.getValue())
    })

    isLoading.value = false
    emit('ready')
  } catch (err: any) {
    loadError.value = `Monaco Editor 加载失败: ${err.message}`
    isLoading.value = false
    console.error('Monaco load error:', err)
  }
}

// ─── 监听 props 变化
watch(
  () => props.modelValue,
  (val) => {
    if (editorInstance && editorInstance.getValue() !== val) {
      const pos = editorInstance.getPosition()
      editorInstance.setValue(val ?? '')
      if (pos) editorInstance.setPosition(pos)
    }
  }
)

watch(resolvedLanguage, (lang) => {
  if (editorInstance && monacoInstance) {
    monacoInstance.editor.setModelLanguage(editorInstance.getModel(), lang)
  }
})

watch(
  () => props.settings,
  (s) => {
    if (!editorInstance || !s) return
    editorInstance.updateOptions({
      theme: s.theme ?? 'vs-dark',
      fontSize: s.fontSize ?? 14,
      wordWrap: s.wordWrap ?? 'on',
      minimap: { enabled: s.minimap ?? true },
      tabSize: s.tabSize ?? 4
    })
  },
  { deep: true }
)

// ─── 暴露给父组件
defineExpose({
  /** 获取当前编辑器内容 */
  getValue: () => editorInstance?.getValue() ?? '',
  /** 格式化代码 */
  format: () => editorInstance?.getAction('editor.action.formatDocument')?.run(),
  /** 聚焦 */
  focus: () => editorInstance?.focus()
})

// ─── 生命周期
onMounted(initMonaco)

onUnmounted(() => {
  editorInstance?.dispose()
  editorInstance = null
})
</script>

<template>
  <div class="monaco-editor-wrapper">
    <!-- 加载中 -->
    <div v-if="isLoading" class="monaco-editor-wrapper__loading">
      <el-icon class="is-loading" :size="24">
        <i class="vi-ep:loading"></i>
      </el-icon>
      <span>编辑器加载中...</span>
    </div>

    <!-- 加载错误 -->
    <div v-else-if="loadError" class="monaco-editor-wrapper__error">
      <el-icon :size="24"><i class="vi-ep:warning"></i></el-icon>
      <span>{{ loadError }}</span>
    </div>

    <!-- 未选择文件 -->
    <div v-else-if="!modelValue && !isLoading" class="monaco-editor-wrapper__placeholder">
      <el-icon :size="48" class="monaco-editor-wrapper__placeholder-icon">
        <i class="vi-carbon:document"></i>
      </el-icon>
      <p>{{ placeholder }}</p>
    </div>

    <!-- Monaco 挂载点 -->
    <div
      ref="containerRef"
      class="monaco-editor-wrapper__container"
      :style="{ visibility: isLoading || loadError ? 'hidden' : 'visible' }"
    ></div>
  </div>
</template>

<style lang="less" scoped>
.monaco-editor-wrapper {
  position: relative;
  width: 100%;
  height: 100%;
  overflow: hidden;
  background: #1e1e1e;

  &__container {
    width: 100%;
    height: 100%;
  }

  &__loading,
  &__error,
  &__placeholder {
    position: absolute;
    display: flex;
    font-size: 14px;
    color: var(--el-text-color-secondary);
    inset: 0;
    flex-direction: column;
    align-items: center;
    justify-content: center;
    gap: 12px;
  }

  &__placeholder {
    background: var(--el-bg-color);

    &-icon {
      color: var(--el-color-info-light-5);
    }

    p {
      margin: 0;
      font-size: 13px;
    }
  }

  &__error {
    color: var(--el-color-danger);
  }
}
</style>
