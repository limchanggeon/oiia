import type {
  CreateBookingResponse,
  ParseResponse,
  PayResponse,
  RouteOption,
  SearchResponse,
  StandbyCheckResponse,
  TravelSuggestResponse,
  TripParams,
} from "./types";

// 배포 시 VITE_API_URL로 백엔드 주소 지정 (개발은 vite proxy 사용)
const BASE = import.meta.env.VITE_API_URL ?? "";

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(BASE + path, {
    headers: { "Content-Type": "application/json" },
    ...init,
  });
  if (!res.ok) {
    const body = await res.json().catch(() => ({}));
    throw new Error(body.error ?? `API 오류 (${res.status})`);
  }
  return res.json() as Promise<T>;
}

export const api = {
  parse: (text: string) =>
    request<ParseResponse>("/api/nlu/parse", { method: "POST", body: JSON.stringify({ text }) }),

  searchRoutes: (origin: string, dest: string, arriveBy: number, dateIso?: string) =>
    request<SearchResponse>("/api/routes/search", {
      method: "POST",
      body: JSON.stringify({ origin, dest, arriveBy, dateIso }),
    }),

  standbyCheck: (searchId: string) =>
    request<StandbyCheckResponse>(`/api/standby/${searchId}/check`),

  createBooking: (route: RouteOption, params: TripParams) =>
    request<CreateBookingResponse>("/api/bookings", {
      method: "POST",
      body: JSON.stringify({ route, params }),
    }),

  pay: (bookingId: string) =>
    request<PayResponse>(`/api/bookings/${bookingId}/pay`, { method: "POST", body: "{}" }),

  travelSuggest: (dest: string, checkIn: string) =>
    request<TravelSuggestResponse>(`/api/travel/suggest?dest=${encodeURIComponent(dest)}&checkIn=${checkIn}`),
};
