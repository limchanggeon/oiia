export interface TripDate {
  label: string;
  md: string;
  iso: string;
}

export interface TripTime {
  min: number; // 자정 기준 분
  label: string;
}

export interface TripParams {
  origin: string | null;
  dest: string | null;
  date: TripDate | null;
  time: TripTime | null;
}

export interface RouteOption {
  id: string;
  mode: string;
  cls: string;
  no: string;
  dep: number;
  arr: number;
  dur: number;
  price: number;
  soldOut: boolean;
  score: number;
  reason?: string;
}

export interface AgentLine {
  tag: string;
  msg: string;
}

export interface AgentLogEntry extends AgentLine {
  t: string;
}

export interface ChatMsg {
  id: number;
  role: "bot" | "user";
  text: string;
  bold?: string; // 굵게 표시할 부분 (text 앞에 붙음)
  typing?: boolean;
  card?: TripParams;
  chips?: string[];
}

export interface PollEntry {
  n: number;
  t: string;
  found: boolean;
}

export interface BookingStep {
  title: string;
  detail: string;
  ms: number;
}

export interface Ticket {
  mode: string;
  no: string;
  origin: string;
  dest: string;
  depLabel: string;
  arrLabel: string;
  dateMd: string;
  seat: string;
  price: number;
}

export type PanelId = "welcome" | "routes" | "standby" | "booking" | "payment" | "done";
export type ViewId = "chat" | "stage";

// API 응답
export interface ParseResponse {
  got: Partial<TripParams>;
  agent: AgentLine[];
}
export interface SearchResponse {
  routes: RouteOption[];
  agent: AgentLine[];
}
export interface StandbyCheckResponse {
  attempt: number;
  available: boolean;
  remaining: number;
}
export interface CreateBookingResponse {
  bookingId: string;
  steps: BookingStep[];
  seat: string;
  agent: AgentLine[];
}
export interface PayResponse {
  ticket: Ticket;
  agent: AgentLine[];
}
export interface TravelCard {
  name: string;
  rating: string | null;
  price: string | null;
  url: string;
  img: string | null;
}
export interface TravelSuggestResponse {
  stays: TravelCard[];
  tnas: TravelCard[];
  agent: AgentLine[];
}
