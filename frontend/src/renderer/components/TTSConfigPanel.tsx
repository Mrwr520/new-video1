import { useState, useEffect, useCallback, useRef } from 'react'
import { apiClient, TTSEngineInfo, TTSVoiceInfo } from '../services/api-client'

interface TTSConfigPanelProps {
  projectId: string
  sceneId: string
  sceneName: string
  dialogue: string
  audioPath: string | null
  onSpeechGenerated?: (audioPath: string) => void
}

/**
 * TTS 语音配置和预览面板
 *
 * Requirements:
 *   6.3: 语音生成完成后，提供音频预览和播放功能
 *   6.5: TTS_Engine 失败时，显示错误信息并提供重试选项
 *   6.6: TTS_Engine 生成采样率不低于 16kHz 的音频文件
 */
export function TTSConfigPanel({
  projectId,
  sceneId,
  sceneName,
  dialogue,
  audioPath,
  onSpeechGenerated,
}: TTSConfigPanelProps): JSX.Element {
  const [engines, setEngines] = useState<TTSEngineInfo[]>([])
  const [voices, setVoices] = useState<TTSVoiceInfo[]>([])
  const [selectedEngine, setSelectedEngine] = useState('edge-tts')
  const [selectedVoice, setSelectedVoice] = useState('zh-CN-XiaoxiaoNeural')
  const [generating, setGenerating] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [currentAudioPath, setCurrentAudioPath] = useState<string | null>(audioPath)
  const audioRef = useRef<HTMLAudioElement>(null)

  // 加载引擎列表
  useEffect(() => {
    apiClient.listTTSEngines().then(setEngines).catch(() => {})
  }, [])

  // 引擎变更时加载语音列表
  const loadVoices = useCallback(async () => {
    try {
      const voiceList = await apiClient.listTTSVoices(selectedEngine)
      setVoices(voiceList)
      if (voiceList.length > 0 && !voiceList.find(v => v.id === selectedVoice)) {
        setSelectedVoice(voiceList[0].id)
      }
    } catch {
      setVoices([])
    }
  }, [selectedEngine, selectedVoice])

  useEffect(() => { loadVoices() }, [loadVoices])

  // 同步外部 audioPath 变更
  useEffect(() => { setCurrentAudioPath(audioPath) }, [audioPath])

  const handleGenerate = async (): Promise<void> => {
    setGenerating(true)
    setError(null)
    try {
      const result = await apiClient.generateSpeech(projectId, sceneId, {
        engine: selectedEngine,
        voice_id: selectedVoice,
      })
      setCurrentAudioPath(result.audio_path)
      onSpeechGenerated?.(result.audio_path)
    } catch (e) {
      setError(e instanceof Error ? e.message : '语音生成失败')
    } finally {
      setGenerating(false)
    }
  }

  /** 构建音频文件的 URL */
  const getAudioUrl = (path: string): string => {
    const match = path.match(/projects[\\/](.+)/)
    if (match) {
      return `http://localhost:8000/api/projects/${projectId}/files/${match[1].replace(/\\/g, '/')}`
    }
    return path
  }

  const hasDialogue = dialogue && dialogue.trim().length > 0

  return (
    <div
      data-testid={`tts-panel-${sceneId}`}
      style={{
        margin: '8px 0',
        padding: '12px',
        background: '#f8f9fa',
        borderRadius: '6px',
        border: '1px solid #e9ecef',
      }}
    >
      <div style={{ fontSize: '13px', fontWeight: 600, marginBottom: '8px', color: '#495057' }}>
        🔊 语音配音 - {sceneName}
      </div>

      {!hasDialogue ? (
        <div style={{ color: '#999', fontSize: '13px' }}>该分镜没有台词/旁白，无法生成语音</div>
      ) : (
        <>
          {/* 引擎和语音选择 */}
          <div style={{ display: 'flex', gap: '8px', marginBottom: '8px', flexWrap: 'wrap' }}>
            <label style={{ fontSize: '12px', display: 'flex', alignItems: 'center', gap: '4px' }}>
              引擎:
              <select
                value={selectedEngine}
                onChange={e => setSelectedEngine(e.target.value)}
                disabled={generating}
                aria-label="选择语音引擎"
                style={{ fontSize: '12px', padding: '2px 4px' }}
              >
                {engines.map(eng => (
                  <option key={eng.name} value={eng.name}>
                    {eng.display_name}
                  </option>
                ))}
              </select>
            </label>

            <label style={{ fontSize: '12px', display: 'flex', alignItems: 'center', gap: '4px' }}>
              语音:
              <select
                value={selectedVoice}
                onChange={e => setSelectedVoice(e.target.value)}
                disabled={generating || voices.length === 0}
                aria-label="选择语音"
                style={{ fontSize: '12px', padding: '2px 4px', maxWidth: '200px' }}
              >
                {voices.map(v => (
                  <option key={v.id} value={v.id}>
                    {v.name} ({v.gender === 'Female' ? '女' : v.gender === 'Male' ? '男' : v.gender})
                  </option>
                ))}
              </select>
            </label>

            <button
              onClick={handleGenerate}
              disabled={generating || !hasDialogue}
              aria-label={`生成语音 ${sceneName}`}
              style={{ fontSize: '12px', padding: '2px 8px' }}
            >
              {generating ? '生成中...' : currentAudioPath ? '重新生成' : '生成语音'}
            </button>
          </div>

          {/* 错误提示（含重试） */}
          {error && (
            <div
              role="alert"
              data-testid={`tts-error-${sceneId}`}
              style={{
                padding: '6px 8px',
                background: '#fff0f0',
                border: '1px solid #ffcccc',
                borderRadius: '4px',
                color: '#cc0000',
                fontSize: '12px',
                marginBottom: '8px',
              }}
            >
              语音生成失败: {error}
              <button
                onClick={handleGenerate}
                style={{ marginLeft: '8px', fontSize: '11px' }}
                aria-label={`重试生成语音 ${sceneName}`}
              >
                重试
              </button>
            </div>
          )}

          {/* 音频预览播放器 */}
          {currentAudioPath && !error && (
            <div data-testid={`tts-audio-${sceneId}`}>
              <audio
                ref={audioRef}
                src={getAudioUrl(currentAudioPath)}
                controls
                style={{ width: '100%', height: '32px' }}
                aria-label={`${sceneName} 语音预览`}
              />
            </div>
          )}
        </>
      )}
    </div>
  )
}
