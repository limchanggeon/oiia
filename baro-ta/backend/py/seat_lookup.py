#!/usr/bin/env python3
"""열차 좌석 상태 실시간 조회 → JSON(stdout).  [VER3 FR-6]

사용: python seat_lookup.py <KORAIL|SRT> <출발역> <도착역> <YYYYMMDD> <HHMMSS>
출력: [{"no": "KTX 101", "mode": "KTX", "depMin": 340, "arrMin": 495, "soldOut": false}, ...]

VER3 §2 시연 안전 규칙:
- **조회 함수만 호출한다.** reserve()/cancel() 등 예약 계열 함수는 이 파일 어디에도 없다.
- 코레일은 조회 시 로그인이 필요 없다. SRT는 로그인이 필요하므로 계정이 없으면
  즉시 실패(exit 1)하고, 호출 측이 UNKNOWN으로 처리한다 (매진으로 변환하지 않음).
- 실패는 숨기지 않는다 — exit 1 + stderr 한 줄. 조용한 폴백은 §5-1 위반이다.
"""
import json
import os
import sys

MODE_MAP = {  # 라이브러리 등급명 → 내부 mode (schedule.SOURCES와 일치해야 한다)
    "KTX": "KTX", "KTX-산천": "KTX", "KTX-이음": "KTX", "KTX-청룡": "KTX",
    "ITX-새마을": "ITX-새마을", "새마을호": "ITX-새마을", "ITX-마음": "ITX-새마을",
    "무궁화호": "무궁화호", "누리로": "무궁화호",
}


def _hhmm(t: str) -> int:
    return int(t[:2]) * 60 + int(t[2:4])


def lookup_korail(dep: str, arr: str, date: str, time: str):
    import re

    from korail2 import Korail, NoResultsError, TrainType

    korail = Korail("", "", auto_login=False)   # 조회는 로그인 불필요
    try:
        # search_train은 지정 시각 이후 소수(10편 내외)만 반환한다 —
        # 오후 도착 마감이어도 새벽 편만 잡히므로 하루 전체를 받는다.
        trains = korail.search_train_allday(
            dep, arr, date, time, train_type=TrainType.ALL, include_no_seats=True
        )
    except NoResultsError:
        return []

    out = []
    for t in trains:
        mode = MODE_MAP.get(t.train_type_name)
        if mode is None:
            continue                    # 알 수 없는 등급은 버린다 (임의 매핑 금지)
        # 요금: 예약 가능 문구에 "45,000원" 형태로 들어온다 (없으면 null → 호출 측이 판단)
        fare = None
        m = re.search(r"([\d,]+)원", getattr(t, "reserve_possible_name", "") or "")
        if m:
            fare = int(m.group(1).replace(",", ""))
        out.append({
            "mode": mode,
            "no": f"{mode} {t.train_no}",
            "depMin": _hhmm(t.dep_time),
            "arrMin": _hhmm(t.arr_time),
            "soldOut": not t.has_seat(),
            "fare": fare,
        })
    return out


def lookup_srt(dep: str, arr: str, date: str, time: str):
    from SRT import SRT

    sid, pw = os.environ.get("SRT_ID", ""), os.environ.get("SRT_PW", "")
    if not (sid and pw):
        raise RuntimeError("SRT_ID/SRT_PW 미설정 — SRT 좌석 조회는 로그인이 필요합니다")

    srt = SRT(sid, pw)                  # 로그인 (조회 목적)
    # available_only=False: 매진 편도 받아야 '매진'을 판정할 수 있다
    trains = srt.search_train(dep, arr, date, time, available_only=False)

    out = []
    for t in trains:
        out.append({
            "mode": "SRT",
            "no": f"SRT {t.train_number}",
            "depMin": _hhmm(t.dep_time),
            "arrMin": _hhmm(t.arr_time),
            "soldOut": not t.seat_available(),
            "fare": getattr(t, "general_seat_price", None) or None,
        })
    return out


def main():
    provider, dep, arr, date, time = sys.argv[1:6]
    if provider == "KORAIL":
        rows = lookup_korail(dep, arr, date, time)
    elif provider == "SRT":
        rows = lookup_srt(dep, arr, date, time)
    else:
        raise ValueError(f"알 수 없는 provider: {provider}")
    json.dump(rows, sys.stdout, ensure_ascii=False)


if __name__ == "__main__":
    try:
        main()
    except Exception as e:  # noqa: BLE001 — 어떤 실패든 UNKNOWN 신호로 축약
        print(f"{type(e).__name__}: {e}", file=sys.stderr)
        sys.exit(1)
