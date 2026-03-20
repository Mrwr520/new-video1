import { useState, useCallback } from 'react'
import { useOptimization } from '../../../store/scriptOptimizationSlice'

/**
 * 优化控制面板 - 启动剧本优化流程并配置参数
 *
 * Requirements:
 *   1.1: 启动剧本优化流程
 *   8.1: 允许配置目标分数
 *   8.2: 允许配置最大迭代次数
 */
export function ControlPanel(): JSX.Element {
  const { state, startOptimization } = useOptimization()

  const [prompt, setPrompt] = useState('')
  const [targetScore, setTargetScore] = useState(8.0)
  const [maxIterations, setMaxIterations] = useState(20)
  const [starting, setStarting] = useState(false)

  const isRunning = state.status === 'running'
  const isDisabled = isRunning || starting

  const handleStart = useCallback(async () => {
    const trimmed = prompt.trim()
    if (!trimmed) return

    setStarting(true)
    try {
      await startOptimization(trimmed, targetScore, maxIterations)
    } catch {
      // Error is handled by the store (SET_ERROR)
    } finally {
      setStarting(false)
    }
  }, [prompt, targetScore, maxIterations, startOptimization])

  const statusLabel = (): string => {
    switch (state.status) {
      case 'running':
        return `迭代中 (${state.currentIteration}/${state.maxIterations}) — ${stageLabel(state.currentStage)}`
      case 'completed':
        return `优化完成 — 最终分数: ${state.currentScore?.toFixed(1) ?? '-'}`
      case 'error':
        return `错误: ${state.error ?? '未知错误'}`
      default:
        return '就绪'
    }
  }

  return (
    <div className="card" style={{ marginBottom: 16 }}>
      <h3 style={{ fontSize: '1.05rem', marginBottom: 16, color: 'var(--accent)' }}>
        剧本优化控制面板
      </h3>

      {/* 初始提示词 */}
      <div className="form-field">
        <label htmlFor="opt-prompt">初始提示词</label>
        <textarea
          id="opt-prompt"
          value={prompt}
          onChange={(e) => setPrompt(e.target.value)}
          placeholder="请输入剧本主题或初始提示词..."
          rows={4}
          disabled={isDisabled}
          aria-describedby="opt-prompt-hint"
        />
        <span id="opt-prompt-hint" style={{ fontSize: '0.75rem', color: 'var(--text-muted)' }}>
          描述你想要生成的视频剧本主题和要求
        </span>
      </div>

      {/* 参数配置 */}
      <div style={{ display: 'flex', gap: 16, flexWrap: 'wrap' }}>
        <div className="form-field" style={{ flex: 1, minWidth: 140 }}>
          <label htmlFor="opt-target-score">目标分数 (0-10)</label>
          <input
            id="opt-target-score"
            type="number"
            min={0}
            max={10}
            step={0.5}
            value={targetScore}
            onChange={(e) => setTargetScore(clamp(parseFloat(e.target.value) || 0, 0, 10))}
            disabled={isDisabled}
          />
        </div>

        <div className="form-field" style={{ flex: 1, minWidth: 140 }}>
          <label htmlFor="opt-max-iterations">最大迭代次数 (1-100)</label>
          <input
            id="opt-max-iterations"
            type="number"
            min={1}
            max={100}
            step={1}
            value={maxIterations}
            onChange={(e) => setMaxIterations(clamp(Math.round(parseFloat(e.target.value) || 1), 1, 100))}
            disabled={isDisabled}
          />
        </div>
      </div>

      {/* 状态显示 */}
      <div
        role="status"
        aria-live="polite"
        style={{
          fontSize: '0.85rem',
          color: statusColor(state.status),
          padding: '8px 12px',
          background: statusBg(state.status),
          borderRadius: 'var(--radius)',
          marginBottom: 12,
        }}
      >
        {statusLabel()}
      </div>

      {/* 启动按钮 */}
      <div className="form-actions">
        <button
          type="button"
          onClick={handleStart}
          disabled={isDisabled || !prompt.trim()}
          aria-label="启动剧本优化"
        >
          {starting ? '启动中...' : isRunning ? '优化进行中...' : '启动优化'}
        </button>
      </div>
    </div>
  )
}

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function clamp(value: number, min: number, max: number): number {
  return Math.min(max, Math.max(min, value))
}

function stageLabel(stage: string): string {
  switch (stage) {
    case 'generating': return '生成剧本'
    case 'searching': return '搜索热点/技巧'
    case 'evaluating': return '评审中'
    case 'completed': return '已完成'
    default: return stage
  }
}

function statusColor(status: string): string {
  switch (status) {
    case 'running': return 'var(--accent)'
    case 'completed': return 'var(--success)'
    case 'error': return 'var(--danger)'
    default: return 'var(--text-secondary)'
  }
}

function statusBg(status: string): string {
  switch (status) {
    case 'running': return 'var(--accent-subtle)'
    case 'completed': return 'var(--success-bg)'
    case 'error': return 'var(--danger-bg)'
    default: return 'var(--bg-secondary)'
  }
}
