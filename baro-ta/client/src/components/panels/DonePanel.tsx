import { useEffect, useRef } from "react";
import { useApp } from "../../store";
import { fmtWon, rand } from "../../utils";

export function DonePanel() {
  const { state, actions } = useApp();
  const { ticket } = state;
  const canvasRef = useRef<HTMLCanvasElement>(null);

  useEffect(() => {
    const cv = canvasRef.current;
    if (!cv) return;
    const ctx = cv.getContext("2d");
    if (!ctx) return;
    ctx.clearRect(0, 0, cv.width, cv.height);
    ctx.fillStyle = "#182420";
    let x = 10;
    while (x < cv.width - 10) {
      const w = rand(2, 9);
      if (rand(0, 2)) ctx.fillRect(x, 8, w, cv.height - 16);
      x += w + rand(2, 6);
    }
  }, [ticket]);

  if (!ticket) return null;

  return (
    <div className="panel active">
      <div className="done-wrap">
        <div className="big">예매 완료!</div>
        <p className="desc">취소표 확보부터 예매까지, 바로타가 함께했어요. ({fmtWon(ticket.price)})</p>
        <div className="ticket">
          <div className="t-head">
            <b>승차권</b>
            <span>바로타 · {ticket.mode}</span>
          </div>
          <div className="t-body">
            <div className="t-route">
              <div className="stn">
                <b>{ticket.origin}</b>
                <span>{ticket.depLabel}</span>
              </div>
              <div className="line" />
              <div className="stn">
                <b>{ticket.dest}</b>
                <span>{ticket.arrLabel}</span>
              </div>
            </div>
            <div className="t-grid">
              <div>
                <span>날짜</span>
                <b>{ticket.dateMd}</b>
              </div>
              <div>
                <span>열차</span>
                <b>{ticket.no}</b>
              </div>
              <div>
                <span>좌석</span>
                <b>{ticket.seat}</b>
              </div>
            </div>
            <canvas ref={canvasRef} width={640} height={108} aria-label="승차권 바코드(모의)" />
          </div>
        </div>
        <div style={{ height: 16 }} />
        <button type="button" className="cta ghost" onClick={() => actions.resetAll(false)}>
          처음 화면으로
        </button>
      </div>
    </div>
  );
}
