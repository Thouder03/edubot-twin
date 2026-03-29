<script setup lang="ts">
/**
 * GLayout.vue - Golden Layout 与 Vue 3 桥接组件
 *
 * 功能:
 * 1. Virtual Components: GL bindComponentEvent → Vue Teleport 渲染
 * 2. 禁用 popout → 注入「设置」齿轮按钮到 Stack header
 * 3. 齿轮按钮点击 → emit 事件由父组件处理设置面板
 * 4. 面板注册表: 从 panels/registry.ts 统一导入
 */
import {
  ref,
  shallowRef,
  onMounted,
  onBeforeUnmount,
  nextTick,
  type Component as VueComponent
} from 'vue'
import {
  GoldenLayout,
  type LayoutConfig,
  type ResolvedLayoutConfig,
  type ComponentContainer,
  type ResolvedComponentItemConfig
} from 'golden-layout'

import { buildComponentMap } from '../panels/registry'

// ---------- Props ----------
interface Props {
  initialLayout?: LayoutConfig
}

const props = withDefaults(defineProps<Props>(), {
  initialLayout: undefined
})

// ---------- Events ----------
const emit = defineEmits<{
  (e: 'settings-toggle', panelId: string): void
}>()

// ---------- 组件映射 ----------
const componentMap: Record<string, VueComponent> = buildComponentMap()

// ---------- 状态 ----------
const glContainerRef = ref<HTMLElement>()
let goldenLayout: GoldenLayout | null = null

// 管理虚拟组件: key=container, value=挂载信息
interface VirtualComponentInfo {
  container: ComponentContainer
  componentType: string
  rootElement: HTMLElement
  panelId: string
}
const virtualComponents = shallowRef<Map<ComponentContainer, VirtualComponentInfo>>(new Map())

// 每创建一个虚拟组件, 往这个列表推一条, 用 v-for 渲染
// 注意: container 类型用 any 避免 TS "类型实例化过深" 问题
interface RenderItem {
  id: number
  panelId: string
  componentType: string
  container: any
  element: HTMLElement | null
}
const renderList = ref<RenderItem[]>([])
let nextId = 0

// ---------- 齿轮按钮 SVG ----------
const SETTINGS_ICON_SVG = `<svg viewBox="0 0 16 16" width="11" height="11" fill="currentColor" xmlns="http://www.w3.org/2000/svg"><path d="M8 4.754a3.246 3.246 0 1 0 0 6.492 3.246 3.246 0 0 0 0-6.492zM5.754 8a2.246 2.246 0 1 1 4.492 0 2.246 2.246 0 0 1-4.492 0z"/><path d="M9.796 1.343c-.527-1.79-3.065-1.79-3.592 0l-.094.319a.873.873 0 0 1-1.255.52l-.292-.16c-1.64-.892-3.433.902-2.54 2.541l.159.292a.873.873 0 0 1-.52 1.255l-.319.094c-1.79.527-1.79 3.065 0 3.592l.319.094a.873.873 0 0 1 .52 1.255l-.16.292c-.892 1.64.901 3.434 2.541 2.54l.292-.159a.873.873 0 0 1 1.255.52l.094.319c.527 1.79 3.065 1.79 3.592 0l.094-.319a.873.873 0 0 1 1.255-.52l.292.16c1.64.893 3.434-.902 2.54-2.541l-.159-.292a.873.873 0 0 1 .52-1.255l.319-.094c1.79-.527 1.79-3.065 0-3.592l-.319-.094a.873.873 0 0 1-.52-1.255l.16-.292c.893-1.64-.902-3.433-2.541-2.54l-.292.159a.873.873 0 0 1-1.255-.52l-.094-.319z"/></svg>`

// ---------- 禁用 popout ----------
function patchConfig(config: LayoutConfig): LayoutConfig {
  return { ...config, header: { ...config.header, popout: false } }
}

// ---------- 齿轮按钮：注入到 GL Stack header ----------
function injectSettingsButtons() {
  if (!glContainerRef.value) return
  const controlsList = glContainerRef.value.querySelectorAll('.lm_controls')
  controlsList.forEach((controls) => {
    if (controls.querySelector('.lm_settings')) return
    const btn = document.createElement('div')
    btn.className = 'lm_settings'
    btn.title = '设置'
    btn.innerHTML = SETTINGS_ICON_SVG
    btn.addEventListener('click', (e) => {
      e.stopPropagation()
      const stack = controls.closest('.lm_stack') || controls.closest('.lm_goldenlayout')
      if (!stack) return
      const activeTab = stack.querySelector('.lm_tab.lm_active') as HTMLElement | null
      const panelId = activeTab?.dataset.panelId || ''
      if (panelId) {
        handleSettingsToggle(panelId)
      }
    })
    const maximiseBtn = controls.querySelector('.lm_maximise')
    const closeBtn = controls.querySelector('.lm_close')
    const insertBefore = maximiseBtn || closeBtn
    if (insertBefore) {
      controls.insertBefore(btn, insertBefore)
    } else {
      controls.appendChild(btn)
    }
  })
}

// ---------- 在 tab 上设置 data 属性 ----------
function setupTabDataAttributes() {
  virtualComponents.value.forEach((info) => {
    try {
      const tab = info.container.tab
      if (tab && tab.element) {
        tab.element.dataset.panelId = info.panelId
        tab.element.dataset.componentType = info.componentType
      }
    } catch {
      /* tab 可能尚未创建 */
    }
  })
}

