/**
 * #6199 — a BAND of margins is not a rung on a threshold rail. Web half of #3788.
 *
 * ── THE DEFECT ───────────────────────────────────────────────────────────────
 *
 * `/events/14637256`, Giants 28 Cowboys 20 — FINAL, won by 8. The full-game
 * margin rail carried:
 *
 *     New York Giants by 14+     100%
 *
 * That row is `"New York G wins by 7 to 14 points"`, from Kalshi's separate
 * `…: Winning Margin` market. It is a BAND, bounded at both ends. The backend
 * files it under `spreads` beside the `…: Spread` cover ladder, and
 * `isFullGameSpread` excludes halves and nothing else, so both reach one rail.
 * `parseSpreadOutcome` then took the LAST number in the name as the threshold,
 * so the band's UPPER edge became the line — and on a settled game the band row
 * served is the WINNING one at `probability: 1.0`, so its mass rode onto a
 * cover line that did not come in.
 *
 * A `ParsedSpread` makes ONE claim: this side by more than `threshold`, at this
 * probability. `P(margin is 7 to 14)` is not that claim, and the upper bound is
 * the entire point of the market.
 *
 * ── WHY THE GUARD READS THE OUTCOME AND NOT THE MARKET NAME ──────────────────
 *
 * The `Winning Margin` market serves TWO shapes, and only one of them is wrong:
 *
 *     "wins by 7 to 14 points"      bounded BOTH ends  -> not a rung
 *     "wins by 15 or more points"   bounded ONE end    -> IS a cover claim
 *
 * #3788 ruled the second one stays, deliberately. Both come from the same
 * market, so a guard keyed on the market name would drop the honest row with
 * the dishonest one. The controls below are that ruling, and they are real
 * controls: they exercise the same call on the same rail and assert the rung
 * SURVIVES. If this file ever goes green with those rungs gone, the guard has
 * widened past its class and every NFL margin map is losing quoted lines.
 *
 * ── MEASURED, 2026-09-14, ALL EIGHT COMPLETED NFL EVENTS ─────────────────────
 *
 * Six of eight carried a bounded band row; four rendered a rung at 100% for a
 * margin that did not happen (`14637256 +8` -> `by 14+`, `14780150 +2` ->
 * `by 6+`, `14780147 -12` -> `by 14+`, `14780139 +7` -> `by 14+`). On
 * `14780150` the rail had TWO rungs and this was one of them.
 */
import React from "react";
import { renderToStaticMarkup } from "react-dom/server";

import MarketMapSection from "@/components/MarketMapSection";
import { parseSpreadOutcome } from "@/lib/marketMapUtils";

