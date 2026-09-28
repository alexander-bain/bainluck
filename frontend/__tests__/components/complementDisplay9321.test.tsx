import "../helpers/minimalDom";
import React, { act } from "react";
import { createRoot } from "react-dom/client";
import EventHeroProbabilityPair from "../../components/EventHeroProbabilityPair";
import GamePlayCard from "../../components/GamePlayCard";
import { chartAxisPercents, homeProbToChartAxis, resolveProbability } from "../../lib/eventKeyStats";
import type { EventDetailResponse, ActiveChartPoint } from "../../lib/types";

// Mounted production hero/readout plus the chart's real label resolver. This
// isolates formatting: both surfaces hold the SAME raw .445 observation.
// It does not claim to reproduce the initial network ordering of the live hold.
describe("#9321 complementary display at a half-percent boundary", () => {
  test.each([0.555, 1 - 0.445])("REST or adopted away=%s agrees with chart and readout", (away) => {
    const event = Object.freeze({ status: "live", hero_probability: .445,
      hero_probability_away: away, hero_probability_source: "blend" }) as EventDetailResponse;
    const point = Object.freeze({ timestamp: "2026-09-28T07:03:00Z", homeProb: .445,
      awayProb: 1 - .445 }) as ActiveChartPoint;
    const r = resolveProbability(event, undefined, point, true, false);
    const chart = chartAxisPercents(homeProbToChartAxis(point.homeProb));
    const host = document.createElement("div");
    document.body.appendChild(host);
    const root = createRoot(host);
    try {
      act(() => root.render(<>
        <section id="hero"><EventHeroProbabilityPair homeProb={r.homeProb} awayProb={r.awayProb}
          homePct={r.homePct} awayPct={r.awayPct} homeColor="#111827" awayColor="#94a3b8" probSourceLabel="Live" /></section>
        <section id="readout"><GamePlayCard activePoint={null} lastPoint={point}
          homeTeam="Landaluce" awayTeam="Trungelliti" /></section>
        <section id="chart">{chart.homeLabel}/{chart.awayLabel}</section>
      </>));
      expect([r.homePct, r.awayPct]).toEqual([44, 56]);
      expect(host.childNodes[0]?.textContent).toContain("44%");
      expect(host.childNodes[0]?.textContent).toContain("56%");
      expect(host.childNodes[2]?.textContent).toBe("44%/56%");
      expect(host.childNodes[1]?.textContent).toContain("44%");
      expect(host.childNodes[1]?.textContent).toContain("56%");
      expect(event.hero_probability_away).toBe(away);
      expect(point.awayProb).toBe(1 - .445);
    } finally { act(() => root.unmount()); document.body.removeChild(host); }
  });
});
