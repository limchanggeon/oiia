import { SAMPLE_SENTENCES, useApp } from "../../store";

const FLOW = [
  { title: "AI 대화형 입력", desc: "챗봇이 출발지·도착지·도착 일시를 유도·추출" },
  { title: "최적 경로 추천", desc: "소요시간·매진 여부·도착 시간차 기반 적합도 산출" },
  { title: "취소표 자동 조회", desc: "랜덤 주기 조회 — 서버 부하 최소화, 약관 준수" },
  { title: "제어권 반환", desc: "자동화는 결제 직전까지 — 최종 결정은 사용자" },
];

export function WelcomePanel() {
  const { actions } = useApp();
  return (
    <div className="panel active">
      <h2>기차·버스 예매, 대화 한 번이면 끝나요</h2>
      <p className="sub">
        왼쪽 채팅창에 목적지와 도착 시간을 말하듯 입력하세요. 매진이어도 취소표를 자동으로 확보해 드립니다.
      </p>
      <div className="welcome-grid">
        {FLOW.map((f, i) => (
          <div className="w-card" key={f.title}>
            <div className="num">{i + 1}</div>
            <b>{f.title}</b>
            <span>{f.desc}</span>
          </div>
        ))}
      </div>
      <div className="try-strip">
        <div className="label">이 문장으로 바로 시연해 보세요</div>
        <div className="samples">
          {SAMPLE_SENTENCES.map((s) => (
            <button key={s} type="button" className="sample-btn" onClick={() => actions.sampleSend(s)}>
              {s}
            </button>
          ))}
        </div>
      </div>
    </div>
  );
}
