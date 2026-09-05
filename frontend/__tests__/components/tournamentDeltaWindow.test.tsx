/**
 * #3033 — THE `+33` SAYS WHICH WINDOW IT MEASURES.
 *
 * On the live men's board, in one frame: the chart opens on `Draw`, its footer
 * says six days, Alcaraz's line climbs about 19 points across it — and the row
 * directly under it reads `+33.4`. Both numbers are correct; `trend_delta` is
 * measured over the row's whole tracked history and the chart is showing the
 * tournament. Nothing on the card reconciles them.
 *
 * Two things are guarded here, and the second is the one that would rot first:
 *
 * 1. The board prints the sentence, in the MARKUP. A helper that returns the
 *    right string and is never rendered fixes nothing.
 * 2. The sentence is computed over the rows on screen and is NOT one date per
 *    board. On the live men's board 23 rows start 6 Aug, 12 start 26 Aug and one
 *    starts 7 Aug, because a contender's history begins when a market first
 *    priced them — so the "state the window once for the whole board" version of
 *    this fix would print one row's date over the others, which is a new false
 *    statement rather than a repair of the old one.
 *
 * The Swift port (`RaceChart.deltaWindowNote`, pinned in `RaceChartTests`) must
 * say the same words. One contract, two renderers.
 */

import React from "react";
import { renderToStaticMarkup } from "react-dom/server";

import TournamentBoard from "@/components/tournament/TournamentBoard";
import { deltaWindowNote } from "@/lib/contenderChart";
import type { TournamentBoardData, TournamentRow } from "@/lib/tournament";

function row(
  entityKey: string,
  {
    delta = 0.04,
    trendStart = "2026-08-06",
  }: { delta?: number | null; trendStart?: string | null } = {}
): TournamentRow {
  return {
    entity_key: entityKey,
    display_name: entityKey,
    seed: null,
    country: null,
    rank: 1,
    state: "live",
    probability: 0.44,
    probability_is_live: true,
    observed_at: "2026-09-05T11:00:00+00:00",
    age_hours: 1,
    price_state: "live",
    freshest_observed_at: "2026-09-05T11:00:00+00:00",
    freshest_age_hours: 1,
    stale_sources: [],
    mixed_freshness: false,
    source_count: 2,
    sources: [],
    blend_rule: "equal_weight_midpoint",
    divergent: false,
    trend: trendStart
      ? [
          { date: trendStart, probability: 0.12 },
          { date: "2026-09-05", probability: 0.44 },
        ]
      : [],
    trend_delta: delta,
  } as unknown as TournamentRow;
}

function board(rows: TournamentRow[]): TournamentBoardData {
  return {
    draw: "mens-singles",
    label: "Men's Singles",
    rows,
    contenders: rows.length,
    unpriced: 0,
    rows_not_live: 0,
    mixed_freshness_rows: 0,
    price_state: "live",
    newest_observed_at: "2026-09-05T11:00:00+00:00",
    age_hours: 1,
  } as unknown as TournamentBoardData;
}

describe("#3033 — what the movement column measures", () => {
  it("names the shared date when the drawn rows agree", () => {
    expect(deltaWindowNote([row("a"), row("b")])).toBe("Movement since 6 Aug.");
  });

  it("says the general truth rather than printing one row's date over the others", () => {
    expect(
      deltaWindowNote([row("a"), row("b", { trendStart: "2026-08-26" })])
    ).toBe("Movement since each contender's first number.");
  });

  it("ignores a row with no delta, which shows no badge to reconcile", () => {
    expect(
      deltaWindowNote([row("a"), row("b", { delta: null, trendStart: "2026-07-01" })])
    ).toBe("Movement since 6 Aug.");
  });

  it("says nothing at all when no drawn row carries a delta", () => {
    expect(deltaWindowNote([])).toBeNull();
    expect(deltaWindowNote([row("a", { delta: null })])).toBeNull();
    expect(deltaWindowNote([row("a", { trendStart: null })])).toBeNull();
  });

  it("prints the sentence on the board itself", () => {
    const html = renderToStaticMarkup(<TournamentBoard board={board([row("a"), row("b")])} />);
    expect(html).toContain('data-testid="board-delta-window"');
    expect(html).toContain("Movement since 6 Aug.");
  });

  it("draws no empty footer when there is no movement claim to explain", () => {
    const html = renderToStaticMarkup(
      <TournamentBoard board={board([row("a", { delta: null })])} />
    );
    expect(html).not.toContain('data-testid="board-delta-window"');
  });
});
