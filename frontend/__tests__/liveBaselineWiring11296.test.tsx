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
    current_odds: odds as Event["current_odds"],
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

function stamp(html: string, testId: string): string | null {
  const m = html.match(new RegExp(`data-testid="${testId}" data-projected-final="(\\d+)-(\\d+)" data-projected-order="([a-z-]+)"`));
  return m ? `${m[1]}-${m[2]} ${m[3]}` : null;
}

const CURRENT_LINE = "event-hero-projected-final";
const BASE_LINE = "event-hero-live-baseline";
const BASE_DETAILS = "event-hero-live-baseline-details";
const FINAL_BAND = "event-hero-final-forecast";

describe("a live game with both typed forecasts", () => {
  it("prints the current pair first and the retained pregame pair beneath it, home first", () => {
    const html = page(liveRow());
    expect(stamp(html, CURRENT_LINE)).toBe("23-27 home-away");
    // The served 17.8 / 20.1, rounded as the card and the final band round it.
    expect(stamp(html, BASE_LINE)).toBe("18-20 home-away");
    expect(html.indexOf(`data-testid="${BASE_LINE}"`)).toBeGreaterThan(
      html.indexOf(`data-testid="${CURRENT_LINE}"`),
    );
  });

  it("is directly beneath: nothing else is drawn between the two lines", () => {
    const html = page(liveRow());
    const current = html.indexOf(`data-testid="${CURRENT_LINE}"`);
    const base = html.indexOf(`data-testid="${BASE_LINE}"`);
    const between = html.slice(current, base);
    // Only the current line's own markup: one opening group, closed before the baseline's.
    expect(between.match(/data-testid=/g)).toHaveLength(1);
  });

  it("is labelled as the projection before the scheduled start, and names both teams", () => {
    const html = page(liveRow());
    expect(html).toContain('aria-label="Projection before scheduled start: Buccaneers 18, Steelers 20"');
    expect(html).toContain('aria-label="Projected final: Buccaneers 23, Steelers 27"');
  });

  it("keeps the current forecast primary: the baseline is the secondary emphasis", () => {
    const html = page(liveRow());
    const row = (id: string) => {
      const at = html.indexOf(`data-testid="${id}"`);
      return html.slice(at, html.indexOf("</div>", at));
    };
    expect(row(CURRENT_LINE)).toContain("font-semibold text-text-primary");
    expect(row(BASE_LINE)).toContain("font-medium text-text-secondary");
    expect(row(BASE_LINE)).not.toContain("text-text-primary");
  });

  it("puts sportsbooks, recorded range and scheduled start in a closed Details", () => {
    const html = page(liveRow());
    const at = html.indexOf(`data-testid="${BASE_DETAILS}"`);
    expect(at).toBeGreaterThan(html.indexOf(`data-testid="${BASE_LINE}"`));
    const tag = html.slice(html.lastIndexOf("<details", at), at);
    expect(tag).not.toMatch(/\bopen\b/);
    expect(html).toContain(`data-forecast-boundary="${START}"`);
    expect(html.slice(at)).toContain("21 sportsbooks");
  });

  it("adds no numeric difference and no final-band markup", () => {
    const html = page(liveRow());
    expect(stamp(html, FINAL_BAND)).toBeNull();
    expect(html).not.toMatch(/[+−-]\d+ pts/);
  });
});

