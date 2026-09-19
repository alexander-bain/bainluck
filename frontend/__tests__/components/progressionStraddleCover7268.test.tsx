/**
 * #7268 — an overflowing championship grid never opens with half a column.
 *
 * WHAT A READER SAW. `/playoffs/epl`, 390px, production, the landing state with
 * no interaction at all: between the team name and `Champion` a narrow vertical
 * band of grey fragments — `%`, `5.0`, `4h` stacked on top of each other, one
 * per row, down all 20 rows, and a lone `4` floating in the header. It reads as
 * rendering damage. It is in fact `Top 4`: 38px of it hidden behind the sticky
 * `Team` cell and 27px showing, and 27px of a CENTRE-aligned wrapped cell is
 * its right-hand off-cuts with every number gone.
 *
 * THE MECHANISM. `sortColumnScrollLeft` (#7192) solves for the sort column and
 * has no term for the column that lands straddling the sticky cell's edge.
 *
 * WHY IT IS NOT FIXED BY SCROLLING — the reading #7268 itself proposed, and the
 * reason arm A carries production numbers instead of invented ones. Measured at
 * 390px on all six grids that overflow, every one of them straddles:
 *
 *     grid  straddling column  hidden  SHOWING  scroll slack
 *     nba   Conference             67       26             0
 *     nfl   Conference             71       22             4
 *     mlb   AL / NL Champ         101       13             5
 *     nhl   Conference             72       21             8
 *     mls   Conference             52       41             8
 *     epl   Top 4                  38       27             1
 *
 * The sort column is the RIGHTMOST column, so resting its right edge on the
 * container's right edge lands at the scroller's own maximum — `scroll slack`
 * is the entire remaining travel and it is 0-8px against slivers of 13-41px.
 * Scrolling the other way, until the straddler is whole, re-clips the sort
 * column by 31-59px, which is the regression #7192 exists to prevent. No offset
 * puts every boundary outside the sticky cell. The fix is therefore what we
 * paint, and this guard is on the painting.
 *
 * WHY ARM B IS A SOURCE SCAN. jsdom has no layout — every rect, `clientWidth`
 * and `scrollWidth` reads 0 — so the effect that measures the straddler cannot
 * be exercised at all and a render assertion would pass against the bug. The
 * arithmetic is pure and lives in arm A; arm B pins the wiring that carries it
 * to the screen. Comment-stripped per #3035: the fix's own comment quotes
 * `bg-surface-card`, `z-10` and the measured table, so an un-stripped scan reads
 * the prose as code and passes on a component that renders none of it.
 */

import { readFileSync } from "fs";
import { join } from "path";

import { stickyStraddleCover } from "../../components/TournamentProgressionTable";

