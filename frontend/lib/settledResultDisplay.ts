import { isAuthoritativeResolution } from "@/lib/resolutionAuthority";
import type { SettlementDisplay } from "@/lib/types";

/**
 * #698 — ONE effective settled-result decision per row, made once per payload,
 * so the row, the hero, the sort, the ladder and the chart caption cannot
 * disagree about whether a result exists.
 *
 * ## What a reader saw
 *
 * `/futures/62134744` (*Marchi vs. Lokoli: Match O/U 21.5*, Polymarket,
 * resolved) serves both legs as `probability 0.5, is_winner false,
 * resolution_source "clob_authoritative"`. `outcomeRowVerdict` reads only the
 * grade and the source, so both rows printed **Lost · 0% · Settled** — a
 * literal 0% the payload never held, over a 50/50 last price that says nothing
 * was decided. Whether that match voided is UNKNOWN; this file does not decide
 * it. It stops the page asserting a result the stored row does not support.
 *
 * ## The contract, and the fallback for an older server
 *
 * The server now serves `settlement_display` (`app/utils/settlement_display.py`)
 * on every row of a resolved Polymarket detail payload. When present it is the
 * answer. When ABSENT on a market the server would have targeted, the page is
 * running ahead of the API (Vercel deploys before Heroku) and the same rules run
 * here on the SERVED values, conservatively: anything short of an exact terminal
 * price agreeing with its grade is unknown, so a web-first deploy cannot briefly
 * restore the two losses. It cannot see the stored price, and it does not hold
 * the server's full source registry (`KNOWN_SOURCES`), so it accepts only the
 * tier-3 subset it DOES hold — `AUTHORITATIVE_RESOLUTION_SOURCES`, pinned to the
 * backend by `resolutionAuthorityMirror6082.test.ts`. Any other source, including
 * one the server would reject as unrecognised, is unknown here. A subset of the
 * server's vocabulary plus the same terminal rule means the fallback can only
 * say LESS than the server, never more (Root counterexample on b0e37eb2b1:
 * `1 / true / "unrecognized_future_source"` read WON here while the server said
 * unknown — `settledCoinFlipSaysResultUnknown698.test.tsx` pins it).
 * Every other market — other sources, open boards — is returned untouched and
 * keeps every legacy contract it had (#4788, #6082, #10066, #10964).
 *
 * ## The projection
 *
 * An `unknown` row keeps its id, name, price, opening and source; only the
 * client-side copy of `is_winner` is set to `null`, which every existing
 * consumer already reads as "no grade" (`gradedWinner`, `pickHeroOutcome`,
 * `sortFuturesOutcomes`, the settled ladder). That is how a midrange `true`
 * cannot crown a phantom champion while its row says "Result unknown". The wire
 * value is not changed and the payload object is never mutated.
 */

const TARGETED_SOURCES: ReadonlySet<string> = new Set(["polymarket"]);
const RETRACTED_SOURCE = "ungradeable_result";
export const CLIENT_FALLBACK_BASIS = "client_rollout_fallback";

interface SettledRow {
  probability: number | null;
  is_winner: boolean | null;
  resolution_source?: string | null;
  settlement_display?: SettlementDisplay | null;
}

interface SettledMarket<R extends SettledRow> {
  source?: string | null;
  status?: string | null;
  outcomes?: R[];
}

function isTargeted(market: { source?: string | null; status?: string | null }): boolean {
  return market.status === "resolved" && TARGETED_SOURCES.has(market.source ?? "");
}

/** The absent-contract fallback on the SERVED values. Conservative by design. */
export function clientFallbackSettlement(row: SettledRow): SettlementDisplay {
  const unknown: SettlementDisplay = { verdict: "unknown", basis: CLIENT_FALLBACK_BASIS };
  if (row.resolution_source === RETRACTED_SOURCE) return unknown;
  // Fail CLOSED on any source outside the verified tier-3 subset (see above).
  if (!isAuthoritativeResolution(row.resolution_source)) return unknown;
  const p = row.probability;
  if (p === null || p === undefined || !Number.isFinite(p)) return unknown;
  if (p === 1 && row.is_winner === true) return { verdict: "won", basis: CLIENT_FALLBACK_BASIS };
  if (p === 0 && row.is_winner === false) return { verdict: "lost", basis: CLIENT_FALLBACK_BASIS };
  return unknown;
}

/** The served contract when present; the fallback on a targeted market; else null. */
export function effectiveSettlement(
  row: SettledRow,
  market: { source?: string | null; status?: string | null },
): SettlementDisplay | null {
  if (row.settlement_display) return row.settlement_display;
  return isTargeted(market) ? clientFallbackSettlement(row) : null;
}

/**
 * The payload with every targeted row's effective settlement attached and
 * every `unknown` row's client copy of `is_winner` withheld. Returns the SAME
 * object when nothing changes, so untouched markets keep their identity.
 */
export function withSettledResultCertainty<R extends SettledRow, M extends SettledMarket<R>>(
  market: M,
): M;
export function withSettledResultCertainty<R extends SettledRow, M extends SettledMarket<R>>(
  market: M | undefined,
): M | undefined;
export function withSettledResultCertainty<R extends SettledRow, M extends SettledMarket<R>>(
  market: M | undefined,
): M | undefined {
  if (!market?.outcomes || market.status !== "resolved") return market;
  let changed = false;
  const outcomes = market.outcomes.map((row) => {
    const effective = effectiveSettlement(row, market);
    if (effective === null) return row;
    const withheld = effective.verdict === "unknown" && row.is_winner !== null;
    if (row.settlement_display === effective && !withheld) return row;
    changed = true;
    return {
      ...row,
      settlement_display: effective,
      ...(withheld ? { is_winner: null } : {}),
    };
  });
  return changed ? { ...market, outcomes } : market;
}

/** Does this row print "Result unknown" instead of a result? */
export function isResultUnknown(
  row: { settlement_display?: SettlementDisplay | null },
  isResolved: boolean,
): boolean {
  return isResolved && row.settlement_display?.verdict === "unknown";
}

/**
 * Whole-board certainty for the hero and the chart caption: `all` when every
 * row's result is unknown, `some` when at least one is, null otherwise. A field
 * whose every row definitely lost is NOT unknown — it is a settled field with no
 * affirmative winner, which an independent field may genuinely have.
 */
export function boardResultCertainty(
  outcomes: readonly { settlement_display?: SettlementDisplay | null }[] | undefined,
  isResolved: boolean,
): "all" | "some" | null {
  if (!isResolved || !outcomes || outcomes.length === 0) return null;
  const unknown = outcomes.filter((o) => isResultUnknown(o, true)).length;
  if (unknown === 0) return null;
  return unknown === outcomes.length ? "all" : "some";
}

/** The chart caption on a settled board, from the same effective verdicts. */
export function settledChartCaption(
  certainty: "all" | "some" | null,
  championLabel: string | null,
): string {
  if (certainty === "all") return "Result unknown; chart shows recorded prices.";
  const settled = championLabel ? `Settled — ${championLabel} won.` : "Settled.";
  return certainty === "some" ? `${settled} Some results unknown.` : settled;
}
