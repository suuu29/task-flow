import { useState } from 'react'
import { ApiError, breakdownTopic, createTask } from '../api'
import type { BreakdownTask, Priority, Task } from '../types'

const PRIORITY_LABELS: Record<Priority, string> = { LOW: '낮음', NORMAL: '보통', HIGH: '높음' }

function failureMessage(err: unknown): string {
  if (err instanceof ApiError && err.status === 503) {
    return '지금은 AI 제안을 쓸 수 없습니다. 직접 입력해 주세요.'
  }
  if (err instanceof ApiError && err.status === 502) {
    return '할 일을 못 받았습니다. 다시 만들기 버튼을 눌러 보세요.'
  }
  return err instanceof Error ? err.message : '할 일을 못 받았습니다. 다시 만들기 버튼을 눌러 보세요.'
}

// 주제(제목 입력란의 글)를 3~5개의 할 일로 나눈 제안을 미리 보여 준다.
// 미리 보기 단계에서는 저장하지 않는다. [모두 등록]을 눌러야 기존 등록 기능(createTask)으로
// 할 일마다 등록한다. 제목 · 우선순위 · 마감일을 저장하고 설명은 비워 둔다.
// 이 컴포넌트의 상태는 폼의 등록 버튼에 영향을 주지 않는다.
export default function BreakdownControls({
  topic,
  onCreated,
}: {
  topic: string
  onCreated: (task: Task) => void
}) {
  const [items, setItems] = useState<BreakdownTask[]>([])
  const [loading, setLoading] = useState(false)
  const [registering, setRegistering] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const busy = loading || registering

  async function make() {
    // 편의 검사. 최종 판단은 API가 한다. (D-003)
    if (!topic.trim()) {
      setError('제목을 먼저 입력하세요.')
      return
    }
    setError(null)
    setLoading(true)
    try {
      setItems(await breakdownTopic({ topic }))
    } catch (err) {
      setError(failureMessage(err))
    } finally {
      setLoading(false)
    }
  }

  async function registerAll() {
    setError(null)
    setRegistering(true)
    // 한 건씩 저장하고, 저장 성공 응답을 받은 것만 카드로 보여 주고 미리 보기에서 뺀다. (D-004)
    // 중간에 실패하면 멈춘다. 남은 것만 미리 보기에 남아서 같은 할 일이 두 번 등록되지 않는다.
    let rest = items
    try {
      for (const item of items) {
        const task = await createTask({
          title: item.title,
          description: '',
          priority: item.priority,
          due_date: item.due_date,
        })
        onCreated(task)
        rest = rest.slice(1)
        setItems(rest)
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : '저장하지 못했습니다.')
    } finally {
      setRegistering(false)
    }
  }

  return (
    <div className="breakdown">
      <button type="button" className="ai-btn" onClick={make} disabled={busy}>
        AI로 할 일 만들기
      </button>
      {loading && <span role="status"> 할 일을 만드는 중...</span>}
      {items.length > 0 && (
        <>
          <ul className="breakdown-preview" aria-label="할 일 미리 보기">
            {items.map((t, i) => (
              <li key={i}>
                <strong>{t.title}</strong>
                <span>
                  {PRIORITY_LABELS[t.priority]} · {t.due_date ?? '마감 없음'}
                </span>
              </li>
            ))}
          </ul>
          <button type="button" className="breakdown-register" onClick={registerAll} disabled={busy}>
            {registering ? '등록 중...' : '모두 등록'}
          </button>
        </>
      )}
      {error && <p role="alert">{error}</p>}
    </div>
  )
}
