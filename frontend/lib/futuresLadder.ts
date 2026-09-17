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
 * True when a rung set wants the roomy label track — any label that is not a short
 * numeric threshold. Dates ("Before October", "2029 or later") need it; "≥ 80"
 * does not.
 */
export function ladderNeedsWideLabels(rungs: readonly QuantityRung[]): boolean {
  return rungs.some((r) => r.label.trim().length > 8);
}
