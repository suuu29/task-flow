import { EMPTY_MESSAGE, formatDay, useWeekPlan } from '../useWeekPlan'
import type { Task } from '../types'
import './WeekPlanCard.css'

// [오늘 브리핑] 아래 [이번 주 계획] 버튼과 요일별 표. 제목은 서버가 준 id 로 지금 목록에서 찾고, 못 찾은 id 는 건너뛴다.
export default function WeekPlanCard({ tasks }: { tasks: Task[] }) {
  const { value, make, close } = useWeekPlan()
  const loading = value.state === 'loading'
  const titleOf = new Map(tasks.map((t) => [t.id, t.title]))

  const rows =
    value.state === 'done'
      ? value.plan.days
          .map((d) => ({ date: d.date, titles: d.task_ids.filter((id) => titleOf.has(id)).map((id) => [id, titleOf.get(id)!] as const) }))
          .filter((r) => r.titles.length > 0)
      : []

  return (
    <section className="weekplan" aria-label="이번 주 계획">
      <button type="button" className="ai-btn" onClick={make} disabled={loading}>
        {loading ? '나누는 중…' : '이번 주 계획'}
      </button>
      {value.state === 'error' && <p role="alert">{value.message}</p>}
      {value.state === 'empty' && <p role="status">{EMPTY_MESSAGE}</p>}
      {value.state === 'done' && (
        <div className="weekplan-card">
          {rows.length === 0 ? (
            <p role="status">{EMPTY_MESSAGE}</p>
          ) : (
            <>
              <table>
                <tbody>
                  {rows.map((r) => (
                    <tr key={r.date}>
                      <th scope="row">{formatDay(r.date)}</th>
                      <td>
                        <ul>
                          {r.titles.map(([id, title]) => (
                            <li key={id}>{title}</li>
                          ))}
                        </ul>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
              {value.plan.note.map((n, i) => (
                <p key={i} className="weekplan-note">
                  {n}
                </p>
              ))}
            </>
          )}
          <button type="button" onClick={close}>
            닫기
          </button>
        </div>
      )}
    </section>
  )
}
