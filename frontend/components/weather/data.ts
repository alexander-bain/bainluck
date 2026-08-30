import { getSourceColor } from "@/lib/sourceColors";
import { formatProbabilityPercent } from "@/lib/probabilityDisplay";

export type Source = "kalshi" | "polymarket";

// Every weather number arrives as a PAIR: `prob`, the whole percent the server
// already decided to print, and `probability`, the value it was decided from.
//
// `prob` alone is not enough, and the reason is the whole of UX-P192. A market
// priced 0.0005 renders to `0`, and `0%` does not read as "unlikely" — it reads
// as IMPOSSIBLE, printed over a quote a market is actively making. Measured in
// ONE query on 2026-08-30 across the outcomes these endpoints serve: 288 of
// 2,663 are strictly inside (0, 1) and render to 0, 21 render to 100 over a
// probability that is not 1, and there is not a single exact zero or null in the
// whole open weather population. So every `0%` this page has printed was a lie.
//
// The site has had the answer since UX-P046 — `formatProbabilityPercent` — and
// every other surface adopted it. `/weather` was the one that never did, because
// the wire only carried the rounded int and an int cannot be un-rounded.
//
// OPTIONAL, deliberately, and for the same reason `FeaturedMarket.leader` is:
// the hourly Redis cache can serve a payload built before the field existed, and
// for that hour `prob / 100` reconstructs exactly today's behaviour — a served
// 0 prints `0%`, not an invented `<1%`. A missing field must degrade to the old
// number, never to a new claim.
export type PrintedProbability = {
  prob: number;
  probability?: number | null;
};

/**
 * The percentage string a weather surface prints for one served number.
 *
 * The site's single home for the decision is `formatProbabilityPercent`; this
 * is the two-argument adapter for a wire that ships the integer and the value
 * separately. `rendered` overrides the INTEGER — the `<1%` / `>99%` rule still
 * runs on the PROBABILITY, because it is a claim about the value and not about
 * which arithmetic produced the integer (see that function's own docstring).
 */
export function weatherPercent(item: PrintedProbability): string {
  return formatProbabilityPercent(item.probability ?? item.prob / 100, {
    rendered: item.prob,
  });
}

/**
 * Whether a served number stands for a live price at all.
 *
 * `prob > 0` was the old test, and it is wrong in exactly the same way the
 * printed `0%` was: it asks the ROUNDED integer whether a market has an
 * opinion. A temperature bucket priced 0.0005 answers no, so the histogram
 * withheld its tooltip — the one place its number could have been read — from
 * the bucket that most needed explaining. There is not one genuine zero in the
 * open weather population, so this predicate is the difference between "no
 * price" and "a small price", which is the whole distinction the page owes.
 */
export function hasPrice(item: PrintedProbability): boolean {
  return (item.probability ?? item.prob / 100) > 0;
}

// `leader` is the name of the outcome `prob` belongs to — "Minneapolis" under
// "Where will it rain on Aug 29, 2026?". Null when the market is binary and the
// question already carries its own answer; OPTIONAL because the hourly Redis
// cache can serve a payload built before the field existed, and a hero that
// printed "undefined" for an hour after deploy would be a worse bug than the
// one this fixes.
export type FeaturedMarket = PrintedProbability & {
  q: string;
  src: Source;
  tag: string;
  closes: string;
  leader?: string | null;
};

/** One labelled bucket of a temperature distribution. */
export type DistBucket = PrintedProbability & { label: string };

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
    dist: DistBucket[];
  };
  kalshiHigh?: {
    unit: "C" | "F";
    mode: number;
    dist: DistBucket[];
  };
  low?: {
    unit: "C" | "F";
    mode: number;
    dist: DistBucket[];
  };
  rainToday?: number;
};

export type RainDay = PrintedProbability & {
  day: string;
  date: string;
  icon: string;
};

export type MonthlyRain = PrintedProbability & {
  city: string;
  /** The month the market resolves for ("Nov 2026"). Not the current month —
   *  a city's surviving row can be any future month, so the card is told. */
  period?: string | null;
  src: Source;
  delta24h?: number;
};

export type EventMarket = PrintedProbability & {
  q: string;
  src: Source;
  closes: string;
  /** See {@link FeaturedMarket.leader} — same field, same contract. */
  leader?: string | null;
};

export type ClimateMarket = PrintedProbability & {
  q: string;
  src: Source;
  scale: "2026" | "2030" | "2050";
};

export type WildCard = PrintedProbability & {
  q: string;
  src: Source;
  tag: string;
  /** See {@link FeaturedMarket.leader} — same field, same contract. */
  leader?: string | null;
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
