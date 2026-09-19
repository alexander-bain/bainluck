/**
 * The event's own headline question, served back to it as a prop (#7064).
 *
 * WHAT THE READER SAW. On `/events/15314172` — Red Sox @ Rays, live — THE DIVERGENCE opened with
 * the game itself, listed twice, under two differently-worded headings, directly below a hero that
 * gave a third number:
 *
 *   hero, top of page                      Boston 55%   Tampa Bay 45%
 *   "BOSTON VS TAMPA BAY"          (kalshi)  Boston 56%   Tampa Bay 46%   ← sums to 102%
 *   "BOSTON RED SOX VS. TAMPA BAY RAYS" (polymarket)  Boston 55%
 *
 * Two market rows, two venues, ONE question — and the hero had already answered it. That is Alex's
 * standing ruling head-on (*the blend is the product — one number per question; source divergence
 * is a data bug, not a feature to show*), and THE DIVERGENCE is not a deliberate comparison
 * surface.
 *
 * WHY THE RULE KEYS ON THE MATCHUP AND NOT ON THE WORDING. The only difference between the two
 * offenders is how each venue spells the same two clubs. A rule that matches a venue's phrasing
 * fixes the one in the screenshot and goes on contradicting the other — and a third venue's
 * wording reintroduces it. So the question asked here is structural: **does this market's name
 * parse as the bare matchup of THIS event's two sides?** Both spellings answer yes; nothing else on
 * a real payload does.
 *
 * WHY THE DECISION IS PER-MARKET, NOT PER-ROW. Suppressing *rows whose outcome names a side* would
 * orphan soccer's "Draw" leg: the two team legs vanish and the third stays behind, answering a
 * question whose siblings are gone. The market is judged once and all of its rows go with it.
 *
 * WHY IT FAILS OPEN. Every guard here refuses in the direction of KEEPING the row — a market name
 * carrying a colon is never a bare matchup, an unparseable key is kept, a missing side name means
 * no match. This filter DELETES something a reader can currently see, so the safe direction is
 * "renders exactly as it does today". A venue that prefixed a league ("MLB: Boston vs Tampa Bay")
 * would not be caught, and that is the deliberate choice, not an oversight.
 *
 * SCOPE. This is the ux half of #7064. The backend classifies these rows into `player_props[]`
 * (`routes/events.py`, not ux's file set under notice 41); the page is in any case the only place
 * that knows the hero has already answered the question. #4646 is the same disease on the
 * "Bigger Picture" rail (`isRelevantGameProp` in `components/RelatedFutures.tsx`) and can adopt
 * `isEventOwnMoneylineMarket` unchanged — it is exported for that and is not otherwise used there
 * yet.
 *
 * PURE: no I/O, no React, no DB.
 */

import { propFamilyName } from "./propFamily";

/**
 * The separators a venue puts between the two sides of a fixture.
 *
 * `vs.` and `v.` carry an optional full stop because Polymarket writes "Boston Red Sox vs. Tampa
 * Bay Rays" where Kalshi writes "Boston vs Tampa Bay" — the exact difference that made one question
 * into two rows.
 */
const SIDE_SEPARATOR = /^(.+?)\s+(?:vs\.?|v\.?|at|@)\s+(.+)$/i;

/** Case, punctuation and whitespace folded, so "vs." and "Vs" compare equal to "vs". */
function fold(value: string | null | undefined): string {
  return (value ?? "")
    .toLowerCase()
    .replace(/[.,]/g, " ")
    .replace(/\s+/g, " ")
    .trim();
}

/**
 * Does `label` name `team`?
 *
 * The same convention `nomineeShowsFace` encodes in `lib/myStuffAwards.ts`: a venue names a club
 * either in full ("Boston Red Sox") or by the short form ("Boston"), which is a whole-word prefix
 * or suffix of the full name. The space in the affix tests is load-bearing — without it "Bo" would
 * name Boston.
 */
export function labelNamesSide(
  label: string | null | undefined,
  team: string | null | undefined,
): boolean {
  const l = fold(label);
  const t = fold(team);
  if (!l || !t) return false;
  return l === t || t.startsWith(l + " ") || t.endsWith(" " + l);
}

/**
 * Is `marketName` the bare matchup of this event's two sides — i.e. the event's own moneyline?
 *
 * Both sides must be named, and they must name DIFFERENT sides, so a market that mentions one club
 * twice is not swept up. A colon means the name carries a qualifier ("Boston vs Tampa Bay: Race to
 * 14 Points"), which is a real market about the game and not the game's own question.
 */
export function isEventOwnMoneylineMarket(
  marketName: string | null | undefined,
  homeTeam: string | null | undefined,
  awayTeam: string | null | undefined,
): boolean {
  const name = (marketName ?? "").trim();
  if (!name || name.includes(":")) return false;
  if (!fold(homeTeam) || !fold(awayTeam)) return false;

  const parts = name.match(SIDE_SEPARATOR);
  if (!parts) return false;
  const [, first, second] = parts;

  return (
    (labelNamesSide(first, awayTeam) && labelNamesSide(second, homeTeam)) ||
    (labelNamesSide(first, homeTeam) && labelNamesSide(second, awayTeam))
  );
}

/** As much of a `game-markets` payload as this module reads. */
export interface OwnMoneylinePayload {
  home_team: string;
  away_team: string;
  player_props: { market_name: string }[];
  props_script?: { key: string | number }[];
}

/**
 * The payload with the event's own moneyline removed from BOTH arrays it reaches.
 *
 * `props_script[]` matters as much as `player_props[]` and is easy to miss: it carries the same
 * market as `"Boston vs Tampa Bay|Boston"` / `"…|Tampa Bay"`, so filtering only the props list
 * leaves THE SCRIPT and WHAT HIT still answering the question — on a settled game, printing the
 * game's own result as a prop that "hit". One key format (`market_name|outcome_name`, read with the
 * house helper `propFamilyName`) lets one predicate serve both.
 *
 * Returns the payload UNCHANGED BY REFERENCE when nothing is dropped, which is the overwhelmingly
 * common case. That is not a micro-optimisation: the event page passes this object as
 * `resetKey={gameMarkets}` to its section error boundaries, so handing back a fresh object every
 * render would reset them continuously.
 */
export function withoutEventOwnMoneyline<T extends OwnMoneylinePayload>(payload: T): T {
  const isOwn = (marketName: string | null | undefined) =>
    isEventOwnMoneylineMarket(marketName, payload.home_team, payload.away_team);

  const props = payload.player_props ?? [];
  const keptProps = props.filter((row) => !isOwn(row?.market_name));

  const script = payload.props_script;
  const keptScript = script
    ? script.filter((mark) => {
        // A key with no parseable family is the concept page's numeric key — keep it. Anything we
        // cannot read, we do not delete.
        const family = propFamilyName(mark?.key);
        return family === null || !isOwn(family);
      })
    : script;

  const propsUnchanged = keptProps.length === props.length;
  const scriptUnchanged = !script || (keptScript ?? []).length === script.length;
  if (propsUnchanged && scriptUnchanged) return payload;

  return {
    ...payload,
    player_props: keptProps,
    ...(script ? { props_script: keptScript } : {}),
  };
}
