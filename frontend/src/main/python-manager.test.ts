/**
 * PythonManager 单元测试
 *
 * 测试 Python 后端生命周期管理的核心逻辑：
 * - 启动/停止/重启流程
 * - 健康检查机制
 * - 崩溃检测与诊断信息
 */

import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { EventEmitter } from 'events'
import { PythonManager, type ProcessStatus } from './python-manager'

// --- Mock child_process ---
const mockProcess = {
  pid: 12345,
  stdout: new EventEmitter(),
  stderr: new EventEmitter(),
  kill: vi.fn(),
  once: vi.fn(),
  on: vi.fn()
}

// 让 mockProcess 支持多个 event listener
function createMockChildProcess() {
  const emitter = new EventEmitter()
  return Object.assign(emitter, {
    pid: 12345,
    stdout: new EventEmitter(),
    stderr: new EventEmitter(),
    kill: vi.fn()
  })
}

let spawnMock: ReturnType<typeof vi.fn>
let currentMockProc: ReturnType<typeof createMockChildProcess>

vi.mock('child_process', () => ({
  spawn: (...args: unknown[]) => spawnMock(...args)
}))

// --- Mock http ---
let httpGetHandler: ((url: unknown, cb: (res: EventEmitter) => void) => EventEmitter) | null = null

vi.mock('http', () => ({
  default: {
    get: (...args: unknown[]) => {
      if (httpGetHandler) {
        return httpGetHandler(args[0], args[1] as (res: EventEmitter) => void)
      }
      const req = new EventEmitter()
      ;(req as any).destroy = vi.fn()
      setTimeout(() => req.emit('error', new Error('no handler')), 0)
      return req
    }
  }
}))

// 模拟健康检查成功
function mockHealthCheckSuccess() {
  httpGetHandler = (_url, cb) => {
    const res = new EventEmitter()
    setTimeout(() => {
      cb(res)
      res.emit('data', Buffer.from('{"status":"ok"}'))
      res.emit('end')
    }, 10)
    const req = new EventEmitter()
    ;(req as any).destroy = vi.fn()
    return req as any
  }
}

// 模拟健康检查失败
function mockHealthCheckFailure() {
  httpGetHandler = (_url, _cb) => {
    const req = new EventEmitter()
    ;(req as any).destroy = vi.fn()
    setTimeout(() => req.emit('error', new Error('ECONNREFUSED')), 10)
    return req as any
  }
}

