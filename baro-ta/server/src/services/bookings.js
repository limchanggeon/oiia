import { fmtTime } from "../data.js";

/**
 * 자동 예매 파이프라인 (인메모리).
 *
 * [실연동 교체 지점] 실제 서비스에서는 각 단계가 WebView/Intent 제어와
 * Vision 기반 화면 인식으로 수행된다. 결제 직전 단계에서 반드시 멈추고
 * 제어권을 사용자에게 반환한다.
 */
export const BOOK_STEPS = [
  { title: "예매 페이지 접속", detail: "WebView로 예매 사이트 로드", ms: 1300 },
  { title: "열차·좌석 선택", detail: "07호차 11A (창측) — Vision으로 화면 요소 인식", ms: 1700 },
  { title: "승객 정보 입력", detail: "저장된 프로필 자동 입력 (성인 1명)", ms: 1400 },
  { title: "결제 페이지 진입", detail: "여기까지 완료 후 자동화를 멈춥니다", ms: 1200 },
];

const bookings = new Map();

export function createBooking({ route, params }) {
  const bookingId = `bk_${Math.random().toString(36).slice(2, 10)}`;
  bookings.set(bookingId, { route, params, paid: false });
  return {
    bookingId,
    steps: BOOK_STEPS,
    seat: "07호차 11A (창측)",
    agent: [{ tag: "AUTO", msg: `자동 예매 시작: ${route.no} (${fmtTime(route.dep)} 출발)` }],
  };
}

export function payBooking(bookingId) {
  const b = bookings.get(bookingId);
  if (!b) return null;
  b.paid = true;
  const { route, params } = b;
  return {
    ticket: {
      mode: route.mode,
      no: route.no,
      origin: params.origin,
      dest: params.dest,
      depLabel: fmtTime(route.dep),
      arrLabel: fmtTime(route.arr),
      dateMd: params.date.md,
      seat: "07호차 11A",
      price: route.price,
    },
    agent: [
      { tag: "USER", msg: "사용자 결제 승인 → 예매 확정" },
      { tag: "DONE", msg: `예매 완료 · ${route.no} · ${route.price.toLocaleString("ko-KR")}원` },
    ],
  };
}
