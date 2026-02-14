/**
 * useDisplayManager - 可视化显示管理（预留框架）
 *
 * 职责:
 * 1. 管理已订阅的显示项（Display）列表
 * 2. 预留 LaserScan / PointCloud2 / MarkerArray 等渲染器注册接口
 * 3. 本次只实现基础框架，具体渲染器后续迭代
 */
import { ref, type Ref } from 'vue'
import * as THREE from 'three'
import type { Ros } from 'roslib'
import type { RosConnectionStatus } from './useRosConnection'

/** 显示项类型（后续扩展） */
export type DisplayType =
  | 'LaserScan'
  | 'PointCloud2'
  | 'MarkerArray'
  | 'RobotModel'
  | 'Path'
  | 'Odometry'

/** 显示项实例 */
export interface DisplayEntry {
  id: string
  type: DisplayType
  topicName: string
  enabled: boolean
  /** 渲染器创建的 Three.js 对象 */
  sceneObject?: THREE.Object3D
}

export function useDisplayManager(
  _getRos: () => Ros | null,
  _connectionStatus: Ref<RosConnectionStatus>,
  scene: THREE.Scene
) {
  const displays = ref<DisplayEntry[]>([])

  /** 添加显示项（预留接口） */
  function addDisplay(type: DisplayType, topicName: string): string {
    const id = `display_${Date.now()}_${Math.random().toString(36).slice(2, 6)}`
    displays.value.push({
      id,
      type,
      topicName,
      enabled: true
    })
    // TODO: 根据 type 创建对应渲染器并订阅 topic
    console.log(`[Display] 添加显示项: ${type} @ ${topicName}`)
    return id
  }

  /** 移除显示项 */
  function removeDisplay(id: string) {
    const idx = displays.value.findIndex((d) => d.id === id)
    if (idx !== -1) {
      const entry = displays.value[idx]
      if (entry.sceneObject) {
        scene.remove(entry.sceneObject)
      }
      displays.value.splice(idx, 1)
    }
  }

  /** 切换显示项可见性 */
  function toggleDisplay(id: string, enabled: boolean) {
    const entry = displays.value.find((d) => d.id === id)
    if (entry) {
      entry.enabled = enabled
      if (entry.sceneObject) {
        entry.sceneObject.visible = enabled
      }
    }
  }

  /** 清理所有显示项 */
  function dispose() {
    for (const entry of displays.value) {
      if (entry.sceneObject) {
        scene.remove(entry.sceneObject)
      }
    }
    displays.value = []
  }

  return {
    displays,
    addDisplay,
    removeDisplay,
    toggleDisplay,
    dispose
  }
}
