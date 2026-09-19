/**
 * #4797 — the shared card stops printing "No price yet" over a price its own
 * payload carries.
 *
 * WHAT A READER SAW. `https://bainluck.com/search?q=chiefs`, 2026-09-19, one
 * screenshot, no scrolling between the two: the GAMES card for `15313996`
 * Lamontville Golden Arrows v Kaizer Chiefs printed `No price yet`, and the
 * ANSWERS card ~400px below it printed `Kaizer Chiefs 47%` for the same
 * fixture. The page disagreeing with itself, not a number merely missing.
 *
 * THE MECHANISM, measured twice (lane1/233 on 2026-09-10, lane1b/387 on
 * 2026-09-19) and re-measured here. Nothing is wrong in the backend: the search
 * payload for that row carries
 *
 *     hero_probability          0.225
 *     hero_probability_away     null
 *     hero_probability_source   "blend"
 *     win_probability_sources   {"polymarket": {"value": 0.225, "evidence_status": "verified", ...}}
 *     current_odds              absent
 *     opening_odds              absent
 *
 * and `EventCard` read `current_odds` and nothing else. No sportsbook ever
 * priced the fixture, so both sides came out null, `noReading` fired, and the
 * #2882 no-reading chrome printed over a served, verified price. 20 of 146 rows
 * across ten production search queries are in this state today.
 *
 * ⚠️ WHY A GUARD PINNED ON THE ISSUE'S ORIGINAL SPECIMENS WOULD PASS AGAINST
 * THE BUG. The fix prescribed in the issue is "fall back to `hero_probability` /
 * `hero_probability_away`". The original pair (`15307090`, `15296921`) carried
 * BOTH fields. The row that is still live carries away as `null` — because
 * `routes/events.py` runs the hero through `printable_away`, so on a
 * draw-priced sport the server withholds the complement for #6238's reason
 * before the client ever sees it. 19 of the 21 rows on the specimen's own
 * payload carry an away figure; the one that does not is the one row the fix
 * exists for. ARM 1 is therefore the null-away case, and ARM 2 asserts that the
 * away slot stays empty rather than being rebuilt as `1 − 0.225` — which on a
 * 22.5 / 47 / ~30 three-way market would print 78% under Kaizer Chiefs.
 *
 * BOTH DIRECTIONS, PER GOTCHA #43. Every rescue arm has a control that proves
 * the fallback is a LAST rung and not an override: a priced card is byte-for-byte
 * unaffected (ARM 4), a card holding both a hero and `current_odds` renders the
 * odds (ARM 5), the UX-P042 untraded-midpoint refusal still fires (ARM 7), and a
 * finished card never takes a hero into the slots that hold its pre-match prior
 * (ARMS 8 and 9). Without those, a change that simply deleted `noReading` would
 * pass ARM 1.
 */

import React from "react";
import { renderToStaticMarkup } from "react-dom/server";

jest.mock("next/link", () => {
  const ReactLib = require("react");
  return {
    __esModule: true,
    default: ({ href, children, ...props }: { href: string; children: React.ReactNode }) =>
      ReactLib.createElement("a", { href, ...props }, children),
  };
});

jest.mock("@/components/Analytics", () => ({
  useAnalyticsContext: () => ({ track: () => {} }),
}));
jest.mock("@/hooks", () => ({
  useAnalytics: () => ({ trackEventCardClick: () => {}, track: () => {} }),
}));
jest.mock("../../hooks", () => ({
  useAnalytics: () => ({ trackEventCardClick: () => {}, track: () => {} }),
}));

import EventCard from "@/components/EventCard";
import type { Event } from "@/lib/types";

const IN_THE_FUTURE = new Date(Date.now() + 26 * 3600_000).toISOString();
const IN_THE_PAST = new Date(Date.now() - 26 * 3600_000).toISOString();

/**
 * `15313996`, field for field off `GET /api/events/search?q=chiefs` on
 * production 2026-09-19 — a draw-priced fixture with a verified Polymarket
 * blend, no sportsbook price, and a withheld away side.
 */
function specimen(over: Partial<Event> = {}): Event {
  return {
    id: 15313996,
    external_id: null,
    sport: "soccer_other",
    sport_name: "Other Soccer",
    home_team: "Lamontville Golden Arrows",
    away_team: "Kaizer Chiefs",
    commence_time: IN_THE_FUTURE,
    completed_at: null,
    status: "scheduled",
    home_score: null,
    away_score: null,
    win_probability_sources: {
      polymarket: {
        value: 0.225,
        display_name: "Polymarket",
        type: "market",
        color: "#3b82f6",
        updated_at: "2026-09-17T19:15:36.402019+00:00",
      },
    },
    hero_probability: 0.225,
    hero_probability_away: null,
    hero_probability_source: "blend",
    home_team_data: { primary_color: "#f59e0b" },
    away_team_data: { primary_color: "#c8a02c" },
    ...over,
  } as unknown as Event;
}

