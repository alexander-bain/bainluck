export type Source = "kalshi" | "polymarket";

export type FeaturedMarket = {
  q: string;
  prob: number;
  src: Source;
  tag: string;
  closes: string;
};

export type CityData = {
  id: string;
  name: string;
  preferredX: number;
  preferredY: number;
  x: number;
  y: number;
  region: "Americas" | "Europe" | "Asia" | "Africa" | "Oceania";
  srcs: Source[];
  marketId?: number;
  high: {
    unit: "C" | "F";
    mode: number;
    dist: Array<{ label: string; prob: number }>;
  };
  kalshiHigh?: {
    unit: "C" | "F";
    mode: number;
    dist: Array<{ label: string; prob: number }>;
  };
  low?: {
    unit: "C" | "F";
    mode: number;
    dist: Array<{ label: string; prob: number }>;
  };
  rainToday?: number;
};

export type RainDay = {
  day: string;
  date: string;
  prob: number;
  icon: string;
};

export type MonthlyRain = {
  city: string;
  prob: number;
  src: Source;
  delta24h?: number;
};

export type EventMarket = {
  q: string;
  prob: number;
  src: Source;
  closes: string;
};

export type ClimateMarket = {
  q: string;
  prob: number;
  src: Source;
  scale: "2026" | "2030" | "2050";
};

export type WildCard = {
  q: string;
  prob: number;
  src: Source;
  tag: string;
};

export const SOURCES = {
  kalshi: { key: "kalshi" as const, label: "Kalshi", color: "#22C55E", bg: "#ECFDF5", fg: "#047857" },
  polymarket: { key: "polymarket" as const, label: "Polymarket", color: "#3B82F6", bg: "#EFF6FF", fg: "#1D4ED8" },
};

export const HERO_FEATURED: FeaturedMarket[] = [];

export const CITIES: CityData[] = [];

export const NYC_RAIN: RainDay[] = [];

export const MONTHLY_RAIN: MonthlyRain[] = [];

export const HURRICANE: EventMarket[] = [];

export const EARTHQUAKE: EventMarket[] = [];

export const TORNADOES: EventMarket[] = [];

export const CLIMATE: ClimateMarket[] = [];

export const WILDCARDS: WildCard[] = [];

export function tomorrowDateStr(): string {
  const d = new Date();
  d.setDate(d.getDate() + 1);
  const months = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];
  return `${months[d.getMonth()]} ${d.getDate()}, ${d.getFullYear()}`;
}

export function tomorrowDateStrUpper(): string {
  return tomorrowDateStr().toUpperCase();
}

export function probColor(p: number): string {
  if (p >= 65) return "#22C55E";
  if (p >= 35) return "#F59E0B";
  return "#EF4444";
}

export function probLabel(p: number): string {
  if (p >= 65) return "Likely";
  if (p >= 35) return "Toss-up";
  return "Unlikely";
}

export function tempColorC(tempC: number): string {
  const stops = [
    { t: -10, c: [37, 99, 235] },
    { t: 5, c: [56, 189, 248] },
    { t: 15, c: [148, 163, 184] },
    { t: 22, c: [245, 158, 11] },
    { t: 32, c: [239, 68, 68] },
    { t: 45, c: [159, 18, 57] },
  ];
  const t = Math.max(stops[0].t, Math.min(stops[stops.length - 1].t, tempC));
  for (let i = 0; i < stops.length - 1; i++) {
    const a = stops[i], b = stops[i + 1];
    if (t >= a.t && t <= b.t) {
      const f = (t - a.t) / (b.t - a.t);
      const c = [0, 1, 2].map(k => Math.round(a.c[k] + (b.c[k] - a.c[k]) * f));
      return `rgb(${c[0]},${c[1]},${c[2]})`;
    }
  }
  return "#94A3B8";
}

export function toC(city: CityData): number {
  return city.high.unit === "C" ? city.high.mode : ((city.high.mode - 32) * 5) / 9;
}

export function sparkFrom(seed: number, end: number, n = 14): number[] {
  let s = seed;
  const rng = () => { s = (s * 9301 + 49297) % 233280; return s / 233280; };
  const start = Math.max(2, Math.min(98, end + (rng() * 30 - 15)));
  const pts: number[] = [];
  let cur = start;
  for (let i = 0; i < n - 1; i++) {
    const target = start + ((end - start) * i) / (n - 1);
    cur = cur * 0.55 + target * 0.45 + (rng() * 8 - 4);
    pts.push(Math.max(2, Math.min(98, cur)));
  }
  pts.push(end);
  return pts;
}
