import { useApp } from "../../store";
import { fmtTime, fmtWon } from "../../utils";

export function RoutesPanel() {
  const { state, actions } = useApp();
  const { params, routes } = state;

  return (
    <div className="panel active">
      <h2>AI 추천 경로</h2>
      <p className="sub">적합도는 희망 도착시각과의 시간차 · 소요시간 · 매진 여부를 종합해 산출합니다.</p>

      <div className="search-strip">
        <div className="seg">
          <span>구간</span>
          <b>
            {params.origin} → {params.dest}
          </b>
        </div>
        <div className="divider" />
        <div className="seg">
          <span>날짜</span>
          <b>
            {params.date?.md} ({params.date?.label})
          </b>
        </div>
        <div className="divider" />
        <div className="seg">
          <span>희망 도착</span>
          <b>{params.time?.label} 까지</b>
        </div>
      </div>

      {routes.map((r, idx) => (
        <div className={`route-row${idx === 0 ? " best" : ""}`} key={r.id}>
          <div className="col-mode">
            <span className={`mode-tag ${r.cls}`}>{r.mode}</span>
            <div className="no">{r.no}</div>
          </div>
          <div className="col-time">
            <span className="t">{fmtTime(r.dep)}</span>
            <span className="arrow">→</span>
            <span className="t">{fmtTime(r.arr)}</span>
            <div className="badges">
              {idx === 0 && <span className="badge-ai">AI 추천 1위</span>}
              {r.soldOut ? <span className="badge-sold">매진</span> : <span className="badge-seat">좌석 있음</span>}
            </div>
          </div>
          <div className="col-dur">
            {Math.floor(r.dur / 60)}시간 {r.dur % 60}분
          </div>
          <div className="col-price">
            <b>{fmtWon(r.price)}</b>
          </div>
          <div className="col-fit">
            <div className="score">적합도 {r.score}점</div>
            <button
              type="button"
              className={`route-btn ${r.soldOut ? "standby" : "book"}`}
              onClick={() => actions.selectRoute(r)}
            >
              {r.soldOut ? "취소표 자동 조회" : "바로 자동 예매"}
            </button>
          </div>
          {r.reason && <div className="route-why">{r.reason}</div>}
        </div>
      ))}
    </div>
  );
}
