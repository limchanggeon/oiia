import { DIST_MIN, MODES, rand } from "../data.js";

/**
 * 경로 후보 산출 + AI 적합도 스코어링.
 *
 * [실연동 교체 지점] 실제 서비스에서는 코레일/SRT/터미널 조회 결과를
 * 이 형태(RouteOption[])로 정규화해 반환한다.
 */
export function searchRoutes({ origin, dest, arriveBy }) {
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

  const minDur = Math.min(...list.map((r) => r.dur));
  for (const r of list) {
    const gap = T - r.arr;
    r.score = Math.round(Math.max(42, Math.min(99, 97 - gap * 0.45 - (r.dur - minDur) * 0.28)));
  }
  list.sort((a, b) => b.score - a.score);

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
