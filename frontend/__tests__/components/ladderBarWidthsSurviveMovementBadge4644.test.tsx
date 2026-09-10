/**
 * #4644 — a ladder's bar length stops encoding its percentage when the row
 * carries a movement badge.
 *
 * Photographed on production at 390px, Discover card "Netflix App Downloads in
 * September", 2026-09-09 21:36 PT:
 *
 *     Above 52  ▼3.5   ██████████░░░░░░░░░   92%
 *     Above 58         ████████████████████   88%   ← longest bar
 *     Above 67  ▲48.0  ████████░░░░░░░░░░░░   94%   ← shortest bar
 *
 * The two longest bars belonged to the two SMALLEST numbers. The bar fill is
 * `probability * 100` and was always right; what differed was the TRACK it was
 * a percentage OF. The row is `label · [badge] · track(flex-1) · percent`, the
 * badge is `shrink-0` and was rendered only on rungs that moved, so a moving
 * rung's track lost the badge's width AND its flex gap. 94% of a short track
 * draws shorter than 88% of a long one.
 *
 * This is #1574 acceptance (c) — one track width per ladder, so equal
 * percentages draw equal bars — arriving one column right of the label track
 * whose comment in the component already blocks the first door.
 *
 * jsdom is not in this suite (testEnvironment: node), so no test here can
 * measure a rendered pixel. These assert the STRUCTURE that makes the widths
 * equal: every row of a ladder with a mover spends the same width on its
 * non-track columns, which is the only thing the flex track's length depends
 * on. Each one reds if the reservation is removed.
 */
import { renderToStaticMarkup } from "react-dom/server";
import QuantityGroup, { type QuantityRung } from "@/components/QuantityGroup";

/** The card in the photograph, in its served order (`sort={false}` there too). */
const netflixLadder: QuantityRung[] = [
  { key: "a", label: "Above 52", probability: 0.92, value: 52, movement: -0.035 },
  { key: "b", label: "Above 58", probability: 0.88, value: 58 },
  { key: "c", label: "Above 67", probability: 0.94, value: 67, movement: 0.48 },
];

/** Every reserved movement slot's declared width, in row order. */
function slotWidths(html: string): string[] {
  return [...html.matchAll(/width:\s*(calc\([^)]*\))/g)].map((m) => m[1]);
}

/** Every bar fill's declared width, in row order. */
function barWidths(html: string): number[] {
  return [...html.matchAll(/width:\s*(\d+)%/g)].map((m) => Number(m[1]));
}

