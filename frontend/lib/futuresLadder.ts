/**
 * futuresLadder — turn a `quantity` market's OWN outcomes into ladder rungs.
 *
 * Queue lane1-Q478 (TOP-PRODUCT-DEFECTS item 10). `QuantityGroup` already existed
 * and the detail page already imported it, but the only thing that could ever feed
 * it was the backend's `threshold_groups` payload — and `extract_threshold()` is
 * purely NUMERIC. A market whose rungs are dates ("Before April", "Before July",
 * "Before October", "Before 2027" — market 109349, "When will Apple release the
 * iPhone 18?") produces `threshold_groups == {}`, so the ladder never rendered and
 * the page fell through to the generic ranked table: rank badges 1-4 and avatar
 * circles reading "BA", "BJ", "BO", "B2".
 *
 * This builder needs no threshold parser at all. It reads the shape field
 * (`market_type`, #194) for WHETHER to draw a ladder, and two facts the payload
 * already carries for HOW to order it. Deliberately no new regex layer: re-deriving
 * shape from outcome names is the very defect this queue closes.
 */

import type { QuantityRung } from "@/components/QuantityGroup";

/** The minimum an outcome must carry to become a rung. */
export interface LadderOutcome {
  id: number;
  name: string;
  probability: number | null;
}

/**
 * Ordering for a quantity ladder, decided from fields the payload already has.
 *
 * A quantity market comes in two sub-kinds and they order differently:
 *
 *   - **Cumulative** ("Before July" ⊂ "Before October"; "≥ 80" ⊂ "≥ 60"). The rungs
 *     nest, so they are NOT mutually exclusive and their probabilities are monotone
 *     non-decreasing along the ladder *by construction*. Ascending probability IS
 *     the ladder order — nothing is inferred from the text.
 *   - **Disjoint bins** ("0-10", "10-20"). These ARE mutually exclusive and their
 *     probabilities carry no ordering information at all, so sorting by probability
 *     would scramble a timeline. Serve order is preserved instead.
 *
 * `mutually_exclusive` is an existing column on `FuturesMarket`, already on the
 * detail payload, and it is exactly the cumulative/disjoint distinction. Using it
 * beats guessing from names.
 */
export type LadderOrder = "cumulative" | "served";

export function ladderOrderFor(mutuallyExclusive: boolean | null | undefined): LadderOrder {
  // Default (null/undefined) is the conservative one: don't reorder what we were given.
  return mutuallyExclusive === false ? "cumulative" : "served";
}

/**
 * ── #4568, second half: WHAT BREAKS A PRICE TIE ON A DATE LADDER ──
 *
 * The filing's own specimen, `/futures/108559` ("When will OpenAI officially
 * announce an IPO?"), serves TWENTY-TWO rungs of which ELEVEN are priced at
 * exactly 1%. Ascending probability therefore decides nothing for half the
 * ladder, and the rows below it rendered in serve order — read top to bottom on
 * production 2026-09-09:
 *
 *     Jan 26 · Oct 25 · Apr 26 · Feb 26 · Mar 26 · Sep 26 · May 26 · Jul 26 ·
 *     Aug 26 · Oct 26 · Jun 26
 *
 * A scrambled timeline. `/futures/108555` (Starlink) does the same over nine
 * tied rungs plus five priceless ones.
 *
 * WHAT THIS DOES **NOT** DO: it does not order the ladder by date. Where two
 * rungs carry different prices the price still decides, exactly as before — a
 * cumulative ladder's prices are its ordering information and overriding them
 * would hide the incoherent quotes that are a TRUTH defect for another lane
 * (108559 prices "Before Dec 1, 2025" at 2% above "Before Oct 1, 2026" at 1%,
 * which is an arbitrage violation, not a sort bug). Only ties move.
 *
 * WHY A PARSER HERE AT ALL, when this module's own header says "deliberately no
 * new regex layer": that sentence is about re-deriving the market's SHAPE from
 * its outcome names, which is the defect Q478 closed and which is untouched —
 * shape still comes from `market_type`, order still from `mutually_exclusive`.
 * A tie is the one place where the payload has told us nothing, and the choice
 * is not "text vs field" but "text vs serve order", which is itself a guess the
 * old comment admitted to ("the source's ordering at least claims to be" a
 * fact).
 *
 * THE GRAMMAR IS THE HOUSE ONE, not a new one:
 * `backend/app/utils/discover_card_archetypes.py::_parse_date_bucket` already
 * parses these labels for the Discover date-bucket card, and this mirrors it —
 * the same lead words, the same month table, the same bare-month-needs-a-lead
 * refusal, the same "anchor month-only buckets to the earliest named year minus
 * one" rule, and the same ALL-OR-NOTHING contract ("a partial timeline is worse
 * than none"). ONE deliberate difference, measured: the Python accepts
 * `Month YYYY` but every Kalshi IPO rung reads `Before Jun 1, 2027`, so the day
 * is optional here. That is why the backend ladder never fired on these markets
 * and why the detail page cannot simply read a served sort value.
 */
