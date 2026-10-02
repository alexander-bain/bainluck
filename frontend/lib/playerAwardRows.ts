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

const TRAILING_CLUB_TAG = /\s*\(([A-Z]{2,4})\)\s*$/;

/**
 * #10188 — the name with a trailing club tag removed, but ONLY when the tag is
 * the card's own club.
 *
 * Kalshi disambiguates namesakes in some series and not others: the Dodgers'
 * Max Muncy is "Max Muncy (LAD)" in `KXMLBAWARDFIN-26NLMVP-MMUNCY13`,
 * `KXMLBNLCSMVP-26-MMUNCY13` and `KXMLBWSMVP-26-MMUNCY13`, and plain
 * "Max Muncy" in `KXMLBNLMVP-26-MMUN`. On the Dodgers card (`/events/15323083`,
 * 2026-10-02) that printed him as two people. On his own club's card the tag
 * says nothing the card header does not, so it is dropped for the key AND the
 * printed name. A tag naming any OTHER club is kept as written: that row is a
 * claim about a different person (the Athletics have a Max Muncy too, #8072),
 * and it must never be folded into this club's namesake.
 */
export function withoutOwnClubTag(
  name: string,
  ownClub: string | null | undefined,
): string {
  const own = (ownClub || "").trim().toUpperCase();
  if (!own) return name;
  const m = TRAILING_CLUB_TAG.exec(name);
  return m && m[1] === own ? name.slice(0, m.index) : name;
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
 * `ownClub` is the card's team tag (`league_context.<side>.short_name`, e.g.
 * "LAD"); see `withoutOwnClubTag`.
 */
export function groupAwardsByPlayer(
  entries: Array<{ name: string | null | undefined; label: string; prob: number }>,
  ownClub?: string | null,
): PlayerAwardRow[] {
  const byKey = new Map<string, PlayerAwardRow>();
  for (const e of entries) {
    const name = withoutOwnClubTag((e.name || "").trim(), ownClub);
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
