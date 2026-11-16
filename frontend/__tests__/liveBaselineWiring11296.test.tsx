/**
 * #11296 / #9483 — the live headline prints the retained pregame projection
 * directly beneath the current projected final.
 *
 * The base row is the production detail of Buccaneers v Steelers
 * (`/events/14966179`, `fixtures/finalForecast11296.json`), whose served
 * `pregame_projection` is 17.8 / 20.1 from 21 sportsbooks. It was captured as
 * a FINAL; here it is replayed as LIVE, with every timestamp moved by one
 * offset so the start is 90 minutes ago, and given a CONSTRUCTED
 * `current_odds.live_projection`. That makes this a synthetic control of the
 * page wiring: it is not a real live game serving both objects, and it pays
 * none of Design's real before/current acceptance.
 *
 * The rule is tested on its own (`livePregameComparison11296.test.ts`); this
 * file proves the page reads it, mounts it beneath the current line in the
 * same team order, and leaves the current forecast alone where it refuses.
 */

import React from "react";
import { renderToStaticMarkup } from "react-dom/server";

import type { Event } from "@/lib/types";
import type { PregameProjection } from "@/lib/finalForecastComparison";
import FIXTURE from "./fixtures/finalForecast11296.json";

const F = FIXTURE as unknown as Record<string, unknown>;
const SERVED_DETAIL = F.detail_14966179 as Event;
const SERVED = SERVED_DETAIL.pregame_projection!;

let eventPayload: unknown;
let historyPayload: unknown;

jest.mock("swr", () => ({
  __esModule: true,
  default: (key: unknown) => {
    const k = Array.isArray(key) ? key[0] : null;
    const data =
      k === "event" ? eventPayload : k === "history" ? historyPayload : undefined;
    return { data, error: undefined, isLoading: false, mutate: () => undefined };
  },
}));

jest.mock("@/hooks", () => ({
  ...jest.requireActual("@/hooks"),
  __esModule: true,
  usePageTracking: () => undefined,
  useScrollDepth: () => undefined,
  useEngagementTime: () => undefined,
  usePinnedEvents: () => ({
    isPinned: () => false,
    togglePin: () => undefined,
    isMaxReached: false,
  }),
}));

jest.mock("@/hooks/useLiveEventStream", () => ({
  __esModule: true,
  useLiveEventStream: () => ({ frame: null, connected: false }),
}));

jest.mock("next/navigation", () => ({
  __esModule: true,
  useRouter: () => ({ push: () => {}, replace: () => {}, prefetch: () => {} }),
  usePathname: () => "/events/14966179",
  useSearchParams: () => new URLSearchParams(),
  useParams: () => ({ id: "14966179" }),
}));

// eslint-disable-next-line @typescript-eslint/no-var-requires
const EventDetailPage = require("@/app/events/[id]/page").default;
// eslint-disable-next-line @typescript-eslint/no-var-requires
const { AnalyticsProvider } = require("@/components/Analytics");

/** Every served instant moved by one offset, so the start is 90 minutes ago. */
const SHIFT_MS = Date.now() - 90 * 60_000 - Date.parse(SERVED.boundary_at);
const shift = (iso: string) => new Date(Date.parse(iso) + SHIFT_MS).toISOString();
const START = shift(SERVED.boundary_at);

const BASELINE: PregameProjection = {
  ...SERVED,
  earliest_captured_at: shift(SERVED.earliest_captured_at),
  latest_captured_at: shift(SERVED.latest_captured_at),
  boundary_at: START,
};

/** Constructed: the producer's in-play shape, confirmed an hour after the start. */
const CURRENT = {
  projected_home_score: 22.6,
  projected_away_score: 27.1,
  kind: "in_play",
  boundary: "commence_time",
  boundary_at: START,
  earliest_confirmed_at: new Date(Date.parse(START) + 60 * 60_000).toISOString(),
  latest_captured_at: new Date(Date.parse(START) + 62 * 60_000).toISOString(),
  source: "sportsbooks",
  basis: "consensus_spread_total",
  bookmaker_count: 7,
  unit: "points",
  period: "full_game",
};

