// #9576 (after-check residual) — THE LADDER MAP READS LIKE ITS OWN ROWS.
//
// Production, 390px, 2026-09-29 ~11:00Z, after PR #9591 went live:
// `/futures/59699693` (Hurricane Polo category?) printed a ">99%" hero and ">99%"
// on every All Outcomes row, and between them this map printed
// "≥ 1 … ≥ 5 · 100%". Every rung is a still-trading 0.995. `QuantityGroup`
// formatted with a bare `Math.round(p * 100)`, while the hero and the rows use
// `probabilityParts`' boundary rule.
//
//   cd frontend && npx jest --testPathPatterns=quantityGroupBoundary9576

import React from "react";
import { renderToStaticMarkup } from "react-dom/server";

import QuantityGroup, { buildThresholdRungs } from "@/components/QuantityGroup";

/** The served Polo rungs: five "Category N or above" legs, each 0.995. */
const POLO = [1, 2, 3, 4, 5].map((n) => ({
  outcome_id: 900 + n,
  name: `Category ${n} or above`,
  probability: 0.995,
  threshold_value: n,
}));

function visible(markup: string): string {
  return markup
    .replace(/<[^>]*>/g, " ")
    .replace(/&gt;/g, ">")
    .replace(/&lt;/g, "<")
    .replace(/\s+/g, " ");
}

describe("#9576 · QuantityGroup prints a rung with the rows' boundary rule", () => {
  it("a still-trading 0.995 on every rung reads >99%, never 100%", () => {
    const rungs = buildThresholdRungs(POLO);
    expect(rungs).toHaveLength(5);
    const text = visible(renderToStaticMarkup(<QuantityGroup rungs={rungs} />));
    expect(text.match(/>99%/g)).toHaveLength(5);
    expect(text).not.toContain("100%");
  });

  it("the other boundary: a live 0.004 reads <1%, never 0%", () => {
    const text = visible(
      renderToStaticMarkup(<QuantityGroup rungs={[{ key: 1, label: "≥ 5", probability: 0.004 }]} />),
    );
    expect(text).toContain("<1%");
    expect(text).not.toMatch(/(^|[^<\d])0%/);
  });

  it("a certain 1.0, an ordinary 0.62 and a missing price print as before", () => {
    const text = visible(
      renderToStaticMarkup(
        <QuantityGroup
          rungs={[
            { key: 1, label: "≥ 1", probability: 1 },
            { key: 2, label: "≥ 2", probability: 0.62 },
            { key: 3, label: "≥ 3", probability: null },
          ]}
        />,
      ),
    );
    expect(text).toContain("100%");
    expect(text).toContain("62%");
    expect(text).toContain("—");
    expect(text).not.toContain(">99%");
  });
});
