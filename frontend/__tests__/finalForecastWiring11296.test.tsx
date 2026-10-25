/**
 * #11296 / #2920 / #9483 — a finished game's headline and cards show the
 * actual result with one "Projection before scheduled start" forecast band.
 *
 * Fixtures are production payloads captured 2026-10-20 02:27Z
 * (`fixtures/finalForecast11296.json`), not hand-made objects:
 *
 *   - Buccaneers 19, Steelers 26 (`/events/14966179`, NFL, final). The detail
 *     and the search row both serve `pregame_projection` 17.8 / 20.1 from 21
 *     sportsbooks, recorded 16:29–16:59Z before the 17:00Z scheduled start.
 *   - Kings 1, Bruins 4 (15331169, NHL, final): served
 *     `pregame_projection_unavailable: "format_unsupported"`, no projection.
 *
 * The rule (`lib/finalForecastComparison.ts`) is reviewed and tested on its
 * own; this file proves the three surfaces read it, print it under the result
 * in the same team order, and print nothing where it refuses.
 */

import React from "react";
import { renderToStaticMarkup } from "react-dom/server";

import type { Event, FeedEventData, FeedItem } from "@/lib/types";
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
  usePathname: () => "/events/14966179",
  useSearchParams: () => new URLSearchParams(),
  useParams: () => ({ id: "14966179" }),
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

const detail = (patch: Partial<Event> = {}): Event =>
  ({ ...(F.detail_14966179 as Event), ...patch }) as Event;
const searchRow = (id: number, patch: Partial<Event> = {}): Event =>
  ({ ...(F[`search_${id}`] as Event), ...patch }) as Event;

const SERVED = (F.detail_14966179 as Event).pregame_projection!;

/** The 49ers v Commanders feed row (the only feed row on file), settled with the real NFL final's numbers. */
function finishedFeedItem(patch: Partial<FeedEventData> = {}): FeedItem {
  const base = F2920.feed_item_14780563 as FeedItem;
  return {
    ...base,
    data: {
      ...(base.data as FeedEventData),
      status: "completed",
      commence_time: SERVED.boundary_at,
      home_score: 19,
      away_score: 26,
      ...patch,
    },
  } as FeedItem;
}

function stamp(html: string, testId: string): string | null {
  const m = html.match(new RegExp(`data-testid="${testId}" data-projected-final="(\\d+)-(\\d+)" data-projected-order="([a-z-]+)"`));
  return m ? `${m[1]}-${m[2]} ${m[3]}` : null;
}

const HERO = "event-hero-final-forecast";
/** Either wording of the band's label, old or new: a refusal prints neither. */
const ANY_BAND_LABEL = /before scheduled start/i;

/** The label span a band prints first: its classes and text. */
function bandLabel(html: string, testId: string): { cls: string; text: string } | null {
  const at = html.indexOf(`data-testid="${testId}"`);
  if (at < 0) return null;
  const m = html.slice(at).match(/<span class="([^"]*)"[^>]*>([^<]*)<\/span>/);
  return m ? { cls: m[1], text: m[2] } : null;
}
const DETAILS = "event-hero-final-forecast-details";

describe("the fixtures are what production served", () => {
  it("the NFL final carries the producer's object; the NHL final carries only its refusal", () => {
    const d = F.detail_14966179 as Event;
    expect([d.status, d.home_team, d.home_score, d.away_team, d.away_score]).toEqual([
      "completed", "Tampa Bay Buccaneers", 19, "Pittsburgh Steelers", 26,
    ]);
    expect(SERVED).toMatchObject({
      projected_home_score: 17.8,
      projected_away_score: 20.1,
      kind: "last_before_scheduled_start",
      boundary: "scheduled_start",
      source: "sportsbooks",
      basis: "consensus_spread_total",
      bookmaker_count: 21,
      unit: "points",
      period: "full_game",
    });
    expect((F.search_14966179 as Event).pregame_projection).toEqual(SERVED);
    const nhl = F.search_15331169 as Event;
    expect([nhl.sport, nhl.status, nhl.pregame_projection]).toEqual(["icehockey_nhl", "completed", undefined]);
    expect(nhl.pregame_projection_unavailable).toBe("format_unsupported");
  });
});