function liveRow(
  patch: Partial<Event> = {},
  liveProjection: Record<string, unknown> | null = CURRENT,
): Event {
  const odds: Record<string, unknown> = { ...SERVED_DETAIL.current_odds };
  if (liveProjection) odds.live_projection = liveProjection;
  return {
    ...SERVED_DETAIL,
    status: "live",
    completed_at: null,
    commence_time: START,
    home_score: 10,
    away_score: 13,
    win_probability_sources: {},
    pregame_projection: BASELINE,
    current_odds: odds as unknown as Event["current_odds"],
    ...patch,
  } as Event;
}

function page(ev: Event, ladder: unknown = null): string {
  eventPayload = ev;
  historyPayload = { aggregate_line: [], pm_spread_data: { projected_final: ladder } };
  return renderToStaticMarkup(
    React.createElement(
      AnalyticsProvider,
      null,
      React.createElement(EventDetailPage, { params: { id: String(ev.id) } }),
    ),
  );
}

function heroCurrentStamp(html: string): string | null {
  const h = html.match(/data-projected-cell="home"[^>]*>([^<]+)<\/span>/)?.[1];
  const a = html.match(/data-projected-cell="away"[^>]*>([^<]+)<\/span>/)?.[1];
  return h && a ? `${Math.round(Number(h))}-${Math.round(Number(a))} home-away` : null;
}

function pregameSummaryText(html: string): string | null {
  const m = html.match(
    /data-testid="headline-12472-pregame-summary"[^>]*><span[^>]*>([^<]+)<\/span>\s*<span[^>]*>([^<]+)<\/span><\/div>/,
  );
  return m ? `${m[1]}  ${m[2]}` : null;
}

const SUMMARY_ID = "headline-12472-pregame-summary";
const FINAL_BAND = "event-hero-final-forecast";

describe("a live game with both typed forecasts (Direction 199 / Ruling 200-B)", () => {
  it("prints the current pair in Proj. and the retained pregame projection in the single grey line below", () => {
    const html = page(liveRow());
    expect(heroCurrentStamp(html)).toBe("23-27 home-away");
    // Served 17.8 (Buccaneers) / 20.1 (Steelers): Steelers is the pregame favourite (20–18).
    const summary = pregameSummaryText(html);
    expect(summary).not.toBeNull();
    expect(summary).toMatch(/^Pregame  /);
    expect(summary).toContain("projected 20–18");
    expect(html.indexOf(`data-testid="${SUMMARY_ID}"`)).toBeGreaterThan(
      html.indexOf('data-projected-cell="home"'),
    );
  });

  it("keeps the grey pregame line single-line (whitespace-nowrap) and quiet (#526071)", () => {
    const html = page(liveRow());
    const at = html.indexOf(`data-testid="${SUMMARY_ID}"`);
    expect(at).toBeGreaterThan(-1);
    const tag = html.slice(html.lastIndexOf("<div", at), html.indexOf(">", at) + 1);
    expect(tag).toContain("whitespace-nowrap");
    expect(tag).toContain("#526071");
  });

  it("adds no numeric difference and no final-band markup", () => {
    const html = page(liveRow());
    expect(html).not.toContain(`data-testid="${FINAL_BAND}"`);
    expect(html).not.toMatch(/[+−-]\d+ pts/);
    expect(html).not.toContain("Projection before");
  });
});

