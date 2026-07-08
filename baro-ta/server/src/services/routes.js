import { DIST_MIN, MODES, rand } from "../data.js";
import { korailAvailable, markKorailDead, searchKorailTrains } from "./korail.js";
import { kobusAvailable, kobusSupported, markKobusDead, searchKobusBuses } from "./kobus.js";

/**
 * 경로 후보 산출 + AI 적합도 스코어링.
 *
 * 코레일 실시간 조회(korail2)를 먼저 시도하고, 실패·0건이면 모의 데이터로
 * 폴백한다. 반환 계약(RouteOption[])은 동일해 클라이언트는 어느 쪽이든 무수정.
 */
export async function searchRoutes({ origin, dest, arriveBy, dateIso }) {
  if (korailAvailable()) {
    try {
      const real = await realRoutes({ origin, dest, arriveBy, dateIso });
      if (real.routes.length) return real;
      const mock = mockRoutes({ origin, dest, arriveBy });
      mock.agent.unshift({ tag: "KORAIL", msg: "실시간 조회 결과가 조건에 없음 → 모의 데이터로 시연" });
      return mock;
    } catch (e) {
      markKorailDead();
      const mock = mockRoutes({ origin, dest, arriveBy });
      mock.agent.unshift({ tag: "KORAIL", msg: `실시간 조회 실패 → 모의 데이터 폴백 (${e.message})` });
      return mock;
    }
  }
  // 최근 실패로 재시도 억제 중 — 상태가 보이지 않으면 디버깅이 어려우니 로그로 남긴다
  const mock = mockRoutes({ origin, dest, arriveBy });
  mock.agent.unshift({ tag: "KORAIL", msg: "최근 실시간 조회 실패 → 잠시 모의 데이터로 동작 (2분 후 자동 재시도)" });
  return mock;
}

// 적합도: 희망 도착시각 대비 여유·소요시간 종합 (실데이터/모의 공용)
function applyScores(list, T) {
  if (!list.length) return;
  const minDur = Math.min(...list.map((r) => r.dur));
  for (const r of list) {
    const gap = T - r.arr;
    r.score = Math.round(Math.max(42, Math.min(99, 97 - gap * 0.45 - (r.dur - minDur) * 0.28)));
  }
  list.sort((a, b) => b.score - a.score);
}

