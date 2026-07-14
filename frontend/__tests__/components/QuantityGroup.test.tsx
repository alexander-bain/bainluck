// L2-118 Phase 1: the Quantity kernel — one question, many rungs, heat-strip.
// The threshold ladder from the Claude Design spec (§03 Grouped markets),
// tokenized on the L2-117 probabilityHeat scale (no raw Tailwind palette).

import { renderToStaticMarkup } from "react-dom/server";
import React from "react";
import QuantityGroup, { buildThresholdRungs } from "../../components/QuantityGroup";

const RUNGS = [
  { key: "a", label: "≥ 60", probability: 0.98, value: 60 },
  { key: "b", label: "≥ 80", probability: 0.91, value: 80, highlighted: true },
  { key: "c", label: "≥ 95", probability: 0.22, value: 95 },
];

describe("QuantityGroup", () => {
  test("renders every rung's label and percentage", () => {
    const html = renderToStaticMarkup(<QuantityGroup title="Tomatometer" rungs={RUNGS} />);
    expect(html).toContain("≥ 60");
    expect(html).toContain("98%");
    expect(html).toContain("≥ 95");
    expect(html).toContain("22%");
    expect(html).toContain("Tomatometer");
  });

  test("highlighted rung carries the accent-brand line treatment", () => {
    const html = renderToStaticMarkup(<QuantityGroup rungs={RUNGS} lineLabel="≥ 80 is the line" />);
    expect(html).toContain("bg-accent-brand/[0.06]");
    expect(html).toContain("text-accent-brand");
    expect(html).toContain("≥ 80 is the line");
  });

  test("uses ONLY tokenized heat — no raw Tailwind palette classes", () => {
    const html = renderToStaticMarkup(<QuantityGroup rungs={RUNGS} />);
    expect(html).toMatch(/bg-accent-(brand|warning|danger)/);
    expect(html).not.toMatch(/(text|bg)-(green|orange|amber|red|gray|slate)-\d/);
  });

  test("never renders american_odds or an odds formatter output", () => {
    const html = renderToStaticMarkup(<QuantityGroup rungs={RUNGS} />);
    expect(html).not.toContain("american_odds");
    expect(html).not.toMatch(/[+-]\d{3,}/); // no "+220 / -150" moneyline
  });

  test("renders a chevron only when interactive", () => {
    const plain = renderToStaticMarkup(<QuantityGroup rungs={RUNGS} />);
    expect(plain).not.toContain("›");
    const interactive = renderToStaticMarkup(
      <QuantityGroup rungs={RUNGS} onRungSelect={() => {}} />,
    );
    expect(interactive).toContain("›");
    expect(interactive).toContain("tap a rung for its history");
  });

  test("distribution strip renders its bins (non-compact only)", () => {
    const dist = [
      { label: "<70", mass: 0.05 },
      { label: "80s", mass: 0.36, highlighted: true },
    ];
    const html = renderToStaticMarkup(<QuantityGroup rungs={RUNGS} distribution={dist} />);
    expect(html).toContain("Where it lands");
    expect(html).toContain("80s");
    // compact glance zoom drops the distribution
    const compact = renderToStaticMarkup(
      <QuantityGroup rungs={RUNGS} distribution={dist} compact />,
    );
    expect(compact).not.toContain("Where it lands");
  });

  test("empty rungs render nothing", () => {
    expect(renderToStaticMarkup(<QuantityGroup rungs={[]} />)).toBe("");
  });

  test("null probability renders an em dash, never throws", () => {
    const html = renderToStaticMarkup(
      <QuantityGroup rungs={[{ key: "x", label: "≥ 10", probability: null }]} />,
    );
    expect(html).toContain("—");
  });
});

describe("buildThresholdRungs", () => {
  test("formats ≥ N labels and carries probability + sort value", () => {
    const rungs = buildThresholdRungs([
      { outcome_id: 1, name: "80+", probability: 0.5, threshold_value: 80, threshold_unit: "" },
      { outcome_id: 2, name: "$90K+", probability: 0.3, threshold_value: 90000, threshold_unit: "$" },
    ]);
    expect(rungs[0].label).toBe("≥ 80");
    expect(rungs[0].value).toBe(80);
    expect(rungs[0].probability).toBe(0.5);
    expect(rungs[1].label).toBe("≥ $90K");
  });

  test("under/below direction flips the operator", () => {
    const rungs = buildThresholdRungs([
      { outcome_id: 3, name: "under 40", probability: 0.2, threshold_value: 40, threshold_direction: "under" },
    ]);
    expect(rungs[0].label).toBe("≤ 40");
  });

  test("component sorts rungs ascending by value", () => {
    const rungs = buildThresholdRungs([
      { outcome_id: 1, name: "95", probability: 0.2, threshold_value: 95 },
      { outcome_id: 2, name: "60", probability: 0.98, threshold_value: 60 },
    ]);
    const html = renderToStaticMarkup(<QuantityGroup rungs={rungs} />);
    expect(html.indexOf("≥ 60")).toBeLessThan(html.indexOf("≥ 95"));
  });
});
