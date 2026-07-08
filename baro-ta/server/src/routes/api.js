import { Router } from "express";
import { parseIntent } from "../services/nlu.js";
import { searchRoutes } from "../services/routes.js";
import { checkSeat } from "../services/standby.js";
import { createBooking, payBooking } from "../services/bookings.js";
import { suggestTravel } from "../services/myrealtrip.js";

const router = Router();

// 자연어 → 필수 파라미터 추출
router.post("/nlu/parse", (req, res) => {
  const { text } = req.body || {};
  if (typeof text !== "string" || !text.trim()) {
    return res.status(400).json({ error: "text가 필요합니다." });
  }
  const got = parseIntent(text);
  const found = Object.entries(got)
    .filter(([, v]) => v != null)
    .map(([k, v]) =>
      k === "origin" ? `출발지=${v}` : k === "dest" ? `도착지=${v}` : k === "date" ? `날짜=${v.md}` : `도착시각=${v.label}`
    );
  res.json({
    got,
    agent: found.length ? [{ tag: "NLU", msg: `파라미터 추출 → ${found.join(", ")}` }] : [],
  });
});

// 경로 후보 검색 + AI 스코어링 (코레일 실시간 조회 → 실패 시 모의 데이터)
router.post("/routes/search", async (req, res) => {
  const { origin, dest, arriveBy, dateIso } = req.body || {};
  if (!origin || !dest || typeof arriveBy !== "number") {
    return res.status(400).json({ error: "origin, dest, arriveBy(분)가 필요합니다." });
  }
  try {
    res.json(await searchRoutes({ origin, dest, arriveBy, dateIso }));
  } catch (e) {
    res.status(500).json({ error: `경로 검색 실패: ${e.message}` });
  }
});

// 취소표 좌석 조회 (클라이언트가 랜덤 주기로 호출)
router.get("/standby/:searchId/check", (req, res) => {
  res.json(checkSeat(req.params.searchId));
});

// 자동 예매 시작 (결제 직전까지)
router.post("/bookings", (req, res) => {
  const { route, params } = req.body || {};
  if (!route || !params) return res.status(400).json({ error: "route, params가 필요합니다." });
  res.json(createBooking({ route, params }));
});

// 도착지 숙소·투어 추천 (마이리얼트립 공식 MCP, 조회 전용)
router.get("/travel/suggest", async (req, res) => {
  const { dest, checkIn } = req.query;
  if (!dest || !/^\d{4}-\d{2}-\d{2}$/.test(checkIn || "")) {
    return res.status(400).json({ error: "dest, checkIn(YYYY-MM-DD)이 필요합니다." });
  }
  const d = new Date(`${checkIn}T00:00:00`);
  d.setDate(d.getDate() + 1);
  const checkOut = `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`;
  const { stays, tnas } = await suggestTravel({ dest, checkIn, checkOut });
  res.json({
    stays,
    tnas,
    agent: [{ tag: "MRT", msg: `마이리얼트립 실시간 검색 — ${dest} 숙소 ${stays.length}건 · 즐길거리 ${tnas.length}건` }],
  });
});

// 결제 확정 (사용자 제어 단계)
router.post("/bookings/:id/pay", (req, res) => {
  const result = payBooking(req.params.id);
  if (!result) return res.status(404).json({ error: "예매를 찾을 수 없습니다." });
  res.json(result);
});

export default router;
