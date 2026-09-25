// #6144 — A LIVE GAME WITH NO SCORE FEED STOPS HEADING A BETTING PROJECTION
// "SCORE DIFFERENTIAL".
//
// ── WHAT THE READER SAW ──────────────────────────────────────────────────────
//
// `/events/15311956` — Hanshin Tigers v Chunichi Dragons, NPB — seen live by
// live/226 at 11:41Z ~2h45m in, and re-read here at 12:30Z once the game had
// been suspended. Frames: `artifacts-live-227/npb-live-15311956.png` and
// `artifacts/ux-1259/before-slice-02.png`.
//
// The page says LIVE. There is **no score and no inning anywhere on it**. Below
// the win-probability curve sits a card headed, in the largest type on it,
// **"Score Differential"**, containing one green line that falls from +1 to
// −5.5 on a TIGERS/DRAGONS axis labelled `+7 / +4 / +1 / −2 / −5 / −8`.
//
// A casual fan reads that as *"Dragons lead by 5 runs."* It is not a score. It
// is the sportsbooks' projected margin, and the only thing that says so is the
// grey legend "Projected margin" under the chart. The reader prices the
// heading.
//
// ── THE POPULATION DOES NOT DRAIN ────────────────────────────────────────────
//
// Every one of the 36 rows at `status='live'` at 12:28Z carried NULL
// `home_score`, `away_score`, `period`, `game_clock` and `espn_id` — 18 tennis,
// 1 esports, 1 soccer, plus the NPB games earlier in the day. Not a race:
// `statpal_livescores` is healthy and its door only ever reaches
// NFL/MLB/NBA/NHL. For these sports in-game never brings a score, so the card
// is permanently the masquerade rather than briefly one.
//
// ── WHY THE NAME MOVED AND THE GATE DID NOT ──────────────────────────────────
//
// The page's own L2-157 Item 4 note names this render — "a projected-spread
// line masquerading as innings" — and suppresses the card PREGAME, on the
// assumption that in-game implies an actual score. Extending that suppression
// is the wrong half to move:
//
//   * in-game the projection is CONTENT (it moved 5.5 runs over 2h45m on this
//     specimen) and is the only read the page has on how the game is going for
//     a sport whose score we cannot fetch;
//   * ux/1034 B5 already ruled the opposite way on this same card for tennis —
//     "the widget keeps its projection, and STOPS DRAWING A LINE IN THE WRONG
//     UNIT" — so a suppression here would silently reverse a shipped decision
//     on 18 of today's 36 live rows.
//
// So the card is named after the series it actually draws. The unit comes from
// `sportVocab`, which already titles this exact quantity for the margin map
// directly below it ("Run margin map"), so one page cannot call one number two
// things — and an undeclared sport gets no unit this code invented.
//
// ── WHAT MUST NOT MOVE, AND IS ASSERTED BELOW ────────────────────────────────
//
// Renaming the heading unconditionally satisfies the ship assertion and is
// wrong, so the controls are load-bearing:
//
//   * A CARD THAT DRAWS THE PLAYED SCORE IS STILL "Score Differential". The
//     settled Panthers–Bears wire — Carolina 37, Chicago 59, Final, with real
//     score and ESPN points on it — is the control, and it must not be renamed.
//   * THE HEADING IS KEYED ON THE DATA, NOT THE SPORT. The load-bearing arm is
//     differential: the identical NPB bytes with one score point added must
//     flip the heading. A fix keyed on the sport key, on `status`, or on
//     "baseball has no espn_id" passes the ship assertion and fails that one.
//   * THE HEADING AND THE CHART AGREE. The point of the rename is that the name
//     matches the series; a heading computed from one predicate and a line
//     gated on another is the same defect with an extra step. Both arms assert
//     the heading beside the chart's own `data-actual-series` on one payload.
//   * THE CARD STILL DRAWS. A suppression is not what shipped, and a blanked
//     widget would pass the ship assertion for the worst possible reason.
//   * TENNIS KEEPS ux/1034 B5's ANSWER. A tennis page HOLDS `score_history` —
//     and those points are SETS under a games axis, so no actual line is drawn.
//     A heading keyed on "is there score history" rather than "is a score
//     drawn" would put "Score Differential" over a scoreless tennis card.

