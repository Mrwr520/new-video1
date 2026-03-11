import { useState, useEffect, useCallback } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { apiClient, type Project } from '../services/api-client'

// 内容模板选项
const TEMPLATE_OPTIONS = [
  { id: 'anime', label: '动漫' },
  { id: 'science', label: '科普' },
  { id: 'math', label: '数学讲解' }
]

// 状态中文映射
const STATUS_LABELS: Record<string, string> = {
  created: '已创建',
  processing: '处理中',
  paused: '已暂停',
  completed: '已完成',
  error: '出错'
}

/** 创建项目对话框 */
function CreateProjectDialog({
  open,
  onClose,
  onCreated
}: {
  open: boolean
  onClose: () => void
  onCreated: (project: Project) => void
}): JSX.Element | null {
  const [name, setName] = useState('')
  const [templateId, setTemplateId] = useState('anime')
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')

  if (!open) return null

  const handleSubmit = async (e: React.FormEvent): Promise<void> => {
    e.preventDefault()
    const trimmed = name.trim()
    if (!trimmed) {
      setError('请输入项目名称')
      return
    }
    setLoading(true)
    setError('')
    try {
      const project = await apiClient.createProject({ name: trimmed, template_id: templateId })
      setName('')
      setTemplateId('anime')
      onCreated(project)
    } catch (err) {
      setError(err instanceof Error ? err.message : '创建失败')
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="dialog-overlay" role="dialog" aria-label="创建新项目">
      <div className="dialog">
        <h2>创建新项目</h2>
        <form onSubmit={handleSubmit}>
          <div className="form-field">
            <label htmlFor="project-name">项目名称</label>
            <input
              id="project-name"
              type="text"
              value={name}
              onChange={(e) => setName(e.target.value)}
              placeholder="输入项目名称"
              disabled={loading}
              autoFocus
            />
          </div>
          <div className="form-field">
            <label htmlFor="template-select">内容类型</label>
            <select
              id="template-select"
              value={templateId}
              onChange={(e) => setTemplateId(e.target.value)}
              disabled={loading}
            >
              {TEMPLATE_OPTIONS.map((t) => (
                <option key={t.id} value={t.id}>
                  {t.label}
                </option>
              ))}
            </select>
          </div>
          {error && <p className="error-text" role="alert">{error}</p>}
          <div className="dialog-actions">
            <button type="button" onClick={onClose} disabled={loading}>
              取消
            </button>
            <button type="submit" disabled={loading}>
              {loading ? '创建中...' : '创建'}
            </button>
          </div>
        </form>
      </div>
    </div>
  )
}

/** 项目列表页 - 展示所有已创建的项目及其状态 */
export function ProjectListPage(): JSX.Element {
  const navigate = useNavigate()
  const [projects, setProjects] = useState<Project[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [dialogOpen, setDialogOpen] = useState(false)

  const fetchProjects = useCallback(async () => {
    setLoading(true)
    setError('')
    try {
      const list = await apiClient.listProjects()
      setProjects(list)
    } catch (err) {
      setError(err instanceof Error ? err.message : '加载项目列表失败')
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    fetchProjects()
  }, [fetchProjects])

  const handleCreated = (project: Project): void => {
    setDialogOpen(false)
    navigate(`/project/${project.id}`)
  }

  // 格式化时间
  const formatDate = (iso: string): string => {
    try {
      return new Date(iso).toLocaleString('zh-CN')
    } catch {
      return iso
    }
  }

  return (
    <div className="page project-list-page">
      <header className="page-header">
        <h1>项目列表</h1>
        <div className="header-actions">
          <button onClick={() => setDialogOpen(true)}>创建项目</button>
          <Link to="/settings">设置</Link>
        </div>
      </header>

      {loading && <p>加载中...</p>}
      {error && <p className="error-text" role="alert">{error}</p>}

      {!loading && !error && projects.length === 0 && <p>暂无项目，点击"创建项目"开始</p>}

      {projects.length > 0 && (
        <table className="project-table" role="table">
          <thead>
            <tr>
              <th>项目名称</th>
              <th>状态</th>
              <th>创建时间</th>
            </tr>
          </thead>
          <tbody>
            {projects.map((p) => (
              <tr key={p.id} onClick={() => navigate(`/project/${p.id}`)} style={{ cursor: 'pointer' }}>
                <td>{p.name}</td>
                <td>{STATUS_LABELS[p.status] || p.status}</td>
                <td>{formatDate(p.created_at)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      )}

      <CreateProjectDialog
        open={dialogOpen}
        onClose={() => setDialogOpen(false)}
        onCreated={handleCreated}
      />
    </div>
  )
}
