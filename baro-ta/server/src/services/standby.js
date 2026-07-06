import { rand } from "../data.js";

/**
 * 취소표 조회 세션 (인메모리).
 * 클라이언트가 랜덤 주기로 check를 호출하면 서버가 좌석 상태를 응답한다.
 *
 * [실연동 교체 지점] 실제 서비스에서는 예매처 좌석 조회 API/스크래핑 결과를
 * 반환한다. 서버 부하 최소화(랜덤 주기)와 이용약관 준수는 클라이언트·서버
 * 양쪽에서 강제한다.
 */
const sessions = new Map();

export function checkSeat(searchId) {
  let s = sessions.get(searchId);
  if (!s) {
    s = { attempts: 0, target: rand(4, 6) }; // 시연: 4~6회째 조회에서 취소표 발견
    sessions.set(searchId, s);
  }
  s.attempts += 1;
  const available = s.attempts >= s.target;
  if (available) sessions.delete(searchId);
  return { attempt: s.attempts, available, remaining: available ? 1 : 0 };
}
