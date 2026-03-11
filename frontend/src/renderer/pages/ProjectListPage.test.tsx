import { render, screen, waitFor, fireEvent } from '@testing-library/react'
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { MemoryRouter } from 'react-router-dom'
import { ProjectListPage } from './ProjectListPage'

// mock useNavigate
const mockNavigate = vi.fn()
vi.mock('react-router-dom', async () => {
  const actual = await vi.importActual('react-router-dom')
  return { ...actual, useNavigate: () => mockNavigate }
})

// mock apiClient
vi.mock('../services/api-client', async () => {
  const actual = await vi.importActual('../services/api-client')
  return {
    ...actual,
    apiClient: {
      listProjects: vi.fn(),
      createProject: vi.fn(),
      getProject: vi.fn(),
      deleteProject: vi.fn()
    }
  }
})

import { apiClient } from '../services/api-client'
const mockApi = apiClient as unknown as {
  listProjects: ReturnType<typeof vi.fn>
  createProject: ReturnType<typeof vi.fn>
}

function renderPage(): void {
  render(
    <MemoryRouter>
      <ProjectListPage />
    </MemoryRouter>
  )
}

describe('ProjectListPage', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  it('加载时显示加载状态，然后展示项目列表', async () => {
    mockApi.listProjects.mockResolvedValueOnce([
      {
        id: '1', name: '我的动漫项目', template_id: 'anime', source_text: null,
        status: 'created', current_step: null,
        created_at: '2024-06-01T10:00:00Z', updated_at: '2024-06-01T10:00:00Z'
      },
      {
        id: '2', name: '科普视频', template_id: 'science', source_text: null,
        status: 'processing', current_step: 'character_extraction',
        created_at: '2024-06-02T12:00:00Z', updated_at: '2024-06-02T12:00:00Z'
      }
    ])

    renderPage()

    // 加载中
    expect(screen.getByText('加载中...')).toBeInTheDocument()

    // 等待项目列表渲染
    await waitFor(() => {
      expect(screen.getByText('我的动漫项目')).toBeInTheDocument()
    })
    expect(screen.getByText('科普视频')).toBeInTheDocument()
    expect(screen.getByText('已创建')).toBeInTheDocument()
    expect(screen.getByText('处理中')).toBeInTheDocument()
  })

  it('空项目列表时显示提示文字', async () => {
    mockApi.listProjects.mockResolvedValueOnce([])

    renderPage()

    await waitFor(() => {
      expect(screen.getByText(/暂无项目/)).toBeInTheDocument()
    })
  })

  it('加载失败时显示错误信息', async () => {
    mockApi.listProjects.mockRejectedValueOnce(new Error('网络错误'))

    renderPage()

    await waitFor(() => {
      expect(screen.getByText('网络错误')).toBeInTheDocument()
    })
  })

  it('点击"创建项目"按钮打开对话框', async () => {
    mockApi.listProjects.mockResolvedValueOnce([])

    renderPage()

    await waitFor(() => {
      expect(screen.getByText(/暂无项目/)).toBeInTheDocument()
    })

    fireEvent.click(screen.getByText('创建项目'))
    expect(screen.getByRole('dialog')).toBeInTheDocument()
    expect(screen.getByLabelText('项目名称')).toBeInTheDocument()
    expect(screen.getByLabelText('内容类型')).toBeInTheDocument()
  })

  it('创建项目成功后导航到项目工作台', async () => {
    mockApi.listProjects.mockResolvedValueOnce([])
    mockApi.createProject.mockResolvedValueOnce({
      id: 'new-id', name: '新项目', template_id: 'anime', source_text: null,
      status: 'created', current_step: null,
      created_at: '2024-06-01T00:00:00Z', updated_at: '2024-06-01T00:00:00Z'
    })

    renderPage()

    await waitFor(() => {
      expect(screen.getByText(/暂无项目/)).toBeInTheDocument()
    })

    // 打开对话框
    fireEvent.click(screen.getByText('创建项目'))

    // 填写表单
    fireEvent.change(screen.getByLabelText('项目名称'), { target: { value: '新项目' } })
    fireEvent.change(screen.getByLabelText('内容类型'), { target: { value: 'anime' } })

    // 提交
    fireEvent.click(screen.getByRole('button', { name: '创建' }))

    await waitFor(() => {
      expect(mockApi.createProject).toHaveBeenCalledWith({ name: '新项目', template_id: 'anime' })
    })
    await waitFor(() => {
      expect(mockNavigate).toHaveBeenCalledWith('/project/new-id')
    })
  })

  it('项目名称为空时显示校验错误', async () => {
    mockApi.listProjects.mockResolvedValueOnce([])

    renderPage()

    await waitFor(() => {
      expect(screen.getByText(/暂无项目/)).toBeInTheDocument()
    })

    fireEvent.click(screen.getByText('创建项目'))
    // 不填名称直接提交
    fireEvent.click(screen.getByRole('button', { name: '创建' }))

    await waitFor(() => {
      expect(screen.getByText('请输入项目名称')).toBeInTheDocument()
    })
    expect(mockApi.createProject).not.toHaveBeenCalled()
  })

  it('取消按钮关闭对话框', async () => {
    mockApi.listProjects.mockResolvedValueOnce([])

    renderPage()

    await waitFor(() => {
      expect(screen.getByText(/暂无项目/)).toBeInTheDocument()
    })

    fireEvent.click(screen.getByText('创建项目'))
    expect(screen.getByRole('dialog')).toBeInTheDocument()

    fireEvent.click(screen.getByRole('button', { name: '取消' }))
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument()
  })

  it('页面标题和设置链接存在', async () => {
    mockApi.listProjects.mockResolvedValueOnce([])

    renderPage()

    expect(screen.getByText('项目列表')).toBeInTheDocument()
    expect(screen.getByText('设置')).toBeInTheDocument()
  })
})
