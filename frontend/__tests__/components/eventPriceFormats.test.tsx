/**
 * NO GAMBLING PRICE FORMATS ON THE EVENT PAGE (#2442).
 *
 * Alex, reading `/events/15293846` during the tournament on 2026-08-31, counted
 * **six on one screen**: `Betting Odds (market)`, `Individual sportsbooks`,
 * `Sportsbooks`, `+4.5`, `spread`, `total`. His note: *a ratified rule being
 * broken on the flagship page.*
 *
 * ═══ WHY A RENDER GUARD AND NOT ONLY THE BUNDLE SCAN ═══
 *
 * `lib/copyBans.ts` gained a `PRICE_FORMAT_BANS` group, and
 * `shippedCopyBans.test.ts` applies it to the bytes Vercel uploads. That is the
 * right backstop and it is **structurally blind to the string Alex quoted
 * first**: `BER +4.5` is assembled at runtime from a team abbreviation and a
 * threshold, so no literal of it exists in any chunk. Measured — the
 * `handicap-notation` rule scores **zero** hits on the built bundle both before
 * and after this fix.
 *
 * The same blindness covers `Betting Odds`, which the API serves at runtime in
 * `win_probability_sources.betting.display_name`. A frontend sweep cannot
 * remove a string the backend sends; only resolving the name through the source
 * registry at the render can.
 *
 * So this file renders the real components over real-shaped payloads and reads
 * the text, and the bundle scan catches the hard-coded case. Two instruments,
 * two blind spots, neither one alone.
 *
 * ═══ THE ONE THING DELIBERATELY LEFT ALONE ═══
 *
 * The bare word *odds*. Alex's instruction on this issue is explicit — *"the
 * word odds alone is fine — do not over-rotate"* — and `The Odds API` is a
 * supplier's name. A guard that banned it would fail our own vendor and be
 * switched off within a week, which is this rule family's recorded failure
 * mode.
 */

import React from "react";
import { renderToStaticMarkup } from "react-dom/server";

// `OddsChart` reaches for the analytics context and THROWS outside its
// provider. Same lesson as CERT-606's `pinFor`: a leaf that reads app-level
// context cannot be rendered by itself without one.
jest.mock("@/components/Analytics/AnalyticsProvider", () => ({
  __esModule: true,
  useAnalyticsContext: () => ({ track: () => {} }),
  AnalyticsProvider: ({ children }: { children: React.ReactNode }) => children,
}));

import { PRICE_FORMAT_BANS, findBannedCopy } from "@/lib/copyBans";
import { sourceLabel } from "@/lib/sourceColors";
import { sportVocab } from "@/lib/marketMapUtils";
import MarketMapSection from "@/components/MarketMapSection";
import OddsChart from "@/components/OddsChart";
import ScoreDifferentialChart from "@/components/ScoreDifferentialChart";

/** Everything a reader can actually see. */
function visibleText(html: string): string {
  return html
    .replace(/<[^>]+>/g, " ")
    .replace(/&[a-z]+;/g, " ")
    .replace(/\s+/g, " ")
    .trim();
}

/** The rules that fired, named, so a failure says WHICH format came back. */
function bannedIn(text: string): string[] {
  return findBannedCopy(text, PRICE_FORMAT_BANS).map(
    (h) => `${h.ban.id}: ${JSON.stringify(h.matched)} in "${h.context}"`
  );
}

/**
 * A real-shaped NBA game-markets payload, WITH TOTALS.
 *
 * CERT-642's diagnosis of the first version of this file: the fixture carried
 * `totals: []`, so `MarketMapSection`'s whole Total column never rendered and
 * the guard could not see the `Total maps` heading it was supposed to be
 * sweeping. **An empty fixture is a blind spot that reads exactly like a clean
 * sweep**, which is why it is a shared factory now rather than a literal one
 * case happens to get right.
 */