function localIsoTomorrow() {
  const d = new Date();
  d.setDate(d.getDate() + 1);
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`;
}

// 버스 등급별 요금 추정 (시간표에 요금이 노출되지 않는 등급용) — 거리(분) 비례
const BUS_FARE_PER_MIN = { 고속: 170, 우등: 250, 심야고속: 190, 심야우등: 275, 프리미엄: 330 };

async function realRoutes({ origin, dest, arriveBy, dateIso }) {
  const T = arriveBy;
  const date = (dateIso || localIsoTomorrow()).replaceAll("-", "");
  // 희망 도착 5시간 전부터 조회해 T 이전 도착 열차를 확보한다
  const startMin = Math.max(0, T - 300);
  const time = `${String(Math.floor(startMin / 60)).padStart(2, "0")}${String(startMin % 60).padStart(2, "0")}00`;

  const wantBus = kobusSupported(origin, dest) && kobusAvailable();
  const [trainsRes, busesRes] = await Promise.allSettled([
    searchKorailTrains({ origin, dest, date, time }),
    wantBus ? searchKobusBuses({ origin, dest, date }) : Promise.resolve([]),
  ]);
  // 기차 조회 실패는 전체 폴백 사유, 버스 실패는 기차만으로 진행
  if (trainsRes.status === "rejected") throw trainsRes.reason;
  const trains = trainsRes.value;
  const buses = busesRes.status === "fulfilled" ? busesRes.value : [];
  if (busesRes.status === "rejected") markKobusDead();

  const usableTrains = trains
    .filter((t) => t.arrDate === date && t.arrMin <= T)
    .map((t, i) => ({
      id: `rt_${Date.now().toString(36)}_r${i}`,
      mode: t.mode,
      cls: "",
      no: t.no,
      dep: t.depMin,
      arr: t.arrMin,
      dur: t.arrMin - t.depMin,
      // 코레일 응답에 가격이 없는 편성은 거리 기반으로 추정
      price: t.price ?? (DIST_MIN[dest] || 120) * 320,
      soldOut: t.soldOut,
    }));

  // KOBUS 시간표에는 도착시각이 없어 소요시간을 거리 기반으로 추정한다
  const busDur = Math.round(((DIST_MIN[dest] || 120) * 1.7) / 5) * 5;
  const usableBuses = buses
    .map((b, i) => ({
      id: `rt_${Date.now().toString(36)}_b${i}`,
      mode: "고속버스",
      cls: "bus",
      no: `${b.company ?? "고속버스"} ${b.busClass}`,
      dep: b.depMin,
      arr: b.depMin + busDur,
      dur: busDur,
      price: b.fare ?? (DIST_MIN[dest] || 120) * (BUS_FARE_PER_MIN[b.busClass] ?? 170),
      soldOut: b.soldOut,
    }))
    .filter((b) => b.arr <= T && b.arr >= T - 360);

  // 희망 도착시각에 가까운 순으로 기차 4 + 버스 2를 스코어링
  usableTrains.sort((a, b) => b.arr - a.arr);
  usableBuses.sort((a, b) => b.arr - a.arr);
  const list = [...usableTrains.slice(0, 4), ...usableBuses.slice(0, 2)];
  applyScores(list, T);

  // 시연 리허설용: 매진 열차가 없어도 취소표 흐름을 보여주고 싶을 때 켠다
  if (process.env.FORCE_STANDBY_DEMO === "1" && list[0]) list[0].soldOut = true;

  if (list[0]) {
    list[0].reason = `희망 도착시각 대비 여유 ${T - list[0].arr}분 — 코레일 실시간 좌석 기준 1위예요.${
      list[0].soldOut ? " 매진이지만 취소표 확보 확률이 높아요." : ""
    }`;
  }

  const agent = [
    { tag: "KORAIL", msg: `코레일 실시간 조회 ${trains.length}건 → 조건 부합 ${usableTrains.length}건 (${origin} → ${dest}, ${date})` },
  ];
  if (wantBus) {
    agent.push(
      busesRes.status === "fulfilled"
        ? { tag: "KOBUS", msg: `고속버스 시간표 ${buses.length}건 → 조건 부합 ${usableBuses.length}건` }
        : { tag: "KOBUS", msg: "고속버스 조회 실패 → 기차만으로 진행" }
    );
  }
  agent.push(...list.map((r) => ({ tag: "SCORE", msg: `${r.no} 적합도 ${r.score}점${r.soldOut ? " · 매진" : ""}` })));
  if (list[0]?.soldOut) agent.push({ tag: "AI", msg: "1위 경로 매진 감지 → 취소표 자동 조회 제안" });

  return { routes: list, agent };
}

function mockRoutes({ origin, dest, arriveBy }) {
  const T = arriveBy;
  const base = DIST_MIN[dest] || 120;
  const offsets = [8, 22, 47, 15, 5]; // 희망 도착시각 대비 여유(분)

  const list = MODES.map((m, i) => {
    const dur = Math.round((base * m.factor) / 5) * 5;
    const arr = T - offsets[i];
    return {
      id: `rt_${Date.now().toString(36)}_${i}`,
      mode: m.mode,
      cls: m.cls,
      no: m.mode === "고속버스" ? `우등 ${rand(11, 89)}회` : `${m.mode} ${rand(101, 899)}`,
      dep: arr - dur,
      arr,
      dur,
      price: m.basePrice * 100 + rand(0, 9) * 100,
      soldOut: false,
    };
  });

  applyScores(list, T);

  // 시연 시나리오: 최적 경로가 매진 → 취소표 자동화 흐름을 보여준다
  list[0].soldOut = true;
  if (list.length > 3) list[3].soldOut = true;
  list[0].reason = `희망 도착시각 대비 여유 ${T - list[0].arr}분, 최단 소요라 1위예요. 매진이지만 취소표 확보 확률이 높아요.`;

  const agent = [
    { tag: "ROUTE", msg: `경로 후보 ${list.length}건 산출 (${origin} → ${dest})` },
    ...list.map((r) => ({ tag: "SCORE", msg: `${r.no} 적합도 ${r.score}점${r.soldOut ? " · 매진" : ""}` })),
    { tag: "AI", msg: "1위 경로 매진 감지 → 취소표 자동 조회 제안" },
  ];

  return { routes: list, agent };
}
