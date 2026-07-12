# VER3 구현 현황 (백엔드)

기능 명세서 VER3 기준. 담당: 백엔드 전반 (FastAPI · LLM · SQLite · 도구 어댑터).

- 계약: `app/schemas_v3.py` · OpenAPI `http://localhost:8000/docs`
- 레퍼런스 UI: `http://localhost:8000/app` (5단계 입력 — 프론트 본 구현의 참조)

## FR 매핑

| FR | 기능 | 구현 | 상태 |
| --- | --- | --- | --- |
| FR-1 | 단계형 입력 (한 화면 한 필드, 5단계) | `static/index.html` · `/api/v3/places/*` | ✅ |
| FR-2 | 입력 기본값·검증 | `POST /api/v3/input/validate` (서버가 판단, 안내 문구까지 생성) | ✅ |
| FR-3 | 단계 이동·중단 복귀 | `GET /api/v3/input/{sid}` · `POST /api/v3/demo/{sid}/reset` | ✅ |
| FR-4 | 확인 요약 + 필드별 수정 | `GET /api/v3/input/{sid}` → `lines[]` | ✅ |
| FR-5 | 전 수단 통합 검색 | `POST /api/v3/search` · `core/search.py` · `tools/tago.py` | ✅ (TAGO 키 필요) |
| FR-6 | 좌석 상태·매진 제외 | `tools/seats.py` (5종 상태, UNKNOWN 미변환) | ⚠️ 열차 실조회 미구성 |
| FR-7 | 여정 재조합 | `core/search.py:_recombine` (환승≤1·대기≥20분·소요≤1.5배) | ✅ |
| FR-8 | 경로 제시 + LLM 설명문 | 추천 근거 키 + `llm/explain.py` (숫자 생성 차단) | ✅ |
| FR-9 | 좌석 선택·선점·결제 시뮬레이션 | `core/simulation.py` (SIM_* 7종 상태) | ✅ |
| FR-10 | 탑승 안내·이메일 알림 | `core/notify.py` · `POST /api/v3/notify/{id}/demo` | ✅ (SMTP 설정 필요) |
| FR-11 | 시뮬레이션 예약 확인 | `GET /api/v3/sim` | ✅ |

## 시연 안전 규칙 (§2, §5) — 코드로 강제

| 규칙 | 구현 |
| --- | --- |
| korail2·SRTrain 예약 함수 호출 금지, 백엔드에서도 비활성화 | `tools/seats.py`에 예약 진입점이 없다. `seats.reserve()`는 호출 즉시 `ReservationDisabled` 예외를 던지는 차단 스텁이다. 예약은 `core/simulation.py`(목업)만 수행한다. |
| 실제/시뮬레이션 값을 같은 상태명으로 저장 금지 (§5-1) | `SeatStatus` 5종이 `LIVE_*` / `SIMULATED_*` / `UNKNOWN`을 타입 수준에서 분리한다. |
| 운행정보·좌석·예약 각각의 데이터 모드 표시 (§5-2) | 모든 경로에 `provenance{schedule, seat, booking, checkedAt, label}`. 표시 문구는 서버가 생성한다. |
| UNKNOWN을 매진으로 변환 금지 (§5-4) | 별도 `unknownJourneys[]`로 분리. 사용자가 [시뮬레이션으로 보기]를 선택할 때만 대체하고 카드에 전환 사실을 덧붙인다 (§5-5). |
| 좌석 조회 캐시·동시호출 합치기·재시도 제한 | `seats.py`: 30초 캐시, in-flight 병합, 동시 4, 재시도 1회, 타임아웃 6초. |
| 데모 초기화로 일괄 삭제 (§5-7) | `db.demo_reset()` — 입력값·시뮬레이션 예약·서버 알림 큐를 한 번에 삭제. |
| LLM은 시간·요금·좌석을 판단·변경 금지 (§4) | 프롬프트 금지 + **사후 검증**: 설명문에 숫자·단위가 섞이면 폐기하고 정형 문구로 대체 (`llm/explain.py:sanitize`). |

## 외부 연동 상태

| 연동 | 용도 | 상태 | 필요한 것 |
| --- | --- | --- | --- |
| TAGO 열차/고속버스/시외버스 | 운행정보·요금 (실제 API) | 구현 완료 | `TAGO_API_KEY` — data.go.kr에서 3개 오픈API 활용신청 |
| korail2 / SRTrain | 열차 좌석 **조회 전용** | 미구성 (`seats._lookup_live_train`) | 라이브러리 설치 + `KORAIL_ID/PW`, `SRT_ID/PW` |
| 버스 좌석 | 시뮬레이션 (명세상 실조회 불가) | ✅ | — |
| 이메일 | 탑승 안내 | 구현 완료 | `DEMO_EMAIL_TO`, `SMTP_*` |
| ODsay | 도시간 복합 경로 | 미착수 | 앱 등록·IP 화이트리스트 |

TAGO 역·터미널 코드는 **하드코딩하지 않고** 코드 조회 API로 매칭해 캐시한다 (`tools/tago.py`).
잘못된 코드를 추측하면 조용히 빈 결과가 나오기 때문이다.

## 검증 중 발견해 고친 것

| 문제 | 조치 |
| --- | --- |
| LLM이 설명문에 실제와 다른 수치 생성 ("10분 빠르고" ↔ 실제 5분) | 숫자 포함 시 폐기 → 정형 문구 (FR-8 위반 방지) |
| 좌석 캐시가 시뮬레이션 플래그를 무시해 매진 시연이 무력화 | 강제 시뮬 시 캐시 우회 |
| 재조합이 각 구간 첫 편성만 확인 → 첫차 매진이면 포기 | 전 편성 조합 탐색 |
| 추천 카드가 요금순에 밀려 최속 열차 누락 | 대표편(빠름·저렴·직통) 우선 선별 |
| mock 배차 간격(40분)이 비현실적이라 환승 조합이 성립 불가 | 실제 배차에 맞게 조정 (KTX 20분 등) |

## 남은 것 (명세 §6 추후 확정 포함)

- 열차 좌석 실시간 조회 (korail2/SRTrain) — 계정 확보 후 `_lookup_live_train` 구현
- ODsay 복합 경로
- 학생 할인 규칙 확정 (`core/fares.py`의 `DISCOUNTS`) — 현재 규칙 미확인 수단은 성인 운임 + "학생 할인 미적용" 표시
- 노약자·학생 할인율 사업자 공표 기준 검증 (현재 값은 시연용 근사치)
