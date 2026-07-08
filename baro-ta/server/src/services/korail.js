import { execFile } from "node:child_process";
import path from "node:path";
import { fileURLToPath } from "node:url";

/**
 * 코레일 실시간 조회 브리지 — py/korail_search.py(korail2-ncard)를 자식 프로세스로 호출한다.
 * venv가 없거나 조회가 실패하면 호출부(routes.js)가 모의 데이터로 폴백한다.
 */
const __dirname = path.dirname(fileURLToPath(import.meta.url));
const PY = path.resolve(__dirname, "../../py/.venv/bin/python");
const SCRIPT = path.resolve(__dirname, "../../py/korail_search.py");

// 한 번 실패하면 잠시 재시도하지 않는다 — 시연 중 검색마다 타임아웃을 기다리지 않도록
let deadUntil = 0;

export function korailAvailable() {
  return Date.now() >= deadUntil;
}

export function markKorailDead() {
  deadUntil = Date.now() + 120_000;
}

export function searchKorailTrains({ origin, dest, date, time }) {
  return new Promise((resolve, reject) => {
    execFile(PY, [SCRIPT, origin, dest, date, time], { timeout: 8000 }, (err, stdout, stderr) => {
      if (err) return reject(new Error((stderr || err.message).trim().slice(0, 200)));
      try {
        resolve(JSON.parse(stdout));
      } catch {
        reject(new Error("korail_search.py 출력 파싱 실패"));
      }
    });
  });
}
