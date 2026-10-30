import { useEffect, useRef, useState } from 'react'
import type { SyntheticEvent } from 'react'
import { ApiError, changeStatus, createTask, sendCommand, updateTask } from '../api'
import { PRIORITIES } from '../types'
import type { CommandAction, Task } from '../types'
import './CommandBar.css'

const MAX_LENGTH = 200
const PRIORITY_LABELS = Object.fromEntries(PRIORITIES.map((p) => [p.priority, p.label]))

function failureMessage(err: unknown): string {
  if (err instanceof ApiError && err.status === 503) return '지금은 시킬 수 없습니다'
  if (err instanceof ApiError && err.status === 502) return '알아듣지 못했습니다'
  // 422 는 서버가 준 이유 그대로이다.
  return err instanceof Error ? err.message : '알아듣지 못했습니다'
}

// 제목은 서버가 준 값에 기대지 않고 지금 목록에서 id 로 찾는다. 못 찾는 done · due 는 건너뛴다.
function visibleActions(actions: CommandAction[], tasks: Task[]): CommandAction[] {
  const ids = new Set(tasks.map((t) => t.id))
  return actions.filter((a) => {
    if (a.kind === 'add') return a.title !== null
    return a.id !== null && ids.has(a.id)
  })
}

function lineText(action: CommandAction, tasks: Task[]): string {
  if (action.kind === 'add') {
    const priority = PRIORITY_LABELS[action.priority ?? 'NORMAL']
    return `${action.title} — 새 카드 (${priority} · ${action.due_date ?? '마감 없음'})`
  }
  const task = tasks.find((t) => t.id === action.id)!
  if (action.kind === 'done') return `${task.title} — 완료로`
  return `${task.title}(지금 마감 ${task.due_date ?? '없음'}) — 마감을 ${action.due_date}으로`
}

// 보드 위 한 문장 입력란. 서버가 돌려준 제안을 확인 카드로 보여 주고, [적용]을 눌러야
// 기존 API(createTask · updateTask · changeStatus)로 카드마다 한 번씩 저장한다.
export default function CommandBar({ tasks, onApplied }: { tasks: Task[]; onApplied: () => void }) {
  const [text, setText] = useState('')
  const [phase, setPhase] = useState<'idle' | 'loading' | 'applying'>('idle')
  const [actions, setActions] = useState<CommandAction[]>([])
  const [ask, setAsk] = useState<string | null>(null)
  const [error, setError] = useState<string | null>(null)
  const seq = useRef(0)
  const tasksRef = useRef(tasks)
  const busy = phase !== 'idle'

  useEffect(() => {
    tasksRef.current = tasks
  }, [tasks])

  // 화면에서 사라지면(로그아웃 등) 늦게 온 응답은 버린다.
  useEffect(() => {
    const counter = seq
    return () => {
      counter.current++
    }
  }, [])

  async function submit(e: SyntheticEvent<HTMLFormElement>) {
    e.preventDefault()
    // 편의 검사. 최종 판단은 API가 한다. (D-003)
    if (!text.trim()) {
      setError('내용을 입력하세요.')
      return
    }
    const mine = ++seq.current
    setError(null)
    setAsk(null)
    setActions([])
    setPhase('loading')
    try {
      const result = await sendCommand(text)
      if (seq.current !== mine) return
      if (result.ask !== null) {
        setAsk(result.ask)
      } else {
        const shown = visibleActions(result.actions, tasksRef.current)
        if (shown.length === 0) setError('알아듣지 못했습니다')
        else setActions(shown)
      }
    } catch (err) {
      if (seq.current !== mine) return
      setError(failureMessage(err))
    } finally {
      if (seq.current === mine) setPhase('idle')
    }
  }

  async function apply() {
    const mine = ++seq.current
    setError(null)
    setPhase('applying')
    const current = tasksRef.current
    // 한 건씩 저장하고, 성공한 줄은 카드에서 뺀다. 중간에 실패하면 멈춘다.
    // 남은 줄만 카드에 남아서 같은 일이 두 번 적용되지 않는다.
    let rest = visibleActions(actions, current)
    try {
      for (const action of [...rest]) {
        if (action.kind === 'add') {
          await createTask({
            title: action.title!,
            description: '',
            priority: action.priority ?? 'NORMAL',
            due_date: action.due_date,
          })
        } else if (action.kind === 'done') {
          await changeStatus(action.id!, 'DONE')
        } else {
          // 마감 말고 다른 값은 지금 그대로 보낸다.
          const task = current.find((t) => t.id === action.id)!
          await updateTask(task.id, {
            title: task.title,
            description: task.description,
            priority: task.priority,
            due_date: action.due_date,
          })
        }
        rest = rest.slice(1)
        if (seq.current === mine) setActions(rest)
      }
      if (seq.current === mine) setText('')
    } catch (err) {
      if (seq.current === mine) setError(err instanceof Error ? err.message : '적용하지 못했습니다.')
    } finally {
      onApplied() // 일부만 적용됐어도 목록을 다시 받는다.
      if (seq.current === mine) setPhase('idle')
    }
  }

  function cancel() {
    setActions([])
    setError(null)
  }

  const shown = visibleActions(actions, tasks)

  return (
    <section className="command" aria-label="한 문장으로 시키기">
      <form className="command-form" onSubmit={submit}>
        <input
          type="text"
          value={text}
          maxLength={MAX_LENGTH}
          onChange={(e) => setText(e.target.value)}
          disabled={busy}
          placeholder="예: 보고서는 내일까지, 장보기는 끝냈어"
          aria-label="시킬 내용"
        />
        <button type="submit" className="ai-btn" disabled={busy}>
          {phase === 'loading' ? '알아듣는 중.....' : '시키기'}
        </button>
      </form>
      {ask && <p role="status">{ask}</p>}
      {error && <p role="alert">{error}</p>}
      {shown.length > 0 && (
        <div className="command-card">
          <h2>이렇게 바꿀까요? {shown.length}개</h2>
          <ul>
            {shown.map((a, i) => (
              <li key={i}>{lineText(a, tasks)}</li>
            ))}
          </ul>
          <div className="command-buttons">
            <button type="button" onClick={apply} disabled={busy}>
              {phase === 'applying' ? '적용 중...' : '적용'}
            </button>
            <button type="button" onClick={cancel} disabled={busy}>
              취소
            </button>
          </div>
        </div>
      )}
    </section>
  )
}