import React from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { readFileSync } from "fs";
import { join } from "path";

import ScoreDifferentialChart from "@/components/ScoreDifferentialChart";
import {
  actualScoreSeriesDrawn,
  scoreDifferentialHeading,
} from "@/lib/scoreDifferentialHeading";

/** `GET /api/events/15311956/history`, 12:30Z, verbatim in every field this
 *  component is handed. The page-level keys it is never passed
 *  (`win_prob_history`, `aggregate_line`, …) are dropped; nothing the chart
 *  reads is trimmed, sampled or rounded. */
const NPB = JSON.parse(
  readFileSync(
    join(__dirname, "fixtures/scoreDiffHeading.15311956.npb.json"),
    "utf8"
  )
);

/** The control: `GET /api/events/14780142/history`, 12:40Z — Carolina 37,
 *  Chicago 59, Final. A real page that DOES hold the played score, so it is the
 *  arm a blanket rename fails.
 *
 *  TRIMMED, and named for it. The wire carries 340 history, 55 score and 175
 *  ESPN points (855 kB); this is the LAST SIX of each, values verbatim, with
 *  `bookmaker_history` dropped. Nothing here turns on the counts — the claim is
 *  that a real played score is present — and the tail is the part that carries
 *  the final 37–59. */
const SETTLED_NFL = JSON.parse(
  readFileSync(
    join(__dirname, "fixtures/scoreDiffHeading.14780142.nfl-settled.tail6.json"),
    "utf8"
  )
);

const EVENT_PAGE_SOURCE = readFileSync(
  join(__dirname, "../app/events/[id]/page.tsx"),
  "utf8"
);
const CHART_SOURCE = readFileSync(
  join(__dirname, "../components/ScoreDifferentialChart.tsx"),
  "utf8"
);

/** `GET /api/events/15310688/history`, 14:25Z — Alexander Zverev 3, Ben
 *  Shelton 1, US Open, `status: "completed"`. The composition specimen int356
 *  asked for at 13:29Z: a SETTLED game with no drawn score, where #6142's
 *  withholding rule and #6144's naming rule are both live on one payload.
 *
 *  Same 14 keys as the NPB fixture, verbatim — nothing the chart reads is
 *  trimmed, sampled or rounded; only the page-level keys the component is never
 *  handed (`win_prob_history`, `aggregate_line`, …) are dropped. */
const SETTLED_TENNIS = JSON.parse(
  readFileSync(
    join(__dirname, "fixtures/scoreDiffHeading.15310688.tennis-settled.json"),
    "utf8"
  )
);

/** #6142's own settled wire, reused rather than re-captured: the same
 *  Panthers–Bears game, captured while its `implied_spreads` still carried a
 *  `kalshi` arm — the arm #6142 withholds on a final. The tail-6 fixture above
 *  was captured later, after that arm had gone, so it cannot stand in here. */
const SETTLED_WITH_KALSHI_ARM = JSON.parse(
  readFileSync(
    join(__dirname, "fixtures/impliedSpread.14780142.settled.json"),
    "utf8"
  )
);

/** Event 15293830's `score_history` (ux/1034 B5's subject): four points, and
 *  they are SETS, under a chart whose axis is in games. */
const TENNIS_SET_SCORE_HISTORY = [
  { timestamp: "2026-09-02T18:39:13Z", home_score: 0, away_score: 0 },
  { timestamp: "2026-09-02T21:03:07Z", home_score: 0, away_score: 1 },
  { timestamp: "2026-09-02T21:40:06Z", home_score: 0, away_score: 2 },
  { timestamp: "2026-09-02T22:11:48Z", home_score: 0, away_score: 3 },
];

