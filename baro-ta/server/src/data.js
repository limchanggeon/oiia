export const STATIONS = [
  "서울", "용산", "수서", "대전", "동대구", "부산", "광주송정", "목포",
  "오송", "천안아산", "익산", "전주", "강릉", "포항", "울산", "여수",
];

// 서울 기준 대략적 KTX 소요시간(분) — 모의 데이터
export const DIST_MIN = {
  부산: 155, 대전: 62, 동대구: 105, 광주송정: 110, 목포: 145,
  오송: 48, 천안아산: 38, 익산: 82, 전주: 100, 강릉: 118,
  포항: 140, 울산: 128, 여수: 180, 서울: 60, 용산: 60, 수서: 60,
};

export const MODES = [
  { mode: "KTX", factor: 1.0, basePrice: 380, cls: "" },
  { mode: "SRT", factor: 0.96, basePrice: 360, cls: "" },
  { mode: "KTX", factor: 1.0, basePrice: 380, cls: "" },
  { mode: "ITX-새마을", factor: 1.55, basePrice: 250, cls: "" },
  { mode: "고속버스", factor: 1.85, basePrice: 210, cls: "bus" },
];

export const rand = (min, max) => Math.floor(Math.random() * (max - min + 1)) + min;

export const fmtTime = (min) => {
  const m = ((min % 1440) + 1440) % 1440;
  return `${String(Math.floor(m / 60)).padStart(2, "0")}:${String(m % 60).padStart(2, "0")}`;
};
