/**
 * 本模块为 @lichtblick/* 包的兼容 shim。
 * 将 Lichtblick 专有的类型和工具替换为本地等效实现，
 * 使得从 Lichtblick 移植的源代码无需安装 @lichtblick 生态依赖。
 */

// ============= @lichtblick/suite 类型 =============

/** 不可变包装类型 */
export type Immutable<T> = Readonly<T>

/** 消息事件 */
export interface MessageEvent<T = unknown> {
  topic: string
  receiveTime: { sec: number; nsec: number }
  message: T
  sizeInBytes: number
  schemaName: string
}

/** 话题定义 */
export interface Topic {
  name: string
  schemaName: string
}

/** 参数值 */
export type ParameterValue = string | number | boolean | undefined

/** 变量值 */
export type VariableValue = string | number | boolean | string[] | number[] | boolean[] | undefined

/** 设置树图标 */
export type SettingsIcon =
  | 'Cube'
  | 'Grid'
  | 'Map'
  | 'Walk'
  | 'Settings'
  | 'Eye'
  | 'EyeOff'
  | 'Camera'
  | string

/** 设置树 Action */
export type SettingsTreeAction =
  | {
      action: 'update'
      payload: {
        path: readonly string[]
        value?: unknown
        input?: string
      }
    }
  | {
      action: 'perform-node-action'
      payload: {
        id: string
        path?: readonly string[]
      }
    }

/** 设置树字段 */
export interface SettingsTreeField {
  label: string
  input: string
  value?: unknown
  help?: string
  error?: string
  placeholder?: string
  disabled?: boolean
  readonly?: boolean
  min?: number
  max?: number
  step?: number
  precision?: number
  options?: Array<{ label: string; value: unknown }>
  labels?: string[]
  tooltip?: string
}

export type SettingsTreeFields = Record<string, SettingsTreeField | undefined>

/** 设置树节点 */
export interface SettingsTreeNode {
  label?: string
  icon?: SettingsIcon
  fields?: SettingsTreeFields
  children?: SettingsTreeNodes
  actions?: SettingsTreeNodeActionItem[]
  defaultExpansionState?: 'collapsed' | 'expanded'
  visible?: boolean
  error?: string
  order?: number
  renamable?: boolean
  enableVisibilityFilter?: boolean
  handler?: (action: SettingsTreeAction) => void
}

export type SettingsTreeNodes = Record<string, SettingsTreeNode | undefined>
export type SettingsTreeChildren = SettingsTreeNodes

export interface SettingsTreeNodeActionItem {
  type: 'action'
  id: string
  label: string
  icon?: SettingsIcon
}

// ============= @lichtblick/log =============

export class Logger {
  private prefix: string
  constructor(prefix: string) {
    this.prefix = prefix
  }
  debug(...args: unknown[]) {
    console.debug(`[${this.prefix}]`, ...args)
  }
  info(...args: unknown[]) {
    console.info(`[${this.prefix}]`, ...args)
  }
  warn(...args: unknown[]) {
    console.warn(`[${this.prefix}]`, ...args)
  }
  error(...args: unknown[]) {
    console.error(`[${this.prefix}]`, ...args)
  }

  static getLogger(name: string): Logger {
    return new Logger(name)
  }
}

// ============= @lichtblick/den =============

/** 简单对象池 */
export class ObjectPool<T> {
  #create: () => T
  #pool: T[] = []
  #maxCapacity: number

  constructor(create: () => T, options?: { maxCapacity?: number }) {
    this.#create = create
    this.#maxCapacity = options?.maxCapacity ?? 1000
  }

  acquire(): T {
    return this.#pool.pop() ?? this.#create()
  }

  release(item: T): void {
    if (this.#pool.length < this.#maxCapacity) {
      this.#pool.push(item)
    }
  }

  clear(): void {
    this.#pool.length = 0
  }
}

/** CameraModelsMap placeholder */
export type CameraModelsMap = Map<string, unknown>