function nbaMarkets() {
  return {
      event_id: 1,
      home_team: "Los Angeles Lakers",
      away_team: "Boston Celtics",
      home_score: null,
      away_score: null,
      status: "scheduled",
      // CERT-642: this array was EMPTY, so the whole Total column never
      // rendered and the guard could not see the "Total maps" heading it was
      // supposed to be sweeping. An empty fixture is a blind spot that looks
      // like a pass.
      totals: [
        { threshold: 218.5, over_probability: 0.55, source: "kalshi", market_type: "game_total", market_name: "Lakers vs Celtics: Total", outcome_name: "Over 218.5", is_winner: null, resolution_source: null, movement: 0, period: null },
        { threshold: 224.5, over_probability: 0.38, source: "kalshi", market_type: "game_total", market_name: "Lakers vs Celtics: Total", outcome_name: "Over 224.5", is_winner: null, resolution_source: null, movement: 0, period: null },
      ],
      player_props: [],
      team_totals: [],
      period_markets: [],
      matchups: [],
      other: [],
      pace: null,
      props_script: [],
      spreads: [
        { market_name: "Lakers vs Celtics: Spread", outcome_name: "Los Angeles Lakers -4.5", threshold: 4.5, probability: 0.52, source: "kalshi", is_winner: null, resolution_source: null },
        { market_name: "Lakers vs Celtics: Spread", outcome_name: "Los Angeles Lakers -7.5", threshold: 7.5, probability: 0.34, source: "kalshi", is_winner: null, resolution_source: null },
        { market_name: "Lakers vs Celtics: Spread", outcome_name: "Boston Celtics -1.5", threshold: 1.5, probability: 0.41, source: "kalshi", is_winner: null, resolution_source: null },
      ],
    };
}

describe("#2442 — the rules themselves", () => {
  it("fires on every format Alex counted", () => {
    // Each of these is a string that WAS on the page. If a pattern is loosened
    // into uselessness these go quiet, which is the failure this pins.
    expect(bannedIn("PRE-GAME BER +4.5")).not.toHaveLength(0);
    expect(bannedIn("WAW -1.5")).not.toHaveLength(0);
    expect(bannedIn("Where it landed vs the pregame spread")).not.toHaveLength(0);
    expect(bannedIn("Projected Spread")).not.toHaveLength(0);
    expect(bannedIn("Game spreads")).not.toHaveLength(0);
    expect(bannedIn("the moneyline")).not.toHaveLength(0);
    expect(bannedIn("over/under 40.5")).not.toHaveLength(0);
  });

  it("leaves alone the language the ruling protects", () => {
    // The bare noun, and our supplier's actual name.
    expect(bannedIn("Betting odds move when news breaks")).toHaveLength(0);
    expect(bannedIn("Spreads (Odds API)")).toHaveLength(0);
    // The VERB. A rule that cannot tell "spread across four rounds" from "the
    // spread" fires on the product's own content and gets deleted.
    expect(bannedIn("The field is spread across four rounds")).toHaveLength(0);
    expect(bannedIn("Points are spread evenly between the two halves")).toHaveLength(0);
    // Ordinary totals, which every scoring surface says correctly.
    expect(bannedIn("Total games played: 40")).toHaveLength(0);
    expect(bannedIn("112 points scored in total")).toHaveLength(0);
  });

  it("does NOT ban American odds, because /about's counter-example depends on it", () => {
    // Alex ruled 2026-07-31 that naming the format we refuse to show is the
    // opposite of selling it, and `/about`'s founding line is the pinned
    // example. A rule here could not tell the two apart, so there is no rule.
    expect(bannedIn('Not "-150 / +130" — just probabilities')).toHaveLength(0);
  });
});

