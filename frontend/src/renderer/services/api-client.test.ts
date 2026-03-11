import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { ApiClient, ApiError } from './api-client'

// mock fetch
const mockFetch = vi.fn()
vi.stubGlobal('fetch', mockFetch)

describe('ApiClient', () => {
  let client: ApiClient

  beforeEach(() => {
    client = new ApiClient('http://localhost:8000')
    mockFetch.mockReset()
  })

  afterEach(() => {
    vi.restoreAllMocks()
  })

  // --- createProject ---
  describe('createProject', () => {
    it('发送 POST 请求并返回项目数据', async () => {
      const project = {
        id: 'abc-123',
        name: '测试项目',
        template_id: 'anime',
        source_text: null,
        status: 'created',
        current_step: null,
        created_at: '2024-01-01T00:00:00Z',
        updated_at: '2024-01-01T00:00:00Z'
      }
      mockFetch.mockResolvedValueOnce({
        ok: true,
        status: 201,
        json: () => Promise.resolve(project)
      })

      const result = await client.createProject({ name: '测试项目', template_id: 'anime' })

      expect(mockFetch).toHaveBeenCalledWith(
        'http://localhost:8000/api/projects',
        expect.objectContaining({
          method: 'POST',
          body: JSON.stringify({ name: '测试项目', template_id: 'anime' })
        })
      )
      expect(result).toEqual(project)
    })

    it('服务端返回错误时抛出 ApiError', async () => {
      mockFetch.mockResolvedValueOnce({
        ok: false,
        status: 422,
        statusText: 'Unprocessable Entity',
        json: () => Promise.resolve({ detail: '名称不能为空' })
      })

      const promise = client.createProject({ name: '', template_id: 'anime' })
      await expect(promise).rejects.toThrow(ApiError)

      // 再次验证错误消息
      mockFetch.mockResolvedValueOnce({
        ok: false,
        status: 422,
        statusText: 'Unprocessable Entity',
        json: () => Promise.resolve({ detail: '名称不能为空' })
      })
      await expect(client.createProject({ name: '', template_id: 'anime' }))
        .rejects.toThrow('名称不能为空')
    })
  })

  // --- listProjects ---
  describe('listProjects', () => {
    it('返回项目数组', async () => {
      const projects = [
        {
          id: '1', name: 'P1', template_id: 'anime', source_text: null,
          status: 'created', current_step: null,
          created_at: '2024-01-01T00:00:00Z', updated_at: '2024-01-01T00:00:00Z'
        }
      ]
      mockFetch.mockResolvedValueOnce({
        ok: true,
        status: 200,
        json: () => Promise.resolve({ projects, total: 1 })
      })

      const result = await client.listProjects()
      expect(result).toEqual(projects)
      expect(mockFetch).toHaveBeenCalledWith(
        'http://localhost:8000/api/projects',
        expect.objectContaining({ headers: { 'Content-Type': 'application/json' } })
      )
    })

    it('空列表时返回空数组', async () => {
      mockFetch.mockResolvedValueOnce({
        ok: true,
        status: 200,
        json: () => Promise.resolve({ projects: [], total: 0 })
      })

      const result = await client.listProjects()
      expect(result).toEqual([])
    })
  })

  // --- getProject ---
  describe('getProject', () => {
    it('返回单个项目', async () => {
      const project = {
        id: 'abc', name: 'Test', template_id: 'science', source_text: null,
        status: 'created', current_step: null,
        created_at: '2024-01-01T00:00:00Z', updated_at: '2024-01-01T00:00:00Z'
      }
      mockFetch.mockResolvedValueOnce({
        ok: true,
        status: 200,
        json: () => Promise.resolve(project)
      })

      const result = await client.getProject('abc')
      expect(result).toEqual(project)
      expect(mockFetch).toHaveBeenCalledWith(
        'http://localhost:8000/api/projects/abc',
        expect.anything()
      )
    })

    it('项目不存在时抛出 404 错误', async () => {
      mockFetch.mockResolvedValueOnce({
        ok: false,
        status: 404,
        statusText: 'Not Found',
        json: () => Promise.resolve({ detail: '项目不存在' })
      })

      await expect(client.getProject('nonexistent')).rejects.toThrow(ApiError)
    })
  })

  // --- deleteProject ---
  describe('deleteProject', () => {
    it('发送 DELETE 请求，204 成功', async () => {
      mockFetch.mockResolvedValueOnce({
        ok: true,
        status: 204,
        json: () => Promise.reject(new Error('no body'))
      })

      await expect(client.deleteProject('abc')).resolves.toBeUndefined()
      expect(mockFetch).toHaveBeenCalledWith(
        'http://localhost:8000/api/projects/abc',
        expect.objectContaining({ method: 'DELETE' })
      )
    })

    it('删除不存在的项目时抛出错误', async () => {
      mockFetch.mockResolvedValueOnce({
        ok: false,
        status: 404,
        statusText: 'Not Found',
        json: () => Promise.resolve({ detail: '项目不存在' })
      })

      await expect(client.deleteProject('nonexistent')).rejects.toThrow(ApiError)
    })
  })

  // --- submitText ---
  describe('submitText', () => {
    it('发送 POST 请求并返回校验结果', async () => {
      const response = { status: 'valid', message: '校验通过', char_count: 50 }
      mockFetch.mockResolvedValueOnce({
        ok: true,
        status: 200,
        json: () => Promise.resolve(response)
      })

      const result = await client.submitText('proj-1', { text: '这是一段测试文本' })

      expect(mockFetch).toHaveBeenCalledWith(
        'http://localhost:8000/api/projects/proj-1/text',
        expect.objectContaining({
          method: 'POST',
          body: JSON.stringify({ text: '这是一段测试文本' })
        })
      )
      expect(result).toEqual(response)
    })

    it('带文件名时包含 filename 字段', async () => {
      const response = { status: 'valid', message: '校验通过', char_count: 100 }
      mockFetch.mockResolvedValueOnce({
        ok: true,
        status: 200,
        json: () => Promise.resolve(response)
      })

      await client.submitText('proj-1', { text: '文件内容', filename: 'test.md' })

      expect(mockFetch).toHaveBeenCalledWith(
        'http://localhost:8000/api/projects/proj-1/text',
        expect.objectContaining({
          body: JSON.stringify({ text: '文件内容', filename: 'test.md' })
        })
      )
    })

    it('校验失败时返回 invalid 状态', async () => {
      const response = { status: 'invalid', message: '文本内容不能为空', char_count: 0 }
      mockFetch.mockResolvedValueOnce({
        ok: true,
        status: 200,
        json: () => Promise.resolve(response)
      })

      const result = await client.submitText('proj-1', { text: '' })
      expect(result.status).toBe('invalid')
    })

    it('项目不存在时抛出 404 错误', async () => {
      mockFetch.mockResolvedValueOnce({
        ok: false,
        status: 404,
        statusText: 'Not Found',
        json: () => Promise.resolve({ detail: '项目不存在' })
      })

      await expect(client.submitText('nonexistent', { text: 'test' })).rejects.toThrow(ApiError)
    })
  })

  // --- 网络错误 ---
  describe('网络错误处理', () => {
    it('JSON 解析失败时使用 statusText', async () => {
      mockFetch.mockResolvedValueOnce({
        ok: false,
        status: 500,
        statusText: 'Internal Server Error',
        json: () => Promise.reject(new Error('invalid json'))
      })

      await expect(client.listProjects()).rejects.toThrow('Internal Server Error')
    })
  })
})