/**
 * ArrayMap - a list of values sorted by numeric keys (number or BigInt).
 * Keys are unique. Binary search for O(log n) lookups.
 * Ported from @lichtblick/den/collection/ArrayMap.
 */
export class ArrayMap<K, V> {
  #list: [K, V][] = []

  get size(): number {
    return this.#list.length
  }

  clear(): [K, V][] {
    return this.#list.splice(0)
  }

  [Symbol.iterator](): IterableIterator<[K, V]> {
    return this.#list[Symbol.iterator]()
  }

  at(index: number): [K, V] | undefined {
    return this.#list[index]
  }

  set(key: K, value: V): V | undefined {
    const index = this.binarySearch(key)
    if (index >= 0) {
      const existingEntry = this.#list[index]![1]
      this.#list[index]![1] = value
      return existingEntry
    } else {
      const newEntry: [K, V] = [key, value]
      const greaterThanIndex = ~index
      if (greaterThanIndex >= this.#list.length) {
        this.#list.push(newEntry)
      } else {
        this.#list.splice(greaterThanIndex, 0, newEntry)
      }
    }
    return undefined
  }

  shift(): [K, V] | undefined {
    return this.#list.shift()
  }

  pop(): [K, V] | undefined {
    return this.#list.pop()
  }

  remove(key: K): [K, V] | undefined {
    const index = this.binarySearch(key)
    if (index >= 0) {
      return this.#list.splice(index, 1)[0]
    }
    return undefined
  }

  removeAfter(key: K): [K, V][] {
    const index = this.binarySearch(key)
    const greaterThanIndex = index >= 0 ? index + 1 : ~index
    return this.#list.splice(greaterThanIndex)
  }

  removeBefore(key: K): [K, V][] {
    const index = this.binarySearch(key)
    const lessThanIndex = index >= 0 ? index : ~index
    return this.#list.splice(0, lessThanIndex)
  }

  minEntry(): [K, V] | undefined {
    return this.#list[0]
  }

  maxEntry(): [K, V] | undefined {
    return this.#list[this.#list.length - 1]
  }

  minKey(): K | undefined {
    return this.#list[0]?.[0]
  }

  maxKey(): K | undefined {
    return this.#list[this.#list.length - 1]?.[0]
  }

  binarySearch(key: K): number {
    const list = this.#list
    if (list.length === 0) return -1

    let left = 0
    let right = list.length - 1

    if (key < list[left]![0]) return ~left
    else if (key > list[right]![0]) return ~(right + 1)

    while (left <= right) {
      const mid = (left + right) >> 1
      const midKey = list[mid]![0]
      if (midKey === key) return mid
      else if (key < midKey) right = mid - 1
      else left = mid + 1
    }
    return ~left
  }
}

// ============= @lichtblick/rostime =============

export interface RosTime {
  sec: number
  nsec: number
}

/** Time alias used by normalizeMessages and ros modules */
export type Time = RosTime

export function toNanoSec(time: RosTime): bigint {
  return BigInt(time.sec) * 1_000_000_000n + BigInt(time.nsec)
}

export function fromNanoSec(nsec: bigint): RosTime {
  const sec = Number(nsec / 1_000_000_000n)
  const nsecRemainder = Number(nsec % 1_000_000_000n)
  return { sec, nsec: nsecRemainder }
}

export function isLessThan(a: RosTime, b: RosTime): boolean {
  if (a.sec < b.sec) return true
  if (a.sec > b.sec) return false
  return a.nsec < b.nsec
}

// ============= @lichtblick/three-text (stub) =============

import * as THREE from 'three'

/**
 * Label - 简化版文字标签（CSS2DObject 替代 @lichtblick/three-text Label）
 */
export class Label extends THREE.Object3D {
  public text = ''
  public fontSize = 12
  public color = 0xffffff
  public backgroundColor = 0x000000

  constructor() {
    super()
  }

  public setText(text: string): void {
    this.text = text
  }

