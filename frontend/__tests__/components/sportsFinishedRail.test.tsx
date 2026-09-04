// ux/1053 — the Finished rail's RENDER.
//
// Every assertion below goes through `LeagueGameRail` and out of the shared
// `EventCard`, never through a helper: a helper-only test passes on a build that
// never calls the helper, which is the class `plant_must_hit_the_render` names.
//
// The two producers are BOTH exercised — `feedEventToEvent` (the /sports
// Finished section) and `leagueGameToEvent` (the league page's Recent Results) —
// because "the tab and the page agree" is a claim about both of them landing on
// the same card, and a test of one proves nothing about the other.

import { renderToStaticMarkup } from "react-dom/server";
import React from "react";
import type { FeedEventData } from "../../lib/types";
import type { LeagueGameBrief } from "../../lib/api";

// The mock FORWARDS every prop, including `className`. A mock that drops it
// renders an anchor with no class, and every emphasis assertion below would
// then be reading an attribute the test itself deleted.
jest.mock("next/link", () => ({
  __esModule: true,
  default: ({ href, children, ...rest }: { href: string; children: React.ReactNode }) => (
    <a href={href} {...rest}>
      {children}
    </a>
  ),
}));

jest.mock("../../hooks", () => ({
  useAnalytics: () => ({ trackEventCardClick: jest.fn() }),
}));

import LeagueGameRail from "../../components/LeagueGameRail";
import { feedEventToEvent } from "../../lib/feedEventToEvent";
import { leagueGameToEvent } from "../../lib/leagueCards";
import { PREMATCH_NUMBER_CLASS } from "../../lib/prematchReading";

/**
 * The Cardinals–Dodgers card off the served payload,
 * `GET /api/feed?limit=40&mode=sports` 2026-09-03: a books rung at 72/28 on a
 * game the 28% side won. Real numbers, so a rounding change shows up here.
 */
function finishedFeedEvent(over: Partial<FeedEventData> = {}): FeedEventData {
  return {
    id: 15300843,
    external_id: "e-15300843",
    sport: "baseball_mlb",
    sport_name: "MLB",
    home_team: "Los Angeles Dodgers",
    away_team: "St. Louis Cardinals",
    commence_time: "2026-09-03T02:10:00+00:00",
    status: "completed",
    home_score: 6,
    away_score: 8,
    prematch_odds: {
      home_probability: 0.7246,
      away_probability: 0.2754,
      home_rendered_percent: 72,
      away_rendered_percent: 28,
      source: "books",
    },
    ...over,
  } as FeedEventData;
}

function rail(events: ReturnType<typeof feedEventToEvent>[]): string {
  return renderToStaticMarkup(
    <LeagueGameRail title="Finished" events={events} settled layout="feed" />,
  );
}

describe("the settled card prints the closing number, beside the name it is about", () => {
  test("BOTH teams get their own figure, from the feed producer", () => {
    const html = rail([feedEventToEvent(finishedFeedEvent())]);

    expect(html).toContain('data-testid="event-card-prematch-home"');
    expect(html).toContain('data-testid="event-card-prematch-away"');
    expect(html).toContain("72%");
    expect(html).toContain("28%");
    // The rung travels with the number, so a guard can ask what each figure is
    // claiming (CERT-812) rather than inferring it from a glyph.
    expect(html).toContain('data-prematch-source="books"');
  });

  test("the same card through the LEAGUE producer prints the same pair", () => {
    // The league envelope carries no `prematch_odds`; `prematchReading` falls
    // back to `opening_odds`, which is a sportsbook median and has always been
    // one. If these two producers ever diverge, this is where it shows.
    const brief = {
      id: 15300843,
      home_team: "Los Angeles Dodgers",
      away_team: "St. Louis Cardinals",
      commence_time: "2026-09-03T02:10:00+00:00",
      status: "completed",
      home_score: 6,
      away_score: 8,
      home_win_probability: null,
      sport: "baseball_mlb",
      opening_odds: { home_probability: 0.7246, away_probability: 0.2754 },
    } as unknown as LeagueGameBrief;

    const html = rail([leagueGameToEvent(brief)]);
    expect(html).toContain("72%");
    expect(html).toContain("28%");
    expect(html).toContain('data-prematch-source="books"');
  });

  test("NO reading, NO number — a settled card never invents one", () => {
    // The regression arm. Without it every assertion above is satisfied by a
    // card that prints a figure unconditionally.
    const html = rail([
      feedEventToEvent(finishedFeedEvent({ prematch_odds: undefined })),
    ]);
    expect(html).not.toContain('data-testid="event-card-prematch-home"');
    expect(html).not.toContain('data-testid="event-card-prematch-away"');
    // Not `not.toContain("%")` — the rail's own grid template contains "100%".
    // The spoken clause only ever renders alongside a figure, so its absence is
    // the assertion that no number reached the reader in either register.
    expect(html).not.toContain("Before the game");
    expect(html).not.toMatch(/\d+%<\/span>/);
  });

  test("settled means settled — the LIVE blend is still refused on a final", () => {
    // `current_odds` on a finished game is a stale live reading. It was never
    // printed here and must not start being printed as a side effect of the
    // pre-match slot opening up, so it is planted at a value nothing else on
    // the card can produce.
    const html = rail([
      feedEventToEvent(
        finishedFeedEvent({
          current_odds: { home_probability: 0.77, away_probability: 0.23 },
        }),
      ),
    ]);
    expect(html).not.toContain("77%");
    expect(html).not.toContain("23%");
    expect(html).toContain("72%"); // the pre-match pair still renders
  });

  test("an UPCOMING card is untouched — it still shows its live-style chips", () => {
    // The control arm for the branch: `isFinished` is what gates all of this,
    // and a guard that only ever renders finished cards cannot tell a correct
    // gate from a missing one.
    const html = renderToStaticMarkup(
      <LeagueGameRail
        title="Upcoming"
        events={[
          feedEventToEvent(
            finishedFeedEvent({
              status: "scheduled",
              home_score: null,
              away_score: null,
              commence_time: "2030-09-03T02:10:00+00:00",
              current_odds: { home_probability: 0.61, away_probability: 0.39 },
            }),
          ),
        ]}
      />,
    );
    expect(html).not.toContain('data-testid="event-card-prematch-home"');
    expect(html).toContain("61%");
  });
});

