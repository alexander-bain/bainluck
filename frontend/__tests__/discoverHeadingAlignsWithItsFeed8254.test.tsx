/**
 * #8254 — THE DISCOVER HEADING BAND OVERHUNG THE CARDS, AND A WIDE WINDOW BOUGHT NOTHING.
 *
 * Alex reported this from Safari on an iPad driving an external monitor: a narrow feed marooned in
 * large side margins, under a white "Discover" slab visibly wider than the cards.
 *
 * Measured on production 2026-09-23 (Chromium, `artifacts/ux-1463/8254/geometry-probe-8254.mjs`,
 * real CSS viewports, dpr 1):
 *
 *   window   feed box    slab box    slab overhang   feed uses
 *    390      334         366         16px/side       86%
 *   1180     1100        1132         16px/side       93%
 *   1440     1248        1392         72px/side       87%
 *   1920     1248        1552        152px/side       65%
 *   2560     1248        1552        152px/side       49%
 *
 * Two causes, one number. The header's painted background spans the site shell
 * (`max-w-content` = 1600px, `app/layout.tsx`), while the heading's inner box and the feed both
 * carried a nested `max-w-7xl` (1280px). So (a) the band was free to be wider than the cards —
 * 1552 − 1248 = 304px total, exactly the measured overhang — and (b) the feed was capped 320px
 * below the shell it lives in, so past ~1328px a wider window added only margin.
 *
 * ═══ 🔴 THE ARM THAT ENCODES THE DEFECT IS ARM 2, NOT ARM 1 — AND MUTATION IS HOW I FOUND THAT ═══
 *
 * My first draft led with "the two boxes must declare the same width" and called that the bug. It
 * is not. **Both boxes already said `max-w-7xl` on the broken tree** — the heading TEXT was always
 * aligned with the cards. What overhung them was the `<header>`'s painted BACKGROUND, which spans
 * the shell and is not either of these boxes. Mutant M1 (revert BOTH to `max-w-7xl`) proves it:
 * it reddens only arm 2, while arm 1 passes happily on the defect.
 *
 * So the load-bearing assertion is arm 2 — the shared token is *the shell's own*. That is what
 * closes the gap between the painted band (1552px) and the cards: 1552 − 1520 leaves 16px a side,
 * the shared padding, instead of 152px. Arm 1 is kept as a REGRESSION arm — it was true before and
 * must stay true — and is honestly labelled as such rather than as the fix.
 *
 * 🔴 ARM 3 IS THE ANTI-STRAWMAN. "Delete the cap entirely" aligns the two boxes and satisfies arm 1
 * while letting cards run edge-to-edge on a 2560px monitor. The shared token must still be a CAP.
 *
 * 🔴 ARM 4 IS THE NO-REGRESSION ARM. Alex's complaint is about wide windows; the phone must not pay
 * for it. `max-w-content` (1600px) and `max-w-7xl` (1280px) are both far wider than a 390px or
 * 1180px viewport, so neither binds there and the rendered geometry is unchanged — which the
 * production probe confirms (334px feed at 390px before the change). This arm pins the reasoning:
 * the token stays a max-width, so it cannot bind on a small screen.
 */

import fs from "fs";
import path from "path";

const SOURCE = fs.readFileSync(
  path.join(process.cwd(), "app/discover/page.tsx"),
  "utf8",
);

/** The `<div>` immediately inside the page's sticky `<header>` — the heading's own width box. */
const HEADING_BOX = /<header className="sticky top-0[^"]*">[\s\S]*?<div className="([^"]*)"/;
/** The feed's `<main>`. */
const FEED_BOX = /<main className="([^"]*)"/;

const widthClasses = (className: string) =>
  className
    .split(/\s+/)
    .filter((c) => /^(max-w-|w-)/.test(c))
    .sort();

