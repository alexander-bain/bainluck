/**
 * ═══ #9799: AN NL GAME'S RAIL DEALT TWO AMERICAN LEAGUE AWARDS ═══
 *
 * Production 2026-09-30, `/events/15321946` Cubs @ Padres (NL Wild Card) at
 * 390px: `MORE MLB · 4` drew `AL Reliever of the Year Winner?` and `MLB: AL
 * Platinum Glove Winner` — half the rail, about a league neither side plays in.
 *
 * The MLB rail's feed rank is the same on every MLB page (#5973), and it is
 * heavy with league-scoped awards. A card naming ONLY the other league cannot be
 * about this game: neither side can win it, and no player on the field can.
 *
 * ## What this does and does not drop
 *
 * It drops a market only when BOTH sides carry the same league
 * (`standings.conference`, read from the payload, never guessed from the team
 * name) AND the market's name names the other league and not this one. So:
 *
 * - an interleague game (Nationals v Tigers, or the World Series) drops nothing,
 *   because both leagues are this game's business;
 * - a side with no conference drops nothing — an unknown is not a league;
 * - `World Series MVP`, `RBI Leader` and anything naming no league stay;
 * - a name that names both leagues stays.
 *
 * #5973 warned that narrowing this rail can take the section off a page. This
 * cannot empty the narrow query silently: `RelatedByTag` filters before it
 * slices, and a narrow query left with nothing falls back to the wide one.
 *
 * MLB only, because it is the only league whose two halves are named in market
 * titles this way and whose conference strings were measured. Another league is
 * one row in `LEAGUE_HALVES`, added when its names are read off production.
 */
const LEAGUE_HALVES: { conference: string; names: RegExp }[] = [
  { conference: "American League", names: /\b(?:AL|ALCS|ALDS|American League)\b/ },
  { conference: "National League", names: /\b(?:NL|NLCS|NLDS|National League)\b/ },
];

/** The one league both sides play in, or `null` when there is not exactly one. */
export function sharedLeague(
  conferences: (string | null | undefined)[],
): string | null {
  if (conferences.length === 0) return null;
  const first = conferences[0];
  if (!first) return null;
  if (!conferences.every((c) => c === first)) return null;
  return LEAGUE_HALVES.some((h) => h.conference === first) ? first : null;
}

/** True when `name` names only a league other than `league`. */
export function namesOnlyTheOtherLeague(
  name: string | null | undefined,
  league: string | null,
): boolean {
  if (!name || !league) return false;
  const ours = LEAGUE_HALVES.find((h) => h.conference === league);
  if (!ours) return false;
  if (ours.names.test(name)) return false;
  return LEAGUE_HALVES.some((h) => h !== ours && h.names.test(name));
}
