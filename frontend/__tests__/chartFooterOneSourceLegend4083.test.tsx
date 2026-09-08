// #4083 — ONE SOURCE LEGEND ON THE WIN-PROBABILITY CARD, AND IT IS THE CHART'S.
//
// ── WHAT THE READER SAW ──────────────────────────────────────────────────────
//
// `bainluck.com/events/15306264` (Padres 3–2 Nationals, a seven-source MLB
// final), **390px**, 2026-09-08T22:40Z. One card, read top to bottom:
//
//     ——— Bain Luck        + 6 sources ⌄        <- OddsChart's own legend
//     Final  3 - 2   Padres 100% — Nationals 0%
//     ——— BainLuck    ——— Sportsbooks   ——— Kalshi
//     ——— Polymarket  ——— MLB Model     ——— ESPN      Sources ⌄
//     ——— Bain Luck Model
//
// Three defects, one cause — a second legend had grown underneath the first:
//
//   1. WE SPELLED OUR OWN NAME TWO WAYS, two rows apart: the chart's `Bain
//      Luck` and the footer's hard-coded `BainLuck`. #2442's rule — "through
//      the source registry, so this chip and the chart legend beside it cannot
//      spell one supplier two ways" — was written for SUPPLIERS, so the one
//      name we control was the only one exempt from it.
//   2. TWO CONTROLS, STACKED, BOTH SAYING "SOURCES": the `+ 6 sources ⌄` press
//      and, ten pixels below, `Sources ⌄`.
//   3. THE CLICK-IN REVEALED WHAT THE READER WAS ALREADY LOOKING AT. `+ N
//      sources` is the press Alex ratified (UX-P154, panel 3B over 3A) for
//      D91(b) — "a user who clicks into the Bain Luck aggregated line sees the
//      underlying source lines". It reveals a seven-chip legend. The footer was
//      already showing that legend, permanently.
//
// ── WHY THAT LAST ONE IS THE SHIP AND NOT A NEATNESS COMPLAINT ───────────────
//
// Alex, relayed to ux 2026-09-08 2:05pm PT (standing notice 33's addendum):
//
//   > "We had this 99% right for months, where the sourcing was clear without
//   >  coming across as an endorsement, and it only got messed up recently, so
//   >  don't reinvent the wheel."
//
// A collapsed press reads as sourcing. A permanent roll-call of seven supplier
// names under a number reads as endorsement. The mechanism he asked for was
// present and working the whole time; what had accumulated beside it was the
// half that undoes it.
//
// ── THERE IS NO COMMIT TO REVERT, WHICH IS WHY THIS IS A GUARD ───────────────
//
// The addendum says restore, so the first move was `git log` on `OddsChart.tsx`:
// #3973 (y-axis zoom), #3892 (callout rounding), #3563 (legend grammar), #3561,
// #3541, #3525. None removes a click-in; none adds the second control. The press
// and the always-on legend ACCUMULATED ALONGSIDE each other — nobody replaced
// anything. A drift with no single bad commit cannot be prevented by reverting
// one, so the rule gets written down instead.
//
// ── WHY A SOURCE SCAN ────────────────────────────────────────────────────────
//
// The subject is JSX inside a default-exported Next.js page: no function to
// call, no value to assert on, and jsdom does not lay out. Same reasoning as
// #3427, which guards the same row — and the same mitigation: every rule below
// has a POSITIVE CONTROL built from the markup that actually shipped, so a rule
// that has stopped describing the bug fails here rather than passing quietly.

import { readFileSync } from "fs";
import { join } from "path";

const PAGE = join(process.cwd(), "app/events/[id]/page.tsx");
const CHART = join(process.cwd(), "components/OddsChart.tsx");

/**
 * The chart footer row — the `border-t` strip holding the disclosure. Located
 * by the button it contains rather than by a line number, so edits above it
 * cannot silently move the guard onto a different element.
 */
function chartFooterRow(source: string): string {
  const button = source.indexOf("setSourcesOpen(!sourcesOpen)");
  expect(button).toBeGreaterThan(-1);
  const rowStart = source.lastIndexOf("border-t border-surface-border", button);
  expect(rowStart).toBeGreaterThan(-1);
  return source.slice(rowStart, button + 400);
}

/**
 * JSX with comments stripped. Every rule below is about what RENDERS, and this
 * file's own explanatory comments quote the strings it bans — so a scan that
 * reads comments would fail on its own documentation, and the obvious "fix"
 * would be to stop writing the documentation down.
 */
