/**
 * #7427 — a wide ladder label loses its TAIL, and the tail is the load-bearing token.
 *
 * Measured in the DOM on production `2629172a` at 390px (`tools/ladder-rung-clip-7427.mjs`,
 * `scrollWidth` vs `clientWidth` on the real element — the clip is 16–33px, small enough that
 * a downscaled whole-page PNG fabricates the answer either way):
 *
 *     rungs=91  clipped=8   slot: 128–135px of a 300px row, font 12px/600
 *
 *     Before 2027            4%          ← fits
 *     Before January 20, …  11%          ← "2029" clipped; 146px of text in a 128px slot
 *
 *     Above 20 million short t…  87%     ← and all five siblings, 161–162px in 135px
 *
 * Two distinct losses, one mechanism. On the date ladder the clipped token is the YEAR, and
 * it is the only thing separating two rungs four years apart — so the 4% → 11% step stops
 * making sense. On the coal ladder EVERY rung loses the same tail, so the ladder stops naming
 * the unit it measures at all. The second is the worse defect and this issue was filed
 * without it; it is here because the population was measured rather than assumed.
 *
 * (#8562: the 45% below is now the CAP of a width sized from the ladder's longest label — a short
 * stock ladder no longer reserves 114px for "$730". Every label this file is about hits the cap.)
 *
 * WHAT DOES NOT CHANGE, AND WHY THAT IS THE POINT. The slot is a fixed `w-[45%]`, and it stays
 * fixed. #1574 acceptance (c) — one track width per ladder, so equal percentages draw equal
 * bars — is the invariant that fixed width buys, and #4404 and #4644 are both previous repairs
 * of the same invariant one column further right. A fix that widened the slot would shorten
 * every bar on every ladder on the site to rescue eight rows, and the widest label measured is
 * 54% of the row, so widening could not fully work even at that price.
 *
 * What goes is the ELLIPSIS, not the width. The removed comment in the component claimed
 * "Truncate rather than wrap so the track always starts at the same x"; the width is fixed
 * either way, so wrapping moves that x by zero. `truncate` was buying nothing and costing the
 * tail. `line-clamp-2` over `truncate` is already the house idiom for exactly this (#4342,
 * `GamePlayCard`, `UpcomingTournaments`) — the two cannot be combined.
 *
 * jsdom is not in this suite (`testEnvironment: node`), so nothing here measures a rendered
 * pixel; these assert the structure the pixels follow from. The pixel proof is the probe
 * above, re-run against the built page — 8 clipped → 0 — and it is the instrument that can
 * actually fail if this reasoning is wrong.
 */
import { renderToStaticMarkup } from "react-dom/server";
import QuantityGroup, { type QuantityRung } from "@/components/QuantityGroup";

/** The Greenland card in the photograph, in its served (chronological) order. */
const greenland: QuantityRung[] = [
  { key: "a", label: "Before 2027", probability: 0.0405, value: 20270100 },
  { key: "b", label: "Before January 20, 2029", probability: 0.1055, value: 20290120 },
];

/** The coal ladder — every rung over the slot, all losing the same unit. */
const coal: QuantityRung[] = [20, 22, 24, 26, 28, 30].map((n, i) => ({
  key: `c${n}`,
  label: `Above ${n} million short tons`,
  probability: 0.87 - i * 0.16,
  value: n,
}));

/**
 * The class attribute of every rung's LABEL span, in row order.
 *
 * Scoped to the label rather than asserted over the whole document on purpose: a row has four
 * other spans, and a document-wide `toContain("truncate")` would pass on any one of them and
 * read as a statement about the label. The label is the span carrying the wide-label type.
 */
function labelClasses(html: string): string[] {
  return [...html.matchAll(/class="([^"]*text-\[12px\] font-semibold[^"]*)"/g)].map((m) => m[1]);
}