/** The wrapper attribute the chart reports its drawn series on. recharts draws
 *  nothing inside `ResponsiveContainer` without a viewport, so a server render
 *  — all a guard can see — cannot observe the `<Line>` itself. Same channel
 *  ux/1034 B5 and #6142 use. */
function seriesAttr(markup: string, attr: string): string | null {
  const m = markup.match(new RegExp(`${attr}="([^"]*)"`));
  return m ? m[1] : null;
}

function renderChart(
  wire: Record<string, unknown>,
  sportKey: string,
  overrides: Record<string, unknown> = {}
): string {
  return renderToStaticMarkup(
    React.createElement(ScoreDifferentialChart, {
      history: wire.history as never,
      homeTeam: wire.home_team as string,
      awayTeam: wire.away_team as string,
      commenceTime: wire.commence_time as string,
      scoreHistory: wire.score_history as never,
      espnHistory: wire.espn_history as never,
      bookmakerHistory: wire.bookmaker_history as never,
      eventStatus: wire.status as string,
      sportKey,
      pmSpreadData: wire.pm_spread_data as never,
      ...overrides,
    } as never)
  );
}

/** What the page computes, from the same two calls, in the same order. */
function headingFor(
  wire: Record<string, unknown>,
  sportKey: string,
  overrides: { scoreHistory?: unknown; espnHistory?: unknown } = {}
): string {
  return scoreDifferentialHeading({
    sportKey,
    actualSeriesDrawn: actualScoreSeriesDrawn({
      sportKey,
      scoreHistory: (overrides.scoreHistory ?? wire.score_history) as never,
      espnHistory: (overrides.espnHistory ?? wire.espn_history) as never,
    }),
  });
}

describe("#6144 — the rule itself", () => {
  it("names the market's line after the market, in the margin map's own unit", () => {
    expect(
      scoreDifferentialHeading({ sportKey: "baseball_npb", actualSeriesDrawn: false })
    ).toBe("Projected Run Margin");
    expect(
      scoreDifferentialHeading({ sportKey: "tennis_atp", actualSeriesDrawn: false })
    ).toBe("Projected Game Margin");
    expect(
      scoreDifferentialHeading({ sportKey: "soccer_other", actualSeriesDrawn: false })
    ).toBe("Projected Goal Margin");
  });

  it("invents no unit for a sport nobody has declared", () => {
    // `UNSCORED_IN_POINTS.unitSingular` is deliberately empty, and every
    // template that interpolates it has to survive that — inline, this one
    // would read "Projected  Margin".
    expect(
      scoreDifferentialHeading({ sportKey: "esports", actualSeriesDrawn: false })
    ).toBe("Projected Margin");
    expect(
      scoreDifferentialHeading({ sportKey: undefined, actualSeriesDrawn: false })
    ).toBe("Projected Margin");
  });

  it("keeps the name a card that draws the played score has always had", () => {
    for (const sportKey of ["baseball_npb", "americanfootball_nfl", "esports", undefined]) {
      expect(
        scoreDifferentialHeading({ sportKey, actualSeriesDrawn: true })
      ).toBe("Score Differential");
    }
  });

  it("reads an actual series only where one is really drawn", () => {
    // Present, absent, and the two shapes of empty.
    expect(
      actualScoreSeriesDrawn({
        sportKey: "baseball_npb",
        scoreHistory: [{ home_score: 1, away_score: 0 }],
      })
    ).toBe(true);
    expect(
      actualScoreSeriesDrawn({ sportKey: "baseball_npb", scoreHistory: [], espnHistory: [] })
    ).toBe(false);
    expect(actualScoreSeriesDrawn({ sportKey: "baseball_npb" })).toBe(false);
    expect(
      actualScoreSeriesDrawn({ sportKey: "baseball_npb", scoreHistory: null, espnHistory: null })
    ).toBe(false);
  });

  it("does not count an ESPN row whose scores are null", () => {
    // `espn_history` carries a row per poll; the score fields are nullable and
    // are null for exactly the sports this issue is about. A `.length > 0` test
    // on that array would read those as a score and re-open the defect.
    expect(
      actualScoreSeriesDrawn({
        sportKey: "baseball_npb",
        espnHistory: [
          { home_score: null, away_score: null },
          { home_score: null, away_score: null },
        ],
      })
    ).toBe(false);
    expect(
      actualScoreSeriesDrawn({
        sportKey: "baseball_npb",
        espnHistory: [{ home_score: null, away_score: null }, { home_score: 3, away_score: 1 }],
      })
    ).toBe(true);
  });

  it("CONTROL: tennis holds set scores and still draws none — ux/1034 B5", () => {
    // The four points are real and are SETS. `scoreboardCountsTheUnit` is what
    // keeps them off a games axis, and the heading has to inherit that: a
    // heading keyed on "is there score history" would head this card Score
    // Differential over a chart with no score on it.
    expect(TENNIS_SET_SCORE_HISTORY.length).toBe(4);
    expect(
      actualScoreSeriesDrawn({
        sportKey: "tennis_wta",
        scoreHistory: TENNIS_SET_SCORE_HISTORY,
      })
    ).toBe(false);
    expect(
      actualScoreSeriesDrawn({
        sportKey: "baseball_npb",
        scoreHistory: TENNIS_SET_SCORE_HISTORY,
      })
    ).toBe(true);
  });
});

