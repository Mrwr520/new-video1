/**
 * Python 后端生命周期管理器
 *
 * 负责通过子进程启动/停止 Python FastAPI 后端，
 * 实现健康检查轮询和崩溃检测与自动重启选项。
 *
 * Requirements: 9.1, 9.2, 9.3, 9.5
 */

import { ChildProcess, spawn } from 'child_process'
import { EventEmitter } from 'events'
import http from 'http'
import path from 'path'

export type ProcessStatus = 'starting' | 'running' | 'stopped' | 'error'

export interface PythonManagerOptions {
  /** Python 解释器路径 */
  pythonPath?: string
  /** 后端服务端口 */
  backendPort?: number
  /** 后端项目目录 */
  backendDir?: string
  /** 健康检查间隔（毫秒） */
  healthCheckInterval?: number
  /** 启动超时时间（毫秒） */
  startTimeout?: number
  /** 健康检查 URL */
  healthCheckUrl?: string
}

export interface DiagnosticInfo {
  error: string
  pythonPath: string
  exitCode: number | null
  stderr: string
}

const DEFAULT_OPTIONS: Required<PythonManagerOptions> = {
  pythonPath: 'python',
  backendPort: 8000,
  backendDir: path.join(process.cwd(), '..', 'backend'),
  healthCheckInterval: 5000,
  startTimeout: 30000,
  healthCheckUrl: ''
}

export class PythonManager extends EventEmitter {
  private process: ChildProcess | null = null
  private status: ProcessStatus = 'stopped'
  private healthCheckTimer: ReturnType<typeof setInterval> | null = null
  private options: Required<PythonManagerOptions>
  private stderrBuffer: string = ''
  private consecutiveFailures: number = 0
  private readonly MAX_CONSECUTIVE_FAILURES = 3

  constructor(options: PythonManagerOptions = {}) {
    super()
    this.options = { ...DEFAULT_OPTIONS, ...options }
    // 动态构建健康检查 URL
    if (!this.options.healthCheckUrl) {
      this.options.healthCheckUrl = `http://127.0.0.1:${this.options.backendPort}/api/health`
    }
  }

  /** 获取当前进程状态 */
  getStatus(): ProcessStatus {
    return this.status
  }

  /** 是否是外部启动的后端（非本进程管理） */
  private externalBackend = false

  /** 启动 Python 后端 (Requirement 9.1)
   *
   * 先检查端口上是否已有后端在运行，如果有则直接复用（外部后端模式），
   * 避免端口冲突导致反复弹出错误对话框。
   */
  async start(): Promise<void> {
    if (this.status === 'running') {
      return
    }

    // 先检查是否已有后端在运行（可能是手动启动的或上次未正常关闭的）
    const alreadyRunning = await this.healthCheck()
    if (alreadyRunning) {
      console.log('检测到后端已在运行，直接复用')
      this.externalBackend = true
      this.setStatus('running')
      this.startHealthCheckPolling()
      return
    }

    this.externalBackend = false
    this.setStatus('starting')
    this.stderrBuffer = ''
    this.consecutiveFailures = 0

    return new Promise<void>((resolve, reject) => {
      const { pythonPath, backendPort, backendDir } = this.options
      // 防止 promise 被多次 resolve/reject
      let settled = false
      const safeResolve = (): void => {
        if (!settled) { settled = true; resolve() }
      }
      const safeReject = (err: Error): void => {
        if (!settled) { settled = true; reject(err) }
      }

      try {
        this.process = spawn(
          pythonPath,
          ['-m', 'uvicorn', 'app.main:app', '--host', '127.0.0.1', '--port', String(backendPort)],
          {
            cwd: backendDir,
            stdio: ['ignore', 'pipe', 'pipe'],
            // Windows 下使用 shell 以支持 PATH 查找
            shell: process.platform === 'win32'
          }
        )
      } catch (err) {
        const diagnostic = this.buildDiagnostic(
          err instanceof Error ? err.message : String(err),
          null
        )
        this.setStatus('error')
        this.emit('diagnostic', diagnostic)
        safeReject(new Error(`Python 后端启动失败: ${diagnostic.error}`))
        return
      }

      // 收集 stderr 用于诊断
      this.process.stderr?.on('data', (data: Buffer) => {
        this.stderrBuffer += data.toString()
      })

      this.process.stdout?.on('data', (_data: Buffer) => {
        // stdout 日志可用于调试，暂不处理
      })

      // 进程异常退出处理 (Requirement 9.5)
      this.process.on('exit', (code, signal) => {
        const wasRunning = this.status === 'running'
        this.stopHealthCheck()
        this.process = null

        if (wasRunning) {
          // 运行中崩溃，发出崩溃事件
          this.setStatus('error')
          this.emit('crash', { exitCode: code, signal })
        } else if (this.status === 'starting') {
          // 启动阶段就退出了，属于启动失败
          const diagnostic = this.buildDiagnostic(
            `进程退出，退出码: ${code}`,
            code
          )
          this.setStatus('error')
          this.emit('diagnostic', diagnostic)
          safeReject(new Error(`Python 后端启动失败: ${diagnostic.error}`))
        }
      })

      this.process.on('error', (err) => {
        this.stopHealthCheck()
        this.process = null
        const diagnostic = this.buildDiagnostic(err.message, null)
        this.setStatus('error')
        this.emit('diagnostic', diagnostic)
        safeReject(new Error(`Python 后端启动失败: ${diagnostic.error}`))
      })

      // 轮询健康检查，等待后端就绪
      const startTime = Date.now()
      const checkReady = (): void => {
        if (this.status !== 'starting') return

        if (Date.now() - startTime > this.options.startTimeout) {
          this.stop().catch(() => {})
          const diagnostic = this.buildDiagnostic('启动超时', null)
          this.setStatus('error')
          this.emit('diagnostic', diagnostic)
          safeReject(new Error(`Python 后端启动超时 (${this.options.startTimeout}ms)`))
          return
        }

        this.healthCheck()
          .then((ok) => {
            if (ok && this.status === 'starting') {
              this.setStatus('running')
              this.startHealthCheckPolling()
              safeResolve()
            } else {
              setTimeout(checkReady, 1000)
            }
          })
          .catch(() => {
            setTimeout(checkReady, 1000)
          })
      }

      // 给进程一点启动时间再开始检查
      setTimeout(checkReady, 500)
    })
  }

