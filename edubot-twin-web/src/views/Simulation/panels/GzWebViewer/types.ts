/**
 * GzWeb postMessage 通信协议类型定义
 *
 * L1: Vue → iframe 指令
 * L2: iframe → Vue 事件
 */

// ════════════════════════════════════════════
// L1: Vue → iframe 指令类型
// ════════════════════════════════════════════

export interface GzPauseCommand {
  type: 'gz:pause'
  payload: { paused: boolean }
}

export interface GzResetCommand {
  type: 'gz:reset'
  payload: { resetType: 'world' | 'model' }
}

export interface GzResetViewCommand {
  type: 'gz:resetView'
  payload: Record<string, never>
}

export interface GzShowGridCommand {
  type: 'gz:showGrid'
  payload: { visible: boolean }
}

export interface GzShowCollisionsCommand {
  type: 'gz:showCollisions'
  payload: { visible: boolean }
}

export interface GzShowOrbitIndicatorCommand {
  type: 'gz:showOrbitIndicator'
  payload: { visible: boolean }
}

export interface GzPingCommand {
  type: 'gz:ping'
  payload: Record<string, never>
}

/** 所有 Vue → iframe 指令的联合类型 */
export type GzCommand =
  | GzPauseCommand
  | GzResetCommand
  | GzResetViewCommand
  | GzShowGridCommand
  | GzShowCollisionsCommand
  | GzShowOrbitIndicatorCommand
  | GzPingCommand

// ════════════════════════════════════════════
// L2: iframe → Vue 事件类型
// ════════════════════════════════════════════

export interface GzReadyEvent {
  type: 'gz:ready'
  payload: Record<string, never>
}

export interface GzConnectionEvent {
  type: 'gz:connection'
  payload: { connected: boolean }
}

export interface GzSimTimeEvent {
  type: 'gz:simTime'
  payload: { simTime: string }
}

export interface GzRealTimeEvent {
  type: 'gz:realTime'
  payload: { realTime: string }
}

export interface GzPausedEvent {
  type: 'gz:paused'
  payload: { paused: boolean }
}

export interface GzPongEvent {
  type: 'gz:pong'
  payload: { connected: boolean; timestamp: number }
}

/** 所有 iframe → Vue 事件的联合类型 */
export type GzEvent =
  | GzReadyEvent
  | GzConnectionEvent
  | GzSimTimeEvent
  | GzRealTimeEvent
  | GzPausedEvent
  | GzPongEvent

// ════════════════════════════════════════════
// 状态类型
// ════════════════════════════════════════════

/** 连接状态机状态 */
export type GzConnectionStatus = 'disconnected' | 'connecting' | 'connected' | 'error'
