// UX-P114 — THE GAME CARD'S TWO NUMBERS ARE ONE ANSWER, asserted against output.
//
// The Discover event card draws the away win probability and the home win
// probability side by side under one "Win Probability" label. `routes/feed.py`
// derives the away side as `round(1.0 - current_home_prob, 6)`, so those two
// numbers are an exact complement pair BY CONSTRUCTION — and rounding them
// independently printed 101 whenever the blend landed on an exact half-percent.
//
// MEASURED on production 2026-08-21 across the 414 scheduled/live events inside
// the feed's own window, blend computed by `compute_aggregate_probability` itself:
// 34 (8.2%) printed 101. Always 101, never 99 — only an exact `.5` fractional part
// misfires, and it rounds BOTH sides up. Green Bay @ Denver read 33 + 68.
//
// ## Why this file renders instead of grepping
//
// #2060's forced lesson, one layer up. A source grep cannot tell a rendered field
// from a declared one: a mutation replacing the commence-time conditional with
// `{false && (` left every `commence_time` string intact and passed the whole
// suite. The contract suite proves `renderedDuelPercents` is RIGHT; only this file
// proves the card SHOWS it. Both are needed, and neither substitutes.
//
// Guards run BOTH directions per gotcha #43: a boundary pair is forced to 100, and
// an ordinary pair — 380 of the 414 measured events — is asserted UNCHANGED.

import React from "react";
import { renderToStaticMarkup } from "react-dom/server";

import { EventCard } from "@/components/discover/EventCard";
import type { FeedEventData, FeedItem } from "@/lib/types";

jest.mock("next/link", () => {
  const ReactLib = require("react");
  return {
    __esModule: true,
    default: ({ href, children, ...props }: { href: string; children: React.ReactNode }) =>
      ReactLib.createElement("a", { href, ...props }, children),
  };
});

// `FeedCard` (the /sports feed's card) reads the analytics context, which has no
// provider under `renderToStaticMarkup`. Stubbed rather than wrapped: this file is
// about the two numbers the card prints, and a real provider would add a second
// thing that can break these tests for reasons unrelated to their subject.
jest.mock("@/components/Analytics", () => ({
  useAnalyticsContext: () => ({ track: () => {} }),
}));

function makeData(over: Partial<FeedEventData> = {}): FeedEventData {
  return {
    id: 15200290,
    external_id: "evt-15200290",
    sport: "americanfootball_nfl",
    sport_name: "NFL",
    home_team: "Denver Broncos",
    away_team: "Green Bay Packers",
    commence_time: "2030-01-01T12:00:00.000Z",
    status: "scheduled",
    home_score: null,
    away_score: null,
    ...over,
  } as FeedEventData;
}

function makeItem(data: FeedEventData): FeedItem {
  return { type: "event", score: 50, reason: "", headline: "", data } as unknown as FeedItem;
}

function render(data: FeedEventData): string {
  return renderToStaticMarkup(
    <EventCard
      item={makeItem(data)}
      data={data}
      liked={false}
      setLiked={() => {}}
      trending={false}
    />
  );
}

/** The two percents the win-probability strip actually PRINTS, [away, home]. */
function printedPercents(data: FeedEventData): number[] {
  const html = render(data);
  const away = html.match(
    /data-testid="event-card-away-probability"[^>]*>(\d+)%/
  );
  const home = html.match(
    /data-testid="event-card-home-probability"[^>]*>(\d+)%/
  );
  if (!away || !home) {
    throw new Error(
      `the win-probability strip did not render two percents.\n${html.slice(0, 1200)}`
    );
  }
  return [Number(away[1]), Number(home[1])];
}

const withOdds = (home: number, away: number, extra: Record<string, unknown> = {}) =>
  makeData({
    current_odds: {
      captured_at: "2030-01-01T11:00:00.000Z",
      home_probability: home,
      away_probability: away,
      spread: null,
      over_under: null,
      projected_home_score: null,
      projected_away_score: null,
      ...extra,
    },
  } as Partial<FeedEventData>);

