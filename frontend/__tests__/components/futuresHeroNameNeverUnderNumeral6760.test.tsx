/**
 * #6760 — the futures hero's 64px numeral stops being drawn on top of the outcome name.
 *
 * ═══ WHAT A READER SAW ═══
 *
 * `https://bainluck.com/futures/61246736` at 390px, 2026-09-17, a tennis match in play:
 *
 *     Sao Pa100%pen: Suzan Lamens vs Solana Sierra Set 1 Winner
 *
 * The number and the name occupied the same pixels and neither could be read. Measured on
 * production by `tools/futures-hero-overlap-6760.mjs` before the fix — 5 of 6 ambient heroes
 * sampled, 5,075px² of rect intersection on the filed specimen, and Chromium's own hit test
 * answering "name" at 16 of 24 points sampled inside the numeral's own box.
 *
 * ═══ THE MECHANISM, WHICH IS WHAT THIS FILE GUARDS ═══
 *
 * The ambient rendering put the numeral and a right-anchored column holding the movement pill
 * AND the outcome name into one 96px box as two independently `position:absolute` children,
 * neither width-constrained. A name long enough to wrap took the full width of the box and ran
 * straight under the numeral. Nothing about it was arithmetic-dependent — it is a property of
 * the shape, not of a particular width.
 *
 * Population, and its limits stated rather than rounded off: of 25,002 open futures markets with
 * a priced leading outcome, 246 carry a leading outcome name over 45 characters and 132 over 55.
 * Both numbers are counted on the MAX-PROBABILITY outcome, which is not exactly what
 * `pickHeroOutcome` returns, and the ambient rendering additionally needs >=3 history points —
 * so neither is a clean bound on how many pages render this today, and neither is quoted as one.
 * What was measured directly: of six production pages probed, the five whose name was 58+
 * characters all wrapped to two lines and all overlapped; the one 13-character name did not. The
 * sample does not bracket the threshold between 13 and 58 and no threshold is claimed.
 *
 * So the assertion is STRUCTURAL, not a width calculation: the outcome name must not live
 * inside the absolutely positioned layer at all. jsdom has no layout — `getBoundingClientRect`
 * returns zeros — so a test in this file could never measure the overlap it is named after, and
 * one that tried would pass on a component that still collided. The geometry is measured by the
 * probe against a real browser; what belongs here is the shape that makes the geometry
 * impossible.
 *
 * ═══ BOTH RENDERINGS ═══
 *
 * `FuturesHero` paints an AMBIENT variant (>=3 sparkline points) and a PLAIN variant, each with
 * its own markup. UX-P233 found a mutation battery renaming the ambient variant's hook survived
 * every assertion in `futuresBaselineRender.test.tsx` because the harness only ever fed it empty
 * history. Every test here runs both.
 */
import { renderToStaticMarkup } from "react-dom/server";
import React from "react";
import { FuturesHero } from "../../components/FuturesHero";

const UP_CURVE = [0.4, 0.45, 0.5, 0.58, 0.62, 0.68];

/** The filed specimen's own outcome name — the whole question, repeated. */
const LONG_NAME = "Sao Paulo Open: Suzan Lamens vs Solana Sierra Set 1 Winner";

/** Both renderings of the same props: [label, sparklinePoints]. */
const RENDERINGS: [string, number[] | undefined][] = [
  ["ambient", UP_CURVE],
  ["plain", undefined],
];

/**
 * 🪤 `outcomeName` takes NO default. A default parameter fires on an explicitly passed
 * `undefined`, so `hero(points, undefined)` — the whole point of the no-name test — would have
 * rendered the long name and the assertion would have failed on a correct component. Callers
 * that want the name pass `LONG_NAME`.
 */
function hero(points: number[] | undefined, outcomeName: string | undefined) {
  return renderToStaticMarkup(
    <FuturesHero
      name="Sao Paulo Open: Suzan Lamens vs Solana Sierra"
      probability={1.0}
      outcomeName={outcomeName}
      movement={-71.5}
      movementLabel="last move · Sep 17"
      sparklinePoints={points}
    />,
  );
}

