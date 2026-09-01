// #1602 (UX-P034): bound the matchups-&-props rail on a large field.
//
// The tennis concept page renders a 1440 x 51,953px document — ~58 desktop
// viewports of continuous scroll. The mechanism, measured from the live
// envelope (`/api/event/event:tennis:...`, 2026-08-09):
//
//   1,637 children, NONE of which carry `kind`, so the page's
//   `children.filter(c => c.kind === "prop")` split sends ALL of them to
//   MatchupsRail (EventProps renders null; `props_script` is empty).
//   splitChildren -> 893 live / 744 settled. The settled tail is already inside
//   a collapsed <details> and costs no height; the 893 live cards render flat in
//   one 3-column grid = 298 rows x ~175px ~= 52,150px. That IS the wall.
//
// Alex ratified the shape 2026-08-09: COLLAPSE BY PROP FAMILY, collapsed by
// default. The families below are DERIVED FROM THAT CENSUS, not invented — they
// bucket 891/893 live and 742/744 settled children, leaving 2 in each fallback.
//
// Why a new name-regex table rather than reusing EventProps' `PROP_GROUPS`:
// PROP_GROUPS keys on `EventConceptChild.prop_type`, and NOT ONE child on this
// page carries that field, so extending it would be a literal no-op. It is also
// not replaced — `prop_type` IS set on UFC/golf/cycling concepts, where
// EventProps still serves it. This is the `golfRelatedSections.ts` precedent
// (ordered regex table + kept-last fallback) applied to a second rail.

export interface MatchupFamilyItem {
  market_name?: string;
  name?: string;
}

/**
 * Ordered — first match wins, so the specific families precede the general
 * ones. "Completed matches" MUST stay first: those names also contain "vs" and
 * would otherwise be swallowed by the match-winner fallback.
 */
export const MATCHUP_FAMILIES: { key: string; label: string; test: RegExp }[] = [
  { key: "completed", label: "Completed matches", test: /completed match/i },
  {
    key: "appearance",
    label: "Around the tournament",
    test: /\battend\b|\bto play in\b|\bplay in the\b|\bannouncers?\b|\bwithdraw/i,
  },
  { key: "set_winner", label: "Set winners", test: /\bset\s*\d*\s*winner\b/i },
  { key: "set_handicap", label: "Set handicaps", test: /\bset\s*(handicap|spread)\b/i },
  { key: "set_total", label: "Set totals", test: /\btotal sets\b|\bsets?\s*o\/?u\b/i },
  {
    key: "game_total",
    label: "Combined score",
    test: /\btotal games\b|\bgames?\s*o\/?u\s*\d|\bmatch\s*o\/?u\s*\d|\bgames?\s*over\/under\b/i,
  },
  {
    key: "game_spread",
    label: "Winning margin",
    test: /\bgame\s*(spread|handicap)\b|[-+]\d+(\.\d+)?\s*games\b/i,
  },
  {
    key: "exact_score",
    label: "Exact match score",
    test: /\bexact\s*(match\s*)?score\b|\bcorrect score\b/i,
  },
  {
    key: "serve",
    label: "Serve & tiebreaks",
    test: /\baces\b|\bdouble faults\b|\btiebreaks?\b|\bbreaks? of serve\b/i,
  },
  { key: "retirement", label: "Retirements", test: /\bretire|\bwalkover\b/i },
];

/** Anything shaped "A vs B" that matched no specific family is the match itself. */
export const MATCHUP_WINNER_FAMILY = { key: "match_winner", label: "Match winners" };

/** Kept last, and never dropped — every child lands somewhere. */
export const MATCHUP_FAMILY_FALLBACK = { key: "other", label: "Other markets" };

/**
 * Grouping engages only ABOVE this many cards in a single rail.
 *
 * The both-direction guard of gotcha #43 lives here. At 24 cards a desktop
 * 3-column grid is 8 rows (~1,400px) — still scannable, and turning it into
 * eight collapsed headers each holding one row would be strictly worse. A UFC
 * card (~12 fights) and a Tour de France GC (24 markets) therefore render
 * EXACTLY as they do today, untouched.
 */
export const MATCHUP_GROUPING_THRESHOLD = 24;

/** The family key for one market name. Pure; exported for tests. */
export function matchupFamilyKey(name: string): string {
  const n = name || "";
  const hit = MATCHUP_FAMILIES.find((f) => f.test.test(n));
  if (hit) return hit.key;
  // `\bv\.\s` catches "A v. B"; the common form is "vs" / "vs.".
  if (/\bvs\.?\b|\bv\.\s/i.test(n)) return MATCHUP_WINNER_FAMILY.key;
  return MATCHUP_FAMILY_FALLBACK.key;
}

/**
 * Bucket a rail's children into ordered, non-empty families.
 *
 * Returns `null` when the rail should render FLAT, exactly as before — either
 * the field is small enough that grouping only adds chrome, or every card lands
 * in one family so the split would produce a single header wrapping the whole
 * grid. Callers must treat `null` as "unchanged behaviour", which is what keeps
 * normal-sized events out of this code path entirely.
 *
 * Nothing is ever dropped: the union of the returned groups is the input.
 * Input order is preserved within each group.
 */
export function groupMatchupsByFamily<T extends MatchupFamilyItem>(
  items: T[],
): { key: string; label: string; items: T[] }[] | null {
  const all = items || [];
  if (all.length <= MATCHUP_GROUPING_THRESHOLD) return null;

  const buckets: Record<string, T[]> = {};
  for (const item of all) {
    const key = matchupFamilyKey(item.market_name || item.name || "");
    (buckets[key] ||= []).push(item);
  }

  const ordered = [...MATCHUP_FAMILIES, MATCHUP_WINNER_FAMILY, MATCHUP_FAMILY_FALLBACK];
  const groups = ordered
    .filter((f) => buckets[f.key]?.length)
    .map((f) => ({ key: f.key, label: f.label, items: buckets[f.key] }));

  // One family for the whole rail is a header around the same wall — not worth
  // the interaction cost, and it would hide a soccer bracket behind a click.
  return groups.length >= 2 ? groups : null;
}
