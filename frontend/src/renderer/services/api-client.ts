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

// Pipeline 相关类型
export interface PipelineStatusResponse {
  current_step: string | null
  progress: number
  step_detail: string
  estimated_remaining: number
  is_running: boolean
  is_waiting_confirmation: boolean
  error_message: string | null
  steps: Record<string, PipelineStepState>
}

export interface PipelineStepState {
  status: string
  progress: number
  error_message: string | null
  started_at: string | null
  completed_at: string | null
}

export interface PipelineEvent {
  type: string
  project_id: string
  step?: string
  step_description?: string
  progress?: number
  error?: string
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

// 配置相关类型
export interface AppConfig {
  python_path: string
  gpu_device: number
  backend_port: number
  llm_api_key: string
  llm_api_url: string
  image_gen_mode: string
  image_gen_api_key: string
  image_gen_api_url: string
  tts_engine: string
  fish_audio_api_key: string
  cosyvoice_api_key: string
  minimax_api_key: string
  minimax_group_id: string
  volcengine_access_token: string
  volcengine_app_id: string
}

export interface AppConfigUpdate {
  python_path?: string
  gpu_device?: number
  backend_port?: number
  llm_api_key?: string
  llm_api_url?: string
  image_gen_mode?: string
  image_gen_api_key?: string
  image_gen_api_url?: string
  tts_engine?: string
  fish_audio_api_key?: string
  cosyvoice_api_key?: string
  minimax_api_key?: string
  minimax_group_id?: string
  volcengine_access_token?: string
  volcengine_app_id?: string
}

// 剧本优化相关类型
export interface ScriptOptimizationVersion {
  session_id: string
  iteration: number
  script: string
  evaluation: {
    total_score: number
    dimension_scores: {
      content_quality: number
      structure: number
      creativity: number
      hotspot_relevance: number
      technique_application: number
    }
    suggestions: string[]
    timestamp: string
  }
  hotspots: Array<{
    title: string
    description: string
    source: string
    relevance_score: number
    timestamp: string
  }>
  techniques: Array<{
    name: string
    description: string
    example: string
    category: string
    source: string
  }>
  timestamp: string
  is_final: boolean
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

// 模型管理相关类型
export interface ModelInfo {
  id: string
  name: string
  description: string
  hf_repo_id: string
  estimated_size_gb: number
  min_vram_gb: number
  status: 'not_downloaded' | 'downloading' | 'downloaded' | 'loading' | 'loaded' | 'error'
  download_progress: number
  error_message: string
  local_path: string
}

export interface ModelsListResponse {
  models: ModelInfo[]
  cache_size_gb: number
  active_model: string | null
}

export interface GPUInfo {
  available: boolean
  device_count?: number
  devices?: Array<{
    index: number
    name: string
    total_memory_gb: number
    free_memory_gb: number
  }>
  cuda_version?: string
  error?: string
}

// 环境检测相关类型
export interface PackageStatus {
  name: string
  display_name: string
  installed: boolean
  version: string | null
  required: boolean
  description: string
}

export interface NvidiaSmiGPU {
  index: number
  name: string
  driver_version: string
  total_memory_mb: number
  free_memory_mb: number
  used_memory_mb: number
  cuda_version: string
}

export interface EnvironmentCheckResponse {
  python_version: string
  python_path: string
  gpu_detected: boolean
  gpu_info: NvidiaSmiGPU[] | null
  gpu_error: string | null
  nvidia_driver_version: string | null
  cuda_version_from_driver: string | null
  packages: PackageStatus[]
  all_installed: boolean
  recommended_torch_index_url: string | null
}

export interface InstallStatusResponse {
  running: boolean
  log: string[]
  success: boolean | null
  message: string
}

// API 客户端类
export class ApiClient {
  private baseUrl: string

