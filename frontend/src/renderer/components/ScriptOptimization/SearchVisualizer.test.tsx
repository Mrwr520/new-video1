import { describe, it, expect, vi } from 'vitest'
import { render, screen } from '@testing-library/react'
import { SearchVisualizer } from './SearchVisualizer'
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
      <SearchVisualizer />
    </OptimizationContext.Provider>,
  )
}

describe('SearchVisualizer', () => {
  it('renders nothing when no data and not searching', () => {
    const { container } = renderWithContext()
    expect(container.innerHTML).toBe('')
  })

  it('renders nothing when stage is generating with no data', () => {
    const { container } = renderWithContext({
      status: 'running',
      currentStage: 'generating',
      hotspots: [],
      techniques: [],
    })
    expect(container.innerHTML).toBe('')
  })

  it('shows searching indicator when stage is searching', () => {
    renderWithContext({
      status: 'running',
      currentStage: 'searching',
    })

    expect(screen.getByTestId('searching-indicator')).toBeInTheDocument()
    expect(screen.getByText('正在搜索热点和技巧…')).toBeInTheDocument()
  })

  it('shows hotspot cards when hotspots exist', () => {
    renderWithContext({
      status: 'running',
      currentStage: 'evaluating',
      hotspots: [
        {
          title: '热点标题1',
          description: '热点描述1',
          source: '来源1',
          relevance_score: 0.9,
          timestamp: '2024-01-01T00:00:00Z',
        },
        {
          title: '热点标题2',
          description: '热点描述2',
          source: '来源2',
          relevance_score: 0.8,
          timestamp: '2024-01-01T00:00:00Z',
        },
      ],
    })

    const cards = screen.getAllByTestId('hotspot-card')
    expect(cards).toHaveLength(2)
    expect(screen.getByText('热点标题1')).toBeInTheDocument()
    expect(screen.getByText('热点描述1')).toBeInTheDocument()
    expect(screen.getByText('来源：来源1')).toBeInTheDocument()
    expect(screen.getByText('热点标题2')).toBeInTheDocument()
  })

  it('shows technique cards when techniques exist', () => {
    renderWithContext({
      status: 'running',
      currentStage: 'evaluating',
      techniques: [
        {
          name: '技巧名称1',
          description: '技巧描述1',
          example: '示例1',
          category: '分类1',
          source: '来源1',
        },
        {
          name: '技巧名称2',
          description: '技巧描述2',
          example: '示例2',
          category: '分类2',
          source: '来源2',
        },
      ],
    })

    const cards = screen.getAllByTestId('technique-card')
    expect(cards).toHaveLength(2)
    expect(screen.getByText('技巧名称1')).toBeInTheDocument()
    expect(screen.getByText('技巧描述1')).toBeInTheDocument()
    expect(screen.getByText('分类：分类1')).toBeInTheDocument()
    expect(screen.getByText('技巧名称2')).toBeInTheDocument()
  })

  it('shows both hotspots and techniques together', () => {
    renderWithContext({
      status: 'running',
      currentStage: 'evaluating',
      hotspots: [
        {
          title: '热点A',
          description: '描述A',
          source: '来源A',
          relevance_score: 0.9,
          timestamp: '2024-01-01T00:00:00Z',
        },
      ],
      techniques: [
        {
          name: '技巧B',
          description: '描述B',
          example: '示例B',
          category: '分类B',
          source: '来源B',
        },
      ],
    })

    expect(screen.getByTestId('hotspot-list')).toBeInTheDocument()
    expect(screen.getByTestId('technique-list')).toBeInTheDocument()
    expect(screen.getAllByTestId('hotspot-card')).toHaveLength(1)
    expect(screen.getAllByTestId('technique-card')).toHaveLength(1)
  })

  it('shows searching indicator alongside existing data', () => {
    renderWithContext({
      status: 'running',
      currentStage: 'searching',
      hotspots: [
        {
          title: '旧热点',
          description: '旧描述',
          source: '旧来源',
          relevance_score: 0.7,
          timestamp: '2024-01-01T00:00:00Z',
        },
      ],
    })

    expect(screen.getByTestId('searching-indicator')).toBeInTheDocument()
    expect(screen.getByTestId('hotspot-list')).toBeInTheDocument()
  })
})
