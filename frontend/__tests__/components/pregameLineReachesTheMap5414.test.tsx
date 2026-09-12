/**
 * #5414 — THE TILE LABELLED `PRE-GAME` SHOWS THE PRE-GAME LINE.
 *
 * ═══ THE DEFECT ═══
 *
 * `app/events/[id]/page.tsx` fed `MarketMapSection`'s `homeSpread` prop from
 * `event.current_odds?.home_spread` — a key `/api/events/{id}` has never
 * emitted; it serialises that column as `spread`. So the prop was `null` on
 * every render of the only page that mounts this component, the derived-spread
 * rung never once fired, and every `Pre-game` marker a reader has ever seen
 * came from the last resort: *whichever quoted rung priced closest to a coin
 * flip*.
 *
 * That fallback lands near the opening line often enough to look healthy,
 * which is why it survived so long. Measured on production, 2026-09-11:
 *
 *   | event                     | opened at | the tile showed |                |
 *   |---------------------------|-----------|-----------------|----------------|
 *   | 15310077 Cubs–Pirates     | **-1.5**  | `CHC by 1.5+`   | right BY LUCK  |
 *   | 15309206 Zverev–Khachanov | **-5.5**  | `ZVE by 2.5+`   | **wrong**      |
 *
 * ═══ WHY THE FIX IS NOT "SPELL THE KEY CORRECTLY" ═══
 *
 * `current_odds` is the LATEST snapshot, and three of this card's markers are
 * labelled `Pre-game` — two of them on games that have already been played.
 * Event 15310077's last snapshot was captured 21:00Z against an 18:20Z first
 * pitch, at `home_probability` 0.999 and `spread` **-7.9**, on a game that
 * opened at -1.5. Feeding that to a tile labelled PRE-GAME is a worse bug than
 * the one being fixed, so correcting the spelling ALONE would have been a
 * regression. The card takes `events.opening_*` — the last pre-game consensus,
 * frozen at first pitch — and the latest snapshot survives only on `pre`,
 * where the two tenses coincide.
 *
 * ═══ WHY TENNIS IS NOT GATED OUT ═══
 *
 * #2441 set `hasDerivedSpread: false` for tennis to stop this page INVENTING a
 * point spread over a sport with no points. `opening_home_spread` is not
 * invented: it is the median of the `spreads` market's home `point` across the
 * quoting books (`odds_polling._parse_snapshot_values` → `_maybe_set_opening_odds`),
 * and for tennis those books quote GAMES — the unit this file already declares
 * for tennis. 129 of 129 US Open ATP events carry one (measured 2026-09-11 over
 * 30 days). #2441's rule is "keep every market a venue actually quoted, lose
 * only the number we made up"; the opening line is the kept half. The unit
 * question tennis really does have is `scoreboardCountsTheUnit`, answered
 * elsewhere and unchanged by this file.
 *
 * ═══ WHAT EACH TEST IS FOR ═══
 *
 * The two specimens are the two rows of the table above, so the suite fails on
 * the exact pages Alex can open. The pick'em case guards the frontend twin of
 * the backend defect in the same commit: a spread of exactly `0.0` is falsy,
 * and every test between the payload and the marker is `!= null`. The last two
 * are CONTROLS — the rung fallback and the `pre`-status derived rung must both
 * survive, or "the fix" is just a deletion.
 */
import React from "react";
import { renderToStaticMarkup } from "react-dom/server";

import MarketMapSection from "@/components/MarketMapSection";

