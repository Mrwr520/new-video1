import { describe, it, expect, vi } from 'vitest'
import { render, screen } from '@testing-library/react'
import { ProgressPanel } from './ProgressPanel'
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
      <ProgressPanel />
    </OptimizationContext.Provider>,
  )
}

describe('ProgressPanel', () => {
  it('renders nothing when status is idle', () => {
    const { container } = renderWithContext()
    expect(container.innerHTML).toBe('')
  })

  it('renders nothing when status is error', () => {
    const { container } = renderWithContext({ status: 'error', error: 'fail' })
    expect(container.innerHTML).toBe('')
  })

  it('shows iteration info when running', () => {
    renderWithContext({
      status: 'running',
      currentIteration: 3,
      maxIterations: 20,
      currentStage: 'generating',
    })

    expect(screen.getByTestId('iteration-info')).toHaveTextContent('迭代 3/20')
    expect(screen.getByTestId('stage-label')).toHaveTextContent('生成剧本')
  })

  it('shows correct stage labels', () => {
    renderWithContext({
      status: 'running',
      currentIteration: 5,
      maxIterations: 20,
      currentStage: 'evaluating',
    })

    expect(screen.getByTestId('stage-label')).toHaveTextContent('评审中')
  })

  it('shows searching stage label', () => {
    renderWithContext({
      status: 'running',
      currentIteration: 2,
      maxIterations: 10,
      currentStage: 'searching',
    })

    expect(screen.getByTestId('stage-label')).toHaveTextContent('搜索热点/技巧')
  })

  it('shows current score when available', () => {
    renderWithContext({
      status: 'running',
      currentIteration: 4,
      maxIterations: 20,
      currentStage: 'evaluating',
      currentScore: 6.5,
    })

    expect(screen.getByTestId('current-score')).toHaveTextContent('当前分数：6.5')
  })

  it('does not show score when null', () => {
    renderWithContext({
      status: 'running',
      currentIteration: 1,
      maxIterations: 20,
      currentStage: 'generating',
      currentScore: null,
    })

    expect(screen.queryByTestId('current-score')).not.toBeInTheDocument()
  })

  it('shows completed state', () => {
    renderWithContext({
      status: 'completed',
      currentIteration: 10,
      maxIterations: 20,
      currentStage: 'completed',
      currentScore: 8.5,
    })

    expect(screen.getByTestId('stage-label')).toHaveTextContent('已完成')
    expect(screen.getByTestId('completed-message')).toHaveTextContent('优化已完成')
    expect(screen.getByTestId('current-score')).toHaveTextContent('8.5')
  })

  it('renders a progress bar with correct value', () => {
    renderWithContext({
      status: 'running',
      currentIteration: 10,
      maxIterations: 20,
      currentStage: 'generating',
    })

    const progressbar = screen.getByRole('progressbar')
    expect(progressbar).toHaveAttribute('aria-valuenow', '50')
  })
})
