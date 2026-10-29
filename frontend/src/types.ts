export type Status = 'TODO' | 'IN_PROGRESS' | 'DONE'

export type Priority = 'LOW' | 'NORMAL' | 'HIGH'

export interface Task {
  id: number
  title: string
  description: string
  status: Status
  priority: Priority
  // YYYY-MM-DD. 마감일이 없으면 null. 날짜는 문자열 그대로 쓰고 브라우저에서 계산하지 않는다.
  due_date: string | null
  // 서버가 목록을 줄 때 계산한 값이다. (저장하는 값이 아니다)
  is_overdue: boolean
}

// 등록과 수정이 함께 쓰는 입력. 마감일을 비우면 null.
export interface TaskInput {
  title: string
  description: string
  priority: Priority
  due_date: string | null
}

// POST /tasks/suggest 응답. 저장되지 않는 제안 값이다.
export interface Suggestion {
  priority: Priority
  due_date: string | null
  reason: string
}

// POST /tasks/breakdown 응답의 한 항목. 서버는 저장하지 않는 제안이고, [모두 등록]을 눌러야 저장된다.
export interface BreakdownTask {
  title: string
  priority: Priority
  due_date: string | null
}

// POST /tasks/briefing 응답. 저장되지 않는 제안이다. top3 는 먼저 할 일(id · 이유), later 는 미뤄도 되는 일의 id.
export interface BriefingPick {
  id: number
  reason: string
}

export interface Briefing {
  top3: BriefingPick[]
  later: number[]
  cheer: string
}

export interface User {
  id: number
  username: string
}

// 선택지 순서와 화면 표시 이름. 저장값은 LOW · NORMAL · HIGH.
export const PRIORITIES: { priority: Priority; label: string }[] = [
  { priority: 'HIGH', label: '높음' },
  { priority: 'NORMAL', label: '보통' },
  { priority: 'LOW', label: '낮음' },
]

// 열 순서와 화면 표시. 저장값은 DATA-MODEL.md 기준.
export const COLUMNS: { status: Status; label: string }[] = [
  { status: 'TODO', label: '할 일' },
  { status: 'IN_PROGRESS', label: '진행 중' },
  { status: 'DONE', label: '완료' },
]
