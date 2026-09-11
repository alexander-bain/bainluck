/**
 * Prop-family grouping for the event props body (UX-P036, gap K14).
 *
 * Why this module exists: the backend builds every game prop's props_script key
 * as `f"{market_name}|{outcome_name}"` and sets `label = outcome_name`
 * (`backend/app/routes/events.py:4707`). So the STATISTIC is on the wire and the
 * label drops it — a live MLB game renders 81 rows reading "Tommy White: 4+"
 * with no way to tell a Hits+Runs+RBIs prop from a Hits prop. Measured on
 * Athletics @ Red Sox 2026-08-09: 73 of 81 rows named no statistic, and three
 * families were interleaved into one flat list.
 *
 * `routes/events.py` belongs to the latency lane (#1494), so this recovers the
 * family CLIENT-SIDE from the key that is already paid for.
 *
 * PURE: no I/O, no React, no DB.
 */

import { childTitleRemainder } from "./otherMarketGroups";

/** Separator the backend uses between market name and outcome name in a key. */
export const FAMILY_SEPARATOR = "|";

/**
 * The family (market name) encoded in a props_script key, or null when the key
 * carries none.
 *
 * Null is the IMPORTANT case, not the edge case: the concept-page consumer
 * (`app/event/[domain]/[slug]/page.tsx`, golf/combat) builds marks with
 * `key: mid` — a NUMBER. Those must keep rendering exactly as they do today, so
 * anything without a parseable family degrades to "ungrouped".
 */
export function propFamilyName(key: string | number): string | null {
  if (typeof key !== "string") return null;
  const i = key.indexOf(FAMILY_SEPARATOR);
  if (i <= 0) return null;
  const family = key.slice(0, i).trim();
  return family.length > 0 ? family : null;
}

/**
 * True when a props_script mark is not an outcome at all but an undecomposed
 * nested child market's TITLE (gotcha #18, the Polymarket parent).
 *
 * #3874: on `/events/15305579` (Andreeva v Potapova, US Open) THE SCRIPT · Props
 * rendered NINE rows all reading `US Open WTA: Mirra Andreeva vs Anasta…` against
 * nine different percentages — every row restating the card's own header and then
 * clipping before the words that would tell them apart. There is no reading of
 * that card that says what any number is about.
 *
 * The decision this expresses is NOT new and is deliberately not re-derived here:
 * `otherMarketGroups.buildMarketSection` already drops exactly this row class from
 * the Additional Markets card ONE CARD LOWER ON THE SAME PAGE, and
 * {@link childTitleRemainder} is that decision, already exported. This composes it
 * with the key format {@link propFamilyName} already owns — the parent title only
 * reaches this surface inside the key, because the backend sets
 * `label = outcome_name` and keeps `market_name` on the left of the separator.
 *
 * **Drop, not shorten** — the point #3557 is open about. De-prefixing makes these
 * rows shorter but cannot make them readable: `Set Handicap +/-1.5 — 64%` names a
 * question and no side of it, and the side is not in the wire text to recover.
 * On the measured payload it is also the safer answer, because the prices look
 * re-used, not merely unsided: eight of the nine rows carried only four distinct
 * values, with `Set Handicap +/-1.5` and `Set 2 Winner` both `0.645`. And the
 * properly sided `Set 2 Winner` in the SAME response reads `0.775` — 65% against
 * 78%, one question and 13 points, both cards on screen at once. (Pregame the
 * split is masked, because THE SCRIPT renders `pregame_mark` rather than
 * `current`: 76% against 78%. It surfaces the moment the match goes live.)
 *
 * False for everything that is a real outcome. A numeric key (the concept page
 * builds marks with `key: mid`) carries no family, so it can never match.
 *
 * **This judges the LABEL, so only apply it where the label is all the reader
 * gets.** The `/events/[id]` mapping builds every mark without `kind`, `question`
 * or `outcomes`, so all of them render as a bare `PropRow` whose entire text is
 * `label` — which is why the drop is unambiguously right there. A caller whose
 * marks carry a shape (the concept page's `kind: "field" | "ladder"`) routes them
 * to a card that renders `question` and NAMED outcomes instead, and such a mark
 * can be perfectly readable while still having a prefixed label. Do not filter
 * those on this predicate alone; that surface is deliberately left untouched.
 */
