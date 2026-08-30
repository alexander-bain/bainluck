/**
 * THE ILLIQUIDITY SIGNAL — one rule, one vocabulary, every surface.
 *
 * ═══ WHAT ALEX ASKED FOR (2026-08-28) ═══
 *
 * *"A really clean, universal signal for illiquidity"*, with three constraints
 * he named himself: the symbol **grades** (at least two levels, because
 * illiquidity is not uniform), the reveal says **precisely when the probability
 * was last updated**, and the same symbol has to work on the grid, on cards and
 * on the questions section — *universal* meaning one thing, not four things
 * that resemble each other. #2256 is his issue, in his words: *"Indicate on the
 * site when probabilities are illiquid and less meaningful."*
 *
 * ═══ WHAT IT IS FOR, ON A PAGE THAT IS LIVE RIGHT NOW ═══
 *
 * The US Open bracket grid prints Venus Williams at 0.8% to reach the
 * quarter-final and 3.6% to reach the semi-final — a number that goes UP for a
 * round she has to survive the first one to play. Q428 chased 27 of those and
 * fixed 11 of them as our own bugs; the residual 16 are faithfully what the
 * markets say, on books that between them traded nothing at all in a day. The
 * charter forbids smoothing them and Alex's triage ruling forbids deleting
 * them, so the mark is the whole answer: **say the number is thin, and let the
 * reader discount it themselves.** (#2257.)
 *
 * ═══ THE GRADE IS THE BACKEND'S, DELIBERATELY ═══
 *
 * `backend/app/utils/market_liquidity.py` owns the rule and this module owns
 * the words. Same split as `price_state`, and for the same reason: the
 * ingredients are two database columns and a venue's own volume figure, none of
 * which the client has, and a second client-side opinion about the same book is
 * how two surfaces come to disagree about one number.
 *
 * Read that module before changing anything here — in particular the note on
 * why a relative-width test is admissible as a MARK when Q428 measured it and
 * refused it as a FILTER. Short version: a filter's mistake deletes a cell and
 * the reader never learns it existed; a mark's mistake leaves the number on the
 * page with our doubt beside it. This signal may never decide whether something
 * renders.
 *
 * ═══ THE COPY, AS ALEX RULED IT ON SEEING IT (2026-08-29) ═══
 *
 * *"The indicator is great, but the mouseover text is way to verbose. no need
 * to reference buyers and sellers. can just clarify that the numbers isn't
 * moving and is less reliable."*
 *
 * So the reveal is now ONE clause about the market and one about what to do
 * with the number, and the mechanism that produced the grade is not in it. The
 * two-word verdict ("Thinly traded") went with the mechanism: the glyph already
 * grades, and the grade survives in the reveal as *less* versus *much less*
 * reliable, which is a difference a reader can act on where two adverbs of
 * trading volume were not. What we measure has not changed at all — only how
 * much of our own working we make a reader read.
 *
 * THE BAN IS PINNED, in `__tests__/lib/liquidityMark.test.tsx` and in the
 * native mirror's tests: no bid, no ask, no spread, no buyers and no sellers,
 * in the reveal OR in the definition. It is the sportsbook vocabulary ruling 7
 * removed from these pages, arriving by a different door.
 */

/** Mirrors `market_liquidity.LIQUIDITY_*`. There is no fifth. */
export type LiquidityLevel = "traded" | "thin" | "barely" | "unknown";

/** Mirrors `market_liquidity.REASON_*`. */
export type LiquidityReason = "no_trades_24h" | "spread_exceeds_price";

/** The shape every surface's payload carries beside its probability. */
export interface LiquidityFacts {
  liquidity?: string | null;
  liquidity_reasons?: string[] | null;
}

const LEVELS: ReadonlySet<string> = new Set([
  "traded",
  "thin",
  "barely",
  "unknown",
]);

/**
 * Read a payload's declared level, fail-closed to `unknown`.
 *
 * An unrecognised string is `unknown` and not `thin`: a mark invented from a
 * value we do not understand is indistinguishable, on the page, from one we
 * measured — and the whole point of the mark is that it is measured.
 */
export function readLiquidity(raw: unknown): LiquidityLevel {
  if (typeof raw !== "string" || !LEVELS.has(raw)) return "unknown";
  return raw as LiquidityLevel;
}

/** Only these two draw anything. `traded` and `unknown` are silent. */
export function isMarked(level: LiquidityLevel): boolean {
  return level === "thin" || level === "barely";
}

/**
 * What to do with a marked number, and the only place the GRADE survives in
 * words. Alex's own register: *less reliable*.
 *
 * "Less" and "much less" rather than two nouns, because this is the half of
 * the sentence a reader acts on and a comparative is the cheapest thing to
 * compare. Neither says the probability is WRONG — the number still renders,
 * and that is the whole settlement of #2257.
 */
export const LIQUIDITY_MEANING: Record<"thin" | "barely", string> = {
  thin: "treat it as less reliable",
  barely: "treat it as much less reliable",
};

