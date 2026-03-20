import { describe, it, expect, vi } from 'vitest'
import { render, screen } from '@testing-library/react'
import { ScriptOptimizationView } from './ScriptOptimizationView'

// Mock the apiClient used by createOptimizationActions
vi.mock('../renderer/services/api-client', () => ({
  apiClient: {
    startScriptOptimization: vi.fn(),
    getOptimizationVersions: vi.fn(),
    getOptimizationVersion: vi.fn(),
  },
}))

describe('ScriptOptimizationView', () => {
  it('renders without crashing', () => {
    render(<ScriptOptimizationView />)
    expect(screen.getByText('剧本迭代优化')).toBeInTheDocument()
  })

  it('renders the ControlPanel', () => {
    render(<ScriptOptimizationView />)
    expect(screen.getByLabelText('初始提示词')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: '启动剧本优化' })).toBeInTheDocument()
  })
})