/**
 * The markup of the one absolutely positioned strip inside the ambient box, from the opening
 * `<div class="absolute` to the close of the box. Used to ask what the absolute layer contains.
 *
 * Deliberately a slice of the real render rather than a parsed tree: the claim is "the name is
 * not in the absolute layer", and the absolute layer is identified the same way a reader of the
 * component would identify it — by the `absolute` class on it.
 */
function absoluteLayer(html: string): string {
  const start = html.indexOf('<div class="absolute inset-x-0');
  if (start === -1) return "";
  // The strip is the last thing in the 96px box, so everything from it to the end of that box.
  return html.slice(start, html.indexOf("</div></div>", start) + "</div></div>".length);
}

describe("#6760 — the outcome name is never inside the hero's absolute layer", () => {
  test.each(RENDERINGS)("%s: the name renders, and is addressable", (_label, points) => {
    const html = hero(points, LONG_NAME);
    expect(html).toContain(LONG_NAME);
    expect(html).toContain('data-testid="hero-outcome-name"');
  });

  test("AMBIENT: the absolute strip holds the numeral and the pill, and NOT the name", () => {
    const html = hero(UP_CURVE, LONG_NAME);
    const strip = absoluteLayer(html);
    // The strip was found at all — otherwise the two assertions below are vacuous.
    expect(strip).not.toBe("");
    expect(strip).toContain("text-[64px]");
    expect(strip).toContain('data-testid="hero-movement"');
    // 🔴 THE DEFECT: before #6760 the name lived here, under the numeral.
    expect(strip).not.toContain(LONG_NAME);
    expect(strip).not.toContain('data-testid="hero-outcome-name"');
  });

  test("AMBIENT: the name is emitted AFTER the box closes, in normal flow", () => {
    const html = hero(UP_CURVE, LONG_NAME);
    const boxStart = html.indexOf('class="relative h-[96px]');
    const nameAt = html.indexOf('data-testid="hero-outcome-name"');
    const stripAt = html.indexOf('<div class="absolute inset-x-0');
    expect(boxStart).toBeGreaterThan(-1);
    expect(nameAt).toBeGreaterThan(stripAt);
    // Normal flow means no ancestor between the name and the hero root is absolute. The name's
    // own tag carries no positioning class, and the box it would have been inside has closed.
    const afterBox = html.slice(html.indexOf("</svg>"));
    expect(afterBox.slice(afterBox.indexOf('data-testid="hero-outcome-name"'))).not.toContain(
      "absolute",
    );
  });

  test.each(RENDERINGS)(
    "%s: the numeral cannot be squeezed by a long name — it is shrink-proof or unshared",
    (label, points) => {
      const html = hero(points, LONG_NAME);
      if (label === "ambient") {
        // In a flex row a long sibling shrinks whatever will shrink. The numeral must not.
        expect(html).toContain("shrink-0 flex items-baseline");
      }
      expect(html).toContain("text-[64px]");
      expect(html).toContain(">1<".replace("1", "100"));
    },
  );

  test.each(RENDERINGS)("%s: no name, no empty name element", (_label, points) => {
    const html = hero(points, undefined);
    expect(html).not.toContain('data-testid="hero-outcome-name"');
    // The numeral still renders — withholding the name must not withhold the number.
    expect(html).toContain("text-[64px]");
  });

  test("AMBIENT: the movement column can shrink so it can never push past the numeral", () => {
    // `min-w-0` is what lets the flex row resolve a long label by shrinking the column instead
    // of overflowing it. Without it a flex item's automatic minimum size is its content, and
    // the row grows past the box rather than fitting inside it.
    const strip = absoluteLayer(hero(UP_CURVE, LONG_NAME));
    expect(strip).toContain("min-w-0");
  });
});
