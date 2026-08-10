/**
 * probabilityEvidence — refuse to assert a probability we do not have.
 *
 * UX-P042 (#1640). Standing ruling #1 says "the blend is the product": ONE number
 * per question. That ruling only means anything if the number is real. A game whose
 * entire evidence base is a single untraded Polymarket book, parked at the midpoint
 * its API returns when it has no price to give, has no probability — and rendering
 * `50%` there is not a blend, it is a fabricated coin flip presented in exactly the
 * same type as a well-sourced number.
 *
 * Measured on production 2026-08-09, event 15187583 (Red Sox @ Blue Jays, scheduled):
 *
 *     hero_probability        0.5
 *     hero_probability_away   0.5
 *     hero_probability_source "blend"        <-- the word every read site gates on
 *     current_odds            {home 0.5, away 0.5, source "aggregate", bookmaker_count 0}
 *     win_probability_sources {"polymarket": 0.5}
 *
 * WHY EXACTLY 0.500 AND NOT A BAND. The value distribution over the 99 upcoming games
 * carrying a Polymarket source is a spike, not a curve:
 *
 *     0.500  ################################# 33
 *     0.495  #####  5
 *     0.505  ####   4
 *     0.415 / 0.420 / 0.425 / 0.430   3 each
 *
 * 33x the next bucket. The `betting` source over the same slate is smooth — 0.500
 * appears 3 times in 243, in line with its neighbours — so those three are genuine
 * pick'ems and MUST keep rendering. That is gotcha #19 (an untraded Polymarket market
 * reports its midpoint) showing up as a single discrete value, so the test is a single
 * discrete value. A band would eat real prices; 0.495 and 0.505 are real.
 *
 * WHY NOT `bookmaker_count === 0`. It was tested first and rejected: it is 0 for ANY
 * non-betting source, including the traded 0.495 (event 15187584) and 0.505 (15187849)
 * rows. Gating on it would have suppressed real prices — the exact both-direction
 * failure gotcha #43 exists to catch.
 *
 * This is not a new heuristic. `eventKeyStats.ts` already refuses a chart-point
 * fallback at exactly 0.5; this applies the same judgment to the primary path.
 *
 * The write-side half — never storing the phantom at all — is #1578, and it is
 * forward-only, so it cannot clear the games already in this state. This module is
 * the read-side gate.
 *
 * PURE: no I/O, no fetch, no DB.
 */

/**
 * The value a Polymarket book reports when it has no trading to price from.
 *
 * Exact equality is deliberate and safe: 0.5 is exactly representable as an IEEE-754
 * double, and JSON `0.5` parses to precisely that value, so `=== 0.5` cannot miss a
 * true placeholder or accidentally catch 0.495 / 0.505.
 */
export const UNTRADED_MIDPOINT = 0.5;

/**
 * The only source known to publish {@link UNTRADED_MIDPOINT} as a non-answer.
 * Kalshi is already spread-guarded upstream; `betting` at 0.500 is a real pick'em.
 */
const PLACEHOLDER_PRONE_SOURCE = "polymarket";

/**
 * `win_probability_sources` arrives in TWO shapes and both are live in production:
 *
 *   - `/api/feed`                      -> `{"mlb": 0.629, "betting": 0.0602}`   (bare number)
 *   - `/api/events/*`, `/search`       -> `{"polymarket": {"value": 0.5, ...}}` (decorated)
 *
 * Reading only one of them would silently no-op on the other surface, so both are
 * accepted here rather than at each call site.
 */
export type WinProbabilitySourceEntry =
  | number
  | { value?: number | null }
  | null
  | undefined;

export type WinProbabilitySources =
  | Record<string, WinProbabilitySourceEntry>
  | null
  | undefined;

/** Normalise either wire shape to a number, or null when there is no usable value. */
export function readSourceValue(entry: WinProbabilitySourceEntry): number | null {
  if (typeof entry === "number") return Number.isFinite(entry) ? entry : null;
  if (entry && typeof entry === "object" && typeof entry.value === "number") {
    return Number.isFinite(entry.value) ? entry.value : null;
  }
  return null;
}

/** Every source that carries a usable numeric value, as `[name, value]` pairs. */
export function readSourceValues(
  sources: WinProbabilitySources,
): Array<[string, number]> {
  if (!sources || typeof sources !== "object") return [];
  const out: Array<[string, number]> = [];
  for (const [name, entry] of Object.entries(sources)) {
    const value = readSourceValue(entry);
    if (value !== null) out.push([name, value]);
  }
  return out;
}

/**
 * True when the ONLY evidence behind this event is an untraded Polymarket midpoint.
 *
 * Deliberately narrow. Two or more sources always pass, even if they average to
 * exactly 0.500 — agreement between independent sources IS evidence.
 */
export function isUntradedPlaceholder(sources: WinProbabilitySources): boolean {
  const values = readSourceValues(sources);
  if (values.length !== 1) return false;
  const [name, value] = values[0];
  return name === PLACEHOLDER_PRONE_SOURCE && value === UNTRADED_MIDPOINT;
}

/** Statuses this gate applies to. */
function isPreGame(status: string | null | undefined): boolean {
  return status !== "live" && status !== "completed" && status !== "closed";
}

export interface ProbabilityEvidenceInput {
  status?: string | null;
  win_probability_sources?: WinProbabilitySources;
}

/**
 * Should this event's probability be withheld rather than asserted?
 *
 * SCOPE, stated rather than assumed: pre-game only. The 31-of-311 cohort measured for
 * #1640 is `status='scheduled'`, and a finished game reads its opening line while a
 * live game reads the blended chart edge — different paths, unmeasured populations.
 * Widening past what was measured is how a suppression rule eats real data.
 */
export function shouldWithholdProbability(
  event: ProbabilityEvidenceInput | null | undefined,
): boolean {
  if (!event) return false;
  if (!isPreGame(event.status)) return false;
  return isUntradedPlaceholder(event.win_probability_sources);
}
