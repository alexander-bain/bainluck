/**
 * #6216 — A FOOTBALL PROP CARD OFFERED "rebounds, assists, 3PT…".
 *
 * `PlayerPropsDashboard.tsx:332` hardcoded three basketball examples into the
 * collapsed-stats button, on every sport. Found on production by ux/1264 while
 * walking a live marquee NFL game under D48 / notice 42: every NFL prop card
 * promised a reader rebounds and three-pointers.
 *
 * The real names were in scope the whole time, and `stat.type` is already a
 * display string (`STAT_TYPES`: "Passing Yards", "Receptions", "Touchdowns")
 * which `StatBox` prints raw. So this is true-instead-of-guessed, not new copy.
 *
 * ## 🔴 THE SECOND DEFECT IN THE SAME SENTENCE, FOUND BY THIS SUITE
 *
 * A first pass at these guards failed on a fixture I had expected to pass, and
 * the fixture was right. The button counted `otherStats` — "everything that is
 * not Points" — which equals "everything not shown" ONLY on a sport that has a
 * Points stat. Basketball does. Football does not: `pointsStats` is empty,
 * `statsToShow` falls back to `player.stats.slice(0, 1)`, and `otherStats` still
 * contains that very stat.
 *
 * So a Bo Nix card showing "Passing Yards" said "+3 more stats", and naming the
 * real stats would have led that list with **Passing Yards, already on the
 * card**. Fixing only the words would have swapped a wrong example for an absurd
 * one. The button now reads `hiddenStats`, derived from `statsToShow` by
 * identity so it cannot drift from what was rendered.
 *
 * ## Why the guards are shaped this way
 *
 * The other risk here is JSX whitespace: the fix spans three lines inside a text
 * node, and JSX joins text lines with a space. `( Passing Yards …)` would be a
 * new cosmetic defect introduced by the fix for a cosmetic defect. So the
 * button's text is asserted as an EXACT string, never with `toContain`.
 */
import { renderToStaticMarkup } from "react-dom/server";
import React from "react";

import PlayerPropsDashboard from "../../components/PlayerPropsDashboard";
import type { GameMarketsResponse } from "../../lib/api";

const NFL_MATCHUP = "Denver Broncos vs. Kansas City Chiefs - Player Props";

function row(outcome: string, threshold: number) {
  return {
    market_name: NFL_MATCHUP,
    outcome_name: outcome,
    threshold,
    over_probability: 0.5,
    source: "kalshi",
    movement: null,
    actual: null,
    hit: null,
    is_winner: false,
    resolution_source: null,
    player_team: "home" as const,
  };
}

function render(rows: Array<Record<string, unknown>>) {
  return renderToStaticMarkup(
    <PlayerPropsDashboard
      data={{ player_props: rows, other: [] } as unknown as GameMarketsResponse}
      eventStatus="pre"
      homeTeam="Denver Broncos"
      awayTeam="Kansas City Chiefs"
      boxScore={null}
    />,
  );
}

/** The `+N more stats (…)` button's own text, whitespace included. */
function moreStatsButtonText(html: string): string | null {
  const m = html.match(/>\+(\d+) more stats?[^<]*</);
  return m ? m[0].slice(1, -1) : null;
}

