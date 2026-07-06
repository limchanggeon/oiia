import { Fragment } from "react";
import { phaseOf, useApp } from "../store";

const PHASES = [
  { n: 1, label: "요청 입력" },
  { n: 2, label: "AI 경로 추천" },
  { n: 3, label: "취소표 확보" },
  { n: 4, label: "예매 · 결제" },
];

export function PhaseBar() {
  const { state } = useApp();
  const current = phaseOf(state.panel);
  return (
    <div className="phasebar">
      {PHASES.map((p, i) => (
        <Fragment key={p.n}>
          {i > 0 && <div className="phase-link" />}
          <div className={`phase${p.n < current ? " done" : ""}${p.n === current ? " current" : ""}`}>
            <div className="p-dot">{p.n < current ? "✓" : p.n}</div>
            <div className="p-label">{p.label}</div>
          </div>
        </Fragment>
      ))}
    </div>
  );
}
