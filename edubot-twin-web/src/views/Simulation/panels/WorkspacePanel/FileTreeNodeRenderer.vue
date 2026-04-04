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
  click: [event: MouseEvent]
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
  default: 'vi-carbon:document'
}

const getFileIcon = (ext?: string) => {
  return ext && FILE_ICON_MAP[ext] ? FILE_ICON_MAP[ext] : FILE_ICON_MAP.default
}

// ─── 树形引导线
// 每个元素对应一个缩进层级，描述该层应渲染的线条类型：
//   'line'        — 祖先级还有更多兄弟在下方，绘制完整竖线
//   'branch-mid'  — 当前节点非最后兄弟，绘制 ├─ 形状
//   'branch-last' — 当前节点是最后兄弟，绘制 └─ 形状
//   ''            — 祖先是最后一个子节点，此层无需续线
const guideInfos = computed(() => {
  const level = props.stat.level as number
  if (level <= 1) return []

  // 从当前节点向上收集祖先链：chain[0] = 第 1 层祖先，chain[level-1] = 当前节点
  const chain: any[] = []
  let node = props.stat
  while (node.parent) {
    chain.unshift(node)
    node = node.parent
  }

  return chain.map((ancestor: any, i: number) => {
    const siblings: any[] = ancestor.parent?.children ?? []
    const isLast = siblings[siblings.length - 1] === ancestor
    const isCurrentLevel = i === chain.length - 1

    if (isCurrentLevel) {
      return isLast ? 'branch-last' : 'branch-mid'
    }
    return isLast ? '' : 'line'
  })
})

// ─── 内联编辑状态管理
const localName = ref('')
const inputRef = ref<HTMLInputElement>()

watch(
  () => props.node.isRenaming,
  (isRenaming) => {
    if (isRenaming) {
      localName.value = props.node.name || props.node.label
      setTimeout(() => {
        inputRef.value?.focus()
      }, 0)
    }
  }
)

function allowExternalFileDrop(e: DragEvent) {
  if (props.node.type !== 'directory') return
  if (!e.dataTransfer?.types?.includes('Files')) return
  e.preventDefault()
  e.dataTransfer.dropEffect = 'copy'
}

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
    :data-node-path="node.path"
    :data-node-type="node.type"
    :data-node-expanded="node.isExpanded ? 'true' : 'false'"
    @click="(e) => !node.isRenaming && emit('click', e)"
    @dragenter="allowExternalFileDrop"
    @dragover="allowExternalFileDrop"
  >
    <!-- 层级缩进引导线 -->
    <span
      v-for="(guide, i) in guideInfos"
      :key="i"
      class="indent-guide"
      :class="guide && `indent-guide--${guide}`"
    ></span>

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
@guide-width: 14px;
@guide-line-left: 7px;
@guide-color: var(--el-border-color-light);

.@{prefix} {
  display: flex;
  align-items: center;
  height: 24px;
  padding: 0 8px 0 4px;
  cursor: pointer;
  user-select: none;

  &:hover {
    background-color: var(--el-fill-color-light);
  }

  &.is-selected {
    color: var(--el-color-primary);
    background-color: var(--el-color-primary-light-9);
  }

  .indent-guide {
    display: inline-flex;
    width: @guide-width;
    align-self: stretch;
    flex-shrink: 0;
    position: relative;

    // 祖先级继续向下：完整竖线（上下各延伸 1px 消除亚像素间隙）
    &--line::before {
      content: '';
      position: absolute;
      top: -1px;
      bottom: -1px;
      left: @guide-line-left;
      width: 1px;
      background-color: @guide-color;
    }

    // ├─ 中间节点：竖线全高 + 右向横线
    &--branch-mid::before {
      content: '';
      position: absolute;
      top: -1px;
      bottom: -1px;
      left: @guide-line-left;
      width: 1px;
      background-color: @guide-color;
    }

    &--branch-mid::after {
      content: '';
      position: absolute;
      top: 50%;
      left: @guide-line-left;
      right: 0;
      height: 1px;
      background-color: @guide-color;
    }

    // └─ 末尾节点：竖线到中点 + 右向横线
    &--branch-last::before {
      content: '';
      position: absolute;
      top: 0;
      bottom: 50%;
      left: @guide-line-left;
      width: 1px;
      background-color: @guide-color;
    }

    &--branch-last::after {
      content: '';
      position: absolute;
      top: 50%;
      left: @guide-line-left;
      right: 0;
      height: 1px;
      background-color: @guide-color;
    }
  }

  .expand-icon {
    display: inline-flex;
    width: 11px;
    height: 16px;
    margin-right: 2px;
    font-size: 12px;
    justify-content: center;
    align-items: center;
  }

  .expand-icon-placeholder {
    width: 4px;
    margin-right: 1px;
  }

  .type-icon {
    margin-right: 4px;
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
