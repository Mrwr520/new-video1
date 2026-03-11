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
}

// 默认客户端实例
export const apiClient = new ApiClient()
