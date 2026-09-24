// #2437 — a rung that states a verdict renders the site-wide settled dialect
// (`Won`/`Lost`, `100%`/`0%`, `Settled`), matching `OutcomeRow`. A rung that
// states nothing renders exactly as today.
import React from "react";
import { renderToStaticMarkup } from "react-dom/server";
import QuantityGroup from "@/components/QuantityGroup";

function render(rungs: Parameters<typeof QuantityGroup>[0]["rungs"]): string {
  return renderToStaticMarkup(
    <QuantityGroup title="Final Results" rungs={rungs} sort={false} />,
  );
}

describe("#2437 QuantityGroup verdict render", () => {
  test("graded rungs print Won/Lost + 100%/0% + Settled", () => {
    const html = render([
      { key: 1, label: "Before April", probability: 0, value: 0, verdict: "lost" },
      { key: 2, label: "Before 2027", probability: 1, value: 1, verdict: "won" },
    ]);
    expect(html).toContain(">Won<");
    expect(html).toContain(">Lost<");
    expect(html).toContain("100%");
    expect(html).toContain("0%");
    expect(html.split("Settled").length - 1).toBe(2);
  });

  test("an ungraded rung beside graded ones keeps its price and states nothing", () => {
    const html = render([
      { key: 1, label: "Before April", probability: 0.42, value: 0, verdict: null },
      { key: 2, label: "Before 2027", probability: 1, value: 1, verdict: "won" },
    ]);
    expect(html).toContain("42%");
    expect(html.split("Settled").length - 1).toBe(1);
    expect(html.split('data-testid="rung-verdict"').length - 1).toBe(1);
  });

  test("a graded rung never advertises a live move", () => {
    const html = render([
      { key: 1, label: "Before April", probability: 0, value: 0, verdict: "lost", movement: 0.035 },
      { key: 2, label: "Before 2027", probability: 1, value: 1, verdict: "won", movement: -0.015 },
    ]);
    expect(html).not.toContain("pts");
  });

  test("an ungraded ladder is byte-untouched: no verdict slot, no Settled", () => {
    const html = render([
      { key: 1, label: "≥ 60", probability: 0.9, value: 60 },
      { key: 2, label: "≥ 80", probability: 0.4, value: 80 },
    ]);
    expect(html).not.toContain("rung-verdict");
    expect(html).not.toContain("Settled");
    expect(html).not.toContain("calc(4ch");
  });
});