const LADDER_MONTHS: Record<string, number> = {
  january: 1, february: 2, march: 3, april: 4, may: 5, june: 6,
  july: 7, august: 8, september: 9, october: 10, november: 11, december: 12,
  jan: 1, feb: 2, mar: 3, apr: 4, jun: 6, jul: 7, aug: 8,
  sep: 9, sept: 9, oct: 10, nov: 11, dec: 12,
};

/**
 * Leads and tails that point the ladder FORWARD from the label's date rather
 * than back to it ("After March", "2029 or later"). On such a ladder a later
 * date is a *smaller* probability, so ascending-by-date would be exactly
 * backwards. We do not attempt to reverse it — we refuse the whole ladder and
 * leave serve order alone. The refusal is the load-bearing half.
 */
// Two expressions rather than one alternation: `/^a|b$/` anchors only the
// branch the anchor sits in, and CodeQL's `js/regex/missing-regexp-anchor`
// refuses it on sight ("misleading operator precedence") — correctly, since the
// reading it warns about is the one a later editor would assume.
const FORWARD_LEAD_RE = /^\s*(?:after|from)\s+/i;
const FORWARD_TAIL_RE = /\s+or\s+(?:later|after)\s*$/i;

function pointsForward(label: string): boolean {
  return FORWARD_LEAD_RE.test(label) || FORWARD_TAIL_RE.test(label);
}

const LADDER_DATE_RE = new RegExp(
  "^\\s*" +
    "(?:(?<lead>before|by|prior\\s+to|on\\s+or\\s+before|in|during|after|from)\\s+)?" +
    "(?:" +
    "(?<month>[a-z]+)\\s+(?:(?<day>\\d{1,2})\\s*,?\\s*)?(?<year>\\d{4})" +
    "|(?<month2>[a-z]+)" +
    "|(?<yearonly>\\d{4})" +
    ")" +
    "(?:\\s+(?:or\\s+later|or\\s+earlier|or\\s+after|or\\s+before))?" +
    "\\s*$",
  "i",
);

/** A label parsed into the fields a chronological sort needs. */
export interface LadderDate {
  /** null for a bare month ("Before October") — the caller anchors it. */
  year: number | null;
  month: number;
  day: number;
}

/**
 * Parse one rung label into `(year|null, month, day)`, or null when it is not
 * confidently a date.
 *
 *     "Before Jun 1, 2027"  -> { year: 2027, month: 6,  day: 1 }
 *     "Before October"      -> { year: null, month: 10, day: 1 }
 *     "Before 2027"         -> { year: 2027, month: 1,  day: 1 }
 *     "March 2027"          -> { year: 2027, month: 3,  day: 1 }
 *     "≥ 80"                -> null
 *
 * The refusal is the load-bearing half (the Python says the same): this runs
 * over every rung of every cumulative ladder, and a false positive invents a
 * timeline out of labels that are not one.
 */
