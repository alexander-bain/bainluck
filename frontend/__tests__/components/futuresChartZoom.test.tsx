// L2-164: SSR render guards for the FuturesChart low-prob zoom chip. Fixed
// 0–100% stays the default (no chip unless opted in); the chip appears — labeled
// with the rounded bound — only for an eligible low-prob, non-mini series.
import { renderToStaticMarkup } from "react-dom/server";
import React from "react";
import { FuturesChart } from "../../components/FuturesChart";
import type { FuturesOutcomeHistory } from "../../lib/types";

// A season-journey-shaped low-prob line (~4% → ~12%), enough points to draw.
const LOW_PROB: FuturesOutcomeHistory[] = [
  {
    outcome_id: 1,
    name: "Boston Red Sox",
    history: [
      { timestamp: "2026-04-01T00:00:00Z", probability: 0.04 },
      { timestamp: "2026-05-01T00:00:00Z", probability: 0.06 },
      { timestamp: "2026-06-01T00:00:00Z", probability: 0.09 },
      { timestamp: "2026-07-01T00:00:00Z", probability: 0.12 },
    ],
  } as unknown as FuturesOutcomeHistory,
];

describe("FuturesChart zoom chip", () => {
  test("renders the zoom chip with a rounded bound when allowZoom + low-prob", () => {
    const html = renderToStaticMarkup(
      <FuturesChart historyData={LOW_PROB} selectedOutcomes={new Set([1])} fixedYAxis allowZoom />,
    );
    // 0.12 * 1.1 = 0.132 → rounds up to 0.15 → "Zoom 0–15%".
    expect(html).toContain("Zoom 0–15%");
    expect(html).toContain("aria-pressed");
  });

  test("no chip when allowZoom is not set (default off)", () => {
    const html = renderToStaticMarkup(
      <FuturesChart historyData={LOW_PROB} selectedOutcomes={new Set([1])} fixedYAxis />,
    );
    expect(html).not.toContain("Zoom 0–");
  });

  test("no chip in mini/sparkline mode even with allowZoom", () => {
    const html = renderToStaticMarkup(
      <FuturesChart historyData={LOW_PROB} selectedOutcomes={new Set([1])} mini allowZoom />,
    );
    expect(html).not.toContain("Zoom 0–");
  });

  test("no chip for a high-prob series (fixed axis already fits)", () => {
    const high: FuturesOutcomeHistory[] = [
      {
        outcome_id: 2,
        name: "Favorite",
        history: [
          { timestamp: "2026-04-01T00:00:00Z", probability: 0.6 },
          { timestamp: "2026-05-01T00:00:00Z", probability: 0.72 },
        ],
      } as unknown as FuturesOutcomeHistory,
    ];
    const html = renderToStaticMarkup(
      <FuturesChart historyData={high} selectedOutcomes={new Set([2])} fixedYAxis allowZoom />,
    );
    expect(html).not.toContain("Zoom 0–");
    // Unzoomed default still pins the axis to 100%.
    expect(html).toContain("100%");
  });
});
