/**
 * WebSocket 客户端服务 - 实时接收剧本优化进度
 *
 * 管理 WebSocket 连接，接收后端推送的迭代进度消息，
 * 通过 dispatch 更新 React Context 状态。
 * 支持自动重连（指数退避）。
 *
 * 需求：5.2, 10.4
 */

import type { Dispatch } from 'react'
import type { OptimizationAction, ProgressPayload } from '../store/scriptOptimizationSlice'

export interface WebSocketServiceOptions {
  /** Base reconnect delay in ms (default: 1000) */
  reconnectDelay?: number
  /** Maximum reconnect delay in ms (default: 30000) */
  maxReconnectDelay?: number
  /** Maximum number of reconnect attempts (default: 10) */
  maxReconnectAttempts?: number
}

const DEFAULT_OPTIONS: Required<WebSocketServiceOptions> = {
  reconnectDelay: 1000,
  maxReconnectDelay: 30000,
  maxReconnectAttempts: 10,
}

export class WebSocketService {
  private ws: WebSocket | null = null
  private dispatch: Dispatch<OptimizationAction> | null = null
  private sessionId: string | null = null
  private wsUrl: string | null = null
  private reconnectAttempts = 0
  private reconnectTimer: ReturnType<typeof setTimeout> | null = null
  private intentionalClose = false
  private options: Required<WebSocketServiceOptions>

  constructor(options?: WebSocketServiceOptions) {
    this.options = { ...DEFAULT_OPTIONS, ...options }
  }

  /**
   * Connect to the WebSocket endpoint for a given session.
   *
   * @param wsUrl - Full WebSocket URL (e.g. from apiClient.getOptimizationWsUrl)
   * @param sessionId - The optimization session ID
   * @param dispatch - React Context dispatch function
   */
  connect(
    wsUrl: string,
    sessionId: string,
    dispatch: Dispatch<OptimizationAction>,
  ): void {
    // Clean up any existing connection first
    this.disconnect()

    this.wsUrl = wsUrl
    this.sessionId = sessionId
    this.dispatch = dispatch
    this.intentionalClose = false
    this.reconnectAttempts = 0

    this._createConnection()
  }

  /** Disconnect and stop reconnecting. */
  disconnect(): void {
    this.intentionalClose = true
    this._clearReconnectTimer()

    if (this.ws) {
      this.ws.onopen = null
      this.ws.onmessage = null
      this.ws.onerror = null
      this.ws.onclose = null
      if (this.ws.readyState === WebSocket.OPEN || this.ws.readyState === WebSocket.CONNECTING) {
        this.ws.close()
      }
      this.ws = null
    }

    this.dispatch = null
    this.sessionId = null
    this.wsUrl = null
    this.reconnectAttempts = 0
  }

  /** Whether the WebSocket is currently open. */
  get isConnected(): boolean {
    return this.ws?.readyState === WebSocket.OPEN
  }

  // ---------------------------------------------------------------
  // Internal
  // ---------------------------------------------------------------

  /** @internal visible for testing */
  _createConnection(): void {
    if (!this.wsUrl) return

    try {
      this.ws = new WebSocket(this.wsUrl)
    } catch {
      this._scheduleReconnect()
      return
    }

    this.ws.onopen = this._handleOpen
    this.ws.onmessage = this._handleMessage
    this.ws.onerror = this._handleError
    this.ws.onclose = this._handleClose
  }

  private _handleOpen = (): void => {
    this.reconnectAttempts = 0
  }

  private _handleMessage = (event: MessageEvent): void => {
    if (!this.dispatch) return

    try {
      const data = JSON.parse(event.data) as ProgressPayload
      this.dispatch({ type: 'UPDATE_FROM_PROGRESS', payload: data })
    } catch {
      // Ignore malformed messages
    }
  }

  private _handleError = (): void => {
    // The close event will fire after error, reconnect is handled there.
  }

  private _handleClose = (): void => {
    this.ws = null
    if (!this.intentionalClose) {
      this._scheduleReconnect()
    }
  }

  /** @internal visible for testing */
  _scheduleReconnect(): void {
    if (this.intentionalClose) return
    if (this.reconnectAttempts >= this.options.maxReconnectAttempts) {
      // Give up and notify via dispatch
      this.dispatch?.({ type: 'SET_ERROR', payload: 'WebSocket 连接失败，已达到最大重连次数' })
      return
    }

    const delay = Math.min(
      this.options.reconnectDelay * Math.pow(2, this.reconnectAttempts),
      this.options.maxReconnectDelay,
    )
    this.reconnectAttempts++

    this.reconnectTimer = setTimeout(() => {
      this.reconnectTimer = null
      this._createConnection()
    }, delay)
  }

  private _clearReconnectTimer(): void {
    if (this.reconnectTimer !== null) {
      clearTimeout(this.reconnectTimer)
      this.reconnectTimer = null
    }
  }
}

/** Singleton instance for app-wide use. */
export const websocketService = new WebSocketService()
