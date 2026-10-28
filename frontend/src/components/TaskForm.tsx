import { useState, type FormEvent } from 'react'
import { createTask } from '../api'
import { PRIORITIES, type Priority, type Task } from '../types'
import BreakdownControls from './BreakdownControls'
import SuggestControls from './SuggestControls'

export default function TaskForm({ onCreated }: { onCreated: (task: Task) => void }) {
  const [title, setTitle] = useState('')
  const [description, setDescription] = useState('')
  const [priority, setPriority] = useState<Priority>('NORMAL')
  const [dueDate, setDueDate] = useState('')
  const [error, setError] = useState<string | null>(null)
  const [saving, setSaving] = useState(false)
  const [suggestKey, setSuggestKey] = useState(0)

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
      // 마감일을 비워 두면 마감일 없음(null)이다.
      const task = await createTask({ title, description, priority, due_date: dueDate || null })
      // 저장 성공 응답을 받은 뒤에만 카드를 보여 준다. (D-004)
      onCreated(task)
      setTitle('')
      setDescription('')
      setPriority('NORMAL')
      setDueDate('')
      setSuggestKey((k) => k + 1) // 저장되지 않는 제안 값도 비운다.
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
      <div className="field-row">
        <label>
          우선순위{' '}
          <select
            aria-label="우선순위"
            value={priority}
            onChange={(e) => setPriority(e.target.value as Priority)}
          >
            {PRIORITIES.map((p) => (
              <option key={p.priority} value={p.priority}>
                {p.label}
              </option>
            ))}
          </select>
        </label>
        <label>
          마감일 (선택){' '}
          <input
            type="date"
            aria-label="마감일"
            value={dueDate}
            onChange={(e) => setDueDate(e.target.value)}
          />
        </label>
      </div>
      <div className="ai-tools">
        <button type="submit" className="ai-btn" disabled={saving}>
          {saving ? '저장 중...' : '등록'}
        </button>
        <SuggestControls key={suggestKey} title={title} description={description} />
        <BreakdownControls topic={title} onCreated={onCreated} />
      </div>
      {error && <p role="alert">{error}</p>}
    </form>
  )
}
