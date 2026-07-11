# 바로타 백엔드 — FastAPI 오케스트레이터

담당: FastAPI · LLM(상용 API/로컬) · SQLite. 플로우차트의 "오케스트레이터 + 판단 엔진 + 저장" 구현.

**설계 원칙 = 붙임성.** 팀원 코드(Next.js 프론트, k-skill CLI 도구)는 아래 계약만 지키면
서로의 내부를 몰라도 붙는다. 모든 스위칭은 환경변수로 한다(.env.example).

## 실행

```bash
cd backend
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --reload --port 8000
```

- 기본값(`LLM_PROVIDER=rule`, `TOOL_MODE=mock`)이면 **키·네트워크 없이 바로 돈다** (골든패스).
- API 문서(OpenAPI): http://localhost:8000/docs ← 팀 간 계약 명세
- Docker: 저장소 루트에서 `docker compose up --build`

## 기능 명세서 매핑 (/api/v2/*)

`기능 명세서.txt` 기준 백엔드 담당 기능 구현 현황. 계약은 `app/schemas_v2.py` + `/docs` 참고.

| FR | 기능 | 엔드포인트 / 모듈 | 상태 |
| --- | --- | --- | --- |
| FR-2 | LLM 슬롯 추출 (자연어 날짜·기본값: 시간대 '아침', 인원 1, 출발지=위치) | `POST /api/v2/dialog/turn` · `llm/dialog.py`, `llm/rule_dialog.py` | ✅ |
| FR-3 | 선택형 되묻기 (질문 1개 + 선택지 2–3, 명사형 라벨) | 위와 동일 — LLM 생성 + 템플릿 폴백 | ✅ |
| FR-4 | 확인 요약 ("7월 15일 화요일 아침 / 대전 → 부산 / 어른 1명") | `core/journey.py:summarize_slots` (결정적) | ✅ |
| FR-6 | 전 수단 통합 검색 (개별 장애 → 해당 수단 제외 + 고지) | `POST /api/v2/journeys/search` · `core/journey.py` | ✅ (mock 어댑터) |
| FR-7 | 매진 확인·자동 제외 | 위와 동일 | ✅ (mock) |
| FR-8 | 여정 재조합 (환승 ≤1, 대기 ≥20분, 소요 ≤직결 최속 1.5배) | `core/journey.py:recombine` | ✅ 알고리즘 제안 구현 |
| FR-10 | 좌석 선점 (예약번호·운임·결제 기한, 결제 자동화 금지) | `POST /api/v2/holds` · `tools/transit_mock.py:reserve` | ✅ (mock — korail2/SRTrain 교체 지점 표시) |
| FR-15 | 내 예매 확인 (결제 대기 카드·남은 시간·취소) | `GET /api/v2/holds`, `pay-confirmed`, `cancel` | ✅ |
| FR-1 | 음성 입력(STT) | `static/index.html` — Web Speech API (ko-KR) | ✅ 레퍼런스 UI |
| FR-9 | 경로 제시 화면 | `static/index.html` — 카드 + LLM 설명문 | ✅ 레퍼런스 UI |
| FR-11 | 결제 연결 | `POST /api/v2/holds/{id}/pay-confirmed` — 결제 자체는 외부(코레일 앱·창구), 앱은 카드정보를 묻지 않음 | ⚠️ 방식 토의 필요 |
| FR-13 | 탑승 안내 | `core/explain.py:build_reminders` — 전날 20시 · 출발 2시간 전 시각·문구 생성 | ⚠️ 발송 채널 토의 필요 |
| — | 경로 설명문 (LLM 용도 3번) | `llm/explain.py` + `core/explain.py` 폴백 | ✅ |

**시니어 UI 레퍼런스 클라이언트** — <http://localhost:8000/app> (의존성 0, 단일 HTML).
Next.js 본 구현의 참조용이며, API 계약이 실제로 동작함을 증명하는 E2E 데모다.
`?demo` 자동 재생 · `?say=<문장>` 임의 발화 시연 · 홈 화면 "시연 설정"에서 매진/장애/경합 토글.
큰 글씨(기본 20px, 토글 시 24px)·64px 버튼·음성 입력 등 NFR-1 시니어 접근성 반영.

**시뮬레이션 모드** (시스템 구성 "데모용 매진·선점·결제 목업") — 요청 `sim` 필드로 제어:
`{"soldOutAll": true}` 전 직결 매진→재조합 시연 · `{"failSources": ["SRT"]}` 수단 장애 시연 ·
`{"holdConflict": true}` 선점 경합 매진(409) 시연.

**명세서 토의사항에 대한 백엔드 기본 동작:**

- FR-3 "3회 이상 반복" — 서버는 `askCount`를 세어 응답에 포함만 하고, 예외 UI(상담 연결 등)는 프론트/회의에서 결정.
- FR-7 "실조회 실패(anti-bot)" — 어댑터 예외 → 해당 수단 제외 + `excludedSources` 고지 (FR-6 예외와 동일 처리).
- FR-10 "버스 선점 불가" — `unreservableLegs`로 안내 문구 제공, 선점 없이 결제 단계 직행 유도.

