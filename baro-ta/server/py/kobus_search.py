#!/usr/bin/env python3
"""KOBUS 고속버스 시간표 조회 → JSON(stdout).

사용: python kobus_search.py <출발터미널코드> <도착터미널코드> <YYYYMMDD>
공식 KOBUS HTTP 플로우(kobus.co.kr /mrs/alcnSrch.do) 조회 전용 — 예매·선점 없음.
k-skill express-bus-booking 헬퍼(MIT)의 검색 파트를 검토 후 조회 전용으로 재작성했다.
실패 시 exit 1 + stderr 한 줄.
"""
from __future__ import annotations

import html
import http.cookiejar
import json
import re
import ssl
import sys
import urllib.parse
import urllib.request

BASE_URL = "https://www.kobus.co.kr"
UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 Chrome/125 Safari/537.36"
FN_SATS_RE = re.compile(r"fnSatsChc\((.*?)\)", re.DOTALL)
ARG_RE = re.compile(r"'([^']*)'")
TAG_RE = re.compile(r"<[^>]+>")


def opener():
    jar = http.cookiejar.CookieJar()
    ctx = ssl._create_unverified_context()
    try:
        ctx.set_ciphers("DEFAULT@SECLEVEL=1")
    except ssl.SSLError:
        pass
    return urllib.request.build_opener(
        urllib.request.HTTPCookieProcessor(jar),
        urllib.request.HTTPSHandler(context=ctx),
    )


def fetch(op, url, data=None, referer=None, timeout=15):
    headers = {"User-Agent": UA}
    if referer:
        headers["Referer"] = referer
    if data is None:
        req = urllib.request.Request(url, headers=headers, method="GET")
    else:
        headers["Content-Type"] = "application/x-www-form-urlencoded"
        req = urllib.request.Request(
            url, data=urllib.parse.urlencode(data).encode(), headers=headers, method="POST"
        )
    with op.open(req, timeout=timeout) as resp:
        return resp.read().decode(resp.headers.get_content_charset() or "utf-8", errors="replace")


def strip_tags(s):
    return re.sub(r"\s+", " ", html.unescape(TAG_RE.sub(" ", s))).strip()


def main():
    depart, arrive, date = sys.argv[1:4]
    op = opener()
    fetch(op, f"{BASE_URL}/main.do")  # 세션 쿠키 확보
    body = fetch(
        op,
        f"{BASE_URL}/mrs/alcnSrch.do",
        {
            "deprCd": depart,
            "arvlCd": arrive,
            "pathDvs": "sngl",
            "pathStep": "1",
            "deprDtm": date,
            "busClsCd": "0",
            "rtrpChc": "1",
            "timeLinkMin": "00",
            "timeLinkMax": "23",
        },
        referer=f"{BASE_URL}/main.do",
    )

    out = []
    for m in FN_SATS_RE.finditer(body):
        args = ARG_RE.findall(m.group(1))
        if len(args) < 2 or len(args[1]) < 4:
            continue  # JS 함수 정의부 등 스케줄 행이 아닌 매치
        # 행 정보는 onclick 앵커 내부(매치 뒤)에 있다:
        # "02 : 00 (주)동양고속 심야우등 26 석 선택" — "선택" 전까지가 이 행
        row = strip_tags(body[m.end() : m.end() + 2500]).split("선택")[0]
        dep_min = int(args[1][:2]) * 60 + int(args[1][2:4])
        seats = re.search(r"(\d+)\s*석", row)
        remaining = int(seats.group(1)) if seats else None
        fare_m = re.search(r"([\d,]{4,})\s*원", row)
        fare = int(fare_m.group(1).replace(",", "")) if fare_m else None
        # "동양고속" 같은 회사명에 "고속"이 걸리지 않도록 구체적인 등급부터 확인
        bus_class = next((c for c in ("프리미엄", "심야우등", "심야고속", "우등") if c in row), "고속")
        comp = re.search(r"\((?:주|유)\)([가-힣A-Za-z]+)", row)
        out.append(
            {
                "depMin": dep_min,
                "busClass": bus_class,
                "company": comp.group(1) if comp else None,
                "remaining": remaining,
                "fare": fare,
                "soldOut": (remaining == 0) or ("매진" in row),
            }
        )
    json.dump(out, sys.stdout, ensure_ascii=False)


if __name__ == "__main__":
    try:
        main()
    except Exception as e:  # noqa: BLE001 — 어떤 실패든 폴백 신호로 축약
        print(f"{type(e).__name__}: {e}", file=sys.stderr)
        sys.exit(1)
