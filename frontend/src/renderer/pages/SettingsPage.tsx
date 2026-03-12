import { useState, useEffect, useCallback } from 'react'
import { Link } from 'react-router-dom'
import { apiClient, type AppConfig, type AppConfigUpdate } from '../services/api-client'

type SaveStatus = 'idle' | 'saving' | 'success' | 'error'

/** 设置页 - Python 环境路径、GPU 配置、API 配置、TTS 引擎选择 */
export function SettingsPage(): JSX.Element {
  const [config, setConfig] = useState<AppConfig | null>(null)
  const [loading, setLoading] = useState(true)
  const [loadError, setLoadError] = useState('')
  const [saveStatus, setSaveStatus] = useState<SaveStatus>('idle')
  const [saveError, setSaveError] = useState('')

  // 表单字段
  const [pythonPath, setPythonPath] = useState('')
  const [gpuDevice, setGpuDevice] = useState(0)
  const [backendPort, setBackendPort] = useState(8000)
  const [llmApiUrl, setLlmApiUrl] = useState('')
  const [llmApiKey, setLlmApiKey] = useState('')
  const [imageGenApiUrl, setImageGenApiUrl] = useState('')
  const [imageGenApiKey, setImageGenApiKey] = useState('')
  const [ttsEngine, setTtsEngine] = useState<'edge-tts' | 'chattts'>('edge-tts')

  const loadConfig = useCallback(async () => {
    setLoading(true)
    setLoadError('')
    try {
      const data = await apiClient.getConfig()
      setConfig(data)
      setPythonPath(data.python_path)
      setGpuDevice(data.gpu_device)
      setBackendPort(data.backend_port)
      setLlmApiUrl(data.llm_api_url)
      setLlmApiKey(data.llm_api_key)
      setImageGenApiUrl(data.image_gen_api_url)
      setImageGenApiKey(data.image_gen_api_key)
      setTtsEngine(data.tts_engine)
    } catch (err) {
      setLoadError(err instanceof Error ? err.message : '加载配置失败')
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    loadConfig()
  }, [loadConfig])

  /** 构建只包含变更字段的更新对象 */
  const buildUpdate = (): AppConfigUpdate => {
    if (!config) return {}
    const update: AppConfigUpdate = {}
    if (pythonPath !== config.python_path) update.python_path = pythonPath
    if (gpuDevice !== config.gpu_device) update.gpu_device = gpuDevice
    if (backendPort !== config.backend_port) update.backend_port = backendPort
    if (llmApiUrl !== config.llm_api_url) update.llm_api_url = llmApiUrl
    if (llmApiKey !== config.llm_api_key) update.llm_api_key = llmApiKey
    if (imageGenApiUrl !== config.image_gen_api_url) update.image_gen_api_url = imageGenApiUrl
    if (imageGenApiKey !== config.image_gen_api_key) update.image_gen_api_key = imageGenApiKey
    if (ttsEngine !== config.tts_engine) update.tts_engine = ttsEngine
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

  return (
    <div className="page settings-page">
      <header className="page-header">
        <h1>设置</h1>
        <Link to="/">返回项目列表</Link>
      </header>

      <form onSubmit={handleSave} aria-label="应用设置">
        {/* Python 环境配置 */}
        <fieldset>
          <legend>Python 环境</legend>
          <div className="form-field">
            <label htmlFor="python-path">Python 路径</label>
            <input
              id="python-path"
              type="text"
              value={pythonPath}
              onChange={(e) => setPythonPath(e.target.value)}
              placeholder="python"
              aria-describedby="python-path-hint"
            />
            <small id="python-path-hint">Python 解释器的完整路径或命令名</small>
          </div>
        </fieldset>

        {/* GPU 配置 */}
        <fieldset>
          <legend>GPU 配置</legend>
          <div className="form-field">
            <label htmlFor="gpu-device">GPU 设备编号</label>
            <input
              id="gpu-device"
              type="number"
              min={0}
              value={gpuDevice}
              onChange={(e) => setGpuDevice(parseInt(e.target.value, 10) || 0)}
              aria-describedby="gpu-device-hint"
            />
            <small id="gpu-device-hint">CUDA 设备编号，默认 0</small>
          </div>
        </fieldset>

        {/* LLM API 配置 */}
        <fieldset>
          <legend>LLM API</legend>
          <div className="form-field">
            <label htmlFor="llm-api-url">API 地址</label>
            <input
              id="llm-api-url"
              type="text"
              value={llmApiUrl}
              onChange={(e) => setLlmApiUrl(e.target.value)}
              placeholder="https://api.openai.com/v1"
            />
          </div>
          <div className="form-field">
            <label htmlFor="llm-api-key">API Key</label>
            <input
              id="llm-api-key"
              type="password"
              value={llmApiKey}
              onChange={(e) => setLlmApiKey(e.target.value)}
              placeholder="sk-..."
              autoComplete="off"
            />
          </div>
        </fieldset>

        {/* 图像生成 API 配置 */}
        <fieldset>
          <legend>图像生成 API</legend>
          <div className="form-field">
            <label htmlFor="image-gen-api-url">API 地址</label>
            <input
              id="image-gen-api-url"
              type="text"
              value={imageGenApiUrl}
              onChange={(e) => setImageGenApiUrl(e.target.value)}
              placeholder="https://api.stability.ai/v1"
            />
          </div>
          <div className="form-field">
            <label htmlFor="image-gen-api-key">API Key</label>
            <input
              id="image-gen-api-key"
              type="password"
              value={imageGenApiKey}
              onChange={(e) => setImageGenApiKey(e.target.value)}
              placeholder="输入 API Key"
              autoComplete="off"
            />
          </div>
        </fieldset>

        {/* TTS 引擎选择 */}
        <fieldset>
          <legend>TTS 语音引擎</legend>
          <div className="form-field">
            <label htmlFor="tts-engine">引擎选择</label>
            <select
              id="tts-engine"
              value={ttsEngine}
              onChange={(e) => setTtsEngine(e.target.value as 'edge-tts' | 'chattts')}
            >
              <option value="edge-tts">Edge-TTS（免费）</option>
              <option value="chattts">ChatTTS（免费，本地）</option>
            </select>
          </div>
        </fieldset>

        {/* 后端端口 */}
        <fieldset>
          <legend>后端服务</legend>
          <div className="form-field">
            <label htmlFor="backend-port">服务端口</label>
            <input
              id="backend-port"
              type="number"
              min={1024}
              max={65535}
              value={backendPort}
              onChange={(e) => setBackendPort(parseInt(e.target.value, 10) || 8000)}
              aria-describedby="backend-port-hint"
            />
            <small id="backend-port-hint">Python 后端服务端口，默认 8000</small>
          </div>
        </fieldset>

        {/* 保存反馈 */}
        {saveStatus === 'success' && (
          <p className="success-text" role="status">配置已保存</p>
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