describe("the finished headline, Buccaneers 19 – Steelers 26", () => {
  it("prints the named band, home first like the columns, rounded as the card rounds", () => {
    const html = page(detail());
    expect(stamp(html, HERO)).toBe("18-20 home-away");
    expect(html).toContain(">Projection before scheduled start<");
    expect(html).toMatch(/aria-label="Projection before scheduled start: [^"]+ 18, [^"]+ 20"/);
  });

  it("keeps the actual result primary: both real scores still print, and no second score table", () => {
    const html = page(detail());
    expect(html).toMatch(/>19<\/span>/);
    expect(html).toMatch(/>26<\/span>/);
    // The band holds the forecast only — never the actual pair again.
    const at = html.indexOf(`data-testid="${HERO}"`);
    const band = html.slice(at, html.indexOf(`data-testid="${DETAILS}"`, at));
    expect(band).not.toMatch(/>19<|>26</);
  });

  it("sits under the settled result, never the pre-game 'Projected final' line", () => {
    const html = page(detail());
    expect(stamp(html, "event-hero-projected-final")).toBeNull();
    expect(html).not.toContain(">Projected final<");
    expect(html).not.toContain("Pregame projection");
  });

  it("does not grade the forecast: no win/loss colour on the band", () => {
    const html = page(detail());
    const at = html.indexOf(`data-testid="${HERO}"`);
    const band = html.slice(at, html.indexOf(`data-testid="${DETAILS}"`, at));
    expect(band).toContain("text-text-primary");
    expect(band).not.toMatch(/accent-(positive|negative|success|danger|live)/);
  });

  it("puts source, recorded range and scheduled start in a closed Details, not the headline", () => {
    const html = page(detail());
    const at = html.indexOf(`data-testid="${DETAILS}"`);
    expect(at).toBeGreaterThan(html.indexOf(`data-testid="${HERO}"`));
    const open = html.lastIndexOf("<details", at);
    const tag = html.slice(open, html.indexOf(">", at));
    expect(tag).not.toMatch(/\sopen(=|\s|>)/);
    expect(tag).toContain(`data-forecast-earliest="${SERVED.earliest_captured_at}"`);
    expect(tag).toContain(`data-forecast-latest="${SERVED.latest_captured_at}"`);
    expect(tag).toContain(`data-forecast-boundary="${SERVED.boundary_at}"`);
    const body = html.slice(at, html.indexOf("</details>", at));
    expect(body).toContain("21 sportsbooks");
    expect(body).toContain("Lines recorded");
    expect(body).toContain("Scheduled start");
    expect(body).not.toMatch(/\bbooks?\b|bookmaker/i);
  });

  it("closed is a final too (the canonical finished predicate)", () => {
    expect(stamp(page(detail({ status: "closed" })), HERO)).toBe("18-20 home-away");
  });

  it("an older payload without the key prints nothing in its place", () => {
    const { pregame_projection: _drop, ...rest } = detail();
    const html = page(rest as Event);
    expect(stamp(html, HERO)).toBeNull();
    expect(html).not.toContain(DETAILS);
    expect(html).not.toMatch(ANY_BAND_LABEL);
  });
});