describe("settled emphasis follows the RESULT, not the prior", () => {
  // The Rangers–Rays card from the ux/1053 shop. The Rays opened favourite at
  // 53% and lost 0-6, and the card bolded their name directly under a bold
  // winning score for the other side.
  const upset = () =>
    finishedFeedEvent({
      home_team: "Texas Rangers",
      away_team: "Tampa Bay Rays",
      home_score: 6,
      away_score: 0,
      prematch_odds: {
        home_probability: 0.47,
        away_probability: 0.53,
        home_rendered_percent: 47,
        away_rendered_percent: 53,
        source: "books",
      },
    });

  test("the WINNER is the emphasised name even when it was the underdog", () => {
    const html = rail([feedEventToEvent(upset())]);
    const winner = nameClass(html, "Texas Rangers");
    const loser = nameClass(html, "Tampa Bay Rays");

    expect(winner).toContain("font-semibold");
    expect(winner).toContain("text-text-primary");
    expect(loser).toContain("text-text-muted");
    expect(loser).not.toContain("font-semibold");
  });

  test("an UPCOMING card still emphasises the favourite — the branch is real", () => {
    // The control arm. Without it, hard-coding "emphasise the home side" would
    // pass the assertion above.
    const html = renderToStaticMarkup(
      <LeagueGameRail
        title="Upcoming"
        events={[
          feedEventToEvent(
            finishedFeedEvent({
              status: "scheduled",
              home_score: null,
              away_score: null,
              commence_time: "2030-09-03T02:10:00+00:00",
              current_odds: { home_probability: 0.3, away_probability: 0.7 },
              prematch_odds: undefined,
            }),
          ),
        ]}
      />,
    );
    expect(nameClass(html, "St. Louis Cardinals")).toContain("text-text-primary");
    expect(nameClass(html, "Los Angeles Dodgers")).toContain("text-text-secondary");
  });

  test("a draw emphasises NEITHER side", () => {
    const html = rail([
      feedEventToEvent(
        finishedFeedEvent({
          home_team: "Aves",
          away_team: "Bees",
          home_score: 2,
          away_score: 2,
        }),
      ),
    ]);
    expect(nameClass(html, "Aves")).toContain("text-text-muted");
    expect(nameClass(html, "Bees")).toContain("text-text-muted");
  });
});

describe("the feed's one-line story survives the shared card", () => {
  test("the label the producer chose renders on the card", () => {
    const html = renderToStaticMarkup(
      <LeagueGameRail
        title="Finished"
        events={[feedEventToEvent(finishedFeedEvent())]}
        settled
        layout="feed"
        labels={{ 15300843: "Won as 28% underdog" }}
      />,
    );
    expect(html).toContain("Won as 28% underdog");
  });

  test("no label supplied — the league page path draws no badge", () => {
    expect(rail([feedEventToEvent(finishedFeedEvent())])).not.toContain(
      "bg-accent-warning/15",
    );
  });
});

