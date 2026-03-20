import { describe, it, expect, vi } from 'vitest'
import { render, screen, fireEvent } from '@testing-library/react'
import { ConfigPanel } from './ConfigPanel'

describe('ConfigPanel', () => {
  it('renders all form fields', () => {
    render(<ConfigPanel />)

    expect(screen.getByLabelText('目标分数 (0-10)')).toBeInTheDocument()
    expect(screen.getByLabelText('最大迭代次数 (1-100)')).toBeInTheDocument()
    expect(screen.getByLabelText('内容质量')).toBeInTheDocument()
    expect(screen.getByLabelText('结构完整性')).toBeInTheDocument()
    expect(screen.getByLabelText('创意性')).toBeInTheDocument()
    expect(screen.getByLabelText('热点相关性')).toBeInTheDocument()
    expect(screen.getByLabelText('技巧运用')).toBeInTheDocument()
    expect(screen.getByLabelText('搜索 API 密钥')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: '保存配置' })).toBeInTheDocument()
  })

  it('renders the API key field as a password input', () => {
    render(<ConfigPanel />)
    const apiKeyInput = screen.getByLabelText('搜索 API 密钥')
    expect(apiKeyInput).toHaveAttribute('type', 'password')
  })

  it('shows validation error when weights do not sum to 1.0', () => {
    const onSave = vi.fn()
    render(<ConfigPanel onSave={onSave} />)

    // Set one weight to 0 so the sum is no longer ~1.0
    const contentInput = screen.getByLabelText('内容质量')
    fireEvent.change(contentInput, { target: { value: '0' } })

    fireEvent.click(screen.getByRole('button', { name: '保存配置' }))

    expect(screen.getByTestId('validation-error')).toBeInTheDocument()
    expect(screen.getByTestId('validation-error')).toHaveTextContent('维度权重之和必须约等于 1.0')
    expect(onSave).not.toHaveBeenCalled()
  })

  it('calls onSave with config values when weights are valid', () => {
    const onSave = vi.fn()
    render(<ConfigPanel onSave={onSave} />)

    // Default weights sum to 1.0, so just click save
    fireEvent.click(screen.getByRole('button', { name: '保存配置' }))

    expect(screen.queryByTestId('validation-error')).not.toBeInTheDocument()
    expect(onSave).toHaveBeenCalledTimes(1)

    const config = onSave.mock.calls[0][0]
    expect(config.targetScore).toBe(8.0)
    expect(config.maxIterations).toBe(20)
    expect(config.weights.content_quality).toBe(0.3)
    expect(config.searchApiKey).toBe('')
  })

  it('displays the current weight sum', () => {
    render(<ConfigPanel />)
    expect(screen.getByTestId('weight-sum')).toHaveTextContent('1.00')
  })
})
