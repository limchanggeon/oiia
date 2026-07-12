# 바로타 백엔드 정리 (팀 공유용)

담당: 백엔드 전반 — FastAPI · LLM · SQLite · 외부 연동(k-skill/도구 어댑터).
기능 명세서 VER3 기준 **FR-1~11 전부 구현·검증 완료**. 이 문서 한 장으로 실행 방법,
무엇이 실데이터인지, API 계약, 남은 일을 파악할 수 있게 정리했다.

- 상세 FR 매핑·버그 수정 이력: [VER3.md](VER3.md)
- 시스템 구조·플로우차트 대응: [ARCHITECTURE.md](../ARCHITECTURE.md)
- v2(대화형) 시절 계약: [API.md](API.md) · [DB.md](DB.md) — **v3 계약은 `/docs`가 기준**

## 1. 빠른 시작

```bash
cd baro-ta/backend
python3 -m venv .venv && .venv/bin/pip install -r requirements.txt
cp .env.example .env            # 키 없이도 mock 모드로 전부 동작한다
.venv/bin/uvicorn app.main:app --port 8000
```

| 주소 | 내용 |
| --- | --- |
| `http://localhost:8000/app` | 5단계 시니어 UI (프론트 본 구현의 참조) |
| `http://localhost:8000/docs` | OpenAPI — **v3 계약의 기준 문서** |
| `http://localhost:8000/health` | 헬스체크 |

시연·심사용 단축 파라미터: `/app?step=3` (해당 단계로), `/app?fill` (입력 자동 채움),
`/app?fill&go` (채우고 바로 검색까지).

## 2. 동작 모드 — 무엇이 실데이터인가

`.env`의 `TOOL_MODE`로 전환한다. 카드마다 출처가 표시되므로 어느 모드든 사용자를 속이지 않는다.

| 데이터 | `mock` (기본) | `live` |
| --- | --- | --- |
| 열차 시간표·요금 (KTX·ITX-새마을·무궁화호) | 시뮬레이션 | **실데이터** (코레일 조회, 키 불필요) |
| 열차 좌석 상태 | 시뮬레이션 | **실시간** (매진 편 자동 제외) |
| SRT 시간표·좌석 | 시뮬레이션 | `SRT_ID/PW` 있으면 실데이터, 없으면 정직 제외 |
| 고속·시외버스 시간표·요금 | 시뮬레이션 | `TAGO_API_KEY` 있으면 실데이터, 없으면 정직 제외 |
| 버스 좌석 | 시뮬레이션 | 시뮬레이션 (명세상 실조회 불가) |
| 예약·결제 | 시뮬레이션 | **항상 시뮬레이션** (실제 예약은 코드 차단) |

live 실측(서울→부산): 열차 83편 실시간 조회, 매진 25편 자동 제외, 실제 요금
(성인 59,800원 / 노약자 경로우대 41,900원). 카드 문구는 명세 §1 그대로
"운행정보 실제 API 조회 · 좌석 실시간 · 예약 시뮬레이션".

조회 실패한 수단은 매진 처리하지 않고 "확인하지 못했어요"로 제외한다(FR-5).
`SCHEDULE_FALLBACK_MOCK=true`면 실패 시 시뮬레이션으로 전환하되 카드에 전환 사실을 표시한다.

## 3. API 한 장 요약 (v3)

모든 응답 스키마는 `app/schemas_v3.py`가 계약이며 `/docs`에서 실시간 확인.

| 메서드·경로 | 용도 |
| --- | --- |
| `GET /api/v3/places/search?q=` | 출발·도착지 자동완성 (역/터미널 구분) |
| `GET /api/v3/places/nearest?lat=&lon=` | 근처 역·터미널 추천 (자동 확정 금지 — 추천만) |
| `POST /api/v3/input/validate` | 단계 입력 검증·저장. 통과 못하면 이유 문구까지 서버가 생성 |
| `GET /api/v3/input/{sessionId}` | 저장된 입력 + 확인 요약 문장(lines[]) (FR-4) |
| `POST /api/v3/demo/{sessionId}/reset` | 데모 초기화 — 입력·시뮬 예약·알림 일괄 삭제 (§5-7) |
| `POST /api/v3/search` | 통합 검색 → 카드 2~3장 + unknownJourneys + 재조합 (FR-5~8) |
| `POST /api/v3/sim/hold` | 좌석 선점 시뮬레이션 시작 (15분, DEMO-XXXXXX) |
| `POST /api/v3/sim/{demoId}/open-payment` | 모의 결제 화면 진입 |
| `POST /api/v3/sim/{demoId}/complete` | 데모 완료 + 알림 2건 등록 (전날 18시, 출발 2시간 전) |
| `POST /api/v3/sim/{demoId}/cancel` | 선점 취소 |
| `GET /api/v3/sim` · `GET /api/v3/sim/{demoId}` | 시뮬레이션 예약 목록·단건 (FR-11) |
| `POST /api/v3/notify/{demoId}/demo` | [알림 시연] 즉시 발송 (실제 메일 — 승인 게이트 통과 필요) |
| `GET /api/stream/{sessionId}` | SSE — 에이전트 로그 실시간 수신 |

프론트가 따라가면 되는 최소 흐름:

```text
places/search → input/validate ×5단계 → input/{sid}(요약 확인)
→ search → sim/hold → open-payment → complete → notify demo
```

검색 요청의 선택 필드: `sim{soldOutAll, failSources, seatLookupFail, holdConflict}`(시연 토글),
`useSimulatedForUnknown`(확인불가를 시뮬레이션으로 대체 — 사용자가 눌렀을 때만),
`onlyConfirmed`(확인된 결과만).

## 4. 모듈 지도