describe('PythonManager', () => {
  let manager: PythonManager

  beforeEach(() => {
    vi.useFakeTimers({ shouldAdvanceTime: true })
    currentMockProc = createMockChildProcess()
    spawnMock = vi.fn().mockReturnValue(currentMockProc)
    httpGetHandler = null

    manager = new PythonManager({
      pythonPath: 'python',
      backendPort: 8000,
      backendDir: '/test/backend',
      healthCheckInterval: 1000,
      startTimeout: 5000
    })
  })

  afterEach(async () => {
    httpGetHandler = null
    vi.useRealTimers()
  })

  describe('getStatus', () => {
    it('初始状态应为 stopped', () => {
      expect(manager.getStatus()).toBe('stopped')
    })
  })

  describe('start', () => {
    it('应使用正确的参数启动 Python 子进程', async () => {
      mockHealthCheckSuccess()

      const startPromise = manager.start()
      // 推进时间让健康检查执行
      await vi.advanceTimersByTimeAsync(2000)
      await startPromise

      expect(spawnMock).toHaveBeenCalledWith(
        'python',
        ['-m', 'uvicorn', 'app.main:app', '--host', '127.0.0.1', '--port', '8000'],
        expect.objectContaining({
          cwd: '/test/backend',
          stdio: ['ignore', 'pipe', 'pipe']
        })
      )
    })

    it('启动成功后状态应为 running', async () => {
      mockHealthCheckSuccess()

      const startPromise = manager.start()
      await vi.advanceTimersByTimeAsync(2000)
      await startPromise

      expect(manager.getStatus()).toBe('running')
    })

    it('如果已经在运行，应直接返回', async () => {
      mockHealthCheckSuccess()

      const startPromise = manager.start()
      await vi.advanceTimersByTimeAsync(2000)
      await startPromise

      // 第二次调用应直接返回
      await manager.start()
      expect(spawnMock).toHaveBeenCalledTimes(1)
    })

    it('启动超时应设置 error 状态并发出诊断事件', async () => {
      mockHealthCheckFailure()

      const diagnosticHandler = vi.fn()
      manager.on('diagnostic', diagnosticHandler)

      const startPromise = manager.start().catch((e: Error) => e)
      // 推进到超时
      await vi.advanceTimersByTimeAsync(6000)

      const result = await startPromise
      expect(result).toBeInstanceOf(Error)
      expect((result as Error).message).toContain('启动超时')
      expect(manager.getStatus()).toBe('error')
      expect(diagnosticHandler).toHaveBeenCalled()

      // 清理：让 stop 内部的 forceKill 和进程退出完成
      await vi.advanceTimersByTimeAsync(6000)
      currentMockProc.emit('exit', 0, null)
      await vi.advanceTimersByTimeAsync(100)
    })

    it('进程启动阶段退出应发出诊断事件', async () => {
      mockHealthCheckFailure()

      const diagnosticHandler = vi.fn()
      manager.on('diagnostic', diagnosticHandler)

      const startPromise = manager.start()

      // 模拟进程在启动阶段退出
      await vi.advanceTimersByTimeAsync(100)
      currentMockProc.emit('exit', 1, null)

      await expect(startPromise).rejects.toThrow('启动失败')
      expect(manager.getStatus()).toBe('error')
      expect(diagnosticHandler).toHaveBeenCalledWith(
        expect.objectContaining({
          exitCode: 1,
          pythonPath: 'python'
        })
      )
    })

    it('spawn 出错应发出诊断事件', async () => {
      const diagnosticHandler = vi.fn()
      manager.on('diagnostic', diagnosticHandler)

      const startPromise = manager.start()

      await vi.advanceTimersByTimeAsync(100)
      currentMockProc.emit('error', new Error('spawn ENOENT'))

      await expect(startPromise).rejects.toThrow('启动失败')
      expect(manager.getStatus()).toBe('error')
      expect(diagnosticHandler).toHaveBeenCalledWith(
        expect.objectContaining({
          error: 'spawn ENOENT'
        })
      )
    })
  })

  describe('stop', () => {
    it('停止后状态应为 stopped', async () => {
      mockHealthCheckSuccess()

      const startPromise = manager.start()
      await vi.advanceTimersByTimeAsync(2000)
      await startPromise

      // 模拟进程退出
      const stopPromise = manager.stop()
      await vi.advanceTimersByTimeAsync(100)
      currentMockProc.emit('exit', 0, null)
      await stopPromise

      expect(manager.getStatus()).toBe('stopped')
    })

    it('没有运行的进程时应直接设为 stopped', async () => {
      await manager.stop()
      expect(manager.getStatus()).toBe('stopped')
    })
  })

  describe('restart', () => {
    it('应先停止再启动', async () => {
      mockHealthCheckSuccess()

      // 先启动
      const startPromise = manager.start()
      await vi.advanceTimersByTimeAsync(2000)
      await startPromise

      // 重启：需要模拟 stop 的进程退出
      const restartPromise = manager.restart()
      await vi.advanceTimersByTimeAsync(100)
      currentMockProc.emit('exit', 0, null)

      // 新进程的健康检查
      await vi.advanceTimersByTimeAsync(2000)
      await restartPromise

      expect(manager.getStatus()).toBe('running')
      // spawn 被调用：初始启动 + taskkill(Windows stop) + 重启 = 3 次
      // 在 Windows 上 stop 会调用 taskkill，也是一次 spawn
      const uvicornCalls = spawnMock.mock.calls.filter(
        (call: unknown[]) => Array.isArray(call[1]) && call[1].includes('app.main:app')
      )
      expect(uvicornCalls).toHaveLength(2)
    })
  })

  describe('healthCheck', () => {
    it('后端返回 ok 时应返回 true', async () => {
      mockHealthCheckSuccess()
      const result = await manager.healthCheck()
      expect(result).toBe(true)
    })

    it('连接失败时应返回 false', async () => {
      mockHealthCheckFailure()
      const result = await manager.healthCheck()
      expect(result).toBe(false)
    })

    it('返回非 ok 状态时应返回 false', async () => {
      httpGetHandler = (_url, cb) => {
        const res = new EventEmitter()
        setTimeout(() => {
          cb(res)
          res.emit('data', Buffer.from('{"status":"error"}'))
          res.emit('end')
        }, 10)
        const req = new EventEmitter()
        ;(req as any).destroy = vi.fn()
        return req as any
      }

      const result = await manager.healthCheck()
      expect(result).toBe(false)
    })

    it('返回无效 JSON 时应返回 false', async () => {
      httpGetHandler = (_url, cb) => {
        const res = new EventEmitter()
        setTimeout(() => {
          cb(res)
          res.emit('data', Buffer.from('not json'))
          res.emit('end')
        }, 10)
        const req = new EventEmitter()
        ;(req as any).destroy = vi.fn()
        return req as any
      }

      const result = await manager.healthCheck()
      expect(result).toBe(false)
    })
  })

  describe('崩溃检测 (Requirement 9.5)', () => {
    it('运行中进程退出应发出 crash 事件', async () => {
      mockHealthCheckSuccess()

      const startPromise = manager.start()
      await vi.advanceTimersByTimeAsync(2000)
      await startPromise

      const crashHandler = vi.fn()
      manager.on('crash', crashHandler)

      // 模拟进程崩溃
      currentMockProc.emit('exit', 1, null)

      expect(crashHandler).toHaveBeenCalledWith({ exitCode: 1, signal: null })
      expect(manager.getStatus()).toBe('error')
    })

    it('连续健康检查失败应发出 crash 事件', async () => {
      mockHealthCheckSuccess()

      const startPromise = manager.start()
      await vi.advanceTimersByTimeAsync(2000)
      await startPromise

      // 切换到健康检查失败
      mockHealthCheckFailure()

      const crashHandler = vi.fn()
      manager.on('crash', crashHandler)

      // 推进时间触发 3 次健康检查失败
      await vi.advanceTimersByTimeAsync(4000)

      expect(crashHandler).toHaveBeenCalled()
      expect(manager.getStatus()).toBe('error')
    })
  })

  describe('状态变更事件', () => {
    it('应在状态变更时发出 status-change 事件', async () => {
      mockHealthCheckSuccess()

      const statusChanges: { from: ProcessStatus; to: ProcessStatus }[] = []
      manager.on('status-change', (change) => statusChanges.push(change))

      const startPromise = manager.start()
      await vi.advanceTimersByTimeAsync(2000)
      await startPromise

      expect(statusChanges).toContainEqual({ from: 'stopped', to: 'starting' })
      expect(statusChanges).toContainEqual({ from: 'starting', to: 'running' })
    })
  })

  describe('stderr 诊断信息收集', () => {
    it('应收集 stderr 输出用于诊断', async () => {
      mockHealthCheckFailure()

      const diagnosticHandler = vi.fn()
      manager.on('diagnostic', diagnosticHandler)

      const startPromise = manager.start()

      // 模拟 stderr 输出
      await vi.advanceTimersByTimeAsync(100)
      currentMockProc.stderr.emit('data', Buffer.from('ModuleNotFoundError: No module named uvicorn'))
      currentMockProc.emit('exit', 1, null)

      await expect(startPromise).rejects.toThrow()

      expect(diagnosticHandler).toHaveBeenCalledWith(
        expect.objectContaining({
          stderr: expect.stringContaining('ModuleNotFoundError')
        })
      )
    })
  })
})
