import { useMemo } from 'react'
import { useOptimization } from '../../../store/scriptOptimizationSlice'

/**
 * 分数可视化组件 - 使用纯 SVG 绘制分数历史曲线
 *
 * Requirements:
 *   5.2: 实时更新迭代次数、当前分数和历史分数曲线
 */

/** Chart layout constants */
const CHART_WIDTH = 480
const CHART_HEIGHT = 240
const PADDING = { top: 20, right: 20, bottom: 32, left: 40 }
const PLOT_W = CHART_WIDTH - PADDING.left - PADDING.right
const PLOT_H = CHART_HEIGHT - PADDING.top - PADDING.bottom
const Y_MIN = 0
const Y_MAX = 10
const TARGET_SCORE = 8

export function ScoreChart(): JSX.Element | null {
  const { state } = useOptimization()
  const { scoreHistory } = state

  if (scoreHistory.length === 0) return null

  return (
    <div className="card" style={{ marginBottom: 16 }}>
      <h3 style={{ fontSize: '1.05rem', marginBottom: 16, color: 'var(--accent)' }}>
        分数趋势
      </h3>
      <ScoreChartSVG scores={scoreHistory} />
    </div>
  )
}

// ---------------------------------------------------------------------------
// Pure SVG chart (extracted for testability)
// ---------------------------------------------------------------------------

interface ScoreChartSVGProps {
  scores: number[]
}

export function ScoreChartSVG({ scores }: ScoreChartSVGProps): JSX.Element {
  const points = useMemo(() => buildPoints(scores), [scores])
  const polyline = points.map((p) => `${p.x},${p.y}`).join(' ')

  const yTicks = [0, 2, 4, 6, 8, 10]
  const targetY = toY(TARGET_SCORE)

  return (
    <svg
      data-testid="score-chart"
      viewBox={`0 0 ${CHART_WIDTH} ${CHART_HEIGHT}`}
      width="100%"
      style={{ maxWidth: CHART_WIDTH, display: 'block' }}
      role="img"
      aria-label="分数历史曲线"
    >
      {/* Y-axis grid lines & labels */}
      {yTicks.map((v) => {
        const y = toY(v)
        return (
          <g key={`y-${v}`}>
            <line
              x1={PADDING.left}
              y1={y}
              x2={PADDING.left + PLOT_W}
              y2={y}
              stroke="var(--bg-secondary, #333)"
              strokeWidth={1}
            />
            <text
              x={PADDING.left - 6}
              y={y + 4}
              textAnchor="end"
              fontSize={11}
              fill="var(--text-muted, #888)"
            >
              {v}
            </text>
          </g>
        )
      })}

      {/* Target score dashed line */}
      <line
        data-testid="target-line"
        x1={PADDING.left}
        y1={targetY}
        x2={PADDING.left + PLOT_W}
        y2={targetY}
        stroke="var(--success, #22c55e)"
        strokeWidth={1.5}
        strokeDasharray="6 4"
      />
      <text
        x={PADDING.left + PLOT_W + 2}
        y={targetY + 4}
        fontSize={10}
        fill="var(--success, #22c55e)"
      >
        目标
      </text>

      {/* X-axis labels */}
      {points.map((p, i) => (
        <text
          key={`x-${i}`}
          x={p.x}
          y={PADDING.top + PLOT_H + 18}
          textAnchor="middle"
          fontSize={11}
          fill="var(--text-muted, #888)"
        >
          {i + 1}
        </text>
      ))}

      {/* Score line */}
      {points.length > 1 && (
        <polyline
          points={polyline}
          fill="none"
          stroke="var(--accent, #6366f1)"
          strokeWidth={2}
          strokeLinejoin="round"
          strokeLinecap="round"
        />
      )}

      {/* Data point dots */}
      {points.map((p, i) => (
        <circle
          key={`dot-${i}`}
          cx={p.x}
          cy={p.y}
          r={4}
          fill="var(--accent, #6366f1)"
          stroke="var(--bg-primary, #1a1a2e)"
          strokeWidth={2}
        />
      ))}
    </svg>
  )
}

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

interface Point {
  x: number
  y: number
}

function toY(value: number): number {
  return PADDING.top + PLOT_H - ((value - Y_MIN) / (Y_MAX - Y_MIN)) * PLOT_H
}

function buildPoints(scores: number[]): Point[] {
  const count = scores.length
  return scores.map((score, i) => ({
    x: count === 1
      ? PADDING.left + PLOT_W / 2
      : PADDING.left + (i / (count - 1)) * PLOT_W,
    y: toY(score),
  }))
}
