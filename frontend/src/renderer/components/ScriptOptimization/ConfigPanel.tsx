import { useState, useCallback } from 'react'

/**
 * 配置值接口
 */
export interface ConfigValues {
  targetScore: number
  maxIterations: number
  weights: DimensionWeightValues
  searchApiKey: string
}

export interface DimensionWeightValues {
  content_quality: number
  structure: number
  creativity: number
  hotspot_relevance: number
  technique_application: number
}

const DEFAULT_WEIGHTS: DimensionWeightValues = {
  content_quality: 0.3,
  structure: 0.2,
  creativity: 0.2,
  hotspot_relevance: 0.15,
  technique_application: 0.15,
}

const WEIGHT_LABELS: Record<keyof DimensionWeightValues, string> = {
  content_quality: '内容质量',
  structure: '结构完整性',
  creativity: '创意性',
  hotspot_relevance: '热点相关性',
  technique_application: '技巧运用',
}

const WEIGHT_SUM_TOLERANCE = 0.05

interface ConfigPanelProps {
  onSave?: (config: ConfigValues) => void
}

/**
 * 配置管理面板 - 配置优化参数
 *
 * Requirements:
 *   8.1: 允许配置目标分数
 *   8.2: 允许配置最大迭代次数
 *   8.3: 允许配置各评审维度的权重
 *   8.4: 允许配置第三方 API 的密钥和端点
 *   8.5: 配置更新时验证配置的有效性
 */
export function ConfigPanel({ onSave }: ConfigPanelProps): JSX.Element {
  const [targetScore, setTargetScore] = useState(8.0)
  const [maxIterations, setMaxIterations] = useState(20)
  const [weights, setWeights] = useState<DimensionWeightValues>({ ...DEFAULT_WEIGHTS })
  const [searchApiKey, setSearchApiKey] = useState('')
  const [validationError, setValidationError] = useState<string | null>(null)

  const weightSum = Object.values(weights).reduce((sum, w) => sum + w, 0)
  const isWeightValid = Math.abs(weightSum - 1.0) <= WEIGHT_SUM_TOLERANCE

  const handleWeightChange = useCallback(
    (key: keyof DimensionWeightValues, value: number) => {
      setWeights((prev) => ({ ...prev, [key]: clamp(value, 0, 1) }))
      setValidationError(null)
    },
    [],
  )

  const handleSave = useCallback(() => {
    if (!isWeightValid) {
      setValidationError(
        `维度权重之和必须约等于 1.0（当前: ${weightSum.toFixed(2)}）`,
      )
      return
    }
    setValidationError(null)
    onSave?.({ targetScore, maxIterations, weights, searchApiKey })
  }, [isWeightValid, weightSum, targetScore, maxIterations, weights, searchApiKey, onSave])

  return (
    <div className="card" style={{ marginBottom: 16 }}>
      <h3 style={{ fontSize: '1.05rem', marginBottom: 16, color: 'var(--accent)' }}>
        优化配置
      </h3>

      {/* 目标分数 & 最大迭代次数 */}
      <div style={{ display: 'flex', gap: 16, flexWrap: 'wrap' }}>
        <div className="form-field" style={{ flex: 1, minWidth: 140 }}>
          <label htmlFor="cfg-target-score">目标分数 (0-10)</label>
          <input
            id="cfg-target-score"
            type="number"
            min={0}
            max={10}
            step={0.5}
            value={targetScore}
            onChange={(e) => setTargetScore(clamp(parseFloat(e.target.value) || 0, 0, 10))}
          />
        </div>

        <div className="form-field" style={{ flex: 1, minWidth: 140 }}>
          <label htmlFor="cfg-max-iterations">最大迭代次数 (1-100)</label>
          <input
            id="cfg-max-iterations"
            type="number"
            min={1}
            max={100}
            step={1}
            value={maxIterations}
            onChange={(e) =>
              setMaxIterations(clamp(Math.round(parseFloat(e.target.value) || 1), 1, 100))
            }
          />
        </div>
      </div>

      {/* 评审维度权重 */}
      <fieldset
        style={{
          border: '1px solid var(--bg-secondary)',
          borderRadius: 'var(--radius)',
          padding: 12,
          marginBottom: 12,
        }}
      >
        <legend style={{ fontSize: '0.9rem', color: 'var(--text-muted)', padding: '0 4px' }}>
          评审维度权重（总和需约等于 1.0）
        </legend>

        <div style={{ display: 'flex', flexWrap: 'wrap', gap: 12 }}>
          {(Object.keys(WEIGHT_LABELS) as (keyof DimensionWeightValues)[]).map((key) => (
            <div className="form-field" key={key} style={{ flex: '1 1 140px' }}>
              <label htmlFor={`cfg-weight-${key}`}>{WEIGHT_LABELS[key]}</label>
              <input
                id={`cfg-weight-${key}`}
                type="number"
                min={0}
                max={1}
                step={0.05}
                value={weights[key]}
                onChange={(e) =>
                  handleWeightChange(key, parseFloat(e.target.value) || 0)
                }
              />
            </div>
          ))}
        </div>

        <div
          style={{
            fontSize: '0.8rem',
            color: isWeightValid ? 'var(--text-muted)' : 'var(--danger)',
            marginTop: 4,
          }}
          data-testid="weight-sum"
        >
          当前权重总和: {weightSum.toFixed(2)}
        </div>
      </fieldset>

      {/* 搜索 API 密钥 */}
      <div className="form-field" style={{ marginBottom: 12 }}>
        <label htmlFor="cfg-api-key">搜索 API 密钥</label>
        <input
          id="cfg-api-key"
          type="password"
          value={searchApiKey}
          onChange={(e) => setSearchApiKey(e.target.value)}
          placeholder="请输入搜索 API 密钥..."
        />
      </div>

      {/* 验证错误 */}
      {validationError && (
        <div
          role="alert"
          style={{
            fontSize: '0.85rem',
            color: 'var(--danger)',
            padding: '8px 12px',
            background: 'var(--danger-bg)',
            borderRadius: 'var(--radius)',
            marginBottom: 12,
          }}
          data-testid="validation-error"
        >
          {validationError}
        </div>
      )}

      {/* 保存按钮 */}
      <div className="form-actions">
        <button type="button" onClick={handleSave} aria-label="保存配置">
          保存配置
        </button>
      </div>
    </div>
  )
}

function clamp(value: number, min: number, max: number): number {
  return Math.min(max, Math.max(min, value))
}
