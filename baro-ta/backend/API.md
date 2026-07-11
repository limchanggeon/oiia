# 바로타 백엔드 API 명세서

| 항목 | 내용 |
| --- | --- |
| 버전 | v2 (기능 명세서 FR-2~FR-15 대응) |
| 기준일 | 2026-07-11 |
| 담당 | 백엔드 (FastAPI · LLM · SQLite) |
| Base URL | 개발 `http://localhost:8000` |
| 살아있는 명세 | `http://localhost:8000/docs` (OpenAPI — 이 문서와 스키마 동일, `app/schemas_v2.py`가 원본) |
| 참고 구현 | `http://localhost:8000/app` (시니어 UI 레퍼런스 — 아래 계약을 실제로 소비하는 예제 코드) |

이 문서는 **프론트(Next.js)·도구(k-skill) 팀원이 백엔드와 주고받는 데이터의 형식과 의미**를 정의한다.
모든 응답은 `application/json`, 인코딩은 UTF-8.

---

## 1. 공통 규약

### 1-1. 데이터 표현

| 항목 | 규약 | 예 |
| --- | --- | --- |
| 시각 | **자정 기준 분(minute) 정수** | `380` = 06:20, `840` = 14:00 |
| 날짜 | ISO `YYYY-MM-DD` 문자열 | `"2026-07-14"` |
| 일시(알림 등) | ISO 8601 로컬 시각 | `"2026-07-11T20:00:00"` |
| 금액 | 원 단위 정수 | `38300` |
| 도시(역) | 아래 16개 문자열만 유효 | `서울, 용산, 수서, 대전, 동대구, 부산, 광주송정, 목포, 오송, 천안아산, 익산, 전주, 강릉, 포항, 울산, 여수` |

분 → "HH:MM" 변환: `String(Math.floor(m/60)).padStart(2,"0") + ":" + String(m%60).padStart(2,"0")`

### 1-2. 세션

- 요청 body의 `sessionId`(문자열)는 클라이언트가 생성·유지한다 (예: localStorage 랜덤 ID).
- 대화 슬롯 상태는 **서버(SQLite)가 sessionId별로 보관**한다 — 프론트는 매 턴 텍스트만 보내면 된다.
- SSE 구독(§3-9)과 내 예매 조회(§3-5)도 같은 sessionId를 쓴다.

### 1-3. 승인 게이트 헤더

예매·결제·취소 등 **side_effect 엔드포인트**(§3-4, 3-7, 3-8)는 `X-Approved-By: <사용자식별>` 헤더를 받는다.

- 개발 기본값(`REQUIRE_APPROVAL=false`): 헤더 생략 가능 (버튼 클릭 = 암묵 승인으로 기록됨)
- `REQUIRE_APPROVAL=true`: 헤더 없으면 **403** — 프론트는 항상 붙이는 것을 권장

### 1-4. 에러 형식

| HTTP | 의미 | body |
| --- | --- | --- |
| 400 | 필수 값 누락/불량 | `{"detail": "필수 슬롯 미충족: ['date']"}` (비즈니스) 또는 FastAPI 검증 배열 (스키마 위반) |
| 403 | 승인 게이트 거부 | `{"detail": "side_effect 액션 '...'에는 사용자 승인이 필요합니다 (X-Approved-By 헤더)"}` |
| 404 | 리소스 없음 | `{"detail": "예약을 찾을 수 없습니다."}` |
| 409 | 상태 충돌 | `{"detail": "방금 자리가 나갔어요"}` (선점 경합), `{"detail": "결제 확인 불가 상태: paid"}` |

### 1-5. agent 배열 (에이전트 로그)

모든 주요 응답에 `agent: AgentLine[]`이 포함된다. 화면 하단 로그/디버그 패널용이며 **UI 로직에 사용하지 말 것**.

```ts
type AgentLine = { tag: string; msg: string }
// tag 종류: NLU, ASK, CONFIRM, GPS, SEARCH, EXPLAIN, RECOMBINE, RESULT, HOLD, PAID, MYBOOK, POLL, ERROR
```

### 1-6. 시뮬레이션 모드 (데모용)

검색·선점 요청의 `sim` 필드로 예외 상황을 재현한다. **미지정 시 전부 꺼짐.**

```ts
type SimOptions = {
  soldOutAll?: boolean      // 직결 전 후보 매진 → 재조합(FR-8) 시연
  failSources?: string[]    // 수단 조회 장애 시연. 예: ["SRT"]
  holdConflict?: boolean    // 선점 경합 매진(409) 시연
}
```

---

## 2. 공통 데이터 타입

### TripDate

| 필드 | 타입 | 설명 | 예 |
| --- | --- | --- | --- |
| label | string | 상대 표현 또는 월일 | `"내일"`, `"7월 14일"` |
| md | string | 화면 표시용 월일 | `"7월 14일"` |
| iso | string | 검색·저장용 | `"2026-07-14"` |

