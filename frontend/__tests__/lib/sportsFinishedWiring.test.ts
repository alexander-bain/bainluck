// live/122 (#4454) — THE WIRING ORDER ON /sports, pinned at the call site.
//
// `sportsFinishedSection.test.ts` proves the module decides correctly. It cannot
// prove the PAGE asks it in the right order, and the order is the whole defect:
// settled games must leave the payload BEFORE `applyFinishedCardGuard` sees it.
// Partition afterwards, or run the guard over the partitioned list "to be safe",
// and every unit test in that file stays green while the section on the reader's
// screen silently empties again — which is exactly the state /sports was in when
// Alex went looking for Shelton–Alcaraz.
//
// There is no render harness for `app/sports/page.tsx`, so this is a source scan.
// It reads IDENTIFIERS, never prose, and it strips comments first: this file's
// own docblocks name every symbol below, and an unstripped scan would pass on a
// comment describing the wiring after the wiring itself had been deleted.

import fs from "fs";
import path from "path";

const PAGE = path.resolve(__dirname, "../../app/sports/page.tsx");

/** Source with `//` and block comments removed, so only executable text is scanned. */
function executableSource(): string {
  const raw = fs.readFileSync(PAGE, "utf8");
  return raw
    .replace(/\/\*[\s\S]*?\*\//g, " ")
    .split("\n")
    .map((line) => line.replace(/(^|\s)\/\/.*$/, "$1"))
    .join("\n");
}

describe("/sports asks for the split BEFORE it asks for the freshness guard", () => {
  test("the guard is handed `rest`, never the whole renderable payload", () => {
    const code = executableSource();
    expect(code).toMatch(/partitionFinishedGames\(\s*renderable\s*\)/);
    expect(code).toMatch(/applyFinishedCardGuard\(\s*rest\s*\)/);
    // The pre-#4454 call, and the regression to catch: the guard over everything.
    expect(code).not.toMatch(/applyFinishedCardGuard\(\s*renderable\s*\)/);
  });

  test("exactly one guard call survives — a second one would re-age the finals", () => {
    const calls = executableSource().match(/applyFinishedCardGuard\(/g) ?? [];
    expect(calls).toHaveLength(1);
  });

  test("the section is built from the split, and rendered", () => {
    const code = executableSource();
    expect(code).toMatch(/buildFinishedSection\(\s*guardedFeed\.finishedGames\s*\)/);
    expect(code).toMatch(/data-section-key="results"/);
  });

  test("`no games` accounts for the finals below it (#1091, from the other side)", () => {
    // The guard's own #1091 reprieve no longer covers settled games, so the
    // empty slate has to carry the condition itself — otherwise a "games are
    // quiet" panel sits on top of four of last night's results.
    const code = executableSource();
    expect(code).toMatch(
      /gameSections\.length === 0 && finishedSection\.shown\.length === 0/,
    );
  });
});
