/**
 * #4125 ITEM 5 — THE TOURNAMENT PAGE IS ONE SCROLL.
 *
 * Alex read `bainluck.com/tournaments/us-open` on 2026-09-08 at 4:00pm PT and
 * said *"not shareable yet"*, with five items. This file guards one of them:
 *
 *   *"The bracket section feels empty. Build it straight into the Tournament
 *   tab; we wouldn't need that level of tab hierarchy."*
 *
 * ⚠️ ITEM 1 (the grey text) IS GUARDED ELSEWHERE AND DELIBERATELY NOT HERE.
 * `noDiagnosticProseOnTournamentPage4122.test.tsx` covers it, shipped with
 * #4122 (live/112, `2e982387`), which landed while this lane was drafting the
 * same removal and went further than the draft did. One owner per issue
 * (notice 6). Two guards over one ruling is how they drift apart and how a
 * later editor gets contradictory failures, so this file stays off that ground
 * — except for one narrow arm at the bottom, and that arm says why it exists.
 *
 * ═══ WHY THIS IS A SOURCE SCAN AND NOT A RENDER ═══
 *
 * The page is a `"use client"` component that fetches in an effect, so a static
 * render returns the loading shell and proves nothing about a tab bar. The
 * precedent is `tournamentDesktopLayout.test.tsx`, which reads the same file
 * for the same reason. Every SECTION on the page is render-tested in its own
 * suite; what is unproven without this file is the page's own skeleton.
 *
 * ⚠️ SCOPED TO THE RETURN BLOCK, NOT THE FILE. The 130-line doc comment at the
 * top of `page.tsx` is a history of the tab layout and says "Bracket tab" many
 * times, as does the comment recording its removal. A whole-file scan for that
 * phrase would fail on the prose explaining the fix — the classic way a source
 * guard ends up pinned to a comment instead of to code.
 */
import * as fs from "fs";
import * as path from "path";

const PAGE = path.join(__dirname, "..", "..", "app", "tournaments", "[slug]", "page.tsx");
const SOURCE: string = fs.readFileSync(PAGE, "utf8");

/** The JSX the component returns, with every kind of comment stripped. */
function renderedSource(): string {
  const start = SOURCE.indexOf("<ErrorBoundary");
  expect(start).toBeGreaterThan(-1);
  return SOURCE.slice(start)
    .replace(/\{\/\*[\s\S]*?\*\/\}/g, " ")
    .replace(/\/\*[\s\S]*?\*\//g, " ")
    .replace(/^\s*\/\/.*$/gm, " ");
}

describe("#4125 item 5 — one page, one scroll", () => {
  it("renders no tab bar", () => {
    const jsx = renderedSource();
    expect(jsx).not.toContain('role="tablist"');
    expect(jsx).not.toContain("aria-selected");
  });

  it("holds no tab state to switch on", () => {
    // The strongest form: not "the bar is hidden" but "there is nothing left
    // that could bring it back". A `tab` state with no bar is one JSX block
    // away from being a bar again.
    expect(SOURCE).not.toMatch(/const \[tab, setTab\]/);
    expect(SOURCE).not.toMatch(/type Tab =/);
    expect(renderedSource()).not.toMatch(/\btab === /);
  });

  it("renders the bracket unconditionally, on the same scroll as the draw", () => {
    const jsx = renderedSource();
    // POSITIVE FIRST — every other arm here is an absence, and an absence-only
    // suite passes on a page that renders nothing at all.
    expect(jsx).toContain("<TournamentBracket");
    expect(jsx).toContain("<DrawToggle");
    expect(jsx).toContain("<TournamentMatches");
    // …and the grid is BELOW the draw's own sections rather than above them or
    // instead of them. Ordering is the thing that replaced the tab, so ordering
    // is what gets pinned.
    expect(jsx.indexOf("<TournamentBracket")).toBeGreaterThan(jsx.indexOf("<DrawToggle"));
    expect(jsx.indexOf("<TournamentBracket")).toBeGreaterThan(jsx.indexOf("<TournamentMatches"));
  });

  it("no longer gates the draw pill on which tab is showing", () => {
    // Was `{(tab === "tournament" || data.draw_released) && <DrawToggle …>}`.
    // With one page the left arm is always true, and a gate that is always true
    // is one a later reader "fixes" by honouring the right arm — which would
    // hide the pill before the draw is released.
    const jsx = renderedSource();
    expect(jsx).not.toMatch(/data\.draw_released\s*\)\s*&&\s*\(\s*<DrawToggle/);
  });

  it("points nobody at a tab that no longer exists", () => {
    // THE ONE ARM THAT TOUCHES ITEM 1's GROUND, AND THE REASON IT IS HERE.
    // "…are on the Bracket tab" is a #4122 string, already removed and already
    // guarded there. But its correctness now depends on THIS ship: the sentence
    // was merely grey text while the tab existed, and became actively false the
    // moment the tab did not. If item 5 were ever reverted the pointer would be
    // honest again, and if the pointer came back while item 5 stands it would
    // be a lie — so the page-level check belongs with the tab, not with the
    // prose sweep. Scoped to this file only; the general rule is #4122's.
    expect(renderedSource()).not.toContain("Bracket tab");
  });
});
