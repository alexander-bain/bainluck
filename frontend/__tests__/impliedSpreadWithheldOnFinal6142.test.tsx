// #6142 RENDER HALF — A FINISHED GAME'S SCORE DIFFERENTIAL CHART STOPS DRAWING
// A "KALSHI IMPLIED" LINE ACROSS A RESULT THAT IS ALREADY ON THE SAME AXIS.
//
// ── WHAT THE READER SAW ──────────────────────────────────────────────────────
//
// `/events/14780142` — Carolina Panthers 37, Chicago Bears **59**, Final —
// read at 390px on 2026-09-14 11:20Z, four hours after the whistle.
// Frame: `artifacts/ux-1257/slice-00.png`.
//
// In the Score Differential card, three things at once:
//
//   * a flat purple dashed line, edge to edge, labelled **Kalshi Implied**,
//     sitting at about **+16 on the PANTHERS side**;
//   * beneath it the orange **Actual Score Diff** line wandering down and
//     finishing at **−22 on the Bears side**;
//   * above the whole card, the scoreboard: **Chicago 59 – Carolina 37**.
//
// One line says Carolina by 16. The line under it says Chicago by 22. The
// scoreboard says Chicago by 22. Nothing on the page reconciles them, and the
// dashed line is drawn at the same weight and in the same idiom as the two real
// time series beside it, so it reads as a third series rather than as a single
// current quote.
//
// Measured on the wire (`GET /api/events/14780142/history`, 11:52Z), which is
// the fixture in this file byte for byte:
//
//     kalshi      home_margin: +15.0   confidence: 0.2
//     sportsbook  home_margin:  −2.6   confidence: 1.0
//     actual                    −22
//
// ── THE SERVER ALREADY RULED THIS CLASS AND LEFT THIS HALF FOR THE RENDER ────
//
// `routes/events.py` (#5078) withholds `projected_final` once a game is over,
// under "settled means settled", and says in the same comment that it is
// stopping deliberately short of the chart's own rungs:
//
//     `implied_spreads`/`implied_totals` are deliberately left alone — they are
//     the chart's own rungs, and this is the narrow claim: no PROJECTION of a
//     game that has already been played.
//
// So this is not a new rule, it is the second half of one. The predicate is the
// producer's own — `status in ("completed", "closed")` — which is why the
// decision lives in `lib/impliedSpreadAxis` and is CALLED rather than written
// inline at the chart's three draw sites: two spellings of "final" on the two
// halves of one rule is how they come to disagree.
//
// ── WHY NOT GATE ON `confidence`, WHICH IS ALSO SERVED AND ALSO IGNORED ──────
//
// It is a real gap — `0.2` draws exactly like `1.0` — but it is not this
// defect's gate. Every kalshi arm measured on 2026-09-14 served `confidence:
// 0.2`, on settled and unplayed games alike (five settled NFL pages, three
// arms; plus the scheduled fixture below). A confidence floor would therefore
// not narrow this case, it would delete the feature on every game. Whether that
// ladder should be *served* is the producer half of #6142 and is untouched here.
//
// ── WHAT MUST NOT MOVE, AND IS ASSERTED BELOW ────────────────────────────────
//
// Deleting the implied-spread line outright satisfies the ship assertion and is
// wrong, so every control here is load-bearing:
//
//   * AN UNPLAYED GAME STILL DRAWS IT, from both venues. The scheduled fixture
//     is Broncos @ Chiefs read live at 11:53Z with a real **polymarket** arm
//     beside the kalshi one — so the polymarket gate is not hypothetical, and a
//     fix that only remembered kalshi would be caught here.
//   * THE SUPPRESSION IS THE STATE, NOT THE PAYLOAD. The load-bearing arm is a
//     differential: the identical settled wire, with `eventStatus` as the ONLY
//     thing that differs, must draw the line in one and not the other. A fix
//     keyed on something the settled payload happens to carry (a null
//     projection, an all-0/1 ladder, an absent bookmaker count) passes the ship
//     assertion and fails this one.
//   * THE CALLER'S `eventStatus` HAS TO ARRIVE. `app/events/[id]/page.tsx`
//     passes `eventStatus={event.status}`; if that prop is ever dropped the gate
//     silently never fires, which is #2086's failure mode exactly — a field
//     declared, passed, and destructured by nobody. The differential proves the
//     prop is read, not merely declared.
//   * THE CARD STILL DRAWS. The failure mode of a suppression is a widget that
//     reads as failed-to-load, which would pass the ship assertion for the worst
//     possible reason. The settled specimen must still report its actual and
//     projected series.
//   * `sportsbook` IS NEVER DRAWN HERE, IN ANY STATE. That clause pre-dates this
//     ship (the arm is already the projected-margin line); it moved into the
//     shared rule and must not have changed meaning on the way.
//
// ── ON WITHDRAWING A NUMBER ──────────────────────────────────────────────────
//
// A fix that removes a wrong-looking value can delete the alarm and keep the
// lie, so: the +15 is the visible symptom of a derivation defect on a settled
// ladder, and that defect is filed, measured and quoted in #6142's producer
// half. The fixture in this directory carries the offending wire verbatim —
// contracts, confidence and all — so the evidence survives in the repository
// even once it is off the reader's screen. What is withdrawn is a contradiction
// from a page, not a finding from the record.