describe("the served percents are what the card prints", () => {
  // The server decides the pair. These are the exact values `feed.py` sends for
  // the specimens, so the card must print them verbatim and derive nothing.
  it.each([
    [15200290, "Green Bay Packers @ Denver Broncos", 0.675, 0.325, 32, 68],
    [15197813, "Toronto FC @ Inter Miami CF", 0.505, 0.495, 49, 51],
    [15277855, "Madison Keys @ Sara Bejlek", 0.355, 0.645, 65, 35],
    [15176690, "Lucrecia Manzur @ Amanda Serrano", 0.955, 0.045, 4, 96],
  ])("%s %s", (_id, _name, home, away, awayPct, homePct) => {
    const printed = printedPercents(
      withOdds(home, away, {
        home_rendered_percent: homePct,
        away_rendered_percent: awayPct,
      })
    );
    expect(printed).toEqual([awayPct, homePct]);
    expect(printed[0] + printed[1]).toBe(100);
  });
});

describe("a payload without the served field still sums to 100", () => {
  // The fallback arm. A Discover response is cached and this bundle can be served
  // against an older deploy, so "the backend ships it" is not "every payload has
  // it". Without a working fallback the fix is invisible for the cache's lifetime.
  it.each([
    ["Green Bay @ Denver", 0.675, 0.325, 32, 68],
    ["Toronto FC @ Inter Miami", 0.505, 0.495, 49, 51],
    ["Madison Keys @ Sara Bejlek", 0.355, 0.645, 65, 35],
    ["Hoffenheim @ Erzgebirge Aue", 0.515, 0.485, 48, 52],
  ])("%s", (_name, home, away, awayPct, homePct) => {
    const printed = printedPercents(withOdds(home, away));
    expect(printed).toEqual([awayPct, homePct]);
    expect(printed[0] + printed[1]).toBe(100);
  });

  it("the fallback agrees with the server on every specimen", () => {
    // If these two arms could disagree, the card would change its answer when a
    // cache expired — the drift the shared contract exists to make impossible.
    for (const [home, away, awayPct, homePct] of [
      [0.675, 0.325, 32, 68],
      [0.505, 0.495, 49, 51],
      [0.355, 0.645, 65, 35],
      [0.955, 0.045, 4, 96],
      [0.515, 0.485, 48, 52],
    ] as const) {
      expect(printedPercents(withOdds(home, away))).toEqual(
        printedPercents(
          withOdds(home, away, {
            home_rendered_percent: homePct,
            away_rendered_percent: awayPct,
          })
        )
      );
    }
  });
});

describe("the leave-alone direction (gotcha #43)", () => {
  it("an ordinary pair off the boundary is printed exactly as before", () => {
    // 380 of the 414 measured events are this case. A rule that moved them would
    // be changing numbers nobody complained about.
    expect(printedPercents(withOdds(0.66, 0.34))).toEqual([34, 66]);
    expect(printedPercents(withOdds(0.62, 0.38))).toEqual([38, 62]);
  });

  it("an exact coin flip stays 50 / 50", () => {
    expect(printedPercents(withOdds(0.5, 0.5))).toEqual([50, 50]);
  });

  it("the favourite keeps its own rounding — the underdog absorbs the point", () => {
    // Denver at 0.675 rounds to 68 on its own. Deriving in away-first positional
    // order would print 67 for it, moving the one number anybody checks.
    expect(printedPercents(withOdds(0.675, 0.325))[1]).toBe(68);
    // …and symmetrically when the AWAY side is favoured.
    expect(printedPercents(withOdds(0.355, 0.645))[0]).toBe(65);
  });
});

describe("the strip is absent, not wrong, when there is nothing to print", () => {
  it("a settled game renders no win-probability strip at all", () => {
    // Settled means settled: a FINAL card must not carry a live-looking split.
    const html = render(
      makeData({
        status: "completed",
        home_score: 24,
        away_score: 17,
        current_odds: {
          captured_at: "2030-01-01T11:00:00.000Z",
          home_probability: 0.675,
          away_probability: 0.325,
          spread: null,
          over_under: null,
          projected_home_score: null,
          projected_away_score: null,
        },
      } as Partial<FeedEventData>)
    );
    expect(html).not.toContain("event-card-away-probability");
  });

  it("an event with no odds renders no strip", () => {
    const html = render(makeData());
    expect(html).not.toContain("event-card-away-probability");
  });
});

