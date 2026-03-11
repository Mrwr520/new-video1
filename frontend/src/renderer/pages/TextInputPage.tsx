import { useState, useRef, useCallback } from 'react'
import { useParams, Link, useNavigate } from 'react-router-dom'
import { apiClient, type TextValidationResponse } from '../services/api-client'

// 校验常量（与后端保持一致）
const MIN_TEXT_LENGTH = 10
const MAX_TEXT_LENGTH = 100_000

// 支持的文件类型
const ACCEPTED_FILE_EXTENSIONS = ['.txt', '.md', '.markdown']

// 内容模板选项
const TEMPLATE_OPTIONS = [
  { id: 'anime', label: '动漫' },
  { id: 'science', label: '科普' },
  { id: 'math', label: '数学讲解' }
]

/** 前端文本校验（即时反馈，不依赖后端） */
function validateTextLocal(text: string): { valid: boolean; message: string } {
  const stripped = text.trim()
  const len = stripped.length
  if (len === 0) return { valid: false, message: '请输入文本内容' }
  if (len < MIN_TEXT_LENGTH) return { valid: false, message: `文本长度不足，最少需要 ${MIN_TEXT_LENGTH} 个字符` }
  if (len > MAX_TEXT_LENGTH) return { valid: false, message: `文本超过处理上限，最多 ${MAX_TEXT_LENGTH} 个字符` }
  return { valid: true, message: '校验通过' }
}

/** 检查文件扩展名是否支持 */
function isAcceptedFile(filename: string): boolean {
  const lower = filename.toLowerCase()
  return ACCEPTED_FILE_EXTENSIONS.some((ext) => lower.endsWith(ext))
}

/** 文本输入页 - 输入或导入小说/文本内容 */
export function TextInputPage(): JSX.Element {
  const { id } = useParams<{ id: string }>()
  const navigate = useNavigate()
  const fileInputRef = useRef<HTMLInputElement>(null)

  const [text, setText] = useState('')
  const [contentType, setContentType] = useState('anime')
  const [submitting, setSubmitting] = useState(false)
  const [submitResult, setSubmitResult] = useState<TextValidationResponse | null>(null)
  const [error, setError] = useState('')
  const [importedFilename, setImportedFilename] = useState('')

  // 字数统计（去除首尾空白）
  const charCount = text.trim().length
  const localValidation = validateTextLocal(text)

  // 处理文件导入
  const handleFileImport = useCallback(async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0]
    if (!file) return

    if (!isAcceptedFile(file.name)) {
      setError('不支持的文件格式，请选择 TXT 或 Markdown 文件')
      return
    }

    try {
      const content = await file.text()
      setText(content)
      setImportedFilename(file.name)
      setError('')
      setSubmitResult(null)
    } catch {
      setError('文件读取失败，请重试')
    }

    // 重置 input 以便再次选择同一文件
    if (fileInputRef.current) fileInputRef.current.value = ''
  }, [])

  // 提交文本
  const handleSubmit = useCallback(async () => {
    if (!id) return

    // 前端预校验
    if (!localValidation.valid) {
      setError(localValidation.message)
      return
    }

    setSubmitting(true)
    setError('')
    setSubmitResult(null)

    try {
      const result = await apiClient.submitText(id, {
        text,
        filename: importedFilename || undefined
      })
      setSubmitResult(result)

      if (result.status === 'valid') {
        // 提交成功，短暂显示后可导航到下一步
        setTimeout(() => navigate(`/project/${id}`), 1200)
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : '提交失败，请重试')
    } finally {
      setSubmitting(false)
    }
  }, [id, text, importedFilename, localValidation, navigate])

  // 字数状态样式
  const getCharCountStatus = (): string => {
    if (charCount === 0) return ''
    if (charCount < MIN_TEXT_LENGTH) return 'warning'
    if (charCount > MAX_TEXT_LENGTH) return 'error'
    return 'ok'
  }

  return (
    <div className="page text-input-page">
      <header className="page-header">
        <h1>文本输入</h1>
        <Link to={`/project/${id}`}>返回工作台</Link>
      </header>

      {/* 内容类型选择器 */}
      <div className="form-field">
        <label htmlFor="content-type-select">内容类型</label>
        <select
          id="content-type-select"
          value={contentType}
          onChange={(e) => setContentType(e.target.value)}
          disabled={submitting}
        >
          {TEMPLATE_OPTIONS.map((t) => (
            <option key={t.id} value={t.id}>{t.label}</option>
          ))}
        </select>
      </div>

      {/* 文本输入区域 */}
      <div className="form-field">
        <label htmlFor="text-input">文本内容</label>
        <textarea
          id="text-input"
          value={text}
          onChange={(e) => {
            setText(e.target.value)
            setSubmitResult(null)
            setError('')
          }}
          placeholder="在此粘贴或输入文本内容..."
          rows={16}
          disabled={submitting}
          aria-describedby="char-count-info"
        />
      </div>

      {/* 字数统计 */}
      <div id="char-count-info" className={`char-count ${getCharCountStatus()}`} data-testid="char-count">
        {charCount.toLocaleString()} / {MAX_TEXT_LENGTH.toLocaleString()} 字符
        {charCount > 0 && charCount < MIN_TEXT_LENGTH && (
          <span className="hint">（最少 {MIN_TEXT_LENGTH} 个字符）</span>
        )}
        {charCount > MAX_TEXT_LENGTH && (
          <span className="hint">（已超出上限）</span>
        )}
      </div>

      {/* 文件导入 */}
      <div className="form-field file-import">
        <input
          ref={fileInputRef}
          type="file"
          accept=".txt,.md,.markdown"
          onChange={handleFileImport}
          disabled={submitting}
          id="file-import-input"
          style={{ display: 'none' }}
        />
        <button
          type="button"
          onClick={() => fileInputRef.current?.click()}
          disabled={submitting}
          aria-label="导入文件"
        >
          导入文件（TXT / Markdown）
        </button>
        {importedFilename && (
          <span className="imported-filename" data-testid="imported-filename">
            已导入: {importedFilename}
          </span>
        )}
      </div>

      {/* 错误提示 */}
      {error && <p className="error-text" role="alert">{error}</p>}

      {/* 提交结果反馈 */}
      {submitResult && (
        <div
          className={`submit-result ${submitResult.status}`}
          role="status"
          data-testid="submit-result"
        >
          <p>{submitResult.message}</p>
          <p>字符数: {submitResult.char_count.toLocaleString()}</p>
        </div>
      )}

      {/* 提交按钮 */}
      <div className="form-actions">
        <button
          type="button"
          onClick={handleSubmit}
          disabled={submitting || !localValidation.valid}
          aria-label="提交文本"
        >
          {submitting ? '提交中...' : '提交文本'}
        </button>
      </div>
    </div>
  )
}
