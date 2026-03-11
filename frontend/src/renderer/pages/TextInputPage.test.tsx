import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { render, screen, fireEvent, waitFor } from '@testing-library/react'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { TextInputPage } from './TextInputPage'

// mock apiClient
vi.mock('../services/api-client', () => ({
  apiClient: {
    submitText: vi.fn()
  }
}))

import { apiClient } from '../services/api-client'
const mockSubmitText = vi.mocked(apiClient.submitText)

// mock navigate
const mockNavigate = vi.fn()
vi.mock('react-router-dom', async () => {
  const actual = await vi.importActual('react-router-dom')
  return {
    ...actual,
    useNavigate: () => mockNavigate
  }
})

function renderPage(): ReturnType<typeof render> {
  return render(
    <MemoryRouter initialEntries={['/project/test-id/text']}>
      <Routes>
        <Route path="/project/:id/text" element={<TextInputPage />} />
      </Routes>
    </MemoryRouter>
  )
}

describe('TextInputPage', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  afterEach(() => {
    vi.restoreAllMocks()
  })

  it('渲染页面标题和基本元素', () => {
    renderPage()
    expect(screen.getByText('文本输入')).toBeInTheDocument()
    expect(screen.getByLabelText('文本内容')).toBeInTheDocument()
    expect(screen.getByLabelText('内容类型')).toBeInTheDocument()
    expect(screen.getByLabelText('提交文本')).toBeInTheDocument()
    expect(screen.getByText('返回工作台')).toBeInTheDocument()
  })

  it('显示字数统计，初始为 0', () => {
    renderPage()
    const charCount = screen.getByTestId('char-count')
    expect(charCount.textContent).toContain('0')
  })

  it('输入文本后更新字数统计', () => {
    renderPage()
    const textarea = screen.getByLabelText('文本内容')
    fireEvent.change(textarea, { target: { value: '这是一段测试文本内容，用于验证字数统计功能' } })
    const charCount = screen.getByTestId('char-count')
    expect(charCount.textContent).toContain('21')
  })

  it('文本为空时提交按钮禁用', () => {
    renderPage()
    const submitBtn = screen.getByLabelText('提交文本')
    expect(submitBtn).toBeDisabled()
  })

  it('文本长度不足时提交按钮禁用', () => {
    renderPage()
    const textarea = screen.getByLabelText('文本内容')
    fireEvent.change(textarea, { target: { value: '短' } })
    const submitBtn = screen.getByLabelText('提交文本')
    expect(submitBtn).toBeDisabled()
  })

  it('文本长度足够时提交按钮启用', () => {
    renderPage()
    const textarea = screen.getByLabelText('文本内容')
    fireEvent.change(textarea, { target: { value: '这是一段足够长的测试文本内容' } })
    const submitBtn = screen.getByLabelText('提交文本')
    expect(submitBtn).not.toBeDisabled()
  })

  it('内容类型选择器包含三种模板', () => {
    renderPage()
    const select = screen.getByLabelText('内容类型')
    expect(select).toBeInTheDocument()
    expect(screen.getByText('动漫')).toBeInTheDocument()
    expect(screen.getByText('科普')).toBeInTheDocument()
    expect(screen.getByText('数学讲解')).toBeInTheDocument()
  })

  it('可以切换内容类型', () => {
    renderPage()
    const select = screen.getByLabelText('内容类型') as HTMLSelectElement
    fireEvent.change(select, { target: { value: 'science' } })
    expect(select.value).toBe('science')
  })

  it('提交成功后显示结果反馈', async () => {
    mockSubmitText.mockResolvedValueOnce({
      status: 'valid',
      message: '校验通过',
      char_count: 20
    })

    renderPage()
    const textarea = screen.getByLabelText('文本内容')
    fireEvent.change(textarea, { target: { value: '这是一段足够长的测试文本内容用于提交' } })

    const submitBtn = screen.getByLabelText('提交文本')
    fireEvent.click(submitBtn)

    await waitFor(() => {
      const result = screen.getByTestId('submit-result')
      expect(result.textContent).toContain('校验通过')
    })

    expect(mockSubmitText).toHaveBeenCalledWith('test-id', {
      text: '这是一段足够长的测试文本内容用于提交',
      filename: undefined
    })
  })

  it('提交失败时显示错误信息', async () => {
    mockSubmitText.mockRejectedValueOnce(new Error('网络错误'))

    renderPage()
    const textarea = screen.getByLabelText('文本内容')
    fireEvent.change(textarea, { target: { value: '这是一段足够长的测试文本内容用于提交' } })

    const submitBtn = screen.getByLabelText('提交文本')
    fireEvent.click(submitBtn)

    await waitFor(() => {
      expect(screen.getByRole('alert')).toHaveTextContent('网络错误')
    })
  })

  it('后端返回 invalid 时显示校验失败信息', async () => {
    mockSubmitText.mockResolvedValueOnce({
      status: 'invalid',
      message: '文本长度不足，最少需要 10 个字符，当前 5 个字符',
      char_count: 5
    })

    renderPage()
    const textarea = screen.getByLabelText('文本内容')
    // 输入足够长的文本通过前端校验，但后端返回 invalid
    fireEvent.change(textarea, { target: { value: '这是一段足够长的测试文本内容用于提交' } })

    const submitBtn = screen.getByLabelText('提交文本')
    fireEvent.click(submitBtn)

    await waitFor(() => {
      const result = screen.getByTestId('submit-result')
      expect(result.textContent).toContain('文本长度不足')
    })
  })

  it('导入文件按钮存在', () => {
    renderPage()
    expect(screen.getByLabelText('导入文件')).toBeInTheDocument()
  })

  it('字数不足时显示最少字符提示', () => {
    renderPage()
    const textarea = screen.getByLabelText('文本内容')
    fireEvent.change(textarea, { target: { value: '短文本' } })
    const charCount = screen.getByTestId('char-count')
    expect(charCount.textContent).toContain('最少 10 个字符')
  })

  it('返回工作台链接指向正确路径', () => {
    renderPage()
    const link = screen.getByText('返回工作台')
    expect(link.getAttribute('href')).toBe('/project/test-id')
  })
})
