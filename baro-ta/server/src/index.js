import express from "express";
import cors from "cors";
import apiRouter from "./routes/api.js";

// server/.env 로드 (코레일 계정 등 서버 전용 비밀) — 없으면 조용히 넘어간다
try {
  process.loadEnvFile();
} catch {
  /* .env 없음 — 조회 전용 모드 */
}

const app = express();
app.use(cors());
app.use(express.json());

app.use("/api", apiRouter);

app.get("/health", (_req, res) => res.json({ ok: true, service: "baro-ta-api" }));

const port = process.env.PORT || 4000;
app.listen(port, () => {
  console.log(`[baro-ta api] listening on http://localhost:${port}`);
});
