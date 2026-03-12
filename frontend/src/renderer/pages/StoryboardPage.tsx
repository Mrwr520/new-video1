import { useState, useEffect, useCallback } from 'react'
import { useParams, Link } from 'react-router-dom'
import { apiClient, StoryboardScene, SceneUpdate } from '../services/api-client'
import { TTSConfigPanel } from '../components/TTSConfigPanel'

export function StoryboardPage(): JSX.Element {
  const { id: projectId } = useParams<{ id: string }>()
  const [scenes, setScenes] = useState<StoryboardScene[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [editingId, setEditingId] = useState<string | null>(null)
  const [editForm, setEditForm] = useState<SceneUpdate>({})
  const [showAddForm, setShowAddForm] = useState(false)
  const [newScene, setNewScene] = useState<SceneUpdate>({})
  const [confirming, setConfirming] = useState(false)
  const [dragIdx, setDragIdx] = useState<number | null>(null)
  const [regeneratingIds, setRegeneratingIds] = useState<Set<string>>(new Set())
  const [keyframeErrors, setKeyframeErrors] = useState<Record<string, string>>({})
  const [videoGeneratingIds, setVideoGeneratingIds] = useState<Set<string>>(new Set())
  const [videoErrors, setVideoErrors] = useState<Record<string, string>>({})
  const loadScenes = useCallback(async () => {
    if (!projectId) return
    try {
      setLoading(true)
      const data = await apiClient.getScenes(projectId)
      setScenes(data)
      setError(null)
    } catch (e) {
      setError(e instanceof Error ? e.message : '加载分镜失败')
    } finally {
      setLoading(false)
    }
  }, [projectId])

  useEffect(() => { loadScenes() }, [loadScenes])

  const handleEdit = (scene: StoryboardScene): void => {
    setEditingId(scene.id)
    setEditForm({
      scene_description: scene.scene_description,
      dialogue: scene.dialogue,
      camera_direction: scene.camera_direction,
    })
  }

  const handleSaveEdit = async (): Promise<void> => {
    if (!projectId || !editingId) return
    try {
      await apiClient.updateScene(projectId, editingId, editForm)
      setEditingId(null)
      await loadScenes()
    } catch (e) {
      setError(e instanceof Error ? e.message : '更新分镜失败')
    }
  }

  const handleDelete = async (sceneId: string): Promise<void> => {
    if (!projectId) return
    try {
      await apiClient.deleteScene(projectId, sceneId)
      await loadScenes()
    } catch (e) {
      setError(e instanceof Error ? e.message : '删除分镜失败')
    }
  }

  const handleAddScene = async (): Promise<void> => {
    if (!projectId) return
    try {
      await apiClient.createScene(projectId, newScene)
      setShowAddForm(false)
      setNewScene({})
      await loadScenes()
    } catch (e) {
      setError(e instanceof Error ? e.message : '添加分镜失败')
    }
  }

  const handleConfirm = async (): Promise<void> => {
    if (!projectId) return
    try {
      setConfirming(true)
      await apiClient.confirmStoryboard(projectId)
      setError(null)
    } catch (e) {
      setError(e instanceof Error ? e.message : '确认分镜失败')
    } finally {
      setConfirming(false)
    }
  }

  const handleRegenerateKeyframe = async (sceneId: string): Promise<void> => {
    if (!projectId) return
    setRegeneratingIds(prev => new Set(prev).add(sceneId))
    setKeyframeErrors(prev => {
      const next = { ...prev }
      delete next[sceneId]
      return next
    })
    try {
      const updated = await apiClient.regenerateKeyframe(projectId, sceneId)
      setScenes(prev => prev.map(s => s.id === sceneId ? updated : s))
    } catch (e) {
      const msg = e instanceof Error ? e.message : '关键帧生成失败'
      setKeyframeErrors(prev => ({ ...prev, [sceneId]: msg }))
    } finally {
      setRegeneratingIds(prev => {
        const next = new Set(prev)
        next.delete(sceneId)
        return next
      })
    }
  }

  const handleDragStart = (idx: number): void => { setDragIdx(idx) }

  const handleDrop = async (targetIdx: number): Promise<void> => {
    if (dragIdx === null || dragIdx === targetIdx || !projectId) return
    const reordered = [...scenes]
    const [moved] = reordered.splice(dragIdx, 1)
    reordered.splice(targetIdx, 0, moved)
    try {
      const result = await apiClient.reorderScenes(projectId, reordered.map(s => s.id))
      setScenes(result)
    } catch (e) {
      setError(e instanceof Error ? e.message : '重排分镜失败')
    }
    setDragIdx(null)
  }

  /** 构建关键帧图片的 URL */
  const getKeyframeUrl = (keyframePath: string): string => {
    // keyframe_path 是后端文件路径，通过文件服务 API 访问
    // 提取 projects/{project_id}/keyframes/scene_{id}.png 部分
    const match = keyframePath.match(/projects[\\/](.+)/)
    if (match) {
      return `http://localhost:8000/api/projects/${projectId}/files/${match[1].replace(/\\/g, '/')}`
    }
    return keyframePath
  }

  /** 构建视频片段的 URL */
  const getVideoUrl = (videoPath: string): string => {
    const match = videoPath.match(/projects[\\/](.+)/)
    if (match) {
      return `http://localhost:8000/api/projects/${projectId}/files/${match[1].replace(/\\/g, '/')}`
    }
    return videoPath
  }

  const handleRegenerateVideo = async (sceneId: string): Promise<void> => {
    if (!projectId) return
    setVideoGeneratingIds(prev => new Set(prev).add(sceneId))
    setVideoErrors(prev => {
      const next = { ...prev }
      delete next[sceneId]
      return next
    })
    try {
      const updated = await apiClient.regenerateVideo(projectId, sceneId)
      setScenes(prev => prev.map(s => s.id === sceneId ? updated : s))
    } catch (e) {
      const msg = e instanceof Error ? e.message : '视频生成失败'
      setVideoErrors(prev => ({ ...prev, [sceneId]: msg }))
    } finally {
      setVideoGeneratingIds(prev => {
        const next = new Set(prev)
        next.delete(sceneId)
        return next
      })
    }
  }

  if (loading) return <div className="page"><p>加载中...</p></div>

  return (
    <div className="page storyboard-page" style={{ padding: '20px', maxWidth: '900px', margin: '0 auto' }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '20px' }}>
        <h1 style={{ margin: 0 }}>分镜编辑</h1>
        <Link to={`/project/${projectId}`}>返回工作台</Link>
      </div>

      {error && <div role="alert" style={{ color: 'red', marginBottom: '16px', padding: '8px', border: '1px solid red', borderRadius: '4px' }}>{error}</div>}

      <div style={{ marginBottom: '16px', display: 'flex', gap: '8px' }}>
        <button onClick={() => setShowAddForm(true)}>+ 添加分镜</button>
        <button onClick={handleConfirm} disabled={confirming || scenes.length === 0}>
          {confirming ? '确认中...' : '确认分镜'}
        </button>
      </div>

      {showAddForm && (
        <div style={{ border: '1px solid #ccc', padding: '16px', borderRadius: '8px', marginBottom: '16px' }}>
          <h3>添加新分镜</h3>
          <label htmlFor="new-scene-desc">场景描述</label>
          <textarea id="new-scene-desc" value={newScene.scene_description || ''} onChange={e => setNewScene({ ...newScene, scene_description: e.target.value })} rows={2} style={{ display: 'block', width: '100%', marginBottom: '8px' }} />
          <label htmlFor="new-scene-dialogue">台词/旁白</label>
          <textarea id="new-scene-dialogue" value={newScene.dialogue || ''} onChange={e => setNewScene({ ...newScene, dialogue: e.target.value })} rows={2} style={{ display: 'block', width: '100%', marginBottom: '8px' }} />
          <label htmlFor="new-scene-camera">镜头指示</label>
          <input id="new-scene-camera" value={newScene.camera_direction || ''} onChange={e => setNewScene({ ...newScene, camera_direction: e.target.value })} style={{ display: 'block', width: '100%', marginBottom: '8px' }} />
          <div style={{ display: 'flex', gap: '8px' }}>
            <button onClick={handleAddScene}>保存</button>
            <button onClick={() => { setShowAddForm(false); setNewScene({}) }}>取消</button>
          </div>
        </div>
      )}

      {scenes.length === 0 ? (
        <p>暂无分镜。可以手动添加，或等待 LLM 自动生成。</p>
      ) : (
        <div style={{ display: 'flex', flexDirection: 'column', gap: '8px' }}>
          {scenes.map((scene, idx) => (
            <div
              key={scene.id}
              draggable
              onDragStart={() => handleDragStart(idx)}
              onDragOver={e => e.preventDefault()}
              onDrop={() => handleDrop(idx)}
              style={{ border: '1px solid #ddd', padding: '16px', borderRadius: '8px', cursor: 'grab', background: dragIdx === idx ? '#f0f0f0' : 'white' }}
            >
              {editingId === scene.id ? (
                <div>
                  <label htmlFor={`edit-desc-${scene.id}`}>场景描述</label>
                  <textarea id={`edit-desc-${scene.id}`} value={editForm.scene_description || ''} onChange={e => setEditForm({ ...editForm, scene_description: e.target.value })} rows={2} style={{ display: 'block', width: '100%', marginBottom: '8px' }} />
                  <label htmlFor={`edit-dialogue-${scene.id}`}>台词/旁白</label>
                  <textarea id={`edit-dialogue-${scene.id}`} value={editForm.dialogue || ''} onChange={e => setEditForm({ ...editForm, dialogue: e.target.value })} rows={2} style={{ display: 'block', width: '100%', marginBottom: '8px' }} />
                  <label htmlFor={`edit-camera-${scene.id}`}>镜头指示</label>
                  <input id={`edit-camera-${scene.id}`} value={editForm.camera_direction || ''} onChange={e => setEditForm({ ...editForm, camera_direction: e.target.value })} style={{ display: 'block', width: '100%', marginBottom: '8px' }} />
                  <div style={{ display: 'flex', gap: '8px' }}>
                    <button onClick={handleSaveEdit}>保存</button>
                    <button onClick={() => setEditingId(null)}>取消</button>
                  </div>
                </div>
              ) : (
                <div>
                  <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                    <strong>#{scene.order}</strong>
                    <span style={{ color: '#888', fontSize: '12px' }}>{scene.camera_direction}</span>
                  </div>
                  <p style={{ margin: '8px 0 4px' }}>{scene.scene_description}</p>
                  {scene.dialogue && <p style={{ margin: '4px 0', fontStyle: 'italic', color: '#555' }}>「{scene.dialogue}」</p>}

                  {/* 关键帧展示区域 */}
                  <div style={{ margin: '8px 0', minHeight: '60px' }}>
                    {regeneratingIds.has(scene.id) ? (
                      <div data-testid={`keyframe-loading-${scene.id}`} style={{ padding: '16px', background: '#f5f5f5', borderRadius: '4px', textAlign: 'center', color: '#888' }}>
                        关键帧生成中...
                      </div>
                    ) : keyframeErrors[scene.id] ? (
                      <div role="alert" data-testid={`keyframe-error-${scene.id}`} style={{ padding: '8px', background: '#fff0f0', border: '1px solid #ffcccc', borderRadius: '4px', color: '#cc0000', fontSize: '13px' }}>
                        <span>生成失败: {keyframeErrors[scene.id]}</span>
                        <button
                          onClick={() => handleRegenerateKeyframe(scene.id)}
                          style={{ marginLeft: '8px', fontSize: '12px' }}
                          aria-label={`重试生成关键帧 ${scene.order}`}
                        >
                          重试
                        </button>
                      </div>
                    ) : scene.keyframe_path ? (
                      <div data-testid={`keyframe-image-${scene.id}`}>
                        <img
                          src={getKeyframeUrl(scene.keyframe_path)}
                          alt={`分镜 ${scene.order} 关键帧`}
                          style={{ maxWidth: '100%', borderRadius: '4px', border: '1px solid #eee' }}
                        />
                      </div>
                    ) : (
                      <div data-testid={`keyframe-empty-${scene.id}`} style={{ padding: '16px', background: '#fafafa', borderRadius: '4px', textAlign: 'center', color: '#aaa', fontSize: '13px' }}>
                        暂无关键帧
                      </div>
                    )}
                  </div>

                  {/* 视频片段预览区域 */}
                  <div style={{ margin: '8px 0', minHeight: '40px' }}>
                    {videoGeneratingIds.has(scene.id) ? (
                      <div data-testid={`video-loading-${scene.id}`} style={{ padding: '16px', background: '#f0f5ff', borderRadius: '4px', textAlign: 'center', color: '#4488cc' }}>
                        视频生成中...
                      </div>
                    ) : videoErrors[scene.id] ? (
                      <div role="alert" data-testid={`video-error-${scene.id}`} style={{ padding: '8px', background: '#fff0f0', border: '1px solid #ffcccc', borderRadius: '4px', color: '#cc0000', fontSize: '13px' }}>
                        <span>视频生成失败: {videoErrors[scene.id]}</span>
                        <button
                          onClick={() => handleRegenerateVideo(scene.id)}
                          style={{ marginLeft: '8px', fontSize: '12px' }}
                          aria-label={`重试生成视频 ${scene.order}`}
                        >
                          重试
                        </button>
                      </div>
                    ) : scene.video_path ? (
                      <div data-testid={`video-player-${scene.id}`}>
                        <video
                          src={getVideoUrl(scene.video_path)}
                          controls
                          style={{ maxWidth: '100%', borderRadius: '4px', border: '1px solid #eee' }}
                          aria-label={`分镜 ${scene.order} 视频预览`}
                        />
                      </div>
                    ) : scene.keyframe_path ? (
                      <div data-testid={`video-empty-${scene.id}`} style={{ padding: '12px', background: '#fafafa', borderRadius: '4px', textAlign: 'center', color: '#aaa', fontSize: '13px' }}>
                        暂无视频片段，点击下方按钮生成
                      </div>
                    ) : null}
                  </div>

                  {/* TTS 语音配音区域 */}
                  <TTSConfigPanel
                    projectId={projectId!}
                    sceneId={scene.id}
                    sceneName={`分镜 ${scene.order}`}
                    dialogue={scene.dialogue}
                    audioPath={scene.audio_path}
                    onSpeechGenerated={(audioPath) => {
                      setScenes(prev => prev.map(s =>
                        s.id === scene.id ? { ...s, audio_path: audioPath } : s
                      ))
                    }}
                  />

                  <div style={{ display: 'flex', gap: '8px', marginTop: '8px' }}>
                    <button onClick={() => handleEdit(scene)} aria-label={`编辑分镜 ${scene.order}`}>编辑</button>
                    <button
                      onClick={() => handleRegenerateKeyframe(scene.id)}
                      disabled={regeneratingIds.has(scene.id)}
                      aria-label={`${scene.keyframe_path ? '重新生成' : '生成'}关键帧 ${scene.order}`}
                    >
                      {regeneratingIds.has(scene.id) ? '生成中...' : scene.keyframe_path ? '重新生成关键帧' : '生成关键帧'}
                    </button>
                    {scene.keyframe_path && (
                      <button
                        onClick={() => handleRegenerateVideo(scene.id)}
                        disabled={videoGeneratingIds.has(scene.id)}
                        aria-label={`${scene.video_path ? '重新生成' : '生成'}视频 ${scene.order}`}
                      >
                        {videoGeneratingIds.has(scene.id) ? '生成中...' : scene.video_path ? '重新生成视频' : '生成视频'}
                      </button>
                    )}
                    <button onClick={() => handleDelete(scene.id)} aria-label={`删除分镜 ${scene.order}`} style={{ color: 'red' }}>删除</button>
                  </div>
                </div>
              )}
            </div>
          ))}
        </div>
      )}
    </div>
  )
}
