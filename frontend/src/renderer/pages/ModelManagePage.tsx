import { useState, useEffect, useCallback } from 'react'
import { Link } from 'react-router-dom'
import { apiClient, type ModelInfo, type GPUInfo } from '../services/api-client'

/** 模型管理页面 — 显示模型状态、GPU 信息、触发下载/删除 */
export function ModelManagePage(): JSX.Element {
  const [models, setModels] = useState<ModelInfo[]>([])
  const [gpuInfo, setGpuInfo] = useState<GPUInfo | null>(null)
  const [cacheSizeGb, setCacheSizeGb] = useState(0)
  const [activeModel, setActiveModel] = useState<string | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [actionLoading, setActionLoading] = useState<Record<string, boolean>>({})

  const loadData = useCallback(async () => {
    setLoading(true)
    setError('')
    try {
      const [modelsRes, gpu] = await Promise.all([
        apiClient.listModels(),
        apiClient.getGPUInfo()
      ])
      setModels(modelsRes.models)
      setCacheSizeGb(modelsRes.cache_size_gb)
      setActiveModel(modelsRes.active_model)
      setGpuInfo(gpu)
    } catch (err) {
      setError(err instanceof Error ? err.message : '加载失败')
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    loadData()
  }, [loadData])

  // 下载中轮询刷新
  useEffect(() => {
    const hasDownloading = models.some(m => m.status === 'downloading')
    if (!hasDownloading) return
    const timer = setInterval(loadData, 3000)
    return () => clearInterval(timer)
  }, [models, loadData])

  const handleDownload = async (modelId: string): Promise<void> => {
    setActionLoading(prev => ({ ...prev, [modelId]: true }))
    try {
      await apiClient.downloadModel(modelId)
      await loadData()
    } catch (err) {
      setError(err instanceof Error ? err.message : '下载失败')
    } finally {
      setActionLoading(prev => ({ ...prev, [modelId]: false }))
    }
  }

  const handleDelete = async (modelId: string): Promise<void> => {
    if (!confirm('确定要删除此模型？删除后需要重新下载。')) return
    setActionLoading(prev => ({ ...prev, [modelId]: true }))
    try {
      await apiClient.deleteModel(modelId)
      await loadData()
    } catch (err) {
      setError(err instanceof Error ? err.message : '删除失败')
    } finally {
      setActionLoading(prev => ({ ...prev, [modelId]: false }))
    }
  }

  const statusLabel = (status: ModelInfo['status']): string => {
    const map: Record<string, string> = {
      not_downloaded: '未下载',
      downloading: '下载中...',
      downloaded: '已就绪',
      loading: '加载中...',
      loaded: '运行中',
      error: '出错'
    }
    return map[status] || status
  }

  const statusColor = (status: ModelInfo['status']): string => {
    const map: Record<string, string> = {
      not_downloaded: '#888',
      downloading: '#e6a817',
      downloaded: '#4caf50',
      loading: '#2196f3',
      loaded: '#4caf50',
      error: '#f44336'
    }
    return map[status] || '#888'
  }

  if (loading) {
    return (
      <div className="page model-manage-page">
        <h1>模型管理</h1>
        <p>加载中...</p>
      </div>
    )
  }

  return (
    <div className="page model-manage-page">
      <header className="page-header">
        <h1>模型管理</h1>
        <Link to="/settings">返回设置</Link>
      </header>

      {error && <p className="error-text" role="alert">{error}</p>}

      {/* GPU 信息卡片 */}
      <section className="gpu-info-card" aria-label="GPU 信息">
        <h2>GPU 环境</h2>
        {gpuInfo?.available ? (
          <div className="gpu-details">
            {gpuInfo.devices?.map(dev => (
              <div key={dev.index} className="gpu-device">
                <span className="gpu-name">{dev.name}</span>
                <span className="gpu-memory">
                  显存: {dev.free_memory_gb} GB 可用 / {dev.total_memory_gb} GB 总计
                </span>
              </div>
            ))}
            <small>CUDA {gpuInfo.cuda_version}</small>
          </div>
        ) : (
          <div className="gpu-unavailable">
            <p>⚠️ {gpuInfo?.error || 'GPU 不可用'}</p>
            <small>
              本地模型需要 NVIDIA GPU。没有 GPU 的情况下，请在设置中切换为"远程 API"模式。
            </small>
          </div>
        )}
      </section>

      {/* 模型列表 */}
      <section className="models-list" aria-label="AI 模型">
        <h2>AI 模型</h2>
        <small>缓存占用: {cacheSizeGb} GB</small>
        {activeModel && <small> · 当前活跃: {activeModel}</small>}

        <div className="model-cards">
          {models.map(model => (
            <div key={model.id} className="model-card" aria-label={model.name}>
              <div className="model-header">
                <h3>{model.name}</h3>
                <span
                  className="model-status-badge"
                  style={{ color: statusColor(model.status) }}
                >
                  {statusLabel(model.status)}
                </span>
              </div>

              <p className="model-description">{model.description}</p>

              <div className="model-meta">
                <span>大小: ~{model.estimated_size_gb} GB</span>
                <span>最低显存: {model.min_vram_gb} GB</span>
              </div>

              {/* 下载进度条 */}
              {model.status === 'downloading' && (
                <div className="progress-bar-container" role="progressbar"
                  aria-valuenow={Math.round(model.download_progress * 100)}
                  aria-valuemin={0} aria-valuemax={100}
                >
                  <div
                    className="progress-bar-fill"
                    style={{ width: `${Math.round(model.download_progress * 100)}%` }}
                  />
                  <span className="progress-text">
                    {Math.round(model.download_progress * 100)}%
                  </span>
                </div>
              )}

              {/* 错误信息 */}
              {model.status === 'error' && model.error_message && (
                <p className="error-text" role="alert">{model.error_message}</p>
              )}

              {/* 操作按钮 */}
              <div className="model-actions">
                {(model.status === 'not_downloaded' || model.status === 'error') && (
                  <button
                    type="button"
                    onClick={() => handleDownload(model.id)}
                    disabled={!!actionLoading[model.id] || !gpuInfo?.available}
                    aria-label={`下载 ${model.name}`}
                  >
                    {actionLoading[model.id] ? '处理中...' : '下载模型'}
                  </button>
                )}
                {(model.status === 'downloaded' || model.status === 'error') && (
                  <button
                    type="button"
                    className="btn-danger"
                    onClick={() => handleDelete(model.id)}
                    disabled={!!actionLoading[model.id]}
                    aria-label={`删除 ${model.name}`}
                  >
                    {actionLoading[model.id] ? '处理中...' : '删除'}
                  </button>
                )}
                {model.status === 'loaded' && (
                  <span className="model-active-label">✓ 正在使用</span>
                )}
              </div>
            </div>
          ))}
        </div>
      </section>

      {/* 使用说明 */}
      <section className="model-help" aria-label="使用说明">
        <h2>使用说明</h2>
        <ul>
          <li>首次使用需要下载模型，下载完成后即可离线使用</li>
          <li>图像生成模型和视频生成模型会交替使用 GPU，不会同时占用</li>
          <li>如果显存不足，可以在设置中切换图像生成为"远程 API"模式</li>
          <li>模型文件缓存在用户目录下，卸载软件不会自动删除</li>
        </ul>
      </section>
    </div>
  )
}