describe("the sports feed's card carries the same fix", () => {
  // `components/FeedCard` is the OTHER served-feed surface that prints both
  // sides — the /sports feed's two stacked chips. It is a different component
  // with a different layout reading the same payload, so a fix to the Discover
  // card says nothing about it. Rendered here rather than grepped, for the reason
  // this whole file exists.
  const FeedCard = require("@/components/FeedCard").default;

  function feedChips(home: number, away: number, served?: [number, number]) {
    const data: any = {
      id: 15200290,
      external_id: "e-15200290",
      sport: "americanfootball_nfl",
      sport_name: "NFL",
      home_team: "Denver Broncos",
      away_team: "Green Bay Packers",
      commence_time: "2030-01-01T12:00:00.000Z",
      status: "scheduled",
      home_score: null,
      away_score: null,
      current_odds: {
        captured_at: "2030-01-01T11:00:00.000Z",
        home_probability: home,
        away_probability: away,
        spread: null,
        over_under: null,
        projected_home_score: null,
        projected_away_score: null,
        ...(served
          ? { away_rendered_percent: served[0], home_rendered_percent: served[1] }
          : {}),
      },
    };
    const html = renderToStaticMarkup(
      <FeedCard item={{ type: "event", score: 50, reason: "", headline: "", data }} />
    );
    const pcts = [...html.matchAll(/>(\d+)%</g)].map((m) => Number(m[1]));
    if (pcts.length < 2) {
      throw new Error(`the chips did not render two percents: ${pcts.join(",")}`);
    }
    return pcts.slice(0, 2); // away chip is drawn first, then home
  }

  it("prints the served pair and it sums to 100", () => {
    expect(feedChips(0.675, 0.325, [32, 68])).toEqual([32, 68]);
  });

  it("BOTH chips are covered — one of these has the AWAY side favoured", () => {
    // Necessary, and it took a planted mutation to notice. The favourite keeps
    // its own rounding by design, so on a home-favourite card the HOME chip is
    // identical with or without the fix — every case above is home-favourite, and
    // dropping the served value from the home chip passed all of them. With the
    // away side favoured the home chip is the derived one (0.355 rounds to 36 on
    // its own; the card must print 35).
    expect(feedChips(0.355, 0.645, [65, 35])).toEqual([65, 35]);
    expect(feedChips(0.355, 0.645)).toEqual([65, 35]);
  });

  it("falls back to the shared rule when the payload predates the field", () => {
    expect(feedChips(0.675, 0.325)).toEqual([32, 68]);
    expect(feedChips(0.505, 0.495)).toEqual([49, 51]);
  });

  it("leaves an ordinary pair alone", () => {
    expect(feedChips(0.62, 0.38)).toEqual([38, 62]);
  });

  it("cannot pass vacuously — the chip reader throws when nothing renders", () => {
    expect(() => feedChips(NaN, NaN)).toThrow();
  });
});

describe("this file cannot pass vacuously", () => {
  // The failure mode a render test has that a unit test does not: the component
  // silently stops rendering the thing, every regex misses, and `[].sum === 0`
  // quietly satisfies nothing. `printedPercents` throws rather than returning an
  // empty array, and this proves the throw is reachable.
  it("throws when the strip is missing rather than reporting a pass", () => {
    expect(() => printedPercents(makeData())).toThrow(
      /did not render two percents/
    );
  });

  it("reads the rendered TEXT, not the data attribute", () => {
    // The card also emits `data-rendered-percent`, which is convenient for the
    // browser rail and useless as a self-check — a component could set it
    // correctly and print something else. The regex above deliberately captures
    // the text node after `>`; this pins that it is doing so.
    const html = render(
      withOdds(0.675, 0.325, {
        home_rendered_percent: 68,
        away_rendered_percent: 32,
      })
    );
    expect(html).toMatch(
      /data-testid="event-card-home-probability"[^>]*>68%<\/span>/
    );
  });
});
