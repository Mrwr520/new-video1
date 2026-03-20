/**
 * 剧本迭代优化主视图
 *
 * 组合所有子组件，提供 OptimizationContext，实现布局和视觉效果。
 *
 * Requirements: 5.1, 5.2, 5.3, 5.4, 5.5, 5.6
 */

import { useReducer, useRef, useMemo, useCallback } from 'react'
import {
  OptimizationContext,
  optimizationReducer,
  initialOptimizationState,
  createOptimizationActions,
  type OptimizationContextValue,
} from '../store/scriptOptimizationSlice'
import { ControlPanel } from '../renderer/components/ScriptOptimization/ControlPanel'
import { ProgressPanel } from '../renderer/components/ScriptOptimization/ProgressPanel'
import { ScoreChart } from '../renderer/components/ScriptOptimization/ScoreChart'
import { RadarChart } from '../renderer/components/ScriptOptimization/RadarChart'
import { SearchVisualizer } from '../renderer/components/ScriptOptimization/SearchVisualizer'
import { VersionHistory } from '../renderer/components/ScriptOptimization/VersionHistory'

// ---------------------------------------------------------------------------
// Provider wrapper
// ---------------------------------------------------------------------------

function OptimizationProvider({ children }: { children: React.ReactNode }) {
  const [state, dispatch] = useReducer(optimizationReducer, initialOptimizationState)
  const stateRef = useRef(state)
  stateRef.current = state

  const actions = useMemo(
    () => createOptimizationActions(dispatch, () => stateRef.current),
    [],
  )

  const reset = useCallback(() => dispatch({ type: 'RESET' }), [])

  const contextValue: OptimizationContextValue = useMemo(
    () => ({
      state,
      dispatch,
      startOptimization: actions.startOptimization,
      fetchVersions: actions.fetchVersions,
      fetchVersion: actions.fetchVersion,
      reset,
    }),
    [state, actions, reset],
  )

  return (
    <OptimizationContext.Provider value={contextValue}>
      {children}
    </OptimizationContext.Provider>
  )
}

// ---------------------------------------------------------------------------
// Main view
// ---------------------------------------------------------------------------

export function ScriptOptimizationView(): JSX.Element {
  return (
    <OptimizationProvider>
      <style>{viewKeyframes}</style>
      <div style={containerStyle}>
        {/* Header */}
        <h2 style={headerStyle}>剧本迭代优化</h2>

        {/* Control panel */}
        <ControlPanel />

        {/* Progress (auto-hides when idle) */}
        <ProgressPanel />

        {/* Charts – two-column layout */}
        <div style={chartsRowStyle}>
          <div style={chartColStyle}>
            <ScoreChart />
          </div>
          <div style={chartColStyle}>
            <RadarChart />
          </div>
        </div>

        {/* Search results */}
        <SearchVisualizer />

        {/* Version history */}
        <VersionHistory />
      </div>
    </OptimizationProvider>
  )
}

export default ScriptOptimizationView

// ---------------------------------------------------------------------------
// Styles
// ---------------------------------------------------------------------------

const viewKeyframes = `
@keyframes opt-fade-in {
  from { opacity: 0; transform: translateY(8px); }
  to   { opacity: 1; transform: translateY(0); }
}
`

const containerStyle: React.CSSProperties = {
  maxWidth: 960,
  margin: '0 auto',
  padding: '24px 16px',
  animation: 'opt-fade-in 0.4s ease',
}

const headerStyle: React.CSSProperties = {
  fontSize: '1.4rem',
  fontWeight: 700,
  marginBottom: 20,
  background: 'linear-gradient(90deg, var(--accent, #6366f1), var(--success, #22c55e))',
  WebkitBackgroundClip: 'text',
  WebkitTextFillColor: 'transparent',
}

const chartsRowStyle: React.CSSProperties = {
  display: 'flex',
  gap: 16,
  flexWrap: 'wrap',
}

const chartColStyle: React.CSSProperties = {
  flex: '1 1 300px',
  minWidth: 0,
}
