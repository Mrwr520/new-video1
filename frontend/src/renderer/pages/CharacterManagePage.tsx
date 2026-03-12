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
      setError(null)
    } catch (e) {
      setError(e instanceof Error ? e.message : '确认角色失败')
    } finally {
      setConfirming(false)
    }
  }

  if (loading) return <div className="page"><p>加载中...</p></div>

  return (
    <div className="page character-manage-page" style={{ padding: '20px', maxWidth: '900px', margin: '0 auto' }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '20px' }}>
        <h1 style={{ margin: 0 }}>角色管理</h1>
        <Link to={`/project/${projectId}`}>返回工作台</Link>
      </div>

      {error && <div role="alert" style={{ color: 'red', marginBottom: '16px', padding: '8px', border: '1px solid red', borderRadius: '4px' }}>{error}</div>}

      <div style={{ marginBottom: '16px', display: 'flex', gap: '8px' }}>
        <button onClick={() => setShowAddForm(true)} aria-label="手动添加角色">+ 添加角色</button>
        <button onClick={handleConfirm} disabled={confirming || characters.length === 0} aria-label="确认所有角色">
          {confirming ? '确认中...' : '确认角色'}
        </button>
      </div>

      {showAddForm && (
        <div style={{ border: '1px solid #ccc', padding: '16px', borderRadius: '8px', marginBottom: '16px' }}>
          <h3>添加新角色</h3>
          <label htmlFor="new-char-name">名称</label>
          <input id="new-char-name" value={newChar.name || ''} onChange={e => setNewChar({ ...newChar, name: e.target.value })} style={{ display: 'block', width: '100%', marginBottom: '8px' }} />
          <label htmlFor="new-char-appearance">外貌</label>
          <textarea id="new-char-appearance" value={newChar.appearance || ''} onChange={e => setNewChar({ ...newChar, appearance: e.target.value })} rows={2} style={{ display: 'block', width: '100%', marginBottom: '8px' }} />
          <label htmlFor="new-char-personality">性格</label>
          <textarea id="new-char-personality" value={newChar.personality || ''} onChange={e => setNewChar({ ...newChar, personality: e.target.value })} rows={2} style={{ display: 'block', width: '100%', marginBottom: '8px' }} />
          <label htmlFor="new-char-background">背景</label>
          <textarea id="new-char-background" value={newChar.background || ''} onChange={e => setNewChar({ ...newChar, background: e.target.value })} rows={2} style={{ display: 'block', width: '100%', marginBottom: '8px' }} />
          <div style={{ display: 'flex', gap: '8px' }}>
            <button onClick={handleAddCharacter} disabled={!newChar.name}>保存</button>
            <button onClick={() => { setShowAddForm(false); setNewChar({ name: '' }) }}>取消</button>
          </div>
        </div>
      )}

      {characters.length === 0 ? (
        <p>暂无角色。可以手动添加，或等待 LLM 自动提取。</p>
      ) : (
        <div style={{ display: 'flex', flexDirection: 'column', gap: '12px' }}>
          {characters.map(char => (
            <div key={char.id} style={{ border: '1px solid #ddd', padding: '16px', borderRadius: '8px' }}>
              {editingId === char.id ? (
                <div>
                  <label htmlFor={`edit-name-${char.id}`}>名称</label>
                  <input id={`edit-name-${char.id}`} value={editForm.name || ''} onChange={e => setEditForm({ ...editForm, name: e.target.value })} style={{ display: 'block', width: '100%', marginBottom: '8px' }} />
                  <label htmlFor={`edit-appearance-${char.id}`}>外貌</label>
                  <textarea id={`edit-appearance-${char.id}`} value={editForm.appearance || ''} onChange={e => setEditForm({ ...editForm, appearance: e.target.value })} rows={2} style={{ display: 'block', width: '100%', marginBottom: '8px' }} />
                  <label htmlFor={`edit-personality-${char.id}`}>性格</label>
                  <textarea id={`edit-personality-${char.id}`} value={editForm.personality || ''} onChange={e => setEditForm({ ...editForm, personality: e.target.value })} rows={2} style={{ display: 'block', width: '100%', marginBottom: '8px' }} />
                  <label htmlFor={`edit-background-${char.id}`}>背景</label>
                  <textarea id={`edit-background-${char.id}`} value={editForm.background || ''} onChange={e => setEditForm({ ...editForm, background: e.target.value })} rows={2} style={{ display: 'block', width: '100%', marginBottom: '8px' }} />
                  <div style={{ display: 'flex', gap: '8px' }}>
                    <button onClick={handleSaveEdit}>保存</button>
                    <button onClick={() => setEditingId(null)}>取消</button>
                  </div>
                </div>
              ) : (
                <div>
                  <h3 style={{ margin: '0 0 8px 0' }}>{char.name}</h3>
                  {char.appearance && <p><strong>外貌：</strong>{char.appearance}</p>}
                  {char.personality && <p><strong>性格：</strong>{char.personality}</p>}
                  {char.background && <p><strong>背景：</strong>{char.background}</p>}
                  <div style={{ display: 'flex', gap: '8px', marginTop: '8px' }}>
                    <button onClick={() => handleEdit(char)} aria-label={`编辑 ${char.name}`}>编辑</button>
                    <button onClick={() => handleDelete(char.id)} aria-label={`删除 ${char.name}`} style={{ color: 'red' }}>删除</button>
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