  /** 停止 Python 后端 (Requirement 9.2) */
  async stop(): Promise<void> {
    this.stopHealthCheck()

    // 外部后端不由我们管理，不需要杀进程
    if (this.externalBackend) {
      this.setStatus('stopped')
      return
    }

    if (!this.process) {
      this.setStatus('stopped')
      return
    }

    return new Promise<void>((resolve) => {
      const proc = this.process!

      const forceKillTimeout = setTimeout(() => {
        // 优雅关闭超时，强制终止
        try {
          if (process.platform === 'win32') {
            // Windows: 使用 taskkill 终止进程树
            spawn('taskkill', ['/pid', String(proc.pid), '/f', '/t'], { shell: true })
          } else {
            proc.kill('SIGKILL')
          }
        } catch {
          // 进程可能已退出
        }
      }, 5000)

      proc.once('exit', () => {
        clearTimeout(forceKillTimeout)
        this.process = null
        this.setStatus('stopped')
        resolve()
      })

      // 先尝试优雅关闭
      try {
        if (process.platform === 'win32') {
          // Windows 下 SIGTERM 不可靠，直接用 taskkill
          spawn('taskkill', ['/pid', String(proc.pid), '/f', '/t'], { shell: true })
        } else {
          proc.kill('SIGTERM')
        }
      } catch {
        clearTimeout(forceKillTimeout)
        this.process = null
        this.setStatus('stopped')
        resolve()
      }
    })
  }

  /** 重启 Python 后端 */
  async restart(): Promise<void> {
    await this.stop()
    await this.start()
  }

  /** 执行一次健康检查 */
  async healthCheck(): Promise<boolean> {
    return new Promise<boolean>((resolve) => {
      const url = new URL(this.options.healthCheckUrl)

      const req = http.get(
        {
          hostname: url.hostname,
          port: url.port,
          path: url.pathname,
          timeout: 3000
        },
        (res) => {
          let data = ''
          res.on('data', (chunk: Buffer) => {
            data += chunk.toString()
          })
          res.on('end', () => {
            try {
              const json = JSON.parse(data)
              resolve(json.status === 'ok')
            } catch {
              resolve(false)
            }
          })
        }
      )

      req.on('error', () => resolve(false))
      req.on('timeout', () => {
        req.destroy()
        resolve(false)
      })
    })
  }

  /** 启动健康检查轮询 (Requirement 9.5 - 崩溃检测) */
  private startHealthCheckPolling(): void {
    this.stopHealthCheck()
    this.consecutiveFailures = 0

    this.healthCheckTimer = setInterval(async () => {
      if (this.status !== 'running') return

      const ok = await this.healthCheck()
      if (ok) {
        this.consecutiveFailures = 0
      } else {
        this.consecutiveFailures++
        if (this.consecutiveFailures >= this.MAX_CONSECUTIVE_FAILURES) {
          // 连续多次健康检查失败，判定为崩溃
          this.stopHealthCheck()
          this.setStatus('error')
          this.emit('crash', { exitCode: null, signal: null })
        }
      }
    }, this.options.healthCheckInterval)
  }

  /** 停止健康检查轮询 */
  private stopHealthCheck(): void {
    if (this.healthCheckTimer) {
      clearInterval(this.healthCheckTimer)
      this.healthCheckTimer = null
    }
  }

  /** 更新状态并发出事件 */
  private setStatus(status: ProcessStatus): void {
    const prev = this.status
    this.status = status
    if (prev !== status) {
      this.emit('status-change', { from: prev, to: status })
    }
  }

  /** 构建诊断信息 (Requirement 9.3) */
  private buildDiagnostic(error: string, exitCode: number | null): DiagnosticInfo {
    return {
      error,
      pythonPath: this.options.pythonPath,
      exitCode,
      stderr: this.stderrBuffer.slice(-2000) // 保留最后 2000 字符
    }
  }
}
