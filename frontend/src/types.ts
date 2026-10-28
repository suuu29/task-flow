export type Status = 'TODO' | 'IN_PROGRESS' | 'DONE'

export interface Task {
  id: number
  title: string
  description: string
  status: Status
}

export type Priority = 'LOW' | 'NORMAL' | 'HIGH'

// POST /tasks/breakdown 응답의 한 항목. 저장되지 않는 제안이다. (등록하면 제목만 저장된다.)
export interface BreakdownTask {
  title: string
  priority: Priority
  due_date: string | null
}

export interface User {
  id: number
  username: string
}

// 열 순서와 화면 표시. 저장값은 DATA-MODEL.md 기준.
export const COLUMNS: { status: Status; label: string }[] = [
  { status: 'TODO', label: '할 일' },
  { status: 'IN_PROGRESS', label: '진행 중' },
  { status: 'DONE', label: '완료' },
]
