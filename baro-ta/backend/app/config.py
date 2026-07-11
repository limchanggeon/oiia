"""환경 설정 — 모든 협업 지점은 환경변수로 스위칭한다 (.env.example 참고)."""
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import List

from dotenv import load_dotenv

# backend/.env 로드 (없으면 조용히 넘어간다)
load_dotenv(Path(__file__).resolve().parent.parent / ".env")


def _bool(name: str, default: bool = False) -> bool:
    return os.environ.get(name, str(default)).strip().lower() in ("1", "true", "yes")


@dataclass
class Settings:
    # LLM 판단 엔진: rule(기본) | anthropic(상용 API) | ollama(로컬)
    llm_provider: str = os.environ.get("LLM_PROVIDER", "rule")
    # 팀 결정(2026-07-11): 슬롯 추출·되묻기·설명문은 Haiku로 충분 → 기본 claude-haiku-4-5
    llm_model: str = os.environ.get("LLM_MODEL", "claude-haiku-4-5")
    ollama_base_url: str = os.environ.get("OLLAMA_BASE_URL", "http://localhost:11434")

    # 도구 어댑터: live | cache | mock (3단 폴백: live → cache → mock)
    tool_mode: str = os.environ.get("TOOL_MODE", "mock")
    kskill_bin: str = os.environ.get("KSKILL_BIN", "k-skill")

    # SQLite (WAL)
    db_path: str = os.environ.get("BAROTA_DB", str(Path(__file__).resolve().parent.parent / "barota.db"))

    # 승인 게이트: true면 side_effect 액션에 X-Approved-By 헤더 필수
    require_approval: bool = field(default_factory=lambda: _bool("REQUIRE_APPROVAL", False))

    cors_origins: List[str] = field(
        default_factory=lambda: [o.strip() for o in os.environ.get("CORS_ORIGINS", "*").split(",")]
    )


settings = Settings()
