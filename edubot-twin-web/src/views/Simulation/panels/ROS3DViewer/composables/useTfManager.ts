/**
 * useTfManager - TF 坐标帧管理 + 可视化
 *
 * 职责:
 * 1. 订阅 /tf 和 /tf_static 话题
 * 2. 维护帧树（parent→child 关系）
 * 3. 提供 getFrameGroup(frameId) 获取 THREE.Group
 * 4. 暴露可用帧列表供设置面板选择
 * 5. 可视化：每帧显示小坐标轴 + 名称标签 + 父子连线
 */
import { ref, watch, type Ref } from 'vue'
import * as THREE from 'three'
import { Ros, Topic } from 'roslib'
import type { RosConnectionStatus } from './useRosConnection'

/** TF 变换消息结构 */
interface TFTransformStamped {
  header: {
    frame_id: string
  }
  child_frame_id: string
  transform: {
    translation: { x: number; y: number; z: number }
    rotation: { x: number; y: number; z: number; w: number }
  }
}

interface TFMessage {
  transforms: TFTransformStamped[]
}

/** 帧可视化对象 */
interface FrameVisual {
  axes: THREE.AxesHelper
  label: THREE.Sprite
}

export function useTfManager(
  getRos: () => Ros | null,
  _connectionStatus: Ref<RosConnectionStatus>,
  scene: THREE.Scene,
  showTfFrames?: Ref<boolean>
) {
  const availableFrames = ref<string[]>([])

  // frameId → THREE.Group
  const frameGroups = new Map<string, THREE.Group>()

  // frameId → 可视化对象
  const frameVisuals = new Map<string, FrameVisual>()

  // 父子连线
  const connectionLines = new Map<string, THREE.Line>()

  // TF 树结构: childId → parentId
  const parentMap = new Map<string, string>()

  // 订阅句柄
  let tfSub: Topic | null = null
  let tfStaticSub: Topic | null = null

  // ---------- 标签纹理生成 ----------

  /** 创建文字纹理 Sprite（帧名称标签） */
  function createLabelSprite(text: string): THREE.Sprite {
    const canvas = document.createElement('canvas')
    const ctx = canvas.getContext('2d')!
    const fontSize = 5
    const padding = 5

    ctx.font = `bold ${fontSize}px Consolas, Monaco, monospace`
    const textMetrics = ctx.measureText(text)
    const textWidth = textMetrics.width

    canvas.width = textWidth + padding * 2
    canvas.height = fontSize + padding * 2

    // 背景
    ctx.fillStyle = 'rgba(255, 255, 255, 0.03)'
    const r = 8
    const w = canvas.width
    const h = canvas.height
    ctx.beginPath()
    ctx.moveTo(r, 0)
    ctx.lineTo(w - r, 0)
    ctx.quadraticCurveTo(w, 0, w, r)
    ctx.lineTo(w, h - r)
    ctx.quadraticCurveTo(w, h, w - r, h)
    ctx.lineTo(r, h)
    ctx.quadraticCurveTo(0, h, 0, h - r)
    ctx.lineTo(0, r)
    ctx.quadraticCurveTo(0, 0, r, 0)
    ctx.closePath()
    ctx.fill()

    // 文字
    ctx.font = `bold ${fontSize}px Consolas, Monaco, monospace`
    ctx.fillStyle = '#cdd6f4'
    ctx.textBaseline = 'middle'
    ctx.fillText(text, padding, canvas.height / 2)

    const texture = new THREE.CanvasTexture(canvas)
    texture.minFilter = THREE.LinearFilter

    const material = new THREE.SpriteMaterial({
      map: texture,
      transparent: true,
      depthTest: false
    })

    const sprite = new THREE.Sprite(material)
    // 根据文字长度调整宽度，保持高度固定
    const aspect = canvas.width / canvas.height
    const scale = 0.3
    sprite.scale.set(scale * aspect, scale, 1)
    sprite.position.set(0, 0.15, 0) // 略微偏上

    return sprite
  }

  // ---------- 可视化管理 ----------

  /** 为某个帧创建可视化对象 */
  function createFrameVisual(frameId: string, group: THREE.Group) {
    // 小坐标轴
    const axes = new THREE.AxesHelper(0.3)
    axes.name = `axes_${frameId}`
    group.add(axes)

    // 文字标签
    const label = createLabelSprite(frameId)
    label.name = `label_${frameId}`
    group.add(label)

    const visible = showTfFrames?.value ?? true
    axes.visible = visible
    label.visible = false

    frameVisuals.set(frameId, { axes, label })
  }

  /** 创建/更新父子帧之间的连线 */
  function updateConnectionLine(childId: string) {
    const parentId = parentMap.get(childId)
    if (!parentId) return

    const childGroup = frameGroups.get(childId)
    const parentGroup = frameGroups.get(parentId)
    if (!childGroup || !parentGroup) return

    const lineKey = `${parentId}->${childId}`

    // 移除旧线
    const oldLine = connectionLines.get(lineKey)
    if (oldLine) {
      scene.remove(oldLine)
      oldLine.geometry.dispose()
      ;(oldLine.material as THREE.Material).dispose()
      connectionLines.delete(lineKey)
    }

    // 获取世界坐标
    const parentPos = new THREE.Vector3()
    const childPos = new THREE.Vector3()
    parentGroup.getWorldPosition(parentPos)
    childGroup.getWorldPosition(childPos)

    // 创建虚线
    const geometry = new THREE.BufferGeometry().setFromPoints([parentPos, childPos])
    const material = new THREE.LineDashedMaterial({
      color: 0x585b70,
      dashSize: 0.1,
      gapSize: 0.05,
      transparent: true,
      opacity: 0.6
    })
    const line = new THREE.Line(geometry, material)
    line.name = `tf_line_${lineKey}`
    line.computeLineDistances()
    line.visible = showTfFrames?.value ?? true

    scene.add(line)
    connectionLines.set(lineKey, line)
  }

  // ---------- 帧管理 ----------

  /** 获取或创建帧对应的 Group */
  function getFrameGroup(frameId: string): THREE.Group {
    let group = frameGroups.get(frameId)
    if (!group) {
      group = new THREE.Group()
      group.name = `tf_frame_${frameId}`
      frameGroups.set(frameId, group)
      // 暂时直接添加到 scene，后续通过 parentMap 组织层级
      scene.add(group)
      // 创建可视化
      createFrameVisual(frameId, group)
      updateAvailableFrames()
    }
    return group
  }

  /** 应用 TF 变换到帧 Group */
  function applyTransform(transform: TFTransformStamped) {
    const { child_frame_id, header } = transform
    const { translation, rotation } = transform.transform

    // 记录父子关系
    parentMap.set(child_frame_id, header.frame_id)

    // 获取/创建子帧 Group
    const childGroup = getFrameGroup(child_frame_id)

    // 确保父帧也存在
    getFrameGroup(header.frame_id)

    // 设置变换
    childGroup.position.set(translation.x, translation.y, translation.z)
    childGroup.quaternion.set(rotation.x, rotation.y, rotation.z, rotation.w)

    // 更新连线
    updateConnectionLine(child_frame_id)
  }

  /** 处理 TF 消息 */
  function handleTFMessage(msg: TFMessage) {
    if (msg.transforms) {
      for (const transform of msg.transforms) {
        applyTransform(transform)
      }
    }
  }

  /** 更新可用帧列表 */
  function updateAvailableFrames() {
    availableFrames.value = Array.from(frameGroups.keys()).sort()
  }

  // ---------- 可见性控制 ----------

  function setVisualsVisible(visible: boolean) {
    frameVisuals.forEach(({ axes, label }) => {
      axes.visible = visible
      label.visible = visible
    })
    connectionLines.forEach((line) => {
      line.visible = visible
    })
  }

  // watch showTfFrames
  if (showTfFrames) {
    watch(showTfFrames, (val) => {
      setVisualsVisible(val)
    })
  }

  // ---------- 订阅管理 ----------

  /** 开始订阅 TF */
  function subscribe() {
    const ros = getRos()
    if (!ros) return

    // /tf - 动态变换
    tfSub = new Topic({
      ros,
      name: '/tf',
      messageType: 'tf2_msgs/TFMessage',
      throttle_rate: 33 // ~30Hz
    })
    tfSub.subscribe(handleTFMessage)

    // /tf_static - 静态变换
    tfStaticSub = new Topic({
      ros,
      name: '/tf_static',
      messageType: 'tf2_msgs/TFMessage',
      throttle_rate: 0
    })
    tfStaticSub.subscribe(handleTFMessage)

    console.log('[TF] 开始订阅 /tf 和 /tf_static')
  }

  /** 取消订阅 */
  function unsubscribe() {
    tfSub?.unsubscribe()
    tfSub = null
    tfStaticSub?.unsubscribe()
    tfStaticSub = null
    console.log('[TF] 取消订阅')
  }

  /** 清理所有帧和可视化 */
  function dispose() {
    unsubscribe()

    // 清理可视化
    frameVisuals.forEach(({ axes, label }) => {
      axes.dispose()
      ;(label.material as THREE.SpriteMaterial).map?.dispose()
      ;(label.material as THREE.SpriteMaterial).dispose()
    })
    frameVisuals.clear()

    // 清理连线
    connectionLines.forEach((line) => {
      line.geometry.dispose()
      ;(line.material as THREE.Material).dispose()
      scene.remove(line)
    })
    connectionLines.clear()

    // 清理帧 Group
    frameGroups.forEach((group) => {
      scene.remove(group)
    })
    frameGroups.clear()
    parentMap.clear()
    availableFrames.value = []
  }

  return {
    availableFrames,
    getFrameGroup,
    subscribe,
    unsubscribe,
    dispose
  }
}
