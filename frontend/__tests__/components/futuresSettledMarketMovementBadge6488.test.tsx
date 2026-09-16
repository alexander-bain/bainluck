/**
 * #6488 — a SETTLED market's "Final Results" table stops advertising a live move.
 *
 * ## The defect, as a reader met it
 *
 * `/futures/61120482` ("Boston Red Sox vs. Texas Rangers - 5th Inning Winner"),
 * production 2026-09-16 05:30Z at 390px. `status='resolved'`, so the page prints
 * a banner reading **"This market has been settled. Resolved 9/15/2026."** and
 * heads the table **"Final Results"** — and then renders:
 *
 *     Draw            OPEN 58%   LAST MOVE  +0.5 pts   LATEST 58%
 *     Texas Rangers   OPEN 22%   LAST MOVE  –          LATEST 23%
 *     Boston Red Sox  OPEN 24%   LAST MOVE  –          LATEST 19%
 *
 * The page says the market is over and, one line down, that its price is still
 * moving. Alex flagged this juxtaposition from his phone
 * (`artifacts/alex-phone-20260915/phone-intake.md`).
 *
 * Note the other two rows already print the muted `–`. Only `Draw` carries a
 * badge, and only because it happens to hold a non-null `probability_change_24h`
 * — so the table was inconsistent with ITSELF as well as with its own heading.
 *
 * ## Why this is not a re-litigation of #4788
 *
 * All three legs carry `resolution_source: null`, so `outcomeRowVerdict` returns
 * `null` and no row prints a verdict. That is #4788 working exactly as ruled —
 * never a confident `Lost` on a leg nobody graded — and it is untouched here.
 * #4788 governs the VERDICT cell; this governs the MOVEMENT cell, which the
 * detail page rules on separately and negatively at three sites:
 * `page.tsx:675` (`movement={!isResolved && …}`), `FuturesHero.tsx:51`
 * (`!resolved && …`), and `page.tsx:898` (the movement explanation). The table
 * was the one widget on the page that missed the rule.
 *
 * #4788's objection — a row with no result "has nothing to trade [the cell] for"
 * — is answered by #3358 rather than overridden: `showLastMove` polls this same
 * predicate across the whole table, so a settled market drops the column instead
 * of filling it with holes, handing its fixed 80px back to the name column.
 *
 * ## What the badge said, and the half that is NOT the renderer's
 *
 * `probability_change_24h = 0.005` → "+0.5 pts". The served history for the same
 * outcome, same payload:
 *
 *     10:15 0.575   12:15 0.570   14:15 0.560   17:17 0.565   23:50 0.575
 *
 * The LAST move was `0.565 → 0.575 = +1.0 pts`; `+0.5` is the *previous* write
 * (`0.560 → 0.565`), because the 23:50 final capture never updated the field. So
 * the column headed "Last move" disagreed with the chart directly above it. That
 * is the producer's half (ruling 003, and the division `OutcomeRow.tsx:82`
 * already draws for grading) and is filed and routed separately — this ship only
 * stops the badge appearing on a settled market at all.
 *
 * ## Under guard in both directions (gotcha #43)
 *
 * The suppression is one branch, and the refusals around it are load-bearing:
 *
 *   - `Draw` on this RESOLVED market ⇒ no move, and the whole column drops
 *   - the same row on an OPEN market ⇒ still moves (the gate is `isResolved`,
 *     not "ungraded", which is what #6082's arm depends on)
 *   - an open market's table is untouched, column and all
 */

import React from "react";
import { renderToStaticMarkup } from "react-dom/server";

import OutcomeRow, {
  outcomeRowPrintsMove,
  outcomeRowVerdict,
} from "@/components/futures/OutcomeRow";
import type { FuturesOutcome } from "@/lib/types";

/**
 * The three legs of `/futures/61120482` exactly as `/api/futures/61120482`
 * served them at 05:30Z on 2026-09-16. Complete and named, so a failure cannot
 * be "fixed" by trimming the fixture to the one row that moves.
 */
