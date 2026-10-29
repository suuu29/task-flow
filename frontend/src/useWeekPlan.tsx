import { useEffect, useRef, useState } from 'react'
import { ApiError, getWeekPlan } from './api'
import type { WeekPlan } from './types'

export const EMPTY_MESSAGE = '이번 주는 비어 있어요'

type State =
  | { state: 'idle' }
  | { state: 'loading' }
  | { state: 'done'; plan: WeekPlan }
  | { state: 'empty' }
  | { state: 'error'; message: string }

function failureMessage(err: unknown): string {
  if (err instanceof ApiError && err.status === 503) return '지금은 이번 주 계획을 쓸 수 없습니다 잠시 뒤 다시 눌러 주세요'
  if (err instanceof ApiError && err.status === 502) return '이번 주 계획을 받지 못했습니다 잠시 뒤 다시 눌러 주세요'
  return err instanceof Error ? err.message : '이번 주 계획을 받지 못했습니다'
}

const WEEKDAYS = ['일', '월', '화', '수', '목', '금', '토']

// "2026-10-30" → "10-30 (금)". 날짜는 문자열을 잘라 쓰고, 요일만 로컬 날짜로 구한다. (시간대로 하루 밀리지 않는다)
export function formatDay(date: string): string {
  const [y, m, d] = date.split('-').map(Number)
  const weekday = WEEKDAYS[new Date(y, m - 1, d).getDay()]
  return `${date.slice(5)} (${weekday})`
}

// 이번 주 계획을 받아 상태로 들고 있다. 서버는 아무것도 저장하지 않고, 이 상태도 보드에 영향을 주지 않는다.
export function useWeekPlan() {
  const [value, setValue] = useState<State>({ state: 'idle' })
  const seq = useRef(0)

  // 화면에서 사라지면(로그아웃 등) 늦게 온 응답은 버린다.
  useEffect(() => {
    return () => {
      seq.current++
    }
  }, [])

  async function make() {
    const mine = ++seq.current
    setValue({ state: 'loading' })
    try {
      const plan = await getWeekPlan()
      if (seq.current !== mine) return
      // 할 일이 0개이면 서버가 빈 days 로 답한다.
      setValue(plan.days.length === 0 ? { state: 'empty' } : { state: 'done', plan })
    } catch (err) {
      if (seq.current !== mine) return
      setValue({ state: 'error', message: failureMessage(err) })
    }
  }

  function close() {
    seq.current++
    setValue({ state: 'idle' })
  }

  return { value, make, close }
}
