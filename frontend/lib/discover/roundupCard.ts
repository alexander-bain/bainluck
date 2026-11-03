/**
 * #10357 — the round-up card's model ("NFL division front-runners").
 *
 * Design reference: Fable's R4 (FABLE-NFL-DIVISION-ROUNDUP-DESIGN-20261007-R4.md)
 * with Alex's Oct 6 rulings. Pure, so every rule below is pinned without a DOM:
 *
 * - Rows run HIGHEST PROBABILITY FIRST. The server already sends them that way;
 *   the card re-sorts anyway, because the order is a ruling, not a hint.
 * - Every row's number is the served blend, formatted by the product's own
 *   formatter (whole percent; 99.7% prints >99%).
 * - A round-up is all-or-nothing: one unreadable row and there is no card. A
 *   division that cannot be blended is a matching defect, not a card state.
 * - Age uses the product's rule unchanged (`lib/sourceAge`, futures cadence =
 *   six hours). Every row old → ONE mark on the footer (the oldest row's age);
 *   some rows old → a mark on each old row; none → no mark. An undatable row is
 *   not old (the product never calls a price it cannot date stale).
 */
import { probabilityParts, type ProbabilityParts } from "@/lib/probabilityDisplay";
import { FUTURES_STALE_AFTER_MS, oldestSourceStamp, sourceIsStale } from "@/lib/sourceAge";
import type { FeedRoundupContract } from "@/lib/types";

/** Over this many characters the headline drops to its long size (R4). */
export const ROUNDUP_LONG_HEADLINE_CHARS = 44;
export const ROUNDUP_MIN_ROWS = 3;
export const ROUNDUP_MAX_ROWS = 4;

export interface RoundupRowModel {
  marketId: number;
  label: string;
  /** The formatter's boundary marker when rounding would claim a boundary; else null. */
  marker: ProbabilityParts["marker"];
  digits: string;
  /** Bar fill as a share of the track, [0, 1]. */
  fill: number;
  observedAt: string | null;
  /** This row carries its own age mark (the "some rows old" state). */
  rowMark: boolean;
}

export interface RoundupCardModel {
  kicker: string;
  title: string;
  tag: string | null;
  footer: string;
  longHeadline: boolean;
  rows: RoundupRowModel[];
  /** The footer's age mark (the "every row old" state), or null. */
  cardMarkObservedAt: string | null;
}

export type RoundupRefusal =
  | "no_contract"
  | "no_title"
  | "no_kicker"
  | "no_footer"
  | "row_count"
  | "bad_row"
  | "duplicate_market";

const isPositiveInt = (v: unknown): v is number => typeof v === "number" && Number.isInteger(v) && v > 0;
const text = (v: unknown): string => (typeof v === "string" ? v.trim() : "");

export function buildRoundupCardModel(
  title: string | null | undefined,
  contract: FeedRoundupContract | null | undefined,
  nowMs: number = Date.now(),
): { model: RoundupCardModel | null; refusal: RoundupRefusal | null } {
  if (!contract || typeof contract !== "object") return { model: null, refusal: "no_contract" };
  const headline = text(title);
  if (!headline) return { model: null, refusal: "no_title" };
  const kicker = text(contract.kicker);
  if (!kicker) return { model: null, refusal: "no_kicker" };
  const footer = text(contract.footer);
  if (!footer) return { model: null, refusal: "no_footer" };
  const served = Array.isArray(contract.rows) ? contract.rows : [];
  if (served.length < ROUNDUP_MIN_ROWS || served.length > ROUNDUP_MAX_ROWS) {
    return { model: null, refusal: "row_count" };
  }

  const seen = new Set<number>();
  const readable: { row: (typeof served)[number]; rowId: number; label: string; index: number }[] = [];
  for (const [index, row] of served.entries()) {
    const label = text(row?.label);
    const p = row?.probability;
    const hasMarket = row != null && row.market_id !== undefined && row.market_id !== null;
    const hasEvent = row != null && row.event_id !== undefined && row.event_id !== null;
    const rowId = hasMarket ? row.market_id : hasEvent ? row.event_id : undefined;
    if (
      !row ||
      hasMarket === hasEvent ||
      !isPositiveInt(rowId) ||
      !label ||
      typeof p !== "number" ||
      !Number.isFinite(p) ||
      p < 0 ||
      p > 1
    ) {
      return { model: null, refusal: "bad_row" };
    }
    if (seen.has(rowId)) return { model: null, refusal: "duplicate_market" };
    seen.add(rowId);
    readable.push({ row, rowId, label, index });
  }

  // Highest first; a tie keeps the served order.
  readable.sort((a, b) => b.row.probability - a.row.probability || a.index - b.index);

  const stamps = readable.map(({ row }) => (typeof row.observed_at === "string" ? row.observed_at : null));
  const stale = stamps.map((s) => sourceIsStale(s, nowMs, FUTURES_STALE_AFTER_MS));
  const allOld = stale.every(Boolean);

  const rows: RoundupRowModel[] = readable.map(({ row, rowId, label }, i) => {
    const parts = probabilityParts(row.probability, {
      rendered: typeof row.rendered_percent === "number" ? row.rendered_percent : undefined,
    });
    return {
      marketId: rowId,
      label,
      marker: parts.marker,
      digits: parts.digits,
      fill: row.probability,
      observedAt: stamps[i],
      rowMark: !allOld && stale[i],
    };
  });

  return {
    model: {
      kicker,
      title: headline,
      tag: text(contract.tag) || null,
      footer,
      longHeadline: headline.length > ROUNDUP_LONG_HEADLINE_CHARS,
      rows,
      cardMarkObservedAt: allOld ? oldestSourceStamp(stamps) : null,
    },
    refusal: null,
  };
}
