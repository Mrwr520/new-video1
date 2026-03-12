import { render, screen, waitFor, fireEvent } from '@testing-library/react'
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { CharacterManagePage } from './CharacterManagePage'

vi.mock('../services/api-client', async () => {
  const actual = await vi.importActual('../services/api-client')
  return {
    ...actual,
    apiClient: {
      getCharacters: vi.fn(),
      createCharacter: vi.fn(),
      updateCharacter: vi.fn(),
      deleteCharacter: vi.fn(),
      confirmCharacters: vi.fn()
    }
  }
})

import { apiClient } from '../services/api-client'
const mockApi = apiClient as unknown as {
  getCharacters: ReturnType<typeof vi.fn>
  createCharacter: ReturnType<typeof vi.fn>
  updateCharacter: ReturnType<typeof vi.fn>
  deleteCharacter: ReturnType<typeof vi.fn>
  confirmCharacters: ReturnType<typeof vi.fn>
}

const sampleChars = [
  { id: 'char-1', name: '张三', appearance: '黑发高个', personality: '沉稳', background: '退役军人', image_prompt: 'tall man' },
  { id: 'char-2', name: '李四', appearance: '金发', personality: '活泼', background: '学生', image_prompt: 'blonde student' }
]

function renderPage(): void {
  render(
    <MemoryRouter initialEntries={['/project/proj-1/chars']}>
      <Routes>
        <Route path="/project/:id/chars" element={<CharacterManagePage />} />
      </Routes>
    </MemoryRouter>
  )
}

