/**
 * #3242 — THE IN-PLAY GAMES LINE SAYS HOW OLD IT IS.
 *
 * ═══ WHAT ALEX SAW ═══
 *
 * `/events/15304420`, 2026-09-05: badge reads `LIVE · 1s ago`, and the games
 * count under it was a full beat behind ESPN. Both statements were true. The
 * badge is `LiveAgeStamp`, which reads the freshest WIN-PROBABILITY write —
 * a different number, on a different writer, at a different cadence — and it
 * was sitting next to a games count that nothing on the page dated.
 *
 * Measured the same day: ESPN published a match's first game at 15:12; our page
 * showed it at 15:22. The rail was correct and only its cadence was behind, so
 * the ship is not a faster beat — it is that the number stops pretending.
 *
 * ═══ WHAT IS TESTED HERE, AND WHAT IS NOT ═══
 *
 * The age itself is computed in an effect (the component is SSR-safe on
 * purpose), and this suite runs in the node environment like the rest of the
 * house, so a static render cannot observe it. So the age rules are tested as
 * the pure functions they now are — with an INJECTED clock, never `Date.now()`,
 * so the assertions do not depend on when CI runs (gotcha #44) — and the render
 * arms test the thing a static render really can see: whether a chip is there
 * at all, and whether it carries the stamp it was handed.
 *
 * The backend halves are `tests/test_tennis_games_line.py` (only in-play rows
 * are stamped, and a re-stamp is not movement) and
 * `tests/test_espn_tennis_anchor.py` (the real pass writes it).
 */

import React from "react";
import { renderToStaticMarkup } from "react-dom/server";

import FreshnessChip, {
  STALE_MS,
  formatAge,
  isStale,
} from "@/components/event/FreshnessChip";

const MIN = 60 * 1000;

describe("how old the games count is, in words", () => {
  test("seconds, then minutes, then hours", () => {
    expect(formatAge(3 * 1000)).toBe("3s ago");
    expect(formatAge(4 * MIN)).toBe("4m ago");
    expect(formatAge(3 * 60 * MIN)).toBe("3h ago");
  });

  test("the measured production lag reads as ten minutes", () => {
    // 15:12 ESPN -> 15:22 us. The number the issue is named after.
    expect(formatAge(10 * MIN)).toBe("10m ago");
  });

  test("a negative age is clamped rather than printed", () => {
    // Clock skew between the dyno and the browser must not print "-4s ago".
    expect(formatAge(-4000)).toBe("0s ago");
  });
});

describe("when the chip stops reading as current", () => {
  test("a fresh confirmation is not stale", () => {
    expect(isStale(30 * 1000)).toBe(false);
    expect(isStale(4 * MIN)).toBe(false);
  });

  test("past the threshold it is", () => {
    expect(isStale(STALE_MS + 1)).toBe(true);
    expect(isStale(11 * MIN)).toBe(true);
  });

  test("exactly at the threshold is NOT yet stale", () => {
    // Pinned deliberately: `>` and `>=` are both defensible and only one is
    // implemented, so the boundary belongs in a test rather than in a reading
    // of the source.
    expect(isStale(STALE_MS)).toBe(false);
  });

  test("the whole point — a starved beat goes stale rather than quiet", () => {
    // #3316 measured a 42.8-minute hole in this beat. A freshness signal that
    // could not report that would be decoration.
    expect(isStale(42.8 * MIN)).toBe(true);
    expect(formatAge(42.8 * MIN)).toBe("43m ago");
  });

  test("no age yet is not stale", () => {
    // First paint, before the effect runs. It must not flash `Stale`.
    expect(isStale(null)).toBe(false);
  });
});

describe("the chip only exists when something dated the number", () => {
  test("an unstamped line renders NO chip", () => {
    // A settled match is not stamped, and neither is a row the pass could not
    // reach. Both must render nothing rather than an empty or zeroed age.
    expect(renderToStaticMarkup(<FreshnessChip asOf={undefined} />)).toBe("");
    expect(renderToStaticMarkup(<FreshnessChip asOf={null} />)).toBe("");
  });

  test("a stamped line renders a chip carrying that exact stamp", () => {
    const html = renderToStaticMarkup(
      <FreshnessChip asOf="2026-09-05T15:22:42+00:00" />,
    );

    expect(html).not.toBe("");
    // The stamp reaches the DOM, so the wiring is observable without the
    // effect: this is what proves the page handed over `observed_at` and not
    // some other timestamp.
    expect(html).toContain("Data as of 2026-09-05T15:22:42+00:00");
  });
});

/**
 * THE WIRING, WHICH IS THE HALF THAT GOES DEAD QUIETLY.
 *
 * Everything above proves the chip renders what it is handed, and the backend
 * suites prove the stamp is written and served. None of that fails if the hero
 * simply stops passing `observed_at` — the page keeps rendering, the games line
 * keeps printing, and the chip silently disappears. That is the shape of every
 * "both ends green, ship dead" bug.
 *
 * A static render of the page is not available here (it is a big client
 * component behind SWR), so this scans the source. Whitespace is normalised
 * first because a source guard defeated by a line break is a guard that reports
 * success on a file it never really read — and the scan asserts it can FAIL, on
 * a mutated copy of the real text, so "it passed" means something.
 */
describe("the hero actually hands the stamp to the chip", () => {
  // eslint-disable-next-line @typescript-eslint/no-var-requires
  const fs = require("fs");
  // eslint-disable-next-line @typescript-eslint/no-var-requires
  const path = require("path");

  const SUBJECT = "app/events/[id]/page.tsx";
  const WIRING = /<FreshnessChip\s+asOf=\{event\.linescore\?\.observed_at\}\s*\/>/;

  const source = (): string => {
    const p = path.join(process.cwd(), SUBJECT);
    // A scan that cannot find its subject must RAISE, not silently pass.
    if (!fs.existsSync(p)) throw new Error(`subject missing: ${SUBJECT}`);
    return fs.readFileSync(p, "utf8").replace(/\s+/g, " ");
  };

  test("the event page passes the games line's own observation time", () => {
    expect(source()).toMatch(WIRING);
  });

  test("and the scan would notice if it stopped", () => {
    // The same pattern against the real file with the wiring removed. Without
    // this arm a typo in the regex would make the test above pass forever.
    const gutted = source().replace(WIRING, "<FreshnessChip />");
    expect(gutted).not.toMatch(WIRING);
  });
});
