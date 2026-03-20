import { useState } from 'react'
import { useOptimization } from '../../../store/scriptOptimizationSlice'

/**
 * 版本历史组件 - 显示所有迭代版本的时间线
 *
 * Requirements:
 *   6.2: 返回所有迭代版本的列表
 *   6.3: 显示选中版本的完整信息
 */
export function VersionHistory(): JSX.Element | null {
  const { state } = useOptimization()
  const [expandedIteration, setExpandedIteration] = useState<number | null>(null)

  if (state.versions.length === 0) {
    return null
  }

  const toggle = (iteration: number) => {
    setExpandedIteration(prev => (prev === iteration ? null : iteration))
  }

  return (
    <div className="card" style={{ marginBottom: 16 }}>
      <h3 style={{ fontSize: '1.05rem', marginBottom: 16, color: 'var(--accent)' }}>
        版本历史
      </h3>

      <div style={{ position: 'relative', paddingLeft: 20 }}>
        {/* Timeline line */}
        <div
          style={{
            position: 'absolute',
            left: 6,
            top: 0,
            bottom: 0,
            width: 2,
            background: 'var(--bg-secondary)',
          }}
        />

        {state.versions.map(version => {
          const isExpanded = expandedIteration === version.iteration
          return (
            <div key={version.iteration} style={{ position: 'relative', marginBottom: 12 }}>
              {/* Timeline dot */}
              <div
                style={{
                  position: 'absolute',
                  left: -17,
                  top: 6,
                  width: 10,
                  height: 10,
                  borderRadius: '50%',
                  background: version.is_final
                    ? 'var(--success, #22c55e)'
                    : 'var(--accent)',
                }}
              />

              {/* Version card */}
              <div
                data-testid={`version-entry-${version.iteration}`}
                onClick={() => toggle(version.iteration)}
                role="button"
                tabIndex={0}
                onKeyDown={e => {
                  if (e.key === 'Enter' || e.key === ' ') {
                    e.preventDefault()
                    toggle(version.iteration)
                  }
                }}
                style={{
                  padding: '8px 12px',
                  borderRadius: 6,
                  background: isExpanded ? 'var(--bg-secondary)' : 'transparent',
                  cursor: 'pointer',
                  transition: 'background 0.2s ease',
                }}
              >
                {/* Header row */}
                <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                  <span style={{ fontWeight: 600 }}>
                    第 {version.iteration} 版
                  </span>
                  <span
                    data-testid={`version-score-${version.iteration}`}
                    style={{
                      fontSize: '0.85rem',
                      color: scoreColor(version.evaluation.total_score),
                      fontWeight: 600,
                    }}
                  >
                    {version.evaluation.total_score.toFixed(1)} 分
                  </span>
                  {version.is_final && (
                    <span
                      data-testid={`version-final-${version.iteration}`}
                      style={{
                        fontSize: '0.7rem',
                        padding: '1px 6px',
                        borderRadius: 4,
                        background: 'var(--success, #22c55e)',
                        color: '#fff',
                      }}
                    >
                      最终版
                    </span>
                  )}
                  <span style={{ marginLeft: 'auto', fontSize: '0.75rem', color: 'var(--text-muted)' }}>
                    {formatTimestamp(version.timestamp)}
                  </span>
                </div>

                {/* Expanded content */}
                {isExpanded && (
                  <div data-testid={`version-detail-${version.iteration}`} style={{ marginTop: 10 }}>
                    {/* Suggestions */}
                    {version.evaluation.suggestions.length > 0 && (
                      <div style={{ marginBottom: 8 }}>
                        <div style={{ fontSize: '0.8rem', color: 'var(--text-muted)', marginBottom: 4 }}>
                          改进建议
                        </div>
                        <ul style={{ margin: 0, paddingLeft: 18, fontSize: '0.85rem' }}>
                          {version.evaluation.suggestions.map((s, i) => (
                            <li key={i}>{s}</li>
                          ))}
                        </ul>
                      </div>
                    )}

                    {/* Script content */}
                    <div>
                      <div style={{ fontSize: '0.8rem', color: 'var(--text-muted)', marginBottom: 4 }}>
                        剧本内容
                      </div>
                      <pre
                        data-testid={`version-script-${version.iteration}`}
                        style={{
                          margin: 0,
                          padding: 8,
                          borderRadius: 4,
                          background: 'var(--bg-primary, #1a1a2e)',
                          fontSize: '0.8rem',
                          whiteSpace: 'pre-wrap',
                          wordBreak: 'break-word',
                          maxHeight: 200,
                          overflowY: 'auto',
                        }}
                      >
                        {version.script}
                      </pre>
                    </div>
                  </div>
                )}
              </div>
            </div>
          )
        })}
      </div>
    </div>
  )
}

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function scoreColor(score: number): string {
  if (score >= 8) return 'var(--success, #22c55e)'
  if (score >= 5) return 'var(--warning, #f59e0b)'
  return 'var(--danger, #ef4444)'
}

function formatTimestamp(ts: string): string {
  try {
    const d = new Date(ts)
    return d.toLocaleTimeString()
  } catch {
    return ts
  }
}
