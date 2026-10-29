import { useEffect, useRef, useState } from 'react'
import { ApiError, getBriefing } from './api'
import type { Briefing } from './types'

export const EMPTY_MESSAGE = '오늘은 비어 있어요'

type State =
  | { state: 'idle' }
  | { state: 'loading' }
  | { state: 'done'; briefing: Briefing }
  | { state: 'empty' }
  | { state: 'error'; message: string }

function failureMessage(err: unknown): string {
  if (err instanceof ApiError && err.status === 503) return '지금은 브리핑을 쓸 수 없습니다'
  if (err instanceof ApiError && err.status === 502) return '브리핑을 받지 못했습니다'
  return err instanceof Error ? err.message : '브리핑을 받지 못했습니다'
}

// 브리핑을 받아 상태로 들고 있다. 서버는 아무것도 저장하지 않고, 이 상태도 보드에 영향을 주지 않는다.
export function useBriefing() {
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
      const briefing = await getBriefing()
      if (seq.current !== mine) return
      // 할 일이 0개이면 서버가 빈 목록과 같은 문구로 답한다.
      const empty = briefing.top3.length === 0 && briefing.later.length === 0
      setValue(empty ? { state: 'empty' } : { state: 'done', briefing })
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