import React from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { readFileSync } from "fs";
import { join } from "path";

import ScoreDifferentialChart from "@/components/ScoreDifferentialChart";
import {
  impliedSpreadSnapshotDrawn,
  drawnImpliedSpreadSources,
} from "@/lib/impliedSpreadAxis";

const SETTLED = JSON.parse(
  readFileSync(
    join(__dirname, "fixtures/impliedSpread.14780142.settled.json"),
    "utf8"
  )
);
const SCHEDULED = JSON.parse(
  readFileSync(
    join(__dirname, "fixtures/impliedSpread.14638896.scheduled.json"),
    "utf8"
  )
);
/** #7660's specimen: Chiefs–Colts live in the 3rd, carrying a believed
 *  polymarket arm (0.97) beside a distrusted kalshi one (0.2). The controls
 *  below that used to run on SCHEDULED run on this instead — see the header. */
const LIVE = JSON.parse(
  readFileSync(
    join(__dirname, "fixtures/impliedSpread.14780544.live.json"),
    "utf8"
  )
);

const CHART_SOURCE = readFileSync(
  join(__dirname, "../components/ScoreDifferentialChart.tsx"),
  "utf8"
);
const EVENT_PAGE_SOURCE = readFileSync(
  join(__dirname, "../app/events/[id]/page.tsx"),
  "utf8"
);

/** The attribute the wrapper reports the drawn snapshot sources on. recharts
 *  renders nothing inside `ResponsiveContainer` without a viewport, so a server
 *  render — all a guard can see — cannot observe a `<Line>` directly. This is
 *  the same wrapper channel `data-actual-series` has used since ux/1034 B5, and
 *  it is built from the very list the legend and the lines are gated on. */
function seriesAttr(markup: string, attr: string): string | null {
  const m = markup.match(new RegExp(`${attr}="([^"]*)"`));
  return m ? m[1] : null;
}

function renderChart(
  wire: Record<string, unknown>,
  overrides: Record<string, unknown> = {}
): string {
  return renderToStaticMarkup(
    React.createElement(ScoreDifferentialChart, {
      history: wire.history as never,
      homeTeam: wire.home_team as string,
      awayTeam: wire.away_team as string,
      commenceTime: wire.commence_time as string,
      scoreHistory: wire.score_history as never,
      eventStatus: wire.status as string,
      sportKey: "americanfootball_nfl",
      pmSpreadData: wire.pm_spread_data as never,
      ...overrides,
    } as never)
  );
}

/** A trusted arm, so these assertions turn on the state and the source alone.
 *  #7660 added the ARM as a third input of the rule and gates on its
 *  `confidence`; passing a believed one here keeps each assertion below about
 *  the one clause it names. The live fixture it added is what proves the two
 *  clauses are independent — see `impliedSpreadConfidenceFloor7660.test.tsx`. */
const COHERENT = {
  spread: -7.5,
  home_margin: 7.5,
  confidence: 0.97,
  contracts: [
    { threshold: 3.5, probability: 0.8 },
    { threshold: 7.5, probability: 0.5 },
    { threshold: 10.5, probability: 0.3 },
  ],
};

