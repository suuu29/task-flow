import { COLUMNS, type Status, type Task, type TaskInput } from '../types'
import TaskCard from './TaskCard'

interface Props {
  tasks: Task[]
  onChangeStatus: (id: number, status: Status) => Promise<void>
  onUpdate: (id: number, input: TaskInput) => Promise<void>
  onDelete: (id: number) => Promise<void>
}

export default function Board({ tasks, ...handlers }: Props) {
  return (
    <div className="board">
      {COLUMNS.map((col) => (
        <section key={col.status} className="column">
          <h2>{col.label}</h2>
          <ul>
            {tasks
              .filter((t) => t.status === col.status)
              .map((t) => (
                <TaskCard key={t.id} task={t} {...handlers} />
              ))}
          </ul>
        </section>
      ))}
    </div>
  )
}
