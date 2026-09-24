/**
 * One PLAYER AWARDS row per person on an event page's team card — #8360.
 *
 * The Bigger Picture team cards group award markets by nominee. They grouped on
 * the raw `outcome_name`, so two Kalshi series that spell one player two ways
 * became two people. Measured on production 2026-09-23, `/events/15318167`:
 * `KXMLBAWARDFIN-26ALMVP-MGARCIA11` names "Maikel Garcia" and
 * `KXMLBALMVP-26-MGAR` names "Maikel García", and the Royals card printed
 *
 *   Maikel Garcia   MVP Finalist 5%
 *   Maikel García   MVP 1%
 *
 * The key is the accent-folded name (`foldForSearch`, which also covers ø/ł/ß —
 * letters that are their own codepoints and survive a bare NFD strip). The
 * printed name prefers a spelling that carries its accents: the venue that
 * wrote "García" wrote the player's name; the one that wrote "Garcia" wrote an
 * ASCII approximation of it.
 */
import { foldForSearch } from "@/lib/contenderChart";

export function playerAwardKey(name: string | null | undefined): string {
  return foldForSearch((name || "").replace(/\s+/g, " "));
}

function hasAccents(name: string): boolean {
  return foldForSearch(name) !== name.toLowerCase().trim();
}

export interface PlayerAwardRow {
  name: string;
  awards: Array<{ label: string; prob: number }>;
}

/**
 * Group award entries by player, awards sorted high→low within a player and
 * players sorted by their best award. Input order decides nothing except the
 * printed name between two equally-accented spellings (first seen wins).
 */
export function groupAwardsByPlayer(
  entries: Array<{ name: string | null | undefined; label: string; prob: number }>,
): PlayerAwardRow[] {
  const byKey = new Map<string, PlayerAwardRow>();
  for (const e of entries) {
    const name = (e.name || "").trim();
    const key = playerAwardKey(name);
    const row = byKey.get(key);
    if (!row) {
      byKey.set(key, { name, awards: [{ label: e.label, prob: e.prob }] });
      continue;
    }
    if (!hasAccents(row.name) && hasAccents(name)) row.name = name;
    row.awards.push({ label: e.label, prob: e.prob });
  }
  return [...byKey.values()]
    .map((r) => ({ name: r.name, awards: r.awards.sort((a, b) => b.prob - a.prob) }))
    .sort((a, b) => (b.awards[0]?.prob ?? 0) - (a.awards[0]?.prob ?? 0));
}
