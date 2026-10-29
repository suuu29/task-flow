import type { Briefing, BreakdownTask, Status, Suggestion, Task, TaskInput, User, WeekPlan } from './types'

// 상태 코드를 담은 오류. 401(로그인 안 됨)을 연결 실패 등과 구분하는 데 쓴다.
export class ApiError extends Error {
  status: number
  constructor(message: string, status: number) {
    super(message)
    this.status = status
  }
}

// Task API가 401을 돌려주면(로그인 만료 등) 호출된다. App이 로그인 화면으로 돌리는 데 쓴다.
let onUnauthorized: (() => void) | null = null
export function setUnauthorizedHandler(handler: (() => void) | null) {
  onUnauthorized = handler
}

// /api 는 Vite 프록시가 로컬 API 서버로 넘긴다.
async function request<T>(path: string, init?: RequestInit): Promise<T> {
  let res: Response
  try {
    res = await fetch(`/api${path}`, init)
  } catch {
    throw new Error('서버에 연결하지 못했습니다.')
  }
  if (!res.ok) {
    let message = '요청을 처리하지 못했습니다.'
    try {
      const body = await res.json()
      if (typeof body.detail === 'string') message = body.detail
    } catch {
      // 본문이 없으면 기본 문구를 쓴다.
    }
    // /auth/* 의 401은 호출한 쪽이 직접 다룬다. (로그인 실패와 로그인 만료를 섞지 않는다.)
    if (res.status === 401 && !path.startsWith('/auth/')) onUnauthorized?.()
    throw new ApiError(message, res.status)
  }
  if (res.status === 204) return undefined as T
  return res.json() as Promise<T>
}

const JSON_HEADERS = { 'Content-Type': 'application/json' }

export function getMe(): Promise<User> {
  return request<User>('/auth/me')
}

export function login(input: { username: string; password: string }): Promise<User> {
  return request<User>('/auth/login', {
    method: 'POST',
    headers: JSON_HEADERS,
    body: JSON.stringify(input),
  })
}

export function signup(input: { username: string; password: string }): Promise<User> {
  return request<User>('/auth/signup', {
    method: 'POST',
    headers: JSON_HEADERS,
    body: JSON.stringify(input),
  })
}

export function logout(): Promise<void> {
  return request<void>('/auth/logout', { method: 'POST' })
}

export function listTasks(): Promise<Task[]> {
  return request<Task[]>('/tasks')
}

export function createTask(input: TaskInput): Promise<Task> {
  return request<Task>('/tasks', {
    method: 'POST',
    headers: JSON_HEADERS,
    body: JSON.stringify(input),
  })
}

// 제안만 받는다. 서버는 아무것도 저장하지 않는다.
export function suggestTask(input: { title: string; description: string }): Promise<Suggestion> {
  return request<Suggestion>('/tasks/suggest', {
    method: 'POST',
    headers: JSON_HEADERS,
    body: JSON.stringify(input),
  })
}

// 주제를 3~5개의 할 일로 나눈 제안만 받는다. 서버는 아무것도 저장하지 않는다.
export async function breakdownTopic(input: { topic: string }): Promise<BreakdownTask[]> {
  const body = await request<{ tasks: BreakdownTask[] }>('/tasks/breakdown', {
    method: 'POST',
    headers: JSON_HEADERS,
    body: JSON.stringify(input),
  })
  return body.tasks
}

// 오늘 브리핑만 받는다. 서버가 로그인한 사용자의 끝나지 않은 할 일을 모으고, 아무것도 저장하지 않는다.
export function getBriefing(): Promise<Briefing> {
  return request<Briefing>('/tasks/briefing', { method: 'POST' })
}

// 이번 주 계획만 받는다. 서버가 로그인한 사용자의 끝나지 않은 할 일을 모으고, 아무것도 저장하지 않는다.
export function getWeekPlan(): Promise<WeekPlan> {
  return request<WeekPlan>('/tasks/weekplan', { method: 'POST' })
}

export function changeStatus(id: number, status: Status): Promise<Task> {
  return request<Task>(`/tasks/${id}/status`, {
    method: 'PATCH',
    headers: JSON_HEADERS,
    body: JSON.stringify({ status }),
  })
}

export function updateTask(id: number, input: TaskInput): Promise<Task> {
  return request<Task>(`/tasks/${id}`, {
    method: 'PATCH',
    headers: JSON_HEADERS,
    body: JSON.stringify(input),
  })
}

export function deleteTask(id: number): Promise<void> {
  return request<void>(`/tasks/${id}`, { method: 'DELETE' })
}