function visibleText(html: string): string {
  return html
    .replace(/<[^>]+>/g, " ")
    .replace(/&#x27;/g, "'")
    .replace(/&amp;/g, "&")
    .replace(/&[a-z]+;/g, " ")
    .replace(/\s+/g, " ")
    .trim();
}

const spreadRung = (matchup: string, outcome: string, probability: number) => ({
  market_name: `${matchup}: Game Spread`,
  outcome_name: outcome,
  threshold: null,
  probability,
  source: "kalshi",
  is_winner: null,
  resolution_source: null,
});

const totalRung = (matchup: string, threshold: number, overProbability: number) => ({
  threshold,
  over_probability: overProbability,
  source: "kalshi",
  market_type: "game_total",
  market_name: `${matchup}: Total Games`,
  outcome_name: `Over ${threshold} games`,
  is_winner: null,
  resolution_source: null,
  movement: 0,
  period: null,
});

/**
 * Event 15309206 — Zverev (home) v Khachanov (away), completed.
 *
 * The ladder is production's shape: three quoted game rungs, of which **-2.5**
 * prices nearest a coin flip. That is where `ZVE by 2.5+` came from, and it is
 * why this payload can tell the fixed card from the broken one — the two
 * answers, 5.5 and 2.5, are both present and both plausible.
 */
function zverevKhachanov(overrides: Record<string, unknown> = {}) {
  const m = "Alexander Zverev vs Karen Khachanov";
  return {
    event_id: 15309206,
    home_team: "Alexander Zverev",
    away_team: "Karen Khachanov",
    home_score: null,
    away_score: null,
    status: "completed",
    player_props: [],
    team_totals: [],
    period_markets: [],
    matchups: [],
    other: [],
    pace: null,
    props_script: [],
    spreads: [
      spreadRung(m, "Alexander Zverev -2.5 games", 0.52),
      spreadRung(m, "Alexander Zverev -5.5 games", 0.34),
      spreadRung(m, "Alexander Zverev -8.5 games", 0.19),
    ],
    // Priced so the three candidate answers for the totals rail are three
    // DIFFERENT rendered numbers, or its tests cannot tell them apart: the
    // opening total 38.5 → `39`, the latest snapshot 44 → `44`, and the
    // nearest-to-even quoted rung 34.5 → `35`. Monotone decreasing, as a real
    // ladder must be.
    totals: [
      totalRung(m, 34.5, 0.52),
      totalRung(m, 38.5, 0.30),
      totalRung(m, 42.5, 0.12),
    ],
    ...overrides,
  };
}

function renderZverev(props: Record<string, unknown> = {}, overrides: Record<string, unknown> = {}) {
  return visibleText(
    renderToStaticMarkup(
      <MarketMapSection
        gameMarkets={zverevKhachanov(overrides) as never}
        eventStatus="completed"
        homeTeam="Alexander Zverev"
        awayTeam="Karen Khachanov"
        homeAbbr="ZVE"
        awayAbbr="KHA"
        homeWinProb={0.7966}
        awayWinProb={0.2034}
        sportKey="tennis_atp_us_open"
        {...props}
      />
    )
  );
}

/**
 * A pick'em, the case the backend half of this commit also fixes. MLB so that
 * `hasDerivedSpread` is `true` and the derived rung is genuinely available —
 * a pick'em that read "Tied" only because every other rung was gated off would
 * prove nothing.
 */
function pickem(overrides: Record<string, unknown> = {}) {
  const m = "Chicago Cubs vs Pittsburgh Pirates";
  return {
    event_id: 15310077,
    home_team: "Chicago Cubs",
    away_team: "Pittsburgh Pirates",
    home_score: null,
    away_score: null,
    status: "scheduled",
    player_props: [],
    team_totals: [],
    period_markets: [],
    matchups: [],
    other: [],
    pace: null,
    props_script: [],
    spreads: [
      spreadRung(m, "Chicago Cubs -1.5", 0.41),
      spreadRung(m, "Pittsburgh Pirates -1.5", 0.38),
    ],
    totals: [totalRung(m, 8.5, 0.51)],
    ...overrides,
  };
}

function renderPickem(props: Record<string, unknown> = {}, eventStatus = "scheduled") {
  return visibleText(
    renderToStaticMarkup(
      <MarketMapSection
        gameMarkets={pickem({ status: eventStatus }) as never}
        eventStatus={eventStatus}
        homeTeam="Chicago Cubs"
        awayTeam="Pittsburgh Pirates"
        homeAbbr="CHC"
        awayAbbr="PIT"
        homeWinProb={0.5}
        awayWinProb={0.5}
        sportKey="baseball_mlb"
        {...props}
      />
    )
  );
}

describe("#5414 — the PRE-GAME tile reads the pre-game line", () => {
  it("THE DEFECT, reproduced: with no opening line the tile shows the coin-flip rung", () => {
    const text = renderZverev();
    // The card drew at all. Without this the assertion below could pass against
    // a map that never rendered.
    expect(text).toContain("Game margin map");
    expect(text).toContain("ZVE by 2.5+");
  });

  it("THE FIX: the served opening spread of -5.5 reaches the tile", () => {
    const text = renderZverev({ openingHomeSpread: -5.5 });
    // Read the MARKER, not the whole card: `ZVE by 5.5+` is also a ladder rung
    // on this payload, so a bare `toContain` would pass against the broken
    // card too. This is the tile beside the `Pre-game` label.
    expect(text).toMatch(/Pre-game\s+ZVE by 5\.5\+/);
    expect(text).not.toMatch(/Pre-game\s+ZVE by 2\.5\+/);
  });

  it("the opening spread outranks the latest snapshot's spread", () => {
    // -7.9 is what event 15310077's last snapshot actually held, captured after
    // first pitch. Whichever sport it is fed to, a `Pre-game` tile must not
    // show it when an opening line exists.
    const text = renderZverev({ openingHomeSpread: -5.5, homeSpread: -7.9 });
    expect(text).toMatch(/Pre-game\s+ZVE by 5\.5\+/);
    expect(text).not.toContain("ZVE by 7.9+");
  });

  it("a settled game never takes the latest snapshot's spread, even with no opening line", () => {
    // ⚠️ MLB, NOT the tennis specimen. On tennis this assertion passes with the
    // tense rule DELETED, because #2441 already gates the derived rung off for
    // a sport with `hasDerivedSpread: false` — the test would be vacuous and
    // would report a guard where there is none. A points sport is the only
    // payload on which the tense rule is the thing doing the work.
    //
    // What it guards: spelling `current_odds.spread` correctly — which this
    // commit does, after years of the prop reading a key the API never emitted
    // — would otherwise have switched this on for every played game, showing a
    // 0.999 blowout's -7.9 line under the word `Pre-game`.
    const text = renderPickem({ homeSpread: -7.9 }, "completed");
    expect(text).toContain("Run margin map");
    expect(text).not.toContain("CHC by 7.9+");
    expect(text).toMatch(/Pre-game\s+CHC by 1\.5\+/);
  });

  it("a PICK'EM opens at exactly 0.0 and reads as a line, not as no line", () => {
    const text = renderPickem({ openingHomeSpread: 0 });
    // `0` is falsy: under a truthiness test this falls through to the rung
    // fallback and the reader is told the market favoured the Cubs by 1.5.
    expect(text).toMatch(/Projection\s+Tied/);
    expect(text).not.toMatch(/Projection\s+CHC by 1\.5\+/);
  });

  it("CONTROL — no opening line, unplayed game: the derived rung still fires", () => {
    // `hasDerivedSpread` is true for MLB and the game has not started, so the
    // latest snapshot IS a pre-game quantity and is the best number available.
    // If this goes red the fix has become a deletion.
    const text = renderPickem({ homeSpread: -2.5 });
    expect(text).toMatch(/Projection\s+CHC by 2\.5\+/);
  });

  it("CONTROL — no line of any kind: the coin-flip rung fallback survives", () => {
    const text = renderPickem();
    expect(text).toMatch(/Projection\s+CHC by 1\.5\+/);
  });
});

describe("#5414 — the totals rail on the same card, fixed in the same pass", () => {
  it("THE FIX: the served opening total reaches the Pre-game marker", () => {
    // 44 is what a long five-setter's LATEST total looks like; the market
    // opened at 38.5. #3210's finding on this file is that fixing one rail and
    // leaving the other is worse than the bug, so this rail is here too.
    const text = renderZverev({ openingOverUnder: 38.5, overUnder: 44 });
    expect(text).toContain("Games map");
    expect(text).toMatch(/Pre-game\s+39/);
    expect(text).not.toMatch(/Pre-game\s+44/);
  });

  it("a settled card with no opening total takes a quoted rung, never the latest", () => {
    // The tense rule on this rail. `44` is on the payload and is the freshest
    // thing the card holds; under a `Pre-game` label it is still wrong, so the
    // marker falls to the nearest-to-even quoted rung, 34.5 → 35.
    const text = renderZverev({ overUnder: 44 });
    expect(text).not.toMatch(/Pre-game\s+44/);
    expect(text).toMatch(/Pre-game\s+35/);
  });

  it("the opening total is read by presence, so `??` cannot decay into `||`", () => {
    // No sport opens at a total of 0, so this is not a live defect the way the
    // spread pick'em is — it is here to PIN THE OPERATOR. The spread rail two
    // describes up really is hit by the falsy-zero class (7.2% of events), and
    // the two rails are eight lines apart; a later hand reaching for `||` on
    // one of them should not find this one unguarded.
    const text = renderZverev({ openingOverUnder: 0, overUnder: 44 });
    expect(text).toMatch(/Pre-game\s+0/);
  });

  it("CONTROL — an unplayed card still takes the latest total as its projection", () => {
    // Before first pitch the latest total IS a pre-game total, and it is
    // fresher than the opening one. If this goes red the tense rule has been
    // written as a deletion.
    const text = renderPickem({ overUnder: 9.5 });
    expect(text).toContain("Projected 10");
  });
});
