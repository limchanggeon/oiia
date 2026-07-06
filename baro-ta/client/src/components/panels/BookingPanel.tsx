import { useApp } from "../../store";

export function BookingPanel() {
  const { state, actions } = useApp();
  const { booking, stepIndex, handoff } = state;
  if (!booking) return null;

  return (
    <div className="panel active">
      <h2>자동 예매 진행</h2>
      <p className="sub">AI가 결제 직전 단계까지 대신 진행합니다. 각 단계는 Vision 기반 화면 인식으로 검증돼요.</p>
      <div className="steps">
        {booking.steps.map((s, i) => {
          const status = i < stepIndex ? "done" : i === stepIndex ? "doing" : "";
          return (
            <div className={`step ${status}`} key={s.title}>
              <div className="st-icon">{i < stepIndex ? "✓" : i === stepIndex ? <span className="spinner" /> : i + 1}</div>
              <div>
                <b>{s.title}</b>
                <span>{s.detail}</span>
              </div>
            </div>
          );
        })}
      </div>
      {handoff && (
        <div className="handoff">
          <h3>여기서부터는 직접 진행하세요</h3>
          <p>
            결제 직전까지 준비를 마쳤어요. 개인정보·결제 보호를 위해 자동화(접근성 서비스)를 해제했습니다. 최종 결제는
            항상 사용자의 몫이에요.
          </p>
          <button type="button" className="cta" onClick={actions.goPayment}>
            결제 화면으로 이동
          </button>
        </div>
      )}
    </div>
  );
}
