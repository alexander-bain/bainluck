// #7748 GUARD — an SVG annotation label must never be placed where the canvas cuts
// its first glyphs off. On production, /about's Alcaraz chart anchored
// "Adductor injury — 14%, the brink" `end` at x=163.5 in a 320-unit viewBox, so the
// label's box started at x=-16.7 and the App Store reviewer's About screen (that page
// IS the app's About screen, #5914) read "ductor injury" — a crop that reads as a typo.
//
// THE CONTROL IS MEASURED, NOT ESTIMATED. `estimateSvgTextWidth` guesses a width from a
// character table; a test that checked it against its own table would prove nothing. So
// the widths below were measured with Chrome's `getBBox()` on the live page, in the
// shipped font stack (Inter 600) at the size the charts use, and they are what the
// estimator is graded against. Recipe, if they ever need re-taking:
//
//   probe = document.createElementNS(SVG_NS, "text")     // appended to the /about chart
//   probe.setAttribute("font-size", "11")
//   probe.setAttribute("font-weight", "600")
//   probe.textContent = s; probe.getBBox().width / 11    // -> em units
//
// Taken 2026-09-21 at 390px viewport against https://www.bainluck.com/about?embed=1.

import { estimateSvgTextWidth, placeLabel } from "@/lib/svgLabelFit";

/** Chrome-measured widths, in em (multiply by font size for user units). */
const MEASURED_EM: Record<string, number> = {
  "Adductor injury — 14%, the brink": 16.3855,
  "Tied on the board — nearly 3× apart in the market": 24.5909,
  "The dip": 3.7145,
};

describe("estimateSvgTextWidth — graded against Chrome, not against itself", () => {
  test.each(Object.entries(MEASURED_EM))(
    "never under-estimates %p, and stays within 25%% of the measured width",
    (label, measuredEm) => {
      const fontSize = 11;
      const measured = measuredEm * fontSize;
      const estimate = estimateSvgTextWidth(label, fontSize);
      // Under-estimating is the failure that ships a clipped label; over-estimating only
      // nudges a label inward. So the floor is hard and the ceiling is loose.
      expect(estimate).toBeGreaterThanOrEqual(measured);
      expect(estimate).toBeLessThanOrEqual(measured * 1.25);
    },
  );

  test("scales linearly with font size", () => {
    const a = estimateSvgTextWidth("Adductor injury", 11);
    const b = estimateSvgTextWidth("Adductor injury", 22);
    expect(b).toBeCloseTo(a * 2, 6);
  });

  test("distinguishes wide from narrow glyphs", () => {
    expect(estimateSvgTextWidth("mmmm", 11)).toBeGreaterThan(
      estimateSvgTextWidth("iiii", 11),
    );
  });

  test("an empty label has no width", () => {
    expect(estimateSvgTextWidth("", 11)).toBe(0);
  });
});

describe("placeLabel — the whole box stays inside the plot", () => {
  const fontSize = 11;
  const gap = 8;
  const left = 10;
  const right = 310;

  /** The rendered box of a placement, using the MEASURED width where we have one. */
  function box(
    placement: { x: number; anchor: "start" | "middle" | "end" },
    label: string,
  ) {
    const w = (MEASURED_EM[label] ?? estimateSvgTextWidth(label, fontSize) / fontSize) * fontSize;
    const x0 =
      placement.anchor === "end"
        ? placement.x - w
        : placement.anchor === "middle"
          ? placement.x - w / 2
          : placement.x;
    return { x0, x1: x0 + w };
  }

  test("the production specimen is no longer clipped", () => {
    // The real /about geometry: width 320, padX 10, 14 points, annotation on index 7.
    const label = "Adductor injury — 14%, the brink";
    const anchorX = 10 + (300 * 7) / 13; // 171.54 — just past the midpoint, which is why
    //                                      the old "right half ⇒ anchor end" rule fired.
    const placement = placeLabel({ anchorX, label, fontSize, gap, left, right });
    const { x0, x1 } = box(placement, label);
    expect(x0).toBeGreaterThanOrEqual(left);
    expect(x1).toBeLessThanOrEqual(right);
    // And the old placement is what this rules out: anchored `end` at anchorX - gap.
    expect(box({ x: anchorX - gap, anchor: "end" }, label).x0).toBeLessThan(0);
  });

  test("a label that fits on the preferred side keeps the original placement", () => {
    // Both directions (gotcha #43): the fix must not move labels that were already fine.
    const short = placeLabel({ anchorX: 250, label: "The dip", fontSize, gap, left, right });
    expect(short).toEqual({ x: 242, anchor: "end" });

    const early = placeLabel({ anchorX: 40, label: "The dip", fontSize, gap, left, right });
    expect(early).toEqual({ x: 48, anchor: "start" });
  });

  test("a label that fits on only one side flips to that side", () => {
    // Right half, so leftward is preferred — but there is no room leftward and plenty right.
    const label = "a long enough annotation label";
    const w = estimateSvgTextWidth(label, fontSize);
    const anchorX = left + 4; // hard against the left edge
    const placement = placeLabel({ anchorX, label, fontSize, gap, left, right, preferLeft: true });
    expect(placement.anchor).toBe("start");
    expect(placement.x).toBe(anchorX + gap);
    expect(anchorX + gap + w).toBeLessThanOrEqual(right);
  });

  test("a label wider than the plot is centred rather than losing one end", () => {
    const label = "an annotation label far wider than the plot area it has to live inside";
    const placement = placeLabel({ anchorX: 40, label, fontSize, gap, left, right });
    expect(placement.anchor).toBe("middle");
    expect(placement.x).toBe((left + right) / 2);
  });
});