// ---------- 齿轮点击 → emit 事件给父组件 ----------
function handleSettingsToggle(targetPanelId: string) {
  emit('settings-toggle', targetPanelId)
}

// ---------- GL 事件处理 ----------
function handleBindComponentEvent(
  container: ComponentContainer,
  itemConfig: ResolvedComponentItemConfig
): ComponentContainer.BindableComponent {
  const componentType =
    typeof itemConfig.componentType === 'string'
      ? itemConfig.componentType
      : String(itemConfig.componentType)

  // 创建 DOM 容器
  const el = document.createElement('div')
  el.style.width = '100%'
  el.style.height = '100%'
  el.style.overflow = 'hidden'

  const id = nextId++
  const panelId = `panel-${id}`
  renderList.value = [...renderList.value, { id, panelId, componentType, container, element: null }]

  const info: VirtualComponentInfo = { container, componentType, rootElement: el, panelId }
  const newMap = new Map(virtualComponents.value)
  newMap.set(container, info)
  virtualComponents.value = newMap

  // 将 DOM 附加到 GL 容器
  container.element.appendChild(el)

  container.virtualRectingRequiredEvent = () => {}
  container.virtualVisibilityChangeRequiredEvent = (_container, _visible) => {
    const entry = renderList.value.find((r) => r.container === _container)
    if (entry && entry.element) {
      entry.element.style.display = _visible ? '' : 'none'
    }
  }

  // 下一帧后刷新 Teleport 目标
  nextTick(() => {
    const entry = renderList.value.find((r) => r.id === id)
    if (entry) {
      entry.element = el
      renderList.value = [...renderList.value]
    }
    setupTabDataAttributes()
    injectSettingsButtons()
  })

  return { component: el, virtual: true }
}

function handleUnbindComponentEvent(container: ComponentContainer): void {
  const newMap = new Map(virtualComponents.value)
  newMap.delete(container)
  virtualComponents.value = newMap
  renderList.value = renderList.value.filter((r) => r.container !== container)
}

// ---------- 生命周期 ----------
onMounted(() => {
  if (!glContainerRef.value) return

  // 创建 GoldenLayout 实例
  goldenLayout = new GoldenLayout(
    glContainerRef.value,
    handleBindComponentEvent,
    handleUnbindComponentEvent
  )

  // GL 自动响应容器尺寸变化（侧栏开关/拖拽时 flex 布局自动调整）
  goldenLayout.resizeWithContainerAutomatically = true

  // 监听布局状态变化，重新注入按钮
  goldenLayout.on('stateChanged', () => {
    nextTick(() => {
      setupTabDataAttributes()
      injectSettingsButtons()
    })
  })

  // 加载初始布局（禁用 popout）
  if (props.initialLayout) {
    goldenLayout.loadLayout(patchConfig(props.initialLayout))
  }

  // 监听窗口大小变化
  window.addEventListener('resize', handleResize)
})

onBeforeUnmount(() => {
  window.removeEventListener('resize', handleResize)
  if (goldenLayout) {
    goldenLayout.destroy()
    goldenLayout = null
  }
})

function handleResize() {
  if (goldenLayout && glContainerRef.value) {
    goldenLayout.setSize(glContainerRef.value.offsetWidth, glContainerRef.value.offsetHeight)
  }
}

// ---------- 暴露方法 ----------
function addComponent(componentType: string, title?: string) {
  if (!goldenLayout) return
  goldenLayout.addComponent(componentType, undefined, title || componentType)
}

function loadLayout(config: LayoutConfig) {
  if (!goldenLayout) return
  goldenLayout.loadLayout(patchConfig(config))
}

function saveLayout(): ResolvedLayoutConfig | undefined {
  if (!goldenLayout) return undefined
  return goldenLayout.saveLayout()
}

defineExpose({
  addComponent,
  loadLayout,
  saveLayout,
  handleResize
})
</script>

<template>
  <div class="gl-wrapper">
    <!-- GL 布局容器 -->
    <div ref="glContainerRef" class="gl-container"></div>

    <!-- 虚拟组件渲染区: 通过 Teleport 渲染到 GL 容器内 -->
    <template v-for="item in renderList" :key="item.id">
      <Teleport v-if="item.element" :to="item.element">
        <component
          :is="componentMap[item.componentType]"
          v-if="componentMap[item.componentType]"
          :panel-id="item.panelId"
        />
        <div v-else class="unknown-component">未知组件: {{ item.componentType }}</div>
      </Teleport>
    </template>
  </div>
</template>

<style lang="less">
/* GL 样式不能用 scoped, 因为 GL 动态注入 DOM */
.gl-wrapper {
  position: relative;
  height: 100%;
  min-width: 0;
  flex: 1;
}

.gl-container {
  width: 100%;
  height: 100%;
}

.unknown-component {
  display: flex;
  width: 100%;
  height: 100%;
  font-size: 14px;
  color: #f38ba8;
  background: #1e1e2e;
  align-items: center;
  justify-content: center;
}

/* 设置按钮样式 */
.lm_controls .lm_settings {
  position: relative;
  display: flex;
  width: 18px;
  height: 18px;
  color: #fff;
  cursor: pointer;
  opacity: 0.4;
  transition: opacity 300ms ease;
  align-items: center;
  justify-content: center;

  &:hover {
    opacity: 1;
  }

  svg {
    pointer-events: none;
  }
}
</style>
