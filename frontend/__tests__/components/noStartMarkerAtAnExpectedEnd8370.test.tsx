/**
 * #8370 — the web chart stops calling the venue's expected END a "Start".
 *
 * WHAT THE READER SAW (shopper pass 0037, production, 390px, 2026-09-24 07:15Z):
 * `/events/15318148`, Svitolina v Minnen, live, Kalshi the only source. The chart
 * opened on "Since Start" (identical to "All"), with a vertical "Start" line at
 * 11:00 PM PDT — 06:00Z, the hour Kalshi expects the market to RESOLVE. Every big
 * swing of the match sat to the left of it, so the page read as if they happened
 * before play.
 *
 * The payload already said so: `commence_time_is_kickoff = false` (#8215). #8253
 * stopped the chart CUTTING at that hour; the marker and the pill kept using it.
 * The phone has declined both since #8323.
 *
 * `false` ⇒ no "Start" marker, no "Since Start" pill, page default "All".
 * `true` and absent ⇒ unchanged (the controls below).
 */

import React from "react";
import { renderToStaticMarkup } from "react-dom/server";

import OddsChart from "@/components/OddsChart";
import { defaultChartTimeRange } from "@/lib/eventKeyStats";
const { AnalyticsProvider } = require("@/components/Analytics");

/** Fixed instants — never `Date.now()` (gotcha #44). */
const COMMENCE = "2026-09-24T06:00:00.000Z"; // the venue's expected RESOLUTION hour
const OPEN = Date.UTC(2026, 8, 24, 2, 57, 0);
const CLOSE = Date.UTC(2026, 8, 24, 7, 20, 0);

const SERIES = (() => {
  const out = [];
  for (let t = OPEN; t <= CLOSE; t += 5 * 60_000) {
    const p = 0.7 + 0.2 * Math.sin((t - OPEN) / 1_800_000);
    out.push({ timestamp: new Date(t).toISOString(), home_probability: p, away_probability: 1 - p });
  }
  return out;
})();

type ChartProps = Partial<React.ComponentProps<typeof OddsChart>>;

function draw(overrides: ChartProps = {}): string {
  return renderToStaticMarkup(
    React.createElement(
      AnalyticsProvider,
      null,
      <OddsChart
        history={[]}
        homeTeam="Elina Svitolina"
        awayTeam="Greet Minnen"
        commenceTime={COMMENCE}
        eventStatus="live"
        isLive
        winProbHistory={{ kalshi: SERIES } as never}
        {...overrides}
      />,
    ),
  );
}

const startMarker = (html: string): string => {
  const m = html.match(/data-start-marker="([^"]*)"/);
  if (!m) throw new Error("the wrapper lost its data-start-marker attribute");
  return m[1];
};
const offersSinceStart = (html: string) => />Since Start</.test(html);
const pressed = (html: string, label: string) =>
  new RegExp(`aria-pressed="true"[^>]*>${label}<`).test(html);

const payload = (commence_time_is_kickoff?: boolean) =>
  ({
    history: [],
    win_prob_history: { kalshi: SERIES },
    ...(commence_time_is_kickoff === undefined ? {} : { commence_time_is_kickoff }),
  }) as never;

describe("#8370 — no 'Start' at an hour the server says is not a start", () => {
  it("the specimen draws ink on both sides of commence_time (else every arm is vacuous)", () => {
    const at = new Date(COMMENCE).getTime();
    expect(SERIES.some((p) => new Date(p.timestamp).getTime() < at)).toBe(true);
    expect(SERIES.filter((p) => new Date(p.timestamp).getTime() >= at).length).toBeGreaterThan(2);
  });

  // Marker arms are read on "All": that window holds ink on both sides of the
  // hour, so it is the one where the marker used to be drawn. ("Since Start"
  // opens at the first point AFTER the hour, and the marker is bounded by ink.)
  it("a served `false` draws no 'Start' marker, even on 'All'", () => {
    expect(startMarker(draw({ commenceTimeIsKickoff: false, externalTimeRange: "all" }))).toBe("");
  });

  it("a served `false` offers no 'Since Start' and opens on 'All'", () => {
    const html = draw({ commenceTimeIsKickoff: false });
    expect(offersSinceStart(html)).toBe(false);
    expect(pressed(html, "All")).toBe(true);
  });

  it("the page's shared range opens on 'All' for a served `false`", () => {
    expect(defaultChartTimeRange(payload(false), COMMENCE)).toBe("all");
  });

  it("CONTROL — `true` keeps the marker, the pill and the 'Since Start' default", () => {
    expect(startMarker(draw({ commenceTimeIsKickoff: true, externalTimeRange: "all" }))).toBe("6:00 AM");
    const html = draw({ commenceTimeIsKickoff: true });
    expect(offersSinceStart(html)).toBe(true);
    expect(pressed(html, "Since Start")).toBe(true);
    expect(defaultChartTimeRange(payload(true), COMMENCE)).toBe("live");
  });

  it("CONTROL — an older payload with no flag is unchanged", () => {
    expect(startMarker(draw({ externalTimeRange: "all" }))).toBe("6:00 AM");
    const html = draw();
    expect(offersSinceStart(html)).toBe(true);
    expect(pressed(html, "Since Start")).toBe(true);
    expect(defaultChartTimeRange(payload(undefined), COMMENCE)).toBe("live");
  });
});
