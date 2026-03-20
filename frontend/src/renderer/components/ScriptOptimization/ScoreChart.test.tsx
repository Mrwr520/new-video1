import { describe, it, expect, vi } from 'vitest'
import { render, screen } from '@testing-library/react'
import { ScoreChart } from './ScoreChart'
import {
  OptimizationContext,
  type OptimizationContextValue,
  type OptimizationState,
  initialOptimizationState,
} from '../../../store/scriptOptimizationSlice'

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
      <ScoreChart />
    </OptimizationContext.Provider>,
  )
}

describe('ScoreChart', () => {
  it('renders nothing when no score history', () => {
    const { container } = renderWithContext({ scoreHistory: [] })
    expect(container.innerHTML).toBe('')
  })

  it('renders SVG when score history exists', () => {
    renderWithContext({
      status: 'running',
      scoreHistory: [3.5, 5.2, 6.8],
    })

    expect(screen.getByTestId('score-chart')).toBeInTheDocument()
  })

  it('shows target score dashed line', () => {
    renderWithContext({
      status: 'running',
      scoreHistory: [4.0],
    })

    const targetLine = screen.getByTestId('target-line')
    expect(targetLine).toBeInTheDocument()
    expect(targetLine.getAttribute('stroke-dasharray')).toBe('6 4')
  })

  it('renders correct number of data point circles', () => {
    renderWithContext({
      status: 'running',
      scoreHistory: [2.0, 4.5, 7.0, 8.5],
    })

    const svg = screen.getByTestId('score-chart')
    const circles = svg.querySelectorAll('circle')
    expect(circles).toHaveLength(4)
  })

  it('has accessible label on the SVG', () => {
    renderWithContext({
      status: 'running',
      scoreHistory: [5.0],
    })

    const svg = screen.getByTestId('score-chart')
    expect(svg).toHaveAttribute('aria-label', '分数历史曲线')
    expect(svg).toHaveAttribute('role', 'img')
  })
})
