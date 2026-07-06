import { useEffect } from "react";
import { AppProvider, useApp } from "./store";
import { TopBar } from "./components/TopBar";
import { ChatRail } from "./components/ChatRail";
import { PhaseBar } from "./components/PhaseBar";
import { TabBar } from "./components/TabBar";
import { AgentConsole } from "./components/AgentConsole";
import { WelcomePanel } from "./components/panels/WelcomePanel";
import { RoutesPanel } from "./components/panels/RoutesPanel";
import { StandbyPanel } from "./components/panels/StandbyPanel";
import { BookingPanel } from "./components/panels/BookingPanel";
import { PaymentPanel } from "./components/panels/PaymentPanel";
import { DonePanel } from "./components/panels/DonePanel";

function Layout() {
  const { state, actions } = useApp();

  // 모바일 모드(≤700px)에서는 패널 전환 시 알맞은 뷰로 자동 이동
  useEffect(() => {
    const mq = window.matchMedia("(max-width: 700px)");
    if (mq.matches) actions.setView(state.panel === "welcome" ? "chat" : "stage");
  }, [state.panel, actions]);

  useEffect(() => {
    const mq = window.matchMedia("(max-width: 700px)");
    const onChange = () => {
      if (mq.matches) actions.setView(state.panel === "welcome" ? "chat" : "stage");
    };
    mq.addEventListener("change", onChange);
    return () => mq.removeEventListener("change", onChange);
  }, [state.panel, actions]);

  return (
    <div className={`shell${state.bigText ? " big" : ""}`}>
      <TopBar />
      <div className="main" data-view={state.view}>
        <ChatRail />
        <section className="stage">
          <PhaseBar />
          <div className="stage-scroll">
            {state.panel === "welcome" && <WelcomePanel />}
            {state.panel === "routes" && <RoutesPanel />}
            {state.panel === "standby" && <StandbyPanel />}
            {state.panel === "booking" && <BookingPanel />}
            {state.panel === "payment" && <PaymentPanel />}
            {state.panel === "done" && <DonePanel />}
          </div>
        </section>
      </div>
      <TabBar />
      <AgentConsole />
    </div>
  );
}

export default function App() {
  return (
    <AppProvider>
      <Layout />
    </AppProvider>
  );
}