describe("#2442 — one supplier, one name, resolved at the render", () => {
  it("never calls the sportsbook source 'Betting Odds', even when the API does", () => {
    // The exact string production serves in
    // `win_probability_sources.betting.display_name`. The registry, not the
    // payload, decides what a reader is shown.
    expect(sourceLabel("betting", "Betting Odds")).toBe("Sportsbooks");
    expect(sourceLabel("odds_api", "Betting Odds")).toBe("Sportsbooks");
    expect(bannedIn(sourceLabel("betting", "Betting Odds"))).toHaveLength(0);
  });

  it("renders the registry name in the CHART, over a payload that says otherwise", () => {
    // THE ARM THAT MATTERS, and the one this file did not have on its first
    // draft: asserting `sourceLabel()` returns "Sportsbooks" proves nothing
    // about `OddsChart`, which had its own fallback map AND preferred the
    // payload's name. The mutation battery proved it — reverting the chart to
    // `meta?.display_name` left a pure-logic version of this suite fully GREEN.
    //
    // `winProbSources` below is the EXACT block production serves. If the
    // chart ever trusts it again, this goes red.
    const html = renderToStaticMarkup(
      <OddsChart
        history={[
          { timestamp: "2026-08-30T15:00:00Z", home_probability: 0.7, away_probability: 0.3, bookmaker_count: 7 },
          { timestamp: "2026-08-30T16:00:00Z", home_probability: 0.84, away_probability: 0.16, bookmaker_count: 7 },
        ] as never}
        homeTeam="Matteo Berrettini"
        awayTeam="Stan Wawrinka"
        commenceTime="2026-08-30T15:00:00Z"
        isLive={false}
        winProbSources={
          {
            betting: {
              display_name: "Betting Odds",
              color: "#0f172a",
              dash_pattern: null,
              type: "market",
            },
          } as never
        }
        eventStatus="closed"
      />
    );
    const text = visibleText(html);

    // The legend rendered — otherwise every absence below is the emptiness of
    // a component that drew nothing.
    expect(text).toContain("Sportsbooks");
    // The payload's own name never reaches the reader...
    expect(text).not.toContain("Betting Odds");
    // ...and neither does our internal taxonomy, which is the other half of
    // what Alex read as `Betting Odds (market)`.
    expect(text).not.toContain("(market)");
    expect(text).not.toContain("(model)");
    expect(bannedIn(text)).toEqual([]);
  });

  it("still names a source the registry has never heard of", () => {
    // The failure direction that matters: a new supplier must not become
    // nameless because it is not in the map yet.
    expect(sourceLabel("some_new_feed", "Some New Feed")).toBe("Some New Feed");
    expect(sourceLabel("some_new_feed")).toBe("some_new_feed");
  });
});