describe("#7427 the wide label keeps its tail", () => {
  test("a clipped date rung wraps instead of ellipsising", () => {
    const classes = labelClasses(renderToStaticMarkup(<QuantityGroup wideLabels sort={false} rungs={greenland} />));
    expect(classes).toHaveLength(2);
    for (const c of classes) {
      expect(c).toContain("line-clamp-2");
      // `truncate` is `overflow-hidden text-ellipsis whitespace-nowrap`, and the third of
      // those is what ate the year. Asserting the absence of the utility is the assertion
      // that the row can use its second line.
      expect(c).not.toContain("truncate");
    }
  });

  test("the full label is in the markup and in the accessible name", () => {
    // Nothing truncates in JS — the loss was purely CSS — and this pins that it stays that
    // way, so a later "fix" that slices the string to fit cannot pass this file.
    const html = renderToStaticMarkup(<QuantityGroup wideLabels sort={false} rungs={greenland} />);
    expect(html).toContain("Before January 20, 2029");
    expect(html).toContain('aria-label="Before January 20, 2029: 11%"');
    expect(html).not.toContain("…");
  });

  test("an unbreakable token cannot spill out of the slot", () => {
    // Wrapping alone breaks at spaces only. A single long token (a venue writes them) would
    // overflow the fixed slot horizontally and be clipped by the clamp's overflow-hidden,
    // which is the defect again in a rarer costume.
    const classes = labelClasses(
      renderToStaticMarkup(
        <QuantityGroup wideLabels rungs={[{ key: "a", label: "Beforeahighlyunlikelydate", probability: 0.1, value: 1 }]} />,
      ),
    );
    expect(classes[0]).toContain("break-words");
  });

  test("the clamp is bounded — a pathological label cannot grow the row without limit", () => {
    // Two lines hold roughly 44 characters at this width against the 27 the widest measured
    // label needs, so the bound is headroom, not a second clip. It is asserted as a BOUND so
    // that removing it (`line-clamp-none`, or no clamp at all) reds this file.
    const classes = labelClasses(
      renderToStaticMarkup(<QuantityGroup wideLabels rungs={coal} />),
    );
    expect(classes).toHaveLength(6);
    for (const c of classes) expect(c).toMatch(/\bline-clamp-2\b/);
  });
});

describe("#7427 CONTROLS — the track invariant and the two other arms are untouched", () => {
  test("the wide slot is still a fixed 45%, so every bar is what it was", () => {
    // The whole repair is that the WIDTH does not move. If this reds, the fix has started
    // paying for the tail out of the bar, which is the thing #1574(c) forbids.
    const classes = labelClasses(renderToStaticMarkup(<QuantityGroup wideLabels sort={false} rungs={greenland} />));
    for (const c of classes) {
      expect(c).toContain("shrink-0");
    }
    const html = renderToStaticMarkup(<QuantityGroup wideLabels sort={false} rungs={greenland} />);
    // #8562 — the slot is sized from the longest label (23 chars here), CAPPED at the 45% it
    // always was. A label this long hits the cap, so this ladder's bars are what they were;
    // the cap is the part that must never move (a wider slot would pay for the tail out of
    // the bar). Every rung carries the SAME width, so #1574(c) still holds.
    const widths = [...html.matchAll(/style="width:(clamp[^"]*)"/g)].map((m) => m[1]);
    expect(widths).toEqual([
      "clamp(2.75rem, calc(23ch + 0.75rem), 45%)",
      "clamp(2.75rem, calc(23ch + 0.75rem), 45%)",
    ]);
  });

  test("a wide ladder whose labels already fit renders exactly as its clipped sibling does", () => {
    // Nothing about the fix is conditional on the label being long, so the short-label
    // ladders that were already correct are provably not a second population.
    const short = labelClasses(
      renderToStaticMarkup(
        <QuantityGroup
          wideLabels
          rungs={[
            { key: "a", label: "2027", probability: 0.4, value: 2027 },
            { key: "b", label: "2028", probability: 0.2, value: 2028 },
          ]}
        />,
      ),
    );
    const long = labelClasses(renderToStaticMarkup(<QuantityGroup wideLabels sort={false} rungs={greenland} />));
    expect(new Set([...short, ...long]).size).toBe(1);
  });

  test("CONTROL: #4404's numeric track still ELLIPSISES — that ruling is not reopened", () => {
    // There the label is mono and numeric and wrapping orphaned an operator above the number
    // it qualified, so widening was right and wrapping was wrong. This fix must not leak into
    // it. A mutation that swaps `truncate` for the clamp globally reds here.
    const html = renderToStaticMarkup(
      <QuantityGroup
        rungs={[
          { key: "a", label: "≥ 0.5 goals", probability: 0.9, value: 0.5 },
          { key: "b", label: "≥ 1.5 goals", probability: 0.7, value: 1.5 },
        ]}
      />,
    );
    expect(html).toContain("clamp(2.75rem, calc(11ch + 0.5rem), 45%)");
    expect(html).toContain("truncate");
    expect(html).not.toContain("line-clamp-2");
  });

  test("CONTROL: the plain numeric ladder keeps its w-11 column byte-for-byte", () => {
    const html = renderToStaticMarkup(
      <QuantityGroup
        rungs={[
          { key: "a", label: "≥ 60", probability: 0.98, value: 60 },
          { key: "b", label: "≥ 95", probability: 0.22, value: 95 },
        ]}
      />,
    );
    expect(html).toContain("w-11");
    expect(html).not.toContain("line-clamp-2");
    expect(html).not.toContain("break-words");
  });
});