  constructor(baseUrl: string = 'http://127.0.0.1:8000') {
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
      const detail = body.detail
      const message = typeof detail === 'string'
        ? detail
        : detail?.message || detail?.detail || JSON.stringify(detail) || res.statusText
      throw new ApiError(res.status, message)
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

  /** 启动 Pipeline */
  async startPipeline(projectId: string): Promise<{ message: string; project_id: string }> {
    return this.request<{ message: string; project_id: string }>(`/api/projects/${projectId}/start`, {
      method: 'POST'
    })
  }

  /** 取消 Pipeline */
  async cancelPipeline(projectId: string): Promise<{ message: string; project_id: string }> {
    return this.request<{ message: string; project_id: string }>(`/api/projects/${projectId}/cancel`, {
      method: 'POST'
    })
  }

  /** 获取 Pipeline 状态 */
  async getPipelineStatus(projectId: string): Promise<PipelineStatusResponse> {
    return this.request<PipelineStatusResponse>(`/api/projects/${projectId}/pipeline-status`)
  }

  /**
   * 订阅 Pipeline SSE 事件流
   * Returns an EventSource that emits pipeline progress events.
   * Caller is responsible for closing the EventSource when done.
   */
  subscribePipelineEvents(projectId: string): EventSource {
    const url = `${this.baseUrl}/api/projects/${projectId}/events`
    return new EventSource(url)
  }

  /** 获取应用配置 */
  async getConfig(): Promise<AppConfig> {
    return this.request<AppConfig>('/api/config')
  }

  /** 更新应用配置（支持部分更新） */
  async updateConfig(data: AppConfigUpdate): Promise<AppConfig> {
    return this.request<AppConfig>('/api/config', {
      method: 'PUT',
      body: JSON.stringify(data)
    })
  }

  // ----------------------------------------------------------
  // 模型管理
  // ----------------------------------------------------------

  /** 获取所有模型列表及状态 */
  async listModels(): Promise<ModelsListResponse> {
    return this.request<ModelsListResponse>('/api/models')
  }

  /** 获取单个模型信息 */
  async getModel(modelId: string): Promise<ModelInfo> {
    return this.request<ModelInfo>(`/api/models/${modelId}`)
  }

  /** 触发模型下载 */
  async downloadModel(modelId: string): Promise<{ message: string; status: string }> {
    return this.request<{ message: string; status: string }>(`/api/models/${modelId}/download`, {
      method: 'POST'
    })
  }

  /** 删除本地缓存的模型 */
  async deleteModel(modelId: string): Promise<{ message: string }> {
    return this.request<{ message: string }>(`/api/models/${modelId}`, {
      method: 'DELETE'
    })
  }

  /** 获取 GPU 信息 */
  async getGPUInfo(): Promise<GPUInfo> {
    return this.request<GPUInfo>('/api/gpu')
  }

  // ----------------------------------------------------------
  // 环境检测与依赖安装
  // ----------------------------------------------------------

  /** 检测 Python 环境（GPU、依赖包） */
  async checkEnvironment(): Promise<EnvironmentCheckResponse> {
    return this.request<EnvironmentCheckResponse>('/api/environment/check')
  }

  /** 安装缺失依赖 */
  async installPackages(packages?: string[], cudaVersion?: string): Promise<{ message: string }> {
    return this.request<{ message: string }>('/api/environment/install', {
      method: 'POST',
      body: JSON.stringify({ packages: packages || [], cuda_version: cudaVersion || null })
    })
  }

  /** 查询安装进度 */
  async getInstallStatus(): Promise<InstallStatusResponse> {
    return this.request<InstallStatusResponse>('/api/environment/install-status')
  }

  // ----------------------------------------------------------
  // 剧本迭代优化
  // ----------------------------------------------------------

  /** 启动剧本优化流程 */
  async startScriptOptimization(data: {
    initial_prompt: string
    target_score?: number
    max_iterations?: number
  }): Promise<{ session_id: string; status: string; message: string }> {
    return this.request<{ session_id: string; status: string; message: string }>(
      '/api/script-optimization/start',
      { method: 'POST', body: JSON.stringify(data) }
    )
  }

  /** 查询优化会话状态 */
  async getOptimizationStatus(sessionId: string): Promise<{
    id: string
    initial_prompt: string
    target_score: number
    max_iterations: number
    status: string
    created_at: string
    completed_at: string | null
  }> {
    return this.request(`/api/script-optimization/${sessionId}/status`)
  }

  /** 获取优化会话的版本历史 */
  async getOptimizationVersions(sessionId: string): Promise<{
    session_id: string
    versions: ScriptOptimizationVersion[]
    total: number
  }> {
    return this.request(`/api/script-optimization/${sessionId}/versions`)
  }

  /** 获取特定迭代版本 */
  async getOptimizationVersion(sessionId: string, iteration: number): Promise<ScriptOptimizationVersion> {
    return this.request(`/api/script-optimization/${sessionId}/versions/${iteration}`)
  }

  /** 获取 WebSocket URL for 优化进度 */
  getOptimizationWsUrl(sessionId: string): string {
    const wsBase = this.baseUrl.replace(/^http/, 'ws')
    return `${wsBase}/ws/script-optimization/${sessionId}`
  }
}

// 默认客户端实例
export const apiClient = new ApiClient()
