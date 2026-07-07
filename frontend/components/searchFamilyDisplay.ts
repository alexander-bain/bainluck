// #993 L2-42: pure display helpers for composed search family rows.
// Extracted so they're unit-testable (the jest setup does logic, not RTL) and so
// the D1 rule (probabilities only — never odds) is enforced in one place.

import type { FuturesFamily, FuturesMarket, FuturesOutcome } from "@/lib/types";

/** The leader outcome to display (leader-pick already applied server-side): the
 *  first top_outcome with a probability. */
export function leaderOutcome(market: FuturesMarket): FuturesOutcome | null {
  const outs = (market.top_outcomes ?? []).filter((o) => o.probability != null);
  return outs.length ? outs[0] : null;
}

/** "Cleveland Cavaliers 27%" — name + probability ONLY (D1: never odds). */
export function leaderLabel(market: FuturesMarket): string | null {
  const ld = leaderOutcome(market);
  if (!ld || ld.probability == null) return null;
  return `${ld.name} ${Math.round(ld.probability * 100)}%`;
}

/** Movement arrow only when |Δ24h| ≥ 2pts (0.02 on the 0-1 scale). */
export function movementArrow(
  mv: number | null | undefined,
): { up: boolean; points: number } | null {
  if (mv == null || Math.abs(mv) < 0.02) return null;
  return { up: mv > 0, points: Math.abs(Math.round(mv * 100)) };
}

/** Resolution date label only when it resolves within 30 days. */
export function resolutionLabel(date: string | null | undefined): string | null {
  if (!date) return null;
  const days = (new Date(date).getTime() - Date.now()) / 86_400_000;
  if (isNaN(days) || days < 0 || days > 30) return null;
  return new Date(date).toLocaleDateString(undefined, { month: "short", day: "numeric" });
}

/** Strip a trailing year / question mark for a cleaner row title. */
export function cleanName(name: string): string {
  return name.replace(/\s*\d{4}(-\d{2,4})?\s*\??$/, "").replace(/\?$/, "").trim() || name;
}

/** market_ids rendered inside families (headline + shown members) — filtered
 *  from the flat list so nothing double-renders. */
export function familyShownIds(families: FuturesFamily[]): Set<number> {
  const ids = new Set<number>();
  for (const fam of families) {
    ids.add(fam.headline.id);
    for (const m of fam.members) ids.add(m.id);
  }
  return ids;
}