export function isChildTitleMark(mark: {
  key: string | number;
  label?: string | null;
}): boolean {
  const family = propFamilyName(mark.key);
  if (family == null) return false;
  return childTitleRemainder(family, mark.label) !== null;
}

/**
 * The boilerplate prefix shared by every family name, ending at a `": "`
 * boundary — "Boston vs A's: Hits" and "Boston vs A's: Home Runs" share
 * "Boston vs A's: ", which is the matchup the user is already looking at.
 *
 * Requires **two or more distinct names**: sharedness across families is the
 * only evidence that a prefix is boilerplate rather than meaning. With a single
 * family, "Best Picture: Winner" would otherwise be stripped to "Winner".
 *
 * Returns "" when there is nothing safe to strip.
 */
export function sharedFamilyPrefix(names: string[]): string {
  const distinct = Array.from(new Set(names));
  if (distinct.length < 2) return "";

  // Longest common character prefix across all names.
  let common = distinct[0];
  for (const name of distinct.slice(1)) {
    let i = 0;
    while (i < common.length && i < name.length && common[i] === name[i]) i += 1;
    common = common.slice(0, i);
    if (!common) return "";
  }

  // Retreat to the last ": " boundary so we never cut a word in half.
  const cut = common.lastIndexOf(": ");
  if (cut < 0) return "";
  const prefix = common.slice(0, cut + 2);

  // Never strip a name down to nothing.
  if (distinct.some((n) => n.slice(prefix.length).trim().length === 0)) return "";
  return prefix;
}

/** Apply {@link sharedFamilyPrefix} to a list of family names. */
export function stripSharedFamilyPrefix(names: string[]): string[] {
  const prefix = sharedFamilyPrefix(names);
  if (!prefix) return names;
  return names.map((n) => (n.startsWith(prefix) ? n.slice(prefix.length).trim() : n));
}

/** This event's two teams, as the page already knows them. */
export interface MatchupNames {
  home?: string | null;
  away?: string | null;
}

/**
 * Separators a venue puts between the two sides of a matchup title. `v` alone
 * is deliberately absent: it is a common word, and no measured payload uses it.
 */
const MATCHUP_SPLIT = /\s+(?:vs\.?|@)\s+/i;

function normalizeTeamText(s: string): string {
  return s
    .normalize("NFD")
    .replace(/[\u0300-\u036f]/g, "")
    .toLowerCase()
    .replace(/\s+/g, " ")
    .trim();
}

/**
 * True when `side` names `team`. Three forms are accepted because all three are
 * on the wire: the venue's short form as a prefix of our name ("Tampa Bay" →
 * "Tampa Bay Rays"), a MANGLED truncation of it ("Los Angeles R" → "Los Angeles
 * Rams", #5181), and the nickname tail on its own ("Rays").
 */
function sideNamesTeam(side: string, team: string): boolean {
  const s = normalizeTeamText(side);
  const t = normalizeTeamText(team);
  if (s.length < 3 || t.length < 3) return false;
  return t.startsWith(s) || t.endsWith(s);
}

/**
 * True when `head` names THIS event's matchup — both sides present, matching
 * the two teams in either order.
 *
 * Both sides are required, and they must name DIFFERENT teams. That is the
 * fail-safe: a market for some other fixture that has been mis-attached to this
 * event (a truth defect under notice 40) does NOT match, so it keeps its prefix
 * and stays visible to the reader instead of being silently disguised as one of
 * ours.
 */
function headNamesMatchup(head: string, home: string, away: string): boolean {
  const sides = head.split(MATCHUP_SPLIT);
  if (sides.length !== 2) return false;
  const [a, b] = sides;
  return (
    (sideNamesTeam(a, away) && sideNamesTeam(b, home)) ||
    (sideNamesTeam(a, home) && sideNamesTeam(b, away))
  );
}

