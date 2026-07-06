export const fmtTime = (min: number): string => {
  const m = ((min % 1440) + 1440) % 1440;
  return `${String(Math.floor(m / 60)).padStart(2, "0")}:${String(m % 60).padStart(2, "0")}`;
};

export const fmtWon = (n: number): string => `${n.toLocaleString("ko-KR")}원`;

export const rand = (min: number, max: number): number =>
  Math.floor(Math.random() * (max - min + 1)) + min;

export const nowLabel = (): string => new Date().toTimeString().slice(0, 8);
