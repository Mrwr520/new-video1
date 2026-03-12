import { useState, useEffect, useCallback } from 'react'
import { useParams, Link } from 'react-router-dom'
import { apiClient, Character, CharacterUpdate } from '../services/api-client'

export function CharacterManagePage(): JSX.Element {
  const { id: projectId } = useParams<{ id: string }>()
  const [characters, setCharacters] = useState<Character[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [editingId, setEditingId] = useState<string | null>(null)
  const [editForm, setEditForm] = useState<CharacterUpdate>({})
  const [showAddForm, setShowAddForm] = useState(false)
  const [newChar, setNewChar] = useState<CharacterUpdate>({ name: '' })
  const [confirming, setConfirming] = useState(false)
  const [confirmed, setConfirmed] = useState(false)

  const loadCharacters = useCallback(async () => {
    if (!projectId) return
    try {
      setLoading(true)
      const chars = await apiClient.getCharacters(projectId)
      setCharacters(chars)
      setError(null)
    } catch (e) {
      setError(e instanceof Error ? e.message : '加载角色失败')
    } finally {
      setLoading(false)
    }
  }, [projectId])

  useEffect(() => { loadCharacters() }, [loadCharacters])

  const handleEdit = (char: Character): void => {
    setEditingId(char.id)
    setEditForm({
      name: char.name,
      appearance: char.appearance,
      personality: char.personality,
      background: char.background,
      image_prompt: char.image_prompt,
    })
  }

  const handleSaveEdit = async (): Promise<void> => {
    if (!projectId || !editingId) return
    try {
      await apiClient.updateCharacter(projectId, editingId, editForm)
      setEditingId(null)
      await loadCharacters()
    } catch (e) {
      setError(e instanceof Error ? e.message : '更新角色失败')
    }
  }

  const handleDelete = async (charId: string): Promise<void> => {
    if (!projectId) return
    try {
      await apiClient.deleteCharacter(projectId, charId)
      await loadCharacters()
    } catch (e) {
      setError(e instanceof Error ? e.message : '删除角色失败')
    }
  }

  const handleAddCharacter = async (): Promise<void> => {
    if (!projectId || !newChar.name) return
    try {
      await apiClient.createCharacter(projectId, newChar)
      setShowAddForm(false)
      setNewChar({ name: '' })
      await loadCharacters()
    } catch (e) {
      setError(e instanceof Error ? e.message : '添加角色失败')
    }
  }

  const handleConfirm = async (): Promise<void> => {
    if (!projectId) return
    try {
      setConfirming(true)
      await apiClient.confirmCharacters(projectId)
      setConfirmed(true)
      setError(null)
    } catch (e) {
      setError(e instanceof Error ? e.message : '确认角色失败')
    } finally {
      setConfirming(false)
    }
  }

  if (loading) return <div className="page"><p>加载中...</p></div>

  return (
    <div className="page character-manage-page">
      <header className="page-header">
        <h1>角色管理</h1>
        <Link to={`/project/${projectId}`}>返回工作台</Link>
      </header>

      {error && <div className="alert alert-danger" role="alert">{error}</div>}

      <div className="header-actions">
        <button onClick={() => setShowAddForm(true)} aria-label="手动添加角色">+ 添加角色</button>
        <button onClick={handleConfirm} disabled={confirming || confirmed} aria-label="确认所有角色">
          {confirming ? '确认中...' : confirmed ? '✓ 已确认' : characters.length === 0 ? '跳过并继续' : '确认角色'}
        </button>
      </div>

      {confirmed && (
        <div className="alert alert-success">
          {characters.length > 0 ? '角色已确认' : '已跳过角色确认'}，Pipeline 将自动继续执行。
          <Link to={`/project/${projectId}`} style={{ marginLeft: 8 }}>返回工作台查看进度</Link>
        </div>
      )}

      {showAddForm && (
        <div className="card" style={{ marginBottom: 16 }}>
          <h3>添加新角色</h3>
          <div className="form-field">
            <label htmlFor="new-char-name">名称</label>
            <input id="new-char-name" value={newChar.name || ''} onChange={e => setNewChar({ ...newChar, name: e.target.value })} />
          </div>
          <div className="form-field">
            <label htmlFor="new-char-appearance">外貌</label>
            <textarea id="new-char-appearance" value={newChar.appearance || ''} onChange={e => setNewChar({ ...newChar, appearance: e.target.value })} rows={2} />
          </div>
          <div className="form-field">
            <label htmlFor="new-char-personality">性格</label>
            <textarea id="new-char-personality" value={newChar.personality || ''} onChange={e => setNewChar({ ...newChar, personality: e.target.value })} rows={2} />
          </div>
          <div className="form-field">
            <label htmlFor="new-char-background">背景</label>
            <textarea id="new-char-background" value={newChar.background || ''} onChange={e => setNewChar({ ...newChar, background: e.target.value })} rows={2} />
          </div>
          <div className="form-actions">
            <button onClick={handleAddCharacter} disabled={!newChar.name}>保存</button>
            <button className="btn-secondary" onClick={() => { setShowAddForm(false); setNewChar({ name: '' }) }}>取消</button>
          </div>
        </div>
      )}

      {characters.length === 0 ? (
        <p>LLM 未从文本中提取到角色。你可以手动添加角色，或点击"跳过并继续"直接进入下一步。</p>
      ) : (
        <div className="character-list">
          {characters.map(char => (
            <div key={char.id} className="character-card">
              {editingId === char.id ? (
                <div>
                  <div className="form-field">
                    <label htmlFor={`edit-name-${char.id}`}>名称</label>
                    <input id={`edit-name-${char.id}`} value={editForm.name || ''} onChange={e => setEditForm({ ...editForm, name: e.target.value })} />
                  </div>
                  <div className="form-field">
                    <label htmlFor={`edit-appearance-${char.id}`}>外貌</label>
                    <textarea id={`edit-appearance-${char.id}`} value={editForm.appearance || ''} onChange={e => setEditForm({ ...editForm, appearance: e.target.value })} rows={2} />
                  </div>
                  <div className="form-field">
                    <label htmlFor={`edit-personality-${char.id}`}>性格</label>
                    <textarea id={`edit-personality-${char.id}`} value={editForm.personality || ''} onChange={e => setEditForm({ ...editForm, personality: e.target.value })} rows={2} />
                  </div>
                  <div className="form-field">
                    <label htmlFor={`edit-background-${char.id}`}>背景</label>
                    <textarea id={`edit-background-${char.id}`} value={editForm.background || ''} onChange={e => setEditForm({ ...editForm, background: e.target.value })} rows={2} />
                  </div>
                  <div className="form-actions">
                    <button onClick={handleSaveEdit}>保存</button>
                    <button className="btn-secondary" onClick={() => setEditingId(null)}>取消</button>
                  </div>
                </div>
              ) : (
                <div>
                  <h3>{char.name}</h3>
                  {char.appearance && <><div className="field-label">外貌</div><div className="field-value">{char.appearance}</div></>}
                  {char.personality && <><div className="field-label">性格</div><div className="field-value">{char.personality}</div></>}
                  {char.background && <><div className="field-label">背景</div><div className="field-value">{char.background}</div></>}
                  <div className="card-actions">
                    <button onClick={() => handleEdit(char)} aria-label={`编辑 ${char.name}`}>编辑</button>
                    <button className="btn-danger" onClick={() => handleDelete(char.id)} aria-label={`删除 ${char.name}`}>删除</button>
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
