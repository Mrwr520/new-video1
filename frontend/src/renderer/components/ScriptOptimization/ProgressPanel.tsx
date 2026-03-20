import { useOptimization } from '../../../store/scriptOptimizationSlice'

/**
 * 进度面板 - 显示迭代优化的实时进度
 *
 * Requirements:
 *   5.2: 实时更新迭代次数、当前分数
 */
export function ProgressPanel(): JSX.Element | null {
  const { state } = useOptimization()

  if (state.status !== 'running' && state.status !== 'completed') {
    return null
  }

  const progress =
    state.maxIterations > 0
      ? (state.currentIteration / state.maxIterations) * 100
      : 0

  return (
    <div className="card" style={{ marginBottom: 16 }}>
      <h3 style={{ fontSize: '1.05rem', marginBottom: 16, color: 'var(--accent)' }}>
        迭代进度
      </h3>

      {/* 迭代次数和阶段 */}
      <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 8 }}>
        <span data-testid="iteration-info">
          迭代 {state.currentIteration}/{state.maxIterations}
        </span>
        <span
          style={{ color: stageColor(state.currentStage) }}
          data-testid="stage-label"
        >
          {stageLabel(state.currentStage)}
        </span>
      </div>

      {/* 进度条 */}
      <div
        role="progressbar"
        aria-valuenow={Math.round(progress)}
        aria-valuemin={0}
        aria-valuemax={100}
        aria-label="迭代进度"
        style={{
          width: '100%',
          height: 8,
          background: 'var(--bg-secondary)',
          borderRadius: 4,
          overflow: 'hidden',
          marginBottom: 12,
        }}
      >
        <div
          style={{
            width: `${progress}%`,
            height: '100%',
            background: state.status === 'completed' ? 'var(--success, #22c55e)' : 'var(--accent)',
            borderRadius: 4,
            transition: 'width 0.3s ease',
          }}
        />
      </div>

      {/* 当前分数 */}
      {state.currentScore != null && (
        <div
          data-testid="current-score"
          style={{
            fontSize: '0.9rem',
            color: 'var(--text-muted)',
          }}
        >
          当前分数：
          <span style={{ fontWeight: 600, color: scoreColor(state.currentScore) }}>
            {state.currentScore.toFixed(1)}
          </span>
        </div>
      )}

      {/* 完成状态 */}
      {state.status === 'completed' && (
        <div
          data-testid="completed-message"
          style={{
            marginTop: 8,
            fontSize: '0.85rem',
            color: 'var(--success, #22c55e)',
          }}
        >
          ✓ 优化已完成
        </div>
      )}
    </div>
  )
}

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function stageLabel(stage: string): string {
  switch (stage) {
    case 'generating': return '生成剧本'
    case 'searching': return '搜索热点/技巧'
    case 'evaluating': return '评审中'
    case 'completed': return '已完成'
    default: return stage
  }
}

function stageColor(stage: string): string {
  switch (stage) {
    case 'generating': return 'var(--accent)'
    case 'searching': return 'var(--warning, #f59e0b)'
    case 'evaluating': return 'var(--info, #3b82f6)'
    case 'completed': return 'var(--success, #22c55e)'
    default: return 'var(--text-muted)'
  }
}

function scoreColor(score: number): string {
  if (score >= 8) return 'var(--success, #22c55e)'
  if (score >= 5) return 'var(--warning, #f59e0b)'
  return 'var(--danger, #ef4444)'
}
