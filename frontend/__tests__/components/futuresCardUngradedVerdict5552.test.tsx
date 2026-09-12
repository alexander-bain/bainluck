/**
 * #5552 / #5457 — `FuturesCard` PRINTS `Lost` ON A LEG NOBODY GRADED
 *
 * ## What a reader sees
 *
 * A reader pins a market on `/my-stuff`. It resolves. Nobody grades it. Every row
 * of the pinned card then reads **`Lost`**, greyed to opacity 0.15 with its bar
 * animated to 0% width — including, on a two-sided question, the side that won.
 *
 * Specimen, production 2026-09-12 11:4xZ — `/api/futures/60693630`,
 * *Set 1 Winner: KHOMUTSIANSKAYA vs Astakhova* (Polymarket, `status: resolved`,
 * settled 11:34:18Z):
 *
 *   | leg | `is_winner` | `resolution_source` | card printed |
 *   |---|---|---|---|
 *   | `No`  | `false` | `null` | **Lost** · bar 0% |
 *   | `Yes` | `false` | `null` | **Lost** · bar 0% |
 *
 * A set has a winner. We told the reader both sides lost.
 *
 * ## The mechanism, and why it is the same one #4788 fixed next door
 *
 * `futures_outcomes.is_winner` is `boolean NULL DEFAULT false`, so an INSERT that
 * merely omits the column stores an affirmative graded LOSS. On a RESOLVED market
 * `is_winner === false` therefore answers two different questions with one bit:
 * "a grader called this a loser" and "nobody has ever been here".
 *
 * `components/futures/OutcomeRow` was fixed for exactly this and exports the
 * discriminator — `outcomeRowVerdict`, which withholds when `resolution_source`
 * is `null`. `FuturesCard` is its unfixed twin: it restated
 * `isResolved && outcome.is_winner === X` at four separate branches (bar colour,
 * bar opacity, bar width, and the `Won`/`Lost` cell). This diff routes all four
 * through the one imported function rather than adding a fifth private copy of
 * the rule — `OutcomeRow`'s own docstring records that restating the condition
 * per branch is how that surface drifted the last time.
 *
 * ## Reach — MEASURED, not reasoned
 *
 * Production `POST /api/admin/db-query`, 2026-09-12 (fingerprints
 * `de085fdc5fe1419e`, `dbf` cohort query above it):
 *
 *   * **609,703 legs on 283,030 resolved markets** carry
 *     `(is_winner false, resolution_source null)` — the population that printed a
 *     `Lost` nobody wrote.
 *   * `is_winner IS TRUE` splits **1,295,486 resolved + 3,885 open, and 0 of either
 *     with a null source**. The win arm cannot currently be fabricated, so gating
 *     it is a no-op today; it is gated anyway for the reason `OutcomeRow` gives —
 *     "guard the loss, trust the win" is a rule that silently stops holding the
 *     first time a producer defaults the other way, and nothing would catch it.
 *
 * ## Why `undefined` must NOT be folded in with `null` — controls 3 and 4
 *
 * `resolution_source` is serialised by `/api/futures/{id}` and NOT by the feed or
 * grouped-feed payloads. So the guard bites exactly where the reach was proven —
 * `/my-stuff` and `/preferences` both fetch by id through `fetchFuturesByIds`
 * (`lib/api.ts:978`) with no status predicate anywhere in the path — and is inert
 * on `/discover`, `/search`, `/hub` and `DiscoverCard`, which serve the field
 * ABSENT. Absent means "this payload cannot say", and the honest answer to that is
 * today's behaviour, not a site-wide blackout of genuine `Won` marks for the
 * length of every Vercel-ahead-of-Heroku deploy skew.
 *
 * ## Red-first, MEASURED against the parent (`0a993f2b1`), not reasoned
 *
 * Ran on the parent with only this file added: **4 fail, 4 pass**.
 *
 * The three ungraded assertions fail as designed (`Lost` printed, bar dimmed to
 * 0.15 and animated to 0% width, live percentages suppressed). The FOURTH failure
 * is the one I did not predict and it is worth naming: *"refuses the retraction
 * even though it carries a source"* is filed below among the controls, but it is a
 * DIFF TEST — the parent prints `Lost` on an `ungradeable_result` leg too. Routing
 * through `outcomeRowVerdict` inherits its unconditional first-line refusal
 * (CAL-P056 / #1852, CERT-2222, CERT-2517) for free, so this card stops asserting a
 * loss on legs we have explicitly declared unknowable. Left in the controls block
 * because that is what it guards against going forward; called out here because a
 * control-shaped test that was never green on the parent is not a control, and
 * quietly banking it as one is how a red-first count stops meaning anything.
 *
 * The four genuine passes are the branches that must not move: a graded `Lost`, a
 * graded `Won`, the absent-key deploy-skew fence, and an unresolved market. Every
 * claim is read off the rendered markup.
 */

import { renderToStaticMarkup } from "react-dom/server";
import FuturesCard from "../../components/FuturesCard";
import type { FuturesMarket, FuturesOutcome } from "../../lib/types";

/**
 * `resolutionSource` is passed as a THREE-state argument on purpose: a value, an
 * explicit `null`, and `undefined` for "the key is not on the wire at all". The
 * absent case is a distinct branch of the guard, so a fixture that could only
 * express `null` would leave it untested.
 */
