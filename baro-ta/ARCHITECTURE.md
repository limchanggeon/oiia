# 바로타 — 시스템 구조 & 실연동 가이드

> 기준일 2026-07-08 · 팀 oiia — 서비스 개요와 실행 방법은 [README.md](README.md) 참고.

기획 단계의 모의(mock) 프로토타입에서 출발해, 현재는 **지도·기차·고속버스·숙박/관광이 전부 실데이터**로 동작한다.
모든 외부 연동은 같은 원칙을 따른다: **실데이터를 먼저 시도하고, 실패하면 mock/대체 구현으로 자동 폴백해서 시연이 절대 죽지 않는다.**

## 전체 구조

```
┌─ client (Vite + React + TS, :5173) ─────────────────────────────┐
│  ChatRail ── 대화형 파라미터 수집 (출발지·도착지·날짜·도착시각)        │
│  RoutesPanel ── RouteMap(지도) + 경로 리스트                       │
│  Standby → Booking → Payment → DonePanel(숙소·투어 추천)          │
└──────────────────────── /api proxy ─────────────────────────────┘
┌─ server (Express ESM, :4000) ───────────────────────────────────┐
│  nlu.js      규칙 기반 파서            [LLM 교체 지점]              │
│  routes.js   경로 검색 오케스트레이션 ──┬─ korail.js ─ py/korail_search.py (korail2-ncard)
│                                      └─ kobus.js ── py/kobus_search.py (KOBUS 공식 HTTP)
│  myrealtrip.js  마이리얼트립 공식 MCP 서버 (JSON-RPC tools/call)     │
│  standby.js / bookings.js  취소표 폴링·자동 예매 (모의)              │
└─────────────────────────────────────────────────────────────────┘
```

## 실연동 현황

| 기능 | 데이터 소스 | 방식 | 실패 시 폴백 |
| --- | --- | --- | --- |
| 지도 + 루트 | 네이버지도 (NCP Maps JS v3) | 브라우저 SDK, `client/.env` 키 | Leaflet + OpenStreetMap (키 불필요) |
| 기차 조회 | 코레일 (비공식 `korail2-ncard`) | 파이썬 child_process, 로그인 불필요 | 모의 데이터 (2분간 재시도 억제) |
| 고속버스 조회 | KOBUS 공식 HTTP (`kobus.co.kr`) | 파이썬 child_process | 버스 제외, 기차만으로 진행 |
| 숙박·관광 추천 | 마이리얼트립 공식 MCP | 서버에서 JSON-RPC 직접 호출, 인증 없음 | 추천 섹션 생략 (조용히) |
| NLU (챗봇) | 규칙 기반 (`nlu.js`) | — | — (로컬 LLM 교체 예정, 아래 참고) |
| 취소표·자동예매 | 모의 | — | — (실예약은 코레일 계정 필요) |

## 처음 받았을 때 설정

```bash
# 1. Node 의존성 (client/server 모두)
npm install

# 2. 파이썬 venv — 코레일·KOBUS 실시간 조회용 (없어도 앱은 mock으로 동작)
python3.13 -m venv server/py/.venv        # 3.10+ 필요
server/py/.venv/bin/pip install -r server/py/requirements.txt

# 3. 네이버지도 키 (없어도 Leaflet 폴백으로 동작)
cp client/.env.example client/.env        # VITE_NAVER_MAP_KEY_ID 채우기

# 4. 실행
npm run dev                               # API :4000 + 웹 :5173
```

## 연동별 상세

### 지도 — `client/src/components/RouteMap*.tsx`

- `RouteMap.tsx`(디스패처)가 구현을 선택한다: `VITE_NAVER_MAP_KEY_ID`가 있으면 `RouteMapNaver`, 없거나 SDK 로드·인증 실패 시 `RouteMapLeaflet`.
- 네이버 인증 실패는 지도 생성 *이후* 늦게 도착할 수 있어 `navermap_authFailure` 전역 훅을 구독해 언제든 폴백한다. 한 번 실패하면 세션 내 재시도하지 않는다(패널 이동 시 깜빡임 방지).
- 지도 라이브러리는 이 세 파일 밖으로 새지 않는다 — 바깥은 역 이름(`origin`/`dest`)만 넘긴다. 역 좌표는 `client/src/stations.ts`.
- **폰 시연 주의**: 폰이 접속하는 주소(예: `http://192.168.x.x:5173`)를 NCP 콘솔 Web 서비스 URL에 추가 등록해야 폰에서 네이버지도가 뜬다. 미등록이면 폰에서만 Leaflet이 뜬다(시연은 그대로 굴러감).

### 기차 — `server/src/services/korail.js` + `py/korail_search.py`

- k-skill `ktx-booking`이 쓰는 것과 같은 스택(`korail2-ncard` + `pycryptodome`). **조회는 코레일 로그인이 필요 없다.** 실제 열차번호·시각·가격·매진 여부가 온다.
- 비공식 API라 코레일 앱의 anti-bot 정책 변경으로 언제든 깨질 수 있다 → 어떤 실패든 mock으로 자동 폴백하고 2분간 재시도하지 않는다. 에이전트 로그에 `[KORAIL] 실시간 조회 실패 → 모의 데이터 폴백`이 찍힌다.
- 검색 로직: 희망 도착 5시간 전부터 조회 → 희망 시각 이전 도착 열차 필터 → 도착시각 근접순 상위 4개 스코어링.
- **실예약(reserve)은 코레일 멤버십 계정이 필요** — `korail2`가 예약·취소까지 지원하므로 계정이 생기면 `bookings.js`의 모의 예매를 실예약으로 교체할 수 있다. 단, 예약 후 20분 내 미결제 시 자동 취소되는 실제 예약이므로 리허설 시 주의.

