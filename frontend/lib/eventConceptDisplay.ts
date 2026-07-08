// #999 Event Concept Pages (slice 1) — pure display helpers for /event/[key].
// Extracted so the rendering logic is unit-tested without mounting the page.
// D1 binds: probabilities only, never odds.

import type {
  EventConceptCompetitor,
  EventConceptChild,
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
