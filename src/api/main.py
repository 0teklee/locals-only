"""
FastAPI 서버 — OpenAI 호환 API + 관측 엔드포인트.

CLI-First 원칙에 따라 이 서버는 선택적.
에디터 연동(Cline, Continue 등) 또는 LAN 접근 시 사용.

실행:
  uvicorn src.api.main:app --reload --port 8080
"""
from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from src.api.state import AppState
from src.api.routes import chat, models, observe, health


@asynccontextmanager
async def lifespan(app: FastAPI):
    """앱 시작/종료 시 ModelPool 초기화/정리."""
    await AppState.get().pool.initialize()
    yield
    # 정리 로직 (필요 시 추가)


app = FastAPI(
    title="Local AI Agent",
    description="White-Box Local LLM Agent — Offline, OpenAI-Compatible",
    version="0.1.0",
    lifespan=lifespan,
)

# LAN 접근을 위해 CORS 허용 (로컬 전용이므로 전체 허용)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(chat.router)
app.include_router(models.router)
app.include_router(observe.router)
app.include_router(health.router)