describe("no footnote mark, and no legend (D57 CORRECTED)", () => {
  // These three tests asserted the opposite this morning: a `†` on a
  // sportsbook rung, a rail legend counting the marks, and the count's exact
  // wording. Alex, 2026-09-03 4:15pm: *"We don't need to say anything about
  // sportsbooks. Our whole product is probabilities and how they're moving.
  // Just show the %."* Inverted rather than deleted — the rail is where the
  // legend lived, so it is where the guard that it stays gone belongs.

  test("a sportsbook rung renders the bare percent, no mark, no legend", () => {
    const html = rail([feedEventToEvent(finishedFeedEvent())]);
    expect(html).not.toContain("†");
    expect(html).not.toContain('data-testid="rail-prematch-source-note"');
    expect(html).not.toContain("sportsbook opening");
    // The WORD, still banned (D57's ban survives its own first fix). The
    // negative lookahead spares `data-prematch-source="books"`, which is the
    // data contract and is asserted present two lines down.
    expect(html).not.toMatch(/\bbooks\b(?!")/);
    expect(html).toContain('data-prematch-source="books"');
  });

  test("SYMMETRY — the market rung renders the same way, in the same treatment", () => {
    // The arm that makes the one above mean something. A rail that had simply
    // lost its numbers would pass every negative assertion; this one requires
    // that the two rungs are drawn identically and that the drawing is the
    // shared treatment rather than a fourth private class list.
    const market = rail([
      feedEventToEvent(
        finishedFeedEvent({
          prematch_odds: {
            home_probability: 0.88,
            away_probability: 0.12,
            home_rendered_percent: 88,
            away_rendered_percent: 12,
            source: "kalshi",
          },
        }),
      ),
    ]);
    expect(market).toContain("88%");
    expect(market).not.toContain("†");
    expect(market).not.toContain('data-testid="rail-prematch-source-note"');
    expect(market).toContain(PREMATCH_NUMBER_CLASS);
    expect(rail([feedEventToEvent(finishedFeedEvent())])).toContain(
      PREMATCH_NUMBER_CLASS,
    );
  });

  test("a rail of mixed rungs says nothing about any of them", () => {
    // Was: "the legend counts the marks actually drawn". There is nothing left
    // to count, and a rail with one of each rung is the case where a surviving
    // per-rung branch would show up.
    const html = rail([
      feedEventToEvent(finishedFeedEvent({ id: 1 })),
      feedEventToEvent(
        finishedFeedEvent({
          id: 2,
          prematch_odds: {
            home_probability: 0.6,
            away_probability: 0.4,
            source: "polymarket",
          },
        }),
      ),
    ]);
    expect(html).not.toContain("of them is a sportsbook opening");
    expect(html).not.toContain("†");
  });
});

describe("the cap declaration leads somewhere", () => {
  test("with links, it names the league pages holding the rest", () => {
    const html = renderToStaticMarkup(
      <LeagueGameRail
        title="Finished"
        events={[feedEventToEvent(finishedFeedEvent())]}
        settled
        layout="feed"
        hasMore
        moreLinks={[{ label: "MLB", href: "/sport/baseball/mlb" }]}
      />,
    );
    expect(html).toContain("Showing the 1 most recent");
    expect(html).toContain('href="/sport/baseball/mlb"');
    expect(html).toContain("more in ");
  });

  test("with no resolvable league, the cap is STILL declared", () => {
    // Register E5's other half: no link is better than a dead one, and a
    // silent cap is worse than either.
    const html = renderToStaticMarkup(
      <LeagueGameRail
        title="Finished"
        events={[feedEventToEvent(finishedFeedEvent())]}
        settled
        layout="feed"
        hasMore
        moreLinks={[]}
      />,
    );
    expect(html).toContain("Showing the 1 most recent");
    expect(html).toContain("more exist");
    expect(html).not.toContain("more in ");
  });
});

/**
 * The class of every name assertion above: the class attribute of the anchor
 * whose TEXT is this name.
 *
 * Deliberately not "search for the name and walk back to the nearest `<a`" —
 * the card's outer link carries an `aria-label` containing both team names, so
 * that form silently reads the wrapper's class and every assertion becomes a
 * statement about `h-full`. Anchored on the text node, and it throws rather
 * than returning "" when it finds nothing, because a vacuous class string
 * satisfies `not.toContain` for free.
 */
function nameClass(html: string, name: string): string {
  const re = new RegExp(`<a\\b[^>]*class="([^"]*)"[^>]*>${escapeRe(name)}<`);
  const m = re.exec(html);
  if (!m) throw new Error(`no anchor whose text is ${JSON.stringify(name)}`);
  return m[1];
}

function escapeRe(s: string): string {
  return s.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
}
