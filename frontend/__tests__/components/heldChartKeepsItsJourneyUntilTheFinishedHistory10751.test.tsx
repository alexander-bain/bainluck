// #10751 — a held chart keeps its journey through the final: it never drops its
// last ~30 minutes of movement while the headline already says Final.
//
// THE SPECIMEN. Production, event 15333459 (Halmstads BK 0-3 Malmo FF,
// Allsvenskan), held page on 2026-10-28, shopper's retained capture
// (artifacts/shopper/event-20261028T1926Z-11685-held-to-final, SHA256SUMS
// ee971d7e…). Both fixtures are those served bodies byte for byte:
//
//   19:57:00.43Z  /history  status live, completed_at null, blend through 19:57:00
//   19:57:14.46Z  /events   status completed, completed_at 19:56:54.82
//   19:59:15.44Z  /history  status completed, result point 19:56:00 (home 0)
//
// For the 2 minutes between the second and third reads the held chart drew
// endpoint 19:27:00 (basis unavailable), 96 categories instead of 118, axis
// ending 12:31 PM — then the finished history put it back.
//
// THE CAUSE. Both the shared domain (`computeSharedChartDomain`) and
// `OddsChart`'s own end cut trim a FINISHED game to its last game-end evidence,
// and they decided "finished" from the DETAIL's status. The body they trimmed
// was still the live one: no ESPN or model series, a score series whose last
// change is the 0-3 at 19:30:23, and sportsbooks that stopped quoting at 19:27.
// So the domain ended at 19:30 and the ink at 19:27, though the body itself
// says the game was still being played when it was built.
//
// THE CONTRACT. A served body built while the event was still in play predates
// the finish, so it carries no evidence of where the game ended; it is drawn
// as served until the history body with the result arrives. That body's
// endpoint is unchanged (#11685 stays green).
//
// Rig: the page's own domain call and the real `OddsChart` at 390px, the
// page's endpoint identity, no frames (the served body already holds every
// minute the held page drew).

import React from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { readFileSync } from "fs";
import { join } from "path";

jest.mock("@/components/Analytics/AnalyticsProvider", () => ({
  __esModule: true,
  useAnalyticsContext: () => ({ track: () => {} }),
  AnalyticsProvider: ({ children }: { children: React.ReactNode }) => children,
}));
jest.mock("recharts", () => ({
  __esModule: true,
  ...jest.requireActual("recharts"),
  ResponsiveContainer: ({ children }: { children: React.ReactElement }) =>
    React.cloneElement(children, { width: 390, height: 300 }),
}));

import OddsChart from "@/components/OddsChart";
import { computeSharedChartDomain } from "@/lib/eventKeyStats";
import { chartEndpointIdentity } from "@/lib/displayIdentity";
import { servedBeforeFinish } from "@/lib/eventState";
import type { EventHistoryResponse } from "@/lib/types";

const fixture = (name: string): EventHistoryResponse =>
  JSON.parse(readFileSync(join(__dirname, "../fixtures", name), "utf8"));
const LIVE_BODY = fixture("event-15333459-history-10751-live-1957.json");
const FINAL_BODY = fixture("event-15333459-history-10751-final-1959.json");
const COMMENCE = "2026-10-28T18:00:00+00:00";
const SPORT = "soccer_sweden_allsvenskan";

const PAGE = readFileSync(join(__dirname, "../../app/events/[id]/page.tsx"), "utf8");

/** The page's chart composition for one (served body, detail status) pair. */
const draw = (body: EventHistoryResponse, status: "live" | "completed", passServedStatus = true) => {
  const domain = computeSharedChartDomain(body, "live", status, COMMENCE, SPORT, null);
  const identity = chartEndpointIdentity({
    served: body, final: body, line: body.aggregate_line, frames: [],
    heroRevision: null, preview: null,
  });
  const html = renderToStaticMarkup(<OddsChart
    history={body.history ?? []} bookmakerHistory={body.bookmaker_history}
    espnHistory={body.espn_history} winProbHistory={body.win_prob_history}
    winProbSources={body.win_prob_sources} scoreHistory={body.score_history}
    aggregateLine={body.aggregate_line ?? undefined} aggregateEndpointIdentity={identity}
    backendBlendServed homeTeam="Halmstads BK" awayTeam="Malmo FF" sportKey={SPORT}
    isLive={status === "live"} eventStatus={status} commenceTime={COMMENCE}
    servedStatus={passServedStatus ? body.status ?? undefined : undefined}
    completedAt={body.completed_at ?? undefined}
    chartStartTime={domain?.start} chartEndTime={domain?.end}
    sharedTicks={domain?.ticks} chartLabelFormat={domain?.labelFormat}
  />);
  return { domain, html };
};
const attr = (html: string, name: string) => new RegExp(`${name}="([^"]*)"`).exec(html)?.[1];
const categories = (html: string) => Number(attr(html, "data-category-span")?.split(",")[2]);