### 고속버스 — `server/src/services/kobus.js` + `py/kobus_search.py`

- KOBUS 공식 웹의 HTTP 플로우(`/mrs/alcnSrch.do`)를 그대로 쓴다. 조회 전용 — 좌석 선점·결제는 하지 않는다.
- 실제 배차 시각·회사·등급(우등/프리미엄/심야)·잔여석이 온다. 요금은 할인 표기되는 등급(프리미엄)만 노출되므로 나머지는 거리 기반 추정(`BUS_FARE_PER_MIN`). 도착시각도 시간표에 없어 거리×1.7로 추정.
- 터미널 코드는 확인된 것만 등록되어 있다 (`kobus.js`의 `TERMINAL_CODES`):

  | 역/도시 | 코드 | 터미널 |
  | --- | --- | --- |
  | 서울 | 010 | 서울경부(고속터미널) |
  | 부산 | 700 | 부산종합 |
  | 광주송정 | 500 | 광주(유·스퀘어) |

  노선을 추가하려면 kobus.co.kr의 노선 조회(`/mrs/readRotLinInf.ajax`)에서 코드를 확인해 표에 한 줄 추가한다. 미등록 구간은 자동으로 기차만 검색된다.
- 경로 검색 결과는 **기차 4건 + 버스 2건**을 합쳐 같은 기준(도착 여유·소요시간)으로 스코어링한다.

### 숙박·관광 — `server/src/services/myrealtrip.js`

- 마이리얼트립 **공식** MCP 서버 `https://mcp-servers.myrealtrip.com/mcp`. 인증·세션 없이 JSON-RPC `tools/call`이 바로 동작한다.
- 사용 도구: `searchStays`(숙소, 체크인/아웃 날짜 반영), `searchTnas`(투어·티켓·액티비티, 판매량순).
- 응답이 위젯 트리(UI DSL) + `copy_text`라서, 위젯 항목의 Text 노드(`value`) · Image(`src`) · `onClickAction.url`을 추출해 카드로 정규화한다. 링크는 날짜가 반영된 실제 예약 페이지.
- 예매 완료 화면(`DonePanel`)이 `/api/travel/suggest`를 호출해 숙소 4 + 즐길거리 4 카드를 보여준다. 실패하면 섹션 자체가 생략될 뿐 화면은 정상.

## API (기획 대비 변경분)

| 메서드 | 경로 | 변경 |
| --- | --- | --- |
| POST | `/api/routes/search` | `dateIso`(여행 날짜) 추가 — 실시간 조회에 사용. 응답 계약(`RouteOption[]`)은 동일 |
| GET | `/api/travel/suggest?dest=&checkIn=` | **신규** — 마이리얼트립 숙소·투어 카드 |

## 시연 가이드

- `http://localhost:5173/?demo` — 서울→부산 시나리오 자동 재생.
- 실데이터 모드에서는 **매진 여부가 진짜**라서, 1위 열차가 매진이면 취소표 흐름이 자연스럽게 나오고 아니면 바로 자동 예매로 간다. 취소표 흐름을 반드시 보여줘야 하면 서버를 `FORCE_STANDBY_DEMO=1 npm run dev`로 켠다.
- 인터넷이 없거나 코레일이 막히면 에이전트 로그에 폴백 라인이 찍히고 mock으로 이어진다 — 시연 관점에서는 동일한 흐름.
- 에이전트 콘솔(하단)에 `[KORAIL]` `[KOBUS]` `[MRT]` 태그가 찍히면 실데이터로 돌고 있다는 뜻.

## 남은 작업 (1차 목표 대비)

1. **챗봇 LLM 교체** — `server/src/services/nlu.js`의 `[LLM 교체 지점]`을 로컬 LLM(Ollama, JSON 스키마 강제) 호출로 교체. 반환 계약을 유지하고, 검증 실패·서버 미기동 시 현재 규칙 파서로 폴백하는 하이브리드 권장.
2. **코레일 실예약** — 코레일 멤버십 계정 확보 시 `bookings.js` 교체.
3. (선택) 공연 잔여석 — k-skill `ticket-availability`는 특정 공연 URL/ID가 입력으로 필요해 보류. 시연용 공연을 정하면 붙일 수 있다.

## 검증 방법

```bash
# 기차+버스 실시간 검색
curl -s -X POST http://localhost:4000/api/routes/search \
  -H "Content-Type: application/json" \
  -d '{"origin":"서울","dest":"부산","arriveBy":840,"dateIso":"2026-07-09"}'

# 숙소·투어 추천
curl -s "http://localhost:4000/api/travel/suggest?dest=%EB%B6%80%EC%82%B0&checkIn=2026-07-09"

# 파이썬 조회 단독 테스트
server/py/.venv/bin/python server/py/korail_search.py 서울 부산 20260709 090000
server/py/.venv/bin/python server/py/kobus_search.py 010 700 20260709
```
