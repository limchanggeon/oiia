import { createContext, useContext, useEffect, useMemo, useReducer, useRef } from "react";
import type { ReactNode } from "react";
import { api } from "./api";
import { nowLabel } from "./utils";
import type {
  AgentLine,
  AgentLogEntry,
  BookingStep,
  ChatMsg,
  PanelId,
  PollEntry,
  RouteOption,
  Ticket,
  TripParams,
  ViewId,
} from "./types";

export const SAMPLE_SENTENCES = [
  "내일 오후 2시까지 서울에서 부산 가야 해요",
  "모레 오전 10시까지 대전 도착하게 해줘",
  "강릉 가고 싶어",
];

interface BookingInfo {
  id: string;
  steps: BookingStep[];
  seat: string;
}

interface State {
  params: TripParams;
  messages: ChatMsg[];
  panel: PanelId;
  view: ViewId;
  bigText: boolean;
  consoleOpen: boolean;
  agentLog: AgentLogEntry[];
  routes: RouteOption[];
  chosen: RouteOption | null;
  pollLog: PollEntry[];
  standbyFound: boolean;
  booking: BookingInfo | null;
  stepIndex: number; // -1: 대기, n: n번째 진행 중, steps.length: 전 단계 완료
  handoff: boolean;
  ticket: Ticket | null;
}

const initialParams: TripParams = { origin: null, dest: null, date: null, time: null };

const initialState: State = {
  params: initialParams,
  messages: [],
  panel: "welcome",
  view: "chat",
  bigText: false,
  consoleOpen: true,
  agentLog: [],
  routes: [],
  chosen: null,
  pollLog: [],
  standbyFound: false,
  booking: null,
  stepIndex: -1,
  handoff: false,
  ticket: null,
};

type Action =
  | { type: "ADD_MSG"; msg: ChatMsg }
  | { type: "REPLACE_MSG"; id: number; patch: Partial<ChatMsg> }
  | { type: "CLEAR_CHIPS" }
  | { type: "SET_PARAMS"; params: TripParams }
  | { type: "SET_PANEL"; panel: PanelId }
  | { type: "SET_VIEW"; view: ViewId }
  | { type: "TOGGLE_BIG" }
  | { type: "TOGGLE_CONSOLE" }
  | { type: "AGENT_LOG"; entry: AgentLogEntry }
  | { type: "SET_ROUTES"; routes: RouteOption[] }
  | { type: "SET_CHOSEN"; route: RouteOption }
  | { type: "RESET_STANDBY" }
  | { type: "POLL_ADD"; entry: PollEntry }
  | { type: "STANDBY_FOUND" }
  | { type: "SET_BOOKING"; booking: BookingInfo }
  | { type: "SET_STEP"; index: number }
  | { type: "SET_HANDOFF" }
  | { type: "SET_TICKET"; ticket: Ticket }
  | { type: "RESET_CHAT" }
  | { type: "RESET_ALL" };

function reducer(state: State, action: Action): State {
  switch (action.type) {
    case "ADD_MSG":
      return { ...state, messages: [...state.messages, action.msg] };
    case "REPLACE_MSG":
      return {
        ...state,
        messages: state.messages.map((m) => (m.id === action.id ? { ...m, ...action.patch, typing: false } : m)),
      };
    case "CLEAR_CHIPS":
      return { ...state, messages: state.messages.map((m) => (m.chips ? { ...m, chips: undefined } : m)) };
    case "SET_PARAMS":
      return { ...state, params: action.params };
    case "SET_PANEL":
      return { ...state, panel: action.panel };
    case "SET_VIEW":
      return { ...state, view: action.view };
    case "TOGGLE_BIG":
      return { ...state, bigText: !state.bigText };
    case "TOGGLE_CONSOLE":
      return { ...state, consoleOpen: !state.consoleOpen };
    case "AGENT_LOG":
      return { ...state, agentLog: [...state.agentLog, action.entry] };
    case "SET_ROUTES":
      return { ...state, routes: action.routes };
    case "SET_CHOSEN":
      return { ...state, chosen: action.route };
    case "RESET_STANDBY":
      return { ...state, pollLog: [], standbyFound: false };
    case "POLL_ADD":
      return { ...state, pollLog: [action.entry, ...state.pollLog] };
    case "STANDBY_FOUND":
      return { ...state, standbyFound: true };
    case "SET_BOOKING":
      return { ...state, booking: action.booking, stepIndex: -1, handoff: false };
    case "SET_STEP":
      return { ...state, stepIndex: action.index };
    case "SET_HANDOFF":
      return { ...state, handoff: true };
    case "SET_TICKET":
      return { ...state, ticket: action.ticket };
    case "RESET_CHAT":
      return { ...state, params: initialParams, messages: [] };
    case "RESET_ALL":
      return {
        ...initialState,
        bigText: state.bigText,
        consoleOpen: state.consoleOpen,
        agentLog: state.agentLog,
      };
    default:
      return state;
  }
}

