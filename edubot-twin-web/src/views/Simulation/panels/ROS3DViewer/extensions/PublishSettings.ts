// SPDX-License-Identifier: MPL-2.0
// PublishSettings — 在设置面板中展示发布配置节点

import * as _ from 'lodash-es'

import { SettingsTreeAction } from '../core/lichtblick-shim'
import type { IRenderer } from '../core/IRenderer'
import { SceneExtension } from '../core/SceneExtension'
import type { SettingsTreeEntry } from '../core/SettingsManager'
import type { PublishClickType } from './PublishClickTool'

// ============================================================
// 默认值
// ============================================================

export const DEFAULT_PUBLISH_SETTINGS = {
  type: 'point' as PublishClickType,
  poseTopic: '/move_base_simple/goal',
  pointTopic: '/clicked_point',
  poseEstimateTopic: '/initialpose',
  poseEstimateXDeviation: 0.5,
  poseEstimateYDeviation: 0.5,
  poseEstimateThetaDeviation: _.round(Math.PI / 12, 8)
}

// ============================================================
// PublishSettings — SceneExtension 主类
// ============================================================

export class PublishSettings extends SceneExtension {
  public static extensionId = 'foxglove.PublishSettings'

  public constructor(renderer: IRenderer, name: string = PublishSettings.extensionId) {
    super(name, renderer)
    renderer.publishClickTool.addEventListener(
      'foxglove.publish-type-change',
      this.#handlePublishToolChange
    )
  }

  public override dispose(): void {
    this.renderer.publishClickTool.removeEventListener(
      'foxglove.publish-type-change',
      this.#handlePublishToolChange
    )
    super.dispose()
  }

  // --- 设置树节点 ---

  public override settingsNodes(): SettingsTreeEntry[] {
    const publish = this.renderer.config.publish ?? DEFAULT_PUBLISH_SETTINGS

    const topicValue: Record<string, string> = {
      point: publish.pointTopic,
      pose: publish.poseTopic,
      pose_estimate: publish.poseEstimateTopic
    }

    return [
      {
        path: ['publish'],
        node: {
          label: '点击发布',
          defaultExpansionState: 'collapsed',
          fields: {
            type: {
              label: '类型',
              input: 'select',
              value: publish.type,
              options: [
                { label: '点 (PointStamped)', value: 'point' },
                { label: '位姿 (PoseStamped)', value: 'pose' },
                { label: '初始位姿估计', value: 'pose_estimate' }
              ],
              help: '在 3D 视图中点击时发布的消息类型'
            },
            topic: {
              label: 'Topic',
              input: 'string',
              value: topicValue[publish.type] ?? publish.pointTopic,
              help: '将要发布到的 ROS Topic 名称'
            },
            ...(publish.type === 'pose_estimate' && {
              poseEstimateXDeviation: {
                label: 'X 偏差 (σ)',
                input: 'number',
                min: 0,
                step: 0.1,
                precision: 4,
                value: publish.poseEstimateXDeviation
              },
              poseEstimateYDeviation: {
                label: 'Y 偏差 (σ)',
                input: 'number',
                min: 0,
                step: 0.1,
                precision: 4,
                value: publish.poseEstimateYDeviation
              },
              poseEstimateThetaDeviation: {
                label: 'θ 偏差 (σ)',
                input: 'number',
                min: 0,
                step: 0.05,
                precision: 6,
                value: publish.poseEstimateThetaDeviation
              }
            })
          },
          handler: this.handleSettingsAction
        }
      }
    ]
  }

  // --- 设置操作处理 ---

  public override handleSettingsAction = (action: SettingsTreeAction): void => {
    if (action.action !== 'update' || !action.payload.path?.length) return

    const path = action.payload.path
    const value = action.payload.value

    if (path[0] !== 'publish') return

    if (path[1] === 'type') {
      // 切换类型 → 通知 PublishClickTool（它会 dispatchEvent publish-type-change → 本扩展刷新树）
      const newType = value as PublishClickType
      if (this.renderer.publishClickTool.publishClickType !== newType) {
        this.renderer.publishClickTool.setPublishClickType(newType)
        this.renderer.publishClickTool.stop()
      }
    } else if (path[1] === 'topic') {
      // 更新对应 type 的 topic
      this.renderer.updateConfig((draft) => {
        const pub = (draft.publish ??= { ...DEFAULT_PUBLISH_SETTINGS })
        const topicStr = (value as string | undefined) ?? ''
        switch (pub.type) {
          case 'point':
            pub.pointTopic = topicStr || DEFAULT_PUBLISH_SETTINGS.pointTopic
            break
          case 'pose':
            pub.poseTopic = topicStr || DEFAULT_PUBLISH_SETTINGS.poseTopic
            break
          case 'pose_estimate':
            pub.poseEstimateTopic = topicStr || DEFAULT_PUBLISH_SETTINGS.poseEstimateTopic
            break
        }
      })
    } else {
      this.renderer.updateConfig((draft) => _.set(draft, path, value))
    }

    this.updateSettingsTree()
  }

  // --- 内部事件处理 ---

  #handlePublishToolChange = (): void => {
    this.renderer.updateConfig((draft) => {
      const pub = (draft.publish ??= { ...DEFAULT_PUBLISH_SETTINGS })
      pub.type = this.renderer.publishClickTool.publishClickType
    })
    this.updateSettingsTree()
  }
}
