/**
 * #11296 / #2920 / #9483 — a completed soccer card and page show the recorded
 * 90-minute forecast beside the actual regulation score, labelled as such.
 *
 * Fixture: `fixtures/soccerFinal15330334.json` is the saved served detail of
 * VfB Stuttgart 1–1 Atlético Madrid (`/api/events/15330334`, 2026-10-20
 * 20:54:12Z; sha256 b5a5334ba52a…56bf), byte-for-byte. It serves `espn.period:
 * "FT"` and an admitted `pregame_projection` 1.5 / 1.9 goals, period
 * regulation, 4 sportsbooks, read 18:37–18:56Z before the 19:00Z scheduled
 * start. It predates the producer's `final_score_period` key, so it carries
 * none: as saved it is the ABSENT-key case. The positive case adds the one key
 * the frozen producer (`93844b810d`, `final_score_period()`) serves for a
 * settled soccer row whose stored period is exactly "FT" — no other field is
 * touched. Nothing here is a served-consumer result; that is owed after the
 * producer is delivered.
 *
 * Every refusal sits beside the positive that differs from it in the one field
 * under test.
 */

import React from "react";
import { renderToStaticMarkup } from "react-dom/server";

import {
  FINAL_FORECAST_LABEL,
  FINAL_FORECAST_LABEL_90_MIN,
  finalForecastComparison,
  finalScorePeriod,
} from "@/lib/finalForecastComparison";
import type { Event, FeedEventData, FeedItem } from "@/lib/types";
import SOCCER from "./fixtures/soccerFinal15330334.json";
import FIXTURE from "./fixtures/finalForecast11296.json";
import FIXTURE_2920 from "./fixtures/webProjectedFinal2920.json";

const F = FIXTURE as unknown as Record<string, unknown>;
const F2920 = FIXTURE_2920 as unknown as Record<string, unknown>;

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
  usePathname: () => "/events/15330334",
  useSearchParams: () => new URLSearchParams(),
  useParams: () => ({ id: "15330334" }),
}));

// eslint-disable-next-line @typescript-eslint/no-var-requires
const EventDetailPage = require("@/app/events/[id]/page").default;
// eslint-disable-next-line @typescript-eslint/no-var-requires
const EventCard = require("@/components/EventCard").default;
// eslint-disable-next-line @typescript-eslint/no-var-requires
const FeedCard = require("@/components/FeedCard").default;
// eslint-disable-next-line @typescript-eslint/no-var-requires
const { AnalyticsProvider } = require("@/components/Analytics");

const wrap = (el: React.ReactElement) =>
  renderToStaticMarkup(React.createElement(AnalyticsProvider, null, el));

function page(ev: Event): string {
  eventPayload = ev;
  historyPayload = { aggregate_line: [], pm_spread_data: { projected_final: null } };
  return wrap(React.createElement(EventDetailPage, { params: { id: String(ev.id) } }));
}
const card = (e: Event) => wrap(React.createElement(EventCard, { event: e }));
const feed = (i: FeedItem) => wrap(React.createElement(FeedCard, { item: i }));

/** The saved served bytes, as saved (no `final_score_period`). */
const saved = (patch: Partial<Event> = {}): Event =>
  ({ ...(SOCCER as unknown as Event), ...patch }) as Event;
/** The same row as the frozen producer serves it after a full-time finish. */
const fullTime = (patch: Partial<Event> = {}): Event =>
  saved({ final_score_period: "regulation", ...patch });

/** The 49ers v Commanders feed row's shape, carrying this soccer final's served fields. */
function feedItem(ev: Event): FeedItem {
  const base = F2920.feed_item_14780563 as FeedItem;
  const data = base.data as FeedEventData;
  return {
    ...base,
    data: {
      ...data,
      id: ev.id,
      sport: ev.sport,
      home_team: ev.home_team,
      away_team: ev.away_team,
      home_team_data: ev.home_team_data,
      away_team_data: ev.away_team_data,
      commence_time: ev.commence_time,
      status: ev.status,
      home_score: ev.home_score,
      away_score: ev.away_score,
      pregame_projection: ev.pregame_projection,
      final_score_period: ev.final_score_period,
    } as FeedEventData,
  } as FeedItem;
}

function stamp(html: string, testId: string): string | null {
  const m = html.match(new RegExp(`data-testid="${testId}" data-projected-final="(\\d+)-(\\d+)" data-projected-order="([a-z-]+)"`));
  return m ? `${m[1]}-${m[2]} ${m[3]}` : null;
}

function bandLabel(html: string, testId: string): { cls: string; text: string } | null {
  const at = html.indexOf(`data-testid="${testId}"`);
  if (at < 0) return null;
  const m = html.slice(at).match(/<span class="([^"]*)"[^>]*>([^<]*)<\/span>/);
  return m ? { cls: m[1], text: m[2] } : null;
}

