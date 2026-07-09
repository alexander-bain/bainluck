// #999 Event Concept Pages (slice 1) — pure display helpers for /event/[key].
// Extracted so the rendering logic is unit-tested without mounting the page.
// D1 binds: probabilities only, never odds.

import type {
  EventConceptCompetitor,
  EventConceptChild,
  EventConceptResponse,
  FuturesOutcomeHistory,
} from "./types";

export function statusLabel(status: string): string {
  switch (status) {
    case "live":
      return "Live";
    case "settled":
      return "Settled";
    default:
      return "Upcoming";
  }
}

/** Competitors sorted by probability desc (the winner-field leaderboard order). */
export function fieldOrder(
  competitors: EventConceptCompetitor[],
): EventConceptCompetitor[] {
  return [...(competitors || [])].sort(
    (a, b) => (b.probability ?? -1) - (a.probability ?? -1),
  );
}

/** The leading outcome (name + probability) for a child matchup/prop row.
 *  Falls back to the child's own name/probability when it has no outcomes. */
export function childLeader(
  child: EventConceptChild,
): { name: string; probability: number | null } | null {
  const outs = child.outcomes || [];
  if (outs.length > 0) {
    const top = [...outs].sort(
      (a, b) => (b.probability ?? -1) - (a.probability ?? -1),
    )[0];
    return { name: top.name, probability: top.probability ?? null };
  }
  if (child.name) return { name: child.name, probability: child.probability ?? null };
  if (child.market_name) return { name: child.market_name, probability: child.probability ?? null };
  return null;
}

/** Split children into live vs settled (decided) so the page keeps live matchups
 *  prominent and groups/de-emphasizes completed ones (L2-63 Item 2 — a decided
 *  match must not masquerade as live at 99%). Settled = the envelope flag, or a
 *  dead-extreme leader as a fallback. */
export function splitChildren(
  children: EventConceptChild[],
): { live: EventConceptChild[]; settled: EventConceptChild[] } {
  const live: EventConceptChild[] = [];
  const settled: EventConceptChild[] = [];
  for (const c of children || []) {
    const p = c.probability;
    const decided = c.settled === true || (p != null && (p >= 0.97 || p <= 0.03));
    (decided ? settled : live).push(c);
  }
  return { live, settled };
}

/** Count of distinct markets tracked on this page — for the header "N markets"
 *  chip. Unions section market_ids, child market_ids, and the evolution market so
 *  the count reflects what the page actually surfaces (not a fabricated total). */
export function marketsTracked(data: EventConceptResponse): number {
  const ids = new Set<number>();
  for (const s of data.sections || []) {
    for (const id of s.market_ids || []) ids.add(id);
  }
  for (const c of data.children || []) {
    if (typeof c.market_id === "number") ids.add(c.market_id);
  }
  const ev = data.primary?.evolution_market_id;
  if (typeof ev === "number") ids.add(ev);
  return ids.size;
}

/** 24h probability movement for a competitor, read defensively from either the
 *  golf-shaped `movement_24h` or the generic `probability_change_24h` extra key.
 *  Returns a signed FRACTION (e.g. +0.03), or null when absent. */
export function competitorMovement(c: EventConceptCompetitor): number | null {
  const raw =
    (c as Record<string, unknown>).movement_24h ??
    (c as Record<string, unknown>).probability_change_24h;
  if (typeof raw !== "number" || Number.isNaN(raw)) return null;
  // Golf movement_24h is already a probability fraction; a value with abs>1 is
  // almost certainly already in points — normalize both to fraction.
  return Math.abs(raw) > 1 ? raw / 100 : raw;
}

/** Format a signed probability fraction as movement points, e.g. +3.2 / -1.0.
 *  Returns null for a null/zero-rounding change so callers can omit the chip. */
export function formatMovement(
  change: number | null | undefined,
): { text: string; dir: "up" | "down" } | null {
  if (change == null || Number.isNaN(change)) return null;
  const pts = change * 100;
  if (Math.abs(pts) < 0.05) return null;
  const dir = pts > 0 ? "up" : "down";
  return { text: `${pts > 0 ? "+" : "−"}${Math.abs(pts).toFixed(1)}`, dir };
}