describe("a missing or incompatible baseline omits the projected half from the grey line while leaving Proj. intact", () => {
  const currentWithoutProjectedHalf = (html: string) => {
    expect(heroCurrentStamp(html)).toBe("23-27 home-away");
    const summary = pregameSummaryText(html);
    if (summary !== null) {
      expect(summary).not.toContain("projected");
    }
  };

  it("no baseline served", () => {
    currentWithoutProjectedHalf(page(liveRow({ pregame_projection: null })));
    currentWithoutProjectedHalf(page(liveRow({ pregame_projection: undefined })));
  });

  it("the producer's refusal instead of a baseline", () => {
    currentWithoutProjectedHalf(
      page(liveRow({ pregame_projection: null, pregame_projection_unavailable: "no_pregame_reading" })),
    );
  });

  it("a baseline over the wrong period", () => {
    currentWithoutProjectedHalf(
      page(liveRow({ pregame_projection: { ...BASELINE, period: "regulation" } })),
    );
  });

  it("a baseline in the wrong unit", () => {
    currentWithoutProjectedHalf(
      page(liveRow({ pregame_projection: { ...BASELINE, unit: "goals" } })),
    );
  });

  it("a baseline read after the start", () => {
    currentWithoutProjectedHalf(
      page(
        liveRow({
          pregame_projection: {
            ...BASELINE,
            latest_captured_at: new Date(Date.parse(START) + 60_000).toISOString(),
          },
        }),
      ),
    );
  });

  it("a baseline read before a different start", () => {
    const earlier = new Date(Date.parse(START) - 3600_000).toISOString();
    currentWithoutProjectedHalf(
      page(
        liveRow({
          pregame_projection: {
            ...BASELINE,
            boundary_at: earlier,
            latest_captured_at: shift(SERVED.earliest_captured_at),
            earliest_captured_at: new Date(Date.parse(earlier) - 7200_000).toISOString(),
          },
        }),
      ),
    );
  });
});

describe("ladders and refused live_projection", () => {
  it("the ladders' in-game pair (no live_projection served) still prints in Proj.", () => {
    const html = page(liveRow({}, null), { home_score: 24.2, away_score: 26.9 });
    expect(heroCurrentStamp(html)).toBe("24-27 home-away");
  });

  it("a refused live_projection withholds Proj.", () => {
    const html = page(liveRow({}, { ...CURRENT, kind: "pregame" }), {
      home_score: 24.2,
      away_score: 26.9,
    });
    expect(heroCurrentStamp(html)).toBeNull();
  });
});

describe("existing gates still decide whether Proj. and the grey line print", () => {
  it("a current pair below the board's score withholds Proj.", () => {
    const html = page(liveRow({ home_score: 24, away_score: 13 }));
    expect(heroCurrentStamp(html)).toBeNull();
  });

  it("a live game with no score pair withholds Proj.", () => {
    const html = page(liveRow({ home_score: null, away_score: null } as Partial<Event>));
    expect(heroCurrentStamp(html)).toBeNull();
  });

  it("before play: no live pregame summary line, whatever the payload carries", () => {
    const later = new Date(Date.now() + 3 * 3600_000).toISOString();
    const html = page(
      liveRow({ status: "scheduled", commence_time: later, home_score: null, away_score: null } as Partial<Event>),
    );
    expect(pregameSummaryText(html)).toBeNull();
  });

  it("hockey: no pregame projected score in the grey line", () => {
    const html = page(
      liveRow(
        { sport: "icehockey_nhl", home_score: 1, away_score: 1 },
        { ...CURRENT, projected_home_score: 3.6, projected_away_score: 2.4 },
      ),
    );
    const summary = pregameSummaryText(html);
    if (summary !== null) {
      expect(summary).not.toContain("projected");
    }
  });
});

describe("the final path prints Pregame · Final with no live grey line", () => {
  it("the served final renders data-phase='after' with no live grey line", () => {
    const html = page(SERVED_DETAIL);
    expect(html).toContain('data-phase="after"');
    expect(pregameSummaryText(html)).toBeNull();
  });
});

describe("soccer prints regulation goals in Proj. and rounded goals in the single grey line", () => {
  it("goals over regulation on both objects: Proj. and Pregame grey line both render", () => {
    const html = page(
      liveRow(
        {
          sport: "soccer_epl",
          home_team: "Arsenal",
          away_team: "Chelsea",
          home_team_data: undefined,
          away_team_data: undefined,
          home_score: 1,
          away_score: 0,
          pregame_projection: {
            ...BASELINE,
            unit: "goals",
            period: "regulation",
            projected_home_score: 1.4,
            projected_away_score: 1.1,
          },
        } as Partial<Event>,
        {
          ...CURRENT,
          unit: "goals",
          period: "regulation",
          projected_home_score: 2.2,
          projected_away_score: 0.9,
        },
      ),
    );
    expect(heroCurrentStamp(html)).toBe("2-1 home-away");
    expect(pregameSummaryText(html)).toContain("projected 1–1");
  });
});
