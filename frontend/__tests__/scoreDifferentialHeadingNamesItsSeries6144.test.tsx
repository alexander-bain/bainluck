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

    const markup = renderChart(NPB, "baseball_npb");

    // The two halves of the claim, on one payload: the card says projection,
    // and projection is all the chart draws.
    expect(headingFor(NPB, "baseball_npb")).toBe("Projected Run Margin");
    expect(seriesAttr(markup, "data-actual-series")).toBe("false");
    expect(seriesAttr(markup, "data-projected-series")).toBe("true");
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

  it("CONTROL: the NPB card still draws — this is a rename, not a suppression", () => {
    // The legend that says "Projected margin" lives inside
    // `ResponsiveContainer` and so is invisible to a server render — which is
    // why the drawn series are reported on the wrapper at all. What IS
    // observable here is everything around the plot, and it is a real card:
    // both range pills, both axis labels, the sportsbook note, no error stub.
    const markup = renderChart(NPB, "baseball_npb");
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
