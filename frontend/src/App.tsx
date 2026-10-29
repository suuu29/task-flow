import { useEffect, useRef, useState } from 'react'
import {
  ApiError,
  changeStatus,
  deleteTask,
  getMe,
  listTasks,
  logout,
  setUnauthorizedHandler,
  updateTask,
} from './api'
import AuthForm from './components/AuthForm'
import Board from './components/Board'
import TaskForm from './components/TaskForm'
import type { Status, Task, TaskInput, User } from './types'

type Load = { state: 'loading' } | { state: 'error'; message: string } | { state: 'ready'; tasks: Task[] }
type Auth =
  | { state: 'checking' }
  | { state: 'error'; message: string }
  | { state: 'anonymous'; notice?: string }
  | { state: 'authed'; user: User }

function App() {
  const [auth, setAuth] = useState<Auth>({ state: 'checking' })
  const [load, setLoad] = useState<Load>({ state: 'loading' })
  const [logoutError, setLogoutError] = useState<string | null>(null)

  // 앱을 열면 로그인 상태부터 확인한다. 401만 로그인 안 됨이고, 연결 실패 등은 오류로 알린다.
  useEffect(() => {
    getMe()
      .then((user) => setAuth({ state: 'authed', user }))
      .catch((err) => {
        if (err instanceof ApiError && err.status === 401) setAuth({ state: 'anonymous' })
        else setAuth({ state: 'error', message: err instanceof Error ? err.message : '로그인 상태를 확인하지 못했습니다.' })
      })
  }, [])

  // 로그인 화면으로 돌린다. 이전 사용자의 목록은 비운다.
  function goAnonymous(notice?: string) {
    setLoad({ state: 'loading' })
    setAuth({ state: 'anonymous', notice })
  }

  // Task API가 401이면(세션 만료 등) 로그인 화면으로 돌린다.
  useEffect(() => {
    setUnauthorizedHandler(() => goAnonymous('로그인이 끝났습니다. 다시 로그인하세요.'))
    return () => setUnauthorizedHandler(null)
  }, [])

  const userId = auth.state === 'authed' ? auth.user.id : null

  // 로그인한 뒤에만 목록을 불러온다. 사용자가 바뀌면 이전 응답은 버린다.
  useEffect(() => {
    if (userId === null) return
    let cancelled = false
    listTasks()
      .then((tasks) => {
        if (!cancelled) setLoad({ state: 'ready', tasks })
      })
      .catch(() => {
        if (!cancelled) setLoad({ state: 'error', message: '카드를 불러오지 못했습니다.' })
      })
    return () => {
      cancelled = true
    }
  }, [userId])

  // 수정·삭제는 API가 성공으로 응답한 뒤에만 목록에 반영한다. (D-004)
  // 상태 변경은 응답을 기다리지 않고 먼저 반영한다. (연습용으로 D-004와 다르게 둠)
  function withTasks(fn: (tasks: Task[]) => Task[]) {
    setLoad((prev) => (prev.state === 'ready' ? { state: 'ready', tasks: fn(prev.tasks) } : prev))
  }

  // 서버가 정렬하고 기한 초과를 계산하므로, 등록·수정·상태 변경이 성공하면 목록을 다시 불러와 맞춘다.
  // 다시 불러오지 못하면 지금 화면 상태를 그대로 둔다. 로그아웃·사용자 변경 뒤나 더 새로운 요청이 있으면 응답을 버린다.
  const userIdRef = useRef<number | null>(null)
  useEffect(() => {
    userIdRef.current = userId
  }, [userId])
  const refreshSeq = useRef(0)

  function refreshTasks() {
    const requestedFor = userIdRef.current
    const seq = ++refreshSeq.current
    listTasks()
      .then((tasks) => {
        if (userIdRef.current !== requestedFor || refreshSeq.current !== seq) return
        withTasks(() => tasks)
      })
      .catch(() => {
        // 화면 상태를 유지한다.
      })
  }

  async function handleChangeStatus(id: number, status: Status) {
    withTasks((tasks) => tasks.map((t) => (t.id === id ? { ...t, status } : t)))
    await changeStatus(id, status)
    refreshTasks()
  }

  async function handleUpdate(id: number, input: TaskInput) {
    const saved = await updateTask(id, input)
    withTasks((tasks) => tasks.map((t) => (t.id === id ? saved : t)))
    refreshTasks()
  }

  async function handleDelete(id: number) {
    await deleteTask(id)
    withTasks((tasks) => tasks.filter((t) => t.id !== id))
  }

  async function handleLogout() {
    setLogoutError(null)
    try {
      await logout()
    } catch (err) {
      // 이미 로그인 안 됨(401)이면 로그아웃된 것과 같다. 그 밖의 실패는 로그인 상태를 유지하고 알린다.
      if (!(err instanceof ApiError && err.status === 401)) {
        setLogoutError(err instanceof Error ? err.message : '로그아웃하지 못했습니다.')
        return
      }
    }
    goAnonymous()
  }

  return (
    <main>
      <header className="app-header">
        <h1>task-flow</h1>
        {auth.state === 'authed' && (
          <div className="user-box">
            <span>{auth.user.username}</span>
            <button type="button" onClick={handleLogout}>
              로그아웃
            </button>
          </div>
        )}
      </header>
      {logoutError && <p role="alert">{logoutError}</p>}
      {auth.state === 'checking' && <p>불러오는 중...</p>}
      {auth.state === 'error' && <p role="alert">{auth.message}</p>}
      {auth.state === 'anonymous' && (
        <AuthForm notice={auth.notice} onLoggedIn={(user) => setAuth({ state: 'authed', user })} />
      )}
      {auth.state === 'authed' && (
        <>
          {load.state === 'loading' && <p>불러오는 중...</p>}
          {/* 불러오지 못했을 때는 빈 보드처럼 보여 주지 않는다. */}
          {load.state === 'error' && <p role="alert">{load.message}</p>}
          {load.state === 'ready' && (
            <>
              <TaskForm
                onCreated={(task) => {
                  withTasks((tasks) => [...tasks, task])
                  refreshTasks()
                }}
              />
              <Board
                tasks={load.tasks}
                onChangeStatus={handleChangeStatus}
                onUpdate={handleUpdate}
                onDelete={handleDelete}
              />
            </>
          )}
        </>
      )}
    </main>
  )
}

export default App
