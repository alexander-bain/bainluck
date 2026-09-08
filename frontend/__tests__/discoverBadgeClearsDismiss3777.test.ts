// #3777 — a Discover card's top-right badge does not hide under the dismiss button.
//
// ═══ THE DEFECT, READ ON PRODUCTION ═══
//
// `/` (Discover, the default landing page) at 390px, 2026-09-08 ~03:20 PT. The
// FIRST card — Vuelta a España 2026, live — printed its status pill as
//
//     ● L
//
// with the rest of the word under the dismiss button. Two elements claimed one
// corner: `DismissBtn` at `absolute top-3 right-3 z-10`, and the `Live` pill at
// `absolute top-3 right-3` with no z-index. The button won.
//
// ═══ WHY THIS IS A SOURCE TEST ═══
//
// The bug is a CSS class collision between two components that never import each
// other. Nothing about it is reachable from rendered output in jsdom, which
// computes no layout: both elements are in the DOM, both are "visible", and the
// overlap exists only under a real box model. Screenshot diffing would catch it
// and is not something this repo runs per-PR.
//
// What CAN be checked cheaply and exactly is the invariant the fix establishes:
// **no badge in a Discover card sits at the dismiss button's coordinates**, and
// every badge that wants the top-right slot uses the one shared constant. That is
// the actual regression — the collision arrived because three call sites
// hand-wrote a position that a fourth had already moved.
//
// The LOOK is what proves the pixels; this is what stops them drifting back.

import { readFileSync, readdirSync } from "fs";
import { join } from "path";

const DISCOVER_DIR = join(__dirname, "..", "components", "discover");

const files = readdirSync(DISCOVER_DIR).filter((f) => f.endsWith(".tsx"));

/** Strip comments: this file's own fix DOCUMENTS the old position. */
const strip = (source: string): string =>
  source
    .replace(/\{\/\*[\s\S]*?\*\/\}/g, "")
    .replace(/\/\*[\s\S]*?\*\//g, "")
    .replace(/(^|[^:])\/\/[^\n]*/g, "$1");

const sources = new Map(
  files.map((f) => [f, strip(readFileSync(join(DISCOVER_DIR, f), "utf8"))]),
);

// The dismiss button's own coordinates, written out rather than read off the
// code under test — a constant lifted from the implementation would agree with
// whatever the implementation currently says.
const DISMISS_SLOT = "absolute top-3 right-3";

describe("#3777 — nothing shares the dismiss button's corner", () => {
  test("the suite is actually reading the components", () => {
    // Vacuity control. A glob that matched nothing would pass every assertion
    // below without looking at a single line.
    expect(files.length).toBeGreaterThan(4);
    expect(files).toContain("ConceptCard.tsx");
    expect(files).toContain("TournamentCard.tsx");
    expect(sources.get("shared.tsx")).toContain("DismissBtn");
  });

  test.each(files)("%s places no badge at the dismiss slot", (file) => {
    const source = sources.get(file)!;
    const hits = source.split(DISMISS_SLOT).length - 1;

    if (file === "shared.tsx") {
      // Exactly one: the dismiss button itself. More would mean a badge has
      // moved back in beside it.
      expect(hits).toBe(1);
      return;
    }
    expect(hits).toBe(0);
  });

  test("every top-right badge uses the shared constant", () => {
    // `ConceptCard` (Live + Final) and `TournamentCard` (Final) are the three
    // that collided; `TrendBadge` in shared.tsx is the one that already had it
    // right. Asserting the count keeps a future fourth badge from hand-rolling
    // the position instead of joining them.
    const uses = [...sources.values()].reduce(
      (n, s) => n + (s.split("TOP_RIGHT_BADGE").length - 1),
      0,
    );
    // 1 declaration + 1 TrendBadge + 2 ConceptCard + 1 TournamentCard, plus the
    // two import statements that carry the name into those files.
    expect(uses).toBeGreaterThanOrEqual(7);

    expect(sources.get("shared.tsx")).toContain(
      'export const TOP_RIGHT_BADGE = "absolute top-3 right-12 z-10"',
    );
  });

  test("the badge slot clears the button rather than merely stacking above it", () => {
    const shared = sources.get("shared.tsx")!;

    // `right-12` is 3rem against the button's `right-3` + `w-7` (1.75rem): the
    // badge starts clear of the button's left edge. A z-index alone would put the
    // pill ON TOP of the button and make the button unclickable — swapping a
    // clipped badge for a dead control, which is worse.
    expect(shared).toContain("right-12");
    expect(shared).not.toContain(
      'export const TOP_RIGHT_BADGE = "absolute top-3 right-3',
    );
  });
});
