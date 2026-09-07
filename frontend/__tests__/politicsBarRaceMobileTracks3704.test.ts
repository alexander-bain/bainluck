// #3704 — THE PROBABILITY BELONGS IN THE ROW, NEXT TO THE BAR IT DESCRIBES.
//
// What the shopper saw, `/politics` -> "Presidential 2028" -> Rankings, on
// production at 390px (`artifacts-live-085/hdr-520.png`): all fourteen rows put
// the candidate and the bar on one line and dropped the percentage onto a
// SECOND line, flush against the card's left padding, directly under the name.
// The header did the same thing with its `Now` label — the bare `NOW` above
// row 1 in that capture is not a stray, it is the header's fifth cell.
//
// ── THE MECHANISM, AND IT IS A TRACK COUNT ──────────────────────────────────
//
// `.barRaceHeader` / `.barRaceRow` are ONE grid declaration used by both, and
// under `@media (max-width: 720px)` it declared FOUR columns:
//
//     grid-template-columns: 14px 14px 1fr 42px;      <- four
//
// But a phone renders FIVE cells, not four. Each element has seven children,
// two of which carry `.hideOnMobile` — and `.hideOnMobile` is `display: none`,
// which removes a grid item from FLOW, it does not merely blank it. So the
// spark and the Δ chip vanish as tracks, and what is left is
//
//     rank · party · name · bar · pct          <- five
//
// Five children into four tracks: the fifth auto-flows into an IMPLICIT second
// row, at column 1. That is the whole bug. The number was not mis-styled and it
// was not wrapping its text — it was in a different grid row, at the far left,
// the full width of the card away from the bar encoding the same quantity.
//
// The four-track list was not arbitrary either: `14px 14px 1fr 42px` is rank,
// party, name, pct. It reads as a list written for the four cells someone MEANT
// to keep, with the bar — which is not optional and is never hidden —
// forgotten. So `pct` did not fall off the end; it was displaced by `barWrap`
// silently taking the track written for it, and 42px is why the bar rendered as
// a 42px pill on a phone. Both halves come out of the one missing track.
//
// ── WHY THIS TEST IS SHAPED THE WAY IT IS ───────────────────────────────────
//
// The invariant has one foot in each of two files and cannot be seen from
// either alone:
//
//     tracks declared for a phone  ==  children that SURVIVE `display: none`
//
// jsdom applies no media query and the CSS Module is swapped for a proxy under
// jest (see `__tests__/helpers/cssModuleProxy.js`), so a render test cannot
// read a single one of these numbers — a rendered `.barRaceRow` reports all
// seven children and no columns at all. The only place the phone layout exists
// is the stylesheet, so this guard reads both sources and holds them against
// each other. It therefore fails for EITHER drift: a sixth cell added to the
// markup, or a track removed from the media query.
//
// Both parsers assert what they found before they assert anything about it. A
// source-scanning guard that quietly matches nothing is worse than no guard,
// so a rename or a reformat that defeats the parse fails here loudly instead of
// going green on an empty set.
//
//   npx jest --testPathPatterns=politicsBarRaceMobileTracks3704

import fs from "node:fs";
import path from "node:path";

const PAGE = fs.readFileSync(
  path.join(__dirname, "..", "app", "politics", "page.tsx"),
  "utf8",
);
const CSS = fs.readFileSync(
  path.join(__dirname, "..", "app", "politics", "politics.module.css"),
  "utf8",
);

const MOBILE_BREAKPOINT = "@media (max-width: 720px)";

/* ═══ 1 · what the markup renders ═══════════════════════════════════════ */

/**
 * The direct children of one JSX element, by indentation.
 *
 * `openMatcher` finds the element's opening line; its children are the lines
 * indented exactly one step deeper that START a tag. Closing tags are excluded
 * by the `(?!\/)`, which is what keeps `barWrap`'s own `</div>` — a line at
 * child depth — from being counted as a sixth cell.
 */
