import { useParams, Link } from 'react-router-dom'
import { useState, useEffect, useRef, useCallback } from 'react'
import { apiClient, type PipelineEvent, type PipelineStatusResponse } from '../services/api-client'

/** Pipeline step labels in order */
const STEP_LABELS: Record<string, string> = {
  character_extraction: '角色提取',
  storyboard_generation: '分镜脚本生成',
  keyframe_generation: '关键帧图片生成',
  video_generation: '视频片段生成',
  tts_generation: '语音配音生成',
  composition: '视频合成',
}

function formatTime(seconds: number): string {
  if (seconds <= 0) return '即将完成'
  const m = Math.floor(seconds / 60)
  const s = seconds % 60
  if (m > 0) return `约 ${m} 分 ${s} 秒`
  return `约 ${s} 秒`
}

// 项目工作台 - 项目的主工作区
export function ProjectWorkbench(): JSX.Element {
  const { id } = useParams<{ id: string }>()
  const [progress, setProgress] = useState(0)
  const [currentStep, setCurrentStep] = useState<string | null>(null)
  const [stepDetail, setStepDetail] = useState('')
  const [estimatedRemaining, setEstimatedRemaining] = useState(0)
  const [isRunning, setIsRunning] = useState(false)
  const [isWaiting, setIsWaiting] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [notification, setNotification] = useState<string | null>(null)
  const eventSourceRef = useRef<EventSource | null>(null)

  // Fetch initial pipeline status
  useEffect(() => {
    if (!id) return
    apiClient.getPipelineStatus(id).then((status: PipelineStatusResponse) => {
      setProgress(status.progress)
      setCurrentStep(status.current_step)
      setStepDetail(status.step_detail)
      setEstimatedRemaining(status.estimated_remaining)
      setIsRunning(status.is_running)
      setIsWaiting(status.is_waiting_confirmation)
      if (status.error_message) setError(status.error_message)
    }).catch(() => {
      // Pipeline status not available yet - that's fine
    })
  }, [id])

  const connectSSE = useCallback(() => {
    if (!id) return
    // Close existing connection
    if (eventSourceRef.current) {
      eventSourceRef.current.close()
    }

    const es = apiClient.subscribePipelineEvents(id)
    eventSourceRef.current = es

    const handleEvent = (e: MessageEvent) => {
      const data: PipelineEvent = JSON.parse(e.data)

      switch (data.type) {
        case 'step_started':
          setCurrentStep(data.step ?? null)
          setStepDetail(data.step_description ?? '')
          setProgress(data.progress ?? 0)
          setIsRunning(true)
          setError(null)
          setNotification(null)
          break
        case 'step_completed':
          setProgress(data.progress ?? 0)
          setNotification(`${STEP_LABELS[data.step ?? ''] ?? data.step} 完成`)
          break
        case 'step_failed':
          setError(data.error ?? '步骤执行失败')
          setIsRunning(false)
          break
        case 'waiting_confirmation':
          setIsWaiting(true)
          setNotification(`${STEP_LABELS[data.step ?? ''] ?? data.step} 等待确认`)
          break
        case 'pipeline_completed':
          setProgress(1)
          setIsRunning(false)
          setNotification('Pipeline 全部完成！')
          es.close()
          break
        case 'pipeline_cancelled':
          setIsRunning(false)
          setNotification('Pipeline 已取消')
          es.close()
          break
      }
    }

    // Listen for all known event types
    for (const eventType of [
      'step_started', 'step_completed', 'step_failed',
      'waiting_confirmation', 'pipeline_completed', 'pipeline_cancelled',
      'status', 'connected',
    ]) {
      es.addEventListener(eventType, handleEvent)
    }

    es.onerror = () => {
      // EventSource will auto-reconnect, but we note the error
      console.warn('SSE connection error, will auto-reconnect')
    }
  }, [id])

  // Cleanup SSE on unmount
  useEffect(() => {
    return () => {
      if (eventSourceRef.current) {
        eventSourceRef.current.close()
      }
    }
  }, [])

  const handleStart = async () => {
    if (!id) return
    try {
      setError(null)
      await apiClient.startPipeline(id)
      setIsRunning(true)
      connectSSE()
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : '启动失败')
    }
  }

  const handleCancel = async () => {
    if (!id) return
    try {
      await apiClient.cancelPipeline(id)
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : '取消失败')
    }
  }

  const progressPercent = Math.round(progress * 100)

  return (
    <div className="page project-workbench">
      <h1>项目工作台</h1>
      <p>项目 ID: {id}</p>

      {/* Pipeline 控制 */}
      <div className="pipeline-controls" style={{ margin: '16px 0' }}>
        {!isRunning ? (
          <button onClick={handleStart} disabled={isRunning}>
            启动 Pipeline
          </button>
        ) : (
          <button onClick={handleCancel}>取消 Pipeline</button>
        )}
      </div>

      {/* 进度条 */}
      {(isRunning || progress > 0) && (
        <div className="pipeline-progress" style={{ margin: '16px 0' }}>
          <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 4 }}>
            <span>{stepDetail || '准备中...'}</span>
            <span>{progressPercent}%</span>
          </div>
          <div
            style={{
              width: '100%',
              height: 20,
              backgroundColor: '#e0e0e0',
              borderRadius: 4,
              overflow: 'hidden',
            }}
          >
            <div
              style={{
                width: `${progressPercent}%`,
                height: '100%',
                backgroundColor: error ? '#e53935' : '#4caf50',
                transition: 'width 0.3s ease',
              }}
            />
          </div>
          {estimatedRemaining > 0 && isRunning && (
            <div style={{ fontSize: 12, color: '#888', marginTop: 4 }}>
              预计剩余: {formatTime(estimatedRemaining)}
            </div>
          )}
        </div>
      )}

      {/* 步骤导航 - 根据当前 Pipeline 状态显示操作指引 */}
      {currentStep && (
        <div style={{ margin: '12px 0', padding: 12, backgroundColor: '#f5f5f5', borderRadius: 4 }}>
          <div style={{ fontWeight: 'bold', marginBottom: 8 }}>工作流进度</div>
          <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap' }}>
            {Object.entries(STEP_LABELS).map(([step, label]) => {
              const stepKeys = Object.keys(STEP_LABELS)
              const currentIdx = stepKeys.indexOf(currentStep || '')
              const stepIdx = stepKeys.indexOf(step)
              const isDone = stepIdx < currentIdx || progress >= 1
              const isCurrent = step === currentStep
              return (
                <span
                  key={step}
                  style={{
                    padding: '4px 10px',
                    borderRadius: 12,
                    fontSize: 13,
                    backgroundColor: isDone ? '#c8e6c9' : isCurrent ? '#bbdefb' : '#e0e0e0',
                    color: isDone ? '#2e7d32' : isCurrent ? '#1565c0' : '#757575',
                    fontWeight: isCurrent ? 'bold' : 'normal',
                  }}
                >
                  {isDone ? '✓ ' : isCurrent ? '▶ ' : ''}{label}
                </span>
              )
            })}
          </div>
        </div>
      )}

      {/* 等待确认提示 */}
      {isWaiting && (
        <div style={{ padding: 8, backgroundColor: '#fff3e0', borderRadius: 4, margin: '8px 0' }}>
          {currentStep === 'character_extraction' && (
            <span>角色提取完成，请前往 <Link to={`/project/${id}/chars`}>角色管理</Link> 确认角色信息后继续。</span>
          )}
          {currentStep === 'storyboard_generation' && (
            <span>分镜生成完成，请前往 <Link to={`/project/${id}/story`}>分镜编辑</Link> 确认分镜后继续。</span>
          )}
          {currentStep !== 'character_extraction' && currentStep !== 'storyboard_generation' && (
            <span>当前步骤等待用户确认，请前往对应页面确认后继续。</span>
          )}
        </div>
      )}

      {/* 错误提示 */}
      {error && (
        <div style={{ padding: 8, backgroundColor: '#ffebee', color: '#c62828', borderRadius: 4, margin: '8px 0' }}>
          错误: {error}
        </div>
      )}

      {/* 通知 */}
      {notification && !error && (
        <div style={{ padding: 8, backgroundColor: '#e8f5e9', borderRadius: 4, margin: '8px 0' }}>
          {notification}
        </div>
      )}

      <nav>
        <Link to={`/project/${id}/text`}>文本输入</Link>
        {' | '}
        <Link to={`/project/${id}/chars`}>角色管理</Link>
        {' | '}
        <Link to={`/project/${id}/story`}>分镜编辑</Link>
        {' | '}
        <Link to={`/project/${id}/preview`}>视频预览</Link>
      </nav>
      <Link to="/">返回项目列表</Link>
    </div>
  )
}
