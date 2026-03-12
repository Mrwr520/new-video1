import { useState, useEffect, useCallback } from 'react'
import { useParams, Link } from 'react-router-dom'
import { apiClient, StoryboardScene, ExportErrorDetail } from '../services/api-client'

// 视频预览页 - 预览生成的视频片段、导出最终视频
// Requirements: 7.4 (完整视频预览), 7.5 (MP4 导出), 7.7 (错误详情与重试)
export function VideoPreviewPage(): JSX.Element {
  const { id: projectId } = useParams<{ id: string }>()
  const [scenes, setScenes] = useState<StoryboardScene[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [selectedScene, setSelectedScene] = useState<string | null>(null)

  // 导出状态
  const [exporting, setExporting] = useState(false)
  const [exportedVideoPath, setExportedVideoPath] = useState<string | null>(null)
  const [exportError, setExportError] = useState<ExportErrorDetail | null>(null)

  // 预览模式: 'clips' 查看片段, 'final' 查看最终视频
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
    // 从绝对路径中提取项目内的相对路径
    const match = videoPath.match(/projects[\\/][^\\/]+[\\/](.+)/)
    if (match) {
      return apiClient.getFileUrl(projectId, match[1].replace(/\\/g, '/'))
    }
    // 如果路径已经是相对路径
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
      // 解析错误详情
      if (e && typeof e === 'object' && 'status' in e && 'detail' in e) {
        const apiErr = e as { status: number; detail: string }
        try {
          const detail = typeof apiErr.detail === 'string'
            ? JSON.parse(apiErr.detail)
            : apiErr.detail
          if (detail && typeof detail === 'object' && 'code' in detail) {
            setExportError(detail as ExportErrorDetail)
          } else {
            setExportError({
              code: 'UNKNOWN_ERROR',
              message: apiErr.detail || '导出失败',
              retryable: true,
            })
          }
        } catch {
          setExportError({
            code: 'UNKNOWN_ERROR',
            message: String(apiErr.detail),
            retryable: true,
          })
        }
      } else {
        setExportError({
          code: 'UNKNOWN_ERROR',
          message: e instanceof Error ? e.message : '导出失败',
          retryable: true,
        })
      }
    } finally {
      setExporting(false)
    }
  }

  const scenesWithVideo = scenes.filter(s => s.video_path)
  const currentScene = scenes.find(s => s.id === selectedScene)

  if (loading) return <div className="page"><p>加载中...</p></div>

  return (
    <div className="page video-preview-page" style={{ padding: '20px', maxWidth: '1000px', margin: '0 auto' }}>
      {/* 顶部导航 */}
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '20px' }}>
        <h1 style={{ margin: 0 }}>视频预览</h1>
        <div style={{ display: 'flex', gap: '8px', alignItems: 'center' }}>
          <Link to={`/project/${projectId}/story`}>返回分镜</Link>
          <Link to={`/project/${projectId}`}>返回工作台</Link>
        </div>
      </div>

      {error && (
        <div role="alert" style={{ color: 'red', marginBottom: '16px', padding: '8px', border: '1px solid red', borderRadius: '4px' }}>
          {error}
        </div>
      )}

      {scenesWithVideo.length === 0 ? (
        <div style={{ textAlign: 'center', padding: '40px', color: '#888' }}>
          <p>暂无已生成的视频片段</p>
          <p style={{ fontSize: '14px' }}>请先在分镜编辑页面生成视频片段</p>
          <Link to={`/project/${projectId}/story`}>前往分镜编辑</Link>
        </div>
      ) : (
        <>
          {/* 导出区域 */}
          <div style={{
            marginBottom: '20px', padding: '16px',
            border: '1px solid #e0e0e0', borderRadius: '8px', background: '#fafafa',
          }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: '12px', flexWrap: 'wrap' }}>
              <button
                onClick={handleExport}
                disabled={exporting}
                aria-label="导出视频"
                style={{
                  padding: '10px 24px', fontSize: '15px', fontWeight: 'bold',
                  background: exporting ? '#ccc' : '#4488cc', color: 'white',
                  border: 'none', borderRadius: '6px', cursor: exporting ? 'not-allowed' : 'pointer',
                }}
              >
                {exporting ? '导出中...' : '导出视频'}
              </button>

              {exporting && (
                <span style={{ color: '#666', fontSize: '14px' }} role="status" aria-live="polite">
                  正在合成视频，请稍候...
                </span>
              )}

              {exportedVideoPath && !exporting && (
                <span style={{ color: '#2a7d2a', fontSize: '14px' }}>✓ 导出成功</span>
              )}

              {/* 预览模式切换 */}
              {exportedVideoPath && (
                <div style={{ marginLeft: 'auto', display: 'flex', gap: '4px' }}>
                  <button
                    onClick={() => setPreviewMode('clips')}
                    style={{
                      padding: '6px 12px', border: '1px solid #ccc', borderRadius: '4px',
                      background: previewMode === 'clips' ? '#4488cc' : 'white',
                      color: previewMode === 'clips' ? 'white' : '#333',
                      cursor: 'pointer',
                    }}
                    aria-label="查看视频片段"
                  >
                    片段预览
                  </button>
                  <button
                    onClick={() => setPreviewMode('final')}
                    style={{
                      padding: '6px 12px', border: '1px solid #ccc', borderRadius: '4px',
                      background: previewMode === 'final' ? '#4488cc' : 'white',
                      color: previewMode === 'final' ? 'white' : '#333',
                      cursor: 'pointer',
                    }}
                    aria-label="查看完整视频"
                  >
                    完整视频
                  </button>
                </div>
              )}
            </div>

            {/* 导出错误显示 (Req 7.7) */}
            {exportError && (
              <div role="alert" style={{
                marginTop: '12px', padding: '12px',
                border: '1px solid #e74c3c', borderRadius: '6px', background: '#fdf0ef',
              }}>
                <div style={{ fontWeight: 'bold', color: '#c0392b', marginBottom: '4px' }}>
                  导出失败 [{exportError.code}]
                </div>
                <div style={{ color: '#555', marginBottom: '8px' }}>{exportError.message}</div>
                {exportError.detail && (
                  <details style={{ marginBottom: '8px' }}>
                    <summary style={{ cursor: 'pointer', color: '#888', fontSize: '13px' }}>查看错误详情</summary>
                    <pre style={{ fontSize: '12px', color: '#666', whiteSpace: 'pre-wrap', marginTop: '4px' }}>
                      {exportError.detail}
                    </pre>
                  </details>
                )}
                {exportError.retryable && (
                  <button
                    onClick={handleExport}
                    disabled={exporting}
                    aria-label="重试导出"
                    style={{
                      padding: '6px 16px', background: '#e74c3c', color: 'white',
                      border: 'none', borderRadius: '4px', cursor: 'pointer',
                    }}
                  >
                    重试
                  </button>
                )}
              </div>
            )}
          </div>

          {/* 完整视频预览 (Req 7.4) */}
          {previewMode === 'final' && exportedVideoPath && projectId && (
            <div style={{ marginBottom: '20px' }}>
              <h2 style={{ margin: '0 0 12px' }}>完整视频预览</h2>
              <video
                key="final-video"
                src={getVideoUrl(exportedVideoPath)}
                controls
                style={{ width: '100%', borderRadius: '8px', background: '#000' }}
                aria-label="完整视频预览"
              />
            </div>
          )}

          {/* 片段预览 */}
          {previewMode === 'clips' && (
            <div style={{ display: 'flex', gap: '20px' }}>
              {/* 主播放器 */}
              <div style={{ flex: 1 }}>
                {currentScene?.video_path ? (
                  <div>
                    <video
                      key={currentScene.id}
                      src={getVideoUrl(currentScene.video_path)}
                      controls
                      autoPlay
                      style={{ width: '100%', borderRadius: '8px', background: '#000' }}
                      aria-label={`分镜 ${currentScene.order} 视频`}
                    />
                    <div style={{ marginTop: '12px' }}>
                      <h3 style={{ margin: '0 0 4px' }}>#{currentScene.order} {currentScene.scene_description}</h3>
                      {currentScene.dialogue && (
                        <p style={{ margin: '4px 0', fontStyle: 'italic', color: '#555' }}>
                          「{currentScene.dialogue}」
                        </p>
                      )}
                      <p style={{ margin: '4px 0', fontSize: '13px', color: '#888' }}>
                        {currentScene.camera_direction}
                      </p>
                    </div>
                  </div>
                ) : (
                  <div style={{
                    padding: '40px', textAlign: 'center', color: '#aaa',
                    background: '#f5f5f5', borderRadius: '8px',
                  }}>
                    请从右侧列表选择一个视频片段
                  </div>
                )}
              </div>

              {/* 片段列表 */}
              <div style={{ width: '240px', flexShrink: 0 }}>
                <h3 style={{ margin: '0 0 12px' }}>视频片段 ({scenesWithVideo.length})</h3>
                <div style={{ display: 'flex', flexDirection: 'column', gap: '8px' }}>
                  {scenesWithVideo.map(scene => (
                    <button
                      key={scene.id}
                      onClick={() => setSelectedScene(scene.id)}
                      style={{
                        padding: '10px',
                        border: selectedScene === scene.id ? '2px solid #4488cc' : '1px solid #ddd',
                        borderRadius: '6px',
                        background: selectedScene === scene.id ? '#f0f5ff' : 'white',
                        cursor: 'pointer', textAlign: 'left',
                      }}
                      aria-label={`选择分镜 ${scene.order} 视频`}
                    >
                      <div style={{ fontWeight: 'bold', fontSize: '13px' }}>#{scene.order}</div>
                      <div style={{
                        fontSize: '12px', color: '#666', marginTop: '2px',
                        overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap',
                      }}>
                        {scene.scene_description}
                      </div>
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