```text
app/
├── api_v3.py        VER3 엔드포인트 13개 (v1·v2는 하위 호환용으로 유지)
├── schemas_v3.py    팀 계약 — Pydantic 모델 전부
├── db.py            SQLite (WAL, 단일 커넥션+락, TTL 만료는 조회 시 처리)
├── core/
│   ├── search.py    오케스트레이터 — 수단별 조회→좌석 병렬→카드 선별→재조합
│   ├── fares.py     인원 유형별 요금 (노약자·성인·학생, 미확인 규칙은 미적용 표시)
│   ├── places.py    역·터미널 카탈로그, 자동완성, 근처 추천
│   ├── simulation.py 선점→결제→완료 상태기계 (SIM_* 7종)
│   ├── notify.py    이메일 알림 (전날 18시 / 출발 2시간 전, 시연용 문구 강제)
│   └── gate.py      side-effect 승인 게이트 + 감사 로그
├── tools/
│   ├── schedule.py  시간표 어댑터 (live: TAGO→코레일 대체 / mock: 현실 배차)
│   ├── seats.py     좌석 어댑터 — 구간 단위 조회·60초 캐시·중복 병합·동시 3·재시도 1
│   └── tago.py      TAGO 3종 (열차/고속/시외) — 역·터미널 코드 동적 조회
├── llm/
│   ├── explain.py   경로 설명문 생성 + 사후 검증(숫자·최상급 주장 폐기)
│   └── holidays.py  공휴일 표 2026–2028 (매년 갱신 필요)
└── py/seat_lookup.py 코레일/SRT 조회 전용 subprocess (예약 함수 없음)
```

## 5. 심사 대응 — 데이터 정직성·안전 규칙 (코드로 강제)

"실데이터인가?"라는 질문에 답하는 장치들. 전부 서버가 강제하므로 프론트가 실수해도 뚫리지 않는다.

- **출처 3분리 표시**: 모든 카드에 `provenance{schedule, seat, booking, checkedAt}` +
  표시 문구를 서버가 생성. 실제/시뮬레이션 값은 상태명부터 분리
  (`LIVE_AVAILABLE` vs `SIMULATED_AVAILABLE` — 같은 이름으로 저장 자체가 불가).
- **UNKNOWN은 매진이 아니다**: 조회 실패는 별도 목록(unknownJourneys)으로 분리.
  사용자가 [시뮬레이션으로 보기]를 눌렀을 때만 대체하고 카드에 전환 사실을 덧붙인다.
- **실제 예약은 구조적으로 불가**: korail2·SRTrain의 예약 함수는 어디서도 호출하지 않고,
  `seats.reserve()`는 호출 즉시 예외를 던지는 차단 스텁. 예약번호도 `DEMO-XXXXXX` 형식만 생성.
- **LLM은 말만 옮긴다**: 시간·요금·좌석의 판단·계산·생성 금지(§4). 프롬프트 금지에
  더해 **사후 검증** — 설명문에 숫자가 섞이거나, 코드가 정한 근거(reasons)에 없는
  최상급 주장("가장 저렴")이 나오면 문장을 폐기하고 정형 문구로 대체.
  (실제로 둘 다 위반 사례가 있어서 만든 장치다.)
- **외부 호출 예절**: 구간 단위 1회 조회를 시간표·좌석이 공유, 60초 캐시,
  동시 3, 재시도 1회 상한. 이메일 발송(실제 외부 부작용)은 승인 게이트+감사 로그.

## 6. 검증 이력

점검 2회에서 16건을 발견·수정했다(전체 표는 [VER3.md](VER3.md)). 대표 사례:

- 자정 넘김 편(20:49 출발→익일 00:03 도착)이 "일찍 도착"으로 오판되어 1위 카드로 노출
- LLM이 최저가가 아닌 편에 "가장 저렴한 기차예요" 생성 (숫자 필터를 우회하는 위반)
- 당일 검색에 이미 출발한 편 노출, 음수 인원 통과, 단계 저장 시 인원 리셋

회귀 범위: v3 전 플로우(입력→검색→선점→완료→알림) + v2 dialog + v1 routes, mock/live 양쪽.

## 7. 남은 것

**.env 값만 채우면 켜지는 것** (코드 완료):

| 항목 | 키 | 어떻게 |
| --- | --- | --- |
| 버스 실조회 | `TAGO_API_KEY` | data.go.kr에서 국토부(TAGO) 열차·고속버스·시외버스 3종 활용신청 |
| SRT 실조회 | `SRT_ID` / `SRT_PW` | SRT 회원 계정 (조회에도 로그인 필요) |
| 알림 실발송 | `DEMO_EMAIL_TO` / `SMTP_*` | 시연용 사전 등록 주소 1개만 |

**팀 결정 대기**: 학생 할인 규칙(현재는 성인 운임+"학생 할인 미적용" 표시로 안전 처리),
할인율 공표 기준 검증(현재 값은 시연용 근사치).

**미착수**: ODsay 복합 경로(데모 시나리오에는 불필요), API.md·DB.md의 v3 갱신
(그때까지 `/docs`가 기준).

## 8. 자주 하는 질문

- **키 없이 시연 되나?** 된다. mock 모드가 기본이고 전 흐름이 돌아간다. 카드에는
  "시뮬레이션"으로 정직하게 표시된다.
- **인터넷 없는 심사장이면?** mock 모드 그대로. LLM 설명문도 실패 시 정형 문구로
  대체되므로 Anthropic 키가 없어도 흐름이 끊기지 않는다.
- **실제 결제·예약이 일어날 가능성은?** 없다. 결제 모듈이 없고, 예약 함수는 호출
  경로 자체가 없으며, 진입 시도는 예외로 차단된다.
- **DB 초기화는?** `POST /api/v3/demo/{sid}/reset` 또는 `barota.db*` 파일 삭제.
