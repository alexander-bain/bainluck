import { getSourceColor } from "@/lib/sourceColors";

export type Source = "kalshi" | "polymarket";

// `leader` is the name of the outcome `prob` belongs to — "Minneapolis" under
// "Where will it rain on Aug 29, 2026?". Null when the market is binary and the
// question already carries its own answer; OPTIONAL because the hourly Redis
// cache can serve a payload built before the field existed, and a hero that
// printed "undefined" for an hour after deploy would be a worse bug than the
// one this fixes.
export type FeaturedMarket = {
  q: string;
  prob: number;
  src: Source;
  tag: string;
  closes: string;
  leader?: string | null;
  /** Real captured prices for the leader outcome, oldest first, 0-100. The
   *  sparkline's only permitted input — see {@link realSpark}. OPTIONAL for
   *  the same reason `leader` is: the hourly Redis cache can serve a payload
   *  built before the field existed, and an absent field must mean "no line",
   *  never "invent one". */
  history?: number[];
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
  /** The month the market resolves for ("Nov 2026"). Not the current month —
   *  a city's surviving row can be any future month, so the card is told. */
  period?: string | null;
  prob: number;
  src: Source;
  delta24h?: number;
};

export type EventMarket = {
  q: string;
  prob: number;
  src: Source;
  closes: string;
  /** See {@link FeaturedMarket.leader} — same field, same contract. */
  leader?: string | null;
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
  /** See {@link FeaturedMarket.leader} — same field, same contract. */
  leader?: string | null;
  /** See {@link FeaturedMarket.history} — same field, same contract. */
  history?: number[];
};

// Colors sourced from the one registry (@/lib/sourceColors). color=solid hex,
// bg=faint tint, fg=readable foreground — same source, same color everywhere.
export const SOURCES = {
  kalshi: { key: "kalshi" as const, label: getSourceColor("kalshi").label, color: getSourceColor("kalshi").hex, bg: getSourceColor("kalshi").faint, fg: getSourceColor("kalshi").fg },
  polymarket: { key: "polymarket" as const, label: getSourceColor("polymarket").label, color: getSourceColor("polymarket").hex, bg: getSourceColor("polymarket").faint, fg: getSourceColor("polymarket").fg },
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

// ux/1069 (#2960) — `sparkFrom(seed, end)` used to live here. It drew a
// 14-point sparkline in which exactly ONE point, the last, was the real price:
// a seeded LCG walked a noise path from a random-offset start toward it, and
// the hero and every wild card rendered that path in the same ink a real price
// history would use. On a probability site an invented line is worse than a
// missing one, because a missing one cannot be believed. It is gone, and
// nothing may replace it — the series now comes from the backend as
// `history`, which contains only rows captured from the market.

/** Fewest real captures that may be drawn as a line.
 *
 *  Two points is a straight segment, and a straight segment reads as a trend
 *  the data has not earned — the same lie the generator told, just cheaper to
 *  draw. Mirrors `MIN_HISTORY_POINTS` in `app/routes/weather.py`: the backend
 *  already withholds shorter series, and this is the second lock, because the
 *  hourly Redis cache can serve a payload built before that filter existed. */
export const MIN_SPARK_POINTS = 3;

/** The real capture series to draw, or null when there is nothing honest to draw.
 *
 *  Returns null — not `[]` — so the caller has to branch and omit the element
 *  entirely. Passing a short array to `<Sparkline>` would render nothing but
 *  leave its sized wrapper behind, and an empty box where a chart belongs is a
 *  placeholder by another name. */
export function realSpark(history: number[] | null | undefined): number[] | null {
  if (!Array.isArray(history)) return null;
  const pts = history.filter((v) => typeof v === "number" && Number.isFinite(v));
  return pts.length >= MIN_SPARK_POINTS ? pts : null;
}
