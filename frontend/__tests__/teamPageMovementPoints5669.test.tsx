/**
 * #5669 — the team page printed the POINTS formatter under a percent sign.
 *
 * ═══ WHAT A READER SAW ═══
 *
 * `/sport/<sport>/<league>/team/<team>`, the headline championship badge:
 *
 *     ↑ 9.7% today
 *
 * `formatMovementPoints` returns POINTS. `movement` is a probability DELTA in
 * 0-1 units, so `movement * 100` is percentage POINTS — the same substrate fact
 * behind #4066 (Discover pill), #5619 (backend sentences), #5608 (search chip)
 * and #5623 (tournament card). A market that went 37.8% -> 47.8% moved TEN
 * POINTS; "↑ 10.0%" reads as a tenth more than it had, about 4.8 points — under
 * half the real move, in a unit the number was never in.
 *
 * ═══ THIS IS A LABEL FOLLOW-UP TO #5652, NOT A REGRESSION IN IT ═══
 *
 * Stated so nobody reverts a correct fix. #5652 replaced a hand-rolled
 * `Math.abs(m * 100).toFixed(1)` with `formatMovementPoints` + `isRenderedMove`
 * to stop a coloured zero. It did not touch the `%`, which was already wrong and
 * had been since the line was written. The NUMBER is unchanged by this fix;
 * only the unit beside it moves.
 *
 * ═══ THE FORM, AND WHY IT IS PINNED ═══
 *
 * ux/1217 ruled the family (via Fable's routing, Sat 2026-09-12):
 *
 *   NOUN   a badge takes the abbreviation, a sentence takes the word. This is a
 *          compact badge beside a team's championship price, so `pts` — the
 *          same string the Discover pill and the tournament card ship. Backend
 *          PROSE ("moved up 38 points today") keeps the spelled-out word.
 *   WIDTH  one decimal, trailing zero KEPT. `formatMovementPoints` already does
 *          this via `.toFixed(1)`, so the fix is the literal and nothing else.
 *
 * Both are pinned below, so a later "harmonisation" fails a test rather than
 * quietly shipping a third spelling onto a sixth surface.
 *
 * ═══ WHY THIS SUITE SCANS SOURCE FOR THE PAGE HALF ═══
 *
 * The team page is an async Next.js server component that fetches on render;
 * #5652's own guard reached it by source scan for exactly this reason and says
 * so. So part 2 asserts the rendered STRING in the source, in BOTH directions —
 * a guard that only proved the `%` was gone would also pass on a page that
 * stopped printing the badge at all (gotcha #43). Part 1 pins the unit contract
 * behaviourally, on the real helper, which is the half a source scan cannot do.
 */

import fs from "node:fs";
import path from "node:path";

import { formatMovementPoints, movementPoints } from "../lib/probabilityDisplay";

const ROOT = path.join(__dirname, "..");
const TEAM_PAGE = "app/sport/[sport]/[league]/team/[team]/page.tsx";

// ---------------------------------------------------------------------------
// Part 1 — the unit contract, on the real helper
// ---------------------------------------------------------------------------

describe("#5669 part 1 — formatMovementPoints returns POINTS, so a '%' beside it is a mislabel", () => {
  test("the ten-point specimen from the family: 37.8% -> 47.8% is 10 points, not 10 percent", () => {
    const delta = 0.478 - 0.378;
    // The wire value is a fraction; the printed magnitude is that fraction in
    // POINTS. If this were a percent CHANGE it would read ~26.5, not 10.0.
    expect(movementPoints(delta)).toBeCloseTo(10.0, 6);
    expect(formatMovementPoints(delta)).toBe("10.0");
  });

  test("the production specimen behind this issue prints 9.7", () => {
    expect(formatMovementPoints(0.097)).toBe("9.7");
  });

  test("WIDTH is pinned: one decimal, trailing zero KEPT", () => {
    // The opposite of the backend formatter, which drops it. Pinned so the two
    // cannot be "harmonised" into one without failing here first.
    expect(formatMovementPoints(0.09)).toBe("9.0");
    expect(formatMovementPoints(0.1)).toBe("10.0");
    expect(formatMovementPoints(0.01)).toBe("1.0");
  });

  test("the magnitude is ABSOLUTE, so the caller owns the sign", () => {
    // The page renders the arrow from `movement > 0`; if the helper carried its
    // own minus the badge would read "↓ -9.7 pts".
    expect(formatMovementPoints(-0.097)).toBe("9.7");
    expect(formatMovementPoints(0.097)).toBe("9.7");
  });
});

// ---------------------------------------------------------------------------
// Part 2 — the rendered string on the page, both directions
// ---------------------------------------------------------------------------

describe("#5669 part 2 — the team page badge says points, and still says something", () => {
  const src = fs.readFileSync(path.join(ROOT, TEAM_PAGE), "utf8");

  test("the scan read the real page, so every assertion below is about something", () => {
    // Without this, a moved file makes the rest of this describe vacuous.
    expect(src.length).toBeGreaterThan(5000);
    expect(src).toContain("formatMovementPoints");
    expect(src).toContain("isRenderedMove");
  });

  test("the headline badge prints ' pts today'", () => {
    expect(src).toContain("{formatMovementPoints(headline.movement)} pts today");
  });

  test("NO movement site on the page puts a '%' against the points formatter", () => {
    // Structural, not a prose match. The first draft asserted
    // `not.toContain("% today")` and failed on line 302 — a COMMENT quoting the
    // old defect string as history. A guard that reddens on its own incident
    // notes gets deleted by whoever trips over it. This matches the RENDER.
    //
    // It also caught the real second surface: the page has TWO movement sites,
    // and #5669's body names only the headline. The futures row printed
    // `{formatMovementPoints(item.probability_change_24h)}%` — the identical
    // defect, on the very row that was #5652's specimen. Fixed in the same
    // commit, because shipping one and leaving the other means the page still
    // calls points percent, two inches lower.
    const PCT_AGAINST_POINTS = /\{formatMovementPoints\([^)]*\)\}\s*%/g;
    expect(src.match(PCT_AGAINST_POINTS)).toBeNull();
  });

  test("BOTH movement sites print ' pts' — the guard above cannot pass by deleting them", () => {
    const printed = src.match(/\{formatMovementPoints\([^)]*\)\}\s*pts/g) ?? [];
    expect(printed).toHaveLength(2);
  });

  test("the badge is still GATED, so this fix did not smuggle the coloured zero back in", () => {
    // #5652's repair and this one touch the same line. A regex-y edit that
    // dropped `isRenderedMove` would re-open 145 coloured zeros.
    expect(src).toContain("isRenderedMove(headline.movement)");
  });

  test("the sign still comes from the raw movement, not from the printed magnitude", () => {
    expect(src).toContain('headline.movement! > 0 ? "↑" : "↓"');
  });
});
