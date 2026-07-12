"""SQLite (WAL) 저장소 — 세션·잔여석·예매·도구캐시·감사로그 + TTL.

플로우차트의 "SQLite (WAL) + in-mem dict / 세션·잔여석·TTL" 담당.
데모 규모에 맞춘 단일 커넥션 + Lock 구조이며, 함수 시그니처만 유지하면
Postgres 등으로 교체 가능하다.
"""
import json
import random
import sqlite3
import threading
import time
from typing import Any, Dict, Optional, Tuple

from .config import settings

_lock = threading.Lock()
_conn: Optional[sqlite3.Connection] = None

STANDBY_TTL = 600      # 취소표 조회 세션 유지 시간(초)
CACHE_TTL_DEFAULT = 60  # LIVE 조회 결과 hold 시간(초) — 플로우차트 "60초 hold"


def init_db() -> None:
    global _conn
    _conn = sqlite3.connect(settings.db_path, check_same_thread=False)
    _conn.execute("PRAGMA journal_mode=WAL")
    _conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS standby_sessions(
            id TEXT PRIMARY KEY,
            attempts INTEGER NOT NULL DEFAULT 0,
            target INTEGER NOT NULL,
            expires_at REAL NOT NULL
        );
        CREATE TABLE IF NOT EXISTS bookings(
            id TEXT PRIMARY KEY,
            route_json TEXT NOT NULL,
            params_json TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'pending',
            created_at REAL NOT NULL
        );
        CREATE TABLE IF NOT EXISTS tool_cache(
            key TEXT PRIMARY KEY,
            payload TEXT NOT NULL,
            expires_at REAL NOT NULL
        );
        CREATE TABLE IF NOT EXISTS audit_log(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            ts REAL NOT NULL,
            session_id TEXT,
            action TEXT NOT NULL,
            kind TEXT NOT NULL,
            approved INTEGER NOT NULL,
            detail TEXT
        );
        CREATE TABLE IF NOT EXISTS dialog_sessions(
            id TEXT PRIMARY KEY,
            slots_json TEXT NOT NULL,
            ask_count INTEGER NOT NULL DEFAULT 0,
            last_target_slot TEXT,
            updated_at REAL NOT NULL
        );
        -- ── VER3 ────────────────────────────────────────
        CREATE TABLE IF NOT EXISTS trip_inputs(
            session_id TEXT PRIMARY KEY,
            input_json TEXT NOT NULL,      -- TripInput (5단계 입력값)
            updated_at REAL NOT NULL
        );
        CREATE TABLE IF NOT EXISTS sim_reservations(
            demo_id TEXT PRIMARY KEY,      -- DEMO-XXXXXX (사업자 예약번호 아님)
            session_id TEXT,
            journey_json TEXT NOT NULL,
            seats_json TEXT NOT NULL,
            passengers_json TEXT NOT NULL,
            fare_json TEXT NOT NULL,
            date_iso TEXT,
            status TEXT NOT NULL,          -- SIM_* / MOCK_PAYMENT_OPENED / DEMO_COMPLETED
            deadline REAL,
            created_at REAL NOT NULL
        );
        CREATE TABLE IF NOT EXISTS demo_notifications(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            demo_id TEXT NOT NULL,
            session_id TEXT,
            at_iso TEXT NOT NULL,
            label TEXT NOT NULL,
            subject TEXT NOT NULL,
            body TEXT NOT NULL,
            sent INTEGER NOT NULL DEFAULT 0,
            created_at REAL NOT NULL
        );

        CREATE TABLE IF NOT EXISTS holds(
            id TEXT PRIMARY KEY,
            session_id TEXT,
            journey_json TEXT NOT NULL,
            passengers INTEGER NOT NULL,
            reserve_no TEXT,
            fare INTEGER NOT NULL,
            deadline REAL,
            status TEXT NOT NULL,
            date_iso TEXT,
            created_at REAL NOT NULL
        );
        """
    )
    _conn.commit()


def _c() -> sqlite3.Connection:
    assert _conn is not None, "init_db()가 호출되지 않았습니다"
    return _conn


# ── 취소표 조회 세션 ──────────────────────────────
def standby_check(search_id: str) -> Tuple[int, bool]:
    """조회 1회 기록. (attempt, available) 반환.

    시연 시나리오: 4~6회째 조회에서 취소표 발견.
    [실연동 교체 지점] 실제 서비스에서는 attempts/target 대신
    예매처 좌석 조회 결과로 available을 판정한다.
    """
    now = time.time()
    with _lock:
        c = _c()
        row = c.execute(
            "SELECT attempts, target, expires_at FROM standby_sessions WHERE id=?", (search_id,)
        ).fetchone()
        if row is None or row[2] < now:
            target = random.randint(4, 6)
            c.execute(
                "INSERT OR REPLACE INTO standby_sessions(id, attempts, target, expires_at) VALUES(?,?,?,?)",
                (search_id, 0, target, now + STANDBY_TTL),
            )
            attempts = 0
        else:
            attempts, target = row[0], row[1]
        attempts += 1
        available = attempts >= target
        if available:
            c.execute("DELETE FROM standby_sessions WHERE id=?", (search_id,))
        else:
            c.execute("UPDATE standby_sessions SET attempts=? WHERE id=?", (attempts, search_id))
        c.commit()
    return attempts, available


# ── 예매 ─────────────────────────────────────────
def booking_create(booking_id: str, route: Dict[str, Any], params: Dict[str, Any]) -> None:
    with _lock:
        _c().execute(
            "INSERT INTO bookings(id, route_json, params_json, status, created_at) VALUES(?,?,?,?,?)",
            (booking_id, json.dumps(route, ensure_ascii=False), json.dumps(params, ensure_ascii=False), "pending", time.time()),
        )
        _c().commit()


def booking_get(booking_id: str) -> Optional[Dict[str, Any]]:
    row = _c().execute(
        "SELECT route_json, params_json, status FROM bookings WHERE id=?", (booking_id,)
    ).fetchone()
    if row is None:
        return None
    return {"route": json.loads(row[0]), "params": json.loads(row[1]), "status": row[2]}


def booking_mark_paid(booking_id: str) -> None:
    with _lock:
        _c().execute("UPDATE bookings SET status='paid' WHERE id=?", (booking_id,))
        _c().commit()


# ── 도구 캐시 (LIVE 결과 60초 hold) ────────────────
def cache_get(key: str) -> Optional[Any]:
    row = _c().execute("SELECT payload, expires_at FROM tool_cache WHERE key=?", (key,)).fetchone()
    if row is None or row[1] < time.time():
        return None
    return json.loads(row[0])


def cache_set(key: str, payload: Any, ttl: int = CACHE_TTL_DEFAULT) -> None:
    with _lock:
        _c().execute(
            "INSERT OR REPLACE INTO tool_cache(key, payload, expires_at) VALUES(?,?,?)",
            (key, json.dumps(payload, ensure_ascii=False), time.time() + ttl),
        )
        _c().commit()


# ── 대화 세션 (FR-2/3 슬롯 상태·되묻기 카운트) ──────
def dialog_get(session_id: str) -> Tuple[Dict[str, Any], int, Optional[str]]:
    row = _c().execute(
        "SELECT slots_json, ask_count, last_target_slot FROM dialog_sessions WHERE id=?", (session_id,)
    ).fetchone()
    if row is None:
        return {}, 0, None
    return json.loads(row[0]), row[1], row[2]


def dialog_save(session_id: str, slots: Dict[str, Any], ask_count: int, last_target_slot: Optional[str]) -> None:
    with _lock:
        _c().execute(
            "INSERT OR REPLACE INTO dialog_sessions(id, slots_json, ask_count, last_target_slot, updated_at) "
            "VALUES(?,?,?,?,?)",
            (session_id, json.dumps(slots, ensure_ascii=False), ask_count, last_target_slot, time.time()),
        )
        _c().commit()


def dialog_reset(session_id: str) -> None:
    with _lock:
        _c().execute("DELETE FROM dialog_sessions WHERE id=?", (session_id,))
        _c().commit()


# ── 좌석 선점 (FR-10/15) ──────────────────────────
def hold_create(
    hold_id: str,
    session_id: Optional[str],
    journey: Dict[str, Any],
    passengers: int,
    reserve_no: Optional[str],
    fare: int,
    deadline: Optional[float],
    date_iso: Optional[str] = None,
) -> None:
    with _lock:
        _c().execute(
            "INSERT INTO holds(id, session_id, journey_json, passengers, reserve_no, fare, deadline, status, date_iso, created_at) "
            "VALUES(?,?,?,?,?,?,?,?,?,?)",
            (hold_id, session_id or "public", json.dumps(journey, ensure_ascii=False),
             passengers, reserve_no, fare, deadline, "held", date_iso, time.time()),
        )
        _c().commit()


def _hold_row_to_dict(row) -> Dict[str, Any]:
    status = row[7]
    deadline = row[6]
    # 기한 경과 시 자동 만료 (lazy) — FR-10 "자동으로 취소"
    if status == "held" and deadline is not None and deadline < time.time():
        status = "expired"
    return {
        "id": row[0], "session_id": row[1], "journey": json.loads(row[2]),
        "passengers": row[3], "reserve_no": row[4], "fare": row[5],
        "deadline": deadline, "status": status, "date_iso": row[8],
    }


_HOLD_COLS = "id, session_id, journey_json, passengers, reserve_no, fare, deadline, status, date_iso"


def hold_get(hold_id: str) -> Optional[Dict[str, Any]]:
    row = _c().execute(f"SELECT {_HOLD_COLS} FROM holds WHERE id=?", (hold_id,)).fetchone()
    return _hold_row_to_dict(row) if row else None


def hold_list(session_id: Optional[str] = None) -> list:
    if session_id:
        rows = _c().execute(
            f"SELECT {_HOLD_COLS} FROM holds WHERE session_id=? ORDER BY created_at DESC", (session_id,)
        ).fetchall()
    else:
        rows = _c().execute(f"SELECT {_HOLD_COLS} FROM holds ORDER BY created_at DESC").fetchall()
    return [_hold_row_to_dict(r) for r in rows]


def hold_set_status(hold_id: str, status: str) -> None:
    with _lock:
        _c().execute("UPDATE holds SET status=? WHERE id=?", (status, hold_id))
        _c().commit()


# ── VER3: 단계형 입력 세션 (FR-1/2/3) ──────────────
def input_get(session_id: str) -> Dict[str, Any]:
    row = _c().execute("SELECT input_json FROM trip_inputs WHERE session_id=?", (session_id,)).fetchone()
    return json.loads(row[0]) if row else {}


def input_save(session_id: str, data: Dict[str, Any]) -> None:
    with _lock:
        _c().execute(
            "INSERT OR REPLACE INTO trip_inputs(session_id, input_json, updated_at) VALUES(?,?,?)",
            (session_id, json.dumps(data, ensure_ascii=False), time.time()),
        )
        _c().commit()


# ── VER3: 시뮬레이션 예약 (FR-9/11) ─────────────────
def sim_create(demo_id: str, session_id: Optional[str], journey: Dict[str, Any], seats: Any,
               passengers: Dict[str, Any], fare: Dict[str, Any], date_iso: Optional[str],
               status: str, deadline: Optional[float]) -> None:
    with _lock:
        _c().execute(
            "INSERT INTO sim_reservations(demo_id, session_id, journey_json, seats_json, passengers_json,"
            " fare_json, date_iso, status, deadline, created_at) VALUES(?,?,?,?,?,?,?,?,?,?)",
            (demo_id, session_id or "public", json.dumps(journey, ensure_ascii=False),
             json.dumps(seats, ensure_ascii=False), json.dumps(passengers, ensure_ascii=False),
             json.dumps(fare, ensure_ascii=False), date_iso, status, deadline, time.time()),
        )
        _c().commit()


_SIM_COLS = ("demo_id, session_id, journey_json, seats_json, passengers_json, fare_json,"
             " date_iso, status, deadline")


def _sim_row(row) -> Dict[str, Any]:
    status, deadline = row[7], row[8]
    # 기한 경과 시 자동 만료 (FR-9 SIM_EXPIRED) — lazy 판정
    if status in ("SIM_HELD", "MOCK_PAYMENT_OPENED") and deadline and deadline < time.time():
        status = "SIM_EXPIRED"
    return {
        "demoId": row[0], "sessionId": row[1], "journey": json.loads(row[2]),
        "seats": json.loads(row[3]), "passengers": json.loads(row[4]), "fare": json.loads(row[5]),
        "dateIso": row[6], "status": status, "deadline": deadline,
    }


def sim_get(demo_id: str) -> Optional[Dict[str, Any]]:
    row = _c().execute(f"SELECT {_SIM_COLS} FROM sim_reservations WHERE demo_id=?", (demo_id,)).fetchone()
    return _sim_row(row) if row else None


def sim_list(session_id: Optional[str] = None) -> list:
    if session_id:
        rows = _c().execute(
            f"SELECT {_SIM_COLS} FROM sim_reservations WHERE session_id=? ORDER BY created_at DESC",
            (session_id,),
        ).fetchall()
    else:
        rows = _c().execute(f"SELECT {_SIM_COLS} FROM sim_reservations ORDER BY created_at DESC").fetchall()
    return [_sim_row(r) for r in rows]


def sim_set_status(demo_id: str, status: str) -> None:
    with _lock:
        _c().execute("UPDATE sim_reservations SET status=? WHERE demo_id=?", (status, demo_id))
        _c().commit()


# ── VER3: 데모 알림 큐 (FR-10) ─────────────────────
def notify_add(demo_id: str, session_id: Optional[str], reminders: list) -> None:
    with _lock:
        for r in reminders:
            _c().execute(
                "INSERT INTO demo_notifications(demo_id, session_id, at_iso, label, subject, body, sent, created_at)"
                " VALUES(?,?,?,?,?,?,0,?)",
                (demo_id, session_id or "public", r["atIso"], r["label"], r["subject"], r["body"], time.time()),
            )
        _c().commit()


def notify_list(demo_id: str) -> list:
    rows = _c().execute(
        "SELECT id, at_iso, label, subject, body, sent FROM demo_notifications WHERE demo_id=? ORDER BY at_iso",
        (demo_id,),
    ).fetchall()
    return [{"id": r[0], "atIso": r[1], "label": r[2], "subject": r[3], "body": r[4], "sent": bool(r[5])}
            for r in rows]


def notify_mark_sent(notif_id: int) -> None:
    with _lock:
        _c().execute("UPDATE demo_notifications SET sent=1 WHERE id=?", (notif_id,))
        _c().commit()


def demo_reset(session_id: str) -> None:
    """[데모 초기화] — 입력값·시뮬레이션 예약·서버 알림 예약을 한 번에 삭제 (§5-7)."""
    with _lock:
        c = _c()
        c.execute("DELETE FROM trip_inputs WHERE session_id=?", (session_id,))
        c.execute("DELETE FROM sim_reservations WHERE session_id=?", (session_id,))
        c.execute("DELETE FROM demo_notifications WHERE session_id=?", (session_id,))
        c.execute("DELETE FROM dialog_sessions WHERE id=?", (session_id,))
        c.commit()


# ── 감사 로그 (승인 게이트) ────────────────────────
def audit(session_id: Optional[str], action: str, kind: str, approved: bool, detail: str = "") -> None:
    with _lock:
        _c().execute(
            "INSERT INTO audit_log(ts, session_id, action, kind, approved, detail) VALUES(?,?,?,?,?,?)",
            (time.time(), session_id or "public", action, kind, 1 if approved else 0, detail),
        )
        _c().commit()
