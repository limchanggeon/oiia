"""바로타 FastAPI 오케스트레이터 — 진입점.

실행:  uvicorn app.main:app --reload --port 8000
문서:  http://localhost:8000/docs (OpenAPI — 팀 간 계약 명세)
데모:  http://localhost:8000/app  (시니어 UI 레퍼런스 클라이언트)
"""
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from . import db
from .api import router
from .api_v2 import router as router_v2
from .config import settings


@asynccontextmanager
async def lifespan(app: FastAPI):
    db.init_db()
    yield


app = FastAPI(
    title="바로타 API",
    description="AI Agent 기반 길찾기&예매 원스톱 서비스 — FastAPI 오케스트레이터 (팀 oiia)",
    version="0.1.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(router, prefix="/api")          # 데모 계약 (기존 React 클라이언트)
app.include_router(router_v2, prefix="/api/v2")    # 기능 명세서 계약 (FR-2~FR-15)

# 시니어 UI 레퍼런스 클라이언트 (기능 명세서 프론트 — Next.js 본 구현의 참고용)
app.mount("/app", StaticFiles(directory=str(Path(__file__).resolve().parent.parent / "static"), html=True), name="app")


@app.get("/health")
async def health() -> dict:
    return {
        "ok": True,
        "service": "baro-ta-api(fastapi)",
        "llm_provider": settings.llm_provider,
        "tool_mode": settings.tool_mode,
    }