  public setColor(r: number, g: number, b: number, _a = 1): void {
    this.color = new THREE.Color(r, g, b).getHex()
  }

  public setBackgroundColor(r: number, g: number, b: number, _a = 1): void {
    this.backgroundColor = new THREE.Color(r, g, b).getHex()
  }

  public setLineHeight(height: number): void {
    this.fontSize = height
  }

  public setAnchorPoint(x: number, y: number): void {
    void x
    void y
  }

  public setBillboard(value: boolean): void {
    void value
  }

  public setOpacity(_value: number): void {
    // noop
  }

  dispose(): void {
    // noop
  }
}

export class LabelPool {
  public scaleFactor = 1

  acquire(): Label {
    return new Label()
  }

  release(_label: Label): void {
    // noop
  }

  setScaleFactor(factor: number): void {
    this.scaleFactor = factor
  }

  dispose(): void {
    // noop
  }
}

export class LabelMaterial extends THREE.ShaderMaterial {
  // stub
}

// ============= @lichtblick/suite-base stubs =============

/** PanelContextMenuItem */
export interface PanelContextMenuItem {
  id: string
  label: string
  handler: () => void
}

/** DraggedMessagePath */
export interface DraggedMessagePath {
  path: string
  rootSchemaName: string
  isTopic: boolean
  isLeaf: boolean
  topicName: string
}

/** MessagePathDropStatus */
export interface MessagePathDropStatus {
  canDrop: boolean
  effect?: 'add' | 'replace'
}

/** Asset */
export interface Asset {
  uri: string
  data: Uint8Array
  mediaType?: string
}

/** BuiltinPanelExtensionContext stubs */
export interface BuiltinPanelExtensionContext {
  unstable_fetchAsset: (
    uri: string,
    options?: { signal?: AbortSignal; baseUrl?: string }
  ) => Promise<Asset>
}

/** ForwardedAnalytics */
export type ForwardedAnalytics = unknown

/** IAnalytics stub */
export interface IAnalytics {
  logEvent(args: Record<string, unknown>): void
}

/** ICameraHandler */
export interface ICameraHandler {
  getActiveCamera(): THREE.PerspectiveCamera | THREE.OrthographicCamera
  handleResize(width: number, height: number, resolution: number): void
  updateSettingsTree(): void
}

/** RosValue — use interface to avoid circular type alias */
export type RosValueArray = ReadonlyArray<RosValue>
export interface RosValueRecord {
  readonly [key: string]: RosValue
}
export type RosValue = string | number | boolean | undefined | RosValueArray | RosValueRecord

/** HUDItem */
export interface HUDItem {
  id: string
  getMessage: () => string
  displayType: 'empty' | 'warning' | 'info' | 'error' | 'calibration' | 'background'
  openSettings?: boolean
}

/** HUDItemManager stub */
export class HUDItemManager {
  #onChange: (() => void) | undefined

  constructor(onChange?: () => void) {
    this.#onChange = onChange
  }

  displayWarning(id: string, getMessage: () => string): void {
    void id
    void getMessage
    this.#onChange?.()
  }

  displayInfo(id: string, getMessage: () => string): void {
    void id
    void getMessage
    this.#onChange?.()
  }

  removeAll(): void {
    this.#onChange?.()
  }

  clear(): void {
    this.removeAll()
  }

  getHUDItems(): HUDItem[] {
    return []
  }
}

/** MarkerPool stub */
export class MarkerPool {
  dispose(): void {
    // noop
  }
}

// ============= @lichtblick/theme stubs =============

export const palette = {
  light: {
    background: {
      default: '#ffffff'
    }
  },
  dark: {
    background: {
      default: '#1a1a1a'
    }
  }
}

export const fontMonospace = '"Roboto Mono", monospace'

// ============= react-null stub =============
// ReactNull is a null typed as any, used by Lichtblick to satisfy React-expecting APIs
export const ReactNull = null as any
