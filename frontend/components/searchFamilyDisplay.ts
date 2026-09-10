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

/** Roughly how many characters of a row title survive at 390px once the answer
 *  and date columns have taken their share. Measured, not guessed: #4136 read
 *  `Colorado Rockies vs. New York Yankees - 9th Inning Winner` rendering as
 *  `Colorado Rockies v…` on production, which is 19 visible characters.
 *
 *  It is only ever used as a COLLISION THRESHOLD — "could these two rows look
 *  the same?" — never to cut a string. The cutting stays in CSS, where it
 *  belongs, so this number being a few characters off changes which rows get
 *  the treatment and never produces a wrong-looking row. */
export const FAMILY_ROW_VISIBLE_CHARS = 20;

/** Longest tail we are willing to reserve. Past this the tail would eat the
 *  whole row and the reader would lose the matchup instead of the suffix —
 *  trading one unreadable row for another. */
const MAX_RESERVED_TAIL = 30;

function commonPrefixLength(a: string, b: string): number {
  const n = Math.min(a.length, b.length);
  let i = 0;
  while (i < n && a[i] === b[i]) i++;
  return i;
}

/** Shortest tail worth reserving. Two rows can differ by a single character
 *  (`… - Winner A` / `… - Winner B`); reserving just `A` does technically tell
 *  them apart, but `Colorado Rockies vs…A` is not something to show a person.
 *  Below this we step back another word so the tail carries its own sense. */
const MIN_RESERVED_TAIL = 4;

/** Split point at or before `at`, snapped back to a word boundary so a reserved
 *  tail never starts mid-word (`s Winner` instead of `9th Inning Winner`), and
 *  then back another word if what survives is too short to read. */
function snapToBoundary(s: string, at: number): number {
  let from = at - 1;
  for (let guard = 0; guard < 8; guard++) {
    const sp = s.lastIndexOf(" ", from);
    if (sp <= 0) return 0;
    const cut = sp + 1;
    if (s.length - cut >= MIN_RESERVED_TAIL) return cut;
    from = sp - 1; // strictly before this space, or the search never advances
  }
  return 0;
}

/**
 * #4136: give every row in ONE family card a title split into a head that may be
 * truncated and a tail that must not be.
 *
 * The defect this exists for: `truncate` always keeps the front of a string, so
 * when two rows in a card share a long prefix it keeps the bytes they SHARE and
 * drops the only bytes that tell them apart. Production served
 * `… - First 5 Innings Winner` and `… - 9th Inning Winner` in one card and both
 * rendered `Colorado Rockies v…` — same visible text, 68% and 8%.
 *
 * So: two rows COLLIDE when they agree on more leading characters than a row can
 * show. For a colliding row the shared run becomes the head (CSS may eat it) and
 * everything after it becomes a reserved tail. A row that collides with nothing
 * is returned whole and renders exactly as it does today — which is what keeps
 * this safe to put under every search result.
 *
 * Deliberately NOT keyed on a separator (` - `, `: `). `Istanbul 3: Skatov vs
 * Erel` and `Istanbul 3: Erel vs Albot` share a separator-delimited head but
 * diverge at character 12, well inside what a row shows, so they need no help;
 * a separator rule would have "fixed" them into `Istanbul 3:…Skatov vs Erel` for
 * nothing. The question is whether the reader can tell the rows apart, and only
 * the shared-prefix length answers that.
 */
export function familyRowTitles(names: string[]): { head: string; tail: string }[] {
  const cleaned = names.map(cleanName);
  return cleaned.map((name, i) => {
    let lcp = 0;
    for (let j = 0; j < cleaned.length; j++) {
      if (j === i) continue;
      const n = commonPrefixLength(name, cleaned[j]);
      if (n >= FAMILY_ROW_VISIBLE_CHARS && n > lcp) lcp = n;
    }
    // `lcp >= name.length` means this row is entirely contained in the run it
    // shares with a sibling — an exact duplicate, or the shorter of a pair like
    // "Rockies vs Yankees" / "Rockies vs Yankees - 9th Inning". There is nothing
    // after the shared bytes to reserve, so there is no split to make. (The
    // LONGER row of such a pair still gets its tail; only this one is exempt.)
    if (!lcp || lcp >= name.length) return { head: name, tail: "" };
    const cut = snapToBoundary(name, lcp);
    const tail = name.slice(cut);
    // A tail that is empty (the rows are identical), that is the whole string
    // (nothing shared survived the snap), or that is too long to reserve, means
    // there is no split worth making — render the row as it is today.
    if (!tail || !cut || tail.length > MAX_RESERVED_TAIL) return { head: name, tail: "" };
    return { head: name.slice(0, cut), tail };
  });
}

/** Trailing join characters left dangling on a hoisted head (`… Yankees - `).
 *  Only ever applied to a string that is about to be shown on its own line, so
 *  there is nothing after it for the separator to separate it from. */
function trimTrailingSeparator(s: string): string {
  return s.replace(/[\s–—\-:·,|]+$/, "");
}

/**
 * #4583: the subject every row of a card shares, or null if they do not share one.
 *
 * The defect this exists for: `familyRowTitles` reserves the tail and lets CSS eat
 * the head, which is correct when the head is the part a reader can spare. On the
 * live `yank` card all five rows split at the SAME point, so the head was not a
 * per-row string at all — it was one subject printed five times, and the row had
 * to shrink it to fit a tail beside it. Production rendered
 * `C 8th Inning Winner` / `C. 7th Inning Winner` / `C... 9th Inning Winner`:
 * a single character is not an abbreviation, it is the layout giving up.
 *
 * The head is only hoistable when EVERY row has one and they are all identical —
 * then showing it once loses nothing by construction, and each row gets the whole
 * width for the bytes that tell it apart. A card whose heads differ keeps today's
 * behaviour exactly, because there the head really is per-row information.
 *
 * Note this deliberately fixes the DUPLICATION rather than the shrink ratio. The
 * head/tail widths were tuned three times (#4136, #4518, #4545) and the current
 * order — head yields everything before the tail yields anything — is right; it
 * was being asked to fit two copies of the same string into one row.
 */
export function familySharedHead(
  titles: { head: string; tail: string }[],
): string | null {
  // A single row is never split (`familyRowTitles` returns it whole), so there is
  // no shared subject to lift out of one.
  if (titles.length < 2) return null;
  // Every row must have been split. A card mixing split and whole rows has no one
  // subject — the whole row's name would go missing from the header.
  if (titles.some((t) => !t.tail)) return null;
  const head = titles[0].head;
  if (titles.some((t) => t.head !== head)) return null;
  return trimTrailingSeparator(head) || null;
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