export interface AppActions {
  sendText(text: string): void;
  pickChip(label: string): void;
  sampleSend(text: string): void;
  selectRoute(route: RouteOption): void;
  startBooking(): void;
  goPayment(): void;
  pay(): Promise<void>;
  standbyAttempt(searchId: string): Promise<boolean>;
  resetAll(quiet?: boolean): void;
  toggleBig(): void;
  toggleConsole(): void;
  setView(view: ViewId): void;
  log(tag: string, msg: string): void;
}

const AppContext = createContext<{ state: State; actions: AppActions } | null>(null);

export function AppProvider({ children }: { children: ReactNode }) {
  const [state, dispatch] = useReducer(reducer, initialState);
  const stateRef = useRef(state);
  stateRef.current = state;

  const msgIdRef = useRef(1);
  const timersRef = useRef<number[]>([]);
  const demoRef = useRef(new URLSearchParams(window.location.search).has("demo"));

  const actions = useMemo<AppActions>(() => {
    const later = (fn: () => void, ms: number) => {
      timersRef.current.push(window.setTimeout(fn, ms));
    };
    const clearTimers = () => {
      timersRef.current.forEach((t) => window.clearTimeout(t));
      timersRef.current = [];
    };
    const log = (tag: string, msg: string) =>
      dispatch({ type: "AGENT_LOG", entry: { t: nowLabel(), tag, msg } });
    const logAll = (lines: AgentLine[]) => lines.forEach((l) => log(l.tag, l.msg));

    const addUser = (text: string) => {
      dispatch({ type: "CLEAR_CHIPS" });
      dispatch({ type: "ADD_MSG", msg: { id: msgIdRef.current++, role: "user", text } });
    };
    const addBot = (
      text: string,
      opts: { bold?: string; chips?: string[]; card?: TripParams; instant?: boolean } = {}
    ) => {
      const id = msgIdRef.current++;
      if (opts.instant) {
        dispatch({ type: "ADD_MSG", msg: { id, role: "bot", text, bold: opts.bold, chips: opts.chips, card: opts.card } });
        return;
      }
      dispatch({ type: "ADD_MSG", msg: { id, role: "bot", text: "", typing: true } });
      later(() => {
        dispatch({ type: "REPLACE_MSG", id, patch: { text, bold: opts.bold, chips: opts.chips, card: opts.card } });
      }, 650);
    };
    const botNote = (text: string, bold?: string) => addBot(text, { bold, instant: true });
    const apiError = (err: unknown) => {
      const msg = err instanceof Error ? err.message : String(err);
      log("ERROR", msg);
      botNote("서버와 통신하지 못했어요. 백엔드(포트 4000)가 켜져 있는지 확인해 주세요.");
    };

    const greet = () => {
      addBot("안녕하세요! 저는 바로타 AI예요.\n어디로, 언제까지 가시는지 편하게 말씀해 주세요.", {
        chips: [SAMPLE_SENTENCES[0], SAMPLE_SENTENCES[2]],
      });
    };

    const mergeParams = (got: Partial<TripParams>): TripParams => {
      const cur = stateRef.current.params;
      const merged: TripParams = {
        origin: got.origin ?? cur.origin,
        dest: got.dest ?? cur.dest,
        date: got.date ?? cur.date,
        time: got.time ?? cur.time,
      };
      dispatch({ type: "SET_PARAMS", params: merged });
      return merged;
    };

    const askNext = (p: TripParams) => {
      if (!p.dest) {
        addBot("어디로 가시나요? 도착지를 알려주세요.", { chips: ["부산", "대전", "강릉", "광주송정"] });
      } else if (!p.date) {
        addBot(`${p.dest}까지 가시는군요! 언제 도착하시면 될까요?`, { chips: ["오늘", "내일", "모레"] });
      } else if (!p.time) {
        addBot("몇 시까지 도착해야 하나요?", { chips: ["오전 9시", "오후 2시", "오후 6시"] });
      } else if (!p.origin) {
        addBot("출발은 지금 계신 현재 위치(서울)에서 하시나요?", {
          chips: ["네, 현재 위치(서울)", "대전에서 출발", "동대구에서 출발"],
        });
      } else {
        log("NLU", "필수 파라미터 4종 확보 완료 → 경로 탐색 준비");
        addBot("좋아요, 이렇게 찾아볼게요!", { card: p, chips: ["경로 검색하기", "다시 입력할래요"] });
        if (demoRef.current) later(() => pickChip("경로 검색하기"), 1800);
      }
    };

    const processText = async (text: string) => {
      try {
        const res = await api.parse(text);
        logAll(res.agent);
        askNext(mergeParams(res.got));
      } catch (err) {
        apiError(err);
      }
    };

    const sendText = (text: string) => {
      const t = text.trim();
      if (!t) return;
      addUser(t);
      void processText(t);
    };

    const doSearch = async () => {
      const p = stateRef.current.params;
      if (!p.origin || !p.dest || !p.time) return;
      try {
        const res = await api.searchRoutes(p.origin, p.dest, p.time.min);
        logAll(res.agent);
        dispatch({ type: "SET_ROUTES", routes: res.routes });
        dispatch({ type: "SET_PANEL", panel: "routes" });
      } catch (err) {
        apiError(err);
      }
    };

    const resetChatOnly = () => {
      dispatch({ type: "RESET_CHAT" });
      greet();
    };

    const pickChip = (label: string) => {
      if (label === "경로 검색하기") {
        addUser(label);
        addBot("잠시만요, 경로를 찾고 있어요…");
        later(() => void doSearch(), 1400);
        return;
      }
      if (label === "다시 입력할래요") {
        addUser(label);
        resetChatOnly();
        return;
      }
      if (label.includes("현재 위치") || label.includes("출발")) {
        addUser(label);
        const origin = label.includes("대전") ? "대전" : label.includes("동대구") ? "동대구" : "서울";
        log("GPS", label.includes("현재 위치") ? "현재 위치 기반 출발지 확정: 서울" : `사용자 지정 출발지: ${origin}`);
        askNext(mergeParams({ origin }));
        return;
      }
      sendText(label);
    };

    const startBookingWith = async (route: RouteOption) => {
      const p = stateRef.current.params;
      try {
        const res = await api.createBooking(route, p);
        logAll(res.agent);
        dispatch({ type: "SET_BOOKING", booking: { id: res.bookingId, steps: res.steps, seat: res.seat } });
        dispatch({ type: "SET_PANEL", panel: "booking" });
        let acc = 200;
        res.steps.forEach((s, i) => {
          later(() => {
            dispatch({ type: "SET_STEP", index: i });
            log("AUTO", `단계 ${i + 1}/${res.steps.length}: ${s.title}`);
          }, acc);
          acc += s.ms;
        });
        later(() => {
          dispatch({ type: "SET_STEP", index: res.steps.length });
          dispatch({ type: "SET_HANDOFF" });
          log("HANDOFF", "결제 직전 도달 → 접근성 서비스 해제, 제어권 사용자 반환");
          botNote(" 결제 직전까지 준비를 마쳤어요. 지금부터는 직접 진행하세요. 자동화는 해제했습니다.");
        }, acc);
      } catch (err) {
        apiError(err);
      }
    };

    const selectRoute = (route: RouteOption) => {
      dispatch({ type: "SET_CHOSEN", route });
      log("USER", `경로 선택: ${route.no}${route.soldOut ? " (매진 → 자동 조회 모드)" : ""}`);
      if (route.soldOut) {
        botNote("는 지금 매진이에요. 취소표 자동 조회를 시작할게요. 자리가 나면 바로 알려드릴게요.", route.no);
        dispatch({ type: "RESET_STANDBY" });
        dispatch({ type: "SET_PANEL", panel: "standby" });
        log("POLL", `취소표 자동 조회 시작 (랜덤 주기 2~5초, 목표: ${route.no})`);
      } else {
        botNote("로 자동 예매를 시작할게요. 결제 직전까지 제가 진행합니다.", route.no);
        void startBookingWith(route);
      }
    };

    const standbyAttempt = async (searchId: string): Promise<boolean> => {
      const res = await api.standbyCheck(searchId);
      dispatch({ type: "POLL_ADD", entry: { n: res.attempt, t: nowLabel(), found: res.available } });
      log("POLL", `시도 #${res.attempt}${res.available ? " → 잔여석 1석 발견 ✓" : " → 매진 유지"}`);
      if (res.available) {
        dispatch({ type: "STANDBY_FOUND" });
        log("AI", "확보 기회 감지 → 자동 예매 파이프라인 대기");
        botNote(` ${res.attempt}번째 조회에서 잔여석을 발견했어요. 자동 예매를 시작하세요.`, "취소표가 나왔어요!");
      }
      return res.available;
    };

    const startBooking = () => {
      const chosen = stateRef.current.chosen;
      if (chosen) void startBookingWith(chosen);
    };

    const goPayment = () => dispatch({ type: "SET_PANEL", panel: "payment" });

    const pay = async () => {
      const booking = stateRef.current.booking;
      if (!booking) return;
      try {
        const res = await api.pay(booking.id);
        logAll(res.agent);
        dispatch({ type: "SET_TICKET", ticket: res.ticket });
        dispatch({ type: "SET_PANEL", panel: "done" });
        botNote(" 즐거운 여행 되세요. 승차권은 진행 화면에서 확인할 수 있어요.", "예매 완료!");
      } catch (err) {
        apiError(err);
      }
    };

    const resetAll = (quiet = false) => {
      clearTimers();
      dispatch({ type: "RESET_ALL" });
      if (!quiet) log("SYS", "세션 초기화");
      greet();
    };

    const sampleSend = (text: string) => {
      clearTimers();
      dispatch({ type: "RESET_ALL" });
      greet();
      later(() => sendText(text), 300);
    };

    return {
      sendText,
      pickChip,
      sampleSend,
      selectRoute,
      startBooking,
      goPayment,
      pay,
      standbyAttempt,
      resetAll,
      toggleBig: () => dispatch({ type: "TOGGLE_BIG" }),
      toggleConsole: () => dispatch({ type: "TOGGLE_CONSOLE" }),
      setView: (view: ViewId) => dispatch({ type: "SET_VIEW", view }),
      log,
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // 최초 진입: 인사 + (데모 모드) 자동 시연
  useEffect(() => {
    actions.log("SYS", "바로타 웹 클라이언트 세션 시작");
    actions.resetAll(true);
    if (demoRef.current) {
      const t = window.setTimeout(() => actions.sendText(SAMPLE_SENTENCES[0]), 900);
      return () => window.clearTimeout(t);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  return <AppContext.Provider value={{ state, actions }}>{children}</AppContext.Provider>;
}

export function useApp() {
  const ctx = useContext(AppContext);
  if (!ctx) throw new Error("useApp must be used within AppProvider");
  return ctx;
}

export function phaseOf(panel: PanelId): number {
  switch (panel) {
    case "welcome":
      return 1;
    case "routes":
      return 2;
    case "standby":
      return 3;
    case "booking":
    case "payment":
      return 4;
    case "done":
      return 5;
  }
}