/**
 * `15312247`, same payload shape on a TWO-WAY sport: the server keeps the away
 * half, so both numbers print. Pinned so the fix is not silently soccer-only.
 */
function twoWaySpecimen(over: Partial<Event> = {}): Event {
  return specimen({
    id: 15312247,
    sport: "baseball_mlb",
    sport_name: "MLB",
    home_team: "Athletics",
    away_team: "New York Yankees",
    win_probability_sources: { polymarket: { value: 0.495 } },
    hero_probability: 0.495,
    hero_probability_away: 0.505,
    ...over,
  } as unknown as Partial<Event>);
}

/** A sportsbook pair, the shape the card has always read. */
const PRICED_ODDS = {
  captured_at: IN_THE_PAST,
  home_probability: 0.62,
  away_probability: 0.38,
  spread: null,
  over_under: null,
  projected_home_score: null,
  projected_away_score: null,
};

function card(event: Event): string {
  return renderToStaticMarkup(<EventCard event={event} />);
}

/** Every whole percent the markup actually prints, in document order. */
function printedPercents(html: string): number[] {
  return Array.from(html.replace(/<[^>]*>/g, " ").matchAll(/(\d+)%/g)).map(m =>
    Number(m[1]),
  );
}

describe("#4797 — a served blend reaches the card", () => {
  test("ARM 1: the live specimen prints its 23% instead of 'No price yet'", () => {
    // THE BUG, in the row that is still on production nine days after the
    // diagnosis. `hero_probability_away` is null here, which is exactly the
    // shape a fixture copied from the issue's original pair would not have.
    const html = card(specimen());
    expect(html).not.toContain("No price yet");
    expect(printedPercents(html)).toContain(23);
    // The bar comes back with the number. `role="meter"` carries no `%`, so
    // `printedPercents` cannot see it and it needs saying separately — and it is
    // what ARMS 8 and 10 assert the ABSENCE of, so all three read one marker.
    expect(html).toContain('role="meter"');
    expect(html).toContain('aria-valuenow="23"');
  });

  test("ARM 2: the withheld away side is NOT rebuilt as the complement", () => {
    // 1 − 0.225 = 0.775 under Kaizer Chiefs would be "Lamontville does not win"
    // — away win OR draw — wearing one team's name, on a market whose real
    // split is 22.5 / 47 / ~30. #6238 is the whole argument; this pins that the
    // fallback did not walk around it.
    const percents = printedPercents(card(specimen()));
    expect(percents).toEqual([23]);
    expect(percents).not.toContain(78);
    expect(percents).not.toContain(77);
  });

  test("ARM 3: a TWO-WAY hero pair prints both sides", () => {
    // The rescue is not soccer-only, and on a sport with no third outcome the
    // served away half is a real number and is printed. Document order is home
    // row then away row, and the pair is rounded ONCE together (#2787), so
    // 0.495 / 0.505 prints 49 then 51 and never 50/50 or a 101.
    expect(printedPercents(card(twoWaySpecimen()))).toEqual([49, 51]);
  });

  test("ARM 3b: with both sides in hand the favourite is still emphasised", () => {
    // `favoriteKnown` is true here (nothing is withheld), so the ordinary
    // emphasis rule must survive the new arm rather than every hero card
    // rendering as a dead heat.
    const html = card(twoWaySpecimen({ hero_probability: 0.81, hero_probability_away: 0.19 }));
    expect(html).toContain("text-text-secondary");
    expect(printedPercents(html)).toEqual([81, 19]);
  });
});

