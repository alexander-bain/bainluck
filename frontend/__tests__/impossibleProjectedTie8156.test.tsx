// #8156 — A LIVE MLB HERO STOPS PRINTING A FINAL SCORE THE SPORT CANNOT PRODUCE.
//
// ── WHAT THE READER SAW ──────────────────────────────────────────────────────
//
// `/events/15316961` (Padres @ Dodgers, `status='live'`, score frozen at 0 – 0,
// Bottom 2nd), 390px, anonymous, production 2026-09-23. Two `tools/look.sh`
// frames of the same page four minutes apart, with nothing happening in the
// game:
//
//     02:39Z    54% – 46% Dodgers      Projected final: 3 – 3
//     02:43Z    55% – 45% Dodgers      Projected final: 4 – 3
//
// and the payload between them carried `{"home_score": 2.5, "away_score": 3.5}`,
// which renders `Projected final: 3 – 4` — the PADRES winning, under a hero
// naming the Dodgers. Three outcomes in four minutes.
//
// Only one of those three is this file's subject. `3 – 3` is not a poor
// estimate, it is an IMPOSSIBLE one: MLB has no ties, and the card stated a
// final score the sport cannot produce directly beneath its own "someone wins"
// probability.
//
// ── WHERE THE IMPOSSIBILITY IS MANUFACTURED ──────────────────────────────────
//
// In the render, not the payload. `Math.round` is applied to each side of the
// pair independently, so ANY pair less than a run apart collapses onto one
// integer — `2.9 / 3.1` prints `3 – 3`. The served value is faithful to the
// books; the tie is ours. On this one event's own history that was 17 of 164
// projection rows (10.4%), all of them in the near-pick'em window where a large
// share of live baseball sits.
//
// ── WHAT THIS FIX IS NOT ─────────────────────────────────────────────────────
//
// It is not the jitter. The underlying pair moves every minute because it is a
// single minute's bookmaker sample (median 2 books, favourite flipping 13 times
// across the event's own rows) — that is #5455's single-row read, `area:backend`,
// and nothing here stabilises it. This is the render half, and it stands alone:
// after it, the same jittering payload can print a wrong-but-possible winner,
// never an impossible scoreline.
//
// ── WHAT MUST NOT MOVE, AND IS ASSERTED BELOW ────────────────────────────────
//
// A gate that simply deleted the projection, or deleted every level pair in
// every sport, would satisfy the ship assertion. So each control is
// load-bearing:
//
//   * A NON-TIED MLB PAIR STILL PROJECTS. The feature is unharmed on the sport
//     the defect was photographed on — the gate reads the PAIR, not the sport.
//   * SOCCER KEEPS ITS LEVEL PROJECTION. A draw is a real football result; a
//     gate that suppressed `1 – 1` would be deleting the truth.
//   * THE NFL KEEPS ITS LEVEL PROJECTION. This is the arm that separates
//     `canEndInATie` from `winnerMarketPricesADraw`: an NFL moneyline is
//     two-sided and pushes on a tie, yet a regular-season game really can end
//     level. The rule is about impossible results, not unlikely ones, and
//     writing the gate against the existing draw field would have failed here
//     and passed everything else in this file.
//   * THE ROUNDING IS THE TEST, NOT THE RAW PAIR. `2.9 / 3.1` is not a tie in
//     the payload and IS one on the screen. A gate comparing the served floats
//     passes every other arm here and leaves the photographed defect live.
//   * THE PAGE STILL DRAWS. The failure mode of a suppression is a card that
//     reads as failed-to-load, which would pass the ship assertion for the
//     wrong reason.

import React from "react";
import { renderToStaticMarkup } from "react-dom/server";

const PROJECTION = "Projected final";

function event(overrides: Record<string, unknown> = {}) {
  return {
    id: 15316961,
    sport_key: "baseball_mlb",
    sport: "baseball_mlb",
    sport_title: "MLB",
    home_team: "Los Angeles Dodgers",
    away_team: "San Diego Padres",
    // The specimen's own state: live, scoreless, and the score PAIR present —
    // so #5697's gate is satisfied and this file is testing its own rule.
    home_score: 0,
    away_score: 0,
    status: "live",
    commence_time: new Date(Date.now() - 40 * 60 * 1000).toISOString(),
    win_probability_sources: {},
    ...overrides,
  };
}

function history(home: number, away: number) {
  return {
    aggregate_line: [],
    pm_spread_data: { projected_final: { home_score: home, away_score: away } },
  };
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
  usePathname: () => "/events/15316961",
  useSearchParams: () => new URLSearchParams(),
  useParams: () => ({ id: "15316961" }),
}));

