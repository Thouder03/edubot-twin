// SPDX-License-Identifier: MPL-2.0
// Adapted from Lichtblick SceneExtensionConfig.ts — simplified for EduBot

import type { IRenderer } from './IRenderer'
import type { SceneExtension } from './SceneExtension'
import type { InterfaceMode } from './types'

/**
 * Configuration for how a SceneExtension is initialized and which modes it supports.
 */
export type ExtensionOverride<T extends SceneExtension = SceneExtension> = {
  /** Factory function to create the extension instance */
  init: (renderer: IRenderer) => T
  /** If defined, only include extension in these interface modes. Undefined = all modes. */
  supportedInterfaceModes?: InterfaceMode[]
}

/**
 * Registry of all SceneExtensions available to the Renderer.
 */
export type SceneExtensionConfig = {
  /** Extensions keyed by unique extensionId */
  extensionsById: Record<string, ExtensionOverride<SceneExtension>>
}

/**
 * Empty default config — consumers will register their extensions.
 */
export const DEFAULT_SCENE_EXTENSION_CONFIG: SceneExtensionConfig = {
  extensionsById: {}
}

/**
 * Create default config — consumers populate extensions externally
 * to avoid circular dependencies between extensions ↔ core.
 */
export function createDefaultSceneExtensionConfig(): SceneExtensionConfig {
  return DEFAULT_SCENE_EXTENSION_CONFIG
}