describe("#4797 — the fallback is a last rung, not an override", () => {
  test("ARM 4 (CONTROL): a card with current_odds and no hero is unchanged", () => {
    expect(printedPercents(card(specimen({
      sport: "baseball_mlb",
      hero_probability: undefined,
      hero_probability_away: undefined,
      hero_probability_source: undefined,
      current_odds: PRICED_ODDS,
    } as unknown as Partial<Event>)))).toEqual([62, 38]);
  });

  test("ARM 5 (CONTROL): current_odds WINS over a disagreeing hero", () => {
    // The one arm that separates "fall back" from "prefer". Without it a fix
    // that read the hero first would pass every rescue arm above, and would
    // move the number on every priced card on the site.
    const html = card(specimen({
      sport: "baseball_mlb",
      hero_probability: 0.11,
      hero_probability_away: 0.89,
      current_odds: PRICED_ODDS,
    } as unknown as Partial<Event>));
    expect(printedPercents(html)).toEqual([62, 38]);
    expect(printedPercents(html)).not.toContain(11);
  });

  test("ARM 6 (CONTROL): no odds AND no hero still says 'No price yet'", () => {
    // #2882's sentence must survive. A fix that deleted `noReading` rather than
    // feeding it passes ARM 1 and fails here.
    const html = card(specimen({
      hero_probability: undefined,
      hero_probability_away: undefined,
      hero_probability_source: undefined,
      win_probability_sources: undefined,
    } as unknown as Partial<Event>));
    expect(html).toContain("No price yet");
    expect(printedPercents(html)).toEqual([]);
  });

  test("ARM 7 (CONTROL): the untraded-midpoint refusal still fires", () => {
    // UX-P042/#1640. An untraded Polymarket book reports exactly 0.500, and the
    // hero built from it reads 0.5 too — so reading the hero ABOVE
    // `shouldWithholdProbability` would re-publish the fabricated coin flip the
    // gate exists to refuse, on precisely the rows that have no sportsbook
    // price to out-rank it.
    const html = card(specimen({
      sport: "baseball_mlb",
      win_probability_sources: { polymarket: { value: 0.5 } },
      hero_probability: 0.5,
      hero_probability_away: 0.5,
    } as unknown as Partial<Event>));
    expect(html).toContain("No price yet");
    expect(printedPercents(html)).toEqual([]);
  });
});

describe("#4797 — a finished card never takes a hero into its prior's slots", () => {
  test("ARM 8 (CONTROL): a closed row with a final_unresolved hero prints no percent", () => {
    // THIS ARM IS THE FINISHED GUARD. The fallback deliberately carries no
    // `!isFinishedStatus(...)` clause: such a clause survives its own mutant,
    // because on a finished card `homeProb`/`awayProb` are read by nothing (the
    // chips, the bar and the no-reading sentence are each gated `!isFinished`).
    // So the protection lives here instead, where it CAN die — drop `!isFinished`
    // from the probability chip and this arm goes red printing 91.
    // `15291547` on production today: `closed`, `hero_probability 0.91`, source
    // `final_unresolved`, no opening line. On a finished card these two slots
    // hold the #2764 PRE-MATCH prior, printed grey beside each name. A
    // last-captured blend dropped in there is a number from after the whistle
    // labelled as what the market thought before it — and Q441/#1495 measured 5
    // of 44 finished games whose last blend named the LOSER as favourite.
    const html = card(specimen({
      id: 15291547,
      sport: "baseball_mlb",
      status: "closed",
      commence_time: IN_THE_PAST,
      completed_at: IN_THE_PAST,
      home_score: 2,
      away_score: 5,
      hero_probability: 0.91,
      hero_probability_away: 0.09,
      hero_probability_source: "final_unresolved",
    } as unknown as Partial<Event>));
    expect(printedPercents(html)).toEqual([]);
    expect(html).not.toContain("No price yet");
    // And no bar. A filled meter built from a settled/last-captured hero is the
    // same claim in pixels, and it survives an assertion that only reads text.
    expect(html).not.toContain('role="meter"');
  });

  test("ARM 9 (CONTROL): a finished row WITH an opening line still prints the opening", () => {
    // The other direction of ARM 8: excluding finished must not cost the prior
    // the card already draws for a settled row.
    const html = card(specimen({
      id: 15292753,
      sport: "baseball_mlb",
      status: "completed",
      commence_time: IN_THE_PAST,
      completed_at: IN_THE_PAST,
      home_score: 4,
      away_score: 1,
      hero_probability: 1,
      hero_probability_away: 0,
      hero_probability_source: "settled",
      opening_odds: { ...PRICED_ODDS, home_probability: 0.57, away_probability: 0.43 },
    } as unknown as Partial<Event>));
    // What this arm kills is the #2764 prior itself: delete the grey span and
    // it goes red. The `not.toContain(100)` half is belt: a settled 1.0 cannot
    // reach the screen on a finished card anyway, because ARM 8's render gate
    // holds the chips shut — stated so nobody later reads it as the guard.
    const percents = printedPercents(html);
    expect(html).toContain('data-testid="event-card-prematch-home"');
    expect(percents).toContain(57);
    expect(percents).not.toContain(100);
  });

  test("ARM 10 (CONTROL): a SUSPENDED row gains a reading and still prints nothing", () => {
    // CERT-792: a stale live blend is not a statement a suspended card may
    // make, and every print site is gated `!isSuspended`. Pinned because it is
    // the reason this issue's two ORIGINAL specimens — both `suspended` — are
    // not what closes it, and so nobody later "fixes" the silence.
    const html = card(specimen({
      status: "suspended",
      commence_time: IN_THE_PAST,
    } as unknown as Partial<Event>));
    expect(printedPercents(html)).toEqual([]);
    expect(html).not.toContain("No price yet");
    expect(html).not.toContain('role="meter"');
  });
});
