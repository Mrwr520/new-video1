import { useState, useEffect, useCallback } from 'react'
import { useParams, Link } from 'react-router-dom'
import { apiClient, StoryboardScene } from '../services/api-client'

// 视频预览页 - 预览生成的视频片段和最终视频
export function VideoPreviewPage(): JSX.Element {
  const { id: projectId } = useParams<{ id: string }>()
  const [scenes, setScenes] = useState<StoryboardScene[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [selectedScene, setSelectedScene] = useState<string | null>(null)

  const loadScenes = useCallback(async () => {
    if (!projectId) return
    try {
      setLoading(true)
      const data = await apiClient.getScenes(projectId)
      setScenes(data)
      // 默认选中第一个有视频的场景
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
    const match = videoPath.match(/projects[\\/](.+)/)
    if (match) {
      return `http://localhost:8000/api/projects/${projectId}/files/${match[1].replace(/\\/g, '/')}`
    }
    return videoPath
  }

  const scenesWithVideo = scenes.filter(s => s.video_path)
  const currentScene = scenes.find(s => s.id === selectedScene)

  if (loading) return <div className="page"><p>加载中...</p></div>

  return (
    <div className="page video-preview-page" style={{ padding: '20px', maxWidth: '1000px', margin: '0 auto' }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '20px' }}>
        <h1 style={{ margin: 0 }}>视频预览</h1>
        <div style={{ display: 'flex', gap: '8px' }}>
          <Link to={`/project/${projectId}/story`}>返回分镜</Link>
          <Link to={`/project/${projectId}`}>返回工作台</Link>
        </div>
      </div>

      {error && <div role="alert" style={{ color: 'red', marginBottom: '16px', padding: '8px', border: '1px solid red', borderRadius: '4px' }}>{error}</div>}

      {scenesWithVideo.length === 0 ? (
        <div style={{ textAlign: 'center', padding: '40px', color: '#888' }}>
          <p>暂无已生成的视频片段</p>
          <p style={{ fontSize: '14px' }}>请先在分镜编辑页面生成视频片段</p>
          <Link to={`/project/${projectId}/story`}>前往分镜编辑</Link>
        </div>
      ) : (
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
                    <p style={{ margin: '4px 0', fontStyle: 'italic', color: '#555' }}>「{currentScene.dialogue}」</p>
                  )}
                  <p style={{ margin: '4px 0', fontSize: '13px', color: '#888' }}>{currentScene.camera_direction}</p>
                </div>
              </div>
            ) : (
              <div style={{ padding: '40px', textAlign: 'center', color: '#aaa', background: '#f5f5f5', borderRadius: '8px' }}>
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
                    cursor: 'pointer',
                    textAlign: 'left',
                  }}
                  aria-label={`选择分镜 ${scene.order} 视频`}
                >
                  <div style={{ fontWeight: 'bold', fontSize: '13px' }}>#{scene.order}</div>
                  <div style={{ fontSize: '12px', color: '#666', marginTop: '2px', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                    {scene.scene_description}
                  </div>
                </button>
              ))}
            </div>
          </div>
        </div>
      )}
    </div>
  )
}
