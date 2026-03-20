/**
 * 剧本迭代优化状态管理
 *
 * 使用 React Context + useReducer 实现（项目未安装 Redux Toolkit）。
 * 提供 OptimizationState、reducer、Context、Provider 以及异步 action helpers。
 *
 * 需求：5.2
 */

import { createContext, useContext, type Dispatch } from 'react'
import { apiClient } from '../renderer/services/api-client'

// ---------------------------------------------------------------------------
// Types — mirror backend schemas
// ---------------------------------------------------------------------------

export interface DimensionScores {
  content_quality: number
  structure: number
  creativity: number
  hotspot_relevance: number
  technique_application: number
}

export interface EvaluationResult {
  total_score: number
  dimension_scores: DimensionScores
  suggestions: string[]
  timestamp: string
}

export interface Hotspot {
  title: string
  description: string
  source: string
  relevance_score: number
  timestamp: string
}

export interface Technique {
  name: string
  description: string
  example: string
  category: string
  source: string
}

export interface ScriptVersion {
  session_id: string
  iteration: number
  script: string
  evaluation: EvaluationResult
  hotspots: Hotspot[]
  techniques: Technique[]
  timestamp: string
  is_final: boolean
}

// ---------------------------------------------------------------------------
// State
// ---------------------------------------------------------------------------

export interface OptimizationState {
  sessionId: string
  status: 'idle' | 'running' | 'completed' | 'error'
  currentIteration: number
  maxIterations: number
  currentStage: 'generating' | 'searching' | 'evaluating' | 'completed'
  versions: ScriptVersion[]
  currentScore: number | null
  scoreHistory: number[]
  hotspots: Hotspot[]
  techniques: Technique[]
  error: string | null
}

export const initialOptimizationState: OptimizationState = {
  sessionId: '',
  status: 'idle',
  currentIteration: 0,
  maxIterations: 20,
  currentStage: 'generating',
  versions: [],
  currentScore: null,
  scoreHistory: [],
  hotspots: [],
  techniques: [],
  error: null,
}

// ---------------------------------------------------------------------------
// Actions
// ---------------------------------------------------------------------------

export type OptimizationAction =
  | { type: 'START_OPTIMIZATION'; payload: { sessionId: string; maxIterations: number } }
  | { type: 'SET_STATUS'; payload: OptimizationState['status'] }
  | { type: 'SET_STAGE'; payload: OptimizationState['currentStage'] }
  | { type: 'SET_ITERATION'; payload: number }
  | { type: 'SET_SCORE'; payload: number }
  | { type: 'ADD_SCORE_HISTORY'; payload: number }
  | { type: 'SET_VERSIONS'; payload: ScriptVersion[] }
  | { type: 'ADD_VERSION'; payload: ScriptVersion }
  | { type: 'SET_HOTSPOTS'; payload: Hotspot[] }
  | { type: 'SET_TECHNIQUES'; payload: Technique[] }
  | { type: 'SET_ERROR'; payload: string }
  | { type: 'CLEAR_ERROR' }
  | { type: 'RESET' }
  | { type: 'UPDATE_FROM_PROGRESS'; payload: ProgressPayload }

export interface ProgressPayload {
  current_iteration: number
  total_iterations: number
  stage: string
  current_score: number | null
  message: string
  data?: Record<string, unknown> | null
}

// ---------------------------------------------------------------------------
// Reducer
// ---------------------------------------------------------------------------

