<script setup lang="ts">
import { ref } from 'vue'
import { Draggable } from '@he-tree/vue'
import '@he-tree/vue/style/default.css'
import FileTreeNodeRenderer from './FileTreeNodeRenderer.vue'
import { useDesign } from '@/hooks/web/useDesign'

const { getPrefixCls } = useDesign()
const prefixCls = getPrefixCls('file-tree-container')

const props = defineProps<{
  treeData: any[]
  loading?: boolean
  selectedPaths: Set<string>
}>()

const emit = defineEmits<{
  'select-file': [path: string, event: MouseEvent]
  'open-file-pinned': [path: string, event: MouseEvent]
  'node-contextmenu': [data: any, event: MouseEvent]
  'toggle-expand': [data: any]
  'drop-external': [files: FileList, targetPath: string]
  'move-internal': [sourcePaths: string[], targetDir: string]
  'rename-submit': [path: string, newName: string]
  'rename-cancel': [path: string]
}>()

// 控制节点能不能成为放置目标
function checkDroppable(stat: any) {
  const dropNode = stat.target
  // 控制是否能放置
  if (dropNode && dropNode.type === 'file') {
    return false // 不能放入文件内
  }
  return true
}

const isDragOver = ref(false)

function onDragOver(e: DragEvent) {
  e.preventDefault()
  isDragOver.value = true
}

function onDragLeave() {
  isDragOver.value = false
}

function onDrop(e: DragEvent) {
  e.preventDefault()
  isDragOver.value = false
  const files = e.dataTransfer?.files
  if (files && files.length > 0) {
    emit('drop-external', files, '.')
  }
}

// 内部树节点拖动落下
function onTreeDrop(stat: any) {
  // stat 中包含拖拽信息，包括 dragged node, dropped target etc.
  const dragNode = stat.dragNode
  const parentNode = stat.parent
  const targetDir = parentNode ? parentNode.path : '.'

  if (dragNode && dragNode.path !== targetDir) {
    emit('move-internal', [dragNode.path], targetDir)
  }
}
</script>

<template>
  <div
    :class="[prefixCls, isDragOver && `${prefixCls}--dragover`]"
    @dragover="onDragOver"
    @dragleave="onDragLeave"
    @drop="onDrop"
  >
    <div v-if="loading" :class="`${prefixCls}__loading`"> Loading... </div>

    <Draggable 
      v-else
      :model-value="treeData"
      :each-droppable="checkDroppable"
      @drop="onTreeDrop"
      class="he-tree"
    >
      <template #default="{ node, stat }">
        <FileTreeNodeRenderer
          :node="node"
          :stat="stat"
          :is-selected="selectedPaths.has(node.path)"
          @click="emit('select-file', node.path, $event)"
          @dblclick="emit('open-file-pinned', node.path, $event)"
          @contextmenu="emit('node-contextmenu', node, $event)"
          @toggle-expand="emit('toggle-expand', node)"
          @rename-submit="(newName: string) => emit('rename-submit', node.path, newName)"
          @rename-cancel="emit('rename-cancel', node.path)"
        />
      </template>
    </Draggable>
  </div>
</template>

<style lang="less" scoped>
@prefix: v-file-tree-container;

.@{prefix} {
  position: relative;
  width: 100%;
  height: 100%;
  overflow: auto;

  &--dragover::after {
    position: absolute;
    pointer-events: none;
    border: 2px dashed var(--el-color-primary);
    content: '';
    inset: 2px;
  }

  :deep(.he-tree) {
    // 覆盖 he-tree 默认样式
  }
}
</style>