### Slots (FR-2)

| 필드 | 타입 | 필수 슬롯 | 설명 |
| --- | --- | --- | --- |
| departure | string \| null | ✅ | 출발 도시 (16개 목록 내) |
| arrival | string \| null | ✅ | 도착 도시 |
| date | TripDate \| null | ✅ | 출발 날짜 |
| timeOfDay | `"아침"\|"낮"\|"저녁"\|"밤"` \| null | — | 응답에서는 기본값 `"아침"`이 채워져 옴 |
| passengers | int \| null | — | 응답에서는 기본값 `1`이 채워져 옴 |

### Leg (여정 구간)

| 필드 | 타입 | 설명 |
| --- | --- | --- |
| mode | `"KTX"\|"SRT"\|"고속버스"\|"시외버스"` | 수단 |
| no | string | 편명 (`"KTX 421"`, `"고속버스 35회"`) |
| **from** | string | 출발 도시 — ⚠️ JSON 키가 예약어 `from` (TS 인터페이스 작성 시 주의) |
| to | string | 도착 도시 |
| dep / arr | int | 출발/도착 시각 (분) |
| fare | int | 구간 요금(원) |
| reservable | bool | 온라인 선점 가능 여부 — **열차만 true, 버스는 false** |

### Journey (FR-6/7/8/9)

| 필드 | 타입 | 설명 |
| --- | --- | --- |
| id | string | `"jn_..."` — 선점 요청에 그대로 전달 |
| legs | Leg[] | 1개(직결) 또는 2개(환승 1회) |
| dep / arr | int | 전체 출발/도착 시각 (분) |
| durationMin | int | 총 소요(분) |
| totalFare | int | 1인 총 요금(원) |
| transfers | int | 갈아타기 수 (0 또는 1) |
| transferWaitMin | int \| null | 환승 대기(분) — 항상 ≥ 20 |
| reservable | bool | 전 구간 온라인 선점 가능 여부 |
| explain | string \| null | 경로 설명문 (LLM 생성, 카드에 그대로 표시) |

### HoldInfo (FR-10/15)

| 필드 | 타입 | 설명 |
| --- | --- | --- |
| holdId | string | `"hd_..."` |
| status | `"held"\|"paid"\|"cancelled"\|"expired"` | 상태 전이는 §4 참고 |
| reserveNo | string \| null | 예약번호 — 버스만 있는 여정이면 null |
| fare | int | **인원 반영** 총 결제 금액(원) |
| deadlineIso | string \| null | 결제 기한 |
| remainingSec | int | 결제까지 남은 초 (held가 아니면 0) — 카운트다운은 이 값 기준으로 클라이언트가 진행 |
| journey | Journey | 선점한 여정 |
| passengers | int | 인원 |
| notices | string[] | FR-10 안심 문구 3종 — **화면에 그대로 표시** (문구 일관성을 위해 서버 제공) |
| unreservableLegs | `{mode, notice}[]` | 버스 구간 안내 (선점 불가 → 결제 단계 직행 안내문) |
| dateIso | string \| null | 여정 날짜 |
| reminders | Reminder[] | **paid 상태일 때만** 채워짐 (FR-13) |

### Reminder (FR-13)

| 필드 | 타입 | 예 |
| --- | --- | --- |
| atIso | string | `"2026-07-11T20:00:00"` |
| label | string | `"전날 저녁"`, `"당일 아침 (출발 2시간 전)"` |
| message | string | `"내일 6시 20분에 서울에서 출발해요. 표와 준비물을 미리 챙겨두세요."` |

---

## 3. 엔드포인트

### 3-1. `POST /api/v2/dialog/turn` — 대화 한 턴 (FR-2/3/4)

사용자 발화(또는 선택지 버튼 값)를 보내면, 슬롯을 추출·병합하고 다음 행동을 알려준다.

**요청**

| 필드 | 타입 | 필수 | 설명 |
| --- | --- | --- | --- |
| sessionId | string | ✅ | 대화 상태 키 |
| text | string | ✅ | 발화 텍스트 (STT 결과 포함) 또는 선택지의 `slot_value` |
| location | string | — | 위치 기반 출발지 기본값 (도시 목록 내 값일 때만 적용) |

**응답** — `next.type`으로 분기한다.

