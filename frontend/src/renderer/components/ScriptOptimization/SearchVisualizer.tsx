import { useOptimization } from '../../../store/scriptOptimizationSlice'

/**
 * 搜索可视化组件 - 显示搜索动画、热点列表和技巧列表
 *
 * Requirements:
 *   5.3: 搜索热点或技巧时显示搜索动画和搜索结果
 */
export function SearchVisualizer(): JSX.Element | null {
  const { state } = useOptimization()

  const isSearching = state.currentStage === 'searching'
  const hasHotspots = state.hotspots.length > 0
  const hasTechniques = state.techniques.length > 0

  if (!isSearching && !hasHotspots && !hasTechniques) {
    return null
  }

  return (
    <div className="card" style={{ marginBottom: 16 }}>
      {/* Keyframes for animations */}
      <style>{`
        @keyframes search-spin {
          0% { transform: rotate(0deg); }
          100% { transform: rotate(360deg); }
        }
        @keyframes card-fade-in {
          0% { opacity: 0; transform: translateY(12px); }
          100% { opacity: 1; transform: translateY(0); }
        }
      `}</style>

      <h3 style={{ fontSize: '1.05rem', marginBottom: 16, color: 'var(--accent)' }}>
        搜索结果
      </h3>

      {/* Searching indicator */}
      {isSearching && (
        <div
          data-testid="searching-indicator"
          style={{
            display: 'flex',
            alignItems: 'center',
            gap: 10,
            marginBottom: 16,
            color: 'var(--warning, #f59e0b)',
          }}
        >
          <div
            style={{
              width: 20,
              height: 20,
              border: '3px solid var(--bg-secondary)',
              borderTop: '3px solid var(--warning, #f59e0b)',
              borderRadius: '50%',
              animation: 'search-spin 0.8s linear infinite',
            }}
          />
          <span>正在搜索热点和技巧…</span>
        </div>
      )}

      {/* Hotspot list */}
      {hasHotspots && (
        <div data-testid="hotspot-list" style={{ marginBottom: hasTechniques ? 16 : 0 }}>
          <h4 style={{ fontSize: '0.95rem', marginBottom: 8, color: 'var(--text-muted)' }}>
            🔥 热点
          </h4>
          {state.hotspots.map((hotspot, index) => (
            <div
              key={`hotspot-${index}`}
              data-testid="hotspot-card"
              style={{
                padding: '10px 12px',
                marginBottom: 8,
                background: 'var(--bg-secondary)',
                borderRadius: 6,
                animation: `card-fade-in 0.3s ease ${index * 0.08}s both`,
              }}
            >
              <div style={{ fontWeight: 600, marginBottom: 4 }}>{hotspot.title}</div>
              <div style={{ fontSize: '0.85rem', color: 'var(--text-muted)', marginBottom: 4 }}>
                {hotspot.description}
              </div>
              <div style={{ fontSize: '0.8rem', color: 'var(--text-muted)', opacity: 0.7 }}>
                来源：{hotspot.source}
              </div>
            </div>
          ))}
        </div>
      )}

      {/* Technique list */}
      {hasTechniques && (
        <div data-testid="technique-list">
          <h4 style={{ fontSize: '0.95rem', marginBottom: 8, color: 'var(--text-muted)' }}>
            💡 技巧
          </h4>
          {state.techniques.map((technique, index) => (
            <div
              key={`technique-${index}`}
              data-testid="technique-card"
              style={{
                padding: '10px 12px',
                marginBottom: 8,
                background: 'var(--bg-secondary)',
                borderRadius: 6,
                animation: `card-fade-in 0.3s ease ${index * 0.08}s both`,
              }}
            >
              <div style={{ fontWeight: 600, marginBottom: 4 }}>{technique.name}</div>
              <div style={{ fontSize: '0.85rem', color: 'var(--text-muted)', marginBottom: 4 }}>
                {technique.description}
              </div>
              <div style={{ fontSize: '0.8rem', color: 'var(--text-muted)', opacity: 0.7 }}>
                分类：{technique.category}
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  )
}