describe("#6144 — on the production wire", () => {
  it("THE SHIP: the NPB page's card is named for the only line it has", () => {
    // Strawman guard: state what the wire holds before asking what is drawn
    // from it, or every assertion below can go vacuously true on an empty file.
    expect(NPB.event_id).toBe(15311956);
    expect(NPB.home_team).toBe("Hanshin Tigers");
    expect(NPB.score_history).toEqual([]);
    expect(NPB.espn_history).toEqual([]);
    expect(
      NPB.history.filter((p: { projected_home_score: number | null }) =>
        p.projected_home_score != null
      ).length
    ).toBe(122);

    // #8617: the projection on this wire is the run line, not a margin, so
    // baseball no longer draws it. The naming rule is unchanged and still
    // holds wherever the projection IS a margin — the same bytes read as a
    // tennis card below prove that half.
    const markup = renderChart(NPB, "baseball_npb");
    expect(seriesAttr(markup, "data-actual-series")).toBe(null);
    expect(markup).toContain("Score data is not available");

    const asMargin = renderChart(NPB, "tennis_wta");
    expect(seriesAttr(asMargin, "data-actual-series")).toBe("false");
    expect(seriesAttr(asMargin, "data-projected-series")).toBe("true");
  });

  it("THE DIFFERENTIAL: one score point — not the sport — decides the name", () => {
    // Identical bytes into both; the only difference is one real score. This is
    // the arm a rename keyed on the sport key, on `status`, or on a NULL
    // `espn_id` cannot pass.
    expect(headingFor(NPB, "baseball_npb")).toBe("Projected Run Margin");
    expect(
      headingFor(NPB, "baseball_npb", {
        scoreHistory: [{ timestamp: "2026-09-14T10:00:00Z", home_score: 1, away_score: 0 }],
      })
    ).toBe("Score Differential");

    const withScore = renderChart(NPB, "baseball_npb", {
      scoreHistory: [{ timestamp: "2026-09-14T10:00:00Z", home_score: 1, away_score: 0 }],
    });
    expect(seriesAttr(withScore, "data-actual-series")).toBe("true");
  });

  it("CONTROL: a settled game that holds its score keeps the old name", () => {
    expect(SETTLED_NFL.status).toBe("completed");
    expect(SETTLED_NFL.score_history.length).toBe(6);
    expect(SETTLED_NFL.score_history[5]).toMatchObject({ home_score: 37, away_score: 59 });

    const markup = renderChart(SETTLED_NFL, "americanfootball_nfl");
    expect(headingFor(SETTLED_NFL, "americanfootball_nfl")).toBe("Score Differential");
    expect(seriesAttr(markup, "data-actual-series")).toBe("true");
  });

  it("CONTROL: a projection-only card still draws — this is a rename, not a suppression", () => {
    // The legend that says "Projected margin" lives inside
    // `ResponsiveContainer` and so is invisible to a server render — which is
    // why the drawn series are reported on the wrapper at all. What IS
    // observable here is everything around the plot, and it is a real card:
    // both range pills, both axis labels, the sportsbook note, no error stub.
    //
    // #8617: read under a sport whose sportsbook spread IS a margin. Baseball's
    // is the run line and is withheld — see runLineIsNotAMargin8617.
    const markup = renderChart(NPB, "americanfootball_nfl");
    expect(markup).not.toContain("Score data is not available");
    expect(markup).toContain("Since Start");
    expect(markup).toContain("Tigers");
    expect(markup).toContain("Dragons");
    expect(markup).toContain("Each gray line is one of the sportsbooks");
    expect(markup.length).toBeGreaterThan(500);
  });

  it("CONTROL: a live tennis card is named for its projection too", () => {
    const markup = renderChart(NPB, "tennis_wta", {
      scoreHistory: TENNIS_SET_SCORE_HISTORY,
    });
    expect(
      headingFor(NPB, "tennis_wta", { scoreHistory: TENNIS_SET_SCORE_HISTORY })
    ).toBe("Projected Game Margin");
    expect(seriesAttr(markup, "data-actual-series")).toBe("false");
  });
});

