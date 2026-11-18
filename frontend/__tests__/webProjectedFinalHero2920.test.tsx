/**
 * #2920 / #9483 — the event headline's projected final: readable, named per
 * team, directly under the chance it explains, and the same pair the cards print.
 *
 * Alex, 2026-10-19, `/events/14780563` before play: `Projected final: 30 – 22`
 * sat in 11px muted type BELOW "11 sportsbooks", two numbers tied to no team.
 * Fixture: that event's production payload, captured 22:20Z
 * (`fixtures/webProjectedFinal2920.json`), kickoff moved into the future so the
 * pre-game arms are not decided by the clock.
 */

import React from "react";
import { renderToStaticMarkup } from "react-dom/server";

import type { Event } from "@/lib/types";
import FIXTURE from "./fixtures/webProjectedFinal2920.json";

const F = FIXTURE as unknown as Record<string, unknown>;

function specimen(patch: Partial<Event> = {}, odds: Record<string, unknown> = {}): Event {
  const base = F.event_14780563 as Event;
  return {
    ...base,
    commence_time: new Date(Date.now() + 3 * 3600_000).toISOString(),
    win_probability_sources: {},
    ...patch,
    current_odds: { ...base.current_odds, ...odds } as Event["current_odds"],
  } as Event;
}

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
  usePathname: () => "/events/14780563",
  useSearchParams: () => new URLSearchParams(),
  useParams: () => ({ id: "14780563" }),
}));

// eslint-disable-next-line @typescript-eslint/no-var-requires
const EventDetailPage = require("@/app/events/[id]/page").default;
// eslint-disable-next-line @typescript-eslint/no-var-requires
const EventCard = require("@/components/EventCard").default;
// eslint-disable-next-line @typescript-eslint/no-var-requires
const { AnalyticsProvider } = require("@/components/Analytics");

function page(ev: Event, ladder: unknown = null): string {
  eventPayload = ev;
  historyPayload = { aggregate_line: [], pm_spread_data: { projected_final: ladder } };
  return renderToStaticMarkup(
    React.createElement(
      AnalyticsProvider,
      null,
      React.createElement(EventDetailPage, { params: { id: "14780563" } }),
    ),
  );
}

function card(ev: Event): string {
  return renderToStaticMarkup(
    React.createElement(AnalyticsProvider, null, React.createElement(EventCard, { event: ev })),
  );
}

function stamp(html: string, testId: string): string | null {
  const m = html.match(new RegExp(`data-testid="${testId}" data-projected-final="(\\d+)-(\\d+)" data-projected-order="([a-z-]+)"`));
  return m ? `${m[1]}-${m[2]} ${m[3]}` : null;
}

function heroStamp(html: string): string | null {
  const h = html.match(/data-projected-cell="home"[^>]*>([^<]+)<\/span>/)?.[1];
  const a = html.match(/data-projected-cell="away"[^>]*>([^<]+)<\/span>/)?.[1];
  return h && a ? `${Math.round(Number(h))}-${Math.round(Number(a))} home-away` : null;
}

const HERO = "event-hero-projected-final";

const __prevGameCard183AFlag = process.env.NEXT_PUBLIC_GAME_CARD_183A;
beforeAll(() => {
  process.env.NEXT_PUBLIC_GAME_CARD_183A = "false";
});
afterAll(() => {
  if (__prevGameCard183AFlag === undefined) {
    delete process.env.NEXT_PUBLIC_GAME_CARD_183A;
  } else {
    process.env.NEXT_PUBLIC_GAME_CARD_183A = __prevGameCard183AFlag;
  }
});

