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
  { id: 108645, label: "Settled today", title: "Georgia Governor", category: "Politics" },
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

export function datePT(value: string, withTime = false): string {
  return new Intl.DateTimeFormat("en-US", {
    timeZone: "America/Los_Angeles", month: "short", day: "numeric",
    ...(withTime ? { hour: "numeric", minute: "2-digit" } : {}),
  }).format(new Date(value)) + (withTime ? " PT" : "");
}
