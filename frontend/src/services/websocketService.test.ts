/**
 * WebSocketService 单元测试
 *
 * 测试 WebSocket 连接管理、消息分发、自动重连和错误处理。
 */

import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { WebSocketService } from './websocketService'
import type { OptimizationAction, ProgressPayload } from '../store/scriptOptimizationSlice'

// ---------------------------------------------------------------------------
// Mock WebSocket
// ---------------------------------------------------------------------------

type WSHandler = ((event: any) => void) | null

class MockWebSocket {
  static CONNECTING = 0
  static OPEN = 1
  static CLOSING = 2
  static CLOSED = 3

  url: string
  readyState: number = MockWebSocket.CONNECTING
  onopen: WSHandler = null
  onmessage: WSHandler = null
  onerror: WSHandler = null
  onclose: WSHandler = null

  constructor(url: string) {
    this.url = url
    MockWebSocket.instances.push(this)
  }

  close(): void {
    this.readyState = MockWebSocket.CLOSED
  }

  /** Simulate the server accepting the connection. */
  simulateOpen(): void {
    this.readyState = MockWebSocket.OPEN
    this.onopen?.({} as Event)
  }

  /** Simulate receiving a message from the server. */
  simulateMessage(data: unknown): void {
    this.onmessage?.({ data: JSON.stringify(data) } as MessageEvent)
  }

  /** Simulate a raw (non-JSON) message. */
  simulateRawMessage(data: string): void {
    this.onmessage?.({ data } as MessageEvent)
  }

  /** Simulate an error followed by close. */
  simulateError(): void {
    this.onerror?.({} as Event)
    this.readyState = MockWebSocket.CLOSED
    this.onclose?.({} as CloseEvent)
  }

  /** Simulate the connection closing. */
  simulateClose(): void {
    this.readyState = MockWebSocket.CLOSED
    this.onclose?.({} as CloseEvent)
  }

  // Track all created instances for assertions
  static instances: MockWebSocket[] = []
  static reset(): void {
    MockWebSocket.instances = []
  }
}

// Install mock globally
const originalWebSocket = globalThis.WebSocket
beforeEach(() => {
  MockWebSocket.reset()
  // @ts-expect-error - replacing global WebSocket with mock
  globalThis.WebSocket = MockWebSocket as unknown as typeof WebSocket
  // Also set the static constants on the mock to match real WebSocket
  ;(globalThis.WebSocket as any).OPEN = MockWebSocket.OPEN
  ;(globalThis.WebSocket as any).CONNECTING = MockWebSocket.CONNECTING
  ;(globalThis.WebSocket as any).CLOSING = MockWebSocket.CLOSING
  ;(globalThis.WebSocket as any).CLOSED = MockWebSocket.CLOSED
})

afterEach(() => {
  globalThis.WebSocket = originalWebSocket
})

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

const TEST_URL = 'ws://localhost:8000/ws/script-optimization/session-123'
const TEST_SESSION = 'session-123'

function createDispatch(): { dispatch: React.Dispatch<OptimizationAction>; actions: OptimizationAction[] } {
  const actions: OptimizationAction[] = []
  const dispatch = (action: OptimizationAction) => { actions.push(action) }
  return { dispatch, actions }
}

function latestWs(): MockWebSocket {
  return MockWebSocket.instances[MockWebSocket.instances.length - 1]
}

function makeProgress(overrides?: Partial<ProgressPayload>): ProgressPayload {
  return {
    current_iteration: 2,
    total_iterations: 20,
    stage: 'evaluating',
    current_score: 6.5,
    message: 'Evaluating script...',
    ...overrides,
  }
}

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