describe("the specimen headline, before play", () => {
  it("prints the Proj. column and names each number on its team row", () => {
    const html = page(specimen());
    expect(heroStamp(html)).toBe("30-22 home-away");
    expect(html).toContain(">Proj.<");
    expect(html).toContain("49ers");
    expect(html).toContain("Commanders");
  });

  it("is no longer the faint 11px provenance line", () => {
    const html = page(specimen());
    expect(html).toContain('data-projected-cell="home"');
    expect(html).not.toContain("Projected final: 30");
  });

  it("sits inside the headline immediately before each team's Chance cell", () => {
    const html = page(specimen());
    const at = html.indexOf('data-projected-cell="away"');
    expect(at).toBeGreaterThan(html.indexOf('data-testid="event-hero-probability"'));
    const chance = html.indexOf("data-hero-digits=", at);
    expect(chance).toBeGreaterThan(at);
  });

  it("is the pair the card one tap back prints", () => {
    const fromCard = stamp(card(specimen()), "event-card-projected-final");
    expect(fromCard).toBe("30-22 home-away");
    expect(heroStamp(page(specimen(), { home_score: 31.4, away_score: 19.9 }))).toBe(fromCard);
  });
});

describe("live and finished", () => {
  const live = () =>
    specimen({
      status: "live",
      commence_time: new Date(Date.now() - 30 * 60_000).toISOString(),
      home_score: 7,
      away_score: 3,
    } as Partial<Event>);

  it("live: the in-game pair prints in Proj. and never the phrase Pregame projection", () => {
    const html = page(live(), { home_score: 27.2, away_score: 19.6 });
    expect(heroStamp(html)).toBe("27-20 home-away");
    expect(html).not.toContain("Pregame projection");
  });

  it("finished: no projected final, whatever pair the payload or ladders carry", () => {
    const html = page(
      specimen({
        status: "completed",
        commence_time: new Date(Date.now() - 4 * 3600_000).toISOString(),
        completed_at: new Date(Date.now() - 600_000).toISOString(),
        home_score: 27,
        away_score: 24,
      } as Partial<Event>),
      { home_score: 27.1, away_score: 24.2 },
    );
    expect(heroStamp(html)).toBeNull();
    expect(html).not.toContain("Pregame projection");
  });
});

describe("the format rule reaches the headline's sportsbook pair", () => {
  it("hockey's puck-line pair is refused before play; with no ladders nothing prints", () => {
    const nhl = specimen(
      { sport: "icehockey_nhl", home_team: "Boston Bruins", away_team: "Buffalo Sabres", home_team_data: undefined, away_team_data: undefined } as Partial<Event>,
      { spread: -1.5, over_under: 5.5, projected_home_score: 3.5, projected_away_score: 2.0 },
    );
    expect(heroStamp(page(nhl))).toBeNull();
  });

  // lane1 R1 on 614c4e7b86: the format gate must withhold hockey's forecast
  // before play, not hand the headline the Kalshi ladders' pair instead.
  it("hockey before play prints nothing even with BOTH a sportsbook pair and a ladder pair", () => {
    const nhl = specimen(
      { sport: "icehockey_nhl", home_team: "Boston Bruins", away_team: "Buffalo Sabres", home_team_data: undefined, away_team_data: undefined } as Partial<Event>,
      { spread: -1.5, over_under: 5.5, projected_home_score: 3.5, projected_away_score: 2.0 },
    );
    // 3.6 / 2.4 rounds to 4 – 2: printable on every other gate, so only R1 withholds it.
    expect(heroStamp(page(nhl, { home_score: 3.6, away_score: 2.4 }))).toBeNull();
  });

  it("control: baseball before play keeps its ladder pair (the run line is not a margin)", () => {
    const mlb = specimen(
      { sport: "baseball_mlb", home_team: "Texas Rangers", away_team: "New York Mets", home_team_data: undefined, away_team_data: undefined } as Partial<Event>,
      { spread: -1.5, over_under: 8.5, projected_home_score: 5.0, projected_away_score: 3.5 },
    );
    expect(heroStamp(page(mlb, { home_score: 4.6, away_score: 3.2 }))).toBe("5-3 home-away");
  });

  it("soccer prints its regulation goal projection in the Proj. column", () => {
    const epl = specimen(
      { sport: "soccer_epl", home_team: "Arsenal", away_team: "Chelsea", home_team_data: undefined, away_team_data: undefined } as Partial<Event>,
      { projected_home_score: 2.1, projected_away_score: 0.9 },
    );
    const html = page(epl);
    expect(heroStamp(html)).toBe("2-1 home-away");
    expect(html).toContain(">Proj.<");
  });
});
