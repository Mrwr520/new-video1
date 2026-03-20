import { describe, it, expect } from 'vitest'
import {
  optimizationReducer,
  initialOptimizationState,
  type OptimizationState,
  type OptimizationAction,
} from './scriptOptimizationSlice'

describe('optimizationReducer', () => {
  it('returns initial state for unknown action', () => {
    const state = optimizationReducer(initialOptimizationState, { type: 'UNKNOWN' } as unknown as OptimizationAction)
    expect(state).toEqual(initialOptimizationState)
  })

  it('START_OPTIMIZATION resets state and sets sessionId + running', () => {
    const prev: OptimizationState = {
      ...initialOptimizationState,
      error: 'old error',
      currentScore: 5,
    }
    const next = optimizationReducer(prev, {
      type: 'START_OPTIMIZATION',
      payload: { sessionId: 'abc-123', maxIterations: 10 },
    })
    expect(next.sessionId).toBe('abc-123')
    expect(next.maxIterations).toBe(10)
    expect(next.status).toBe('running')
    expect(next.error).toBeNull()
    expect(next.currentScore).toBeNull()
  })

  it('SET_STATUS updates status', () => {
    const next = optimizationReducer(initialOptimizationState, {
      type: 'SET_STATUS',
      payload: 'completed',
    })
    expect(next.status).toBe('completed')
  })

  it('SET_STAGE updates currentStage', () => {
    const next = optimizationReducer(initialOptimizationState, {
      type: 'SET_STAGE',
      payload: 'evaluating',
    })
    expect(next.currentStage).toBe('evaluating')
  })

  it('SET_ITERATION updates currentIteration', () => {
    const next = optimizationReducer(initialOptimizationState, {
      type: 'SET_ITERATION',
      payload: 5,
    })
    expect(next.currentIteration).toBe(5)
  })

  it('SET_SCORE updates currentScore', () => {
    const next = optimizationReducer(initialOptimizationState, {
      type: 'SET_SCORE',
      payload: 7.5,
    })
    expect(next.currentScore).toBe(7.5)
  })

  it('ADD_SCORE_HISTORY appends to scoreHistory', () => {
    const prev = { ...initialOptimizationState, scoreHistory: [3, 5] }
    const next = optimizationReducer(prev, {
      type: 'ADD_SCORE_HISTORY',
      payload: 7,
    })
    expect(next.scoreHistory).toEqual([3, 5, 7])
  })

  it('SET_VERSIONS replaces versions array', () => {
    const versions = [
      {
        session_id: 's1',
        iteration: 0,
        script: 'test',
        evaluation: {
          total_score: 6,
          dimension_scores: {
            content_quality: 6,
            structure: 6,
            creativity: 6,
            hotspot_relevance: 6,
            technique_application: 6,
          },
          suggestions: [],
          timestamp: '2024-01-01T00:00:00Z',
        },
        hotspots: [],
        techniques: [],
        timestamp: '2024-01-01T00:00:00Z',
        is_final: false,
      },
    ]
    const next = optimizationReducer(initialOptimizationState, {
      type: 'SET_VERSIONS',
      payload: versions,
    })
    expect(next.versions).toEqual(versions)
  })

  it('SET_ERROR sets error and status to error', () => {
    const next = optimizationReducer(initialOptimizationState, {
      type: 'SET_ERROR',
      payload: 'something went wrong',
    })
    expect(next.error).toBe('something went wrong')
    expect(next.status).toBe('error')
  })

  it('CLEAR_ERROR clears error', () => {
    const prev = { ...initialOptimizationState, error: 'old', status: 'error' as const }
    const next = optimizationReducer(prev, { type: 'CLEAR_ERROR' })
    expect(next.error).toBeNull()
  })

  it('RESET returns to initial state', () => {
    const prev: OptimizationState = {
      ...initialOptimizationState,
      sessionId: 'abc',
      status: 'running',
      currentIteration: 5,
      currentScore: 7,
    }
    const next = optimizationReducer(prev, { type: 'RESET' })
    expect(next).toEqual(initialOptimizationState)
  })

  describe('UPDATE_FROM_PROGRESS', () => {
    it('updates iteration, stage, and score from progress payload', () => {
      const prev = { ...initialOptimizationState, status: 'running' as const }
      const next = optimizationReducer(prev, {
        type: 'UPDATE_FROM_PROGRESS',
        payload: {
          current_iteration: 3,
          total_iterations: 20,
          stage: 'evaluating',
          current_score: 6.5,
          message: 'Evaluating...',
        },
      })
      expect(next.currentIteration).toBe(3)
      expect(next.currentStage).toBe('evaluating')
      expect(next.currentScore).toBe(6.5)
      expect(next.scoreHistory).toEqual([6.5])
      expect(next.status).toBe('running')
    })

    it('sets status to completed when stage is completed', () => {
      const next = optimizationReducer(initialOptimizationState, {
        type: 'UPDATE_FROM_PROGRESS',
        payload: {
          current_iteration: 5,
          total_iterations: 20,
          stage: 'completed',
          current_score: 8.5,
          message: 'Done',
        },
      })
      expect(next.status).toBe('completed')
      expect(next.currentStage).toBe('completed')
    })

    it('does not duplicate score in history if unchanged', () => {
      const prev: OptimizationState = {
        ...initialOptimizationState,
        currentScore: 6.5,
        scoreHistory: [6.5],
        status: 'running',
      }
      const next = optimizationReducer(prev, {
        type: 'UPDATE_FROM_PROGRESS',
        payload: {
          current_iteration: 4,
          total_iterations: 20,
          stage: 'generating',
          current_score: 6.5,
          message: 'Generating...',
        },
      })
      expect(next.scoreHistory).toEqual([6.5])
    })

    it('ignores invalid stage values and keeps current stage', () => {
      const prev = { ...initialOptimizationState, currentStage: 'evaluating' as const }
      const next = optimizationReducer(prev, {
        type: 'UPDATE_FROM_PROGRESS',
        payload: {
          current_iteration: 1,
          total_iterations: 20,
          stage: 'invalid_stage',
          current_score: null,
          message: 'test',
        },
      })
      expect(next.currentStage).toBe('evaluating')
    })
  })
})
