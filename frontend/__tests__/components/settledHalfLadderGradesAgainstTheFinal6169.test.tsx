/**
 * #6169 — A SETTLED HALF LADDER STOPS PRICING LINES THE HALF ALREADY CLEARED.
 *
 * Mystery-shopped on production 2026-09-14 at 390px, `/events/14637256`
 * (New York Giants 28 · Dallas Cowboys 20, SNF, Final at 03:28Z). The 2nd half
 * points map printed, on one card:
 *
 *   FINAL  27 points
 *   LAST QUOTE FOR GOING OVER
 *   Over 7.5   50%      Over 20.5  50%
 *   Over 10.5  50%      Over 21.5  50%
 *   Over 14.5  50%      Over 24.5  50%
 *   Over 17.5  50%      Over 38.5  50%
 *
 * Seven of those eight lines were cleared by a half that scored 27, and the card
 * says 27 in its own tile two inches above. The 1st half card beside it was
 * correct, so a reader saw one half graded honestly and the other calling every
 * settled line a coin flip.
 *
 * ═══ TWO DEFECTS, AND THIS SUITE IS THE RENDER ONE ═══
 *
 * The payload is separately wrong — `_enforce_monotonicity` capped six settled
 * `1.0` verdicts down to one stale rung, which is #6169's serving half in
 * `routes/events.py` (lane1b, merged `f0d9c759a`). This half is the render one,
 * and lane1b's own note is that either half alone removes the reader-visible
 * harm.
 *
 * It is the UNBUILT HALF OF #3769. That rule — *"on a settled match
 * `over_probability` is the RESOLVED price … so a done ladder grades against the
 * final instead of quoting it"* — was implemented for the full-game total card
 * (`gradeRung`, `MarketMapSection`) and never for the half cards, which built
 * their ladder with no `outcome` at all. So `ladderGraded()` was false for every
 * half card that has ever rendered, and a finished half could only ever quote.
 *
 * ═══ WHY THE GRADE IS THE SCORE AND NOT THE PRICE ═══
 *
 * The grade never consults `over_probability` or `is_winner`. It is decided by
 * the half's own score, gated on the same `isDone && halfScores` the FINAL
 * marker is gated on — #3769's rule that the ladder grades exactly when the card
 * draws the number it grades against, and #3210's that a sentence promises a
 * comparison exactly when the rail draws one.
 *
 * That is what makes this half independent of the serving half: the card reads
 * correctly whether the payload is still capping the rungs to 0.5 (as production
 * served it when this was shot) or serving the settled verdicts. Both payloads
 * are arms below and both must grade identically.
 *
 * ═══ WHAT MAKES THIS SUITE NON-VACUOUS ═══
 *
 * "No 50%" is also what a card that never rendered looks like, so every arm
 * renders the REAL `MarketMapSection` and asserts the card is STILL THERE by
 * title and still naming every rung. The controls differ from the defect arms in
 * ONE input each: the prices (kills a fix keyed on the payload), the event status
 * (kills a fix missing `isDone`), the ESPN history (kills a fix that grades
 * without the number it grades against), and the threshold above the final
 * (kills a fix that grades everything `cleared`).
 *
 * Every number below is production's, read from
 * `/api/events/14637256/game-markets` and `/api/events/14637256/history` at
 * 2026-09-14 17:5xZ: halftime 14-7, final 28-20, so 1H = 21 and 2H = 27.
 */

import React from "react";
import { renderToStaticMarkup } from "react-dom/server";

import MarketMapSection from "@/components/MarketMapSection";
import { ladderGraded } from "@/components/MarketMap";
import { quotedLinesPhrase, settledLinesPhrase } from "@/lib/marketMapUtils";