function rendered(source: string): string {
  return source.replace(/\/\*[\s\S]*?\*\//g, "").replace(/^\s*\/\/.*$/gm, "");
}

describe("#4083 the win-probability card carries one source legend", () => {
  const page = rendered(readFileSync(PAGE, "utf8"));
  const chart = rendered(readFileSync(CHART, "utf8"));
  const row = chartFooterRow(page);
  /**
   * The row MINUS its disclosure button. The chips stood to the left of the
   * button, and the button's own label is now the word `Sportsbooks` — so a
   * name scan over the whole row would fire on the fix. Split, and each half
   * gets the rule that belongs to it.
   */
  const besideTheButton = row.slice(0, row.indexOf("<button"));

  it("the footer strip names no source of its own", () => {
    // The seven chips, by the names they rendered. Any one of them back in this
    // row means the second legend has returned, whether or not the other six do
    // — the duplication is per-name, not all-or-nothing.
    for (const name of [
      "BainLuck",
      "Sportsbooks",
      "Kalshi",
      "Polymarket",
      "MLB Model",
      "Bain Luck Model",
      "ESPN",
    ]) {
      expect(besideTheButton).not.toContain(`>${name}<`);
    }
  });

  it("the footer strip draws no legend swatch", () => {
    // A name is only half a chip. The `w-4 h-[2px]` rule was the coloured line
    // beside each label, and a chip list rebuilt from `sourceLabel(...)` calls
    // would carry the swatches while dodging every literal above.
    expect(row).not.toContain("w-4 h-[2px]");
    expect(row).not.toContain("sourceLabel(");
    expect(row).not.toMatch(/\.map\(\s*\(?\s*chip/);
  });

  it("the page hard-codes no source or brand name into the chart card", () => {
    // The narrower rule the footer taught us: `BainLuck` unspaced is not a
    // supplier we can pick up from a registry, it is our own name typed by
    // hand, and it was wrong for as long as it existed. `Bain Luck Model` is a
    // real distinct source (the stat model) and is allowed — via the registry,
    // in the chart's legend, which is why this asserts on the page only.
    expect(page).not.toContain("BainLuck");
  });

  it("the surviving disclosure names the table it opens, not 'Sources'", () => {
    // `Sources ⌄` under `+ 6 sources ⌄` was two affordances for one idea. It
    // opens `BookmakerTable`, whose own first column is headed "Sportsbook", so
    // naming it is both the collision fix and the more truthful label — and it
    // is the vocabulary D91/notice 33 settled on.
    expect(row).toContain(">Sportsbooks<");
    expect(row).not.toContain(">Sources<");
  });

  it("the per-sportsbook table is still reachable — the control was renamed, not removed", () => {
    // THE FIX THAT WOULD HAVE BEEN WRONG. The issue's own wording is "keep ONE
    // control", and deleting this one satisfies it while silently taking the
    // per-sportsbook probability table off the event page. Nobody asked for
    // that, and a reader who wants to see the eleven books behind "Sportsbooks"
    // has nowhere else on this page to go.
    expect(page).toContain("setSourcesOpen(!sourcesOpen)");
    expect(page).toContain("<BookmakerTable");
  });

  it("the chart's legend is collapsed by default, so the press has something to reveal", () => {
    // D91(b) as Alex describes it: the aggregated line is the default and the
    // source lines are what clicking in adds. If this initialises to `true` the
    // card is back where it started — every source named before anyone asked.
    expect(chart).toMatch(/legendExpanded[\s\S]{0,40}useState\(false\)/);
    // And the chips are gated on it: rendered when the reader expands, or in
    // sportsbooks-only mode where there is no blend for them to compete with.
    expect(chart).toContain("(!isMultiSource || legendExpanded) && resolvedSources.map");
  });

  it("carries ux/1034 B7 forward: the surviving legend still reads the payload", () => {
    // Alex asked B7 be VERIFIED, not built — "the legend must pick [Polymarket]
    // up without a deploy". That rule used to live in `lib/chartSourceChips.ts`,
    // which fed the strip this ship deleted. It is not lost: `resolvedSources`
    // iterates the payload's own series and resolves every name and colour
    // through the same registry, one layer up. Deleting the module without
    // moving its rule here is how a guarded property becomes an unguarded one.
    expect(chart).toContain("Object.entries(winProbHistory)");
    expect(chart).toContain("sourceLabel(key,");
  });

  it("POSITIVE CONTROL: every rule fires on the markup that shipped", () => {
    // The footer exactly as it stood, trimmed to the parts the rules read. If
    // this reconstruction passed, the rules would be describing something other
    // than the card Alex was looking at.
    const shipped =
      '<div className="px-4 sm:px-5 py-2 border-t border-surface-border flex items-center justify-between gap-2">' +
      '<div className="flex flex-wrap items-center gap-x-4 gap-y-1 min-w-0">' +
      '<div className="flex items-center gap-1.5">' +
      '<div className="w-4 h-[2px] rounded" style={{ backgroundColor: c }} />' +
      '<span className="text-[10px] text-text-muted">BainLuck</span></div>' +
      '<span className="text-[10px] text-text-muted">{sourceLabel("betting")}</span>' +
      "{sourceChips.map((chip) => (" +
      '<span className="text-[10px] text-text-muted">{chip.label}</span>))}' +
      "</div><button onClick={() => setSourcesOpen(!sourcesOpen)}>" +
      '<span className="text-[10px] text-text-muted font-medium">Sources</span>';

    // Through the SAME split the real rule uses, so the control exercises the
    // predicate rather than a lookalike of it.
    expect(shipped.slice(0, shipped.indexOf("<button"))).toContain(">BainLuck<");
    expect(shipped).toContain("w-4 h-[2px]");
    expect(shipped).toContain("sourceLabel(");
    expect(shipped).toMatch(/\.map\(\s*\(?\s*chip/);
    expect(shipped).toContain(">Sources<");
    expect(shipped).not.toContain(">Sportsbooks<");
  });
});
