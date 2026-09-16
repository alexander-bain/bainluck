/**
 * #6548 — a settled board's chart hid the race on a phone.
 *
 * ═══ WHAT A READER SAW ═══
 *
 * `/futures/110141` ("South Dakota Republican Governor nominee?", resolved
 * 7/28/2026), production, **390px**, 2026-09-16 12:4xZ
 * (`artifacts/ux-1296/6548-BEFORE-390.png`):
 *
 *   - one blue line, entering at 50% and flat at 100% from early August
 *   - x-axis Jun 18 · Aug 2 · Sep 16
 *   - a legend with a RED key for "Dusty Johnson" and no red line anywhere
 *
 * The same URL at **1280px** (`6548-BEFORE-1280.png`) is a different story
 * entirely: Dusty Johnson leads at ~50-70% from Mar 20, Larry Rhoden sits near
 * 0%, and in early June they cross — red collapses, blue climbs to 100%. That
 * crossover IS the race. On a phone it was behind the left edge.
 *
 * ═══ MECHANISM ═══
 *
 * #3035 made the plot rest on its RIGHT edge, and was right to: on a LIVE race
 * the news is the newest point, and a reader opening the US Open title race was
 * landing on January. A decided question inverts that premise — the right edge
 * is a flat run to the resolution and the contest is behind the left edge. So
 * #3035's own harm came back at the opposite end of the same scroller.
 *
 * ═══ THE COUPLING THIS HAD TO BREAK FIRST ═══
 *
 * `edgeOverflowFor` computed its maximum scroll by calling `anchorScrollLeft`.
 * The two were one function only because the anchor HAPPENED to be the maximum
 * offset. Making the anchor conditional without splitting them would have made
 * every settled chart compute its fades against 0 and report no right-hand
 * overflow while holding a screen and a half of hidden plot — a second defect
 * wearing the first one's fix. `maxScrollLeft` is now the geometry and
 * `anchorScrollLeft` is the editorial; the tests below pin both.
 *
 * Reported by authority/381, who measured the reveal as continuous in viewport
 * width (390→529 red px, 600→1,654, 768→2,587, 900→3,518, 1280→3,519,
 * byte-identical across repeats) — a viewport clip, not a breakpoint and not a
 * load race. Reproduced here at 390 and 1280 before building.
 */

import {
  anchorScrollLeft,
  edgeOverflowFor,
  maxScrollLeft,
  EDGE_TOLERANCE_PX,
} from "@/lib/chartScroll";

/** A 390px phone against the plot's `min-w-[600px]`, as #3035's own fixture had it. */
const PHONE = { scrollWidth: 600, clientWidth: 390 };
/** A desktop wide enough that nothing overflows. */
const DESKTOP = { scrollWidth: 600, clientWidth: 1280 };