function visibleText(html: string): string {
  return html
    .replace(/<[^>]+>/g, " ")
    .replace(/&#x27;|&#39;|&apos;/g, "'")
    .replace(/&amp;/g, "&")
    .replace(/&[a-z]+;/g, " ")
    .replace(/\s+/g, " ")
    .trim();
}

/** How many summary tiles of this kind the section drew. */
function tileCount(html: string, key: string): number {
  return html.split(`data-tile="${key}"`).length - 1;
}

/**
 * Each rung's verdict, bounded by the NEXT rung's label rather than by a
 * character count.
 *
 * A fixed window is the trap here and this suite fell into it once: `Over 24.5
 * cleared Over 38.5 not cleared` is 39 characters, so a 40-char window read the
 * following row's verdict back onto this one. And `toContain("cleared")` is
 * satisfied by `"not cleared"`, so the two mistakes cancel and a wrong grade
 * scores as a pass. Exact strings, exact bounds.
 */
function verdictsOf(text: string, rungs: Rung[]): string[] {
  const body = text.slice(text.indexOf("Each line vs the final"));
  return rungs.map(([t], i) => {
    const at = body.indexOf(`Over ${t} `);
    if (at < 0) return `${t}:absent`;
    const next = i + 1 < rungs.length ? body.indexOf(`Over ${rungs[i + 1][0]} `, at) : -1;
    const cell = body.slice(at + `Over ${t} `.length, next < 0 ? undefined : next).trim();
    return `${t}:${cell}`;
  });
}

type Rung = [threshold: number, overProbability: number];

/**
 * `/events/14637256` 2H **exactly as production served it** — eight rungs, all
 * capped to 0.5, seven of them `is_winner: true`. This is the payload behind the
 * photograph.
 */
const SNF_2H_CAPPED: Rung[] = [
  [7.5, 0.5],
  [10.5, 0.5],
  [14.5, 0.5],
  [17.5, 0.5],
  [20.5, 0.5],
  [21.5, 0.5],
  [24.5, 0.5],
  [38.5, 0.5],
];

/**
 * The same eight rungs as the DATABASE holds them, and as the serving half
 * (`f0d9c759a`) makes the payload serve them once it is live. Same card, same
 * score, and the grade below must not notice the difference.
 */
const SNF_2H_SETTLED: Rung[] = [
  [7.5, 1.0],
  [10.5, 1.0],
  [14.5, 1.0],
  [17.5, 1.0],
  [20.5, 1.0],
  [21.5, 1.0],
  [24.5, 1.0],
  [38.5, 0.0],
];

/** `/events/14637256` 1H as served — the card that was already right. 1H = 21. */
const SNF_1H: Rung[] = [
  [7.5, 1.0],
  [10.5, 1.0],
  [14.5, 1.0],
  [17.5, 1.0],
  [20.5, 1.0],
];

/**
 * A synthetic pair straddling the 27-point half, for the boundary. Not a
 * production ladder and not claimed as one: it exists to pin the comparison's
 * direction and to prove the tile and the grade read ONE number.
 */
const STRADDLE_2H: Rung[] = [
  [26.5, 0.5],
  [27.5, 0.5],
];

/**
 * A rung sitting EXACTLY on the 27-point half. Venues quote totals at `.5`
 * precisely so this cannot happen, so this is not claimed as a production
 * ladder — it exists because without it `>` and `>=` grade every fixture in
 * this file identically and the comparison is untested. `Over 27` on a 27-point
 * half did not go over.
 */
const ON_THE_NUMBER_2H: Rung[] = [
  [26, 0.5],
  [27, 0.5],
  [28, 0.5],
];

const HOME = "New York Giants";
const AWAY = "Dallas Cowboys";

/** Production's own history rows: halftime 14-7, final 28-20. */
const ESPN_HISTORY = [
  { period: "1st Quarter", home_score: 0, away_score: 0, timestamp: "2026-09-14T00:20:00+00:00" },
  { period: "Halftime", home_score: 14, away_score: 7, timestamp: "2026-09-14T01:30:00+00:00" },
  { period: "Final", home_score: 28, away_score: 20, timestamp: "2026-09-14T03:28:00+00:00" },
];

function half(period: "1H" | "2H", rungs: Rung[]) {
  const label = period === "1H" ? "1st" : "2nd";
  return rungs.map(([threshold, over]) => ({
    market_name: `DAL Cowboys vs NY Giants: ${label} Half Total`,
    outcome_name: `Over ${threshold} ${period} points scored`,
    threshold,
    probability: null,
    market_type: "half_total",
    over_probability: over,
    period,
    source: "kalshi",
    // Deliberately the production values: the grade must not read them.
    is_winner: true,
    resolution_source: "api_settlement",
    movement: 0,
  }));
}

function markets(period: "1H" | "2H", rungs: Rung[]) {
  return {
    event_id: 14637256,
    home_team: HOME,
    away_team: AWAY,
    home_score: 28,
    away_score: 20,
    status: "completed",
    player_props: [],
    team_totals: [],
    period_markets: half(period, rungs),
    matchups: [],
    other: [],
    pace: null,
    props_script: [],
    spreads: [],
    totals: [],
  };
}

/**
 * The section as the finished event page mounts it, holding ONE half's ladder.
 * No `spreads` and no `totals`, so the only card in the markup is that half's
 * points map and every percentage below belongs to it.
 */
function renderMap(
  period: "1H" | "2H",
  rungs: Rung[],
  opts: { eventStatus?: string; espnHistory?: typeof ESPN_HISTORY } = {}
): string {
  return renderToStaticMarkup(
    <MarketMapSection
      gameMarkets={markets(period, rungs) as never}
      eventStatus={opts.eventStatus ?? "completed"}
      homeTeam={HOME}
      awayTeam={AWAY}
      homeAbbr="NYG"
      awayAbbr="DAL"
      sportKey="americanfootball_nfl"
      espnHistory={"espnHistory" in opts ? opts.espnHistory : ESPN_HISTORY}
    />
  );
}

const cardTitle = (period: "1H" | "2H") =>
  period === "1H" ? "1st half points map" : "2nd half points map";

describe("#6169 the settled half ladder grades instead of quoting", () => {
  it("prints no price at all on the card Alex would have read", () => {
    const html = renderMap("2H", SNF_2H_CAPPED);
    const text = visibleText(html);

    // The card is still here, with all eight rungs named. This is what makes
    // the absence below an assertion rather than a description of a card that
    // vanished.
    expect(text).toContain(cardTitle("2H"));
    for (const [t] of SNF_2H_CAPPED) expect(text).toContain(`Over ${t}`);

    // The photograph, gone: seven cleared lines and the one that was not.
    expect(text).toContain("Each line vs the final");
    expect(text).not.toContain("Last quote for going over");
    expect(text).not.toContain("50%");
    expect(text).not.toContain("%");

    // And the tile it contradicted is still on the card, still reading 27.
    expect(tileCount(html, "final")).toBe(1);
    expect(text).toContain("27 points");
  });

  it("grades each of the eight lines the way a 27-point half decided it", () => {
    // Seven cleared, one not — per rung, in order, as exact cell contents.
    expect(verdictsOf(visibleText(renderMap("2H", SNF_2H_CAPPED)), SNF_2H_CAPPED)).toEqual([
      "7.5:cleared",
      "10.5:cleared",
      "14.5:cleared",
      "17.5:cleared",
      "20.5:cleared",
      "21.5:cleared",
      "24.5:cleared",
      "38.5:not cleared",
    ]);
  });

  it("CONTROL: the corrected payload grades identically — the score decides, not the price", () => {
    // The serving half of #6169 (`f0d9c759a`) turns SNF_2H_CAPPED into
    // SNF_2H_SETTLED. Same event, same score, eight rungs moved from 0.5 to
    // 1.0/0.0. A render fix that read `over_probability` — or `is_winner`,
    // which is `true` on every row of both fixtures including the rung that
    // did NOT clear — gives a different answer here and fails.
    const capped = verdictsOf(visibleText(renderMap("2H", SNF_2H_CAPPED)), SNF_2H_CAPPED);
    const settled = verdictsOf(visibleText(renderMap("2H", SNF_2H_SETTLED)), SNF_2H_SETTLED);

    expect(settled).toEqual(capped);
    expect(settled).toEqual([
      "7.5:cleared",
      "10.5:cleared",
      "14.5:cleared",
      "17.5:cleared",
      "20.5:cleared",
      "21.5:cleared",
      "24.5:cleared",
      "38.5:not cleared",
    ]);
    // Non-vacuity: the two fixtures really are different payloads, so the
    // equality above is a claim and not a tautology about one input.
    expect(SNF_2H_SETTLED).not.toEqual(SNF_2H_CAPPED);
  });

  it("CONTROL: the boundary is strictly above, and the tile and the grade read one number", () => {
    // 26.5 and 27.5 around a half that scored exactly 27. A card whose tile
    // says 27 while its ladder flips somewhere else is the defect this ship is
    // about, in the opposite direction.
    const html = renderMap("2H", STRADDLE_2H);
    const text = visibleText(html);

    expect(text).toContain("27 points");
    expect(text.slice(text.indexOf("Over 26.5"), text.indexOf("Over 27.5"))).toContain("cleared");
    expect(text.slice(text.indexOf("Over 26.5"), text.indexOf("Over 27.5"))).not.toContain(
      "not cleared"
    );
    expect(text.slice(text.indexOf("Over 27.5"))).toContain("not cleared");
  });

  it("CONTROL: a line ON the final did not go over it", () => {
    // The only arm that distinguishes `>` from `>=`. Every other ladder here is
    // quoted at `.5` against an integer score, so the two comparisons agree
    // everywhere else and a mutant swapping them survives the whole file.
    expect(
      verdictsOf(visibleText(renderMap("2H", ON_THE_NUMBER_2H)), ON_THE_NUMBER_2H)
    ).toEqual(["26:cleared", "27:not cleared", "28:not cleared"]);
  });

  it("grades the 1st half card too, against ITS half and not the game's", () => {
    // 1H scored 21, and all five of its rungs are below that. The game scored
    // 48; a fix that graded halves against the full-game total agrees here and
    // is caught by the 2nd-half arms above, where 48 clears 38.5 and 27 does
    // not. Both cards are asserted so neither can be fixed alone.
    const text = visibleText(renderMap("1H", SNF_1H));

    expect(text).toContain(cardTitle("1H"));
    expect(text).toContain("Each line vs the final");
    expect(text).toContain("21 points");
    expect(text).not.toContain("not cleared");
    expect(text).not.toContain("%");
  });

  it("CONTROL: before the whistle the ladder still quotes", () => {
    // The side of the rule this ship makes no claim about. A scheduled game has
    // no final to grade against, and the same eight rungs must read as chances.
    const text = visibleText(renderMap("2H", SNF_2H_CAPPED, { eventStatus: "scheduled" }));

    expect(text).toContain(cardTitle("2H"));
    expect(text).toContain("Chance of going over");
    expect(text).toContain("50%");
    expect(text).not.toContain("cleared");
  });

  it("CONTROL: a finished game with no half scores quotes, because the card draws no number", () => {
    // 🔴 The gate, and the reason it is the marker's gate and not `isDone`.
    // `halfScores` comes from ESPN's halftime row; without it this card draws
    // no FINAL tile, so there is nothing on it to grade against and nothing for
    // a reader to check the grade with. #3769's own rule. A fix gated on
    // `isDone` alone passes every arm above and fails here — and it would be
    // grading against a number it invented.
    const html = renderMap("2H", SNF_2H_CAPPED, { espnHistory: undefined });
    const text = visibleText(html);

    expect(text).toContain(cardTitle("2H"));
    expect(tileCount(html, "final")).toBe(0);
    expect(text).toContain("Last quote for going over");
    expect(text).toContain("50%");
    expect(text).not.toContain("cleared");
  });
});

describe("#6169 the sentence over the ladder moves with the ladder", () => {
  it("stops calling eight graded rows quotes", () => {
    // A graded ladder prints no percentage at all, so "Eight lines quoted" over
    // eight `cleared` rows named a thing the reader cannot see — one card in two
    // tenses, which is exactly what #3210 fixed on the card above this one.
    const text = visibleText(renderMap("2H", SNF_2H_CAPPED));

    expect(text).toContain(settledLinesPhrase(8));
    expect(text).toContain("Eight lines settled");
    expect(text).not.toContain(quotedLinesPhrase(8));
    expect(text).not.toContain("quoted");
  });

  it("CONTROL: an ungraded ladder on the same card still says quoted", () => {
    // Same eight rungs, same flat band, only the grade withdrawn. A fix that
    // renamed the sentence outright rather than binding it to `ladderGraded`
    // passes the arm above and fails here.
    const text = visibleText(renderMap("2H", SNF_2H_CAPPED, { espnHistory: undefined }));

    expect(text).toContain(quotedLinesPhrase(8));
    expect(text).not.toContain(settledLinesPhrase(8));
  });

  it("the two phrases differ only in the verb, for every count", () => {
    // Non-vacuity for the pair: if someone makes them the same string, both
    // assertions above still pass and the card learns nothing.
    for (let n = 0; n <= 10; n++) {
      expect(settledLinesPhrase(n)).toBe(quotedLinesPhrase(n).replace(/quoted$/, "settled"));
      expect(settledLinesPhrase(n)).not.toBe(quotedLinesPhrase(n));
    }
    expect(settledLinesPhrase(1)).toBe("One line settled");
    expect(settledLinesPhrase(8)).toBe("Eight lines settled");
  });
});

describe("#6169 ladderGraded is what decides, and it is all-or-nothing", () => {
  it("a half ladder now satisfies the predicate the heading reads", () => {
    // #3769 made `ladderGraded` all-or-nothing precisely so one ladder cannot
    // print `cleared` beside `50%`. Before this ship no half ladder could ever
    // satisfy it, because none carried an `outcome` at all.
    const rungs = SNF_2H_CAPPED.map(([t]) => ({
      label: `Over ${t}`,
      probability: 50,
      side: "right" as const,
      outcome: (27 > t ? "cleared" : "missed") as "cleared" | "missed",
    }));

    expect(ladderGraded(rungs)).toBe(true);
    expect(ladderGraded(rungs.map((r, i) => (i === 3 ? { ...r, outcome: undefined } : r)))).toBe(
      false
    );
  });
});