export function parseLadderDate(label: string | null | undefined): LadderDate | null {
  const m = LADDER_DATE_RE.exec(label ?? "");
  if (!m?.groups) return null;
  const g = m.groups;

  const inRangeDay = (raw: string | undefined): number | null => {
    if (raw === undefined) return 1;
    const day = Number(raw);
    return day >= 1 && day <= 31 ? day : null;
  };

  if (g.month && g.year) {
    const month = LADDER_MONTHS[g.month.toLowerCase()];
    const day = inRangeDay(g.day);
    const year = Number(g.year);
    if (!month || day === null || year < 1900 || year > 2999) return null;
    return { year, month, day };
  }
  if (g.month2) {
    const month = LADDER_MONTHS[g.month2.toLowerCase()];
    if (!month) return null;
    // A lone month with no qualifier ("October") is a label, not a cutoff;
    // require the before/by framing that makes it a bucket. Mirrors the Python.
    return g.lead ? { year: null, month, day: 1 } : null;
  }
  if (g.yearonly) {
    const year = Number(g.yearonly);
    if (year < 1900 || year > 2999) return null;
    return { year, month: 1, day: 1 };
  }
  return null;
}

/**
 * A chronological rank for every row, or null when this rung set is not a date
 * ladder we will reorder.
 *
 * Null (no tie-break, serve order stands) when ANY of:
 *   - fewer than two rows;
 *   - any label fails to parse — the all-or-nothing rule, because a timeline
 *     with three rungs placed and one guessed reads as authoritative and is not;
 *   - any label points forward ("After June", "2029 or later"), where ascending
 *     date is the wrong direction.
 */
function chronologicalRanks(
  rows: readonly LadderOutcome[],
): Map<LadderOutcome, number> | null {
  if (rows.length < 2) return null;

  const parsed: Array<[LadderOutcome, LadderDate]> = [];
  for (const row of rows) {
    if (pointsForward(row.name ?? "")) return null;
    const got = parseLadderDate(row.name);
    if (!got) return null;
    parsed.push([row, got]);
  }

  const years = parsed.map(([, d]) => d.year).filter((y): y is number => y !== null);
  let anchor: number | null;
  if (years.length > 0 && years.length < parsed.length) {
    // "Before October" beside "Before 2027" means October of the year BEFORE the
    // first dated bucket — the only reading under which it precedes it.
    anchor = Math.min(...years) - 1;
  } else if (years.length > 0) {
    anchor = null; // every rung dated; no anchor needed
  } else {
    anchor = 2000; // no year anywhere: relative month order is still a ladder
  }

  const ranks = new Map<LadderOutcome, number>();
  for (const [row, d] of parsed) {
    const year = d.year ?? anchor;
    if (year === null) return null;
    ranks.set(row, (year * 100 + d.month) * 100 + d.day);
  }
  return ranks;
}

/**
 * Build ladder rungs from a market's own outcomes.
 *
 * Labels are the outcome names verbatim — a date rung has no numeric value to
 * format, and inventing "≥ N" text for it would be a lie. `QuantityGroup`'s
 * `wideLabels` mode exists for exactly this ("the 'by WHEN' variant of the
 * kernel"), so the caller pairs the two.
 *
 * The returned rungs always carry an explicit `value` giving their final position,
 * so the caller can leave `QuantityGroup`'s own `sort` on without it re-deciding
 * the order: rung `value` is the index, ascending.
 */
export function buildOutcomeLadderRungs(
  outcomes: readonly LadderOutcome[],
  order: LadderOrder,
): QuantityRung[] {
  const rows = [...outcomes];

  if (order === "cumulative") {
    // Ascending probability. Where the prices differ they decide, and that is
    // unchanged.
    //
    // TIES: on a ladder whose rungs all parse as dates, a tie is broken
    // chronologically (#4568 — see `chronologicalRanks` above for why, and for
    // the three refusals that send us back to the old behaviour). Everywhere
    // else ties KEEP SERVE ORDER: `Array.prototype.sort` is stable (ES2019), so
    // returning 0 leaves the source's own order alone.
    //
    // What must never come back is tiebreaking on outcome ID. Market 109349
    // prices "Before April" and "Before July" identically at 1%, and its ids run
    // 1596640 = July, 1596641 = April — so insertion order renders **July above
    // April**, a backwards timeline on the exact market Q478 was about. Neither
    // rule below can reach an id.
    const chrono = chronologicalRanks(rows);
    rows.sort((a, b) => {
      const ap = a.probability ?? Number.POSITIVE_INFINITY;
      const bp = b.probability ?? Number.POSITIVE_INFINITY;
      if (ap !== bp) return ap - bp;
      if (!chrono) return 0;
      return (chrono.get(a) ?? 0) - (chrono.get(b) ?? 0);
    });
  }

  return rows.map((o, i) => ({
    key: o.id,
    label: o.name,
    probability: o.probability,
    value: i,
  }));
}