describe("refusals reach the headline", () => {
  it("hockey: the served NHL final has no projection and prints no band", () => {
    const nhl = searchRow(15331169);
    const html = page(
      detail({
        id: nhl.id,
        sport: nhl.sport,
        home_team: nhl.home_team,
        away_team: nhl.away_team,
        home_score: nhl.home_score,
        away_score: nhl.away_score,
        home_team_data: undefined,
        away_team_data: undefined,
        pregame_projection: undefined,
        pregame_projection_unavailable: "format_unsupported",
      } as Partial<Event>),
    );
    expect(stamp(html, HERO)).toBeNull();
    expect(html).not.toMatch(ANY_BAND_LABEL);
  });

  it("hockey: even a projection object on an NHL final prints nothing", () => {
    const html = page(
      detail({
        sport: "icehockey_nhl",
        home_team: "Los Angeles Kings",
        away_team: "Boston Bruins",
        home_team_data: undefined,
        away_team_data: undefined,
        home_score: 1,
        away_score: 4,
        pregame_projection: { ...SERVED, unit: "goals", projected_home_score: 3.4, projected_away_score: 2.1 },
      } as Partial<Event>),
    );
    expect(stamp(html, HERO)).toBeNull();
  });

  it("soccer: a 90-minute forecast is withheld under a scoreboard final", () => {
    const html = page(
      detail({
        sport: "soccer_epl",
        home_team: "Leeds United",
        away_team: "Manchester United",
        home_team_data: undefined,
        away_team_data: undefined,
        home_score: 1,
        away_score: 1,
        pregame_projection: { ...SERVED, unit: "goals", period: "regulation", projected_home_score: 1.2, projected_away_score: 1.5 },
      } as Partial<Event>),
    );
    expect(stamp(html, HERO)).toBeNull();
  });

  it("a game still in play prints no final band, whatever the payload carries", () => {
    const html = page(detail({ status: "live", completed_at: null } as Partial<Event>));
    expect(stamp(html, HERO)).toBeNull();
  });
});

describe("the cards", () => {
  it("EventCard (search/league): the served NFL final prints the band beneath its result, home first", () => {
    const html = card(searchRow(14966179));
    expect(stamp(html, "event-card-final-forecast")).toBe("18-20 home-away");
    expect(html).toContain(">Projection before scheduled start<");
    expect(html).not.toContain(">Projected final<");
    // The score strip still prints the actual result, above the band.
    const band = html.indexOf('data-testid="event-card-final-forecast"');
    expect(html.indexOf(">19<")).toBeGreaterThan(-1);
    expect(html.indexOf(">19<")).toBeLessThan(band);
    expect(html.indexOf(">26<")).toBeLessThan(band);
  });

  it("EventCard: the served NHL final prints no band", () => {
    const html = card(searchRow(15331169));
    expect(stamp(html, "event-card-final-forecast")).toBeNull();
    expect(html).not.toMatch(ANY_BAND_LABEL);
  });

  it("card and headline print the same pair for the same game", () => {
    expect(stamp(card(searchRow(14966179)), "event-card-final-forecast")).toBe(
      stamp(page(detail()), HERO),
    );
  });

  it("FeedCard: away first like its rows, once the feed carries the key", () => {
    const html = feed(finishedFeedItem({ pregame_projection: SERVED } as Partial<FeedEventData>));
    expect(stamp(html, "feed-card-final-forecast")).toBe("18-20 away-home");
    expect(html).toMatch(/aria-label="Projection before scheduled start: [^"]+ 20, [^"]+ 18"/);
  });

  it("FeedCard: as `/api/feed` serves today (no key), nothing prints", () => {
    const html = feed(finishedFeedItem());
    expect(stamp(html, "feed-card-final-forecast")).toBeNull();
    expect(html).not.toMatch(ANY_BAND_LABEL);
  });
});

