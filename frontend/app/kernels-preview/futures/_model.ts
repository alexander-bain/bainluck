import { isMarketShape, type MarketShape } from "@/lib/marketShape";
import { probabilityParts } from "@/lib/probabilityDisplay";
import { outcomeRowVerdict } from "@/components/futures/OutcomeRow";
import type { FuturesMarketDetailResponse, FuturesOutcome, FuturesOutcomeHistory } from "@/lib/types";

export const CASES = [
  { id: 109085, label: "Duel", title: "Kansas Senate", category: "Politics" },
  { id: 108629, label: "Field", title: "Closest Governor race", category: "Politics" },
  { id: 65536371, label: "Ladder", title: "Denver snow", category: "Weather" },
  { id: 227, label: "Participation", title: "Playoff qualifiers", category: "College football" },
  { id: 109918, label: "One leg", title: "Governor sweep", category: "Politics" },
  { id: 108645, label: "Settled", title: "Georgia Governor", category: "Politics" },
] as const;

export type StudyState = "payload" | "open" | "settled";
export interface RelatedMarket {
  id: number;
  name: string;
  lead: string;
  probability: number | null;
  verdict: "won" | "lost" | null;
  sources: string[];
  outcomes?: FuturesOutcome[];
  status?: string;
}
export interface PrototypeData {
  detail: FuturesMarketDetailResponse;
  history: FuturesOutcomeHistory[];
  sources: string[];
  capturedAt: string;
  related: RelatedMarket[];
  historyNote: string | null;
  settledAt: string | null;
  finalDetail?: FuturesMarketDetailResponse;
  finalCapturedAt?: string;
  venueRules?: string;
}

// Stored shape is authoritative. In particular, a one-leg market never grows
// an invented No, and participation never enters a normalization branch.
export function storedShape(detail: FuturesMarketDetailResponse): MarketShape {
  return isMarketShape(detail.market_type) ? detail.market_type : "unshaped";
}

export function bodyKind(detail: FuturesMarketDetailResponse): MarketShape {
  const shape = storedShape(detail);
  // 227 is served as `field` + mutually_exclusive:false. Keep that stored value
  // intact; the field's independent form is a band, never a one-winner split.
  return shape === "field" && !detail.mutually_exclusive ? "participation" : shape;
}

export function rankedOutcomes(detail: FuturesMarketDetailResponse): FuturesOutcome[] {
  return [...detail.outcomes].sort((a, b) => (b.probability ?? -1) - (a.probability ?? -1));
}

export function percentText(probability: number | null, rendered?: number | null): string {
  if (probability == null) return "—";
  const parts = probabilityParts(probability, rendered == null ? undefined : { rendered });
  return `${parts.marker ?? ""}${parts.digits}%`;
}

export function payloadVerdict(detail: FuturesMarketDetailResponse, outcome: FuturesOutcome) {
  return outcomeRowVerdict(outcome, detail.status === "resolved");
}

export function datePT(value: string, withTime = false, exact = false): string {
  return new Intl.DateTimeFormat("en-US", {
    timeZone: "America/Los_Angeles", month: "short", day: "numeric",
    ...(exact || new Date(value).getUTCFullYear() !== 2026 ? { year: "numeric" as const } : {}),
    ...(withTime ? { hour: "numeric", minute: "2-digit", ...(exact ? { second: "2-digit" as const } : {}) } : {}),
  }).format(new Date(value)) + (withTime ? " PT" : "");
}

export function validProbability(value: unknown): value is number {
  return typeof value === "number" && Number.isFinite(value) && value >= 0 && value <= 1;
}

/** A registered-twin opening blend is not in this payload. Do not compare a
 * one-venue opening with the served two-venue number. */
export function openingFor(data: PrototypeData, outcome: FuturesOutcome): number | null {
  if (data.sources.length > 1) return null;
  return validProbability(outcome.opening_probability) ? outcome.opening_probability : null;
}

export interface Observation { t: number; probability: number; timestamp: string }
export function observations(history: FuturesOutcomeHistory[], id: number): Observation[] {
  const byTime = new Map<number, Observation>();
  for (const row of history.find((s) => s.outcome_id === id)?.history ?? []) {
    if (row.bookmaker === "settlement" || !validProbability(row.probability)) continue;
    const t = Date.parse(row.timestamp);
    if (Number.isFinite(t)) byTime.set(t, { t, probability: row.probability, timestamp: row.timestamp });
  }
  return [...byTime.values()].sort((a, b) => a.t - b.t);
}

/** Narrow presentation adapter for the six supplied Denver threshold rows.
 * Never infer a comparator/unit for a different untyped family. */
export function snowThreshold(detail: FuturesMarketDetailResponse, row: FuturesOutcome): number | null {
  if (detail.id !== 65536371 || storedShape(detail) !== "quantity") return null;
  const match = /^Above (\d+) inches$/.exec(row.name);
  return match ? Number(match[1]) : null;
}
