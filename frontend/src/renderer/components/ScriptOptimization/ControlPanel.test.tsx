import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, fireEvent, waitFor } from '@testing-library/react'
import { ControlPanel } from './ControlPanel'
import {
  OptimizationContext,
  type OptimizationContextValue,
  type OptimizationState,
  initialOptimizationState,
} from '../../../store/scriptOptimizationSlice'

// Helper: wrap ControlPanel with a mock OptimizationContext
function renderWithContext(overrides: Partial<OptimizationContextValue> = {}, stateOverrides: Partial<OptimizationState> = {}) {
  const state: OptimizationState = { ...initialOptimizationState, ...stateOverrides }
  const ctx: OptimizationContextValue = {
    state,
    dispatch: vi.fn(),
    startOptimization: vi.fn().mockResolvedValue('session-1'),
    fetchVersions: vi.fn().mockResolvedValue(undefined),
    fetchVersion: vi.fn().mockResolvedValue(null),
    reset: vi.fn(),
    ...overrides,
  }

  return {
    ctx,
    ...render(
      <OptimizationContext.Provider value={ctx}>
        <ControlPanel />
      </OptimizationContext.Provider>,
    ),
  }
}

describe('ControlPanel', () => {
  it('renders prompt textarea, score input, iterations input, and start button', () => {
    renderWithContext()

    expect(screen.getByLabelText('初始提示词')).toBeInTheDocument()
    expect(screen.getByLabelText('目标分数 (0-10)')).toBeInTheDocument()
    expect(screen.getByLabelText('最大迭代次数 (1-100)')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: '启动剧本优化' })).toBeInTheDocument()
  })

  it('start button is disabled when prompt is empty', () => {
    renderWithContext()
    expect(screen.getByRole('button', { name: '启动剧本优化' })).toBeDisabled()
  })

  it('start button is enabled when prompt has text', () => {
    renderWithContext()
    fireEvent.change(screen.getByLabelText('初始提示词'), { target: { value: '测试主题' } })
    expect(screen.getByRole('button', { name: '启动剧本优化' })).toBeEnabled()
  })

  it('calls startOptimization with correct params on click', async () => {
    const startOptimization = vi.fn().mockResolvedValue('session-1')
    renderWithContext({ startOptimization })

    fireEvent.change(screen.getByLabelText('初始提示词'), { target: { value: '我的剧本' } })
    fireEvent.change(screen.getByLabelText('目标分数 (0-10)'), { target: { value: '9' } })
    fireEvent.change(screen.getByLabelText('最大迭代次数 (1-100)'), { target: { value: '15' } })

    fireEvent.click(screen.getByRole('button', { name: '启动剧本优化' }))

    await waitFor(() => {
      expect(startOptimization).toHaveBeenCalledWith('我的剧本', 9, 15)
    })
  })

  it('disables all inputs while optimization is running', () => {
    renderWithContext({}, { status: 'running', currentIteration: 3, maxIterations: 20, currentStage: 'generating' })

    expect(screen.getByLabelText('初始提示词')).toBeDisabled()
    expect(screen.getByLabelText('目标分数 (0-10)')).toBeDisabled()
    expect(screen.getByLabelText('最大迭代次数 (1-100)')).toBeDisabled()
  })

  it('shows running status with iteration info', () => {
    renderWithContext({}, { status: 'running', currentIteration: 5, maxIterations: 20, currentStage: 'evaluating' })

    expect(screen.getByRole('status')).toHaveTextContent('迭代中 (5/20) — 评审中')
  })

  it('shows completed status with final score', () => {
    renderWithContext({}, { status: 'completed', currentScore: 8.5 })

    expect(screen.getByRole('status')).toHaveTextContent('优化完成 — 最终分数: 8.5')
  })

  it('shows error status', () => {
    renderWithContext({}, { status: 'error', error: '连接失败' })

    expect(screen.getByRole('status')).toHaveTextContent('错误: 连接失败')
  })

  it('shows idle status by default', () => {
    renderWithContext()
    expect(screen.getByRole('status')).toHaveTextContent('就绪')
  })

  it('default target score is 8.0 and max iterations is 20', () => {
    renderWithContext()
    expect(screen.getByLabelText('目标分数 (0-10)')).toHaveValue(8)
    expect(screen.getByLabelText('最大迭代次数 (1-100)')).toHaveValue(20)
  })
})
