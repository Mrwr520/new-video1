import { describe, it, expect, vi } from 'vitest'
import { render, screen, fireEvent } from '@testing-library/react'
import { VersionHistory } from './VersionHistory'
import {
  OptimizationContext,
  type OptimizationContextValue,
  type OptimizationState,
  type ScriptVersion,
  initialOptimizationState,
} from '../../../store/scriptOptimizationSlice'

function makeVersion(overrides: Partial<ScriptVersion> = {}): ScriptVersion {
  return {
    session_id: 'session-1',
    iteration: 1,
    script: '这是第一版剧本内容',
    evaluation: {
      total_score: 6.5,
      dimension_scores: {
        content_quality: 7,
        structure: 6,
        creativity: 7,
        hotspot_relevance: 5,
        technique_application: 6,
      },
      suggestions: ['增加更多细节', '优化结构'],
      timestamp: '2024-01-01T12:00:00Z',
    },
    hotspots: [],
    techniques: [],
    timestamp: '2024-01-01T12:00:00Z',
    is_final: false,
    ...overrides,
  }
}

function renderWithContext(stateOverrides: Partial<OptimizationState> = {}) {
  const state: OptimizationState = { ...initialOptimizationState, ...stateOverrides }
  const ctx: OptimizationContextValue = {
    state,
    dispatch: vi.fn(),
    startOptimization: vi.fn().mockResolvedValue('session-1'),
    fetchVersions: vi.fn().mockResolvedValue(undefined),
    fetchVersion: vi.fn().mockResolvedValue(null),
    reset: vi.fn(),
  }

  return render(
    <OptimizationContext.Provider value={ctx}>
      <VersionHistory />
    </OptimizationContext.Provider>,
  )
}

describe('VersionHistory', () => {
  it('renders nothing when no versions', () => {
    const { container } = renderWithContext({ versions: [] })
    expect(container.innerHTML).toBe('')
  })

  it('shows version entries when versions exist', () => {
    const versions = [makeVersion({ iteration: 1 }), makeVersion({ iteration: 2 })]
    renderWithContext({ versions })

    expect(screen.getByTestId('version-entry-1')).toBeInTheDocument()
    expect(screen.getByTestId('version-entry-2')).toBeInTheDocument()
  })

  it('shows iteration number and score for each version', () => {
    const versions = [
      makeVersion({ iteration: 1, evaluation: { ...makeVersion().evaluation, total_score: 5.2 } }),
      makeVersion({ iteration: 2, evaluation: { ...makeVersion().evaluation, total_score: 7.8 } }),
    ]
    renderWithContext({ versions })

    expect(screen.getByTestId('version-entry-1')).toHaveTextContent('第 1 版')
    expect(screen.getByTestId('version-score-1')).toHaveTextContent('5.2 分')
    expect(screen.getByTestId('version-entry-2')).toHaveTextContent('第 2 版')
    expect(screen.getByTestId('version-score-2')).toHaveTextContent('7.8 分')
  })

  it('shows final badge for final version', () => {
    const versions = [
      makeVersion({ iteration: 1, is_final: false }),
      makeVersion({ iteration: 2, is_final: true }),
    ]
    renderWithContext({ versions })

    expect(screen.queryByTestId('version-final-1')).not.toBeInTheDocument()
    expect(screen.getByTestId('version-final-2')).toHaveTextContent('最终版')
  })

  it('clicking a version expands it to show script content', () => {
    const versions = [makeVersion({ iteration: 1, script: '测试剧本内容' })]
    renderWithContext({ versions })

    // Not expanded initially
    expect(screen.queryByTestId('version-detail-1')).not.toBeInTheDocument()

    // Click to expand
    fireEvent.click(screen.getByTestId('version-entry-1'))
    expect(screen.getByTestId('version-detail-1')).toBeInTheDocument()
    expect(screen.getByTestId('version-script-1')).toHaveTextContent('测试剧本内容')
  })

  it('clicking an expanded version collapses it', () => {
    const versions = [makeVersion({ iteration: 1 })]
    renderWithContext({ versions })

    fireEvent.click(screen.getByTestId('version-entry-1'))
    expect(screen.getByTestId('version-detail-1')).toBeInTheDocument()

    fireEvent.click(screen.getByTestId('version-entry-1'))
    expect(screen.queryByTestId('version-detail-1')).not.toBeInTheDocument()
  })
})