/**
 * The one clause that says what is wrong, said the way Alex asked for it —
 * *the number isn't moving* — and never as the arithmetic that found it.
 *
 * Two stems and not two sentences, because the reveal prints exactly ONE of
 * them (see `liquidityReveal`). The wide-book stem is deliberately not a
 * statement about movement: a market can be quoting an absurd range and still
 * have traded this morning, and "hasn't moved" on that outcome would be a
 * claim we never measured — the same over-claim `FRESHNESS_DEFINITION` exists
 * to refuse one section over.
 */
const REASON_STEM: Record<LiquidityReason, string> = {
  no_trades_24h: "This number hasn't moved in a while",
  spread_exceeds_price: "Barely anybody is trading this market",
};

function readReasons(raw: unknown): LiquidityReason[] {
  if (!Array.isArray(raw)) return [];
  const out: LiquidityReason[] = [];
  for (const value of raw) {
    if (value === "no_trades_24h" || value === "spread_exceeds_price") {
      out.push(value);
    }
  }
  return out;
}

/**
 * "27 Aug, 2:14 PM" in the READER's own timezone.
 *
 * Alex's constraint is "precisely when", and a relative age is the thing he
 * already called ambiguous — "32 hours ago" leaves the reader doing arithmetic
 * against a clock they have to guess at. Their own clock is the one they can
 * check. Same call `lib/slate.matchTime` makes, for the same reason.
 *
 * Returns `null` rather than throwing on an unparseable value: a reveal is
 * chrome, and chrome must never be able to take a grid down.
 */
export function preciseObservedAt(observedAt: string | null | undefined): string | null {
  if (!observedAt) return null;
  const at = new Date(observedAt);
  if (Number.isNaN(at.getTime())) return null;
  return at.toLocaleString(undefined, {
    day: "numeric",
    month: "short",
    hour: "numeric",
    minute: "2-digit",
  });
}

/**
 * The whole reveal, in one string: what is wrong, what to do about it, and
 * precisely when.
 *
 * ONE STRING because it has to survive four different disclosure mechanisms —
 * a web `title=`, a screen reader's accessible name, an inline caption on a
 * card, and a tap-to-open caption on the phone. A structured object would let
 * three of them drift; a sentence cannot.
 *
 * ONE REASON, never both, which is the change Alex's 2026-08-29 ruling asked
 * for. `barely` is the level where both facts failed and the old sentence
 * listed both, which is exactly the version he called *way too verbose* — and
 * the second clause bought the reader nothing, because the two facts do not
 * lead to two different responses. Both true is still one caution; the glyph
 * and `LIQUIDITY_MEANING` carry that it is the worse one.
 *
 * `no_trades_24h` wins the tie, and every `barely` carries it, so a hollow mark
 * always reads as "hasn't moved". The other stem is reachable only on a `thin`
 * marked for its book alone.
 *
 * Returns `null` for `traded` and `unknown`, which is what makes "no mark" the
 * cheap default rather than a case every caller has to remember to handle.
 */
export function liquidityReveal(
  facts: LiquidityFacts,
  observedAt?: string | null
): string | null {
  const level = readLiquidity(facts.liquidity);
  if (!isMarked(level)) return null;
  const marked = level as "thin" | "barely";

  const reasons = readReasons(facts.liquidity_reasons);
  // A marked level always arrives with at least one reason from the backend. A
  // payload that lost them still gets a true sentence rather than "  .": the
  // wide-book stem claims only that the market is barely traded, which is what
  // being marked at all already means.
  const stem = reasons.includes("no_trades_24h")
    ? REASON_STEM.no_trades_24h
    : REASON_STEM.spread_exceeds_price;

  const when = preciseObservedAt(observedAt);
  // "Last number" and not "last traded": we do not receive trades, and the
  // timestamp is the last time a probability reached us. It is also the label
  // `tournamentProps.FRESHNESS_DEFINITION` already teaches on this page, which
  // is why it is not "last reading" — one fact, one name for it.
  const last = when === null ? "" : ` Last number: ${when}.`;

  return `${stem} — ${LIQUIDITY_MEANING[marked]}.${last}`;
}

/**
 * Said ONCE per surface, never per cell. Mirrors
 * `market_liquidity.LIQUIDITY_DEFINITION`.
 *
 * The LAST sentence is the load-bearing one. Where a venue publishes nothing
 * to check we cannot mark, so an UNMARKED number has not been cleared — it has
 * been left alone. Gotcha #53 in one clause: an absence must not read as a good
 * answer.
 *
 * The middle sentence still teaches both glyphs, and it now does it without
 * teaching the two facts underneath them (Alex, 2026-08-29): "one sign of that"
 * and "both" is the whole of what a reader needs to order two symbols, and the
 * bid/ask arithmetic that produced the count is ours to carry, not theirs.
 */
export const LIQUIDITY_DEFINITION =
  "We mark a number when the market behind it is barely being traded, which usually means it hasn't moved in a while and is less reliable. A half mark means we found one sign of that; a hollow mark means we found both. Where a venue publishes nothing to check against we cannot mark, so a number with no mark is one we have not been able to question.";