const HERO = "event-hero-final-forecast";
const DETAILS = "event-hero-final-forecast-details";
const ANY_BAND_LABEL = /before scheduled start/i;

const surfaces: Array<[string, (e: Event) => string, string, string]> = [
  ["headline", page, HERO, "2-2 home-away"],
  ["EventCard", card, "event-card-final-forecast", "2-2 home-away"],
  ["FeedCard", (e) => feed(feedItem(e)), "feed-card-final-forecast", "2-2 away-home"],
];

describe("the fixture is what production served", () => {
  it("a completed 1–1 soccer final, FT, with an admitted 90-minute forecast and no period key", () => {
    const s = saved();
    expect([s.id, s.sport, s.status, s.home_team, s.home_score, s.away_team, s.away_score]).toEqual([
      15330334, "soccer_uefa_champs_league", "completed", "VfB Stuttgart", 1, "Atlético Madrid", 1,
    ]);
    expect((s.espn as { period?: string }).period).toBe("FT");
    expect(s.pregame_projection).toMatchObject({
      projected_home_score: 1.5,
      projected_away_score: 1.9,
      unit: "goals",
      period: "regulation",
      bookmaker_count: 4,
      boundary_at: "2026-10-20T19:00:00+00:00",
    });
    expect("final_score_period" in (SOCCER as object)).toBe(false);
  });
});

describe("finalScorePeriod: what the actual score covers", () => {
  it("soccer: only the served 'regulation' admits; absent, null and anything else are null", () => {
    expect(finalScorePeriod("soccer_uefa_champs_league", "regulation")).toBe("regulation");
    for (const served of [undefined, null, "", "full_game", "Regulation", "AET", "FT", "penalties"]) {
      expect(finalScorePeriod("soccer_uefa_champs_league", served)).toBeNull();
    }
  });

  it("soccer is never full_game, whatever is served", () => {
    for (const served of [undefined, null, "regulation", "full_game"]) {
      expect(finalScorePeriod("soccer_epl", served)).not.toBe("full_game");
    }
  });

  it("football and basketball stay full_game, and ignore a served soccer key", () => {
    for (const sport of ["americanfootball_nfl", "americanfootball_ncaaf", "basketball_nba"]) {
      for (const served of [undefined, null, "regulation"]) {
        expect(finalScorePeriod(sport, served)).toBe("full_game");
      }
    }
  });

  it("sports with no projected-final format answer null (the rule refuses them anyway)", () => {
    for (const sport of ["icehockey_nhl", "baseball_mlb", "tennis_atp_us_open", null, undefined, ""]) {
      expect(finalScorePeriod(sport, "regulation")).toBeNull();
    }
  });
});

describe("the rule's label says the 90-minute basis at the comparison", () => {
  it("soccer with regulation evidence: the 90-minute label, rounded 2–2 as the card rounds", () => {
    const s = fullTime();
    const out = finalForecastComparison({
      sportKey: s.sport,
      status: s.status,
      homeScore: s.home_score,
      awayScore: s.away_score,
      actualPeriod: finalScorePeriod(s.sport, s.final_score_period),
      projection: s.pregame_projection,
    });
    expect(out?.label).toBe(FINAL_FORECAST_LABEL_90_MIN);
    expect(out?.label).toBe("Projection (90 min) before scheduled start");
    expect(out?.forecast).toEqual({ home: 2, away: 2 });
    expect(out?.details.bookmakerCount).toBe(4);
  });

  it("the 90-minute label keeps the band's meaning: a projection, before the SCHEDULED start", () => {
    expect(FINAL_FORECAST_LABEL_90_MIN).toMatch(/^Projection\b/);
    expect(FINAL_FORECAST_LABEL_90_MIN).toMatch(/\bbefore scheduled start$/);
    expect(FINAL_FORECAST_LABEL_90_MIN).not.toMatch(/kick-?off|actual|regulation/i);
  });
});

