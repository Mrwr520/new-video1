import { render, screen, waitFor } from '@testing-library/react'
import { describe, it, expect, vi } from 'vitest'
import { MemoryRouter, Routes, Route } from 'react-router-dom'
import { ProjectListPage } from './pages/ProjectListPage'
import { ProjectWorkbench } from './pages/ProjectWorkbench'
import { TextInputPage } from './pages/TextInputPage'
import { CharacterManagePage } from './pages/CharacterManagePage'
import { StoryboardPage } from './pages/StoryboardPage'
import { VideoPreviewPage } from './pages/VideoPreviewPage'
import { SettingsPage } from './pages/SettingsPage'

// Mock apiClient 以避免异步加载阻塞路由测试
vi.mock('./services/api-client', async () => {
  const actual = await vi.importActual('./services/api-client')
  return {
    ...actual,
    apiClient: {
      listProjects: vi.fn().mockResolvedValue([]),
      getProject: vi.fn().mockResolvedValue({ id: 'test', name: 'Test', status: 'created' }),
      getCharacters: vi.fn().mockResolvedValue([]),
      getScenes: vi.fn().mockResolvedValue([]),
      listTTSEngines: vi.fn().mockResolvedValue([]),
      listTTSVoices: vi.fn().mockResolvedValue([]),
      generateSpeech: vi.fn().mockResolvedValue({ audio_path: '' }),
      getFileUrl: vi.fn().mockReturnValue(''),
      exportVideo: vi.fn().mockResolvedValue({ video_path: '' }),
      submitText: vi.fn().mockResolvedValue({ status: 'valid', message: '', char_count: 0 }),
      getPipelineStatus: vi.fn().mockResolvedValue({ current_step: null, progress: 0, step_detail: '', estimated_remaining: 0 }),
    }
  }
})

// 辅助函数：渲染指定路由
function renderWithRouter(initialRoute: string) {
  return render(
    <MemoryRouter initialEntries={[initialRoute]}>
      <Routes>
        <Route path="/" element={<ProjectListPage />} />
        <Route path="/project/:id" element={<ProjectWorkbench />} />
        <Route path="/project/:id/text" element={<TextInputPage />} />
        <Route path="/project/:id/chars" element={<CharacterManagePage />} />
        <Route path="/project/:id/story" element={<StoryboardPage />} />
        <Route path="/project/:id/preview" element={<VideoPreviewPage />} />
        <Route path="/settings" element={<SettingsPage />} />
      </Routes>
    </MemoryRouter>
  )
}

describe('页面路由', () => {
  it('/ 渲染项目列表页', () => {
    renderWithRouter('/')
    expect(screen.getByText('项目列表')).toBeInTheDocument()
  })

  it('/project/:id 渲染项目工作台', () => {
    renderWithRouter('/project/test-123')
    expect(screen.getByText('项目工作台')).toBeInTheDocument()
    expect(screen.getByText('项目 ID: test-123')).toBeInTheDocument()
  })

  it('/project/:id/text 渲染文本输入页', () => {
    renderWithRouter('/project/abc/text')
    expect(screen.getByText('文本输入')).toBeInTheDocument()
  })

  it('/project/:id/chars 渲染角色管理页', async () => {
    renderWithRouter('/project/abc/chars')
    expect(await screen.findByText('角色管理')).toBeInTheDocument()
  })

  it('/project/:id/story 渲染分镜编辑页', async () => {
    renderWithRouter('/project/abc/story')
    expect(await screen.findByText('分镜编辑')).toBeInTheDocument()
  })

  it('/project/:id/preview 渲染视频预览页', async () => {
    renderWithRouter('/project/abc/preview')
    expect(await screen.findByText('视频预览')).toBeInTheDocument()
  })

  it('/settings 渲染设置页', () => {
    renderWithRouter('/settings')
    expect(screen.getByText('设置')).toBeInTheDocument()
  })
})
