/**
 * #4125 — THE TOURNAMENT PAGE IS ONE SCROLL, AND CARRIES NO METHOD PROSE.
 *
 * Alex read `bainluck.com/tournaments/us-open` on 2026-09-08 at 4:00pm PT and
 * said *"not shareable yet"*. Two of his five items are structural and land in
 * this file; the other three (the standard card family, chart granularity,
 * doubles) are behaviour and belong with their components.
 *
 *   item 1  *"All the grey text is madness, and shouldn't be user-facing at
 *           all."* → notice 34.
 *   item 5  *"The bracket section feels empty. Build it straight into the
 *           Tournament tab; we wouldn't need that level of tab hierarchy."*
 *
 * ═══ WHY THIS IS A SOURCE SCAN AND NOT A RENDER ═══
 *
 * The page is a `"use client"` component that fetches in an effect, so a static
 * render returns the loading shell and proves nothing about the tab bar. The
 * precedent is `tournamentDesktopLayout.test.tsx`, which reads the same file
 * for the same reason, and every SECTION on the page is render-tested in its
 * own suite — what is unproven without this file is the page's own skeleton.
 *
 * ⚠️ SCOPED TO THE RETURN BLOCK, NOT THE FILE. The 130-line doc comment at the
 * top of `page.tsx` is a history of the tab layout and mentions "Bracket tab"
 * eleven times; so does the comment recording its removal. A whole-file scan
 * for that phrase would fail on the prose explaining the fix, which is the
 * classic way a source guard ends up pinned to a comment instead of to code.
 */
import * as fs from "fs";
import * as path from "path";

const PAGE = path.join(__dirname, "..", "..", "app", "tournaments", "[slug]", "page.tsx");
const SOURCE: string = fs.readFileSync(PAGE, "utf8");

/**
 * The JSX the component returns, with comments stripped.
 *
 * Comments are not code and are not copy: this ship's own explanation of itself
 * names the things it removed, and a scan that could not tell those apart would
 * be unfailable in one direction and unpassable in the other.
 */
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
    // The strongest form of the assertion: not "the bar is hidden" but "there
    // is nothing left that could bring it back". A `tab` state with no bar is
    // one JSX block away from being a bar again.
    expect(SOURCE).not.toMatch(/const \[tab, setTab\]/);
    expect(SOURCE).not.toMatch(/type Tab =/);
    expect(renderedSource()).not.toMatch(/\btab === /);
  });

  it("renders the bracket unconditionally, on the same scroll as the draw", () => {
    const jsx = renderedSource();
    // POSITIVE FIRST — an absence-only suite passes on a page that renders
    // nothing at all, and every other arm here is an absence.
    expect(jsx).toContain("<TournamentBracket");
    expect(jsx).toContain("<DrawToggle");
    expect(jsx).toContain("<TournamentMatches");
    // …and the grid is BELOW the draw's own sections, not above or instead of
    // them. Order is the thing that replaced the tab, so order is pinned.
    expect(jsx.indexOf("<TournamentBracket")).toBeGreaterThan(jsx.indexOf("<DrawToggle"));
    expect(jsx.indexOf("<TournamentBracket")).toBeGreaterThan(jsx.indexOf("<TournamentMatches"));
  });

  it("no longer gates the draw pill on which tab is showing", () => {
    // Was `{(tab === "tournament" || data.draw_released) && <DrawToggle …>}`.
    // With one page the left arm is always true, and a gate that is always true
    // is a gate somebody will later "fix" by reading the right arm again — which
    // would hide the pill before the draw is released.
    const jsx = renderedSource();
    expect(jsx).not.toMatch(/data\.draw_released\s*\)\s*&&\s*\(\s*<DrawToggle/);
  });
});

describe("#4125 item 1 — no method prose in the page body", () => {
  it("has no footer paragraph", () => {
    const jsx = renderedSource();
    expect(jsx).not.toContain("<footer");
    expect(jsx).not.toContain("Each probability combines");
    expect(jsx).not.toContain("daily readings with no smoothing");
  });

  it("names none of the removed explainers anywhere it renders", () => {
    // The six strings Alex listed, by value. They live in five different files
    // and each has its own guard; this arm is the page-level backstop that
    // catches one being re-imported here.
    const jsx = renderedSource();
    for (const gone of [
      "Each probability combines",
      "Questions about reaching a round",
      "Bracket tab",
      "open a match page",
      "could not tie to a market of ours",
      "not when it was created",
      "A half mark means",
    ]) {
      expect(jsx).not.toContain(gone);
    }
  });
});
