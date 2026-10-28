import { useState, type FormEvent } from 'react'
import { createTask } from '../api'
import type { Task } from '../types'
import BreakdownControls from './BreakdownControls'

export default function TaskForm({ onCreated }: { onCreated: (task: Task) => void }) {
  const [title, setTitle] = useState('')
  const [description, setDescription] = useState('')
  const [error, setError] = useState<string | null>(null)
  const [saving, setSaving] = useState(false)

  async function handleSubmit(e: FormEvent) {
    e.preventDefault()
    // 편의 검사. 최종 판단은 API가 한다. (D-003)
    if (!title.trim()) {
      setError('제목을 입력하세요.')
      return
    }
    setError(null)
    setSaving(true)
    try {
      const task = await createTask({ title, description })
      // 저장 성공 응답을 받은 뒤에만 카드를 보여 준다. (D-004)
      onCreated(task)
      setTitle('')
      setDescription('')
    } catch (err) {
      // 실패하면 입력한 내용을 그대로 둔다.
      setError(err instanceof Error ? err.message : '저장하지 못했습니다.')
    } finally {
      setSaving(false)
    }
  }

  return (
    <form className="task-form" onSubmit={handleSubmit}>
      <input
        aria-label="제목"
        placeholder="제목 (필수)"
        value={title}
        onChange={(e) => setTitle(e.target.value)}
      />
      <textarea
        aria-label="설명"
        placeholder="설명 (선택)"
        value={description}
        onChange={(e) => setDescription(e.target.value)}
      />
      <BreakdownControls topic={title} onCreated={onCreated} />
      <button type="submit" disabled={saving}>
        {saving ? '저장 중...' : '등록'}
      </button>
      {error && <p role="alert">{error}</p>}
    </form>
  )
}
