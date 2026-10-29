from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.auth import router as auth_router
from app.breakdown import router as breakdown_router
from app.config import get_session_secret
from app.db import init_db
from app.suggest import router as suggest_router
from app.tasks import router as tasks_router


@asynccontextmanager
async def lifespan(_: FastAPI):
    get_session_secret()  # 비어 있으면 시작하지 않는다.
    init_db()
    yield


app = FastAPI(title="task-flow API", lifespan=lifespan)

# 로컬 개발 서버(Vite) 주소만 허용한다.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_credentials=True,  # 세션 쿠키를 주고받는다. (D-022)
    allow_methods=["*"],
    allow_headers=["*"],
)


app.include_router(auth_router)
app.include_router(suggest_router)  # /tasks/{task_id} 보다 먼저 등록한다.
app.include_router(breakdown_router)
app.include_router(tasks_router)


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}
