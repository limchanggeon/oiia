import { useEffect, useRef } from "react";
import { useApp } from "../../store";
import { fmtTime, rand } from "../../utils";

export function StandbyPanel() {
  const { state, actions } = useApp();
  const { chosen, params, pollLog, standbyFound } = state;
  const searchIdRef = useRef(`sb_${Math.random().toString(36).slice(2, 10)}`);
  const attempts = pollLog.length;

  // 랜덤 주기 폴링 (시연용 배속 1.2~2.6초 — 실서비스 2~5초)
  useEffect(() => {
    if (standbyFound) return;
    let timer = 0;
    let stopped = false;
    const tick = async () => {
      if (stopped) return;
      const found = await actions.standbyAttempt(searchIdRef.current).catch(() => false);
      if (!stopped && !found) timer = window.setTimeout(tick, rand(1200, 2600));
    };
    timer = window.setTimeout(tick, 900);
    return () => {
      stopped = true;
      window.clearTimeout(timer);
    };
  }, [standbyFound, actions]);

  if (!chosen) return null;

  return (
    <div className="panel active">
      <h2>취소표 자동 조회 중</h2>
      <p className="sub">
        {chosen.no} · {fmtTime(chosen.dep)} 출발 · {params.date?.md} — 자리가 나는 즉시 자동 예매로 전환합니다.
      </p>
      <div className="standby-grid">
        <div className="radar-card">
          <div className={`radar${standbyFound ? " found" : ""}`}>
            <div style={{ textAlign: "center" }}>
              <div className="count">{standbyFound ? "1석" : attempts}</div>
              <div className="cap">{standbyFound ? "잔여석 발견" : "조회 횟수"}</div>
            </div>
          </div>
          <div className="poll-status">{standbyFound ? "취소표가 나왔어요!" : "좌석 상태를 확인하고 있어요"}</div>
          <p className="poll-note">
            랜덤 주기(2~5초) 조회로 서버 부하를 최소화하고
            <br />
            이용약관 준수 범위에서 동작합니다.
          </p>
        </div>
        <div className="poll-log">
          {pollLog.map((e) => (
            <div className="row" key={e.n}>
              <span>
                #{e.n} 좌석 조회 · {e.t}
              </span>
              {e.found ? <span className="r-found">잔여석 발견!</span> : <span className="r-sold">매진</span>}
            </div>
          ))}
        </div>
        {standbyFound && (
          <div className="found-banner">
            <span>{chosen.no} 잔여석 확보 가능 — 자동 예매를 시작할까요?</span>
            <button type="button" className="cta-inline" onClick={actions.startBooking}>
              자동 예매 시작
            </button>
          </div>
        )}
      </div>
    </div>
  );
}