describe("the longer label wraps inside its band (Design R1)", () => {
  // Measured in headless Chromium on the system font (lane1 artifact
  // 11296-r1-label): "Before scheduled start" is ~132px on one line and
  // "Projection before scheduled start" ~193px. Capped at 8rem (128px) the
  // new label breaks as "Projection before / scheduled start", so neither
  // the card's numbers nor the headline's team columns lose room they had.
  // A class read cannot see geometry; it pins the decision so a revert is loud.
  const bands: Array<[string, () => string, string]> = [
    ["headline", () => page(detail()), HERO],
    ["EventCard", () => card(searchRow(14966179)), "event-card-final-forecast"],
    [
      "FeedCard",
      () => feed(finishedFeedItem({ pregame_projection: SERVED } as Partial<FeedEventData>)),
      "feed-card-final-forecast",
    ],
  ];

  it.each(bands)("%s: the full label, never the old standalone one", (_name, render, id) => {
    const html = render();
    expect(bandLabel(html, id)?.text).toBe("Projection before scheduled start");
    expect(html).not.toContain(">Before scheduled start<");
  });

  it.each(bands)("%s: capped so it wraps, at the same size, never cut", (_name, render, id) => {
    const cls = bandLabel(render(), id)!.cls.split(/\s+/);
    expect(cls).toContain("max-w-[8rem]");
    expect(cls).toContain("text-xs");
    for (const cut of ["truncate", "whitespace-nowrap", "text-ellipsis", "overflow-hidden"]) {
      expect(cls).not.toContain(cut);
    }
    expect(cls.some((c) => /^line-clamp-/.test(c) || /^text-\[/.test(c))).toBe(false);
  });

  it.each(bands)("%s: the numbers keep their own uncapped box after the label", (_name, render, id) => {
    const html = render();
    const at = html.indexOf(`data-testid="${id}"`);
    const label = html.indexOf(">Projection before scheduled start<", at);
    const pair = html.indexOf('aria-hidden="true"', label);
    expect(label).toBeGreaterThan(at);
    expect(pair).toBeGreaterThan(label);
    const pairTag = html.slice(html.lastIndexOf("<span", pair), pair);
    expect(pairTag).toContain("font-semibold text-text-primary");
    expect(pairTag).not.toContain("max-w-");
  });

  it("the pre-game line keeps its own label, uncapped", () => {
    // #2920's specimen before play: the feed row with the producer's pair.
    const base = F2920.feed_item_14780563 as FeedItem;
    const data = base.data as FeedEventData;
    const html = feed({
      ...base,
      data: {
        ...data,
        commence_time: new Date(Date.now() + 3 * 3600_000).toISOString(),
        current_odds: { ...data.current_odds!, projected_home_score: 29.6, projected_away_score: 22.3 },
      },
    } as FeedItem);
    expect(stamp(html, "feed-card-projected-final")).toBe("30-22 away-home");
    expect(bandLabel(html, "feed-card-projected-final")?.text).toBe("Projected final");
    expect(bandLabel(html, "feed-card-projected-final")!.cls.split(/\s+/)).not.toContain("max-w-[8rem]");
    expect(html).not.toMatch(ANY_BAND_LABEL);
  });

  // lane1b R1 on 32cfa31c49: soccer's pre-game label is ~136px on one line,
  // wider than the 8rem cap, so a cap on every label broke "Projected final
  // (90 min)" across two lines on EPL/MLS cards and headlines that fit before.
  // The production EPL search row (Leeds v Manchester United, 15315510, served
  // 1.2 / 1.2 from 11 sportsbooks), set before play as #2920's cards test does.
  const eplBeforePlay = (): Event =>
    ({
      ...(F2920.search_15315510 as Event),
      status: "scheduled",
      commence_time: new Date(Date.now() + 3 * 3600_000).toISOString(),
      home_score: null,
      away_score: null,
    }) as Event;

  it.each([
    ["EventCard", () => card(eplBeforePlay()), "event-card-projected-final"],
    ["headline", () => page(eplBeforePlay()), "event-hero-projected-final"],
  ] as Array<[string, () => string, string]>)(
    "soccer before play (%s): \"Projected final (90 min)\" prints uncapped",
    (_name, render, id) => {
      const html = render();
      expect(stamp(html, id)).toBe("1-1 home-away");
      const label = bandLabel(html, id)!;
      expect(label.text).toBe("Projected final (90 min)");
      expect(label.cls.split(/\s+/)).not.toContain("max-w-[8rem]");
      expect(label.cls.split(/\s+/)).toContain("text-xs");
      expect(html).not.toMatch(ANY_BAND_LABEL);
    },
  );
});
