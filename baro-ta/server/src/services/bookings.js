import { fmtTime } from "../data.js";
import { cancelKorailReservation, korailCredsPresent, reserveKorailTrain } from "./korail.js";

/**
 * 자동 예매 파이프라인 (인메모리).
 *
 * 실시간 검색으로 나온 기차(route.id가 `_r*`)이고 코레일 계정(server/.env)이
 * 있으면 korail2로 **실제 예약(좌석 확보, 결제 전)**을 잡는다. 실패하면 기존
 * 시연용 모의 예매로 폴백한다. 결제는 항상 사용자 몫 — 데모 결제 시 실예약은
 * 기본적으로 자동 취소해 계정에 미결제 예약이 쌓이지 않게 한다
 * (유지하려면 KORAIL_KEEP_RESERVATION=1).
 */
export const BOOK_STEPS = [
  { title: "예매 페이지 접속", detail: "WebView로 예매 사이트 로드", ms: 1300 },
  { title: "열차·좌석 선택", detail: "잔여 좌석 확인 후 자동 선택", ms: 1700 },
  { title: "승객 정보 입력", detail: "저장된 프로필 자동 입력 (성인 1명)", ms: 1400 },
  { title: "결제 페이지 진입", detail: "여기까지 완료 후 자동화를 멈춥니다", ms: 1200 },
];

const bookings = new Map();

// 실시간 검색 결과로 만들어진 기차 경로만 실예약 대상 (모의 경로는 열차번호가 랜덤)
const isRealTrainRoute = (route) => route.cls !== "bus" && /_r\d+$/.test(route.id);

export async function createBooking({ route, params }) {
  const bookingId = `bk_${Math.random().toString(36).slice(2, 10)}`;
  const record = { route, params, paid: false, rsvId: null };
  bookings.set(bookingId, record);

  const agent = [{ tag: "AUTO", msg: `자동 예매 시작: ${route.no} (${fmtTime(route.dep)} 출발)` }];
  let seat = "07호차 11A (창측)"; // 모의 좌석 (실예약 성공 시 교체)

  if (korailCredsPresent() && isRealTrainRoute(route) && params.date?.iso && params.origin && params.dest) {
    try {
      const trainNo = route.no.split(" ").pop();
      const depTime = `${String(Math.floor(route.dep / 60)).padStart(2, "0")}${String(route.dep % 60).padStart(2, "0")}00`;
      const res = await reserveKorailTrain({
        origin: params.origin,
        dest: params.dest,
        date: params.date.iso.replaceAll("-", ""),
        trainNo,
        depTime,
      });
      const rsv = res.reservation ?? {};
      record.rsvId = rsv.rsv_id ?? null;
      if (rsv.seat_no) seat = `${rsv.srcar_no ? `${rsv.srcar_no}호차 ` : ""}${rsv.seat_no}`;
      agent.push({
        tag: "KORAIL",
        msg: `실제 예약 확보 — 예약번호 ${record.rsvId}${rsv.buy_limit_time ? `, 결제기한 ${String(rsv.buy_limit_time).slice(0, 2)}:${String(rsv.buy_limit_time).slice(2, 4)}` : ""}`,
      });
      agent.push({ tag: "SAFE", msg: "결제 전 상태로만 확보 — 미결제 시 코레일이 자동 취소" });
    } catch (e) {
      agent.push({ tag: "KORAIL", msg: `실예약 실패(${e.message.slice(0, 60)}) → 시연 모드 예매로 진행` });
    }
  }

  return {
    bookingId,
    steps: BOOK_STEPS,
    seat,
    agent,
  };
}

export async function payBooking(bookingId) {
  const b = bookings.get(bookingId);
  if (!b) return null;
  b.paid = true;
  const { route, params } = b;

  const agent = [
    { tag: "USER", msg: "사용자 결제 승인 → 예매 확정" },
    { tag: "DONE", msg: `예매 완료 · ${route.no} · ${route.price.toLocaleString("ko-KR")}원` },
  ];

  // 데모 결제는 실결제가 아니므로, 실예약이 있으면 계정 보호를 위해 자동 취소한다
  if (b.rsvId && process.env.KORAIL_KEEP_RESERVATION !== "1") {
    try {
      await cancelKorailReservation(b.rsvId);
      agent.push({ tag: "KORAIL", msg: `시연용 실예약 ${b.rsvId} 자동 취소 완료 (계정 보호)` });
    } catch (e) {
      agent.push({ tag: "KORAIL", msg: `실예약 자동 취소 실패 — 코레일톡에서 확인 필요 (${e.message.slice(0, 50)})` });
    }
  } else if (b.rsvId) {
    agent.push({ tag: "KORAIL", msg: `실예약 ${b.rsvId} 유지 중 — 코레일톡에서 결제 가능` });
  }

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
    agent,
  };
}