describe("#4644 the track is the same length on every row", () => {
  test("the production ladder reserves the badge slot on all three rungs", () => {
    const html = renderToStaticMarkup(
      <QuantityGroup bare compact wideLabels sort={false} maxRungs={3} rungs={netflixLadder} />,
    );

    // Two rungs moved; three rungs get a slot. Before the fix this was 2.
    const widths = slotWidths(html);
    expect(widths.length).toBe(3);
    expect(new Set(widths).size).toBe(1);

    // The badges themselves are unchanged — the un-moved rung stays unmarked.
    expect(html.match(/▲/g)?.length).toBe(1);
    expect(html.match(/▼/g)?.length).toBe(1);

    // And the bars still say what the numbers say.
    expect(barWidths(html)).toEqual([92, 88, 94]);
  });

  test("two rungs at the SAME percentage draw the same bar whether or not they moved", () => {
    // The property #1574 acceptance (c) states, pointed at this door. Equal
    // fills were never the failure; equal tracks were.
    const html = renderToStaticMarkup(
      <QuantityGroup
        sort={false}
        rungs={[
          { key: "moved", label: "Above 58", probability: 0.88, value: 58, movement: 0.48 },
          { key: "still", label: "Above 61", probability: 0.88, value: 61 },
        ]}
      />,
    );

    const widths = slotWidths(html);
    expect(widths.length).toBe(2);
    expect(widths[0]).toBe(widths[1]);
    expect(barWidths(html)).toEqual([88, 88]);
  });

  test("the reserved slot on an un-moved rung is empty and out of the a11y tree", () => {
    const html = renderToStaticMarkup(
      <QuantityGroup
        sort={false}
        rungs={[
          { key: "moved", label: "Above 58", probability: 0.88, value: 58, movement: 0.48 },
          { key: "still", label: "Above 61", probability: 0.5, value: 61 },
        ]}
      />,
    );

    // A placeholder that a screen reader announces would be a worse bug than
    // the one being fixed: it is width, not content.
    expect(html).toContain('aria-hidden="true"');
    // Exactly one of the two slots is hidden — the mover's badge is still read.
    expect(html.match(/aria-hidden="true"/g)?.length).toBe(1);
    expect(html).toContain('aria-label="up 48.0 points"');
  });

  test("the slot is sized from the longest badge THIS ladder prints", () => {
    // "▲48.0" is 5 characters; "▲0.5" is 4. A ladder is measured on its own ink,
    // the same rule the label track uses, so a one-mover ladder does not pay for
    // a badge width no rung of it will ever print.
    const wide = renderToStaticMarkup(
      <QuantityGroup
        sort={false}
        rungs={[
          { key: "a", label: "Above 52", probability: 0.92, value: 52, movement: 0.48 },
          { key: "b", label: "Above 58", probability: 0.88, value: 58 },
        ]}
      />,
    );
    const narrow = renderToStaticMarkup(
      <QuantityGroup
        sort={false}
        rungs={[
          { key: "a", label: "Above 52", probability: 0.92, value: 52, movement: 0.005 },
          { key: "b", label: "Above 58", probability: 0.88, value: 58 },
        ]}
      />,
    );
    expect(slotWidths(wide)[0]).toBe("calc(5ch + 0.5rem)");
    expect(slotWidths(narrow)[0]).toBe("calc(4ch + 0.5rem)");
  });
});

describe("#4644 controls — what must NOT have moved", () => {
  test("a ladder where nothing moved reserves nothing at all", () => {
    // The conservatism this file already practises: a ladder that was right
    // renders exactly what it rendered, so no bar on the site shortens by a
    // pixel for a badge that will never appear.
    const html = renderToStaticMarkup(
      <QuantityGroup
        rungs={[
          { key: "a", label: "≥ 60", probability: 0.98, value: 60 },
          { key: "b", label: "≥ 95", probability: 0.22, value: 95 },
        ]}
      />,
    );
    expect(slotWidths(html)).toEqual([]);
    expect(html).toContain("w-11");
    expect(html).not.toContain("▲");
  });

  test("UX-P275 survives: a sub-rounding drift is still not a badge, and not a slot", () => {
    const html = renderToStaticMarkup(
      <QuantityGroup
        rungs={[
          { key: "a", label: "≥ 60", probability: 0.98, value: 60, movement: 0.00003 },
          { key: "b", label: "≥ 95", probability: 0.22, value: 95, movement: -0.00002 },
        ]}
      />,
    );
    expect(html).not.toContain("▲");
    expect(html).not.toContain("▼");
    // …and because no rung PRINTS a move, the ladder is the untouched one above.
    expect(slotWidths(html)).toEqual([]);
  });

  test("the #4404 label track is still one width per ladder", () => {
    // The neighbouring invariant, restated from this file's side: a mover must
    // not disturb the label column either.
    const html = renderToStaticMarkup(
      <QuantityGroup
        rungs={[
          { key: "a", label: "≥ 0.5 goals", probability: 0.9, value: 0.5, movement: 0.48 },
          { key: "b", label: "≥ 1.5 goals", probability: 0.7, value: 1.5 },
        ]}
      />,
    );
    const labelWidths = [...html.matchAll(/width:\s*(clamp\([^)]*\)[^;"]*)/g)].map((m) => m[1]);
    expect(labelWidths.length).toBe(2);
    expect(new Set(labelWidths).size).toBe(1);
  });
});
