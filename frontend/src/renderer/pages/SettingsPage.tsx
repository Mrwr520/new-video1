import { useState, useEffect, useCallback } from 'react'
import { Link } from 'react-router-dom'
import {
  apiClient,
  type AppConfig,
  type AppConfigUpdate,
  type ModelInfo,
  type GPUInfo,
  type EnvironmentCheckResponse,
  type InstallStatusResponse
} from '../services/api-client'

type SaveStatus = 'idle' | 'saving' | 'success' | 'error'

/** 设置页 - 集成模型管理、GPU 信息、图像/视频生成模式切换 */
export function SettingsPage(): JSX.Element {
  const [config, setConfig] = useState<AppConfig | null>(null)
  const [loading, setLoading] = useState(true)
  const [loadError, setLoadError] = useState('')
  const [saveStatus, setSaveStatus] = useState<SaveStatus>('idle')
  const [saveError, setSaveError] = useState('')

  // 模型和 GPU 状态
  const [models, setModels] = useState<ModelInfo[]>([])
  const [gpuInfo, setGpuInfo] = useState<GPUInfo | null>(null)
  const [cacheSizeGb, setCacheSizeGb] = useState(0)
  const [modelActionLoading, setModelActionLoading] = useState<Record<string, boolean>>({})

  // 环境检测状态
  const [envCheck, setEnvCheck] = useState<EnvironmentCheckResponse | null>(null)
  const [envLoading, setEnvLoading] = useState(false)
  const [installStatus, setInstallStatus] = useState<InstallStatusResponse | null>(null)
  const [installing, setInstalling] = useState(false)

  // 表单字段
  const [pythonPath, setPythonPath] = useState('')
  const [gpuDevice, setGpuDevice] = useState(0)
  const [backendPort, setBackendPort] = useState(8000)
  const [llmApiUrl, setLlmApiUrl] = useState('')
  const [llmApiKey, setLlmApiKey] = useState('')
  const [imageGenMode, setImageGenMode] = useState('local')
  const [imageGenApiUrl, setImageGenApiUrl] = useState('')
  const [imageGenApiKey, setImageGenApiKey] = useState('')
  const [ttsEngine, setTtsEngine] = useState<string>('edge-tts')
  const [fishAudioApiKey, setFishAudioApiKey] = useState('')
  const [cosyvoiceApiKey, setCosyvoiceApiKey] = useState('')
  const [minimaxApiKey, setMinimaxApiKey] = useState('')
  const [minimaxGroupId, setMinimaxGroupId] = useState('')
  const [volcengineAccessToken, setVolcengineAccessToken] = useState('')
  const [volcengineAppId, setVolcengineAppId] = useState('')

  const loadConfig = useCallback(async () => {
    setLoading(true)
    setLoadError('')
    try {
      const [data, modelsRes, gpu] = await Promise.all([
        apiClient.getConfig(),
        apiClient.listModels().catch(() => ({ models: [], cache_size_gb: 0, active_model: null })),
        apiClient.getGPUInfo().catch(() => ({ available: false, error: 'GPU 检测失败' } as GPUInfo))
      ])
      setConfig(data)
      // 同时加载环境检测
      apiClient.checkEnvironment().then(setEnvCheck).catch(() => {})
      setPythonPath(data.python_path)
      setGpuDevice(data.gpu_device)
      setBackendPort(data.backend_port)
      setLlmApiUrl(data.llm_api_url)
      setLlmApiKey(data.llm_api_key)
      setImageGenMode(data.image_gen_mode || 'local')
      setImageGenApiUrl(data.image_gen_api_url)
      setImageGenApiKey(data.image_gen_api_key)
      setTtsEngine(data.tts_engine)
      setFishAudioApiKey(data.fish_audio_api_key)
      setCosyvoiceApiKey(data.cosyvoice_api_key)
      setMinimaxApiKey(data.minimax_api_key)
      setMinimaxGroupId(data.minimax_group_id)
      setVolcengineAccessToken(data.volcengine_access_token)
      setVolcengineAppId(data.volcengine_app_id)
      setModels(modelsRes.models)
      setCacheSizeGb(modelsRes.cache_size_gb)
      setGpuInfo(gpu)
    } catch (err) {
      setLoadError(err instanceof Error ? err.message : '加载配置失败')
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => { loadConfig() }, [loadConfig])

  // 下载中轮询
  useEffect(() => {
    const hasDownloading = models.some(m => m.status === 'downloading')
    if (!hasDownloading) return
    const timer = setInterval(async () => {
      try {
        const res = await apiClient.listModels()
        setModels(res.models)
        setCacheSizeGb(res.cache_size_gb)
      } catch { /* ignore */ }
    }, 3000)
    return () => clearInterval(timer)
  }, [models])

  // 安装进度轮询
  useEffect(() => {
    if (!installing) return
    const timer = setInterval(async () => {
      try {
        const status = await apiClient.getInstallStatus()
        setInstallStatus(status)
        if (!status.running) {
          setInstalling(false)
          // 安装完成后刷新环境检测
          apiClient.checkEnvironment().then(setEnvCheck).catch(() => {})
          apiClient.getGPUInfo().then(setGpuInfo).catch(() => {})
        }
      } catch { /* ignore */ }
    }, 2000)
    return () => clearInterval(timer)
  }, [installing])

  const handleInstallAll = async (): Promise<void> => {
    setInstalling(true)
    setInstallStatus({ running: true, log: [], success: null, message: '准备安装...' })
    try {
      await apiClient.installPackages([], envCheck?.recommended_torch_index_url?.split('/').pop() || undefined)
    } catch (err) {
      setInstalling(false)
      setInstallStatus({ running: false, log: [], success: false, message: err instanceof Error ? err.message : '启动安装失败' })
    }
  }

  const handleRefreshEnv = async (): Promise<void> => {
    setEnvLoading(true)
    try {
      const env = await apiClient.checkEnvironment()
      setEnvCheck(env)
    } catch { /* ignore */ }
    setEnvLoading(false)
  }

  const buildUpdate = (): AppConfigUpdate => {
    if (!config) return {}
    const update: AppConfigUpdate = {}
    if (pythonPath !== config.python_path) update.python_path = pythonPath
    if (gpuDevice !== config.gpu_device) update.gpu_device = gpuDevice
    if (backendPort !== config.backend_port) update.backend_port = backendPort
    if (llmApiUrl !== config.llm_api_url) update.llm_api_url = llmApiUrl
    if (llmApiKey !== config.llm_api_key) update.llm_api_key = llmApiKey
    if (imageGenMode !== (config.image_gen_mode || 'local')) update.image_gen_mode = imageGenMode
    if (imageGenApiUrl !== config.image_gen_api_url) update.image_gen_api_url = imageGenApiUrl
    if (imageGenApiKey !== config.image_gen_api_key) update.image_gen_api_key = imageGenApiKey
    if (ttsEngine !== config.tts_engine) update.tts_engine = ttsEngine
    if (fishAudioApiKey !== config.fish_audio_api_key) update.fish_audio_api_key = fishAudioApiKey
    if (cosyvoiceApiKey !== config.cosyvoice_api_key) update.cosyvoice_api_key = cosyvoiceApiKey
    if (minimaxApiKey !== config.minimax_api_key) update.minimax_api_key = minimaxApiKey
    if (minimaxGroupId !== config.minimax_group_id) update.minimax_group_id = minimaxGroupId
    if (volcengineAccessToken !== config.volcengine_access_token) update.volcengine_access_token = volcengineAccessToken
    if (volcengineAppId !== config.volcengine_app_id) update.volcengine_app_id = volcengineAppId
    return update
  }

  const handleSave = async (e: React.FormEvent): Promise<void> => {
    e.preventDefault()
    const update = buildUpdate()
    if (Object.keys(update).length === 0) {
      setSaveStatus('success')
      setSaveError('')
      return
    }
    setSaveStatus('saving')
    setSaveError('')
    try {
      const updated = await apiClient.updateConfig(update)
      setConfig(updated)
      setSaveStatus('success')
    } catch (err) {
      setSaveError(err instanceof Error ? err.message : '保存配置失败')
      setSaveStatus('error')
    }
  }

  const handleModelDownload = async (modelId: string): Promise<void> => {
    setModelActionLoading(prev => ({ ...prev, [modelId]: true }))
    try {
      await apiClient.downloadModel(modelId)
      const res = await apiClient.listModels()
      setModels(res.models)
      setCacheSizeGb(res.cache_size_gb)
    } catch (err) {
      setSaveError(err instanceof Error ? err.message : '模型下载失败')
      setSaveStatus('error')
    } finally {
      setModelActionLoading(prev => ({ ...prev, [modelId]: false }))
    }
  }

  const handleModelDelete = async (modelId: string): Promise<void> => {
    if (!confirm('确定要删除此模型？删除后需要重新下载。')) return
    setModelActionLoading(prev => ({ ...prev, [modelId]: true }))
    try {
      await apiClient.deleteModel(modelId)
      const res = await apiClient.listModels()
      setModels(res.models)
      setCacheSizeGb(res.cache_size_gb)
    } catch (err) {
      setSaveError(err instanceof Error ? err.message : '模型删除失败')
      setSaveStatus('error')
    } finally {
      setModelActionLoading(prev => ({ ...prev, [modelId]: false }))
    }
  }

  const statusLabel = (status: ModelInfo['status']): string => {
    const map: Record<string, string> = {
      not_downloaded: '⬇ 未下载',
      downloading: '⏳ 下载中...',
      downloaded: '✅ 已就绪',
      loading: '🔄 加载中...',
      loaded: '🟢 运行中',
      error: '❌ 出错'
    }
    return map[status] || status
  }

  // 按用途分组模型
  const imageModel = models.find(m => m.id === 'sdxl-base')
  const videoModel = models.find(m => m.id === 'hunyuan-video')

  if (loading) {
    return (
      <div className="page settings-page">
        <h1>设置</h1>
        <p>加载配置中...</p>
      </div>
    )
  }

  if (loadError) {
    return (
      <div className="page settings-page">
        <h1>设置</h1>
        <p className="error-text" role="alert">{loadError}</p>
        <button type="button" onClick={loadConfig}>重试</button>
        <Link to="/">返回项目列表</Link>
      </div>
    )
  }

  /** 渲染单个模型卡片 */
  const renderModelCard = (model: ModelInfo, purpose: string): JSX.Element => (
    <div className="model-card" key={model.id} aria-label={model.name}>
      <div className="model-card-header">
        <div>
          <span className="model-card-purpose">{purpose}</span>
          <h4>{model.name}</h4>
        </div>
        <span className="model-status-badge">{statusLabel(model.status)}</span>
      </div>
      <p className="model-description">{model.description}</p>
      <div className="model-meta">
        <span>大小: ~{model.estimated_size_gb} GB</span>
        <span>最低显存: {model.min_vram_gb} GB</span>
      </div>
      {model.status === 'downloading' && (
        <div className="progress-bar-container" role="progressbar"
          aria-valuenow={Math.round(model.download_progress * 100)}
          aria-valuemin={0} aria-valuemax={100}
        >
          <div className="progress-bar-fill"
            style={{ width: `${Math.round(model.download_progress * 100)}%` }}
          />
          <span className="progress-text">{Math.round(model.download_progress * 100)}%</span>
        </div>
      )}
      {model.status === 'error' && model.error_message && (
        <p className="error-text" role="alert">{model.error_message}</p>
      )}
      <div className="model-actions">
        {(model.status === 'not_downloaded' || model.status === 'error') && (
          <button type="button" onClick={() => handleModelDownload(model.id)}
            disabled={!!modelActionLoading[model.id]}
          >
            {modelActionLoading[model.id] ? '下载中...' : '下载模型'}
          </button>
        )}
        {(model.status === 'downloaded' || model.status === 'error') && model.local_path && (
          <button type="button" className="btn-danger"
            onClick={() => handleModelDelete(model.id)}
            disabled={!!modelActionLoading[model.id]}
          >
            删除
          </button>
        )}
        {model.status === 'loaded' && <span className="model-active-label">✓ 正在使用</span>}
        {model.status === 'downloading' && <span>请等待下载完成...</span>}
      </div>
    </div>
  )

  return (
    <div className="page settings-page">
      <header className="page-header">
        <h1>设置</h1>
        <Link to="/">返回项目列表</Link>
      </header>

      {/* ========== GPU 环境信息 ========== */}
      <section className="settings-section gpu-info-section" aria-label="GPU 环境">
        <h2>🖥️ GPU 环境 <Link to="/models" style={{ fontSize: '0.8rem', fontWeight: 'normal', marginLeft: 12 }}>模型管理详情 →</Link></h2>

        {envCheck ? (
          <div className="gpu-details">
            {envCheck.gpu_detected && envCheck.gpu_info ? (
              <>
                {envCheck.gpu_info.map(dev => (
                  <div key={dev.index} className="gpu-device-row">
                    <span className="gpu-name">🟢 {dev.name}</span>
                    <span className="gpu-memory">
                      {Math.round(dev.free_memory_mb / 1024 * 10) / 10} GB 可用 / {Math.round(dev.total_memory_mb / 1024 * 10) / 10} GB 总计
                    </span>
                  </div>
                ))}
                <small>
                  NVIDIA 驱动 {envCheck.nvidia_driver_version} · CUDA {envCheck.cuda_version_from_driver} · Python {envCheck.python_version}
                </small>
              </>
            ) : (
              <div className="gpu-unavailable">
                <p>⚠️ {envCheck.gpu_error || '未检测到 NVIDIA GPU'}</p>
                <small>本地模型需要 NVIDIA GPU + CUDA 驱动。没有 GPU 请使用远程 API 模式。</small>
              </div>
            )}
          </div>
        ) : gpuInfo?.available ? (
          <div className="gpu-details">
            {gpuInfo.devices?.map(dev => (
              <div key={dev.index} className="gpu-device-row">
                <span className="gpu-name">{dev.name}</span>
                <span className="gpu-memory">
                  {dev.free_memory_gb} GB 可用 / {dev.total_memory_gb} GB 总计
                </span>
              </div>
            ))}
            <small>CUDA {gpuInfo.cuda_version} · 模型缓存占用: {cacheSizeGb} GB</small>
          </div>
        ) : (
          <div className="gpu-unavailable">
            <p>⚠️ {gpuInfo?.error || 'GPU 不可用'}</p>
          </div>
        )}

        {/* 依赖包状态 */}
        {envCheck && (
          <div style={{ marginTop: 16 }}>
            <h3 style={{ fontSize: '0.95rem', marginBottom: 8 }}>
              📦 Python 依赖
              {envCheck.all_installed
                ? <span style={{ color: '#22c55e', marginLeft: 8 }}>✅ 全部就绪</span>
                : <span style={{ color: '#ef4444', marginLeft: 8 }}>⚠️ 有缺失</span>}
              <button type="button" onClick={handleRefreshEnv} disabled={envLoading}
                style={{ marginLeft: 12, fontSize: '0.8rem', padding: '2px 8px' }}>
                {envLoading ? '检测中...' : '🔄 重新检测'}
              </button>
            </h3>
            <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(220px, 1fr))', gap: 8 }}>
              {envCheck.packages.map(pkg => (
                <div key={pkg.name} style={{
                  padding: '6px 10px', borderRadius: 6,
                  background: pkg.installed ? '#f0fdf4' : '#fef2f2',
                  border: `1px solid ${pkg.installed ? '#bbf7d0' : '#fecaca'}`,
                  fontSize: '0.85rem',
                }}>
                  <span>{pkg.installed ? '✅' : '❌'} {pkg.display_name}</span>
                  {pkg.version && <span style={{ color: '#888', marginLeft: 4 }}>v{pkg.version}</span>}
                  {!pkg.installed && pkg.required && <span style={{ color: '#ef4444', marginLeft: 4 }}>(必需)</span>}
                </div>
              ))}
            </div>

            {!envCheck.all_installed && (
              <div style={{ marginTop: 12 }}>
                {envCheck.recommended_torch_index_url && (
                  <small style={{ display: 'block', marginBottom: 6, color: '#666' }}>
                    检测到 CUDA {envCheck.cuda_version_from_driver}，将自动匹配 PyTorch CUDA 版本
                  </small>
                )}
                <button type="button" onClick={handleInstallAll} disabled={installing}
                  style={{ padding: '8px 24px', fontSize: '0.95rem', fontWeight: 600 }}>
                  {installing ? '⏳ 安装中...' : '🚀 一键安装所有缺失依赖'}
                </button>
              </div>
            )}

            {/* 安装日志 */}
            {installStatus && (installStatus.running || installStatus.log.length > 0) && (
              <div style={{ marginTop: 12 }}>
                <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 4 }}>
                  <span style={{ fontSize: '0.85rem', fontWeight: 600 }}>
                    {installStatus.running ? '⏳ 安装进行中...' : installStatus.success ? '✅ 安装完成' : '❌ 安装失败'}
                  </span>
                  {installStatus.message && <span style={{ fontSize: '0.8rem', color: '#666' }}>{installStatus.message}</span>}
                </div>
                <pre style={{
                  background: '#1e1e1e', color: '#d4d4d4', padding: 12, borderRadius: 6,
                  fontSize: '0.75rem', maxHeight: 200, overflow: 'auto', whiteSpace: 'pre-wrap',
                }}>
                  {installStatus.log.slice(-50).join('\n') || '等待输出...'}
                </pre>
              </div>
            )}
          </div>
        )}
      </section>

      <form onSubmit={handleSave} aria-label="应用设置">

        {/* ========== 图像生成（关键帧） ========== */}
        <fieldset className="settings-section">
          <legend>🎨 图像生成（关键帧）</legend>

          <div className="form-field">
            <label htmlFor="image-gen-mode">生成模式</label>
            <select id="image-gen-mode" value={imageGenMode}
              onChange={(e) => setImageGenMode(e.target.value)}
            >
              <option value="local">本地模型（Stable Diffusion XL，免费，需要 GPU）</option>
              <option value="api">远程 API（DALL-E / Flux 等，需要 API Key）</option>
            </select>
            <small id="image-gen-mode-hint">
              {imageGenMode === 'local'
                ? '使用本地 GPU 生成图像，无需联网和 API Key'
                : '通过远程 API 生成图像，需要配置 API 地址和密钥'}
            </small>
          </div>

          {/* 本地模式：显示 SDXL 模型状态 */}
          {imageGenMode === 'local' && imageModel && (
            <div className="model-section">
              {renderModelCard(imageModel, '关键帧生成')}
              {!gpuInfo?.available && !envCheck?.gpu_detected && (
                <p className="warning-text">
                  ⚠️ 未检测到 GPU，本地模式可能无法正常工作。建议切换为远程 API 模式。
                </p>
              )}
            </div>
          )}

          {/* API 模式：显示 API 配置 */}
          {imageGenMode === 'api' && (
            <>
              <div className="form-field">
                <label htmlFor="image-gen-api-url">API 地址</label>
                <input id="image-gen-api-url" type="text" value={imageGenApiUrl}
                  onChange={(e) => setImageGenApiUrl(e.target.value)}
                  placeholder="https://api.openai.com/v1"
                />
              </div>
              <div className="form-field">
                <label htmlFor="image-gen-api-key">API Key</label>
                <input id="image-gen-api-key" type="password" value={imageGenApiKey}
                  onChange={(e) => setImageGenApiKey(e.target.value)}
                  placeholder="输入 API Key" autoComplete="off"
                />
              </div>
            </>
          )}
        </fieldset>

        {/* ========== 视频生成 ========== */}
        <fieldset className="settings-section">
          <legend>🎬 视频生成</legend>
          <p className="section-description">
            视频生成使用本地 HunyuanVideo 模型，将关键帧图片转化为动态视频片段。
            需要 NVIDIA GPU（最低 6GB 显存）。
          </p>
          {videoModel && renderModelCard(videoModel, '视频生成')}
          {!gpuInfo?.available && !envCheck?.gpu_detected && (
            <p className="warning-text">
              ⚠️ 未检测到 GPU，视频生成功能不可用。请安装 NVIDIA 驱动和 CUDA。
            </p>
          )}
        </fieldset>

        {/* ========== LLM API ========== */}
        <fieldset className="settings-section">
          <legend>🤖 LLM API（角色提取 & 分镜生成）</legend>
          <div className="form-field">
            <label htmlFor="llm-api-url">API 地址</label>
            <input id="llm-api-url" type="text" value={llmApiUrl}
              onChange={(e) => setLlmApiUrl(e.target.value)}
              placeholder="https://api.openai.com/v1"
            />
            <small>支持 OpenAI 兼容接口（OpenAI、DeepSeek、通义千问等）</small>
          </div>
          <div className="form-field">
            <label htmlFor="llm-api-key">API Key</label>
            <input id="llm-api-key" type="password" value={llmApiKey}
              onChange={(e) => setLlmApiKey(e.target.value)}
              placeholder="sk-..." autoComplete="off"
            />
          </div>
        </fieldset>

        {/* ========== TTS 语音引擎 ========== */}
        <fieldset className="settings-section">
          <legend>🔊 TTS 语音引擎</legend>
          <div className="form-field">
            <label htmlFor="tts-engine">引擎选择</label>
            <select id="tts-engine" value={ttsEngine}
              onChange={(e) => setTtsEngine(e.target.value)}
            >
              <option value="edge-tts">Edge-TTS（免费）</option>
              <option value="chattts">ChatTTS（免费，本地）</option>
              <option value="fish-speech">Fish Audio（收费）</option>
              <option value="cosyvoice">CosyVoice 阿里通义（收费）</option>
              <option value="minimax-tts">MiniMax TTS（收费）</option>
              <option value="volcengine-tts">火山引擎 TTS（收费）</option>
            </select>
          </div>

          {/* 根据选择的引擎显示对应的 API Key 配置 */}
          {ttsEngine === 'fish-speech' && (
            <div className="form-field">
              <label htmlFor="fish-audio-api-key">Fish Audio API Key</label>
              <input id="fish-audio-api-key" type="password" value={fishAudioApiKey}
                onChange={(e) => setFishAudioApiKey(e.target.value)}
                placeholder="输入 Fish Audio API Key" autoComplete="off"
              />
              <small>注册获取: <a href="https://fish.audio" target="_blank" rel="noreferrer">fish.audio</a></small>
            </div>
          )}
          {ttsEngine === 'cosyvoice' && (
            <div className="form-field">
              <label htmlFor="cosyvoice-api-key">DashScope API Key</label>
              <input id="cosyvoice-api-key" type="password" value={cosyvoiceApiKey}
                onChange={(e) => setCosyvoiceApiKey(e.target.value)}
                placeholder="输入阿里 DashScope API Key" autoComplete="off"
              />
              <small>注册获取: <a href="https://dashscope.console.aliyun.com" target="_blank" rel="noreferrer">dashscope.console.aliyun.com</a></small>
            </div>
          )}
          {ttsEngine === 'minimax-tts' && (
            <>
              <div className="form-field">
                <label htmlFor="minimax-api-key">MiniMax API Key</label>
                <input id="minimax-api-key" type="password" value={minimaxApiKey}
                  onChange={(e) => setMinimaxApiKey(e.target.value)}
                  placeholder="输入 MiniMax API Key" autoComplete="off"
                />
              </div>
              <div className="form-field">
                <label htmlFor="minimax-group-id">MiniMax Group ID</label>
                <input id="minimax-group-id" type="text" value={minimaxGroupId}
                  onChange={(e) => setMinimaxGroupId(e.target.value)}
                  placeholder="输入 MiniMax Group ID"
                />
                <small>注册获取: <a href="https://platform.minimaxi.com" target="_blank" rel="noreferrer">platform.minimaxi.com</a></small>
              </div>
            </>
          )}
          {ttsEngine === 'volcengine-tts' && (
            <>
              <div className="form-field">
                <label htmlFor="volcengine-access-token">火山引擎 Access Token</label>
                <input id="volcengine-access-token" type="password" value={volcengineAccessToken}
                  onChange={(e) => setVolcengineAccessToken(e.target.value)}
                  placeholder="输入火山引擎 Access Token" autoComplete="off"
                />
              </div>
              <div className="form-field">
                <label htmlFor="volcengine-app-id">火山引擎 App ID</label>
                <input id="volcengine-app-id" type="text" value={volcengineAppId}
                  onChange={(e) => setVolcengineAppId(e.target.value)}
                  placeholder="输入火山引擎 App ID"
                />
                <small>注册获取: <a href="https://console.volcengine.com" target="_blank" rel="noreferrer">console.volcengine.com</a></small>
              </div>
            </>
          )}
        </fieldset>

        {/* ========== 高级设置 ========== */}
        <fieldset className="settings-section">
          <legend>⚙️ 高级设置</legend>
          <div className="form-field">
            <label htmlFor="python-path">Python 路径</label>
            <input id="python-path" type="text" value={pythonPath}
              onChange={(e) => setPythonPath(e.target.value)}
              placeholder="python" aria-describedby="python-path-hint"
            />
            <small id="python-path-hint">Python 解释器的完整路径或命令名</small>
          </div>
          <div className="form-field">
            <label htmlFor="gpu-device">GPU 设备编号</label>
            <input id="gpu-device" type="number" min={0} value={gpuDevice}
              onChange={(e) => setGpuDevice(parseInt(e.target.value, 10) || 0)}
              aria-describedby="gpu-device-hint"
            />
            <small id="gpu-device-hint">CUDA 设备编号，多 GPU 时选择使用哪块，默认 0</small>
          </div>
          <div className="form-field">
            <label htmlFor="backend-port">后端服务端口</label>
            <input id="backend-port" type="number" min={1024} max={65535}
              value={backendPort}
              onChange={(e) => setBackendPort(parseInt(e.target.value, 10) || 8000)}
              aria-describedby="backend-port-hint"
            />
            <small id="backend-port-hint">Python 后端服务端口，默认 8000</small>
          </div>
        </fieldset>

        {/* 保存反馈 */}
        {saveStatus === 'success' && (
          <p className="success-text" role="status">✅ 配置已保存</p>
        )}
        {saveStatus === 'error' && (
          <p className="error-text" role="alert">{saveError}</p>
        )}

        <div className="form-actions">
          <button type="submit" disabled={saveStatus === 'saving'}>
            {saveStatus === 'saving' ? '保存中...' : '保存设置'}
          </button>
        </div>
      </form>
    </div>
  )
}
