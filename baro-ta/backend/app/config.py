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

    # 외부 API 키 (운행정보·요금 — TAGO/ODsay)
    tago_api_key: str = os.environ.get("TAGO_API_KEY", "")
    odsay_api_key: str = os.environ.get("ODSAY_API_KEY", "")

    # 열차 좌석 **조회 전용** 계정 (VER3 §2: 예약 함수 호출 금지, 로그·클라이언트 노출 금지)
    korail_id: str = os.environ.get("KORAIL_ID", "")
    korail_pw: str = os.environ.get("KORAIL_PW", "")
    srt_id: str = os.environ.get("SRT_ID", "")
    srt_pw: str = os.environ.get("SRT_PW", "")

    # 데모 이메일 알림 (FR-10) — 사용자 이메일 입력 없음, 서버에 미리 등록된 주소로만 전송
    demo_email_to: str = os.environ.get("DEMO_EMAIL_TO", "")
    smtp_host: str = os.environ.get("SMTP_HOST", "")
    smtp_port: int = int(os.environ.get("SMTP_PORT", "587"))
    smtp_user: str = os.environ.get("SMTP_USER", "")
    smtp_pass: str = os.environ.get("SMTP_PASS", "")

    # SQLite (WAL)
    db_path: str = os.environ.get("BAROTA_DB", str(Path(__file__).resolve().parent.parent / "barota.db"))

    # 승인 게이트: true면 side_effect 액션에 X-Approved-By 헤더 필수
    require_approval: bool = field(default_factory=lambda: _bool("REQUIRE_APPROVAL", False))

    cors_origins: List[str] = field(
        default_factory=lambda: [o.strip() for o in os.environ.get("CORS_ORIGINS", "*").split(",")]
    )


settings = Settings()
