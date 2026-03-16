/**
 * roslib 最小类型声明
 *
 * roslib (v1.x ESM) 使用命名导出，这里补充项目中用到的 API 的类型。
 */
declare module 'roslib' {
  import { EventEmitter } from 'eventemitter3'

  export interface RosOptions {
    url?: string
  }

  export class Ros extends EventEmitter {
    constructor(options?: RosOptions)
    connect(url: string): void
    close(): void
    on(event: 'connection', callback: () => void): this
    on(event: 'close', callback: () => void): this
    on(event: 'error', callback: (error: Error) => void): this
    isConnected: boolean
  }

  export interface TopicOptions {
    ros: Ros
    name: string
    messageType: string
    /** 节流间隔（ms），减少高频话题的回调频率 */
    throttle_rate?: number
    /** 队列长度 */
    queue_length?: number
    /** 队列大小 */
    queue_size?: number
  }

  export class Topic<T = any> extends EventEmitter {
    constructor(options: TopicOptions)
    subscribe(callback: (message: T) => void): void
    unsubscribe(callback?: (message: T) => void): void
    advertise(): void
    unadvertise(): void
    publish(message: T | Record<string, unknown>): void
    name: string
    messageType: string
  }
}
