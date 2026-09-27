import React from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { Histogram } from "../../components/economics/atoms";

// /economics at 390px, the Inflation card: "September 2026 CPI MoM Combo ·
// Headline & Core" (market 61484986). Each bucket is two legs. The side label
// column (88px, truncate) printed three rows reading `0.5% or above…` and three
// reading `Exactly 0.4%,…` — 37.5% and 37% were two different questions a
// reader could not tell apart. The served labels were whole; the layout ate
// them. These are the served labels, verbatim, in served order.
const COMBO: [number, string][] = [
  [37.5, "Headline: 0.5% or above, Core: 0.3% or above"],
  [37.0, "Headline: 0.5% or above, Core: Exactly 0.2%"],
  [7.0, "Headline: 0.5% or above, Core: 0.1% or below"],
  [4.0, "Headline: Exactly 0.4%, Core: 0.1% or below"],
  [3.0, "Headline: Exactly 0.4%, Core: Exactly 0.2%"],
  [2.0, "Headline: Exactly 0.4%, Core: 0.3% or above"],
  [1.0, "Headline: 0.2% or below, Core: Exactly 0.2%"],
  [1.0, "Headline: 0.2% or below, Core: 0.3% or above"],
];

const html = (buckets: [number, string][]) =>
  renderToStaticMarkup(<Histogram buckets={buckets} color="#10B981" />);

const printedLabels = (markup: string) =>
  [...markup.matchAll(/<span class="font-mono text-\[10px\] leading-snug break-words[^"]*">([^<]*)<\/span>/g)].map(m => m[1]);

describe("a combo histogram's leg labels", () => {
  it("prints every label whole, both legs", () => {
    expect(printedLabels(html(COMBO))).toEqual(COMBO.map(b => b[1]));
  });

  it("never truncates a label", () => {
    // The ellipsis is what made the rows identical; a stacked label wraps.
    expect(html(COMBO)).not.toMatch(/truncate/);
  });

  it("keeps each leg's name — the shared `Headline:` is not boilerplate here", () => {
    const labels = printedLabels(html(COMBO));
    expect(labels.every(l => l.startsWith("Headline: ") && l.includes(", Core: "))).toBe(true);
  });

  it("the two top rows are told apart on screen", () => {
    const labels = printedLabels(html(COMBO));
    expect(labels[0]).not.toBe(labels[1]);
    expect(new Set(labels).size).toBe(labels.length);
  });
});

describe("short labels keep the side column", () => {
  it("a bracket histogram is not stacked", () => {
    const markup = html([
      [45, "3.5%"],
      [22.5, "3.6%"],
      [10, "1.9 to 2.1%"],
      [4, "0.0% or Below"],
    ]);
    expect(markup).not.toContain('data-histogram-row="stacked"');
    expect(markup).toContain("text-right shrink-0 truncate");
  });

  it("one long label stacks the whole card, so rows stay aligned", () => {
    const markup = html([
      [60, "3.5%"],
      [40, "Headline: 0.5% or above, Core: 0.3% or above"],
    ]);
    expect(markup.match(/data-histogram-row="stacked"/g)).toHaveLength(2);
  });
});
