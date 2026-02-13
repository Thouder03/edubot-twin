/**
 * useTfManager - TF 坐标帧管理
 *
 * 职责:
 * 1. 订阅 /tf 和 /tf_static 话题
 * 2. 维护帧树（parent→child 关系）
 * 3. 提供 getFrameGroup(frameId) 获取 THREE.Group
 * 4. 暴露可用帧列表供设置面板选择
 */
import { ref, type Ref } from 'vue'
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

export function useTfManager(
  getRos: () => Ros | null,
  connectionStatus: Ref<RosConnectionStatus>,
  scene: THREE.Scene
) {
  const availableFrames = ref<string[]>([])

  // frameId → THREE.Group
  const frameGroups = new Map<string, THREE.Group>()

  // TF 树结构: childId → parentId
  const parentMap = new Map<string, string>()

  // 订阅句柄
  let tfSub: Topic | null = null
  let tfStaticSub: Topic | null = null

  /** 获取或创建帧对应的 Group */
  function getFrameGroup(frameId: string): THREE.Group {
    let group = frameGroups.get(frameId)
    if (!group) {
      group = new THREE.Group()
      group.name = `tf_frame_${frameId}`
      frameGroups.set(frameId, group)
      // 暂时直接添加到 scene，后续通过 parentMap 组织层级
      scene.add(group)
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

  /** 清理所有帧 */
  function dispose() {
    unsubscribe()
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
