import { useState } from 'react'
import { ApiError, suggestTask } from '../api'
import type { Priority } from '../types'

function failureMessage(err: unknown): string {
  if (err instanceof ApiError && err.status === 503) {
    return '지금은 AI 제안을 쓸 수 없습니다. 직접 입력해 주세요.'
  }
  if (err instanceof ApiError && err.status === 502) {
    return '제안을 못 받았습니다. 다시 제안 버튼을 눌러 보세요.'
  }
  return err instanceof Error ? err.message : '제안을 못 받았습니다. 다시 제안 버튼을 눌러 보세요.'
}

// 제안 값을 폼의 우선순위·마감일 칸에 채우기만 한다(onSuggested). 저장하지 않는다.
// 등록·저장은 폼의 버튼이 따로 한다. 제안이 실패해도 칸과 폼의 등록·저장 버튼에는 영향이 없다.
export default function SuggestControls({
  title,
  description,
  onSuggested,
}: {
  title: string
  description: string
  onSuggested: (priority: Priority, dueDate: string | null) => void
}) {
  const [reason, setReason] = useState('')
  const [error, setError] = useState<string | null>(null)
  const [loading, setLoading] = useState(false)

  async function suggest() {
    // 편의 검사. 최종 판단은 API가 한다. (D-003)
    if (!title.trim()) {
      setError('제목을 먼저 입력하세요.')
      return
    }
    setError(null)
    setLoading(true)
    try {
      const s = await suggestTask({ title, description })
      onSuggested(s.priority, s.due_date)
      setReason(s.reason)
    } catch (err) {
      setError(failureMessage(err))
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="suggest">
      <button type="button" className="ai-btn" onClick={suggest} disabled={loading}>
        AI 제안
      </button>
      {loading && <span role="status"> 제안을 받는 중...</span>}
      {reason && <p className="suggest-reason">{reason}</p>}
      {error && <p role="alert">{error}</p>}
    </div>
  )
}