describe('WebSocketService', () => {
  let service: WebSocketService

  beforeEach(() => {
    vi.useFakeTimers()
    service = new WebSocketService({
      reconnectDelay: 100,
      maxReconnectDelay: 1600,
      maxReconnectAttempts: 5,
    })
  })

  afterEach(() => {
    service.disconnect()
    vi.useRealTimers()
  })

  describe('connect', () => {
    it('creates a WebSocket with the given URL', () => {
      const { dispatch } = createDispatch()
      service.connect(TEST_URL, TEST_SESSION, dispatch)

      expect(MockWebSocket.instances).toHaveLength(1)
      expect(latestWs().url).toBe(TEST_URL)
    })

    it('isConnected is true after open', () => {
      const { dispatch } = createDispatch()
      service.connect(TEST_URL, TEST_SESSION, dispatch)
      expect(service.isConnected).toBe(false)

      latestWs().simulateOpen()
      expect(service.isConnected).toBe(true)
    })

    it('disconnects previous connection when connecting again', () => {
      const { dispatch } = createDispatch()
      service.connect(TEST_URL, TEST_SESSION, dispatch)
      const first = latestWs()
      first.simulateOpen()

      service.connect(TEST_URL, 'session-456', dispatch)
      expect(first.readyState).toBe(MockWebSocket.CLOSED)
      expect(MockWebSocket.instances).toHaveLength(2)
    })
  })

  describe('message handling', () => {
    it('dispatches UPDATE_FROM_PROGRESS on valid message', () => {
      const { dispatch, actions } = createDispatch()
      service.connect(TEST_URL, TEST_SESSION, dispatch)
      latestWs().simulateOpen()

      const progress = makeProgress()
      latestWs().simulateMessage(progress)

      expect(actions).toHaveLength(1)
      expect(actions[0]).toEqual({ type: 'UPDATE_FROM_PROGRESS', payload: progress })
    })

    it('dispatches multiple messages in order', () => {
      const { dispatch, actions } = createDispatch()
      service.connect(TEST_URL, TEST_SESSION, dispatch)
      latestWs().simulateOpen()

      latestWs().simulateMessage(makeProgress({ current_iteration: 1, stage: 'generating' }))
      latestWs().simulateMessage(makeProgress({ current_iteration: 1, stage: 'searching' }))
      latestWs().simulateMessage(makeProgress({ current_iteration: 1, stage: 'evaluating', current_score: 5.0 }))

      expect(actions).toHaveLength(3)
      expect(actions[0].type).toBe('UPDATE_FROM_PROGRESS')
      expect(actions[2].type).toBe('UPDATE_FROM_PROGRESS')
      expect((actions[2] as any).payload.current_score).toBe(5.0)
    })

    it('ignores malformed (non-JSON) messages', () => {
      const { dispatch, actions } = createDispatch()
      service.connect(TEST_URL, TEST_SESSION, dispatch)
      latestWs().simulateOpen()

      latestWs().simulateRawMessage('not json')

      expect(actions).toHaveLength(0)
    })
  })

  describe('disconnect', () => {
    it('closes the WebSocket and clears state', () => {
      const { dispatch } = createDispatch()
      service.connect(TEST_URL, TEST_SESSION, dispatch)
      latestWs().simulateOpen()

      service.disconnect()

      expect(service.isConnected).toBe(false)
    })

    it('does not dispatch after disconnect', () => {
      const { dispatch, actions } = createDispatch()
      service.connect(TEST_URL, TEST_SESSION, dispatch)
      const ws = latestWs()
      ws.simulateOpen()

      service.disconnect()

      // Simulate a late message arriving on the old socket reference
      // (handlers are nulled out, so this should be a no-op)
      ws.onmessage?.({ data: JSON.stringify(makeProgress()) } as MessageEvent)

      expect(actions).toHaveLength(0)
    })

    it('is safe to call multiple times', () => {
      const { dispatch } = createDispatch()
      service.connect(TEST_URL, TEST_SESSION, dispatch)
      service.disconnect()
      service.disconnect()
      // No error thrown
    })
  })

  describe('auto-reconnect', () => {
    it('reconnects after unexpected close', () => {
      const { dispatch } = createDispatch()
      service.connect(TEST_URL, TEST_SESSION, dispatch)
      latestWs().simulateOpen()

      // Simulate unexpected close
      latestWs().simulateClose()
      expect(MockWebSocket.instances).toHaveLength(1)

      // Advance past first reconnect delay (100ms)
      vi.advanceTimersByTime(100)
      expect(MockWebSocket.instances).toHaveLength(2)
    })

    it('uses exponential backoff for reconnect delays', () => {
      const { dispatch } = createDispatch()
      service.connect(TEST_URL, TEST_SESSION, dispatch)

      // Close immediately (before open)
      latestWs().simulateClose()

      // 1st reconnect: 100ms
      vi.advanceTimersByTime(99)
      expect(MockWebSocket.instances).toHaveLength(1)
      vi.advanceTimersByTime(1)
      expect(MockWebSocket.instances).toHaveLength(2)

      // 2nd close → 200ms delay
      latestWs().simulateClose()
      vi.advanceTimersByTime(199)
      expect(MockWebSocket.instances).toHaveLength(2)
      vi.advanceTimersByTime(1)
      expect(MockWebSocket.instances).toHaveLength(3)

      // 3rd close → 400ms delay
      latestWs().simulateClose()
      vi.advanceTimersByTime(399)
      expect(MockWebSocket.instances).toHaveLength(3)
      vi.advanceTimersByTime(1)
      expect(MockWebSocket.instances).toHaveLength(4)
    })

    it('caps reconnect delay at maxReconnectDelay', () => {
      const { dispatch } = createDispatch()
      service.connect(TEST_URL, TEST_SESSION, dispatch)

      // Exhaust attempts to reach the cap: delays are 100, 200, 400, 800, 1600
      // After attempt 4 (delay 800), attempt 5 should be capped at 1600
      for (let i = 0; i < 4; i++) {
        latestWs().simulateClose()
        vi.advanceTimersByTime(100 * Math.pow(2, i))
      }

      // Now at attempt 4, delay should be min(100*2^4=1600, 1600) = 1600
      latestWs().simulateClose()
      vi.advanceTimersByTime(1599)
      const countBefore = MockWebSocket.instances.length
      vi.advanceTimersByTime(1)
      expect(MockWebSocket.instances.length).toBe(countBefore + 1)
    })

    it('resets reconnect counter on successful open', () => {
      const { dispatch } = createDispatch()
      service.connect(TEST_URL, TEST_SESSION, dispatch)

      // Fail once
      latestWs().simulateClose()
      vi.advanceTimersByTime(100)
      expect(MockWebSocket.instances).toHaveLength(2)

      // Succeed
      latestWs().simulateOpen()

      // Fail again — delay should be back to 100ms (not 200ms)
      latestWs().simulateClose()
      vi.advanceTimersByTime(100)
      expect(MockWebSocket.instances).toHaveLength(3)
    })

    it('dispatches SET_ERROR after max reconnect attempts', () => {
      const { dispatch, actions } = createDispatch()
      service.connect(TEST_URL, TEST_SESSION, dispatch)

      // Exhaust all 5 attempts
      for (let i = 0; i < 5; i++) {
        latestWs().simulateClose()
        vi.advanceTimersByTime(100 * Math.pow(2, i))
      }

      // 6th close should trigger the error dispatch
      latestWs().simulateClose()

      const errorAction = actions.find((a) => a.type === 'SET_ERROR')
      expect(errorAction).toBeDefined()
      expect((errorAction as any).payload).toContain('最大重连次数')
    })

    it('does not reconnect after intentional disconnect', () => {
      const { dispatch } = createDispatch()
      service.connect(TEST_URL, TEST_SESSION, dispatch)
      latestWs().simulateOpen()

      service.disconnect()

      vi.advanceTimersByTime(10000)
      // Only the original connection was created
      expect(MockWebSocket.instances).toHaveLength(1)
    })

    it('cancels pending reconnect on disconnect', () => {
      const { dispatch } = createDispatch()
      service.connect(TEST_URL, TEST_SESSION, dispatch)

      // Trigger reconnect schedule
      latestWs().simulateClose()

      // Disconnect before timer fires
      service.disconnect()
      vi.advanceTimersByTime(10000)

      expect(MockWebSocket.instances).toHaveLength(1)
    })
  })

  describe('error handling', () => {
    it('reconnects after WebSocket error', () => {
      const { dispatch } = createDispatch()
      service.connect(TEST_URL, TEST_SESSION, dispatch)
      latestWs().simulateOpen()

      latestWs().simulateError()

      vi.advanceTimersByTime(100)
      expect(MockWebSocket.instances).toHaveLength(2)
    })
  })
})