function gridChildren(openMatcher: RegExp): string[] {
  const lines = PAGE.split("\n");
  const openIdx = lines.findIndex((l) => openMatcher.test(l));
  if (openIdx === -1) {
    throw new Error(
      `#3704 guard cannot find ${openMatcher} in app/politics/page.tsx. ` +
        `If the element was renamed or moved, re-point this guard — do not delete it.`,
    );
  }

  const openIndent = lines[openIdx].search(/\S/);
  const childIndent = openIndent + 2;
  const children: string[] = [];

  for (let i = openIdx + 1; i < lines.length; i++) {
    const line = lines[i];
    if (!line.trim()) continue;
    const indent = line.search(/\S/);
    if (indent <= openIndent) break; // the element's own closing tag
    if (indent !== childIndent) continue; // nested content, not a grid cell
    if (/^<(?!\/)/.test(line.trim())) children.push(line.trim());
  }
  return children;
}

const HEADER_CELLS = gridChildren(/<div className=\{s\.barRaceHeader\}>/);
const ROW_CELLS = gridChildren(/<div key=\{c\.name\} className=\{s\.barRaceRow\}>/);

const hiddenOnPhone = (cells: string[]) =>
  cells.filter((c) => c.includes("s.hideOnMobile")).length;

describe("#3704 · the markup the parser is reasoning about", () => {
  test("header and row are the SAME grid shape — one declaration serves both", () => {
    // The stylesheet styles `.barRaceHeader, .barRaceRow` together. That is only
    // sound while their cell counts agree; if they ever diverge, the shared
    // declaration is the bug and this is where it surfaces.
    expect(HEADER_CELLS).toHaveLength(7);
    expect(ROW_CELLS).toHaveLength(7);
  });

  test("exactly two cells leave the grid on a phone, in both", () => {
    expect(hiddenOnPhone(HEADER_CELLS)).toBe(2);
    expect(hiddenOnPhone(ROW_CELLS)).toBe(2);
  });

  test("the bar and the pct are cells in their own right, and neither is hidden", () => {
    // The regression put these two in one track. Naming them keeps a future
    // edit from "simplifying" the pct back inside `barWrap`.
    const barWrap = ROW_CELLS.find((c) => c.includes("s.barWrap"));
    const pct = ROW_CELLS.find((c) => c.includes("s.pct"));
    expect(barWrap).toBeDefined();
    expect(pct).toBeDefined();
    expect(barWrap).not.toContain("s.hideOnMobile");
    expect(pct).not.toContain("s.hideOnMobile");
  });
});

/* ═══ 2 · what the stylesheet declares ══════════════════════════════════ */

/** Track count of a `grid-template-columns` value, paren-aware. */
function countTracks(value: string): number {
  let depth = 0;
  let current = "";
  const tracks: string[] = [];
  for (const ch of value.trim()) {
    if (ch === "(") depth++;
    if (ch === ")") depth--;
    // `minmax(32px, 1fr)` is ONE track: only split on whitespace at depth 0.
    if (/\s/.test(ch) && depth === 0) {
      if (current) tracks.push(current);
      current = "";
    } else {
      current += ch;
    }
  }
  if (current) tracks.push(current);
  return tracks.length;
}

/** The `grid-template-columns` declared for the bar race, inside `block`. */
function barRaceTracks(block: string, where: string): number {
  const rule = block.match(
    /\.barRaceHeader,\s*\n\s*\.barRaceRow\s*\{[^}]*?grid-template-columns:\s*([^;]+);/,
  );
  if (!rule) {
    throw new Error(
      `#3704 guard found no shared .barRaceHeader/.barRaceRow ` +
        `grid-template-columns ${where}. The phone layout lives only here.`,
    );
  }
  return countTracks(rule[1]);
}

const MOBILE_BLOCK = (() => {
  const start = CSS.indexOf(MOBILE_BREAKPOINT);
  if (start === -1) {
    throw new Error(`#3704 guard cannot find "${MOBILE_BREAKPOINT}" in politics.module.css`);
  }
  return CSS.slice(start);
})();