function specimen(): FuturesOutcome[] {
  return [
    {
      id: 229747869,
      name: "Draw",
      probability: 0.575,
      opening_probability: 0.575,
      probability_change_24h: 0.005,
      is_winner: null,
      resolution_source: null,
    },
    {
      id: 229747870,
      name: "Texas Rangers",
      probability: 0.225,
      opening_probability: 0.22,
      probability_change_24h: null,
      is_winner: null,
      resolution_source: null,
    },
    {
      id: 229747871,
      name: "Boston Red Sox",
      probability: 0.19,
      opening_probability: 0.24,
      probability_change_24h: null,
      is_winner: null,
      resolution_source: null,
    },
  ] as unknown as FuturesOutcome[];
}

const draw = () => specimen()[0];

/** The page's own whole-table decision (#3358, `page.tsx:511`), reproduced. */
function showLastMove(outcomes: FuturesOutcome[], isResolved: boolean): boolean {
  return outcomes.some((o) => outcomeRowPrintsMove(o, isResolved));
}

/**
 * `showLastMove` is passed as the page computes it, NOT hardcoded true: on a
 * settled market the honest render is the one where the column is already gone,
 * and pinning it open would test a screen no reader can reach.
 */
function render(o: FuturesOutcome, isResolved: boolean): string {
  return renderToStaticMarkup(
    <OutcomeRow
      outcome={o}
      rank={1}
      isLeader={false}
      isSelected={false}
      onToggleSelect={() => {}}
      hasHistory={false}
      marketCategory="baseball_mlb"
      marketName="Boston Red Sox vs. Texas Rangers - 5th Inning Winner"
      isResolved={isResolved}
      rendered={null}
      renderedOpening={null}
      showLastMove={showLastMove(specimen(), isResolved)}
      showEntityImage={false}
    />,
  );
}

describe("#6488 a settled market's table prints no live movement", () => {
  it("the specimen row prints no move once the market is resolved", () => {
    expect(outcomeRowPrintsMove(draw(), true)).toBe(false);
  });

  it("the whole column drops, so no row is left holding a dash-hole", () => {
    // #4788's objection, answered: the cell is not blanked, the column is gone.
    expect(showLastMove(specimen(), true)).toBe(false);
  });

  it("the rendered row does not print the badge or its points suffix", () => {
    const html = render(draw(), true);
    expect(html).not.toContain("+0.5");
    expect(html).not.toContain("pts");
    // The row still says who it is and what it last traded at — this ship
    // removes a badge, never a price.
    expect(html).toContain("Draw");
    expect(html).toContain("58%");
  });

  it("no leg is crowned: #4788's verdict rule is untouched by this change", () => {
    // All three carry `resolution_source: null`. Were this ship to have leaked
    // into the verdict path, these would read "lost".
    for (const o of specimen()) {
      expect(outcomeRowVerdict(o, true)).toBeNull();
    }
  });

  // ── CONTROLS ────────────────────────────────────────────────────────────────

  it("CONTROL: the same row on an OPEN market still prints its move", () => {
    // The gate is `isResolved`, not "ungraded" — #6082's arm rides on this.
    expect(outcomeRowPrintsMove(draw(), false)).toBe(true);
    expect(showLastMove(specimen(), false)).toBe(true);
    expect(render(draw(), false)).toContain("pts");
  });

  it("CONTROL: a graded row on a settled market was already silent", () => {
    // It trades the cell for its verdict one line earlier, so this ship changes
    // nothing for it — asserted so a later edit cannot claim credit for it.
    const graded = {
      ...draw(),
      is_winner: true,
      resolution_source: "api_settlement",
    } as FuturesOutcome;
    expect(outcomeRowPrintsMove(graded, true)).toBe(false);
    expect(outcomeRowVerdict(graded, true)).toBe("won");
  });
});
