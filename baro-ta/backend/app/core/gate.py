"""read / side_effect 승인 게이트.

- read 액션(경로 조회 등)은 자동 통과.
- side_effect 액션(예매 생성·결제)은 사용자 승인 근거가 필요하다.
  데모 기본값(REQUIRE_APPROVAL=false)에서는 클라이언트 버튼 클릭을
  암묵적 승인으로 간주하고 감사 로그만 남긴다.
  REQUIRE_APPROVAL=true면 X-Approved-By 헤더가 없는 side_effect 요청을 거부한다.
모든 판정은 SQLite audit_log에 기록된다.
"""
from typing import Optional

from .. import db
from ..config import settings

READ = "read"
SIDE_EFFECT = "side_effect"


class ApprovalRequired(Exception):
    def __init__(self, action: str):
        self.action = action
        super().__init__(f"side_effect 액션 '{action}'에는 사용자 승인이 필요합니다 (X-Approved-By 헤더)")


def check(action: str, kind: str, session_id: Optional[str] = None, approved_by: Optional[str] = None) -> None:
    if kind == SIDE_EFFECT:
        if approved_by is None and settings.require_approval:
            db.audit(session_id, action, kind, approved=False, detail="승인 없음 → 거부")
            raise ApprovalRequired(action)
        db.audit(session_id, action, kind, approved=True, detail=approved_by or "implicit-user(버튼 클릭)")
    else:
        db.audit(session_id, action, kind, approved=True, detail="read 자동 통과")
