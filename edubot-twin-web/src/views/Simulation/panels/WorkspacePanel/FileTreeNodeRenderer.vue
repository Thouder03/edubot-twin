<script setup lang="ts">
import { ref, watch, computed } from 'vue'
import { ElInput } from 'element-plus'
import { Icon } from '@/components/Icon'
import { useDesign } from '@/hooks/web/useDesign'

const { getPrefixCls } = useDesign()
const prefixCls = getPrefixCls('file-tree-node')

const props = defineProps<{
  node: any
  stat: any
  isSelected: boolean
}>()

const emit = defineEmits<{
  'toggle-expand': []
  'rename-submit': [newName: string]
  'rename-cancel': []
}>()

const FILE_ICON_MAP: Record<string, string> = {
  '.py': 'vi-vscode-icons:file-type-python',
  '.cpp': 'vi-vscode-icons:file-type-cpp',
  '.json': 'vi-vscode-icons:file-type-json',
  '.yaml': 'vi-vscode-icons:file-type-yaml',
  '.txt': 'vi-carbon:document',
  default: 'vi-carbon:document' // 简化骨架，具体实现再丰满
}

const getFileIcon = (ext?: string) => {
  return ext && FILE_ICON_MAP[ext] ? FILE_ICON_MAP[ext] : FILE_ICON_MAP.default
}

// ─── 内联编辑状态管理
const localName = ref('')
const inputRef = ref<HTMLInputElement>()

watch(
  () => props.node.isRenaming,
  (isRenaming) => {
    if (isRenaming) {
      localName.value = props.node.name || props.node.label
      // nextTick聚焦
      setTimeout(() => {
        inputRef.value?.focus()
      }, 0)
    }
  }
)

function submitRename() {
  if (!props.node.isRenaming) return
  const trimName = localName.value.trim()
  if (trimName && trimName !== props.node.name) {
    emit('rename-submit', trimName)
  } else {
    emit('rename-cancel')
  }
}

function cancelRename() {
  if (!props.node.isRenaming) return
  emit('rename-cancel')
}
</script>

<template>
  <div
    :class="[prefixCls, isSelected && 'is-selected']"
    :style="{ paddingLeft: `${stat.level * 16}px` }"
  >
    <!-- 展开/折叠箭头 -->
    <span v-if="node.type === 'directory'" class="expand-icon" @click.stop="emit('toggle-expand')">
      <Icon :icon="node.isExpanded ? 'vi-ep:arrow-down' : 'vi-ep:arrow-right'" />
    </span>
    <span v-else class="expand-icon-placeholder"></span>

    <!-- 文件/文件夹图标 -->
    <Icon
      v-if="node.type === 'directory'"
      :icon="node.isExpanded ? 'vi-ep:folder-opened' : 'vi-ep:folder'"
      class="type-icon"
    />
    <Icon v-else :icon="getFileIcon(node.extension)" class="type-icon" />

    <!-- 节点名称或输入框 -->
    <span v-if="!node.isRenaming" class="label">{{ node.label }}</span>
    <el-input
      v-else
      ref="inputRef"
      v-model="localName"
      size="small"
      class="rename-input"
      @keyup.enter="submitRename"
      @keyup.esc="cancelRename"
      @blur="submitRename"
      @click.stop
    />
  </div>
</template>

<style lang="less" scoped>
@prefix: v-file-tree-node;

.@{prefix} {
  display: flex;
  align-items: center;
  padding: 4px 8px;
  cursor: pointer;
  user-select: none;

  &:hover {
    background-color: var(--el-fill-color-light);
  }

  &.is-selected {
    color: var(--el-color-primary);
    background-color: var(--el-color-primary-light-9);
  }

  .expand-icon {
    display: inline-flex;
    width: 16px;
    height: 16px;
    margin-right: 4px;
    font-size: 12px;
    justify-content: center;
    align-items: center;
  }

  .expand-icon-placeholder {
    width: 16px;
    margin-right: 4px;
  }

  .type-icon {
    margin-right: 6px;
    font-size: 16px;
  }

  .label {
    overflow: hidden;
    font-size: 13px;
    text-overflow: ellipsis;
    white-space: nowrap;
    flex: 1;
  }

  .rename-input {
    height: 24px;
    font-size: 13px;
    flex: 1;

    :deep(.el-input__wrapper) {
      height: 24px;
      padding: 0 4px;
      line-height: 24px;
      box-shadow: 0 0 0 1px var(--el-color-primary) inset;
    }
  }
}
</style>
