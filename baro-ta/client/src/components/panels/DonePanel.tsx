import { useEffect, useRef, useState } from "react";
import { api } from "../../api";
import { useApp } from "../../store";
import { fmtWon, rand } from "../../utils";
import type { TravelCard, TravelSuggestResponse } from "../../types";

function CardRow({ cards }: { cards: TravelCard[] }) {
  return (
    <div className="sg-grid">
      {cards.map((c) => (
        <a key={c.url} className="sg-card" href={c.url} target="_blank" rel="noreferrer">
          {c.img && <img src={c.img} alt="" loading="lazy" />}
          <b>{c.name}</b>
          <span>{[c.rating, c.price].filter(Boolean).join(" · ")}</span>
        </a>
      ))}
    </div>
  );
}

export function DonePanel() {
  const { state, actions } = useApp();
  const { ticket } = state;
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const [suggest, setSuggest] = useState<TravelSuggestResponse | null>(null);
  const dest = state.params.dest;
  const dateIso = state.params.date?.iso;

  // 예매 완료 후 도착지 숙소·즐길거리 추천 (실패 시 조용히 생략 — 필수 요소 아님)
  useEffect(() => {
    if (!ticket || !dest || !dateIso) return;
    let alive = true;
    api
      .travelSuggest(dest, dateIso)
      .then((res) => {
        if (!alive) return;
        setSuggest(res);
        res.agent.forEach((l) => actions.log(l.tag, l.msg));
      })
      .catch(() => {});
    return () => {
      alive = false;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [ticket, dest, dateIso]);

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
        {suggest && (suggest.stays.length > 0 || suggest.tnas.length > 0) && (
          <div className="suggest">
            <div className="sg-head">
              {dest} 여행, 이어서 준비할까요?
              <span>마이리얼트립 실시간 검색</span>
            </div>
            {suggest.stays.length > 0 && (
              <>
                <div className="sg-label">숙소</div>
                <CardRow cards={suggest.stays} />
              </>
            )}
            {suggest.tnas.length > 0 && (
              <>
                <div className="sg-label">관광 · 즐길거리</div>
                <CardRow cards={suggest.tnas} />
              </>
            )}
          </div>
        )}
        <div style={{ height: 16 }} />
        <button type="button" className="cta ghost" onClick={() => actions.resetAll(false)}>
          처음 화면으로
        </button>
      </div>
    </div>
  );
}