// ── #6144 × #6142, THE COMBINATION int356 ASKED FOR ─────────────────────────
//
// Both rules now speak about this one component from opposite directions:
// #6142 WITHHOLDS a series on a final, #6144 NAMES the card after the series it
// draws. A settled game with no drawn score hits both at once, and the failure
// they could compose into is a specific one — a card headed "Projected Game
// Margin" with every projection withheld from inside it, which is #6144 again
// with the words rearranged.
//
// It does not happen, and the reason is asserted rather than argued: the two
// rules speak about different series. #6142 withholds the venues' implied-spread
// SNAPSHOT; the projected-margin LINE that the heading names is the sportsbook
// series, which that rule has always and in every game state left alone.
describe("#6144 × #6142 — a settled game with no drawn score", () => {
  it("THE COMBINATION, on real settled wire: named for its projection, still drawing it", () => {
    // Strawman guard first: a settled game (not a live one), whose score IS
    // held — three sets to one, on the wire — and is still not drawable.
    expect(SETTLED_TENNIS.event_id).toBe(15310688);
    expect(SETTLED_TENNIS.status).toBe("completed");
    expect(SETTLED_TENNIS.score_history.length).toBe(4);
    expect(SETTLED_TENNIS.score_history[3]).toMatchObject({ home_score: 3, away_score: 1 });
    expect(
      SETTLED_TENNIS.history.filter(
        (p: { projected_home_score: number | null }) => p.projected_home_score != null
      ).length
    ).toBe(107);

    const markup = renderChart(SETTLED_TENNIS, "tennis_atp_us_open");

    // Settled, and still named for the projection — the rule is keyed on the
    // series that is drawn, not on whether the game is running. A heading that
    // read "Score Differential" on a finished match because it is finished
    // would put the 3–1 in sets over an axis of games.
    expect(headingFor(SETTLED_TENNIS, "tennis_atp_us_open")).toBe("Projected Game Margin");
    expect(seriesAttr(markup, "data-actual-series")).toBe("false");
    expect(seriesAttr(markup, "data-projected-series")).toBe("true");
    expect(markup).not.toContain("Score data is not available");

    // And the projection survives the range this page opens on. A settled game
    // with post-start data defaults to "Since Start", so that — not "All" — is
    // the mode a reader lands in, and the card the heading names would be an
    // empty frame if the projections all sat before the first ball. 93 of the
    // wire's 107 projected points fall after the 18:13:40Z start; the filter is
    // the component's own, so this is measured rather than asserted.
    expect(
      seriesAttr(
        renderChart(SETTLED_TENNIS, "tennis_atp_us_open", { externalTimeRange: "live" }),
        "data-projected-series"
      )
    ).toBe("true");
  });

  it("the heading never names a series #6142 has withheld", () => {
    // #6142's own settled wire, which still carries the `kalshi` arm — the one
    // a final withholds. Strawman guard: the arm has to BE there, or the
    // "none" below is the absence of a rule rather than the rule.
    expect(SETTLED_WITH_KALSHI_ARM.status).toBe("completed");
    expect(Object.keys(SETTLED_WITH_KALSHI_ARM.pm_spread_data.implied_spreads)).toEqual([
      "kalshi",
      "sportsbook",
    ]);

    // Under its own sport the two rules do not meet: the played score is drawn,
    // so the card keeps its name while #6142 withholds the snapshot.
    const asNfl = renderChart(SETTLED_WITH_KALSHI_ARM, "americanfootball_nfl");
    expect(headingFor(SETTLED_WITH_KALSHI_ARM, "americanfootball_nfl")).toBe("Score Differential");
    expect(seriesAttr(asNfl, "data-implied-spread-series")).toBe("none");

    // The intersection itself. Identical bytes under a sport whose scoreboard
    // does not count the chart's unit — a settled game, a withheld kalshi arm,
    // and no actual line. The card is renamed AND the projected series it is
    // renamed after is still on the chart; the withholding takes the snapshot,
    // never the line the heading names.
    const asTennis = renderChart(SETTLED_WITH_KALSHI_ARM, "tennis_wta");
    expect(headingFor(SETTLED_WITH_KALSHI_ARM, "tennis_wta")).toBe("Projected Game Margin");
    expect(seriesAttr(asTennis, "data-actual-series")).toBe("false");
    expect(seriesAttr(asTennis, "data-implied-spread-series")).toBe("none");
    expect(seriesAttr(asTennis, "data-projected-series")).toBe("true");

    // NON-VACUITY of the withholding half: these bytes CAN draw the arm, so the
    // three "none"s above are a rule firing and not a payload with nothing in
    // it. Without this row they would pass on an empty map.
    //
    // #7660 made this probe vary two fields instead of one. That arm carries
    // `confidence: 0.2`, which is now withheld in EVERY state, so flipping only
    // the status no longer draws it — and an assertion of "none" there would be
    // the very vacuity this row exists to rule out. Both gates are opened, and
    // each is closed again on its own below, which says more than the original
    // single flip did.
    const believed = JSON.parse(JSON.stringify(SETTLED_WITH_KALSHI_ARM));
    believed.pm_spread_data.implied_spreads.kalshi.confidence = 0.97;

    expect(
      seriesAttr(
        renderChart(believed, "tennis_wta", { eventStatus: "scheduled" }),
        "data-implied-spread-series"
      )
    ).toBe("kalshi");
    // Close each gate in turn: the state alone withholds it, and the
    // confidence alone withholds it.
    expect(
      seriesAttr(renderChart(believed, "tennis_wta"), "data-implied-spread-series")
    ).toBe("none");
    expect(
      seriesAttr(
        renderChart(SETTLED_WITH_KALSHI_ARM, "tennis_wta", { eventStatus: "scheduled" }),
        "data-implied-spread-series"
      )
    ).toBe("none");
    // …and the name does not move with it. The two rules are orthogonal: one
    // reads `status`, the other reads the drawn score.
    expect(headingFor(SETTLED_WITH_KALSHI_ARM, "tennis_wta")).toBe("Projected Game Margin");
  });

  it("and #6142 is INERT on the real tennis specimen — so the row above is not it", () => {
    // Measured 14:25Z on both settled US Open matches served today (15310688
    // Zverev–Shelton, 15310026 Sabalenka–Rybakina): the implied_spreads map
    // carries `sportsbook` and nothing else. That arm is excluded in EVERY game
    // state on its own long-standing grounds — it is already the projected
    // line — so a "none" on real tennis wire says nothing about #6142, and
    // reading it as a settled-game assertion would be reading an absence.
    expect(Object.keys(SETTLED_TENNIS.pm_spread_data.implied_spreads)).toEqual(["sportsbook"]);
    expect(
      seriesAttr(renderChart(SETTLED_TENNIS, "tennis_atp_us_open"), "data-implied-spread-series")
    ).toBe("none");
    expect(
      seriesAttr(
        renderChart(SETTLED_TENNIS, "tennis_atp_us_open", { eventStatus: "live" }),
        "data-implied-spread-series"
      )
    ).toBe("none");
  });
});

