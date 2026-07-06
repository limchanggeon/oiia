import { useState } from "react";
import { useApp } from "../../store";
import { fmtTime, fmtWon } from "../../utils";

export function PaymentPanel() {
  const { state, actions } = useApp();
  const { chosen, params, booking } = state;
  const [busy, setBusy] = useState(false);
  if (!chosen) return null;

  const onPay = async () => {
    setBusy(true);
    await actions.pay();
    setBusy(false);
  };

  return (
    <div className="panel active">
      <h2>결제하기</h2>
      <p className="sub">지금부터는 사용자가 직접 진행하는 단계입니다.</p>
      <div className="pay-grid">
        <div className="manual-note">
          자동화 종료 — 접근성 서비스가 해제되었어요. 아래 내용을 확인하고 직접 결제해 주세요.
        </div>
        <div className="pay-summary">
          <div className="row">
            <span className="k">열차</span>
            <span>{chosen.no}</span>
          </div>
          <div className="row">
            <span className="k">구간</span>
            <span>
              {params.origin} → {params.dest}
            </span>
          </div>
          <div className="row">
            <span className="k">일시</span>
            <span>
              {params.date?.md} {fmtTime(chosen.dep)} 출발
            </span>
          </div>
          <div className="row">
            <span className="k">좌석</span>
            <span>{booking?.seat ?? "07호차 11A (창측)"} · 성인 1명</span>
          </div>
          <div className="row total">
            <span className="k">결제 금액</span>
            <span>{fmtWon(chosen.price)}</span>
          </div>
        </div>
        <div>
          <div className="pay-methods">
            <label className="pay-method">
              <input type="radio" name="pay" defaultChecked /> 신용·체크카드
            </label>
            <label className="pay-method">
              <input type="radio" name="pay" /> 간편결제 (카카오페이·네이버페이)
            </label>
            <label className="pay-method">
              <input type="radio" name="pay" /> 휴대폰 결제
            </label>
          </div>
          <div style={{ height: 14 }} />
          <button type="button" className="cta wide" onClick={onPay} disabled={busy}>
            {busy ? "결제 처리 중…" : "결제하기"}
          </button>
        </div>
      </div>
    </div>
  );
}
