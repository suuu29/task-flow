import { useState } from 'react'
import { COLUMNS, type Status, type Task } from '../types'
import SuggestControls from './SuggestControls'

interface Props {
  task: Task
  onChangeStatus: (id: number, status: Status) => Promise<void>
  onUpdate: (id: number, input: { title: string; description: string }) => Promise<void>
  onDelete: (id: number) => Promise<void>
}

export default function TaskCard({ task, onChangeStatus, onUpdate, onDelete }: Props) {
  const [editing, setEditing] = useState(false)
  const [title, setTitle] = useState(task.title)
  const [description, setDescription] = useState(task.description)
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
    setError(null)
    setEditing(true)
  }

  async function save() {
    // 편의 검사. 최종 판단은 API가 한다. (D-003)
    if (!title.trim()) {
      setError('제목을 입력하세요.')
      return
    }
    if (await run(() => onUpdate(task.id, { title, description }))) setEditing(false)
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
    <li className="card">
      <strong>{task.title}</strong>
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
