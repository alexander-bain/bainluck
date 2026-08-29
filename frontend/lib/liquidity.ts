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
 * The two-word verdict. Short enough for a screen reader to lead with and for
 * the reveal to open on.
 *
 * "Traded" rather than "liquid" — Alex's own word is *illiquid*, but that is
 * the same class of vocabulary as "props/futures", which ruling 7 removed from
 * this page for requiring a sportsbook to parse. What the reader needs to know
 * is that hardly anybody is buying and selling it.
 */
export const LIQUIDITY_LABEL: Record<"thin" | "barely", string> = {
  thin: "Thinly traded",
  barely: "Barely traded",
};

/**
 * What being marked MEANS, in the second person, once per level.
 *
 * Both sentences are claims about the market, not about the number: we are not
 * saying the probability is wrong, we are saying the thing that produced it is
 * small. That distinction is the whole reason the cell still renders.
 */
export const LIQUIDITY_MEANING: Record<"thin" | "barely", string> = {
  thin: "Treat this as a rough guide.",
  barely: "Treat this as little more than a guess.",
};

/** Which of the two facts failed, said as a fact rather than as a metric. */
const REASON_TEXT: Record<LiquidityReason, string> = {
  no_trades_24h: "nobody has traded it in the last day",
  spread_exceeds_price:
    "the gap between what buyers offer and what sellers want is wider than the number itself",
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
 * The whole reveal, in one string: verdict, why, and precisely when.
 *
 * ONE STRING because it has to survive four different disclosure mechanisms —
 * a web `title=`, a screen reader's accessible name, an inline caption on a
 * card, and a tap-to-open caption on the phone. A structured object would let
 * three of them drift; a sentence cannot.
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

  const reasons = readReasons(facts.liquidity_reasons).map((r) => REASON_TEXT[r]);
  // A marked level always has at least one reason from the backend, but a
  // payload that lost them still gets a readable sentence rather than "  .".
  const because =
    reasons.length === 0
      ? ""
      : ` — ${reasons.length === 1 ? reasons[0] : `${reasons[0]}, and ${reasons[1]}`}`;

  const when = preciseObservedAt(observedAt);
  // "when we last saw a number" and not "when it last changed hands": we do not
  // receive trades, and the timestamp is the last time a probability reached
  // us. The same over-claim `tournamentProps.FRESHNESS_DEFINITION` exists to
  // stop, in the one sentence most likely to repeat it.
  const last = when === null ? "" : ` Last number: ${when}.`;

  return `${LIQUIDITY_LABEL[marked]}${because}. ${LIQUIDITY_MEANING[marked]}${last}`;
}

/**
 * Said ONCE per surface, never per cell. Mirrors
 * `market_liquidity.LIQUIDITY_DEFINITION`.
 *
 * The second sentence is the load-bearing one. Where a venue publishes nothing
 * to check we cannot mark, so an UNMARKED number has not been cleared — it has
 * been left alone. Gotcha #53 in one clause: an absence must not read as a good
 * answer.
 */
export const LIQUIDITY_DEFINITION =
  "We mark a number when the market behind it is barely being traded — nobody has traded it in the last day, or the gap between what buyers offer and what sellers want is wider than the number itself. A half mark means one of those is true; a hollow mark means both are. Where a venue publishes nothing to check against we cannot mark, so a number with no mark is one we have not been able to question.";
