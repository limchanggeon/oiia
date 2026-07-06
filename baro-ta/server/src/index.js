import express from "express";
import cors from "cors";
import apiRouter from "./routes/api.js";

const app = express();
app.use(cors());
app.use(express.json());

app.use("/api", apiRouter);

app.get("/health", (_req, res) => res.json({ ok: true, service: "baro-ta-api" }));

const port = process.env.PORT || 4000;
app.listen(port, () => {
  console.log(`[baro-ta api] listening on http://localhost:${port}`);
});
