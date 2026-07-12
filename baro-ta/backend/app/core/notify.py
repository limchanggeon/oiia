"""탑승 안내 이메일 알림 (FR-10).

- 사용자 로그인·이메일 입력 없음 — 서버에 미리 등록된 데모 주소(DEMO_EMAIL_TO)로만 전송.
- 알림 시각: 출발 전날 오후 6시 · 출발 2시간 전 (KST). 이미 2시간 이내면 즉시 1회.
- 제목·본문에 "경진대회 시연용 알림"을 명시하고, 실제 승차권으로 오인될 표현을 쓰지 않는다.
- 마지막 알림 전송 후 알림 데이터는 삭제한다 (§FR-10) — db.notify_cleanup 이 수행.
"""
import datetime as dt
import smtplib
from email.message import EmailMessage
from typing import Any, Dict, List, Optional, Tuple

from ..config import settings

KST = dt.timezone(dt.timedelta(hours=9))
SUBJECT_PREFIX = "[경진대회 시연용 알림]"


def _fmt(minutes: int) -> str:
    m = minutes % 1440
    return f"{m // 60}시 {m % 60:02d}분"


def build_reminders(journey: Dict[str, Any], date_iso: str, now: Optional[dt.datetime] = None) -> List[Dict[str, Any]]:
    """알림 계획 생성 — 전날 18시 · 출발 2시간 전. 이미 임박하면 즉시 1회."""
    now = now or dt.datetime.now(KST)
    d = dt.date.fromisoformat(date_iso)
    dep_min = journey["dep"]
    departure = dt.datetime.combine(d, dt.time(dep_min // 60 % 24, dep_min % 60), tzinfo=KST)

    origin = journey["legs"][0].get("fromName") or journey["legs"][0]["from"]
    dest = journey["legs"][-1].get("toName") or journey["legs"][-1]["to"]
    transfer = ""
    if journey["transfers"] > 0:
        transfer = f"\n환승: {journey['transferAt']}에서 {journey['transferWaitMin']}분 대기"

    body_core = (
        f"여정: {origin} → {dest}\n"
        f"출발: {date_iso} {_fmt(journey['dep'])}\n"
        f"도착: {_fmt(journey['arr'])}{transfer}\n\n"
        "※ 본 메일은 2026 디지털 경진대회 시연용 알림입니다.\n"
        "※ 실제 승차권이 아니며, 실제 예약·결제가 이루어지지 않았습니다."
    )

    plans: List[Tuple[dt.datetime, str]] = [
        (dt.datetime.combine(d - dt.timedelta(days=1), dt.time(18, 0), tzinfo=KST), "출발 전날 오후 6시"),
        (departure - dt.timedelta(hours=2), "출발 2시간 전"),
    ]
    future = [(at, label) for at, label in plans if at > now]
    if not future:
        # 이미 출발 2시간 이내 → 즉시 1회 (FR-10)
        future = [(now, "즉시 (출발 임박)")]

    return [
        {
            "atIso": at.isoformat(),
            "label": label,
            "subject": f"{SUBJECT_PREFIX} {origin} → {dest} 탑승 안내 ({label})",
            "body": body_core,
            "sent": False,
        }
        for at, label in future
    ]


def mask(addr: str) -> str:
    if "@" not in addr:
        return "(미설정)"
    name, host = addr.split("@", 1)
    keep = name[:2] if len(name) > 2 else name[:1]
    return f"{keep}{'*' * max(1, len(name) - len(keep))}@{host}"


def send(subject: str, body: str) -> Dict[str, Any]:
    """데모 이메일 발송. SMTP 미설정이면 전송하지 않고 내용만 반환한다(시연 계속 가능)."""
    to = settings.demo_email_to
    if not (to and settings.smtp_host and settings.smtp_user):
        return {
            "sent": False,
            "to": mask(to) if to else "(미설정)",
            "error": "SMTP 미설정 — .env의 DEMO_EMAIL_TO / SMTP_* 를 채우면 실제 전송됩니다.",
        }

    msg = EmailMessage()
    msg["Subject"] = subject
    msg["From"] = settings.smtp_user
    msg["To"] = to
    msg.set_content(body)
    try:
        with smtplib.SMTP(settings.smtp_host, settings.smtp_port, timeout=10) as s:
            s.starttls()
            s.login(settings.smtp_user, settings.smtp_pass)
            s.send_message(msg)
        return {"sent": True, "to": mask(to), "error": None}
    except Exception as e:
        return {"sent": False, "to": mask(to), "error": f"{type(e).__name__}: {e}"}