describe("#8254 — the Discover heading and its feed are one container, not two", () => {
  const heading = SOURCE.match(HEADING_BOX);
  const feed = SOURCE.match(FEED_BOX);

  it("the file still has the two boxes this guard is about", () => {
    // Without this, a refactor that renames either element turns every arm below into a
    // vacuous pass on a null match.
    expect(heading).not.toBeNull();
    expect(feed).not.toBeNull();
  });

  it("ARM 1 (REGRESSION, not the fix) — heading box and feed box still declare the SAME width", () => {
    // Already true on the broken tree: both said `max-w-7xl`, so the heading TEXT was aligned with
    // the cards all along. Kept so a future change cannot move one box without the other — but it
    // is NOT the assertion that catches #8254. See arm 2 and mutant M1.
    expect(widthClasses(heading![1])).toEqual(widthClasses(feed![1]));
    expect(widthClasses(feed![1]).length).toBeGreaterThan(0);
  });

  it("ARM 2 — THE DEFECT ARM: that width is the site shell's own token", () => {
    // `app/layout.tsx` caps the shell at `max-w-content`, and the header's painted background
    // spans exactly that. While these boxes sat at `max-w-7xl` the band overhung the cards by
    // 152px a side; on the shell's token the overhang is the shared 16px padding. Same change
    // stops the feed being capped 320px inside its own shell.
    expect(widthClasses(feed![1])).toContain("max-w-content");
    const layout = fs.readFileSync(path.join(process.cwd(), "app/layout.tsx"), "utf8");
    expect(layout).toContain("max-w-content");
  });

  it("ARM 3 — it is still a CAP, so a 2560px monitor does not run cards edge to edge", () => {
    // "Remove the max-width" also makes arm 1 pass. It is not the fix.
    expect(widthClasses(feed![1]).some((c) => c.startsWith("max-w-"))).toBe(true);
    expect(widthClasses(feed![1])).not.toContain("w-full");
  });

  it("ARM 4 — the phone is untouched: the shared token is a max-width, so it cannot bind at 390px", () => {
    // Measured: the feed box is 334px at a 390px viewport both before and after, because neither
    // 1280px nor 1600px binds there. A width token that were not a max-* could.
    for (const c of widthClasses(feed![1])) expect(c).toMatch(/^max-w-/);
    for (const c of widthClasses(heading![1])) expect(c).toMatch(/^max-w-/);
  });

  it("ARM 5 — the column ladder is unchanged, so the extra width is wider cards, not more of them", () => {
    // Four columns in ~1520px are ~368px each; a fifth would be ~291px, NARROWER than the ~300px
    // the defect produced. Widening and then re-narrowing would satisfy the issue's words and
    // defeat its purpose.
    // #8491 moved the ladder from CSS multi-column to a grid with the same 1/2/3/4 tracks and
    // 16px gutter (MasonryCell); the page renders MASONRY_GRID_CLASS.
    const { MASONRY_GRID_CLASS } = require("../components/discover/MasonryCell");
    expect(SOURCE).toContain("className={MASONRY_GRID_CLASS}");
    expect(MASONRY_GRID_CLASS).toContain("grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 gap-x-4");
    expect(MASONRY_GRID_CLASS).not.toMatch(/cols-5/);
  });
});

/**
 * ═══ THE RESIDUE — two boxes the first fix could not see (ux/1465, 2026-09-23) ═══
 *
 * The deployed LOOK at 1920px paid arms 1–2: band and feed now share 1600px and line up. It also
 * showed the first-run line "Probability, not betting…" starting at x≈336 while the "Discover"
 * title and the cards start at x≈200 — 136px of indent, exactly (1600 − 1280) / 2 − 24. The line
 * lives in `FirstRunOrientation.tsx` with its own `max-w-7xl`, and `app/discover/loading.tsx`
 * (the skeleton, "mirrors app/discover/page.tsx") kept `max-w-7xl` on both boxes, so a wide
 * window drew the skeleton 1280px wide and then jumped to 1600px when the feed arrived.
 *
 * The arms above read ONE file and name two boxes, which is why neither was caught. This arm pins
 * the SET: every page-width box on the Discover route — page, skeleton, and the strip between
 * header and feed — declares the feed's width token.
 */
describe("#8254 residue — every page-width Discover box shares the feed's width", () => {
  const feedWidth = widthClasses(SOURCE.match(FEED_BOX)![1]);
  const read = (rel: string) => fs.readFileSync(path.join(process.cwd(), rel), "utf8");

  const BOXES: Array<[string, RegExp]> = [
    ["loading.tsx header box", HEADING_BOX],
    ["loading.tsx feed box", FEED_BOX],
  ];

  it.each(BOXES)("app/discover/loading.tsx — %s", (_label, box) => {
    const m = read("app/discover/loading.tsx").match(box);
    expect(m).not.toBeNull();
    expect(widthClasses(m![1])).toEqual(feedWidth);
  });

  it("the first-run orientation line sits on the same width as the heading above it", () => {
    const m = read("components/discover/FirstRunOrientation.tsx").match(
      /<div className="([^"]*)" data-testid="discover-orientation"/,
    );
    expect(m).not.toBeNull();
    expect(widthClasses(m![1])).toEqual(feedWidth);
  });

  it("no Discover page-width box is left on the old 1280px cap", () => {
    for (const rel of [
      "app/discover/page.tsx",
      "app/discover/loading.tsx",
      "components/discover/FirstRunOrientation.tsx",
    ]) {
      expect(read(rel)).not.toMatch(/className="[^"]*\bmax-w-7xl\b/);
    }
  });
});
