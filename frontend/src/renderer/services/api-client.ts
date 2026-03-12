/**
 * API 客户端 - 与 Python 后端通信
 */

// 项目相关类型
export interface Project {
  id: string
  name: string
  template_id: string
  source_text: string | null
  status: string
  current_step: string | null
  created_at: string
  updated_at: string
}

export interface CreateProjectRequest {
  name: string
  template_id: string
}

export interface ProjectListResponse {
  projects: Project[]
  total: number
}

// 文本提交相关类型
export interface SubmitTextRequest {
  text: string
  filename?: string
}

export interface TextValidationResponse {
  status: 'valid' | 'invalid'
  message: string
  char_count: number
}

// 角色相关类型
export interface Character {
  id: string
  name: string
  appearance: string
  personality: string
  background: string
  image_prompt: string
}

export interface CharacterUpdate {
  name?: string
  appearance?: string
  personality?: string
  background?: string
  image_prompt?: string
}

// 分镜相关类型
export interface StoryboardScene {
  id: string
  order: number
  scene_description: string
  dialogue: string
  camera_direction: string
  image_prompt: string
  motion_prompt: string
  keyframe_path: string | null
  video_path: string | null
  audio_path: string | null
}

export interface SceneUpdate {
  scene_description?: string
  dialogue?: string
  camera_direction?: string
  image_prompt?: string
  motion_prompt?: string
}

export interface RegenerateVideoRequest {
  duration?: number
  fps?: number
  use_teacache?: boolean
}

// TTS 相关类型
export interface TTSEngineInfo {
  name: string
  display_name: string
  is_paid: boolean
  supported_languages: string[]
  requires_api_key: boolean
  description: string
}

export interface TTSVoiceInfo {
  id: string
  name: string
  language: string
  gender: string
  preview_url: string | null
}

export interface GenerateSpeechRequest {
  engine?: string
  voice_id?: string
}

export interface GenerateSpeechResponse {
  audio_path: string
  scene_id: string
  engine: string
  voice_id: string
}

// 导出相关类型
export interface ExportRequest {
  resolution_width?: number
  resolution_height?: number
  fps?: number
  codec?: string
  bitrate?: string
}

export interface ExportResponse {
  video_path: string
  message: string
}

export interface ExportErrorDetail {
  code: string
  message: string
  detail?: string
  retryable: boolean
}

// API 错误类型
export class ApiError extends Error {
  constructor(
    public status: number,
    public detail: string
  ) {
    super(detail)
    this.name = 'ApiError'
  }
}

// API 客户端类
export class ApiClient {
  private baseUrl: string

  constructor(baseUrl: string = 'http://localhost:8000') {
    this.baseUrl = baseUrl
  }

  private async request<T>(path: string, options?: RequestInit): Promise<T> {
    const url = `${this.baseUrl}${path}`
    const res = await fetch(url, {
      headers: { 'Content-Type': 'application/json' },
      ...options
    })
    if (!res.ok) {
      const body = await res.json().catch(() => ({ detail: res.statusText }))
      throw new ApiError(res.status, body.detail || res.statusText)
    }
    // 204 No Content 不解析 body
    if (res.status === 204) return undefined as T
    return res.json()
  }

  /** 创建项目 */
  async createProject(data: CreateProjectRequest): Promise<Project> {
    return this.request<Project>('/api/projects', {
      method: 'POST',
      body: JSON.stringify(data)
    })
  }

  /** 获取项目列表 */
  async listProjects(): Promise<Project[]> {
    const res = await this.request<ProjectListResponse>('/api/projects')
    return res.projects
  }

  /** 获取项目详情 */
  async getProject(id: string): Promise<Project> {
    return this.request<Project>(`/api/projects/${id}`)
  }

  /** 删除项目 */
  async deleteProject(id: string): Promise<void> {
    return this.request<void>(`/api/projects/${id}`, { method: 'DELETE' })
  }

  /** 提交文本内容 */
  async submitText(projectId: string, data: SubmitTextRequest): Promise<TextValidationResponse> {
    return this.request<TextValidationResponse>(`/api/projects/${projectId}/text`, {
      method: 'POST',
      body: JSON.stringify(data)
    })
  }

  /** 获取角色列表 */
  async getCharacters(projectId: string): Promise<Character[]> {
    return this.request<Character[]>(`/api/projects/${projectId}/characters`)
  }

  /** 手动添加角色 */
  async createCharacter(projectId: string, data: CharacterUpdate): Promise<Character> {
    return this.request<Character>(`/api/projects/${projectId}/characters`, {
      method: 'POST',
      body: JSON.stringify(data)
    })
  }

