/**
 * #5623 — the /golf and /sport tournament card printed a POINT move as a percent.
 *
 *     Leader · +10.0% today          <- a 10-POINT move (37.8% -> 47.8%)
 *
 * `movement` is a probability delta, so `movement * 100` is percentage POINTS.
 * A reader takes "+10.0%" as a tenth more than the leader had, about 4.8 points:
 * under half the real move, in a unit the number was never in. Same family as
 * #4066 (the Discover pill, `MovementBadge`) and #5619 (eight backend sentences).
 *
 * TWO HOUSE RULES MEET ON THIS LINE AND PULL OPPOSITE WAYS ON PURPOSE
 * (ux/1217, Sat 2026-09-12, answering the routing question):
 *
 *   NOUN   a badge takes the abbreviation, a sentence takes the word. This is a
 *          compact caption beside a name on a 390px card, so `pts` — the same
 *          string the Discover pill shipped at 14:46Z. The backend's prose
 *          ("moved up 38 points today") keeps the spelled-out word.
 *   WIDTH  one decimal, trailing zero KEPT — the opposite of the backend
 *          formatter, which drops it. This number's consistency is INTERNAL to
 *          the card: it stands in a column with five sibling `.toFixed(1)`
 *          probabilities 40px away. The backend sentence has no numbers beside it.
 *
 * Neither is drift, and the arms below pin both so that "harmonising" them later
 * fails a test instead of quietly shipping.
 *
 * THE SIGN ARM IS NOT DECORATION. `formatMovementPoints` returns the ABSOLUTE
 * magnitude. The pre-fix line read `movement > 0 ? "+" : ""` and was correct only
 * because `(m * 100).toFixed(1)` carried its own minus. Keeping that empty branch
 * while switching to the absolute helper renders a FALL as a rise wearing red —
 * which is what the first proposed snippet for this fix would have done.
 */

import React from "react";
import { renderToStaticMarkup } from "react-dom/server";

import TournamentCard from "@/components/TournamentCard";
import type { GolfTournament } from "@/lib/types";

function tournamentWithMovement(movement24h: number | null): GolfTournament {
  return {
    key: "asia-masters-2026",
    name: "Asia Masters 2026",
    tour: "PGA Tour",
    golfers: [
      { name: "Dplus Challengers", probability: 0.478, movement_24h: movement24h },
      { name: "Academy", probability: 0.123, movement_24h: null },
    ],
  } as unknown as GolfTournament;
}

function render(movement24h: number | null): string {
  return renderToStaticMarkup(
    React.createElement(TournamentCard, {
      tournament: tournamentWithMovement(movement24h),
    } as never),
  );
}

/** The visible caption, with tags stripped.
 *
 * 🔴 Stripped deliberately. #4066's first guard asserted against raw markup and
 * was half vacuous, because the `aria-label` on that component already stated
 * the correct unit — so a positive match hit the string that was never broken.
 * This card has no such label today, but the habit is the point: assert what the
 * eye sees, not what the markup happens to contain.
 */
function visible(markup: string): string {
  return markup.replace(/<[^>]*>/g, " ").replace(/\s+/g, " ").trim();
}

describe("#5623 · the tournament card's movement is POINTS, not percent", () => {
  it("a ten-point rise reads '+10.0 pts today', never '+10.0%'", () => {
    const text = visible(render(0.1));
    expect(text).toContain("+10.0 pts today");
    expect(text).not.toContain("+10.0% today");
  });

  it("a fall keeps its minus sign", () => {
    // `formatMovementPoints` is absolute. Drop the sign and this renders as a
    // RISE — the colour would be the only thing saying otherwise, and colour is
    // not a unit.
    const text = visible(render(-0.111));
    expect(text).toContain("-11.1 pts today");
    expect(text).not.toContain("+11.1 pts today");
  });

  it("keeps ONE decimal including the trailing zero (the card's internal rule)", () => {
    // The backend formatter would say "10 points" here. This card says "10.0"
    // because of the five sibling one-decimal probabilities beside it. If someone
    // "harmonises" the two, this fails.
    expect(visible(render(0.1))).toContain("10.0 pts");
    expect(visible(render(0.1))).not.toContain(" 10 pts");
  });

  it("says 'pts', not the spelled-out 'points' (badge register, not prose)", () => {
    const text = visible(render(0.235));
    expect(text).toContain("23.5 pts today");
    expect(text).not.toContain("23.5 points");
  });

  it("prints no movement caption at all when the move would render as zero", () => {
    // UX-P275 via `isRenderedMove`: the gate is derived from the RENDERED string
    // at this decimal width, replacing a hand-picked `Math.abs(m) > 0.001` that
    // was safe only by coincidence. A move too small to print must not produce a
    // coloured "+0.0 pts today".
    const text = visible(render(0.00004));
    expect(text).not.toContain("pts today");
    expect(text).not.toContain("0.0 pts");
  });

  it("shows a move the OLD hand-picked threshold suppressed even though it prints", () => {
    // THIS ARM IS THE ONE THAT TESTS THE GATE SWAP, and it exists because the
    // arm above does not: with the defect restored (`Math.abs(m) > 0.001`) the
    // whole suite stayed green, because a move too small to print is hidden by
    // BOTH gates. A guard that cannot tell the two apart is not guarding them.
    //
    // Mapped, rather than assumed. The gates disagree on exactly one window,
    // 0.0005 <= |m| <= 0.001 — a move that ROUNDS TO A VISIBLE `0.1 pts` but
    // failed the old fraction threshold and was printed as nothing:
    //
    //     m=0.0004   0.0 pts   old hidden   new hidden
    //     m=0.0008   0.1 pts   old HIDDEN   new shown   <- here
    //     m=0.0011   0.1 pts   old shown    new shown
    //
    // The reverse direction is IMPOSSIBLE: passing `> 0.001` means |m*100| >
    // 0.1, which can never round to 0.0. So — stated plainly because the
    // comment above is easy to over-read — the coloured-zero defect UX-P275
    // was NOT live on this card, and adopting `isRenderedMove` here buys
    // drift-resistance (the gate is now derived from the width it renders at,
    // so changing `decimals` cannot desynchronise them) plus this small
    // widening. It does not repair a `+0.0 pts` a reader was seeing.
    const text = visible(render(0.0008));
    expect(text).toContain("+0.1 pts today");
  });

  it("prints nothing for a null movement", () => {
    expect(visible(render(null))).not.toContain("pts today");
  });
});
