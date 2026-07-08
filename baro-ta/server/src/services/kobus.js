import { execFile } from "node:child_process";
import path from "node:path";
import { fileURLToPath } from "node:url";

/**
 * KOBUS 고속버스 시간표 브리지 — py/kobus_search.py를 자식 프로세스로 호출한다.
 * 실패하면 호출부가 버스 없이(기차만) 진행한다.
 */
const __dirname = path.dirname(fileURLToPath(import.meta.url));
const PY = path.resolve(__dirname, "../../py/.venv/bin/python");
const SCRIPT = path.resolve(__dirname, "../../py/kobus_search.py");

// KOBUS 터미널 코드 — 문서·실조회로 확인된 것만. 추가하려면 kobus.co.kr
// 노선 조회(/mrs/readRotLinInf.ajax)에서 코드를 확인해 넣는다.
const TERMINAL_CODES = {
  서울: "010", // 서울경부(고속터미널)
  부산: "700",
  광주송정: "500", // 광주(유·스퀘어)
};

export function kobusSupported(origin, dest) {
  return Boolean(TERMINAL_CODES[origin] && TERMINAL_CODES[dest]);
}

let deadUntil = 0;

export function kobusAvailable() {
  return Date.now() >= deadUntil;
}

export function markKobusDead() {
  deadUntil = Date.now() + 120_000;
}

export function searchKobusBuses({ origin, dest, date }) {
  return new Promise((resolve, reject) => {
    execFile(
      PY,
      [SCRIPT, TERMINAL_CODES[origin], TERMINAL_CODES[dest], date],
      { timeout: 10000 },
      (err, stdout, stderr) => {
        if (err) return reject(new Error((stderr || err.message).trim().slice(0, 200)));
        try {
          resolve(JSON.parse(stdout));
        } catch {
          reject(new Error("kobus_search.py 출력 파싱 실패"));
        }
      }
    );
  });
}
