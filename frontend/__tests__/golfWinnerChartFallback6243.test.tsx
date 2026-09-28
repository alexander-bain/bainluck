/**
 * #6243 — the golf hub's "Win Probability" chart draws the Winner market that has a
 * curve, not the one whose whole history is one snapshot.
 *
 * Production 2026-09-28, Alfred Dunhill Links: `current_event.market_ids` opens on
 * DataGolf 62904927 (30 outcomes × 1 point, all at 00:37:20Z). The old fallback
 * advanced only on `outcomes.length === 0`, read 30, and stopped — the chart printed
 * "Limited price history available". Kalshi's Winner 62455818 (120 points over 8
 * timestamps) never got asked. The walk must also never land on a Round Leader or
 * Top-N curve under a "Win Probability" heading (#955).
 */
import "./helpers/minimalDom";
import React, { act } from "react";
import { createRoot } from "react-dom/client";

const mockFetch = jest.fn();
jest.mock("@/lib/api", () => ({
  fetchFuturesHistory: (...args: unknown[]) => mockFetch(...args),
}));
jest.mock("@/components/EvolutionView", () => ({
  EvolutionView: ({ marketId }: { marketId: number }) => <span>chart:{marketId}</span>,
}));

import { EvolutionViewWithFallback } from "@/components/golf/GolfWinnerEvolutionChart";
import { isDrawableHistory, winnerChartCandidates } from "@/lib/golfWinnerChart";

const DG_WIN = 62904927;
const DG_TOP5 = 62904928;
const K_WIN = 62455818;
const K_R1 = 62952894;

const oneSnapshot = {
  outcomes: Array.from({ length: 30 }, (_, i) => ({
    outcome_id: i,
    name: `Golfer ${i}`,
    history: [{ timestamp: "2026-09-28T00:37:20.758062+00:00", probability: 0.03,
      american_odds: null, bookmaker: "datagolf" }],
  })),
};
const curve = {
  outcomes: [{
    outcome_id: 1, name: "Tommy Fleetwood",
    history: [
      { timestamp: "2026-09-27T23:51:00Z", probability: 0.13, american_odds: null, bookmaker: "kalshi" },
      { timestamp: "2026-09-28T07:52:00Z", probability: 0.135, american_odds: null, bookmaker: "kalshi" },
    ],
  }],
};

async function renderChart(ids: number[], names: string[] | undefined, byId: Record<number, unknown>) {
  mockFetch.mockReset();
  mockFetch.mockImplementation((id: number) =>
    byId[id] ? Promise.resolve(byId[id]) : Promise.reject(new Error("no")),
  );
  const host = document.createElement("div");
  document.body.appendChild(host);
  const root = createRoot(host);
  await act(async () => {
    root.render(<EvolutionViewWithFallback marketIds={ids} marketNames={names}
      marketName="Alfred Dunhill Links Championship — Win Probability" defaultTopN={8} hours={168} />);
  });
  for (let i = 0; i < 6; i++) await act(async () => { await Promise.resolve(); });
  const text = host.textContent;
  act(() => root.unmount());
  document.body.removeChild(host);
  return { text, asked: mockFetch.mock.calls.map((c) => c[0]) };
}

const IDS = [DG_WIN, K_WIN, DG_TOP5, K_R1];
const NAMES = [
  "Alfred Dunhill Links Championship - Winner",
  "Alfred Dunhill Links Championship Winner",
  "Alfred Dunhill Links Championship - Top 5 Finish",
  "Alfred Dunhill Links Championship End of Round 1 Leader",
];

describe("#6243 golf Win Probability chart fallback", () => {
  it("walks past a one-snapshot Winner to the traded Winner with a curve", async () => {
    const { text, asked } = await renderChart(IDS, NAMES, { [DG_WIN]: oneSnapshot, [K_WIN]: curve });
    expect(text).toBe(`chart:${K_WIN}`);
    expect(asked).toEqual([DG_WIN, K_WIN]);
  });

  it("keeps the first Winner when it draws (no change to today's good case)", async () => {
    const { text, asked } = await renderChart(IDS, NAMES, { [DG_WIN]: curve, [K_WIN]: curve });
    expect(text).toBe(`chart:${DG_WIN}`);
    expect(asked).toEqual([DG_WIN]);
  });

  it("never lands on a Round Leader or Top-N curve under a Win Probability heading", async () => {
    const { text, asked } = await renderChart(IDS, NAMES,
      { [DG_WIN]: oneSnapshot, [K_WIN]: oneSnapshot, [DG_TOP5]: curve, [K_R1]: curve });
    // nothing can draw: the first Winner's own empty state, exactly as before
    expect(text).toBe(`chart:${DG_WIN}`);
    expect(asked).not.toContain(DG_TOP5);
    expect(asked).not.toContain(K_R1);
  });

  it("without names walks the served list as before", async () => {
    const { text } = await renderChart([DG_WIN, DG_TOP5], undefined, { [DG_WIN]: oneSnapshot, [DG_TOP5]: curve });
    expect(text).toBe(`chart:${DG_TOP5}`);
  });
});

describe("#6243 helpers", () => {
  it("a field of single points at one moment is not drawable; two moments are", () => {
    expect(isDrawableHistory(oneSnapshot)).toBe(false);
    expect(isDrawableHistory(curve)).toBe(true);
    expect(isDrawableHistory({ outcomes: [] })).toBe(false);
  });

  it("null prices do not count toward a line", () => {
    expect(isDrawableHistory({ outcomes: [{ outcome_id: 1, name: "x", history: [
      { timestamp: "2026-09-27T00:00:00Z", probability: null, american_odds: null, bookmaker: "k" },
      { timestamp: "2026-09-28T00:00:00Z", probability: 0.1, american_odds: null, bookmaker: "k" },
    ] }] })).toBe(false);
  });

  it("candidates are the Winner questions in served order; none ⇒ the list unchanged", () => {
    expect(winnerChartCandidates(IDS, NAMES)).toEqual([DG_WIN, K_WIN]);
    expect(winnerChartCandidates([DG_TOP5, K_R1], [NAMES[2], NAMES[3]])).toEqual([DG_TOP5, K_R1]);
    expect(winnerChartCandidates(IDS, NAMES.slice(0, 2))).toEqual(IDS);
  });
});