describe('CharacterManagePage', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  it('加载时显示加载状态，然后展示角色列表', async () => {
    mockApi.getCharacters.mockResolvedValueOnce(sampleChars)

    renderPage()
    expect(screen.getByText('加载中...')).toBeInTheDocument()

    await waitFor(() => {
      expect(screen.getByText('张三')).toBeInTheDocument()
    })
    expect(screen.getByText('李四')).toBeInTheDocument()
    expect(screen.getByText(/黑发高个/)).toBeInTheDocument()
    expect(screen.getByText(/沉稳/)).toBeInTheDocument()
  })

  it('空角色列表时显示提示文字', async () => {
    mockApi.getCharacters.mockResolvedValueOnce([])

    renderPage()

    await waitFor(() => {
      expect(screen.getByText(/暂无角色/)).toBeInTheDocument()
    })
  })

  it('加载失败时显示错误信息', async () => {
    mockApi.getCharacters.mockRejectedValueOnce(new Error('网络错误'))

    renderPage()

    await waitFor(() => {
      expect(screen.getByRole('alert')).toHaveTextContent('网络错误')
    })
  })

  it('点击"添加角色"按钮显示添加表单', async () => {
    mockApi.getCharacters.mockResolvedValueOnce([])

    renderPage()

    await waitFor(() => {
      expect(screen.getByText(/暂无角色/)).toBeInTheDocument()
    })

    fireEvent.click(screen.getByLabelText('手动添加角色'))
    expect(screen.getByText('添加新角色')).toBeInTheDocument()
    expect(screen.getByLabelText('名称')).toBeInTheDocument()
    expect(screen.getByLabelText('外貌')).toBeInTheDocument()
    expect(screen.getByLabelText('性格')).toBeInTheDocument()
    expect(screen.getByLabelText('背景')).toBeInTheDocument()
  })

  it('手动添加角色成功后刷新列表', async () => {
    mockApi.getCharacters
      .mockResolvedValueOnce([])
      .mockResolvedValueOnce([{ id: 'char-new', name: '王五', appearance: '', personality: '', background: '', image_prompt: '' }])
    mockApi.createCharacter.mockResolvedValueOnce({ id: 'char-new', name: '王五', appearance: '', personality: '', background: '', image_prompt: '' })

    renderPage()

    await waitFor(() => {
      expect(screen.getByText(/暂无角色/)).toBeInTheDocument()
    })

    fireEvent.click(screen.getByLabelText('手动添加角色'))
    fireEvent.change(screen.getByLabelText('名称'), { target: { value: '王五' } })
    fireEvent.click(screen.getByText('保存'))

    await waitFor(() => {
      expect(mockApi.createCharacter).toHaveBeenCalledWith('proj-1', expect.objectContaining({ name: '王五' }))
    })
    await waitFor(() => {
      expect(screen.getByText('王五')).toBeInTheDocument()
    })
  })

  it('编辑角色信息并保存', async () => {
    mockApi.getCharacters
      .mockResolvedValueOnce(sampleChars)
      .mockResolvedValueOnce([
        { ...sampleChars[0], appearance: '白发' },
        sampleChars[1]
      ])
    mockApi.updateCharacter.mockResolvedValueOnce({ ...sampleChars[0], appearance: '白发' })

    renderPage()

    await waitFor(() => {
      expect(screen.getByText('张三')).toBeInTheDocument()
    })

    fireEvent.click(screen.getByLabelText('编辑 张三'))

    const appearanceInput = screen.getByLabelText('外貌')
    fireEvent.change(appearanceInput, { target: { value: '白发' } })
    fireEvent.click(screen.getByText('保存'))

    await waitFor(() => {
      expect(mockApi.updateCharacter).toHaveBeenCalledWith('proj-1', 'char-1', expect.objectContaining({ appearance: '白发' }))
    })
  })

  it('删除角色后刷新列表', async () => {
    mockApi.getCharacters
      .mockResolvedValueOnce(sampleChars)
      .mockResolvedValueOnce([sampleChars[1]])
    mockApi.deleteCharacter.mockResolvedValueOnce(undefined)

    renderPage()

    await waitFor(() => {
      expect(screen.getByText('张三')).toBeInTheDocument()
    })

    fireEvent.click(screen.getByLabelText('删除 张三'))

    await waitFor(() => {
      expect(mockApi.deleteCharacter).toHaveBeenCalledWith('proj-1', 'char-1')
    })
    await waitFor(() => {
      expect(screen.queryByText('张三')).not.toBeInTheDocument()
    })
  })

  it('确认角色按钮调用 API', async () => {
    mockApi.getCharacters.mockResolvedValueOnce(sampleChars)
    mockApi.confirmCharacters.mockResolvedValueOnce({ message: '角色已确认', count: 2 })

    renderPage()

    await waitFor(() => {
      expect(screen.getByText('张三')).toBeInTheDocument()
    })

    fireEvent.click(screen.getByLabelText('确认所有角色'))

    await waitFor(() => {
      expect(mockApi.confirmCharacters).toHaveBeenCalledWith('proj-1')
    })
  })

  it('没有角色时确认按钮禁用', async () => {
    mockApi.getCharacters.mockResolvedValueOnce([])

    renderPage()

    await waitFor(() => {
      expect(screen.getByText(/暂无角色/)).toBeInTheDocument()
    })

    expect(screen.getByLabelText('确认所有角色')).toBeDisabled()
  })

  it('取消编辑恢复显示模式', async () => {
    mockApi.getCharacters.mockResolvedValueOnce(sampleChars)

    renderPage()

    await waitFor(() => {
      expect(screen.getByText('张三')).toBeInTheDocument()
    })

    fireEvent.click(screen.getByLabelText('编辑 张三'))
    expect(screen.getByLabelText('名称')).toBeInTheDocument()

    fireEvent.click(screen.getByText('取消'))
    // Should be back to display mode
    await waitFor(() => {
      expect(screen.queryByLabelText('名称')).not.toBeInTheDocument()
    })
  })

  it('取消添加表单隐藏表单', async () => {
    mockApi.getCharacters.mockResolvedValueOnce([])

    renderPage()

    await waitFor(() => {
      expect(screen.getByText(/暂无角色/)).toBeInTheDocument()
    })

    fireEvent.click(screen.getByLabelText('手动添加角色'))
    expect(screen.getByText('添加新角色')).toBeInTheDocument()

    // Click the cancel button inside the add form
    const cancelButtons = screen.getAllByText('取消')
    fireEvent.click(cancelButtons[0])

    expect(screen.queryByText('添加新角色')).not.toBeInTheDocument()
  })
})