describe("#6216 the collapsed-stats button names the stats this player actually has", () => {
  it("an NFL card no longer offers rebounds, assists or 3PT", () => {
    const html = render([
      row("Bo Nix: Passing Yards O/U 245.5", 245.5),
      row("Bo Nix: Rushing Yards O/U 24.5", 24.5),
      row("Bo Nix: Touchdowns O/U 1.5", 1.5),
    ]);
    // The literal defect, by name. These words appear nowhere in an NFL card.
    expect(html).not.toContain("rebounds");
    expect(html).not.toContain("assists");
    expect(html).not.toContain("3PT");
  });

  it("it names the real ones, with no JSX whitespace seam", () => {
    const html = render([
      row("Bo Nix: Passing Yards O/U 245.5", 245.5),
      row("Bo Nix: Rushing Yards O/U 24.5", 24.5),
      row("Bo Nix: Touchdowns O/U 1.5", 1.5),
    ]);
    // EXACT, not `toContain`: the fix spans three lines in a JSX text node, and
    // JSX joins text lines with a space. `( Passing Yards` would pass a
    // substring check and look broken on the card.
    expect(moreStatsButtonText(html)).toBe("+2 more stats (Rushing Yards, Touchdowns)");
  });

  it("caps the list at three and elides the rest", () => {
    const html = render([
      row("Bo Nix: Passing Yards O/U 245.5", 245.5),
      row("Bo Nix: Rushing Yards O/U 24.5", 24.5),
      row("Bo Nix: Touchdowns O/U 1.5", 1.5),
      row("Bo Nix: Interceptions O/U 0.5", 0.5),
      row("Bo Nix: Sacks O/U 2.5", 2.5),
    ]);
    const text = moreStatsButtonText(html);
    expect(text).toBe("+4 more stats (Rushing Yards, Touchdowns, Interceptions…)");
    // The count reports every HIDDEN stat; only the examples are capped.
    expect(text).toMatch(/^\+4 /);
  });

  it("no ellipsis when nothing is actually elided — the other direction", () => {
    const html = render([
      row("Bo Nix: Passing Yards O/U 245.5", 245.5),
      row("Bo Nix: Rushing Yards O/U 24.5", 24.5),
      row("Bo Nix: Touchdowns O/U 1.5", 1.5),
    ]);
    expect(moreStatsButtonText(html)).not.toContain("…");
  });

  it("the singular still reads 'stat', not 'stats'", () => {
    const html = render([
      row("Bo Nix: Passing Yards O/U 245.5", 245.5),
      row("Bo Nix: Rushing Yards O/U 24.5", 24.5),
    ]);
    // Two stats, one shown, one hidden → "+1 more stat".
    expect(moreStatsButtonText(html)).toBe("+1 more stat (Rushing Yards)");
  });

  it("a BASKETBALL card names basketball stats — the examples were never wrong, only fixed", () => {
    const html = renderToStaticMarkup(
      <PlayerPropsDashboard
        data={{
          player_props: [
            {
              ...row("Nikola Jokic: Rebounds O/U 12.5", 12.5),
              market_name: "Denver Nuggets vs. Phoenix Suns - Player Props",
            },
            {
              ...row("Nikola Jokic: Assists O/U 9.5", 9.5),
              market_name: "Denver Nuggets vs. Phoenix Suns - Player Props",
            },
          ],
          other: [],
        } as unknown as GameMarketsResponse}
        eventStatus="pre"
        homeTeam="Denver Nuggets"
        awayTeam="Phoenix Suns"
        boxScore={null}
      />,
    );
    // The point of the fix: the words are READ, not guessed. On a basketball
    // card "Rebounds" is correct — and now it is correct because it is true,
    // not because the hardcoded string happened to match the sport.
    expect(moreStatsButtonText(html)).toBe("+1 more stat (Assists)");
  });

  /**
   * THE NON-REGRESSION PROOF FOR THE COUNT CHANGE.
   *
   * A card WITH a Points stat is the case where `otherStats` and `hiddenStats`
   * coincide — `statsToShow` is `[Points]`, so everything else is hidden by
   * definition. The count here is IDENTICAL under the old rule and the new one,
   * which is what makes "only the sports that were already miscounting move" a
   * measured statement rather than a claim.
   */
  it("a card with a Points stat counts exactly as it did before", () => {
    const html = renderToStaticMarkup(
      <PlayerPropsDashboard
        data={{
          player_props: [
            { ...row("Nikola Jokic: Points O/U 27.5", 27.5), market_name: "Denver Nuggets vs. Phoenix Suns - Player Props" },
            { ...row("Nikola Jokic: Rebounds O/U 12.5", 12.5), market_name: "Denver Nuggets vs. Phoenix Suns - Player Props" },
            { ...row("Nikola Jokic: Assists O/U 9.5", 9.5), market_name: "Denver Nuggets vs. Phoenix Suns - Player Props" },
          ],
          other: [],
        } as unknown as GameMarketsResponse}
        eventStatus="pre"
        homeTeam="Denver Nuggets"
        awayTeam="Phoenix Suns"
        boxScore={null}
      />,
    );
    // Old rule: otherStats = [Rebounds, Assists] -> "+2". New rule: statsToShow
    // = [Points], hidden = [Rebounds, Assists] -> "+2". Same number, by design.
    expect(moreStatsButtonText(html)).toBe("+2 more stats (Rebounds, Assists)");
  });
});
