// #883 slice 2 (L2-47): the futures-detail HERO chart must be the single leader
// blend line for ALL market sizes — including >10-outcome markets, which used to
// render the multi-line TournamentChart (contradicting "one clean number + why it
// moved"). Source-inspection guard (like FuturesCardD1) — the page's SWR/chart
// deps make RTL brittle, and the invariant we protect is "the hero no longer
// branches to a multi-line tournament chart", which the source proves directly.

import { readFileSync } from "fs";
import { join } from "path";

const src = readFileSync(
  join(__dirname, "../../app/futures/[id]/page.tsx"),
  "utf8",
);

// Strip comments so our own explanatory comment (which names TournamentChart)
// doesn't trip the assertions — only executed code matters.
const code = src
  .replace(/\/\*[\s\S]*?\*\//g, "")
  .replace(/\/\/.*$/gm, "");

describe("futures-detail hero chart (#883 blend-only, single leader line)", () => {
  test("hero no longer renders the multi-line TournamentChart", () => {
    expect(code).not.toContain("TournamentChart");
  });

  test("no >10-outcome branch on the hero chart", () => {
    // the old `market.outcomes.length > 10 ? <TournamentChart> : ...` branch is gone
    expect(code).not.toMatch(/outcomes\.length\s*>\s*10\s*\?/);
  });

  test("hero renders FuturesChart with a fixed 0-100 axis (blend line)", () => {
    expect(code).toContain("<FuturesChart");
    expect(code).toContain("fixedYAxis");
  });

  test("the progression 'By Stage' table is still available", () => {
    // we only removed the multi-line hero chart, not the progression view
    expect(code).toContain("TournamentProgressionTable");
  });
});

describe("futures-detail edge states (#883 L2-49)", () => {
  test("loading renders an anatomy skeleton, not a spinner void", () => {
    expect(code).toMatch(/animate-pulse/);
    expect(code).not.toContain("LoadingSpinner");
  });

  test("resolved-aware hero (featured winner + resolved flag)", () => {
    expect(code).toContain("pickHeroOutcome");
    expect(code).toContain("resolved={isResolved}");
  });

  test("movement explanation is suppressed on resolved markets", () => {
    expect(code).toMatch(/movementExplanation\s*&&\s*!isResolved/);
  });

  test("honest empty state instead of a broken sparse chart", () => {
    expect(code).toContain("Not enough price history yet");
  });
});
