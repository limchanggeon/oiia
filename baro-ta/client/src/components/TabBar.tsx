import { useApp } from "../store";

export function TabBar() {
  const { state, actions } = useApp();
  return (
    <nav className="tabbar">
      <button
        type="button"
        className={`tab-btn${state.view === "chat" ? " active" : ""}`}
        onClick={() => actions.setView("chat")}
      >
        <span className="t-ico">
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
            <path d="M21 15a2 2 0 0 1-2 2H8l-5 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z" />
          </svg>
        </span>
        AI 대화
      </button>
      <button
        type="button"
        className={`tab-btn${state.view === "stage" ? " active" : ""}`}
        onClick={() => actions.setView("stage")}
      >
        <span className="t-ico">
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
            <circle cx="6" cy="19" r="3" />
            <circle cx="18" cy="5" r="3" />
            <path d="M9 19h8.5a3.5 3.5 0 0 0 0-7h-11a3.5 3.5 0 0 1 0-7H15" />
          </svg>
        </span>
        진행 화면
      </button>
    </nav>
  );
}