/**
 * Drop the leading `"<away> vs <home>: "` from every family whose head names
 * this event's matchup.
 *
 * #4866: {@link sharedFamilyPrefix} takes ONE longest-common prefix across the
 * whole section, so it only fires when the section is homogeneous. Since #1735
 * un-suppressed the graded windows, a live MLB page carries two cohorts —
 * player props (`Drake Baldwin: Hits O/U 2.5`) and matchup-level markets
 * (`Tampa Bay vs Atlanta: Total Bases`) — whose common prefix is the empty
 * string. Measured on Tampa Bay @ Atlanta (`/events/15308050`): 91 group
 * headers, 33 of them repeating the matchup the hero already states.
 *
 * Why this is keyed on the EVENT'S OWN TEAMS and not on cohort sharedness: the
 * obvious generalisation — compute a prefix per `": "` head — reads well on the
 * matchup cohort and destroys the player cohort. `Drake Baldwin` heads seven
 * families on that same payload, so it clears any "shared ⇒ boilerplate"
 * threshold and the player's name, which IS the meaning of the row, is the
 * thing that gets stripped. Sharedness cannot tell boilerplate from meaning
 * here; only knowing what the page already says can.
 *
 * Index-preserving, so callers can zip the result against their own ordering.
 */
export function stripEventMatchupPrefix(
  names: string[],
  matchup?: MatchupNames | null,
): string[] {
  const home = matchup?.home?.trim();
  const away = matchup?.away?.trim();
  if (!home || !away) return names;

  return names.map((name) => {
    const i = name.indexOf(": ");
    if (i <= 0) return name;
    const remainder = name.slice(i + 2).trim();
    // Never strip a name down to nothing (same guard as sharedFamilyPrefix).
    if (!remainder) return name;
    return headNamesMatchup(name.slice(0, i), home, away) ? remainder : name;
  });
}

export interface PropFamilyGroup<T> {
  /**
   * Display name, already prefix-stripped. `null` means "no family" — the
   * caller must render these exactly as it did before grouping existed.
   */
  name: string | null;
  items: T[];
}

/**
 * Partition items into family groups, preserving the caller's ordering both
 * BETWEEN groups (by first appearance) and WITHIN them.
 *
 * When no item carries a family, returns a single `{ name: null }` group — so a
 * caller can branch on `groups.length === 1 && groups[0].name === null` and emit
 * its original markup untouched.
 */
export function groupByPropFamily<T>(
  items: T[],
  keyOf: (item: T) => string | number,
  matchup?: MatchupNames | null,
): PropFamilyGroup<T>[] {
  const named = new Map<string, T[]>();
  const unfamiliar: T[] = [];
  const order: string[] = [];

  for (const item of items) {
    const family = propFamilyName(keyOf(item));
    if (family == null) {
      unfamiliar.push(item);
      continue;
    }
    let bucket = named.get(family);
    if (!bucket) {
      bucket = [];
      named.set(family, bucket);
      order.push(family);
    }
    bucket.push(item);
  }

  if (order.length === 0) return [{ name: null, items }];

  // #4866 (per-family, needs the event's teams) composed with the section-wide
  // longest-common prefix. Both are index-preserving, so the zip with `order`
  // below still holds.
  //
  // The order of these two is NOT load-bearing on any shape we serve, and that
  // is a measured claim, not an assumption: swapping them kills no test and
  // changes no header on either specimen payload. They only diverge when a head
  // NESTS one inside the other ("Game: Tampa Bay vs Atlanta: Hits"), which no
  // venue sends today. Matchup-first is kept because it lets the matchup rule
  // read the venue's original head rather than one another rule has already
  // trimmed — so if a nested head ever does arrive, the rule that fails is the
  // one that fails safe (a prefix stays, nothing is wrongly stripped).
  const display = stripSharedFamilyPrefix(
    stripEventMatchupPrefix(order, matchup),
  );
  const groups: PropFamilyGroup<T>[] = order.map((family, i) => ({
    name: display[i],
    items: named.get(family) as T[],
  }));

  // Mixed payloads shouldn't happen, but a family-less remainder must never be
  // dropped on the floor — it trails the named groups, in its original order.
  if (unfamiliar.length > 0) groups.push({ name: null, items: unfamiliar });
  return groups;
}