/**
 * ── #7398: THE HEADING OVER A CROSS-MARKET THRESHOLD LADDER ──
 *
 * `threshold_groups` is a dict keyed by a SCOPE KEY, and the detail page printed
 * that key as the section heading. A scope key is a grouping identifier, never
 * prose: `detect_threshold_groups` builds it from `group:<group_id>`, or from
 * `compute_threshold_stem`, which substitutes `#` for the numeral it collapses.
 * So `/futures/60653756` drew **`# OR BELOW`** over a 20-rung Treasury board and
 * `/futures/60775290` drew **`ABOVE #`** — an internal token on a reader's
 * screen (notice 34), while the sibling ladder on the same page is headed by a
 * sentence.
 *
 * THE RULE, and it is the one worth keeping: **a scope key is never a heading.**
 * It is applied to whatever we would print, not only to the key we were handed —
 * if `group_title` ever arrives as a scope key it is refused just the same.
 *
 * WHY THE ANSWER IS SOMETIMES NO HEADING AT ALL. The page's own `<h1>` is
 * `market.name`, and for a single-market group the payload's `group_title` IS
 * that name (measured on all three specimens, production 2026-09-20). Repeating
 * the question in small caps above its own rungs is not context, it is an echo,
 * so the ladder goes titleless exactly the way the "More outcomes" disclosure
 * two blocks down already does. A `group_title` that says something the H1 does
 * not — a cross-market group's event title — is real context and is kept.
 */
export function isThresholdScopeKey(key: string | null | undefined): boolean {
  const k = (key ?? "").trim();
  if (!k) return true;
  // `#` is `compute_threshold_stem`'s placeholder; `group:` is the explicit
  // group-id scope. Either one means we are holding a key, not a title.
  return k.toLowerCase().startsWith("group:") || k.includes("#");
}

/** Whitespace/case-insensitive, so an H1 echo is caught however it is spaced. */
function sameHeading(a: string, b: string | null | undefined): boolean {
  return a.trim().toLowerCase() === (b ?? "").trim().toLowerCase();
}

/** The two refusals of #7398, applied to whatever we are about to print. */
function printableHeading(
  candidate: string,
  pageTitle: string | null | undefined,
): string | undefined {
  const c = candidate.trim();
  if (!c) return undefined;
  if (isThresholdScopeKey(c)) return undefined;
  if (sameHeading(c, pageTitle)) return undefined;
  return c;
}

/**
 * ── #8019: THE RUNGS NAME THEIR OWN SUBJECT ──
 *
 * #7398 correctly refuses a scope key as a heading, and correctly answers "no
 * heading at all" when the only alternative echoes the page's `<h1>`. That
 * answer is right for ONE ladder on a page. It is wrong for thirty-two:
 * `/futures/58728338` ("Pro Football: Team Wins in First 8 Weeks") draws 32
 * consecutive `≥ 1 / ≥ 2 / ≥ 3` stacks, two of them identical, and nothing on
 * the page says which team any of them is about — while every outcome name in
 * the payload begins `Buffalo: `, `Pittsburgh: `, `Cleveland: `.
 *
 * So when the key and the group title have both been refused, the LAST place to
 * look is the rungs themselves: if every outcome name in this group carries the
 * same `"<subject>: "` prefix, that subject is what distinguishes this ladder
 * from its siblings, and it is the heading. It goes through the same two
 * refusals — a subject is not exempt from them.
 *
 * WHY THIS IS A FALLBACK AND NOT A PREFERENCE. It only ever fills a heading
 * that would otherwise be blank, so no ladder that reads correctly today can
 * change. Measured on production 2026-09-22: over a random 40 grouped markets,
 * 11 ladder groups derive no subject and are untouched; over the 9 open boards
 * whose outcomes are all `"<x>: <rung>"`, 217 of 217 ladder groups derive one
 * (longest "Deportivo De La Coruna", 22 chars — these are subjects, not prose).
 *
 * The subject is served verbatim. `/futures/58728387` prefixes two of its
 * groups `New York J: ` and `New York G: `, so those cards will read "New York
 * J" and "New York G" — Kalshi's own truncation, filed separately, and still
 * strictly more than the nothing a reader gets today.
 */