function visibleText(html: string): string {
  return html
    .replace(/<[^>]+>/g, " ")
    .replace(/&#x27;/g, "'")
    .replace(/&amp;/g, "&")
    .replace(/&[a-z]+;/g, " ")
    .replace(/\s+/g, " ")
    .trim();
}

const rung = (outcome: string) =>
  parseSpreadOutcome(outcome, 1.0, "kalshi", "New York Giants", "Dallas Cowboys");

/**
 * Event 14637256 as production served it on 2026-09-14, trimmed to the fields
 * these maps read. The band row sits in source order where production put it,
 * between the 6.5 and 7.5 cover lines — it is not the first or last row, so a
 * fix that merely reordered the ladder could not pass this.
 */
function giantsCowboys(overrides: Record<string, unknown> = {}) {
  const spread = (outcome: string, marketName: string) => ({
    market_name: marketName,
    outcome_name: outcome,
    threshold: null,
    probability: 1.0,
    source: "kalshi",
    is_winner: true,
    resolution_source: "api_settlement",
  });
  const cover = (n: string) =>
    spread(`New York G wins by over ${n} points`, "Dallas vs New York: Spread");
  return {
    event_id: 14637256,
    home_team: "New York Giants",
    away_team: "Dallas Cowboys",
    home_score: 28,
    away_score: 20,
    status: "completed",
    player_props: [],
    team_totals: [],
    period_markets: [],
    matchups: [],
    other: [],
    pace: null,
    props_script: [],
    spreads: [
      cover("1.5"),
      cover("2.5"),
      cover("3.5"),
      cover("4.5"),
      cover("5.5"),
      cover("6.5"),
      spread(
        "New York G wins by 7 to 14 points",
        "Dallas vs New York G: Winning Margin"
      ),
      cover("7.5"),
    ],
    totals: [],
    ...overrides,
  };
}

function renderGame(overrides: Record<string, unknown> = {}) {
  return visibleText(
    renderToStaticMarkup(
      <MarketMapSection
        gameMarkets={giantsCowboys(overrides) as never}
        eventStatus="completed"
        homeTeam="New York Giants"
        awayTeam="Dallas Cowboys"
        homeAbbr="NYG"
        awayAbbr="DAL"
        homeWinProb={1.0}
        awayWinProb={0.0}
        homeSpread={-3.5}
        overUnder={44.5}
        sportKey="americanfootball_nfl"
      />
    )
  );
}

describe("#6199 — a bounded margin band is not a rung", () => {
  it("THE DEFECT: the settled rail no longer claims a margin that did not happen", () => {
    const text = renderGame();
    // The card really rendered. Without this the absence below could be the
    // absence of the whole map rather than the absence of the band rung.
    expect(text).toContain("Margin: expected vs final");
    // The Giants won by 8. `by 14+` was drawn at 100%.
    expect(text).not.toContain("NYG by 14+");
    // ...and the honest cover lines the same rail draws are still there, so
    // this is a dropped ROW and not a dropped RAIL.
    expect(text).toContain("NYG by 7.5+");
    expect(text).toContain("NYG by 1.5+");
  });

  it("refuses both band spellings production serves", () => {
    expect(rung("New York G wins by 7 to 14 points")).toBeNull();
    expect(rung("New York G wins by 1 to 6 points")).toBeNull();
  });

  it("refuses the same claim written with a dash", () => {
    expect(rung("New York G wins by 7-14 points")).toBeNull();
    expect(rung("New York G wins by 1–6 points")).toBeNull();
  });

  /* ── CONTROLS. #3788 ruled each of these stays a rung. ──────────────────── */

  it("CONTROL: 'or more' is bounded at ONE end, so it survives as a cover claim", () => {
    const r = rung("New York G wins by 15 or more points");
    expect(r).not.toBeNull();
    expect(r!.threshold).toBe(15);
    expect(r!.isHome).toBe(true);
  });

  it("CONTROL: an ordinary cover line survives", () => {
    const r = rung("New York G wins by over 7.5 points");
    expect(r).not.toBeNull();
    expect(r!.threshold).toBe(7.5);
  });

  it("CONTROL: a signed spread survives — the dash arm must not reach it", () => {
    const lakers = parseSpreadOutcome(
      "Los Angeles Lakers -4.5",
      0.5,
      "kalshi",
      "Los Angeles Lakers",
      "Boston Celtics"
    );
    expect(lakers).not.toBeNull();
    expect(lakers!.threshold).toBe(4.5);

    const shelton = parseSpreadOutcome(
      "Ben Shelton -1.5 games",
      0.5,
      "kalshi",
      "Frances Tiafoe",
      "Ben Shelton"
    );
    expect(shelton).not.toBeNull();
    expect(shelton!.threshold).toBe(1.5);
  });

  /**
   * SYNTHETIC, and labelled as such: no production row looks like this today.
   *
   * It is here because the `by <digits>` anchor is otherwise unkillable — drop
   * it from the pattern and every other test in this file still passes, because
   * nothing in today's data distinguishes "a range of margins" from "a range of
   * digits". The anchor is what keeps the refusal pointed at a MARGIN claim, so
   * a ticker-derived name carrying a date would still yield its rung rather
   * than being silently dropped as a band. That is the whole reason the rule is
   * written as `by 7 to 14` and not as `7 to 14`.
   */
  it("CONTROL (synthetic): a digit range that is not a margin claim keeps its rung", () => {
    const dated = parseSpreadOutcome(
      "New York G (2026-09-14) wins by over 3.5 points",
      0.5,
      "kalshi",
      "New York Giants",
      "Dallas Cowboys"
    );
    expect(dated).not.toBeNull();
    // 3.5, not 14: the date must not become the line either. Written this way
    // deliberately — putting the range LAST would have made the expected value
    // the date's own digits, which is a different defect and not this ship's.
    expect(dated!.threshold).toBe(3.5);
  });

  it("CONTROL: a band on the AWAY side is refused too, and its cover lines are not", () => {
    const away = (o: string) =>
      parseSpreadOutcome(o, 1.0, "kalshi", "Carolina Panthers", "Arizona Cardinals");
    expect(away("Arizona wins by 7 to 14 points")).toBeNull();
    const cover = away("Arizona wins by over 7.5 points");
    expect(cover).not.toBeNull();
    expect(cover!.isHome).toBe(false);
  });
});
