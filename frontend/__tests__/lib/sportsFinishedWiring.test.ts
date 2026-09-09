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

  test("the section is built from the POOL, and rendered", () => {
    const code = executableSource();
    // #4454 second pass: page one alone never carries a final (it asks for 20
    // items and the ranker puts them from position 30 down), so the section is
    // built from page one's finals PLUS the deferred lookup's, deduped.
    expect(code).toMatch(/buildFinishedSection\(\s*finishedPool\s*\)/);
    expect(code).toMatch(/data-section-key="results"/);
  });

  test("#4454 second pass: the deferred lookup exists and cannot delay page one", () => {
    const code = executableSource();
    // Gated on `feedData`, so it cannot start until page one has resolved. A
    // bare key here would fire both requests at once and put the section's
    // nice-to-have in a race with the cards the reader is waiting for.
    expect(code).toMatch(/feedData \? sportsFinishedLookupKey\(user\?\.uid\) : null/);
    // Its own key, so it can never land in page one's SWR cache slot.
    expect(code).toMatch(/sportsFinishedLookupKey/);
    // Dense window: the whole reason 40 is enough. Without this the same yield
    // costs a 60-item pull, and the constant below stops making sense.
    expect(code).toMatch(/include_futures:\s*false/);
    expect(code).toMatch(/limit:\s*FINISHED_LOOKUP_LIMIT/);
  });

  test("#4454 second pass: the lookup walks the SAME ladder, and dedups", () => {
    const code = executableSource();
    // A card page one would have refused for an empty envelope must not walk in
    // through the side door — same filter, same partition, in that order.
    expect(code).toMatch(/finishedLookup\?\.items \?\? \[\]\)\.filter\(feedItemHasRenderableContent\)/);
    expect(code).toMatch(/partitionFinishedGames\(renderable\)\.finished/);
    // The same id pagination already dedups on; page one's copy wins.
    expect(code).toMatch(/seen\.has\(getSportsItemId\(item\)\)/);
    expect(code).toMatch(/new Set\(guardedFeed\.finishedGames\.map\(getSportsItemId\)\)/);
  });

  test("page one's OWN limit is untouched — the latency budget is not the fix", () => {
    const code = executableSource();
    // Raising this to reach position 30 was the tempting fix and the wrong one:
    // it triples the first-paint payload to fill a section below the fold.
    expect(code).toMatch(/fetchGroupedFeed\(\{ limit: 20, sportsOnly: true \}\)/);
    expect(code).not.toMatch(/initialFeedRequest\(\s*\d+\s*\)/);
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