describe("#6144 — the heading and the series read one predicate", () => {
  it("the chart gates its actual line on the shared rule, not a second copy", () => {
    // Strawman guard: the import must exist, or the `not.toMatch` below passes
    // by hunting a spelling that was renamed away.
    expect(CHART_SOURCE).toContain(
      'from "@/lib/scoreDifferentialHeading"'
    );
    expect(CHART_SOURCE).toContain("actualScoreSeriesDrawn({");

    // The pre-#6144 inline spelling. This is the shape that lets the chart and
    // the heading drift apart, which is #6144 with an extra step.
    expect(CHART_SOURCE).not.toMatch(
      /hasActualScoreData\s*=\s*\n?\s*scoreboardCountsTheUnit\s*&&/
    );
  });

  it("the page computes the heading and renders it, rather than a literal", () => {
    // A gate whose input silently stops arriving fires never while every
    // assertion above stays green (#2086). These are the three lines that have
    // to be on the page for any of this to reach a reader.
    expect(EVENT_PAGE_SOURCE).toContain("actualScoreSeriesDrawn({");
    expect(EVENT_PAGE_SOURCE).toContain("scoreDifferentialHeading({");
    expect(EVENT_PAGE_SOURCE).toContain("{scoreDiffHeading}");

    // And the hardcoded heading is gone from the card. Matched with its JSX
    // whitespace so the many PROSE mentions of the card in this file's comments
    // — which must stay — are not what keeps this green.
    expect(EVENT_PAGE_SOURCE).not.toMatch(/>\s*\n\s*Score Differential\s*\n\s*</);
  });

  it("the page feeds both calls the event's own data, not a constant", () => {
    // The three assertions above prove the page CALLS the rule. They cannot
    // see what it passes, and `actualSeriesDrawn: false` or a dropped
    // `sportKey` is a one-word mutant that renames every card — or none —
    // while leaving them all green. The page renders under `"use client"` with
    // live fetches, so the arguments are asserted at the call text.
    const gate = EVENT_PAGE_SOURCE.slice(
      EVENT_PAGE_SOURCE.indexOf("const drawsActualScore = actualScoreSeriesDrawn({")
    );
    const gateArgs = gate.slice(0, gate.indexOf("});"));
    expect(gateArgs).toContain("sportKey: event?.sport || undefined");
    expect(gateArgs).toContain("scoreHistory: historyData?.score_history");
    expect(gateArgs).toContain("espnHistory: historyData?.espn_history");

    const title = EVENT_PAGE_SOURCE.slice(
      EVENT_PAGE_SOURCE.indexOf("const scoreDiffHeading = scoreDifferentialHeading({")
    );
    const titleArgs = title.slice(0, title.indexOf("});"));
    expect(titleArgs).toContain("sportKey: event?.sport || undefined");
    expect(titleArgs).toContain("actualSeriesDrawn: drawsActualScore");
  });

  it("the page hands the chart the sport key the rule is keyed on", () => {
    const from = EVENT_PAGE_SOURCE.indexOf("<ScoreDifferentialChart");
    const call = EVENT_PAGE_SOURCE.slice(from, from + EVENT_PAGE_SOURCE.slice(from).indexOf("/>"));
    expect(call).toContain("<ScoreDifferentialChart");
    expect(call).toContain("sportKey={event.sport || undefined}");
    expect(call).toContain("scoreHistory=");
  });
});