const CODE = readFileSync(
  join(__dirname, "../../components/TournamentProgressionTable.tsx"),
  "utf8",
)
  .replace(/\/\*[\s\S]*?\*\//g, "")
  .replace(/^\s*\/\/.*$/gm, "");

/**
 * The JSX block for one element, from its testid back to its opening `<div`
 * and forward to the self-closing `/>`. Element-scoped, because a file-scoped
 * `toContain` cannot say WHICH element carries the class it found — the
 * over-reach #7246 had to narrow in #7192's guard, twice.
 */
function blockFor(testid: string): string {
  const at = CODE.indexOf(`data-testid="${testid}"`);
  expect(at).toBeGreaterThan(-1);
  const open = CODE.lastIndexOf("<div", at);
  const close = CODE.indexOf("/>", at);
  expect(open).toBeGreaterThan(-1);
  expect(close).toBeGreaterThan(at);
  return CODE.slice(open, close + 2);
}

/**
 * The six grids that overflow at 390px, exactly as production measured them on
 * 2026-09-19 (`artifacts/ux-1365/straddle-all-7268.json`). Column boxes are
 * given in CONTENT coordinates — which is how a column is actually laid out,
 * scroll-free — and converted to the scroller's client box here, so the numbers
 * below can be read straight off the page and a later re-measure can replace
 * them without arithmetic.
 */
const GRIDS: {
  slug: string;
  stickyRight: number;
  scrollLeft: number;
  cols: [number, number][];
  sliver: number;
}[] = [
  { slug: "nba", stickyRight: 188, scrollLeft: 243, sliver: 26,
    cols: [[188, 296], [296, 364], [364, 457], [457, 551]] },
  { slug: "nfl", stickyRight: 188, scrollLeft: 247, sliver: 22,
    cols: [[188, 296], [296, 364], [364, 457], [457, 559]] },
  { slug: "mlb", stickyRight: 188, scrollLeft: 277, sliver: 13,
    cols: [[188, 296], [296, 364], [364, 478], [478, 590]] },
  { slug: "nhl", stickyRight: 188, scrollLeft: 248, sliver: 21,
    cols: [[188, 296], [296, 364], [364, 457], [457, 564]] },
  { slug: "mls", stickyRight: 188, scrollLeft: 52, sliver: 41,
    cols: [[188, 281], [281, 368]] },
  { slug: "epl", stickyRight: 188, scrollLeft: 121, sliver: 27,
    cols: [[188, 271], [271, 336], [336, 430]] },
];

const clientCols = (g: (typeof GRIDS)[number]) =>
  g.cols.map(([left, right]) => ({ left: left - g.scrollLeft, right: right - g.scrollLeft }));

describe("#7268 arm A — what is showing of a half-covered column", () => {
  test.each(GRIDS)(
    "/playoffs/$slug covers exactly the $sliver px its straddler leaves showing",
    (g) => {
      expect(
        stickyStraddleCover({ cols: clientCols(g), stickyRight: g.stickyRight }),
      ).toBe(g.sliver);
    },
  );

  test("it is what SHOWS, not the column's width", () => {
    // The mutant this kills returns the straddler's full width, which on every
    // grid above is 2-9x the answer and would paint over the sort column.
    const epl = GRIDS.find((g) => g.slug === "epl")!;
    const straddler = clientCols(epl)[1];
    expect(straddler.right - straddler.left).toBe(65); // `Top 4` is 65px wide
    expect(stickyStraddleCover({ cols: clientCols(epl), stickyRight: 188 })).toBe(27);
  });

  test("a grid resting at the seam — every boundary clear — is not covered", () => {
    // THE STATE THAT MAKES THE `left <` TEST LOAD-BEARING. Un-scrolled, the
    // first stage column BEGINS where the sticky block ends, so its right edge
    // is past the seam and its left edge is exactly on it. Without that test
    // the answer here is the whole column and a fix for a sliver blanks a
    // column nobody was hiding.
    const cols = [{ left: 188, right: 271 }, { left: 271, right: 336 }];
    expect(stickyStraddleCover({ cols, stickyRight: 188 })).toBe(0);
  });

  test("a column wholly PAST the seam is not covered", () => {
    expect(
      stickyStraddleCover({ cols: [{ left: 200, right: 280 }], stickyRight: 188 }),
    ).toBe(0);
  });

  test("a column wholly BEHIND the seam is not covered, and never negatively", () => {
    // Left to itself this returns `right - stickyRight`, a negative width. Every
    // grid above has one or two of these to the left of its straddler, so the
    // table would catch it too — but the claim deserves its own name.
    const cover = stickyStraddleCover({
      cols: [{ left: -55, right: 53 }, { left: 53, right: 121 }],
      stickyRight: 188,
    });
    expect(cover).toBe(0);
  });

  test("jsdom's all-zero layout asks for no cover", () => {
    expect(stickyStraddleCover({ cols: [{ left: 0, right: 0 }], stickyRight: 0 })).toBe(0);
    expect(stickyStraddleCover({ cols: [], stickyRight: 188 })).toBe(0);
  });

  test("an unmeasured sticky cell asks for no cover", () => {
    // `stickyRight` is 0 when the name header has no box yet. Nothing may be
    // painted from that, least of all a cover the width of a whole column.
    expect(
      stickyStraddleCover({ cols: [{ left: 67, right: 150 }], stickyRight: 0 }),
    ).toBe(0);
  });

  test("sub-pixel overhang is not a straddle", () => {
    // Matches `sortColumnScrollLeft`'s tolerance: fractional layout widths leave
    // a column a hair past an edge, and painting 0.3px is a repaint on every
    // resize for nothing.
    expect(
      stickyStraddleCover({ cols: [{ left: 100, right: 188.3 }], stickyRight: 188 }),
    ).toBe(0);
    expect(
      stickyStraddleCover({ cols: [{ left: 187.7, right: 260 }], stickyRight: 188 }),
    ).toBe(0);
  });

  test("the straddler is found by geometry, not by position in the list", () => {
    // `AL / NL Champ` is the THIRD of MLB's four columns and the answer is 13px;
    // a mutant that reaches for the first, the last, or the widest is wrong by
    // 100px or more.
    const mlb = GRIDS.find((g) => g.slug === "mlb")!;
    const cols = clientCols(mlb);
    expect(stickyStraddleCover({ cols, stickyRight: 188 })).toBe(13);
    expect(cols[0].right - 188).not.toBe(13);
    expect(cols[cols.length - 1].right - 188).not.toBe(13);
  });
});

describe("#7268 arm B — the component paints it, and only where it should", () => {
  test("the cover is measured on every scroll and resize, not frozen at mount", () => {
    // It lives in the same callback as the seam it sits on, which the existing
    // guards already pin to `onScroll` and the ResizeObserver.
    const sync = CODE.slice(
      CODE.indexOf("const syncScrollAffordance"),
      CODE.indexOf("const alignSortColumn"),
    );
    expect(sync).toContain("stickyStraddleCover(");
    expect(sync).toContain("setStraddleCover(");
    // Measured off the stage headers themselves and the same name cell the seam
    // is measured from — not a constant, which would be wrong at one of the
    // `Team` column's two widths.
    expect(sync).toContain("stageThRefs.current.values()");
    expect(sync).toMatch(/stickyRight: nameBox \? nameBox\.right - scrollerLeft : 0/);
  });

  test("the cover is an inert opaque extension of the sticky block", () => {
    const cover = blockFor("progression-straddle-cover");
    expect(cover).toContain("pointer-events-none absolute");
    expect(cover).toContain("inset-y-0");
    expect(cover).toContain("bg-surface-card");
    expect(cover).toContain('aria-hidden="true"');
    // OPAQUE, not a fade — the fade is the defect. The cue at this same seam is
    // 32px of `bg-gradient-to-r` and across a 27px sliver it is 16% opaque at
    // the far end, which greys the off-cuts and leaves them legible.
    expect(cover).not.toContain("bg-gradient");
    // NOT z-10. The sticky cells are, and they must keep winning.
    expect(cover).not.toMatch(/\bz-\d/);
  });

  test("its width and position come from the measurement, not from literals", () => {
    const cover = blockFor("progression-straddle-cover");
    expect(cover).toContain("width: straddleCover");
    expect(cover).toContain("left: stickyEdge");
    // A Tailwind width class would silently win over the measured one.
    expect(cover).not.toMatch(/\bw-\d/);
    expect(cover).not.toMatch(/\bw-\[/);
  });

  test("nothing is painted when nothing is straddling", () => {
    // The common case — every desktop, and any grid whose columns fall clear of
    // the seam. `> 0` and not `>= 0`: a zero-width opaque div is still a div in
    // the tree and this fix must be inert where there is no defect.
    expect(CODE).toContain("straddleCover > 0 && (");
  });

  test("the fade moves out beyond the cover instead of sitting under it", () => {
    // Two overlays at the same x would put the gradient's opaque end on top of
    // the cover and its transparent end on the straddler — the defect again,
    // through a second element.
    const cue = blockFor("progression-scroll-affordance-left");
    expect(cue).toContain("left: stickyEdge + (restingOnAlignment ? straddleCover : 0)");
    // And the cue itself is otherwise untouched: #7192 measured this seam and
    // #7246 narrowed it, and neither claim is being reopened here.
    expect(cue).toContain(
      "pointer-events-none absolute inset-y-0 w-8 bg-gradient-to-r from-surface-card to-transparent",
    );
  });

  test("the cover exists only while the grid rests where the alignment put it", () => {
    // WHY, and it is not tidiness: the width is discontinuous. Drag the
    // straddler left and the cover grows with it, and the instant its left edge
    // clears the seam it straddles nothing and the cover is 0 — so a reader
    // mid-drag watches up to 65px of cover vanish and a whole column appear at
    // once. The landing state is what #7268 photographed and what no reader
    // chose; a reader driving the scroller gets an ordinary scroller.
    expect(CODE).toContain("restingOnAlignment && straddleCover > 0 && (");
    const align = CODE.slice(
      CODE.indexOf("const alignSortColumn"),
      CODE.indexOf("const handleScroll"),
    );
    expect(align).toContain("setRestingOnAlignment(true)");
    // Set BEFORE the `next === null` bail, so a grid the arithmetic declines to
    // move is still resting on the alignment it endorsed.
    expect(align.indexOf("setRestingOnAlignment(true)")).toBeLessThan(
      align.indexOf("if (next === null) return;"),
    );
  });

  test("the component does not mistake its own scroll for the reader taking over", () => {
    // The alignment assigns `scrollLeft`, which fires a scroll event. If that
    // cleared the resting flag the cover would exist for one frame and never
    // again — which looks exactly like the fix not working.
    const handler = CODE.slice(
      CODE.indexOf("const handleScroll"),
      CODE.indexOf("useEffect", CODE.indexOf("const handleScroll")),
    );
    expect(handler).toContain("if (selfScroll.current) selfScroll.current = false;");
    expect(handler).toContain("setRestingOnAlignment(false)");
    // The clear belongs to the reader branch only.
    const readerBranch = handler.slice(handler.indexOf("else {"));
    expect(readerBranch).toContain("setRestingOnAlignment(false)");
    expect(readerBranch).toContain("readerScrolled.current = true");
  });

  test("it is a sibling of the scroller, or it scrolls away with the content", () => {
    const scroller = CODE.indexOf("ref={scrollRef}");
    const cover = CODE.indexOf('data-testid="progression-straddle-cover"');
    expect(cover).toBeGreaterThan(CODE.indexOf("</table>"));
    expect(cover).toBeGreaterThan(scroller);
  });

  test("every inert overlay on this table is one of the four we can name", () => {
    // The file-wide count #7246 kept, extended by this fix's cover and turned
    // into an enumeration so the next one has to say what it is rather than
    // bump a number. Four overlays: the bleed cover (#7246), the right-hand
    // cue and the left-hand cue (#7192), and this straddle cover (#7268).
    expect(CODE.match(/pointer-events-none absolute/g)).toHaveLength(4);
    for (const testid of [
      "progression-sticky-bleed-cover",
      "progression-scroll-affordance",
      "progression-scroll-affordance-left",
      "progression-straddle-cover",
    ]) {
      expect(blockFor(testid)).toContain("pointer-events-none absolute");
    }
  });
});
