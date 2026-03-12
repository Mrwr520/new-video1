import { render, screen, waitFor, fireEvent } from '@testing-library/react'
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { StoryboardPage } from './StoryboardPage'

vi.mock('../services/api-client', async () => {
  const actual = await vi.importActual('../services/api-client')
  return {
    ...actual,
    apiClient: {
      getScenes: vi.fn(),
      createScene: vi.fn(),
      updateScene: vi.fn(),
      deleteScene: vi.fn(),
      reorderScenes: vi.fn(),
      confirmStoryboard: vi.fn(),
      regenerateKeyframe: vi.fn(),
      listTTSEngines: vi.fn().mockResolvedValue([]),
      listTTSVoices: vi.fn().mockResolvedValue([]),
      generateSpeech: vi.fn().mockResolvedValue({ audio_path: '' })
    }
  }
})

import { apiClient } from '../services/api-client'
const mockApi = apiClient as unknown as {
  getScenes: ReturnType<typeof vi.fn>
  createScene: ReturnType<typeof vi.fn>
  updateScene: ReturnType<typeof vi.fn>
  deleteScene: ReturnType<typeof vi.fn>
  reorderScenes: ReturnType<typeof vi.fn>
  confirmStoryboard: ReturnType<typeof vi.fn>
  regenerateKeyframe: ReturnType<typeof vi.fn>
}

const sampleScenes = [
  {
    id: 'scene-1', order: 1, scene_description: '城市远景',
    dialogue: '故事开始', camera_direction: '远景',
    image_prompt: '', motion_prompt: '', keyframe_path: null
  },
  {
    id: 'scene-2', order: 2, scene_description: '室内场景',
    dialogue: '你好', camera_direction: '近景',
    image_prompt: '', motion_prompt: '',
    keyframe_path: '/projects/proj-1/keyframes/scene_scene-2.png'
  }
]

function renderPage(): void {
  render(
    <MemoryRouter initialEntries={['/project/proj-1/story']}>
      <Routes>
        <Route path="/project/:id/story" element={<StoryboardPage />} />
      </Routes>
    </MemoryRouter>
  )
}

describe('StoryboardPage - 关键帧功能', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  it('无关键帧时显示"暂无关键帧"占位', async () => {
    mockApi.getScenes.mockResolvedValueOnce([sampleScenes[0]])
    renderPage()

    await waitFor(() => {
      expect(screen.getByTestId('keyframe-empty-scene-1')).toHaveTextContent('暂无关键帧')
    })
  })

  it('有关键帧时显示图片', async () => {
    mockApi.getScenes.mockResolvedValueOnce([sampleScenes[1]])
    renderPage()

    await waitFor(() => {
      const img = screen.getByTestId('keyframe-image-scene-2')
      expect(img).toBeTruthy()
      expect(img.tagName).toBe('IMG')
      expect(img.getAttribute('alt')).toBe('分镜 2 关键帧')
    })
  })

  it('无关键帧时按钮显示"生成关键帧"', async () => {
    mockApi.getScenes.mockResolvedValueOnce([sampleScenes[0]])
    renderPage()

    await waitFor(() => {
      expect(screen.getByLabelText('生成关键帧 1')).toBeInTheDocument()
    })
  })

  it('有关键帧时按钮显示"重新生成关键帧"', async () => {
    mockApi.getScenes.mockResolvedValueOnce([sampleScenes[1]])
    renderPage()

    await waitFor(() => {
      expect(screen.getByLabelText('重新生成关键帧 2')).toBeInTheDocument()
    })
  })

  it('点击生成关键帧按钮调用 API 并更新场景', async () => {
    mockApi.getScenes.mockResolvedValueOnce([sampleScenes[0]])
    const updatedScene = {
      ...sampleScenes[0],
      keyframe_path: '/projects/proj-1/keyframes/scene_scene-1.png'
    }
    mockApi.regenerateKeyframe.mockResolvedValueOnce(updatedScene)

    renderPage()

    await waitFor(() => {
      expect(screen.getByLabelText('生成关键帧 1')).toBeInTheDocument()
    })

    fireEvent.click(screen.getByLabelText('生成关键帧 1'))

    await waitFor(() => {
      expect(mockApi.regenerateKeyframe).toHaveBeenCalledWith('proj-1', 'scene-1')
    })

    // 生成完成后应显示图片
    await waitFor(() => {
      expect(screen.getByTestId('keyframe-image-scene-1')).toBeInTheDocument()
    })
  })

  it('生成中显示加载状态', async () => {
    mockApi.getScenes.mockResolvedValueOnce([sampleScenes[0]])
    // 让 regenerateKeyframe 永远不 resolve 来测试加载状态
    let resolvePromise: (value: unknown) => void
    mockApi.regenerateKeyframe.mockReturnValueOnce(
      new Promise(resolve => { resolvePromise = resolve })
    )

    renderPage()

    await waitFor(() => {
      expect(screen.getByLabelText('生成关键帧 1')).toBeInTheDocument()
    })

    fireEvent.click(screen.getByLabelText('生成关键帧 1'))

    await waitFor(() => {
      expect(screen.getByTestId('keyframe-loading-scene-1')).toHaveTextContent('关键帧生成中...')
    })

    // 按钮应显示"生成中..."且被禁用
    expect(screen.getByText('生成中...')).toBeDisabled()
  })

  it('生成失败时显示错误信息和重试按钮（Req 4.5）', async () => {
    mockApi.getScenes.mockResolvedValueOnce([sampleScenes[0]])
    mockApi.regenerateKeyframe.mockRejectedValueOnce(new Error('图像 API 超时'))

    renderPage()

    await waitFor(() => {
      expect(screen.getByLabelText('生成关键帧 1')).toBeInTheDocument()
    })

    fireEvent.click(screen.getByLabelText('生成关键帧 1'))

    await waitFor(() => {
      const errorEl = screen.getByTestId('keyframe-error-scene-1')
      expect(errorEl).toHaveTextContent('图像 API 超时')
    })

    // 应有重试按钮
    expect(screen.getByLabelText('重试生成关键帧 1')).toBeInTheDocument()
  })

  it('点击重试按钮重新调用 API', async () => {
    mockApi.getScenes.mockResolvedValueOnce([sampleScenes[0]])
    mockApi.regenerateKeyframe
      .mockRejectedValueOnce(new Error('超时'))
      .mockResolvedValueOnce({
        ...sampleScenes[0],
        keyframe_path: '/projects/proj-1/keyframes/scene_scene-1.png'
      })

    renderPage()

    await waitFor(() => {
      expect(screen.getByLabelText('生成关键帧 1')).toBeInTheDocument()
    })

    // 第一次失败
    fireEvent.click(screen.getByLabelText('生成关键帧 1'))
    await waitFor(() => {
      expect(screen.getByTestId('keyframe-error-scene-1')).toBeInTheDocument()
    })

    // 点击重试
    fireEvent.click(screen.getByLabelText('重试生成关键帧 1'))

    await waitFor(() => {
      expect(mockApi.regenerateKeyframe).toHaveBeenCalledTimes(2)
    })

    // 重试成功后显示图片
    await waitFor(() => {
      expect(screen.getByTestId('keyframe-image-scene-1')).toBeInTheDocument()
    })
  })
})