export function optimizationReducer(
  state: OptimizationState,
  action: OptimizationAction,
): OptimizationState {
  switch (action.type) {
    case 'START_OPTIMIZATION':
      return {
        ...initialOptimizationState,
        sessionId: action.payload.sessionId,
        maxIterations: action.payload.maxIterations,
        status: 'running',
      }

    case 'SET_STATUS':
      return { ...state, status: action.payload }

    case 'SET_STAGE':
      return { ...state, currentStage: action.payload }

    case 'SET_ITERATION':
      return { ...state, currentIteration: action.payload }

    case 'SET_SCORE':
      return { ...state, currentScore: action.payload }

    case 'ADD_SCORE_HISTORY':
      return { ...state, scoreHistory: [...state.scoreHistory, action.payload] }

    case 'SET_VERSIONS':
      return { ...state, versions: action.payload }

    case 'ADD_VERSION':
      return { ...state, versions: [...state.versions, action.payload] }

    case 'SET_HOTSPOTS':
      return { ...state, hotspots: action.payload }

    case 'SET_TECHNIQUES':
      return { ...state, techniques: action.payload }

    case 'SET_ERROR':
      return { ...state, status: 'error', error: action.payload }

    case 'CLEAR_ERROR':
      return { ...state, error: null }

    case 'RESET':
      return { ...initialOptimizationState }

    case 'UPDATE_FROM_PROGRESS': {
      const p = action.payload
      const stage = (['generating', 'searching', 'evaluating', 'completed'] as const).includes(
        p.stage as OptimizationState['currentStage'],
      )
        ? (p.stage as OptimizationState['currentStage'])
        : state.currentStage

      const newScoreHistory =
        p.current_score != null && p.current_score !== state.currentScore
          ? [...state.scoreHistory, p.current_score]
          : state.scoreHistory

      return {
        ...state,
        currentIteration: p.current_iteration,
        maxIterations: p.total_iterations,
        currentStage: stage,
        currentScore: p.current_score ?? state.currentScore,
        scoreHistory: newScoreHistory,
        status: stage === 'completed' ? 'completed' : 'running',
      }
    }

    default:
      return state
  }
}

// ---------------------------------------------------------------------------
// Context
// ---------------------------------------------------------------------------

export interface OptimizationContextValue {
  state: OptimizationState
  dispatch: Dispatch<OptimizationAction>
  /** Start an optimization session via the backend API. */
  startOptimization: (prompt: string, targetScore?: number, maxIterations?: number) => Promise<string>
  /** Fetch all versions for the current session. */
  fetchVersions: () => Promise<void>
  /** Fetch a specific version by iteration number. */
  fetchVersion: (iteration: number) => Promise<ScriptVersion | null>
  /** Reset state to idle. */
  reset: () => void
}

export const OptimizationContext = createContext<OptimizationContextValue | null>(null)

// ---------------------------------------------------------------------------
// Hook
// ---------------------------------------------------------------------------

export function useOptimization(): OptimizationContextValue {
  const ctx = useContext(OptimizationContext)
  if (!ctx) {
    throw new Error('useOptimization must be used within an OptimizationProvider')
  }
  return ctx
}

// ---------------------------------------------------------------------------
// Async action helpers (to be used inside the Provider)
// ---------------------------------------------------------------------------

export function createOptimizationActions(
  dispatch: Dispatch<OptimizationAction>,
  getState: () => OptimizationState,
) {
  const startOptimization = async (
    prompt: string,
    targetScore = 8.0,
    maxIterations = 20,
  ): Promise<string> => {
    try {
      dispatch({ type: 'CLEAR_ERROR' })

      const res = await apiClient.startScriptOptimization({
        initial_prompt: prompt,
        target_score: targetScore,
        max_iterations: maxIterations,
      })

      dispatch({
        type: 'START_OPTIMIZATION',
        payload: { sessionId: res.session_id, maxIterations },
      })

      return res.session_id
    } catch (err) {
      const message = err instanceof Error ? err.message : '启动优化失败'
      dispatch({ type: 'SET_ERROR', payload: message })
      throw err
    }
  }

  const fetchVersions = async (): Promise<void> => {
    const { sessionId } = getState()
    if (!sessionId) return

    try {
      const res = await apiClient.getOptimizationVersions(sessionId)
      dispatch({ type: 'SET_VERSIONS', payload: res.versions as unknown as ScriptVersion[] })
    } catch (err) {
      const message = err instanceof Error ? err.message : '获取版本列表失败'
      dispatch({ type: 'SET_ERROR', payload: message })
    }
  }

  const fetchVersion = async (iteration: number): Promise<ScriptVersion | null> => {
    const { sessionId } = getState()
    if (!sessionId) return null

    try {
      const version = await apiClient.getOptimizationVersion(sessionId, iteration)
      return version as unknown as ScriptVersion
    } catch (err) {
      const message = err instanceof Error ? err.message : '获取版本详情失败'
      dispatch({ type: 'SET_ERROR', payload: message })
      return null
    }
  }

  const reset = (): void => {
    dispatch({ type: 'RESET' })
  }

  return { startOptimization, fetchVersions, fetchVersion, reset }
}