```ts
type DialogTurnResponse = {
  slots: Slots                  // 병합·기본값 적용된 현재 슬롯
  missing: ("departure"|"arrival"|"date")[]
  next: AskNext | ConfirmNext   // ↓
  askCount: number              // 되묻기 누적 횟수 — 3 이상이면 예외 UI 권장 (FR-3 토의사항)
  agent: AgentLine[]
}
type AskNext = {                // 빈 필수 슬롯이 있을 때
  type: "ask"
  question: string              // 그대로 표시
  options: { label: string; slot_value: string }[]  // 2~3개 버튼. 선택 시 slot_value를 다음 turn의 text로 전송
  target_slot: "departure"|"arrival"|"date"
}
type ConfirmNext = {            // 필수 슬롯 완성
  type: "confirm"
  summary: string               // "7월 14일 화요일 아침 / 대전 → 부산 / 어른 2명" — 확인 화면에 그대로 표시
}
```

**예시 ① 정보 부족 → 되묻기** (실측)

```json
// 요청
{ "sessionId": "s_a1b2c3", "text": "부산 한번 가보고 싶네" }
// 응답
{
  "slots": { "departure": null, "arrival": "부산", "date": null, "timeOfDay": "아침", "passengers": 1 },
  "missing": ["departure", "date"],
  "next": {
    "type": "ask",
    "question": "어디에서 출발하세요?",
    "options": [
      { "label": "서울 출발", "slot_value": "서울" },
      { "label": "대전 출발", "slot_value": "대전" },
      { "label": "동대구 출발", "slot_value": "동대구" }
    ],
    "target_slot": "departure"
  },
  "askCount": 1,
  "agent": [ { "tag": "NLU", "msg": "(anthropic) 슬롯 추출 → arrival=부산" }, { "tag": "ASK", "msg": "되묻기 #1 → departure" } ]
}
```

**예시 ② 완성 → 확인 요약** (실측)

```json
// 요청
{ "sessionId": "s_a1b2c3", "text": "다음 주 화요일 아침 서울에서 부산, 어른 두 명" }
// 응답
{
  "slots": { "departure": "서울", "arrival": "부산",
             "date": { "label": "7월 14일", "md": "7월 14일", "iso": "2026-07-14" },
             "timeOfDay": "아침", "passengers": 2 },
  "missing": [],
  "next": { "type": "confirm", "summary": "7월 14일 화요일 아침 / 서울 → 부산 / 어른 2명" },
  "askCount": 1,
  "agent": [ "..." ]
}
```

수정(FR-4 [고칠게요])은 별도 API 없이 **정정 발화를 다시 보내면 된다** — 새로 추출된 값이 기존 슬롯을 덮어쓴다 (예: `"대전에서 출발"`, `"모레"`, `"세 명"`).

### 3-2. `POST /api/v2/dialog/{sessionId}/reset` — 대화 초기화

응답: `{"ok": true}`. 슬롯·되묻기 카운트가 삭제된다.

### 3-3. `POST /api/v2/journeys/search` — 통합 검색 (FR-6/7/8)

**요청**

| 필드 | 타입 | 필수 | 설명 |
| --- | --- | --- | --- |
| sessionId | string | △ | 세션에 저장된 슬롯으로 검색 (`slots` 생략 시 필수) |
| slots | Slots | △ | 직접 지정 시 세션 대신 사용 |
| sim | SimOptions | — | §1-6 |

**응답**

```ts
type JourneySearchResponse = {
  journeys: Journey[]        // 예약 가능한 경로만, 최대 3개, 추천순 정렬
  excludedSources: string[]  // 장애로 제외된 수단 → "일부 교통편은 확인하지 못했어요" 고지 + 재검색 버튼 (FR-6 예외)
  recombined: boolean        // true면 직결 전량 매진 → 환승 대체 여정 (배지 표시 권장)
  agent: AgentLine[]
}
```

**예시** (실측, 일부 생략)

```json
{
  "journeys": [{
    "id": "jn_3f9c1a2b7d",
    "legs": [{ "mode": "KTX", "no": "KTX 421", "from": "서울", "to": "부산",
               "dep": 380, "arr": 535, "fare": 38300, "reservable": true }],
    "dep": 380, "arr": 535, "durationMin": 155, "totalFare": 38300,
    "transfers": 0, "transferWaitMin": null, "reservable": true,
    "explain": "갈아타지 않는 제일 빠른 차예요."
  }],
  "excludedSources": [],
  "recombined": false,
  "agent": [ "..." ]
}
```

에러: 400 `"필수 슬롯 미충족: [...]"` / 400 `"slots 또는 sessionId가 필요합니다."`

### 3-4. `POST /api/v2/holds` — 좌석 선점 (FR-10) 〔side_effect〕

**요청**

| 필드 | 타입 | 필수 | 설명 |
| --- | --- | --- | --- |
| sessionId | string | — | |
| journey | Journey | ✅ | 검색 응답의 객체를 **그대로** 전달 |
| passengers | int | — | 기본 1. `slots.passengers` 값을 넣을 것 |
| dateIso | string | — | `slots.date.iso` — **탑승 안내(FR-13) 계산에 필요하므로 반드시 전달 권장** |
| sim | SimOptions | — | `holdConflict`만 유효 |

