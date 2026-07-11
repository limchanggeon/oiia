# 바로타 (baro-ta)

AI Agent 기반 길찾기&예매 원스톱 서비스 — 2026 디지털 경진대회 SW부문, 팀 oiia.

React 프론트엔드 + Express API 백엔드 구조의 웹 프로토타입입니다.
지도(네이버지도)·기차(코레일)·고속버스(KOBUS)·숙박/관광(마이리얼트립)은 실데이터로 동작하며,
실패 시 모의 데이터로 자동 폴백합니다 — 상세 구조·설정·시연 가이드는 [ARCHITECTURE.md](ARCHITECTURE.md) 참고.

## 실행 방법

```bash
npm install   # 최초 1회 (client/server 모두 설치됨)
npm run dev   # 백엔드(4000) + 프론트(5173) 동시 실행
```

브라우저에서 http://localhost:5173 접속.
`http://localhost:5173/?demo` 로 열면 시연 시나리오(서울→부산)가 자동 재생됩니다.

## 구조

```
baro-ta/
├─ client/                  # Vite + React + TypeScript
│  └─ src/
│     ├─ store.tsx          # 앱 상태(리듀서) + 대화 플로우 컨트롤러
│     ├─ api.ts             # 백엔드 API 클라이언트 (VITE_API_URL로 배포 주소 지정)
│     ├─ components/        # TopBar · ChatRail · PhaseBar · TabBar · AgentConsole
│     └─ components/panels/ # Welcome → Routes → Standby → Booking → Payment → Done
├─ server/                  # Express (ESM) — 초기 프로토타입 백엔드
│  └─ src/
│     ├─ routes/api.js      # REST 엔드포인트
│     └─ services/          # nlu · routes · standby · bookings
└─ backend/                 # FastAPI 오케스트레이터 (본 구현 — backend/README.md 참고)
   └─ app/                  # LLM(rule/Claude/Ollama) · SQLite(WAL) · SSE · 승인 게이트 · k-skill 어댑터
```

Express와 FastAPI는 **같은 REST 계약**을 구현한다 — 클라이언트는 `VITE_API_URL`로
어느 쪽이든 선택할 수 있다 (Express :4000, FastAPI :8000). 플로우차트 기준 목표 백엔드는
FastAPI이며, 팀 통합 가이드(SSE·k-skill CLI 계약·LLM 스위칭)는 `backend/README.md`에 있다.

## API

| 메서드 | 경로 | 설명 |
| --- | --- | --- |
| POST | `/api/nlu/parse` | 자연어 → 출발지·도착지·날짜·희망 도착시각 추출 |
| POST | `/api/routes/search` | 경로 후보 산출 + AI 적합도 스코어링 |
| GET | `/api/standby/:searchId/check` | 취소표 좌석 조회 (클라이언트가 랜덤 주기로 호출) |
| POST | `/api/bookings` | 자동 예매 시작 (결제 직전 단계까지) |
| POST | `/api/bookings/:id/pay` | 결제 확정 (사용자 제어 단계) |

응답의 `agent` 배열은 화면 하단 "AI AGENT 내부 동작 로그"에 표시됩니다.

## 실서비스 교체 지점

- `server/src/services/nlu.js` — 규칙 기반 파서를 LLM 호출로 교체 (반환 계약 유지)
- `server/src/services/routes.js` — 모의 경로를 코레일/SRT/터미널 조회 결과로 교체
- `server/src/services/standby.js` — 좌석 조회 실연동 (랜덤 주기·약관 준수 유지)
- `server/src/services/bookings.js` — WebView/Intent + Vision 자동화 파이프라인 연동
- 인메모리 저장소(standby/bookings) → DB로 교체

## 참고

- 단일 파일 프로토타입(발표용): `../prototypes/baro-ta-web.html`(데스크탑), `../prototypes/baro-ta-prototype.html`(모바일 프레임)
- 자동 예매는 항상 **결제 직전에 멈추고 제어권을 사용자에게 반환**하는 것이 서비스 원칙입니다.
