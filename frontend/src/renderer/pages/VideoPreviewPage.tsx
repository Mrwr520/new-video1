import { useState, useEffect, useCallback } from 'react'
import { useParams, Link } from 'react-router-dom'
import { apiClient, StoryboardScene, ExportErrorDetail } from '../services/api-client'

export function VideoPreviewPage(): JSX.Element {
  const { id: projectId } = useParams<{ id: string }>()
  const [scenes, setScenes] = useState<StoryboardScene[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [selectedScene, setSelectedScene] = useState<string | null>(null)
  const [exporting, setExporting] = useState(false)
  const [exportedVideoPath, setExportedVideoPath] = useState<string | null>(null)
  const [exportError, setExportError] = useState<ExportErrorDetail | null>(null)
  const [previewMode, setPreviewMode] = useState<'clips' | 'final'>('clips')

  const loadScenes = useCallback(async () => {
    if (!projectId) return
    try {
      setLoading(true)
      const data = await apiClient.getScenes(projectId)
      setScenes(data)
      const firstWithVideo = data.find(s => s.video_path)
      if (firstWithVideo) setSelectedScene(firstWithVideo.id)
      setError(null)
    } catch (e) {
      setError(e instanceof Error ? e.message : '加载分镜失败')
    } finally {
      setLoading(false)
    }
  }, [projectId])

  useEffect(() => { loadScenes() }, [loadScenes])

  const getVideoUrl = (videoPath: string): string => {
    if (!projectId) return videoPath
    const match = videoPath.match(/projects[\\/][^\\/]+[\\/](.+)/)
    if (match) return apiClient.getFileUrl(projectId, match[1].replace(/\\/g, '/'))
    return apiClient.getFileUrl(projectId, videoPath.replace(/\\/g, '/'))
  }

  const handleExport = async () => {
    if (!projectId) return
    setExporting(true)
    setExportError(null)
    setExportedVideoPath(null)
    try {
      const result = await apiClient.exportVideo(projectId)
      setExportedVideoPath(result.video_path)
      setPreviewMode('final')
    } catch (e: unknown) {
      if (e && typeof e === 'object' && 'status' in e && 'detail' in e) {
        const apiErr = e as { status: number; detail: string }
        try {
          const detail = typeof apiErr.detail === 'string' ? JSON.parse(apiErr.detail) : apiErr.detail
          if (detail && typeof detail === 'object' && 'code' in detail) {
            setExportError(detail as ExportErrorDetail)
          } else {
            setExportError({ code: 'UNKNOWN_ERROR', message: apiErr.detail || '导出失败', retryable: true })
          }
        } catch {
          setExportError({ code: 'UNKNOWN_ERROR', message: String(apiErr.detail), retryable: true })
        }
      } else {
        setExportError({ code: 'UNKNOWN_ERROR', message: e instanceof Error ? e.message : '导出失败', retryable: true })
      }
    } finally {
      setExporting(false)
    }
  }

  const scenesWithVideo = scenes.filter(s => s.video_path)
  const currentScene = scenes.find(s => s.id === selectedScene)

  if (loading) return <div className="page"><p>加载中...</p></div>

  return (
    <div className="page video-preview-page">
      <header className="page-header">
        <h1>视频预览</h1>
        <div className="header-actions">
          <Link to={`/project/${projectId}/story`}>返回分镜</Link>
          <Link to={`/project/${projectId}`}>返回工作台</Link>
        </div>
      </header>

      {error && <div className="alert alert-danger" role="alert">{error}</div>}

      {scenesWithVideo.length === 0 ? (
        <div className="empty-state-block">
          <p>暂无已生成的视频片段</p>
          <p>请先在分镜编辑页面生成视频片段</p>
          <Link to={`/project/${projectId}/story`}>前往分镜编辑</Link>
        </div>
      ) : (
        <>
          {/* 导出区域 */}
          <div className="export-section">
            <div className="export-controls">
              <button onClick={handleExport} disabled={exporting} aria-label="导出视频">
                {exporting ? '导出中...' : '导出视频'}
              </button>

              {exporting && <span className="badge badge-info" role="status" aria-live="polite">正在合成视频，请稍候...</span>}
              {exportedVideoPath && !exporting && <span className="badge badge-success">✓ 导出成功</span>}

              {exportedVideoPath && (
                <div className="preview-mode-toggle">
                  <button
                    className={previewMode === 'clips' ? 'btn-primary' : 'btn-secondary'}
                    onClick={() => setPreviewMode('clips')}
                    aria-label="查看视频片段"
                  >片段预览</button>
                  <button
                    className={previewMode === 'final' ? 'btn-primary' : 'btn-secondary'}
                    onClick={() => setPreviewMode('final')}
                    aria-label="查看完整视频"
                  >完整视频</button>
                </div>
              )}
            </div>

            {exportError && (
              <div className="alert alert-danger" role="alert" style={{ marginTop: 12 }}>
                <div style={{ fontWeight: 600, marginBottom: 4 }}>导出失败 [{exportError.code}]</div>
                <div>{exportError.message}</div>
                {exportError.detail && (
                  <details style={{ marginTop: 8 }}>
                    <summary>查看错误详情</summary>
                    <pre className="error-detail-pre">{exportError.detail}</pre>
                  </details>
                )}
                {exportError.retryable && (
                  <button className="btn-danger" onClick={handleExport} disabled={exporting} aria-label="重试导出" style={{ marginTop: 8 }}>重试</button>
                )}
              </div>
            )}
          </div>

          {/* 完整视频预览 */}
          {previewMode === 'final' && exportedVideoPath && projectId && (
            <div className="final-video-section">
              <h2>完整视频预览</h2>
              <div className="video-player">
                <video key="final-video" src={getVideoUrl(exportedVideoPath)} controls aria-label="完整视频预览" />
              </div>
            </div>
          )}

          {/* 片段预览 */}
          {previewMode === 'clips' && (
            <div className="clips-layout">
              <div className="clips-player">
                {currentScene?.video_path ? (
                  <div>
                    <div className="video-player">
                      <video key={currentScene.id} src={getVideoUrl(currentScene.video_path)} controls autoPlay aria-label={`分镜 ${currentScene.order} 视频`} />
                    </div>
                    <div className="clip-info">
                      <h3>#{currentScene.order} {currentScene.scene_description}</h3>
                      {currentScene.dialogue && <p className="clip-dialogue">「{currentScene.dialogue}」</p>}
                      {currentScene.camera_direction && <p className="clip-camera">{currentScene.camera_direction}</p>}
                    </div>
                  </div>
                ) : (
                  <div className="video-player">
                    <span>请从右侧列表选择一个视频片段</span>
                  </div>
                )}
              </div>

              <div className="clips-sidebar">
                <h3>视频片段 ({scenesWithVideo.length})</h3>
                <div className="scene-selector">
                  {scenesWithVideo.map(scene => (
                    <button
                      key={scene.id}
                      className={selectedScene === scene.id ? 'active' : ''}
                      onClick={() => setSelectedScene(scene.id)}
                      aria-label={`选择分镜 ${scene.order} 视频`}
                    >
                      <div className="scene-selector-order">#{scene.order}</div>
                      <div className="scene-selector-desc">{scene.scene_description}</div>
                    </button>
                  ))}
                </div>
              </div>
            </div>
          )}
        </>
      )}
    </div>
  )
}