describe("#3704 · the phone grid declares a track for every cell it renders", () => {
  test("the mobile track count equals the cells that survive display:none", () => {
    const visibleOnPhone = ROW_CELLS.length - hiddenOnPhone(ROW_CELLS);
    expect(visibleOnPhone).toBe(5); // rank · party · name · bar · pct

    // THE REGRESSION ASSERTION. This read 4 before the fix.
    expect(barRaceTracks(MOBILE_BLOCK, "inside the mobile media query")).toBe(
      visibleOnPhone,
    );
  });

  test("`.hideOnMobile` is display:none — which is WHY those cells leave flow", () => {
    // The count above is only correct because the hidden cells are removed from
    // the grid rather than blanked in place. Swap this for `visibility: hidden`
    // or `opacity: 0` and the phone needs SEVEN tracks, not five — the arithmetic
    // this whole guard rests on changes, so it is pinned here rather than assumed.
    const rule = MOBILE_BLOCK.match(/\.hideOnMobile\s*\{([^}]*)\}/);
    expect(rule).not.toBeNull();
    expect(rule![1]).toMatch(/display:\s*none/);
  });

  test("the desktop grid still declares a track for all seven cells", () => {
    // The other half of the same invariant, and the reason the bug was invisible
    // at 1280px: nothing is hidden there, so seven cells need seven tracks.
    const desktop = CSS.slice(0, CSS.indexOf(MOBILE_BREAKPOINT));
    const header = desktop.match(
      /\.barRaceHeader\s*\{[^}]*?grid-template-columns:\s*([^;]+);/,
    );
    const row = desktop.match(
      /\.barRaceRow\s*\{[^}]*?grid-template-columns:\s*([^;]+);/,
    );
    expect(header).not.toBeNull();
    expect(row).not.toBeNull();
    expect(countTracks(header![1])).toBe(HEADER_CELLS.length);
    expect(countTracks(row![1])).toBe(ROW_CELLS.length);
  });
});

/* ═══ 3 · the bar is the flexible track, not the name ═══════════════════ */

describe("#3704 · every row's bar is the same width", () => {
  test("the phone grid sizes the NAME fixed and the BAR flexible", () => {
    // Each row is its own grid — `.barRaceRow` is per-candidate, not a subgrid —
    // so a content-sized name column would resolve differently in every row and
    // the bars would stop being comparable down the column. That is the trap this
    // pins: the name track must not be `auto`/`max-content`, and the slack must
    // land on the bar. (It also means the bar, not dead whitespace, absorbs the
    // extra width on a 430px phone.)
    const rule = MOBILE_BLOCK.match(
      /\.barRaceHeader,\s*\n\s*\.barRaceRow\s*\{[^}]*?grid-template-columns:\s*([^;]+);/,
    );
    const tracks = rule![1].trim().split(/\s+(?![^(]*\))/);
    const [, , name, bar] = tracks;

    expect(name).toMatch(/^\d+px$/); // fixed: same in every row
    expect(name).not.toMatch(/auto|max-content|min-content/);
    expect(bar).toContain("fr"); // the slack lands here
  });

  test("the bar track carries an EXPLICIT minimum, so the header cannot widen it", () => {
    // A bare `1fr` is `minmax(auto, 1fr)`, and that `auto` floor is min-content.
    // The header's cell over this track holds the unbreakable word "PROBABILITY";
    // a row's holds only `.barWrap`. Under a bare `1fr` the header's bar track
    // would float up to the width of that word while every row's stayed at the
    // fr share, and the header would stop lining up with the rows it labels —
    // silently, and only on a phone. The explicit minimum is what forbids that.
    const rule = MOBILE_BLOCK.match(
      /\.barRaceHeader,\s*\n\s*\.barRaceRow\s*\{[^}]*?grid-template-columns:\s*([^;]+);/,
    );
    const bar = rule![1].trim().split(/\s+(?![^(]*\))/)[3];
    expect(bar).toMatch(/^minmax\(\s*\d+px\s*,\s*1fr\s*\)$/);
  });
});