describe("#6142 — the rule itself", () => {
  it("draws a venue snapshot on a game that has not finished", () => {
    expect(impliedSpreadSnapshotDrawn({ source: "kalshi", isFinal: false, arm: COHERENT })).toBe(true);
    expect(impliedSpreadSnapshotDrawn({ source: "polymarket", isFinal: false, arm: COHERENT })).toBe(true);
  });

  it("draws no venue snapshot once the game is final", () => {
    expect(impliedSpreadSnapshotDrawn({ source: "kalshi", isFinal: true, arm: COHERENT })).toBe(false);
    expect(impliedSpreadSnapshotDrawn({ source: "polymarket", isFinal: true, arm: COHERENT })).toBe(false);
  });

  it("never draws the sportsbook arm — it is already the projected-margin line", () => {
    // Both states: this clause moved into the shared rule and did not change
    // meaning on the way. The settled fixture carries a real sportsbook arm.
    expect(impliedSpreadSnapshotDrawn({ source: "sportsbook", isFinal: false, arm: COHERENT })).toBe(false);
    expect(impliedSpreadSnapshotDrawn({ source: "sportsbook", isFinal: true, arm: COHERENT })).toBe(false);
  });

  it("reads the production payloads' own source sets, in payload order", () => {
    const settledArms = SETTLED.pm_spread_data.implied_spreads;
    const liveArms = LIVE.pm_spread_data.implied_spreads;

    // Strawman guard: if these fixtures ever stop carrying the arms the
    // assertions below are about, every expectation underneath goes vacuously
    // true. State what the wire holds before asking what is drawn from it.
    expect(Object.keys(settledArms)).toEqual(["kalshi", "sportsbook"]);
    expect(Object.keys(liveArms)).toEqual([
      "kalshi",
      "polymarket",
      "sportsbook",
    ]);

    expect(drawnImpliedSpreadSources(settledArms, true)).toEqual([]);
    // #7660 moved these. The settled fixture's only non-sportsbook arm is
    // `kalshi` at confidence 0.2, so un-finaling it no longer draws it; and on
    // the live wire the distrusted `kalshi` arm is FIRST in payload order and
    // the believed `polymarket` arm second, so this pair states the filter.
    expect(drawnImpliedSpreadSources(settledArms, false)).toEqual([]);
    expect(drawnImpliedSpreadSources(liveArms, false)).toEqual(["polymarket"]);
  });

  it("keeps payload order when more than one arm survives", () => {
    // The claim above used to carry this too, and can no longer: every
    // production fixture here now has exactly one drawable arm, so an order
    // assertion over them would pass on a function that sorted, reversed or
    // hard-coded. Stated on a record whose order is the only thing in question.
    const believed = { spread: -3, home_margin: 3, confidence: 0.9 };
    expect(
      drawnImpliedSpreadSources(
        { polymarket: believed, kalshi: believed },
        false
      )
    ).toEqual(["polymarket", "kalshi"]);
    expect(
      drawnImpliedSpreadSources(
        { kalshi: believed, polymarket: believed },
        false
      )
    ).toEqual(["kalshi", "polymarket"]);
  });

  it("treats an absent or empty payload as nothing to draw, in either state", () => {
    for (const isFinal of [true, false]) {
      expect(drawnImpliedSpreadSources(undefined, isFinal)).toEqual([]);
      expect(drawnImpliedSpreadSources(null, isFinal)).toEqual([]);
      expect(drawnImpliedSpreadSources({}, isFinal)).toEqual([]);
    }
  });
});

describe("#6142 — the chart, on the production wire", () => {
  it("THE SHIP: the settled Panthers–Bears page draws no implied-spread line", () => {
    // The offending number is on the wire this render is given.
    expect(
      SETTLED.pm_spread_data.implied_spreads.kalshi.home_margin
    ).toBe(15.0);
    expect(SETTLED.status).toBe("completed");

    const markup = renderChart(SETTLED);
    expect(seriesAttr(markup, "data-implied-spread-series")).toBe("none");
  });

  it("THE DIFFERENTIAL: one field — the state — decides it, on one payload", () => {
    // Identical bytes into both renders; `eventStatus` is the only difference.
    // This is the arm a fix keyed on anything the settled payload merely
    // happens to carry cannot pass.
    //
    // #7660 moved it onto the LIVE wire. It has to run on a payload with a
    // drawable arm, and SETTLED's only one is kalshi at confidence 0.2, which
    // is now withheld in BOTH states — on that fixture this control would read
    // "none" either way and prove nothing about `eventStatus` at all.
    const asFinal = renderChart(LIVE, { eventStatus: "completed" });
    const asLive = renderChart(LIVE);

    expect(LIVE.status).toBe("live");
    expect(seriesAttr(asFinal, "data-implied-spread-series")).toBe("none");
    expect(seriesAttr(asLive, "data-implied-spread-series")).toBe("polymarket");
  });

  it("`closed` is final too, not just `completed`", () => {
    // The producer's predicate is `status in ("completed", "closed")`. A gate
    // that learned only the word on the specimen would pass every arm above.
    expect(
      seriesAttr(renderChart(SETTLED, { eventStatus: "closed" }), "data-implied-spread-series")
    ).toBe("none");
  });

  it("CONTROL: a game that has not finished still draws a venue snapshot", () => {
    // #6142 wrote this as "an unplayed game still draws it, FROM BOTH VENUES",
    // on the scheduled fixture, guarding against a fix that deleted the line
    // outright. #7660 narrowed what it can claim and kept what it protects: on
    // that fixture both arms are now withheld (polymarket 0.3, kalshi 0.2), so
    // the live wire carries the control instead — a non-final game still draws,
    // and what it draws is the believed arm rather than nothing.
    expect(LIVE.status).toBe("live");
    const markup = renderChart(LIVE);
    expect(seriesAttr(markup, "data-implied-spread-series")).toBe("polymarket");

    // The coverage #7660 knowingly gave up, asserted so it cannot change by
    // accident: a non-final game whose only arms are distrusted draws none.
    expect(SCHEDULED.status).toBe("scheduled");
    expect(
      seriesAttr(renderChart(SCHEDULED), "data-implied-spread-series")
    ).toBe("none");
  });

  it("CONTROL: the settled card still draws — this is a suppression, not a blank", () => {
    const markup = renderChart(SETTLED);
    expect(seriesAttr(markup, "data-actual-series")).toBe("true");
    expect(seriesAttr(markup, "data-projected-series")).toBe("true");
    // And it is a real card, not an error stub.
    expect(markup).not.toContain("Score data is not available");
    expect(markup.length).toBeGreaterThan(500);
  });
});