describe("#10751 the held chart keeps its journey until the finished history arrives", () => {
  it("the specimen's bodies are what production served", () => {
    expect(LIVE_BODY.status).toBe("live");
    expect(LIVE_BODY.completed_at).toBeNull();
    expect(LIVE_BODY.aggregate_line!.at(-1)!.timestamp).toBe("2026-10-28T19:57:00.153342+00:00");
    expect(LIVE_BODY.history!.at(-1)!.timestamp).toBe("2026-10-28T19:27:00+00:00");
    expect(LIVE_BODY.score_history!.at(-1)!.timestamp).toBe("2026-10-28T19:30:23.597747+00:00");
    expect(FINAL_BODY.status).toBe("completed");
    expect(FINAL_BODY.aggregate_line!.at(-1)).toEqual({ timestamp: "2026-10-28T19:56:00+00:00", home_probability: 0 });
  });

  it("live (capture #130): the line ends on the served 19:57:00 edge over 118 categories", () => {
    const { html } = draw(LIVE_BODY, "live");
    expect(attr(html, "data-chart-endpoint-at")).toBe("2026-10-28T19:57:00.153342+00:00");
    expect(attr(html, "data-chart-endpoint-basis")).toBe("history");
    expect(categories(html)).toBe(118);
  });

  it("Final detail, live body still held (captures #131-#138): the same journey stays drawn", () => {
    const live = draw(LIVE_BODY, "live");
    const held = draw(LIVE_BODY, "completed");
    expect(attr(held.html, "data-chart-endpoint-at")).toBe("2026-10-28T19:57:00.153342+00:00");
    expect(attr(held.html, "data-chart-endpoint-basis")).toBe("history");
    expect(attr(held.html, "data-callout-label")).toBe("1%");
    expect(categories(held.html)).toBe(categories(live.html));
    expect(held.domain!.end).toBe(live.domain!.end);
    expect(Date.parse(held.domain!.end)).toBeGreaterThanOrEqual(Date.parse("2026-10-28T19:57:00Z"));
  });

  it("the finished history (capture #139) ends on the result, as before (#11685)", () => {
    const { html, domain } = draw(FINAL_BODY, "completed");
    expect(attr(html, "data-chart-endpoint-at")).toBe("2026-10-28T19:56:00+00:00");
    expect(attr(html, "data-chart-endpoint-basis")).toBe("history");
    expect(attr(html, "data-callout-label")).toBe("0%");
    expect(domain!.end).toBe("2026-10-28T19:56:00.000Z");
  });

  it("CONTROL: an older body with no status keeps today's cut, in the domain and in the ink", () => {
    const unstated = { ...LIVE_BODY, status: undefined };
    const domain = computeSharedChartDomain(unstated, "live", "completed", COMMENCE, SPORT, null);
    expect(domain!.end).toBe("2026-10-28T19:31:00.000Z"); // the last score change (19:30:23), on its minute: production's "12:31 PM" axis
    const { html } = draw(unstated, "completed");
    expect(attr(html, "data-chart-endpoint-at")).toBe("2026-10-28T19:27:00+00:00"); // the last sportsbook quote
  });

  it("CONTROL: OddsChart told nothing about the body (absent prop) keeps today's cut", () => {
    const { html } = draw(LIVE_BODY, "completed", false);
    expect(attr(html, "data-chart-endpoint-at")).toBe("2026-10-28T19:27:00+00:00");
  });

  it("both page charts (card and fullscreen) hand OddsChart the served body's status", () => {
    expect(PAGE.match(/servedStatus=\{historyData\?\.status \?\? undefined\}/g)).toHaveLength(2);
    expect(PAGE.match(/<OddsChart\b/g)).toHaveLength(2);
  });
});

describe("servedBeforeFinish", () => {
  it.each([
    [{ status: "live", completed_at: null }, true],
    [{ status: "scheduled" }, true],
    [{ status: "suspended", completed_at: null }, true],
    [{ status: "live", completed_at: "2026-10-28T19:56:54Z" }, false],
    [{ status: "completed", completed_at: "2026-10-28T19:56:54Z" }, false],
    [{ status: "completed", completed_at: null }, false],
    [{ status: "closed" }, false],
    [{ status: undefined }, false],
    [{ status: null }, false],
    [null, false],
    [undefined, false],
  ])("%j -> %s", (served, expected) => {
    expect(servedBeforeFinish(served)).toBe(expected);
  });
});