  /** 更新角色 */
  async updateCharacter(projectId: string, charId: string, data: CharacterUpdate): Promise<Character> {
    return this.request<Character>(`/api/projects/${projectId}/characters/${charId}`, {
      method: 'PUT',
      body: JSON.stringify(data)
    })
  }

  /** 删除角色 */
  async deleteCharacter(projectId: string, charId: string): Promise<void> {
    return this.request<void>(`/api/projects/${projectId}/characters/${charId}`, {
      method: 'DELETE'
    })
  }

  /** 确认角色 */
  async confirmCharacters(projectId: string): Promise<{ message: string; count: number }> {
    return this.request<{ message: string; count: number }>(`/api/projects/${projectId}/confirm-characters`, {
      method: 'POST'
    })
  }

  /** 获取分镜列表 */
  async getScenes(projectId: string): Promise<StoryboardScene[]> {
    return this.request<StoryboardScene[]>(`/api/projects/${projectId}/scenes`)
  }

  /** 添加分镜 */
  async createScene(projectId: string, data: SceneUpdate): Promise<StoryboardScene> {
    return this.request<StoryboardScene>(`/api/projects/${projectId}/scenes`, {
      method: 'POST',
      body: JSON.stringify(data)
    })
  }

  /** 更新分镜 */
  async updateScene(projectId: string, sceneId: string, data: SceneUpdate): Promise<StoryboardScene> {
    return this.request<StoryboardScene>(`/api/projects/${projectId}/scenes/${sceneId}`, {
      method: 'PUT',
      body: JSON.stringify(data)
    })
  }

  /** 重排分镜 */
  async reorderScenes(projectId: string, sceneIds: string[]): Promise<StoryboardScene[]> {
    return this.request<StoryboardScene[]>(`/api/projects/${projectId}/scenes/reorder`, {
      method: 'PUT',
      body: JSON.stringify({ scene_ids: sceneIds })
    })
  }

  /** 删除分镜 */
  async deleteScene(projectId: string, sceneId: string): Promise<void> {
    return this.request<void>(`/api/projects/${projectId}/scenes/${sceneId}`, {
      method: 'DELETE'
    })
  }

  /** 确认分镜 */
  async confirmStoryboard(projectId: string): Promise<{ message: string; count: number }> {
    return this.request<{ message: string; count: number }>(`/api/projects/${projectId}/confirm-storyboard`, {
      method: 'POST'
    })
  }

  /** 重新生成关键帧 */
  async regenerateKeyframe(projectId: string, sceneId: string): Promise<StoryboardScene> {
    return this.request<StoryboardScene>(`/api/projects/${projectId}/scenes/${sceneId}/regenerate-keyframe`, {
      method: 'POST'
    })
  }

  /** 重新生成视频片段 */
  async regenerateVideo(projectId: string, sceneId: string, options?: RegenerateVideoRequest): Promise<StoryboardScene> {
    return this.request<StoryboardScene>(`/api/projects/${projectId}/scenes/${sceneId}/regenerate-video`, {
      method: 'POST',
      body: JSON.stringify(options ?? {})
    })
  }

  /** 获取 TTS 引擎列表 */
  async listTTSEngines(): Promise<TTSEngineInfo[]> {
    return this.request<TTSEngineInfo[]>('/api/tts/engines')
  }

  /** 获取指定引擎的语音列表 */
  async listTTSVoices(engine: string): Promise<TTSVoiceInfo[]> {
    return this.request<TTSVoiceInfo[]>(`/api/tts/engines/${engine}/voices`)
  }

  /** 为分镜生成语音 */
  async generateSpeech(projectId: string, sceneId: string, options?: GenerateSpeechRequest): Promise<GenerateSpeechResponse> {
    return this.request<GenerateSpeechResponse>(`/api/projects/${projectId}/scenes/${sceneId}/generate-speech`, {
      method: 'POST',
      body: JSON.stringify(options ?? {})
    })
  }

  /** 导出视频 */
  async exportVideo(projectId: string, options?: ExportRequest): Promise<ExportResponse> {
    return this.request<ExportResponse>(`/api/projects/${projectId}/export`, {
      method: 'POST',
      body: JSON.stringify(options ?? {})
    })
  }

  /** 获取项目文件 URL */
  getFileUrl(projectId: string, filePath: string): string {
    return `${this.baseUrl}/api/projects/${projectId}/files/${filePath}`
  }
}

// 默认客户端实例
export const apiClient = new ApiClient()