/** Extract a competitor's probability series (0–1) from fetched history, matched
 *  by normalized name. Returns time-ordered probabilities (nulls dropped). Empty
 *  when the competitor has no matching series — the caller then omits the
 *  sparkline rather than inventing history. */
export function seriesForName(
  outcomes: FuturesOutcomeHistory[] | undefined,
  name: string,
): number[] {
  if (!outcomes || !name) return [];
  const norm = (s: string) => s.trim().toLowerCase();
  const target = norm(name);
  const match = outcomes.find((o) => norm(o.name) === target);
  if (!match) return [];
  return match.history
    .filter((p) => p.probability != null)
    .map((p) => p.probability as number);
}

/** L2-71: a competitor's own probability series (from the envelope-attached
 *  history), for the sparkline. Empty when no history — omit, never fabricate. */
export function seriesFromCompetitor(c: EventConceptCompetitor): number[] {
  return (c.history || [])
    .filter((p) => p && p.probability != null)
    .map((p) => p.probability);
}

/** L2-71: build FuturesOutcomeHistory[] from the envelope competitors that carry
 *  history, so the RaceToTitleChart draws from the envelope (no extra fetch).
 *  Optionally filter each series to the last `hours` (client-side range switch). */
export function competitorsToOutcomeHistory(
  competitors: EventConceptCompetitor[],
  hours?: number,
): FuturesOutcomeHistory[] {
  const cutoff =
    hours && hours > 0 ? Date.now() - hours * 3600 * 1000 : null;
  const out: FuturesOutcomeHistory[] = [];
  for (const c of competitors || []) {
    if (typeof c.outcome_id !== "number" || !c.history || c.history.length === 0) continue;
    const pts = cutoff
      ? c.history.filter((p) => {
          const t = new Date(p.timestamp).getTime();
          return Number.isNaN(t) || t >= cutoff;
        })
      : c.history;
    out.push({
      outcome_id: c.outcome_id,
      name: c.name,
      history: pts.map((p) => ({
        timestamp: p.timestamp,
        probability: p.probability,
        american_odds: null,
        bookmaker: "aggregate",
      })),
    });
  }
  return out;
}

/** L2-78: calendar days until an event starts, from `now` (ms). Honest countdown
 *  for the pre-tournament header — the *calendar-day* difference (UTC), so July 9
 *  → July 15 reads "6 days" the way a person counts it (not 5-and-a-fraction).
 *  Returns null when there's no start, the date is unparseable, or the start day
 *  is already past. 0 = starts on today's date. Pure so it's clock-free tested. */
export function daysUntilStart(
  start: string | null | undefined,
  now: number,
): number | null {
  if (!start) return null;
  const t = new Date(start).getTime();
  if (Number.isNaN(t)) return null;
  const dayMs = 24 * 3600 * 1000;
  const days = Math.floor(t / dayMs) - Math.floor(now / dayMs);
  if (days < 0) return null;
  return days;
}

/** L2-78: the header countdown label for an upcoming event, or null when there's
 *  nothing to show (live/settled, or no future start). Kept pure + separate from
 *  the component so the wording is unit-tested. */
export function countdownLabel(
  status: string,
  start: string | null | undefined,
  now: number,
): string | null {
  if (status === "live" || status === "settled") return null;
  const days = daysUntilStart(start, now);
  if (days == null) return null;
  if (days === 0) return "Starts today";
  return `Starts in ${days} day${days === 1 ? "" : "s"}`;
}

/** A readable event date range (either bound optional). */
export function eventDateRange(
  start?: string | null,
  end?: string | null,
): string | null {
  const fmt = (d: string) => {
    const dt = new Date(d);
    return Number.isNaN(dt.getTime())
      ? d
      : dt.toLocaleDateString("en-US", { month: "short", day: "numeric" });
  };
  if (start && end) return `${fmt(start)} – ${fmt(end)}`;
  if (start) return fmt(start);
  if (end) return fmt(end);
  return null;
}