> **팀원용 인터페이스 명세: [API.md](API.md)** — 데이터 형식·필드 정의·실측 예시·에러·상태 전이 전부 이 문서에 있다.

## API 계약 (Express server/ 와 동일 + 확장)

| 메서드 | 경로 | 설명 |
| --- | --- | --- |
| POST | `/api/nlu/parse` | 자연어 → `{got, agent}` (LLM 또는 규칙 기반) |
| POST | `/api/routes/search` | 경로 후보 + scoring.py 재랭킹 → `{routes, agent}` |
| GET | `/api/standby/{searchId}/check` | 취소표 좌석 조회 (SQLite 세션·TTL) |
| POST | `/api/bookings` | 자동 예매 시작 — **side_effect 게이트** 통과 필요 |
| POST | `/api/bookings/{id}/pay` | 결제 확정 — **side_effect 게이트** |
| GET | `/api/travel/suggest` | 숙소·투어 추천 (형태만 유지 — 실연동은 Express 참고) |
| GET | `/api/stream/{sessionId}` | **SSE** — 에이전트 로그·이벤트 실시간 push |
| GET | `/health` | 상태 + 현재 llm_provider/tool_mode |

요청·응답 스키마는 `app/schemas.py` = `client/src/types.ts` 1:1. 기존 React 클라이언트는
`VITE_API_URL=http://localhost:8000` 만 지정하면 그대로 동작한다(검증됨).

## 팀원 통합 지점

### Next.js 프론트 담당
- REST는 위 표 그대로. 에이전트 로그는 응답 JSON의 `agent` 배열 **또는** SSE로 수신:

```ts
const es = new EventSource(`${API}/api/stream/${sessionId}`); // 세션 없으면 "public"
es.onmessage = (e) => {
  const ev = JSON.parse(e.data); // {type: "agent", tag: "NLU", msg: "..."} 등
};
```

- 요청 body에 `sessionId`를 넣으면 해당 채널로 이벤트가 push된다.

### k-skill CLI 담당 (도구)
`TOOL_MODE=live`일 때 아래 계약으로 subprocess 호출된다 (`app/tools/kskill.py`):

```bash
echo '{"origin":"서울","dest":"부산","arriveBy":840,"dateIso":"2026-07-08"}' \
  | k-skill run route-search --json
# → stdout에 RouteOption[] JSON (app/schemas.py 참고), 성공 시 exit 0
```

- 바이너리 경로: `KSKILL_BIN` 환경변수 (기본 `k-skill`)
- 실패(비정상 종료·타임아웃·JSON 아님) 시 서버가 **cache → mock 3단 폴백**으로 처리하므로
  실패를 숨기지 말고 exit code로 알리면 된다. 폴백 여부는 에이전트 로그 `[TOOL] source=...`에 표시된다.

### LLM 스위칭 (본인 담당)
`LLM_PROVIDER` 환경변수 하나로 교체 — 파서 계약(`app/llm/base.py`)은 동일:

| 값 | 구현 | 비고 |
| --- | --- | --- |
| `rule` | `rule_parser.py` | 기본값·폴백. 키 불필요 |
| `anthropic` | `anthropic_parser.py` | 상용 API (Claude, structured outputs). `ANTHROPIC_API_KEY` 필요 |
| `ollama` | `ollama_parser.py` | 로컬 LLM (guided JSON, temp=0). `OLLAMA_BASE_URL` |

LLM 호출이 실패하면 자동으로 규칙 기반 폴백하고 에이전트 로그에 드러낸다 (시연이 죽지 않음).

## 승인 게이트 (read / side_effect)

- 조회(read)는 자동 통과, 예매·결제(side_effect)는 승인 근거를 SQLite `audit_log`에 기록.
- 데모 기본값 `REQUIRE_APPROVAL=false`: 버튼 클릭 = 암묵 승인 (기존 클라이언트 호환).
- `REQUIRE_APPROVAL=true`: side_effect 요청에 `X-Approved-By: <사용자 식별>` 헤더 필수, 없으면 403.

## SQLite 스키마 (`app/db.py`, WAL)

> ERD와 설계 노트(관계·TTL·상태 전이·JSON 컬럼 전략)는 **[DB.md](DB.md)** 참고.

| 테이블 | 용도 |
| --- | --- |
| `standby_sessions` | 취소표 조회 세션 (attempts/target, TTL 10분) |
| `bookings` | 예매 (pending → paid) |
| `tool_cache` | LIVE 조회 결과 60초 hold |
| `audit_log` | 승인 게이트 판정 기록 |

## 디렉토리

```
backend/app/
├─ main.py            # FastAPI 앱, CORS, lifespan
├─ api.py             # 엔드포인트 (REST + SSE)
├─ schemas.py         # 계약 (types.ts와 1:1)
├─ config.py          # 환경변수
├─ db.py              # SQLite WAL
├─ events.py          # SSE 브로커
├─ core/scoring.py    # 재랭킹 (결정적 코드)
├─ core/gate.py       # read/side_effect 승인 게이트
├─ llm/               # rule / anthropic / ollama 파서
└─ tools/             # 3-mode 어댑터 + k-skill subprocess + mock
```