describe("positive: Stuttgart 1–1 Atlético after a full-time finish", () => {
  it.each(surfaces)("%s prints the 90-minute band, in its own team order", (_n, render, id, want) => {
    const html = render(fullTime());
    expect(stamp(html, id)).toBe(want);
    expect(bandLabel(html, id)?.text).toBe("Projection (90 min) before scheduled start");
    expect(html).not.toContain(`>${FINAL_FORECAST_LABEL}<`);
  });

  it.each(surfaces)("%s: the longer label wraps in the same capped box, same size, never cut", (_n, render, id) => {
    const cls = bandLabel(render(fullTime()), id)!.cls.split(/\s+/);
    expect(cls).toContain("max-w-[8rem]");
    expect(cls).toContain("text-xs");
    for (const cut of ["truncate", "whitespace-nowrap", "text-ellipsis", "overflow-hidden"]) {
      expect(cls).not.toContain(cut);
    }
  });

  it("headline: the actual 1–1 stays the result and the band holds only the forecast", () => {
    const html = page(fullTime());
    const at = html.indexOf(`data-testid="${HERO}"`);
    const band = html.slice(at, html.indexOf(`data-testid="${DETAILS}"`, at));
    expect(band).toContain("2");
    expect(band).not.toMatch(/>1</);
    expect(band).not.toMatch(/accent-(positive|negative|success|danger|live)/);
    expect(html).toMatch(/aria-label="Projection \(90 min\) before scheduled start: [^"]+ 2, [^"]+ 2"/);
  });

  it("headline: provenance stays in the closed Details, the forecast's own (4 sportsbooks)", () => {
    const html = page(fullTime());
    const at = html.indexOf(`data-testid="${DETAILS}"`);
    expect(at).toBeGreaterThan(html.indexOf(`data-testid="${HERO}"`));
    const body = html.slice(at, html.indexOf("</details>", at));
    expect(body).toContain("4 sportsbooks");
    expect(body).toContain('data-forecast-boundary="2026-10-20T19:00:00+00:00"');
    expect(body).not.toMatch(/\bbooks?\b|bookmaker|odds.?api|espn/i);
  });

  it("card and headline print the same pair for the same game", () => {
    expect(stamp(card(fullTime()), "event-card-final-forecast")).toBe(stamp(page(fullTime()), HERO));
  });
});

describe("refused: the actual period is absent, null or not regulation", () => {
  const notRegulation: Array<[string, () => Event]> = [
    ["the saved bytes as served (no key)", () => saved()],
    ["null", () => saved({ final_score_period: null })],
    ["full_game", () => saved({ final_score_period: "full_game" as unknown as "regulation" })],
    ["AET", () => saved({ final_score_period: "AET" as unknown as "regulation" })],
    ["a shootout tally (3–2, no key)", () => saved({ home_score: 3, away_score: 2 })],
  ];

  for (const [name, ev] of notRegulation) {
    it.each(surfaces)(`${name}: %s prints no band`, (_n, render, id) => {
      const html = render(ev());
      expect(stamp(html, id)).toBeNull();
      expect(html).not.toMatch(ANY_BAND_LABEL);
    });
  }

  it("the forecast's own period is never read as the score's: regulation forecast + no key = withheld", () => {
    expect(saved().pregame_projection?.period).toBe("regulation");
    expect(stamp(page(saved()), HERO)).toBeNull();
  });

  it.each(surfaces)("a stale key on a match still in play: %s prints no final band", (_n, render, id) => {
    const html = render(fullTime({ status: "live", completed_at: null } as Partial<Event>));
    expect(stamp(html, id)).toBeNull();
  });

  it.each(surfaces)("no baseline: the key alone never makes a comparison (%s)", (_n, render, id) => {
    const html = render(fullTime({ pregame_projection: undefined, pregame_projection_unavailable: "no_pregame_reading" }));
    expect(stamp(html, id)).toBeNull();
    expect(html).not.toMatch(ANY_BAND_LABEL);
  });
});

describe("football and basketball are untouched", () => {
  const nflDetail = (patch: Partial<Event> = {}): Event =>
    ({ ...(F.detail_14966179 as Event), ...patch }) as Event;
  const nflSearch = (patch: Partial<Event> = {}): Event =>
    ({ ...(F.search_14966179 as Event), ...patch }) as Event;

  it("the served NFL final keeps its full-game band and label on the headline and the card", () => {
    const html = page(nflDetail());
    expect(stamp(html, HERO)).toBe("18-20 home-away");
    expect(bandLabel(html, HERO)?.text).toBe(FINAL_FORECAST_LABEL);
    const c = card(nflSearch());
    expect(stamp(c, "event-card-final-forecast")).toBe("18-20 home-away");
    expect(bandLabel(c, "event-card-final-forecast")?.text).toBe(FINAL_FORECAST_LABEL);
  });

  it("a stray soccer key on an NFL row changes nothing (byte-identical markup)", () => {
    expect(page(nflDetail({ final_score_period: "regulation" }))).toBe(page(nflDetail()));
    expect(card(nflSearch({ final_score_period: "regulation" }))).toBe(card(nflSearch()));
  });

  it("an NBA final still compares on full_game", () => {
    const p = { ...(F.detail_14966179 as Event).pregame_projection!, projected_home_score: 118.6, projected_away_score: 112.2 };
    const html = card(nflSearch({ sport: "basketball_nba", home_score: 112, away_score: 118, pregame_projection: p }));
    expect(stamp(html, "event-card-final-forecast")).toBe("119-112 home-away");
    expect(bandLabel(html, "event-card-final-forecast")?.text).toBe(FINAL_FORECAST_LABEL);
  });
});
