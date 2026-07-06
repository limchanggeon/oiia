import { useEffect, useRef, useState } from "react";
import type { FormEvent } from "react";
import { useApp } from "../store";
import type { ChatMsg } from "../types";

function ParamCard({ msg }: { msg: ChatMsg }) {
  const p = msg.card;
  if (!p) return null;
  return (
    <div className="param-card">
      <div className="title">요청 확인</div>
      <div className="param-row">
        <span className="k">출발지</span>
        <span className="v">{p.origin}</span>
      </div>
      <div className="param-row">
        <span className="k">도착지</span>
        <span className="v">{p.dest}</span>
      </div>
      <div className="param-row">
        <span className="k">날짜</span>
        <span className="v">
          {p.date?.md} ({p.date?.label})
        </span>
      </div>
      <div className="param-row">
        <span className="k">희망 도착</span>
        <span className="v">{p.time?.label} 까지</span>
      </div>
    </div>
  );
}

function Bubble({ msg }: { msg: ChatMsg }) {
  if (msg.typing) {
    return (
      <span className="typing">
        <i />
        <i />
        <i />
      </span>
    );
  }
  return (
    <div className="bubble">
      {msg.bold && <b>{msg.bold}</b>}
      {msg.text.split("\n").map((line, i) => (
        <span key={i}>
          {i > 0 && <br />}
          {line}
        </span>
      ))}
      <ParamCard msg={msg} />
    </div>
  );
}

export function ChatRail() {
  const { state, actions } = useApp();
  const [input, setInput] = useState("");
  const scrollRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const el = scrollRef.current;
    if (el) el.scrollTop = el.scrollHeight;
  }, [state.messages]);

  const onSubmit = (e: FormEvent) => {
    e.preventDefault();
    if (!input.trim()) return;
    actions.sendText(input);
    setInput("");
  };

  return (
    <aside className="chat-rail">
      <div className="rail-head">
        <div className="avatar">타</div>
        <div>
          <b>바로타 AI</b>
          <span>● 대화 가능</span>
        </div>
      </div>
      <div className="chat-scroll" ref={scrollRef}>
        <div className="chat-body">
          {state.messages.map((msg) => (
            <div key={msg.id} className={`msg ${msg.role}`}>
              <div className="who">{msg.role === "bot" ? "바로타 AI" : "나"}</div>
              <Bubble msg={msg} />
              {msg.chips && (
                <div className="chips">
                  {msg.chips.map((chip) => (
                    <button key={chip} type="button" className="chip" onClick={() => actions.pickChip(chip)}>
                      {chip}
                    </button>
                  ))}
                </div>
              )}
            </div>
          ))}
        </div>
      </div>
      <form className="chat-input" onSubmit={onSubmit}>
        <input
          type="text"
          value={input}
          onChange={(e) => setInput(e.target.value)}
          placeholder="예: 내일 오후 2시까지 부산 가야 해요"
          aria-label="메시지 입력"
        />
        <button className="send-btn" type="submit">
          전송
        </button>
      </form>
    </aside>
  );
}