describe("#2442 — the market maps speak in margins, not handicaps", () => {
  it("builds every margin-ladder rung as a margin, through the real section", () => {
    // Deliberately NOT `MarketMap` with hand-written labels: that would assert
    // the renderer prints the strings this test invented, which is the vacuous
    // shape this repo has been bitten by before. `MarketMapSection` is where
    // the label is BUILT, so it is what runs.
    const gameMarkets = nbaMarkets();

    const html = renderToStaticMarkup(
      <MarketMapSection
        gameMarkets={gameMarkets as never}
        eventStatus="scheduled"
        homeTeam="Los Angeles Lakers"
        awayTeam="Boston Celtics"
        homeAbbr="LAL"
        awayAbbr="BOS"
        homeWinProb={0.62}
        awayWinProb={0.38}
        homeSpread={-4.5}
        overUnder={null}
        sportKey="basketball_nba"
      />
    );
    const text = visibleText(html);

    // The section rendered at all — otherwise the clean sweep below is the
    // emptiness of a component that returned null, not the absence of a format.
    expect(text.length).toBeGreaterThan(20);
    // The rungs are built, and built as margins.
    expect(text).toContain("LAL by 4.5+");
    expect(text).toContain("BOS by 1.5+");
    // And nowhere on it is a betting line.
    expect(bannedIn(text)).toEqual([]);
    expect(text).not.toContain("LAL +4.5");
    // "covering" is the betting VERB — a side covers THE SPREAD. It is pinned
    // by a literal rather than by a rule on purpose: a pattern loose enough to
    // catch the bare gerund would also fire on "covering the field" and
    // "covering all four rounds", and this file's whole discipline is that a
    // rule which cries wolf is a rule somebody deletes. The mutation battery
    // is what found this — reverting the verb left every OTHER arm green.
    expect(text).not.toContain("covering");
    expect(text).toContain("winning by");
  });

  it("renders the TOTAL column too — the blind spot CERT-642 found", () => {
    // The first version of this suite passed while `Total maps` shipped,
    // because its fixture carried `totals: []` and the column never rendered.
    // An empty fixture is a blind spot that reads exactly like a clean sweep.
    const html = renderToStaticMarkup(
      <MarketMapSection
        gameMarkets={nbaMarkets() as never}
        eventStatus="scheduled"
        homeTeam="Los Angeles Lakers"
        awayTeam="Boston Celtics"
        homeAbbr="LAL"
        awayAbbr="BOS"
        homeWinProb={0.62}
        awayWinProb={0.38}
        homeSpread={-4.5}
        overUnder={220}
        sportKey="basketball_nba"
      />
    );
    const text = visibleText(html);
    // It rendered — otherwise the absence below is nothing at all.
    expect(text).toContain("218.5");
    expect(text).not.toContain("Total maps");
    expect(bannedIn(text)).toEqual([]);
  });

  it("sweeps the score-differential chart, which the first sweep never rendered", () => {
    // CERT-642's other finding lived here: `Gray lines show individual
    // sportsbooks`, the third spelling of one supplier, in a component no arm
    // of this suite had ever mounted. A sweep is only as wide as its renders.
    const html = renderToStaticMarkup(
      <ScoreDifferentialChart
        history={[
          { timestamp: "2026-08-30T15:00:00Z", home_probability: 0.7, away_probability: 0.3, projected_home_score: 112, projected_away_score: 104, bookmaker_count: 7 },
          { timestamp: "2026-08-30T16:00:00Z", home_probability: 0.8, away_probability: 0.2, projected_home_score: 115, projected_away_score: 102, bookmaker_count: 7 },
        ] as never}
        homeTeam="Los Angeles Lakers"
        awayTeam="Boston Celtics"
        commenceTime="2026-08-30T15:00:00Z"
        isLive={false}
        eventStatus="closed"
        bookmakerHistory={
          {
            betmgm: [
              { timestamp: "2026-08-30T15:00:00Z", home_probability: 0.69, away_probability: 0.31, projected_home_score: 111, projected_away_score: 105 },
              { timestamp: "2026-08-30T16:00:00Z", home_probability: 0.79, away_probability: 0.21, projected_home_score: 114, projected_away_score: 103 },
            ],
          } as never
        }
      />
    );
    const text = visibleText(html);
    // The caption rendered — the `bookmakers.length > 0` branch is reached.
    expect(text).toMatch(/Gray lines show/);
    // ...and says it through the registry, like every other surface.
    expect(text).toContain("sportsbooks");
    expect(text).not.toContain("individual sportsbooks");
    expect(text).not.toContain("Projected Spread");
    expect(bannedIn(text)).toEqual([]);
  });

  it("gives the default sport a unit, not a betting noun", () => {
    // "Total map" was the over/under's name; every other branch already said
    // the sport's own unit.
    expect(sportVocab("basketball_nba").totalTitle).toBe("Points map");
    expect(sportVocab("baseball_mlb").totalTitle).toBe("Runs map");
    expect(sportVocab("icehockey_nhl").totalTitle).toBe("Goals map");
    for (const key of ["basketball_nba", "baseball_mlb", "icehockey_nhl", "tennis_atp_us_open"]) {
      const v = sportVocab(key);
      expect(bannedIn(`Full game ${v.totalTitle.toLowerCase()}`)).toEqual([]);
      expect(bannedIn(`Full game ${v.marginTitle.toLowerCase()}`)).toEqual([]);
    }
  });
});
