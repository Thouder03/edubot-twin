<script setup lang="ts">
import { ref, computed } from 'vue'
import { ElMessageBox } from 'element-plus'
import { ContextMenu } from '@/components/ContextMenu'
import type { ContextMenuSchema } from '@/components/ContextMenu/src/types'

const props = defineProps<{
  commands: any // useWorkspace 的聚合实例
}>()

const visible = ref(false)
const position = ref({ x: 0, y: 0 })
const currentNode = ref<any>(null)

async function createFolder() {
  const node = currentNode.value
  const targetDir = node?.type === 'directory' ? node.path : (node?.parentPath ?? '.')

  try {
    const { value } = await ElMessageBox.prompt('请输入文件夹名称', '新建文件夹', {
      confirmButtonText: '确定',
      cancelButtonText: '取消',
      inputPlaceholder: '例如：new-folder',
      inputPattern: /^[^\\/]+$/,
      inputErrorMessage: '文件夹名称不能包含 / 或 \\',
      inputValidator: (val: string) => {
        if (!val.trim()) return '文件夹名称不能为空'
        return true
      }
    })

    const folderName = value.trim()
    const path = targetDir === '.' ? folderName : `${targetDir}/${folderName}`
    await props.commands.mkdirCommand(path)
  } catch {
    // 用户取消
  }
}

const schema = computed<ContextMenuSchema[]>(() => {
  const node = currentNode.value
  const singleSelected = props.commands.selectedPaths.value.size === 1
  const paths = Array.from(props.commands.selectedPaths.value) as string[]

  return [
    {
      icon: 'vi-carbon:folder',
      label: '新建文件夹 (New Folder)',
      command: () => {
        void createFolder()
      }
    },
    {
      icon: 'vi-carbon:edit',
      label: '重命名 (Rename)',
      disabled: !singleSelected,
      command: () => {
        if (node) props.commands.startRenameCommand(node.path)
      }
    },
    {
      icon: 'vi-carbon:copy',
      label: '复制 (Copy)',
      disabled: paths.length === 0,
      command: () => {
        props.commands.copyCommand(paths)
      }
    },
    {
      icon: 'vi-carbon:cut-out',
      label: '剪切 (Cut)',
      disabled: paths.length === 0,
      command: () => {
        props.commands.cutCommand(paths)
      }
    },
    {
      icon: 'vi-carbon:paste',
      label: '粘贴 (Paste)',
      disabled: !props.commands.clipboard?.value?.paths?.length,
      command: () => {
        // 如果点的是文件，贴到父级；点的是目录，贴到该目录
        const targetDir = node?.type === 'directory' ? node.path : (node?.parentPath ?? '.')
        props.commands.pasteCommand(targetDir)
      }
    },
    {
      divided: true,
      icon: 'vi-carbon:trash-can',
      label: '删除 (Delete)',
      disabled: paths.length === 0,
      command: () => {
        props.commands.deleteCommand(paths)
      }
    }
  ]
})

const showMenu = (e: MouseEvent, node: any) => {
  currentNode.value = node
  position.value = { x: e.clientX, y: e.clientY }
  visible.value = true

  // 主动触发 ContextMenu (由于 ContextMenu 封装了 ElDropdown，我们可以借用其 click 触发)
  setTimeout(() => {
    triggerRef.value?.click()
  }, 0)
}

const triggerRef = ref<HTMLElement>()

defineExpose({
  show: showMenu
})
</script>

<template>
  <div
    v-show="visible"
    :style="{ position: 'fixed', left: position.x + 'px', top: position.y + 'px', zIndex: 9999 }"
  >
    <ContextMenu :schema="schema" trigger="click">
      <div ref="triggerRef" style="width: 1px; height: 1px; visibility: hidden"></div>
    </ContextMenu>
  </div>
</template>
