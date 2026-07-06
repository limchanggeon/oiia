import { useEffect, useRef } from "react";
import { useApp } from "../store";

export function AgentConsole() {
  const { state, actions } = useApp();
  const logRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const el = logRef.current;
    if (el) el.scrollTop = el.scrollHeight;
  }, [state.agentLog]);

  return (
    <footer className={`console${state.consoleOpen ? "" : " collapsed"}`}>
      <div className="c-head" onClick={actions.toggleConsole}>
        <span className="label">AI AGENT 내부 동작 로그</span>
        <span className="hint">NLU 추출 · 경로 스코어링 · 폴링 · 제어권 반환 이벤트</span>
        <span className="caret">{state.consoleOpen ? "▼ 접기" : "▲ 펼치기"}</span>
      </div>
      <div className="agent-log" ref={logRef} aria-live="polite">
        {state.agentLog.map((e, i) => (
          <div key={i}>
            <span className="t">[{e.t}]</span> <span className="tag">[{e.tag}]</span> {e.msg}
          </div>
        ))}
      </div>
    </footer>
  );
}