function outcome(
  id: number,
  name: string,
  probability: number,
  isWinner: boolean | null,
  resolutionSource: string | null | undefined,
): FuturesOutcome {
  const base = {
    id,
    name,
    probability,
    american_odds: null,
    rank: null,
    rank_change_24h: null,
    probability_change_24h: null,
    movement: null,
    opening_probability: null,
    opening_american_odds: null,
    is_winner: isWinner,
    last_updated: null,
  } as Record<string, unknown>;
  // Only SET the key when it is meant to be on the wire — `{ resolution_source:
  // undefined }` and "no such key" are the same thing to the guard, but writing it
  // explicitly here would hide the fact that this fixture is modelling an older
  // serialiser rather than a null grade.
  if (resolutionSource !== undefined) base.resolution_source = resolutionSource;
  return base as unknown as FuturesOutcome;
}

function market(outcomes: FuturesOutcome[], status: string): FuturesMarket {
  return {
    id: 60693630,
    name: "Set 1 Winner: KHOMUTSIANSKAYA vs Astakhova",
    description: null,
    source: "polymarket",
    category: null,
    sport: "tennis",
    sport_name: null,
    llm_sport_category: "tennis",
    external_id: null,
    mutually_exclusive: true,
    commence_time: null,
    resolution_date: null,
    outcome_count: outcomes.length,
    created_at: null,
    updated_at: null,
    status,
    outcomes,
  } as unknown as FuturesMarket;
}

function render(m: FuturesMarket): string {
  const html = renderToStaticMarkup(<FuturesCard market={m} />);
  if (!/role="progressbar"/.test(html)) {
    throw new Error(
      "no outcome rows rendered — the extractor is blind, not the card empty",
    );
  }
  return html;
}

/** The two production legs of the specimen, parameterised on grading state. */
const legs = (
  isWinner: boolean | null,
  source: string | null | undefined,
): FuturesOutcome[] => [
  outcome(227272054, "No", 0.585, isWinner, source),
  outcome(227272053, "Yes", 0.415, isWinner, source),
];

/**
 * The mini bar's inline geometry for each row, in render order.
 *
 * Read off the `style` attribute of the element that follows each progressbar,
 * because opacity and width are the two halves of the same visual claim as the
 * word: a fix that removed `Lost` but left the bar collapsed to 0% and faded to
 * 0.15 would still be telling the reader the leg lost, silently. Asserting the
 * word alone cannot see that.
 */
function barStyles(html: string): string[] {
  return [...html.matchAll(/role="progressbar"[\s\S]*?<div[^>]*style="([^"]*)"/g)]
    .map((m) => m[1]);
}

describe("#5552 — an ungraded leg on a resolved market states no verdict", () => {
  it("prints no 'Lost' on the production specimen (is_winner false, source null)", () => {
    expect(render(market(legs(false, null), "resolved"))).not.toContain("Lost");
  });

  it("leaves the ungraded bar at its live width and opacity, not 0% / 0.15", () => {
    const styles = barStyles(render(market(legs(false, null), "resolved")));
    expect(styles).toHaveLength(2);
    for (const style of styles) {
      expect(style).not.toContain("opacity:0.15");
      expect(style).not.toMatch(/width:\s*0%/);
    }
    // The leader keeps the futures accent it would have had while open — the row
    // is not "a loss we are being coy about", it is a row with no verdict.
    expect(styles[0]).toContain("58.5%");
    expect(styles[1]).toContain("41.5%");
  });

  it("still prints the live probabilities it withheld the verdict in favour of", () => {
    const html = render(market(legs(false, null), "resolved"));
    // 59/41, not 59/42: a two-outcome market is one question, so #2831's
    // `renderedOutcomeRowPercents` decides the pair once instead of rounding
    // 0.585/0.415 independently into a set of percentages that sums to 101.
    expect(html).toContain("59%");
    expect(html).toContain("41%");
  });
});

describe("#5552 controls — the branches that must NOT move", () => {
  it("still prints 'Lost' when a grader actually called it", () => {
    const html = render(market(legs(false, "polymarket_resolution"), "resolved"));
    expect(html).toContain("Lost");
    expect(barStyles(html)[0]).toMatch(/width:\s*0%/);
  });

  it("still prints 'Won' for a graded winner", () => {
    const graded = [
      outcome(227272054, "No", 0.585, true, "polymarket_resolution"),
      outcome(227272053, "Yes", 0.415, false, "polymarket_resolution"),
    ];
    const html = render(market(graded, "resolved"));
    expect(html).toContain("Won");
    expect(html).toContain("Lost");
  });

  it("is INERT on a payload with no resolution_source key — the deploy-skew fence", () => {
    // `/discover`, `/search`, `/hub` and `DiscoverCard` serve the field absent, and
    // so does every surface for the length of a Vercel-ahead-of-Heroku deploy.
    // Absent is not null: folding them together would blank 1,295,486 genuine
    // verdicts to remove a defect that only ever prints a false `Lost`.
    const html = render(market(legs(false, undefined), "resolved"));
    expect(html).toContain("Lost");
  });

  it("refuses the retraction even though it carries a source", () => {
    // `ungradeable_result` is our own statement that the leg is unknowable
    // (CAL-P056 / #1852). A non-empty source is not automatically a grade, and
    // `outcomeRowVerdict` refuses this one first and unconditionally.
    const html = render(market(legs(false, "ungradeable_result"), "resolved"));
    expect(html).not.toContain("Lost");
  });

  it("says nothing about a market that has not resolved", () => {
    const html = render(market(legs(false, "polymarket_resolution"), "open"));
    expect(html).not.toContain("Lost");
    expect(html).not.toContain("Won");
  });
});
