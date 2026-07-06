import { STATIONS, fmtTime } from "../data.js";

/**
 * 자연어에서 예매 필수 파라미터를 추출한다 (규칙 기반).
 *
 * [LLM 교체 지점] 실제 서비스에서는 이 함수 내부를 LLM 호출로 교체한다.
 * 반환 계약(부분 파라미터 객체)만 유지하면 클라이언트는 수정 없이 동작한다.
 */
export function parseIntent(text) {
  const got = {};

  for (const s of STATIONS) {
    if (new RegExp(`${s}(역)?\\s*(에서|출발)`).test(text)) got.origin = s;
    // "에(?!서)": "서울에서"의 '에'가 도착지 조사로 오인되지 않도록
    if (new RegExp(`${s}(역)?\\s*(까지|으로|로|에(?!서)|가|행|도착)`).test(text)) got.dest = s;
  }
  const mentioned = STATIONS.filter((s) => text.includes(s));
  if (got.dest && got.dest === got.origin) got.dest = mentioned.find((s) => s !== got.origin) || null;
  if (!got.dest && mentioned.length) got.dest = mentioned.find((s) => s !== got.origin) || null;
  if (/지금|현재\s*위치|여기서/.test(text)) got.origin = "서울";

  const today = new Date();
  // toISOString()은 UTC 기준이라 KST에서 하루 어긋난다 — 로컬 날짜로 조립
  const localIso = (d) =>
    `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`;
  const mkDate = (offset, label) => {
    const d = new Date(today);
    d.setDate(d.getDate() + offset);
    return {
      label,
      md: `${d.getMonth() + 1}월 ${d.getDate()}일`,
      iso: localIso(d),
    };
  };
  if (text.includes("오늘")) got.date = mkDate(0, "오늘");
  else if (text.includes("내일")) got.date = mkDate(1, "내일");
  else if (text.includes("모레")) got.date = mkDate(2, "모레");
  else {
    const m = text.match(/(\d{1,2})월\s*(\d{1,2})일/);
    if (m) {
      const d = new Date(today.getFullYear(), Number(m[1]) - 1, Number(m[2]));
      got.date = { label: `${m[1]}월 ${m[2]}일`, md: `${m[1]}월 ${m[2]}일`, iso: localIso(d) };
    }
  }

  // 시간 = 희망 도착 시각
  const tm = text.match(/(오전|오후|아침|저녁|밤)?\s*(\d{1,2})시\s*(반|(\d{1,2})분)?/) || text.match(/()(\d{1,2}):(\d{2})/);
  if (tm) {
    let h = parseInt(tm[2], 10);
    let mi = 0;
    if (tm[3] === "반") mi = 30;
    else if (tm[4]) mi = parseInt(tm[4], 10);
    else if (tm[3] && /^\d+$/.test(tm[3])) mi = parseInt(tm[3], 10);
    const mer = tm[1] || "";
    if ((mer === "오후" || mer === "저녁" || mer === "밤") && h < 12) h += 12;
    if (!mer && h <= 8) h += 12; // 모호하면 낮 시간대로 해석
    got.time = { min: h * 60 + mi, label: fmtTime(h * 60 + mi) };
  }

  return got;
}
