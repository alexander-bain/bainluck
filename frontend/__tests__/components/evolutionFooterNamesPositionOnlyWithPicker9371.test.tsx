/**
 * #9371 — THE CHART FOOTER NAMES A POSITION ONLY WHEN THE CHART HAS A PICKER.
 *
 * Seen on https://bainluck.com/categories/golf at 390px, 2026-09-28 12:28Z:
 *
 *     Alfred Dunhill Links Championship — Win Probability    8 of
 *     — Win                                                   41
 *
 * `EvolutionView`'s footer appended `activePositionLabel`, which fell back to
 * "Win" for every chart WITHOUT a position picker — the golf hub (name already
 * says "Win Probability") and the tournament page's fallback ("… - Winner").
 * And the count was a shrinkable flex child, so it wrapped.
 *
 * SHIP arm: the golf hub's real props render the name alone. CONTROL arm: a
 * chart WITH a picker still names the selected position. Rendered with the real
 * component (static markup; SWR has no data on the server, so the footer shows
 * its loading-state count — the footer markup is the same either way).
 */

import { renderToStaticMarkup } from "react-dom/server";
import React from "react";

jest.mock("@/lib/api", () => ({
  fetchFuturesHistory: jest.fn(),
  fetchMultiMarketHistory: jest.fn(),
}));

import { EvolutionView, type PositionOption } from "@/components/EvolutionView";

function footer(html: string): string {
  const i = html.lastIndexOf("border-t border-surface-border bg-surface-secondary/80");
  expect(i).toBeGreaterThan(-1);
  return html.slice(i);
}

/** The footer's label span, as a reader reads it: React separates adjacent text
 *  nodes with a literal `<!-- -->`, which is not text. No tag stripping. */
function text(fragment: string): string {
  const m = fragment.match(/<span class="min-w-0">([^<]*(?:<!-- -->[^<]*)*)<\/span>/);
  expect(m).not.toBeNull();
  return m![1].split("<!-- -->").join("");
}

describe("#9371 EvolutionView footer", () => {
  it("SHIP: the golf hub's props print the name once, with no appended '— Win'", () => {
    const html = renderToStaticMarkup(
      <EvolutionView
        marketId={62455818}
        marketName="Alfred Dunhill Links Championship — Win Probability"
        defaultTopN={8}
        hours={168}
      />
    );
    const f = text(footer(html));
    expect(f).toContain("Alfred Dunhill Links Championship — Win Probability");
    expect(f).not.toContain("Win Probability — Win");
    expect(f).not.toMatch(/ — Win(?! Probability)/);
  });

  it("CONTROL: a chart with a position picker still names the selected position", () => {
    const positions: PositionOption[] = [
      { key: "top_5", label: "Top 5", marketId: 1 },
      { key: "win", label: "Win", marketId: 2 },
    ];
    const html = renderToStaticMarkup(
      <EvolutionView marketId={2} marketName="Alfred Dunhill Links Championship" positionOptions={positions} />
    );
    // default selection is the LAST option ("win")
    expect(text(footer(html))).toContain("Alfred Dunhill Links Championship — Win");
  });

  it("the count stays on one line beside a long name", () => {
    const html = renderToStaticMarkup(
      <EvolutionView marketId={62455818} marketName="Alfred Dunhill Links Championship — Win Probability" />
    );
    const f = footer(html);
    expect(f).toMatch(/<span class="shrink-0 whitespace-nowrap">0 of 0<\/span>/);
    expect(f).toContain('<span class="min-w-0">');
  });
});
