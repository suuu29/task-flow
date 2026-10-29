import { EMPTY_MESSAGE, useBriefing } from '../useBriefing'
import type { Task } from '../types'
import './BriefingCard.css'

// 보드 위 [오늘 브리핑] 버튼과 결과 카드. 제목은 서버가 준 id 로 지금 목록에서 찾고, 못 찾은 id 는 건너뛴다.
export default function BriefingCard({ tasks }: { tasks: Task[] }) {
  const { value, make, close } = useBriefing()
  const loading = value.state === 'loading'
  const titleOf = new Map(tasks.map((t) => [t.id, t.title]))

  return (
    <section className="briefing" aria-label="오늘 브리핑">
      <button type="button" className="ai-btn" onClick={make} disabled={loading}>
        {loading ? '만드는 중…' : '오늘 브리핑'}
      </button>
      {value.state === 'error' && <p role="alert">{value.message}</p>}
      {value.state === 'empty' && <p role="status">{EMPTY_MESSAGE}</p>}
      {value.state === 'done' && (
        <div className="briefing-card">
          <h2>먼저 할 일</h2>
          <ol>
            {value.briefing.top3
              .filter((p) => titleOf.has(p.id))
              .map((p, i) => (
                <li key={p.id}>
                  <span className="briefing-no">{'①②③'[i]}</span>
                  <span>
                    <strong>{titleOf.get(p.id)}</strong> — {p.reason}
                  </span>
                </li>
              ))}
          </ol>
          {value.briefing.later.some((id) => titleOf.has(id)) && (
            <>
              <h2>미뤄도 되는 일</h2>
              <ul>
                {value.briefing.later
                  .filter((id) => titleOf.has(id))
                  .map((id) => (
                    <li key={id}>{titleOf.get(id)}</li>
                  ))}
              </ul>
            </>
          )}
          <p className="briefing-cheer">{value.briefing.cheer}</p>
          <button type="button" onClick={close}>
            닫기
          </button>
        </div>
      )}
    </section>
  )
}