export function ladderSubjectHeading(
  outcomeNames: readonly (string | null | undefined)[] | undefined,
): string | undefined {
  if (!outcomeNames || outcomeNames.length === 0) return undefined;
  let subject: string | undefined;
  for (const name of outcomeNames) {
    const at = (name ?? "").indexOf(": ");
    // `at <= 0` covers both "no separator" and a name that OPENS with it, which
    // would make the subject empty.
    if (at <= 0) return undefined;
    const candidate = (name ?? "").slice(0, at).trim();
    if (!candidate) return undefined;
    if (subject === undefined) subject = candidate;
    else if (subject !== candidate) return undefined;
  }
  return subject;
}

/**
 * The reader-facing heading for one threshold ladder, or `undefined` for none
 * (`QuantityGroup`'s `title` is optional — omitted means no title row).
 */
export function thresholdLadderTitle(
  scopeKey: string,
  groupTitle: string | null | undefined,
  pageTitle: string | null | undefined,
  outcomeNames?: readonly (string | null | undefined)[],
): string | undefined {
  const candidate = isThresholdScopeKey(scopeKey) ? groupTitle ?? "" : scopeKey;
  return (
    printableHeading(candidate, pageTitle) ??
    printableHeading(ladderSubjectHeading(outcomeNames) ?? "", pageTitle)
  );
}

/**
 * ── #8167: THE SUBJECT IS NOT ALWAYS BEHIND A COLON ──
 *
 * #8019's rule reads the subject off a `"<subject>: "` prefix, which is Kalshi's
 * shape for a team-wins board. A SPREAD board writes the same fact as prose:
 * `/futures/59319183` ("San Diego vs Atlanta: Spread") serves
 *
 *     Atlanta wins by over 1.5 / 2.5 / 3.5 runs
 *     San Diego wins by over 1.5 / 2.5 / 3.5 runs
 *
 * — no colon anywhere, so every refusal in this file fires in turn (the stems
 * `atlanta wins by over #` / `san diego wins by over #` hold `#`, the
 * `group_title` echoes the `<h1>`, and `ladderSubjectHeading` finds no
 * separator) and the reader meets TWO IDENTICAL, COMPLETELY UNLABELLED cards
 * reading `≥ 1.5 / 2.5 / 3.5 runs` twice. Settled, every leg reads `0%` and the
 * two are literally pixel-alike (lane1b/517, production `83a20bc7`, 390px, two
 * independent boards).
 *
 * THE RULE. What distinguishes sibling ladders is whatever their outcome names
 * do NOT share. So: take each group's common leading words, then strip the
 * trailing run those prefixes all share. "Atlanta wins by over" and "San Diego
 * wins by over" both end "wins by over"; what is left is "Atlanta" and "San
 * Diego". No prose knowledge, no verb list, no market-type special case — the
 * page's own siblings say which words are the subject.
 *
 * WHY IT IS PAGE-LEVEL AND ALL-OR-NOTHING. The strip is a property of the set,
 * not of one card, and a rule that fires coherently or not at all cannot leave a
 * board half-labelled. It refuses unless it can name at least two DIFFERENT
 * subjects (one repeated subject distinguishes nothing, and an echo is what
 * #7398 exists to refuse), and it refuses anything longer than a subject —
 * 4 words / 24 chars, against #8019's measured longest of 22 ("Deportivo De La
 * Coruna"). A single group returns nothing: with no sibling there is nothing to
 * tell apart, and the `<h1>` already says it.
 *
 * It only ever fills a heading that is otherwise BLANK — `thresholdLadderTitle`
 * runs first and unchanged — so no ladder that reads correctly today moves.
 */
