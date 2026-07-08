#!/usr/bin/env python3
"""코레일 실제 예약/취소 → JSON(stdout).

사용:
  python korail_booking.py reserve <출발역> <도착역> <YYYYMMDD> <열차번호> <HHMMSS>
  python korail_booking.py cancel <예약번호>

계정은 KORAIL_ID / KORAIL_PW 환경변수로 받는다.
예약은 결제 전 상태로만 생성한다(기한 내 미결제 시 코레일이 자동 취소).
결제는 항상 사용자가 코레일톡/웹에서 직접 — 서비스 원칙과 동일.
"""
import json
import os
import sys

from korail2 import Korail, TrainType


def public_attrs(obj):
    out = {}
    for a in dir(obj):
        if a.startswith("_"):
            continue
        v = getattr(obj, a)
        if not callable(v):
            out[a] = str(v)
    return out


def main():
    mode = sys.argv[1]
    korail = Korail(os.environ["KORAIL_ID"], os.environ["KORAIL_PW"], want_feedback=False)

    if mode == "reserve":
        dep, arr, date, train_no, time = sys.argv[2:7]
        trains = korail.search_train(dep, arr, date, time, train_type=TrainType.ALL)
        target = next((t for t in trains if t.train_no.lstrip("0") == train_no.lstrip("0")), None)
        if target is None:
            raise RuntimeError(f"{date} {time} 이후에서 열차 {train_no}를 찾지 못함")
        rsv = korail.reserve(target)
        json.dump({"ok": True, "reservation": public_attrs(rsv)}, sys.stdout, ensure_ascii=False)

    elif mode == "cancel":
        rsv_id = sys.argv[2]
        rsv = next((r for r in korail.reservations() if str(r.rsv_id) == rsv_id), None)
        if rsv is None:
            raise RuntimeError(f"예약 {rsv_id} 없음 (이미 취소되었을 수 있음)")
        korail.cancel(rsv)
        json.dump({"ok": True, "cancelled": rsv_id}, sys.stdout, ensure_ascii=False)

    else:
        raise RuntimeError(f"알 수 없는 모드: {mode}")


if __name__ == "__main__":
    try:
        main()
    except Exception as e:  # noqa: BLE001 — 어떤 실패든 호출부 폴백 신호로 축약
        print(f"{type(e).__name__}: {e}", file=sys.stderr)
        sys.exit(1)