// eslint-disable-next-line @typescript-eslint/no-var-requires
const EventDetailPage = require("@/app/events/[id]/page").default;
// eslint-disable-next-line @typescript-eslint/no-var-requires
const { AnalyticsProvider } = require("@/components/Analytics");

function draw(): string {
  return renderToStaticMarkup(
    React.createElement(
      AnalyticsProvider,
      null,
      React.createElement(EventDetailPage, { params: { id: "15316961" } }),
    ),
  );
}

beforeEach(() => {
  eventPayload = event();
  historyPayload = history(3.1, 2.9);
});

describe("#8156 an impossible projected final is not printed", () => {
  it("prints no projected final when the rounded MLB pair is a tie", () => {
    // The photographed frame: 3.1 / 2.9 rounds to `3 – 3`, a scoreline MLB
    // cannot produce.
    historyPayload = history(3.1, 2.9);

    const html = draw();

    // The ship.
    expect(html).not.toContain(PROJECTION);
    // NON-VACUITY. A suppression whose real effect is a blank card would pass
    // the line above. This is the specimen's own hero, still drawn.
    expect(html).toContain("Dodgers");
    expect(html).toContain("Padres");
    expect(html.length).toBeGreaterThan(2000);
  });

  it("prints no projected final when the served pair is exactly level", () => {
    // The same claim arriving without any help from the rounding.
    historyPayload = history(3, 3);

    expect(draw()).not.toContain(PROJECTION);
  });

  it("puts the impossible scoreline nowhere on the page, under any label", () => {
    // The arms above read the label. This one reads the SCORELINE itself, in
    // the exact glyphs the hero renders it with (thin spaces around an en
    // dash), so a "fix" that merely renamed the line would fail here.
    //
    // ⚠️ THE SEPARATOR IS WRITTEN AS ESCAPES ON PURPOSE. The hero renders the
    // pair with `{"\u2009\u2013\u2009"}`; the pretty ASCII form `3 - 3` never appears
    // in the markup, so an assertion spelled that way could not fail and would
    // be a decoration.
    //
    // Notice 34 is the other half of the same assertion: the space is left
    // empty and not explained, so no apology takes the scoreline's place.
    historyPayload = history(3.1, 2.9);

    const html = draw();

    expect(html).not.toContain("3\u2009\u2013\u20093");
    expect(html).not.toContain("too close");
  });

  // ── controls: everywhere the projection was right, it survives ─────────────

  it("still projects an MLB pair that rounds apart", () => {
    // The gate reads the PAIR. Baseball itself is not suppressed.
    historyPayload = history(4.2, 2.8);

    expect(draw()).toContain(PROJECTION);
  });

  it("still projects an MLB pair that is under a run apart but rounds apart", () => {
    // 3.6 / 2.6 is 1.0 apart in the payload and rounds to `4 – 3`. The gate
    // asks what the READER will see, not how wide the served pair is, so a
    // version written as "suppress anything under a run apart" — the natural
    // paraphrase of the mechanism — would wrongly fail here.
    historyPayload = history(3.6, 2.6);

    expect(draw()).toContain(PROJECTION);
  });

  it("still projects a level soccer pair — a draw is a real result", () => {
    eventPayload = event({
      sport: "soccer_usa_mls",
      sport_key: "soccer_usa_mls",
      sport_title: "MLS",
      home_team: "LA Galaxy",
      away_team: "Seattle Sounders",
    });
    historyPayload = history(1.1, 0.9);

    expect(draw()).toContain(PROJECTION);
  });

  it("still projects a level NFL pair — rare is not impossible", () => {
    // THE ARM THAT SEPARATES THIS FIELD FROM `winnerMarketPricesADraw`. The NFL
    // moneyline is two-sided and pushes on a tie, so the existing draw field
    // reads `false` here; a regular-season game level after overtime is still a
    // recorded tie. A gate written against the draw field fails exactly this
    // arm and passes every other one in the file.
    eventPayload = event({
      sport: "americanfootball_nfl",
      sport_key: "americanfootball_nfl",
      sport_title: "NFL",
      home_team: "Green Bay Packers",
      away_team: "Chicago Bears",
      home_score: 7,
      away_score: 7,
    });
    historyPayload = history(23.6, 24.2);

    expect(draw()).toContain(PROJECTION);
  });

  it("still projects a scheduled MLB game whose pair rounds apart", () => {
    // #5697's control, re-asserted from this file so a tie gate written into
    // the wrong predicate cannot quietly take the pre-game case with it.
    eventPayload = event({
      status: "scheduled",
      home_score: null,
      away_score: null,
      commence_time: new Date(Date.now() + 3 * 60 * 60 * 1000).toISOString(),
    });
    historyPayload = history(5.1, 3.4);

    expect(draw()).toContain(PROJECTION);
  });
});
