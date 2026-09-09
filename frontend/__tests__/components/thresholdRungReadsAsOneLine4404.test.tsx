/**
 * #4404 — a threshold rung reads as one line, and its unit is a separate word.
 *
 * On production `/sports` at 390px every soccer totals ladder printed:
 *
 *     ≥
 *     0.5goals   ████████████████░░░░   89%  >
 *
 * Two defects wearing one label, and they need separate assertions because
 * either one alone still leaves the row unreadable:
 *
 *  1. **`0.5goals`** — `formatThresholdLabel` joined the threshold and its unit
 *     with nothing between them. A string bug, wrong at every width, and the
 *     cheapest thing in this file to guard.
 *  2. **The orphaned `≥`** — the numeric label track is a fixed `w-11`
 *     (2.75rem ≈ 44px), which holds "≥ 95" and "$90K+" but not a unit-bearing
 *     label. Measured on the live page: label box 44px, ink 62px,
 *     `white-space: normal`, so it wrapped between the operator and the number
 *     it qualifies. 32 rungs, four per card, three cards in one viewport.
 *
 * The control that can fail is the numeric ladder: it must keep the `w-11`
 * class byte-for-byte, because a fix that widened EVERY ladder would also be a
 * fix that silently shortened every bar on the site (#1574 acceptance c is the
 * property at stake — one width per ladder, so equal percentages draw equal
 * bars).
 */
import { renderToStaticMarkup } from "react-dom/server";
import QuantityGroup, { buildThresholdRungs } from "@/components/QuantityGroup";

const totalsOutcomes = [0.5, 1.5, 2.5, 3.5].map((v, i) => ({
  outcome_id: i + 1,
  name: `Over ${v}`,
  probability: 0.9 - i * 0.2,
  threshold_value: v,
  threshold_unit: "goals",
  threshold_direction: "over",
}));

describe("#4404 the label string", () => {
  test("a word unit is a separate word", () => {
    const rungs = buildThresholdRungs(totalsOutcomes);
    expect(rungs.map((r) => r.label)).toEqual([
      "≥ 0.5 goals",
      "≥ 1.5 goals",
      "≥ 2.5 goals",
      "≥ 3.5 goals",
    ]);
    // Stated as its own invariant so a future unit ("yards", "points", "wins")
    // cannot regress past a list of four literals.
    for (const r of rungs) expect(r.label).not.toMatch(/\d[A-Za-z]/);
  });

  test("a SYMBOL unit stays welded to its number", () => {
    // "≥ 80 %" would be wrong in the other direction, so the separator is
    // decided by the unit's first character, not by a flag.
    const [pct] = buildThresholdRungs([
      { outcome_id: 1, name: "80+", probability: 0.5, threshold_value: 80, threshold_unit: "%" },
    ]);
    expect(pct.label).toBe("≥ 80%");
  });

  test("the currency shapes are untouched", () => {
    const rungs = buildThresholdRungs([
      { outcome_id: 1, name: "a", probability: 0.5, threshold_value: 90_000, threshold_unit: "$" },
      { outcome_id: 2, name: "b", probability: 0.4, threshold_value: 2_500_000, threshold_unit: "$" },
    ]);
    expect(rungs.map((r) => r.label)).toEqual(["≥ $90K", "≥ $2.5M"]);
  });

  test("a bare numeric threshold is unchanged", () => {
    const [r] = buildThresholdRungs([
      { outcome_id: 1, name: "80", probability: 0.5, threshold_value: 80 },
    ]);
    expect(r.label).toBe("≥ 80");
  });
});

describe("#4404 the label track", () => {
  test("a unit-bearing ladder gets a track that cannot wrap it", () => {
    const html = renderToStaticMarkup(
      <QuantityGroup title="Total goals" rungs={buildThresholdRungs(totalsOutcomes)} />,
    );
    // Not the 44px column that produced the wrap…
    expect(html).not.toContain("w-11");
    // …a track sized to the longest label ("≥ 3.5 goals" = 11 chars), floored at
    // the old width and capped so it can never eat the bar, and non-wrapping
    // (`truncate` = overflow-hidden + text-ellipsis + whitespace-nowrap).
    expect(html).toContain("clamp(2.75rem, calc(11ch + 0.5rem), 45%)");
    expect(html).toContain("truncate");
  });

  test("ONE width for every rung — equal percentages still draw equal bars", () => {
    const html = renderToStaticMarkup(
      <QuantityGroup rungs={buildThresholdRungs(totalsOutcomes)} />,
    );
    const widths = [...html.matchAll(/width:\s*(clamp\([^)]*\)[^;"]*)/g)].map((m) => m[1]);
    expect(widths.length).toBe(4);
    expect(new Set(widths).size).toBe(1);
  });

  test("CONTROL: a numeric ladder keeps the w-11 column exactly as it was", () => {
    const html = renderToStaticMarkup(
      <QuantityGroup
        rungs={[
          { key: "a", label: "≥ 60", probability: 0.98, value: 60 },
          { key: "b", label: "≥ 95", probability: 0.22, value: 95 },
        ]}
      />,
    );
    expect(html).toContain("w-11");
    expect(html).not.toContain("clamp(2.75rem");
  });

  test("CONTROL: a 5-character label still fits the old column", () => {
    // "$90K+" is exactly the width the fixed track was chosen for. One character
    // more and the ladder must widen; this pins the boundary from the short side
    // so the threshold cannot drift up and re-open the wrap.
    const fits = renderToStaticMarkup(
      <QuantityGroup rungs={[{ key: "a", label: "$90K+", probability: 0.5, value: 90 }]} />,
    );
    expect(fits).toContain("w-11");
    const doesNot = renderToStaticMarkup(
      <QuantityGroup rungs={[{ key: "a", label: "$900K+", probability: 0.5, value: 900 }]} />,
    );
    expect(doesNot).not.toContain("w-11");
  });

  test("CONTROL: wideLabels is still its own track, not this one", () => {
    const html = renderToStaticMarkup(
      <QuantityGroup
        wideLabels
        rungs={[
          { key: "a", label: "2027", probability: 0.4, value: 2027 },
          { key: "b", label: "2029 or later", probability: 0.1, value: 2029 },
        ]}
      />,
    );
    expect(html).toContain("w-[45%]");
    expect(html).not.toContain("clamp(2.75rem");
  });
});
