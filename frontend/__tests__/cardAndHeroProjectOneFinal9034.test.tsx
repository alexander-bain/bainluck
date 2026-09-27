/**
 * #9034 — one game, one projected final.
 *
 * WHAT A READER SAW. Production 2026-09-27 03:25Z, 390px: Dolphins v Chiefs
 * (`/events/14781701`, kickoff 17:00Z). The search card read `Proj 18-29`; the
 * event page one tap later read `Projected final: 17 – 28`. The card rounded
 * `current_odds` (17.5 / 28.7, 21 sportsbooks); the hero rounded `/history`'s
 * `pm_spread_data.projected_final` (17.2 / 27.6, Kalshi).
 *
 * THE RULE. Before kickoff the page prints the card's pair — the card cannot
 * read `/history`, so the pair both can read is the sportsbooks'. Live, the
 * card prints no projection and the page keeps the ladders' pair.
 *
 * Fixture: the specimen's own search row (shared with #9006's file), with
 * `commence_time` moved into the future so the pre-game arms cannot be decided
 * by the clock; the ladder pair is the issue's 17.2 / 27.6.
 */

import React from "react";
import { renderToStaticMarkup } from "react-dom/server";

import type { Event } from "@/lib/types";
import FIXTURE from "./fixtures/fightCardPrintsNoProjectedScore9006.json";

const SPECIMEN = (FIXTURE as unknown as Record<string, Event>)["14781701"];
const SEP = " – ";
const LADDER = { home_score: 17.2, away_score: 27.6 };

function event(patch: Partial<Event> = {}, odds: Record<string, unknown> = {}): Event {
  return {
    ...SPECIMEN,
    commence_time: new Date(Date.now() + 14 * 3600_000).toISOString(),
    win_probability_sources: {},
    ...patch,
    current_odds: { ...SPECIMEN.current_odds, ...odds } as Event["current_odds"],
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
  usePathname: () => "/events/14781701",
  useSearchParams: () => new URLSearchParams(),
  useParams: () => ({ id: "14781701" }),
}));

// eslint-disable-next-line @typescript-eslint/no-var-requires
const EventDetailPage = require("@/app/events/[id]/page").default;
// eslint-disable-next-line @typescript-eslint/no-var-requires
const EventCard = require("@/components/EventCard").default;
// eslint-disable-next-line @typescript-eslint/no-var-requires
const { AnalyticsProvider } = require("@/components/Analytics");

function page(ev: Event, ladder: unknown = LADDER): string {
  eventPayload = ev;
  historyPayload = { aggregate_line: [], pm_spread_data: { projected_final: ladder } };
  return renderToStaticMarkup(
    React.createElement(
      AnalyticsProvider,
      null,
      React.createElement(EventDetailPage, { params: { id: "14781701" } }),
    ),
  );
}

function card(ev: Event): string {
  return renderToStaticMarkup(
    React.createElement(AnalyticsProvider, null, React.createElement(EventCard, { event: ev })),
  );
}

function heroPair(html: string): string | null {
  const m = html.match(/Projected final: (\d+) – (\d+)/);
  return m ? `${m[1]}-${m[2]}` : null;
}

function cardPair(html: string): string | null {
  const m = html.match(/Proj <span[^>]*>(\d+)-(\d+)</);
  return m ? `${m[1]}-${m[2]}` : null;
}

describe("#9034 — card and hero print one projected final", () => {
  it("the specimen: the card and the page print the same pair, the card's", () => {
    const ev = event();
    expect(cardPair(card(ev))).toBe("18-29");
    expect(heroPair(page(ev))).toBe("18-29");
  });

  it("the ladders' disagreeing pair is nowhere on the page before kickoff", () => {
    // Strawman against a fix that printed both: the photographed `17 – 28`
    // must be gone, not joined.
    expect(page(event())).not.toContain(`17${SEP}28`);
  });

  it("agreement holds for any disagreeing pair, not just the specimen's numbers", () => {
    const ev = event({}, { projected_home_score: 24.4, projected_away_score: 20.6 });
    expect(cardPair(card(ev))).toBe("24-21");
    expect(heroPair(page(ev, { home_score: 27.9, away_score: 16.2 }))).toBe("24-21");
  });
});

describe("#9034 — where the card prints no projection, the page keeps the ladders", () => {
  it("live: the card prints no Proj and the hero keeps the ladders' pair", () => {
    const ev = event(
      {
        status: "live",
        commence_time: new Date(Date.now() - 20 * 60_000).toISOString(),
        home_score: 3,
        away_score: 7,
      } as Partial<Event>,
    );
    expect(cardPair(card(ev))).toBeNull();
    expect(heroPair(page(ev))).toBe("17-28");
  });

  it("no sportsbook pair: the hero prints the ladders' pair, as before", () => {
    const ev = event({}, { projected_home_score: null, projected_away_score: null });
    expect(cardPair(card(ev))).toBeNull();
    expect(heroPair(page(ev))).toBe("17-28");
  });

  it("a sport whose spread is not a margin: the card prints none, the hero keeps the ladders", () => {
    const ev = event(
      {
        sport: "baseball_mlb",
        home_team: "Los Angeles Dodgers",
        away_team: "San Diego Padres",
      } as Partial<Event>,
      { projected_home_score: 4.6, projected_away_score: 3.1 },
    );
    expect(cardPair(card(ev))).toBeNull();
    expect(heroPair(page(ev, { home_score: 5.2, away_score: 3.3 }))).toBe("5-3");
  });
});
