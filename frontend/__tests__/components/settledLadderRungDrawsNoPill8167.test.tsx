// #8167, second half — A `0%` RUNG STILL DREW A SOLID RED PILL.
//
// On the settled board `/futures/59319183` every leg prices at exactly `0`, and
// each row painted a short solid red bar at the left of its track beside its own
// `0%` numeral. At a glance that reads as a small non-zero value.
//
// This is #4660 with a different input. That fix removed the 2% floor for a rung
// with NO price, because the floor turned an absent number into a visible red
// claim of near-impossibility; `probabilityHeat(0)` returns `known: true`, so an
// exact zero walked straight past it and kept the floor.
//
// Both directions (gotcha #43): the floor is load-bearing for a genuine long
// shot (#1574) and must survive here, including the long shot that ROUNDS to
// zero — which is why the gate is on the probability and not on the percent.

import { renderToStaticMarkup } from "react-dom/server";
import QuantityGroup from "@/components/QuantityGroup";

/** The fill widths, in DOM order, as the browser would paint them. */
const fills = (html: string) =>
  Array.from(
    html.matchAll(/block h-full rounded-md ([a-z0-9-]+)"\s*style="width:(\d+)%"/g),
  ).map((m) => ({ bar: m[1], width: Number(m[2]) }));

// The settled spread board's own ladder, verbatim.
const SETTLED = [
  { key: "a", label: "≥ 1.5 runs", probability: 0, value: 1.5 },
  { key: "b", label: "≥ 2.5 runs", probability: 0, value: 2.5 },
  { key: "c", label: "≥ 3.5 runs", probability: 0, value: 3.5 },
];

describe("#8167 — a zero rung paints nothing", () => {
  test("every leg of a settled ladder draws no fill at all", () => {
    const drawn = fills(renderToStaticMarkup(<QuantityGroup rungs={SETTLED} />));
    expect(drawn).toHaveLength(3);
    expect(drawn.map((d) => d.width)).toEqual([0, 0, 0]);
  });

  test("the number cell still says 0% — the numeral does the work", () => {
    const html = renderToStaticMarkup(<QuantityGroup rungs={SETTLED} />);
    expect(html).toContain('aria-label="≥ 1.5 runs: 0%"');
  });

  test("the track survives, so the ladder keeps its shape", () => {
    const html = renderToStaticMarkup(<QuantityGroup rungs={SETTLED} />);
    expect(html).toContain(
      "flex-1 h-[18px] rounded-md bg-surface-elevated overflow-hidden",
    );
  });

  test("a genuine long shot that ROUNDS to 0% keeps its sliver", () => {
    // 0.004 → `Math.round(0.4)` is 0. A repair gated on the rounded percent
    // would silently delete this bar too, which is the #4660 defect returning
    // from the other side.
    const drawn = fills(
      renderToStaticMarkup(
        <QuantityGroup
          rungs={[{ key: "x", label: "≥ 9.5 runs", probability: 0.004, value: 9.5 }]}
        />,
      ),
    );
    expect(drawn).toEqual([{ bar: "bg-accent-danger", width: 2 }]);
  });

  test("the 2% floor is untouched for an ordinary long shot (#1574)", () => {
    const drawn = fills(
      renderToStaticMarkup(
        <QuantityGroup
          rungs={[{ key: "y", label: "≥ 4.5 runs", probability: 0.02, value: 4.5 }]}
        />,
      ),
    );
    expect(drawn).toEqual([{ bar: "bg-accent-danger", width: 2 }]);
  });

  test("an unpriced rung is still zero (#4660 does not regress)", () => {
    const drawn = fills(
      renderToStaticMarkup(
        <QuantityGroup
          rungs={[{ key: "z", label: "≥ 4.5 runs", probability: null, value: 4.5 }]}
        />,
      ),
    );
    expect(drawn).toEqual([{ bar: "bg-surface-border", width: 0 }]);
  });

  test("a priced rung above the floor is unchanged", () => {
    const drawn = fills(
      renderToStaticMarkup(
        <QuantityGroup
          rungs={[{ key: "w", label: "≥ 0.5 runs", probability: 0.64, value: 0.5 }]}
        />,
      ),
    );
    expect(drawn).toEqual([{ bar: "bg-accent-brand", width: 64 }]);
  });
});

describe("#8167 — the settled board's two cards are no longer alike", () => {
  test("each card prints its own side above identical rungs", () => {
    // The rungs ARE identical and stay identical — that is the market. The
    // heading is the only thing that can tell them apart.
    const atlanta = renderToStaticMarkup(
      <QuantityGroup title="Atlanta" rungs={SETTLED} />,
    );
    const sanDiego = renderToStaticMarkup(
      <QuantityGroup title="San Diego" rungs={SETTLED} />,
    );
    expect(atlanta).toContain("Atlanta");
    expect(sanDiego).toContain("San Diego");
    expect(atlanta).not.toEqual(sanDiego);
  });

  test("and without a title they are byte-identical — the defect, pinned", () => {
    // This is the BEFORE, kept as a control: it is what the reader met, and it
    // is what proves the heading is the whole repair.
    expect(renderToStaticMarkup(<QuantityGroup rungs={SETTLED} />)).toEqual(
      renderToStaticMarkup(<QuantityGroup rungs={SETTLED} />),
    );
  });
});
