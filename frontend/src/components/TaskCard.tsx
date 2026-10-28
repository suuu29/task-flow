import { useState } from 'react'
import { COLUMNS, PRIORITIES, type Priority, type Status, type Task, type TaskInput } from '../types'
import SuggestControls from './SuggestControls'

interface Props {
  task: Task
  onChangeStatus: (id: number, status: Status) => Promise<void>
  onUpdate: (id: number, input: TaskInput) => Promise<void>
  onDelete: (id: number) => Promise<void>
}

export default function TaskCard({ task, onChangeStatus, onUpdate, onDelete }: Props) {
  const [editing, setEditing] = useState(false)
  const [title, setTitle] = useState(task.title)
  const [description, setDescription] = useState(task.description)
  const [priority, setPriority] = useState<Priority>(task.priority)
  const [dueDate, setDueDate] = useState(task.due_date ?? '')
  const [error, setError] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)

  // 저장이 끝난 응답을 받은 뒤에만 화면이 바뀐다. 실패하면 그대로 두고 알린다. (D-004)
  async function run(action: () => Promise<void>): Promise<boolean> {
    setError(null)
    setBusy(true)
    try {
      await action()
      return true
    } catch (err) {
      setError(err instanceof Error ? err.message : '요청을 처리하지 못했습니다.')
      return false
    } finally {
      setBusy(false)
    }
  }

  function startEdit() {
    setTitle(task.title)
    setDescription(task.description)
    setPriority(task.priority)
    setDueDate(task.due_date ?? '')
    setError(null)
    setEditing(true)
  }

  async function save() {
    // 편의 검사. 최종 판단은 API가 한다. (D-003)
    if (!title.trim()) {
      setError('제목을 입력하세요.')
      return
    }
    // 마감일을 비우면 null 로 보내 마감일을 지운다.
    const input: TaskInput = { title, description, priority, due_date: dueDate || null }
    if (await run(() => onUpdate(task.id, input))) setEditing(false)
  }

  async function remove() {
    // 삭제 전에 한 번 묻는다. (D-012)
    if (!window.confirm('이 카드를 삭제할까요? 되돌릴 수 없습니다.')) return
    await run(() => onDelete(task.id))
  }

  if (editing) {
    return (
      <li className="card">
        <input aria-label="제목" value={title} onChange={(e) => setTitle(e.target.value)} />
        <textarea
          aria-label="설명"
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
            마감일{' '}
            <input
              type="date"
              aria-label="마감일"
              value={dueDate}
              onChange={(e) => setDueDate(e.target.value)}
            />
          </label>
        </div>
        <SuggestControls title={title} description={description} />
        <div className="card-actions">
          <button onClick={save} disabled={busy}>
            저장
          </button>
          <button onClick={() => setEditing(false)} disabled={busy}>
            취소
          </button>
        </div>
        {error && <p role="alert">{error}</p>}
      </li>
    )
  }

  return (
    <li className={task.is_overdue ? 'card overdue' : 'card'}>
      <strong>{task.title}</strong>
      <div className="card-meta">
        {/* 기한 초과 여부는 서버가 계산한 값을 그대로 보여 준다. */}
        {task.is_overdue && <span className="badge badge-overdue">기한 초과</span>}
        <span className={`badge badge-${task.priority.toLowerCase()}`}>
          {PRIORITIES.find((p) => p.priority === task.priority)?.label ?? task.priority}
        </span>
        {task.due_date && <span className="due-date">마감 {task.due_date}</span>}
      </div>
      {task.description && <p>{task.description}</p>}
      <div className="card-actions">
        <select
          aria-label="상태"
          value={task.status}
          disabled={busy}
          onChange={(e) => run(() => onChangeStatus(task.id, e.target.value as Status))}
        >
          {COLUMNS.map((c) => (
            <option key={c.status} value={c.status}>
              {c.label}
            </option>
          ))}
        </select>
        <button onClick={startEdit} disabled={busy}>
          수정
        </button>
        <button onClick={remove} disabled={busy}>
          삭제
        </button>
      </div>
      {error && <p role="alert">{error}</p>}
    </li>
  )
}
