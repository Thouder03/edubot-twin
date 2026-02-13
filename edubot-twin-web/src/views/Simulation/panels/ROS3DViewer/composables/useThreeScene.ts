/**
 * useThreeScene - Three.js 场景初始化与生命周期管理
 *
 * 职责:
 * 1. 创建 Scene / PerspectiveCamera / WebGLRenderer
 * 2. 集成 OrbitControls（鼠标旋转/缩放/平移）
 * 3. Grid / Axes 辅助线的显示控制
 * 4. 背景色响应式更新
 * 5. ResizeObserver 自动适配容器尺寸
 */
import { ref, watch, type Ref } from 'vue'
import * as THREE from 'three'
import { OrbitControls } from 'three/examples/jsm/controls/OrbitControls.js'

export interface ThreeSceneOptions {
  showGrid: Ref<boolean>
  showAxes: Ref<boolean>
  backgroundColor: Ref<string>
  gridSize?: Ref<number>
  gridDivisions?: Ref<number>
}

export function useThreeScene(options: ThreeSceneOptions) {
  const { showGrid, showAxes, backgroundColor, gridSize, gridDivisions } = options

  // ---------- 核心对象 ----------
  let renderer: THREE.WebGLRenderer | null = null
  let camera: THREE.PerspectiveCamera | null = null
  let controls: OrbitControls | null = null
  let animationId: number | null = null
  let resizeObserver: ResizeObserver | null = null

  const scene = new THREE.Scene()
  const sceneReady = ref(false)

  // ---------- 辅助对象 ----------
  let gridHelper: THREE.GridHelper | null = null
  let axesHelper: THREE.AxesHelper | null = null

  /** 创建/重建网格线 */
  function createGrid() {
    if (gridHelper) {
      scene.remove(gridHelper)
      gridHelper.dispose()
    }
    const size = gridSize?.value ?? 20
    const divisions = gridDivisions?.value ?? 20
    gridHelper = new THREE.GridHelper(size, divisions, 0x444466, 0x333355)
    gridHelper.visible = showGrid.value
    scene.add(gridHelper)
  }

  /** 创建坐标轴 */
  function createAxes() {
    if (axesHelper) {
      scene.remove(axesHelper)
      axesHelper.dispose()
    }
    axesHelper = new THREE.AxesHelper(3)
    axesHelper.visible = showAxes.value
    scene.add(axesHelper)
  }

  /** 更新背景色 */
  function updateBackgroundColor(color: string) {
    scene.background = new THREE.Color(color)
  }

  // ---------- 动画渲染循环 ----------
  function animate() {
    animationId = requestAnimationFrame(animate)
    controls?.update()
    if (renderer && camera) {
      renderer.render(scene, camera)
    }
  }

  // ---------- 尺寸自适应 ----------
  function handleResize(container: HTMLElement) {
    if (!renderer || !camera) return
    const { clientWidth: w, clientHeight: h } = container
    if (w === 0 || h === 0) return
    camera.aspect = w / h
    camera.updateProjectionMatrix()
    renderer.setSize(w, h)
  }

  // ---------- 挂载 ----------
  function mount(container: HTMLElement) {
    // Renderer
    renderer = new THREE.WebGLRenderer({ antialias: true })
    renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2))
    renderer.setSize(container.clientWidth, container.clientHeight)
    container.appendChild(renderer.domElement)

    // Camera
    camera = new THREE.PerspectiveCamera(
      60,
      container.clientWidth / container.clientHeight,
      0.1,
      1000
    )
    camera.position.set(5, 5, 5)
    camera.lookAt(0, 0, 0)

    // Controls
    controls = new OrbitControls(camera, renderer.domElement)
    controls.enableDamping = true
    controls.dampingFactor = 0.1
    controls.target.set(0, 0, 0)
    controls.update()

    // 环境光
    const ambientLight = new THREE.AmbientLight(0xffffff, 0.6)
    scene.add(ambientLight)
    const directionalLight = new THREE.DirectionalLight(0xffffff, 0.8)
    directionalLight.position.set(10, 15, 10)
    scene.add(directionalLight)

    // 辅助线
    updateBackgroundColor(backgroundColor.value)
    createGrid()
    createAxes()

    // 渲染循环
    animate()
    sceneReady.value = true

    // ResizeObserver
    resizeObserver = new ResizeObserver(() => handleResize(container))
    resizeObserver.observe(container)
  }

  // ---------- 销毁 ----------
  function dispose() {
    sceneReady.value = false
    if (animationId !== null) {
      cancelAnimationFrame(animationId)
      animationId = null
    }
    resizeObserver?.disconnect()
    resizeObserver = null
    controls?.dispose()
    controls = null

    if (gridHelper) {
      scene.remove(gridHelper)
      gridHelper.dispose()
      gridHelper = null
    }
    if (axesHelper) {
      scene.remove(axesHelper)
      axesHelper.dispose()
      axesHelper = null
    }

    renderer?.dispose()
    renderer?.domElement.remove()
    renderer = null
    camera = null
  }

  // ---------- Watch 响应式配置 ----------
  watch(showGrid, (val) => {
    if (gridHelper) gridHelper.visible = val
  })
  watch(showAxes, (val) => {
    if (axesHelper) axesHelper.visible = val
  })
  watch(backgroundColor, (val) => {
    updateBackgroundColor(val)
  })
  if (gridSize) {
    watch(gridSize, () => createGrid())
  }
  if (gridDivisions) {
    watch(gridDivisions, () => createGrid())
  }

  return {
    scene,
    sceneReady,
    mount,
    dispose
  }
}