const MAX_SUBJECT_WORDS = 4;
const MAX_SUBJECT_CHARS = 24;

function splitWords(value: string): string[] {
  return value.trim().split(/\s+/).filter(Boolean);
}

function sameWord(a: string, b: string): boolean {
  return a.toLowerCase() === b.toLowerCase();
}

/**
 * The leading words every name in one group shares, in the first name's casing
 * (the payload's own — the stems are lowercased and would print "san diego").
 */
function commonPrefixWords(
  names: readonly (string | null | undefined)[],
): string[] | undefined {
  const lists = names.map((n) => splitWords(n ?? "")).filter((w) => w.length > 0);
  if (lists.length === 0) return undefined;
  let prefix = lists[0];
  for (const list of lists.slice(1)) {
    let i = 0;
    while (i < prefix.length && i < list.length && sameWord(prefix[i], list[i])) i++;
    prefix = prefix.slice(0, i);
    if (prefix.length === 0) return [];
  }
  return prefix;
}

/**
 * One subject per group — what tells these ladders apart — or `undefined` for
 * every group when they cannot be told apart honestly.
 */
export function ladderDistinguishingSubjects(
  groups: readonly (readonly (string | null | undefined)[])[],
): (string | undefined)[] {
  const none = groups.map(() => undefined);
  if (groups.length < 2) return none;

  const prefixes = groups.map((g) => commonPrefixWords(g));
  if (prefixes.some((p) => p === undefined || p.length === 0)) return none;
  const known = prefixes as string[][];

  // The strip is MAXIMAL, and a prefix stripped empty means "refuse", not "keep
  // the last word" (the empty subject is caught below). Stopping one word short
  // instead looks safer and is worse: given prefixes "wins by over" and "Atlanta
  // wins by over" — one side of a board whose payload omits its subject — it
  // keeps a verb as the heading and labels two cards "wins" and "Atlanta wins".
  // There is no honest subject there, so the honest answer is none.
  const maxStrip = Math.min(...known.map((p) => p.length));
  let strip = 0;
  while (strip < maxStrip) {
    const word = known[0][known[0].length - 1 - strip];
    if (!known.every((p) => sameWord(p[p.length - 1 - strip], word))) break;
    strip++;
  }

  const subjects = known.map((p) => p.slice(0, p.length - strip).join(" "));
  // EVERY subject distinct, not merely two of them. On a three-ladder board two
  // cards can strip to the same word while a third differs, and "at least two
  // are different" waves that through — which is the reported defect (two
  // identical headings) wearing a heading. All-or-nothing: if any pair collides
  // the whole page falls back to no headings rather than to a wrong one.
  if (new Set(subjects.map((s) => s.toLowerCase())).size !== subjects.length) return none;
  if (
    subjects.some(
      (s) =>
        !s || s.length > MAX_SUBJECT_CHARS || splitWords(s).length > MAX_SUBJECT_WORDS,
    )
  ) {
    return none;
  }
  return subjects;
}

/**
 * Every ladder heading on one page, in the order the groups are given.
 *
 * `thresholdLadderTitle` decides each card on its own first, exactly as before;
 * only a card left blank by all of its refusals falls through to the
 * page-level subject, and that goes through the same two refusals.
 */
export function thresholdLadderTitles(
  groups: readonly { stem: string; outcomeNames: readonly (string | null | undefined)[] }[],
  groupTitle: string | null | undefined,
  pageTitle: string | null | undefined,
): (string | undefined)[] {
  const subjects = ladderDistinguishingSubjects(groups.map((g) => g.outcomeNames));
  return groups.map(
    (g, i) =>
      thresholdLadderTitle(g.stem, groupTitle, pageTitle, g.outcomeNames) ??
      printableHeading(subjects[i] ?? "", pageTitle),
  );
}

/**
 * True when a rung set wants the roomy label track — any label that is not a short
 * numeric threshold. Dates ("Before October", "2029 or later") need it; "≥ 80"
 * does not.
 */
export function ladderNeedsWideLabels(rungs: readonly QuantityRung[]): boolean {
  return rungs.some((r) => r.label.trim().length > 8);
}