describe("#6142 — the three draw sites read one list", () => {
  // The attribute above is built from `impliedSpreadSources`, so it cannot
  // report a suppression the chart did not perform — but only while the legend
  // and the lines are gated on that same list. These assertions are what stop a
  // change re-gating one of them on the raw payload and leaving the attribute
  // telling the truth about a line that is still drawn.

  it("the data build, the legend and both lines all gate on the shared list", () => {
    // Strawman guard: the names below must exist, or every `not.toMatch` under
    // this describe passes by looking for something that was renamed away.
    expect(CHART_SOURCE).toContain("drawnImpliedSpreadSources(");
    expect(CHART_SOURCE).toContain("const impliedSpreadSources");

    // data build
    expect(CHART_SOURCE).toContain("if (!impliedSpreadSources.includes(source)) continue;");
    // legend payload + the two lines: four `includes` gates in all, plus the
    // build's own, plus the wrapper attribute's `join`.
    expect(
      CHART_SOURCE.match(/impliedSpreadSources\.includes\("kalshi"\)/g)
    ).toHaveLength(2);
    expect(
      CHART_SOURCE.match(/impliedSpreadSources\.includes\("polymarket"\)/g)
    ).toHaveLength(2);
  });

  it("the page still hands the chart the state the gate is keyed on", () => {
    // The differential above proves the component READS `eventStatus`. It
    // cannot prove the page still PASSES it, and a gate whose input silently
    // stops arriving fires never while every test here stays green — which is
    // the whole of #2086. Asserted against the one call site.
    const call = EVENT_PAGE_SOURCE.slice(
      EVENT_PAGE_SOURCE.indexOf("<ScoreDifferentialChart")
    ).slice(0, EVENT_PAGE_SOURCE.slice(EVENT_PAGE_SOURCE.indexOf("<ScoreDifferentialChart")).indexOf("/>"));
    expect(call).toContain("<ScoreDifferentialChart");
    expect(call).toContain("eventStatus={event.status}");
    expect(call).toContain("pmSpreadData=");
  });

  it("no draw site reaches past the list into the raw payload", () => {
    // The pre-#6142 spelling. `implied_spreads` may still be READ (the prop
    // type declares it, and the shared list is computed from it) — what may not
    // come back is a render or legend gate keyed straight on an arm.
    expect(CHART_SOURCE).not.toMatch(/implied_spreads\?\.kalshi\s*&&/);
    expect(CHART_SOURCE).not.toMatch(/implied_spreads\?\.polymarket\s*&&/);
    expect(CHART_SOURCE).not.toMatch(/implied_spreads\?\.kalshi\s*\n?\s*\?/);
    expect(CHART_SOURCE).not.toMatch(/implied_spreads\?\.polymarket\s*\n?\s*\?/);
    // And the clause that moved out of the build loop has not crept back as a
    // second, separate statement of the same rule.
    expect(CHART_SOURCE).not.toContain('if (source === "sportsbook") continue;');
  });
});