describe("#6548 — a decided question rests on its race, not on its dead end", () => {
  test("settled rests at the LEFT edge, where the contest is", () => {
    expect(anchorScrollLeft(PHONE, { settled: true })).toBe(0);
  });

  test("CONTROL: live still rests at the RIGHT edge — #3035 is not undone", () => {
    expect(anchorScrollLeft(PHONE)).toBe(210);
    expect(anchorScrollLeft(PHONE, { settled: false })).toBe(210);
    // An absent options object must behave exactly like the old one-arg call.
    expect(anchorScrollLeft(PHONE, {})).toBe(anchorScrollLeft(PHONE));
  });

  test("a plot that does not overflow rests at 0 either way", () => {
    expect(anchorScrollLeft(DESKTOP)).toBe(0);
    expect(anchorScrollLeft(DESKTOP, { settled: true })).toBe(0);
  });

  // ─── The coupling. These are the assertions that would have caught the
  // second defect if the split had been skipped.
  test("maxScrollLeft is geometry only — settledness cannot reach it", () => {
    expect(maxScrollLeft(PHONE)).toBe(210);
    expect(maxScrollLeft(DESKTOP)).toBe(0);
  });

  test("a settled phone chart resting at 0 still reports plot hidden to the RIGHT", () => {
    const atRest = { ...PHONE, scrollLeft: anchorScrollLeft(PHONE, { settled: true }) };
    expect(atRest.scrollLeft).toBe(0);
    const edges = edgeOverflowFor(atRest);
    expect(edges.right).toBe(true);
    expect(edges.left).toBe(false);
  });

  test("a live phone chart at its own anchor reports plot hidden to the LEFT", () => {
    const atRest = { ...PHONE, scrollLeft: anchorScrollLeft(PHONE) };
    const edges = edgeOverflowFor(atRest);
    expect(edges.left).toBe(true);
    expect(edges.right).toBe(false);
  });

  // The split is the ship's second half, and it is NOT behavioural today:
  // `edgeOverflowFor` passes only `metrics`, so `anchorScrollLeft(metrics)`
  // falls through to `maxScrollLeft` and re-coupling the two is an EQUIVALENT
  // mutant — measured, by re-coupling them and watching all 24 tests stay green.
  // The hazard is latent rather than absent: the day any caller hands the
  // anchor an `opts`, a re-coupled `edgeOverflowFor` computes a settled chart's
  // maximum scroll as 0 and withdraws the right-hand fade from 210px of hidden
  // race. A behavioural test cannot reach that, so the structure is pinned
  // directly — the same source-scan idiom this file already uses on the
  // component, and the only assertion here that fails on the re-coupled tree.
  test("the fades read GEOMETRY, not the editorial anchor", () => {
    const LIB = require("fs")
      .readFileSync(
        require("path").join(__dirname, "../../lib/chartScroll.ts"),
        "utf8",
      )
      .replace(/\/\*[\s\S]*?\*\//g, "")
      .replace(/^\s*\/\/.*$/gm, "");
    // Sliced declaration-to-next-export rather than matched to the first
    // `\n}`: this function's RETURN TYPE is an inline object literal, so a
    // lazy brace match stops at the end of the signature and captures a body
    // that contains neither call. That near-miss passed a bare truthiness
    // check, so the non-vacuity assertion below is on `return {` — the one
    // token that proves the body itself was captured.
    const start = LIB.indexOf("export function edgeOverflowFor");
    expect(start).toBeGreaterThanOrEqual(0);
    const after = LIB.slice(start + 1);
    const nextExport = after.indexOf("\nexport ");
    const body = nextExport === -1 ? after : after.slice(0, nextExport);
    expect(body).toContain("return {");
    expect(body).toContain("maxScrollLeft(metrics)");
    expect(body).not.toContain("anchorScrollLeft");
  });

  test("CONTROL: the edge tolerance is untouched by this ship", () => {
    expect(EDGE_TOLERANCE_PX).toBe(1);
    const justOff = { ...PHONE, scrollLeft: EDGE_TOLERANCE_PX };
    expect(edgeOverflowFor(justOff).left).toBe(false);
  });
});

describe("#6548 — FuturesChart passes its settledness to the anchor", () => {
  // Comments stripped, like #3035 arm B: otherwise this file's own prose about
  // `settled` would satisfy the scan.
  const CODE = require("fs")
    .readFileSync(
      require("path").join(__dirname, "../../components/FuturesChart.tsx"),
      "utf8",
    )
    .replace(/\/\*[\s\S]*?\*\//g, "")
    .replace(/^\s*\/\/.*$/gm, "");

  test("the anchor call is handed `settled`, not just the element", () => {
    expect(CODE).toMatch(
      /el\.scrollLeft\s*=\s*anchorScrollLeft\(\s*el\s*,\s*\{\s*settled\s*\}\s*\)/,
    );
  });

  test("`settled` is in the effect's deps, so a late resolution re-anchors", () => {
    // The page can hydrate before it knows the question is decided. An anchor
    // computed while it still believed itself live must not be the final word.
    expect(CODE).toMatch(/\[\s*mini\s*,\s*displayedOutcomes\s*,\s*settled\s*,/);
  });
});