describe("a missing or incompatible baseline leaves the current forecast exactly as it was", () => {
  const currentOnly = (html: string) => {
    expect(stamp(html, CURRENT_LINE)).toBe("23-27 home-away");
    expect(stamp(html, BASE_LINE)).toBeNull();
    expect(html).not.toContain(`data-testid="${BASE_DETAILS}"`);
  };

  it("no baseline served", () => {
    currentOnly(page(liveRow({ pregame_projection: null })));
    currentOnly(page(liveRow({ pregame_projection: undefined })));
  });

  it("the producer's refusal instead of a baseline", () => {
    currentOnly(page(liveRow({ pregame_projection: null, pregame_projection_unavailable: "no_pregame_reading" })));
  });

  it("a baseline over the wrong period", () => {
    currentOnly(page(liveRow({ pregame_projection: { ...BASELINE, period: "regulation" } })));
  });

  it("a baseline in the wrong unit", () => {
    currentOnly(page(liveRow({ pregame_projection: { ...BASELINE, unit: "goals" } })));
  });

  it("a baseline read after the start", () => {
    currentOnly(
      page(
        liveRow({
          pregame_projection: { ...BASELINE, latest_captured_at: new Date(Date.parse(START) + 60_000).toISOString() },
        }),
      ),
    );
  });

  it("a baseline read before a different start", () => {
    const earlier = new Date(Date.parse(START) - 3600_000).toISOString();
    currentOnly(page(liveRow({ pregame_projection: { ...BASELINE, boundary_at: earlier, latest_captured_at: shift(SERVED.earliest_captured_at), earliest_captured_at: new Date(Date.parse(earlier) - 7200_000).toISOString() } })));
  });
});

describe("an untyped current source gets no baseline", () => {
  it("the ladders' in-game pair (no live_projection served) prints alone", () => {
    const html = page(liveRow({}, null), { home_score: 24.2, away_score: 26.9 });
    expect(stamp(html, CURRENT_LINE)).toBe("24-27 home-away");
    expect(stamp(html, BASE_LINE)).toBeNull();
  });

  it("a refused live_projection prints neither current nor baseline (the existing withholding)", () => {
    const html = page(liveRow({}, { ...CURRENT, kind: "pregame" }), { home_score: 24.2, away_score: 26.9 });
    expect(stamp(html, CURRENT_LINE)).toBeNull();
    expect(stamp(html, BASE_LINE)).toBeNull();
  });
});

describe("existing gates still decide whether there is a current line at all", () => {
  it("a current pair below the board's score prints nothing, and so no baseline", () => {
    const html = page(liveRow({ home_score: 24, away_score: 13 }));
    expect(stamp(html, CURRENT_LINE)).toBeNull();
    expect(stamp(html, BASE_LINE)).toBeNull();
  });

  it("a live game with no score pair prints nothing, and so no baseline", () => {
    const html = page(liveRow({ home_score: null, away_score: null } as Partial<Event>));
    expect(stamp(html, CURRENT_LINE)).toBeNull();
    expect(stamp(html, BASE_LINE)).toBeNull();
  });

  it("before play: no baseline, whatever the payload carries", () => {
    const later = new Date(Date.now() + 3 * 3600_000).toISOString();
    const html = page(liveRow({ status: "scheduled", commence_time: later, home_score: null, away_score: null } as Partial<Event>));
    expect(stamp(html, BASE_LINE)).toBeNull();
  });

  it("hockey: nothing, whatever both objects say", () => {
    const html = page(
      liveRow({ sport: "icehockey_nhl", home_score: 1, away_score: 1 }, { ...CURRENT, projected_home_score: 3.6, projected_away_score: 2.4 }),
    );
    expect(stamp(html, BASE_LINE)).toBeNull();
  });
});

describe("the final path is unchanged", () => {
  it("the served final still prints its own band, and no live baseline", () => {
    const html = page(SERVED_DETAIL);
    expect(stamp(html, FINAL_BAND)).toBe("18-20 home-away");
    expect(stamp(html, BASE_LINE)).toBeNull();
    expect(html).toContain('data-testid="event-hero-final-forecast-details"');
    expect(html).not.toContain(`data-testid="${BASE_DETAILS}"`);
  });
});

describe("soccer keeps its 90-minute basis visible on both lines", () => {
  it("goals over regulation on both objects: the label says 90 min", () => {
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
          pregame_projection: { ...BASELINE, unit: "goals", period: "regulation", projected_home_score: 1.4, projected_away_score: 1.1 },
        } as Partial<Event>,
        { ...CURRENT, unit: "goals", period: "regulation", projected_home_score: 2.2, projected_away_score: 0.9 },
      ),
    );
    expect(html).toContain('aria-label="Projected final (90 min): Arsenal 2, Chelsea 1"');
    expect(html).toContain('aria-label="Projection (90 min) before scheduled start: Arsenal 1, Chelsea 1"');
  });
});
