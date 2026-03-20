import { useMemo } from 'react'
import { useOptimization } from '../../../store/scriptOptimizationSlice'
import type { DimensionScores } from '../../../store/scriptOptimizationSlice'

/**
 * 维度雷达图 - 使用纯 SVG 绘制五维评审雷达图
 *
 * 显示五个评审维度（内容质量、结构完整性、创意性、热点相关性、技巧运用）的得分。
 * 使用 CSS transition 实现平滑动画效果。
 *
 * Requirements:
 *   5.5: 显示各维度评分的雷达图
 */

/** Dimension definitions in display order */
const DIMENSIONS: { key: keyof DimensionScores; label: string }[] = [
  { key: 'content_quality', label: '内容质量' },
  { key: 'structure', label: '结构完整性' },
  { key: 'creativity', label: '创意性' },
  { key: 'hotspot_relevance', label: '热点相关性' },
  { key: 'technique_application', label: '技巧运用' },
]

const NUM_SIDES = DIMENSIONS.length
const MAX_VALUE = 10
const GRID_LEVELS = [2, 4, 6, 8, 10]
const SIZE = 300
const CENTER = SIZE / 2
const RADIUS = 110
const LABEL_OFFSET = 24

export function RadarChart(): JSX.Element | null {
  const { state } = useOptimization()

  if (state.versions.length === 0) return null

  const latestVersion = state.versions[state.versions.length - 1]
  const scores = latestVersion.evaluation.dimension_scores

  return (
    <div className="card" style={{ marginBottom: 16 }}>
      <h3 style={{ fontSize: '1.05rem', marginBottom: 16, color: 'var(--accent)' }}>
        维度评分
      </h3>
      <RadarChartSVG scores={scores} />
    </div>
  )
}

// ---------------------------------------------------------------------------
// Pure SVG radar chart (extracted for testability)
// ---------------------------------------------------------------------------

interface RadarChartSVGProps {
  scores: DimensionScores
}

export function RadarChartSVG({ scores }: RadarChartSVGProps): JSX.Element {
  const vertices = useMemo(() => buildVertices(), [])
  const dataPoints = useMemo(() => buildDataPoints(scores, vertices), [scores, vertices])
  const dataPolygon = dataPoints.map((p) => `${p.x},${p.y}`).join(' ')

  return (
    <svg
      data-testid="radar-chart"
      viewBox={`0 0 ${SIZE} ${SIZE}`}
      width="100%"
      style={{ maxWidth: SIZE, display: 'block', margin: '0 auto' }}
      role="img"
      aria-label="维度评分雷达图"
    >
      {/* Concentric pentagon grid lines */}
      {GRID_LEVELS.map((level) => {
        const scale = level / MAX_VALUE
        const pts = vertices
          .map((v) => `${CENTER + v.dx * scale},${CENTER + v.dy * scale}`)
          .join(' ')
        return (
          <polygon
            key={`grid-${level}`}
            points={pts}
            fill="none"
            stroke="var(--bg-secondary, #333)"
            strokeWidth={1}
            opacity={0.6}
          />
        )
      })}

      {/* Axis lines from center to each vertex */}
      {vertices.map((v, i) => (
        <line
          key={`axis-${i}`}
          x1={CENTER}
          y1={CENTER}
          x2={CENTER + v.dx}
          y2={CENTER + v.dy}
          stroke="var(--bg-secondary, #333)"
          strokeWidth={1}
          opacity={0.4}
        />
      ))}

      {/* Data polygon with CSS transition for animation */}
      <polygon
        data-testid="radar-data-polygon"
        points={dataPolygon}
        fill="var(--accent, #6366f1)"
        fillOpacity={0.25}
        stroke="var(--accent, #6366f1)"
        strokeWidth={2}
        strokeLinejoin="round"
        style={{ transition: 'all 0.5s ease' }}
      />

      {/* Data point dots */}
      {dataPoints.map((p, i) => (
        <circle
          key={`dot-${i}`}
          cx={p.x}
          cy={p.y}
          r={4}
          fill="var(--accent, #6366f1)"
          stroke="var(--bg-primary, #1a1a2e)"
          strokeWidth={2}
          style={{ transition: 'cx 0.5s ease, cy 0.5s ease' }}
        />
      ))}

      {/* Dimension labels */}
      {vertices.map((v, i) => {
        const labelX = CENTER + v.dx * ((RADIUS + LABEL_OFFSET) / RADIUS)
        const labelY = CENTER + v.dy * ((RADIUS + LABEL_OFFSET) / RADIUS)
        return (
          <text
            key={`label-${i}`}
            x={labelX}
            y={labelY}
            textAnchor="middle"
            dominantBaseline="central"
            fontSize={12}
            fill="var(--text-muted, #888)"
            data-testid={`radar-label-${DIMENSIONS[i].key}`}
          >
            {DIMENSIONS[i].label}
          </text>
        )
      })}
    </svg>
  )
}

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

interface Vertex {
  dx: number
  dy: number
}

interface Point {
  x: number
  y: number
}

/** Build unit-direction vertices for a regular pentagon (starting from top). */
function buildVertices(): Vertex[] {
  return Array.from({ length: NUM_SIDES }, (_, i) => {
    const angle = (Math.PI * 2 * i) / NUM_SIDES - Math.PI / 2
    return {
      dx: Math.cos(angle) * RADIUS,
      dy: Math.sin(angle) * RADIUS,
    }
  })
}

/** Map dimension scores to SVG coordinates. */
function buildDataPoints(scores: DimensionScores, vertices: Vertex[]): Point[] {
  return DIMENSIONS.map((dim, i) => {
    const value = Math.min(Math.max(scores[dim.key], 0), MAX_VALUE)
    const scale = value / MAX_VALUE
    return {
      x: CENTER + vertices[i].dx * scale,
      y: CENTER + vertices[i].dy * scale,
    }
  })
}
