#!/usr/bin/env python3
"""코레일 실시간 열차 조회 → JSON(stdout).

사용: python korail_search.py <출발역> <도착역> <YYYYMMDD> <HHMMSS>
korail2-ncard 사용, 조회는 로그인 불필요. 실패 시 exit 1 + stderr 한 줄.
비즈니스 로직(도착시각 필터·스코어링)은 Node 쪽(services/routes.js)이 담당한다.
"""
import json
import re
import sys

from korail2 import Korail, NoResultsError, TrainType


def main():
    dep, arr, date, time = sys.argv[1:5]
    korail = Korail("", "", auto_login=False)
    try:
        trains = korail.search_train(
            dep, arr, date, time, train_type=TrainType.ALL, include_no_seats=True
        )
    except NoResultsError:
        trains = []

    out = []
    for t in trains:
        price = None
        m = re.search(r"([\d,]+)원", t.reserve_possible_name or "")
        if m:
            price = int(m.group(1).replace(",", ""))
        out.append(
            {
                "mode": t.train_type_name,
                "no": f"{t.train_type_name} {t.train_no}",
                "depMin": int(t.dep_time[:2]) * 60 + int(t.dep_time[2:4]),
                "arrMin": int(t.arr_time[:2]) * 60 + int(t.arr_time[2:4]),
                "depDate": t.dep_date,
                "arrDate": t.arr_date,
                "soldOut": not t.has_seat(),
                "price": price,
            }
        )
    json.dump(out, sys.stdout, ensure_ascii=False)


if __name__ == "__main__":
    try:
        main()
    except Exception as e:  # noqa: BLE001 — 어떤 실패든 폴백 신호로 축약
        print(f"{type(e).__name__}: {e}", file=sys.stderr)
        sys.exit(1)
