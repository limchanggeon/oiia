import { useApp } from "../store";

export function TopBar() {
  const { state, actions } = useApp();
  return (
    <header className="topbar">
      <div>
        <div className="logo">
          바로<em>타</em>
        </div>
        <div className="slogan">바로 찾고, 바로 타다 — AI Agent 길찾기&예매 원스톱</div>
      </div>
      <span className="demo-badge">2026 디지털 경진대회 · 팀 oiia · React + API 프로토타입</span>
      <div className="spacer" />
      <button className="icon-btn" aria-pressed={state.bigText} onClick={actions.toggleBig}>
        가 큰글씨
      </button>
      <button className="icon-btn" onClick={() => actions.resetAll(false)}>
        ↺ 처음부터
      </button>
    </header>
  );
}