**응답**: `HoldInfo` (status=`"held"`). `notices` 3개 문구와 `remainingSec` 카운트다운을 화면에 표시한다.
버스 구간이 있으면 `unreservableLegs`에 안내문이 온다 (버스는 예약 시스템이 없어 선점 없이 결제 직행 — 명세 5장).

**에러**: **409** `{"detail": "방금 자리가 나갔어요"}` — 경합 매진 (FR-10 예외).
프론트는 "다른 길을 찾아볼까요?" 동의를 받고 §3-3을 다시 호출한다.

### 3-5. `GET /api/v2/holds?sessionId=...` — 내 예매 목록 (FR-15)

응답: `{ holds: HoldInfo[], agent: AgentLine[] }` — 최신순.
`status:"held"`가 있으면 첫 화면 최상단에 "결제를 기다리는 표가 있어요 — N분 남았어요" 카드를 노출한다 (N = `remainingSec/60`).
기한이 지난 held는 서버가 조회 시점에 자동으로 `"expired"`로 바꿔 준다.

### 3-6. `GET /api/v2/holds/{holdId}` — 예매 상세

응답: `HoldInfo`. 404 가능.

### 3-7. `POST /api/v2/holds/{holdId}/pay-confirmed` — 결제 완료 확인 〔side_effect〕

결제 자체는 외부(코레일 앱·창구)에서 사용자가 직접 한다. 이 API는 **상태 전이만** 수행한다 (결제 자동화 금지 — FR-10).
응답: `HoldInfo` (status=`"paid"`, **reminders 채워짐**). 에러: 404 / 409 `"결제 확인 불가 상태: ..."`.

### 3-8. `POST /api/v2/holds/{holdId}/cancel` — 선점 취소 〔side_effect〕

응답: `HoldInfo` (status=`"cancelled"`). 404 가능.

### 3-9. `GET /api/stream/{sessionId}` — SSE 실시간 이벤트

`text/event-stream`. 각 이벤트의 `data`는 JSON:

```json
{ "type": "agent", "tag": "SEARCH", "msg": "통합 검색: 후보 12건 (서울 → 부산, 아침)" }
```

- `type`: `"agent"`(로그) 또는 `"standby"`(레거시 취소표 이벤트)
- 15초마다 keep-alive 주석(`: ping`)이 온다 — 무시하면 됨
- 사용 예: `new EventSource(\`${API}/api/stream/${sessionId}\`).onmessage = e => JSON.parse(e.data)`

### 3-10. `GET /health` — 상태 확인

```json
{ "ok": true, "service": "baro-ta-api(fastapi)", "llm_provider": "anthropic", "tool_mode": "mock" }
```

---

## 4. 선점 상태 전이

```text
             pay-confirmed          (FR-13 reminders 제공)
  held ────────────────────▶ paid
   │
   ├── cancel ─────────────▶ cancelled
   └── 결제 기한 경과 (자동) ─▶ expired     * 조회 시점에 판정됨
```

`paid / cancelled / expired`는 종결 상태 — 이후 pay-confirmed·cancel 호출은 409.

---

## 5. 레거시 API (`/api/*`) — 기존 React 데모 전용

v2 이전 계약. Express(:4000)와 FastAPI(:8000) 양쪽에 동일하게 존재하며 **신규 개발은 v2를 사용**한다.

| 메서드 | 경로 | 비고 |
| --- | --- | --- |
| POST | `/api/nlu/parse` | v2 dialog/turn의 전신 (되묻기 없음) |
| POST | `/api/routes/search` | 단일 수단 목록 (Journey 아님 — RouteOption) |
| GET | `/api/standby/{searchId}/check` | 취소표 폴링 |
| POST | `/api/bookings`, `/api/bookings/{id}/pay` | 모의 자동 예매 |
| GET | `/api/travel/suggest` | 숙소·투어 (실연동은 Express `myrealtrip.js`) |

---

## 6. 백엔드가 도구 팀원에게 기대하는 계약 (참고)

`TOOL_MODE=live`일 때 subprocess로 호출한다 (`app/tools/kskill.py`):

```bash
echo '{"origin":"서울","dest":"부산","arriveBy":840,"dateIso":"2026-07-14"}' \
  | k-skill run route-search --json
# stdout: 정규화된 결과 JSON, 성공 시 exit 0
```

실패(비정상 종료·타임아웃·JSON 아님) 시 서버가 cache → mock으로 폴백하므로 실패를 숨기지 말 것.

---

## 7. 변경 이력

| 날짜 | 내용 |
| --- | --- |
| 2026-07-11 | 최초 작성. v2 전 엔드포인트 + LLM 기본 모델 claude-haiku-4-5 반영 |
