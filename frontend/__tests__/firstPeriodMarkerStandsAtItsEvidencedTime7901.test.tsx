/**
 * #7901 — the FIRST period marker stood at the scheduled start, not at the
 * moment the period was observed.
 *
 * On `/events/15316297` (Blue Jays @ Orioles, MLB, 2026-09-21) the `T1` rule
 * stood at 22:35:00Z — `commence_time` exactly — while the served marker says
 * 23:22:33Z. Every other marker on the same plot stood at its own served time.
 * So the page told a reader the top of the 1st began at 3:35 PM and that
 * nothing then happened for 47 minutes.
 *
 * Measured at 390px with `tools/period-marker-position-7901.mjs`, which inverts
 * the axis through its own ticks. Production `e37fb7dc6` against a local build
 * carrying this fix, two minutes apart, same event:
 *
 *   BEFORE  T1 drawn 22:34:59Z  = commence−0.0m   (served 23:22:33Z, −47.6m)
 *   AFTER   T1 drawn 23:21:59Z  = commence+47.0m  (served 23:22:33Z,  −0.6m)
 *
 * −0.6m is the floor, not a residual: `ensurePoint` buckets every category to
 * the minute, so a marker at :33s is painted on the :00s column. Every sibling
 * marker reads −0.6 to −0.8m on BOTH arms — which is the point. `T1` was the one
 * marker not keeping company with the rest, and now it does.
 *
 * The surviving label SET is unchanged on the win-probability chart
 * (`T1,B1,B2,T4,B5,T7,B8` either way). The score-differential chart loses `T9`,
 * because `placePeriodLabels` reduces greedily and its survivor set is a
 * function of every marker's position — filed as #7951, not fixed here. The
 * trade is deliberate: an omission among the eleven this chart already makes,
 * against a sentence that was false.
 *
 * ═══ WHY THE THREE EXISTING CHANNELS COULD NOT SEE IT ═══
 *
 * `data-period-boundaries` (CERT-1984), `data-period-label-rows` (#6882) and
 * `data-period-labels` (#7876) report how many markers survive, which row each
 * lands on, and what each is called. A marker drawn at the wrong INSTANT is
 * present, on row 0, correctly named `T1` and correctly spelled — all three
 * channels read healthy on the defect. `data-period-times` (#7901) is the
 * fourth, and this suite is why it exists.
 *
 * ═══ THE CAUSE, AND WHY IT SURVIVED SO LONG ═══
 *
 * `applyCommenceTime` rewrote the first boundary's timestamp to the game start
 * whenever its label was a first-period one, justified as "data may arrive
 * late". `page.tsx` did not hand it `commence_time` directly — it handed it
 * `computeRealStartTime(...)`, a helper whose whole purpose was to notice a late
 * start and pass the real one instead. That helper could never fire: it
 * minimised over every `win_prob_history` series, and on this event Polymarket
 * begins 2026-09-15 and Kalshi 2026-09-18 — days before first pitch — so its
 * "is the earliest live reading more than 3 minutes after nominal?" test was
 * answered by a market quote and always said no.
 *
 * Two things dressed as safety, composing into a confident false statement.
 */

import React from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { readFileSync } from "fs";
import { join } from "path";
import { spawnSync } from "child_process";

import { AnalyticsProvider } from "@/components/Analytics";
import OddsChart from "@/components/OddsChart";
import ScoreDifferentialChart from "@/components/ScoreDifferentialChart";
import { derivePeriodBoundaries, type PeriodBoundary } from "@/lib/periodMarkers";

const FIXTURE = "fixtures/firstPeriodMarker.15316297.mlb-late-start.json";
const WIRE = JSON.parse(readFileSync(join(__dirname, FIXTURE), "utf8"));
const SPORT = "baseball_mlb";

const COMMENCE_MS = Date.parse(WIRE.commence_time);
const SERVED_FIRST_MARKER = WIRE.period_markers[0].timestamp;
const SERVED_FIRST_MS = Date.parse(SERVED_FIRST_MARKER);

function boundaries(): PeriodBoundary[] {
  return derivePeriodBoundaries(
    undefined,
    undefined,
    undefined,
    WIRE.period_markers,
    SPORT,
  );
}

// ───────────────────────────────────────────────────────────────────────────
// The specimen actually carries the defect. Every assertion below is about a
// 47-minute displacement; on a payload where the game started on time they
// would all pass while the page went on lying about the late ones.
// ───────────────────────────────────────────────────────────────────────────

describe("#7901 — the specimen is a genuinely late-starting game", () => {
  it("the first served marker is 47.6 minutes after the scheduled start", () => {
    const gapMin = (SERVED_FIRST_MS - COMMENCE_MS) / 60000;
    expect(Math.round(gapMin * 10) / 10).toBe(47.6);
  });

  it("it is the TOP OF THE 1ST — the period the scheduled start is meant to be", () => {
    expect(WIRE.period_markers[0].period).toBe("Top 1st");
  });

  it("no game-state channel saw anything before it — so nothing evidences 22:35Z", () => {
    // The whole question is whether we have any reason to believe the inning
    // began at the scheduled time. A point that observes the GAME carries a
    // `game_state`; a market quote does not.
    const earliestGameState = Object.values(
      WIRE.win_prob_history as Record<string, Array<{ timestamp: string; game_state?: unknown }>>,
    )
      .flat()
      .filter((p) => p.game_state != null)
      .map((p) => Date.parse(p.timestamp))
      .sort((a, b) => a - b)[0];

    expect(earliestGameState).toBeGreaterThan(COMMENCE_MS + 40 * 60000);
  });

  it("yet the market series ran across that window — we WERE watching, and saw no game", () => {
    // This is what makes the scheduled time indefensible rather than merely
    // unproven: the silence is not "we were not looking".
    const markets = ["kalshi", "polymarket"] as const;
    for (const k of markets) {
      const pts = WIRE.win_prob_history[k] as Array<{ timestamp: string; game_state?: unknown }>;
      expect(Date.parse(pts[0].timestamp)).toBeLessThan(COMMENCE_MS);
      // ...and not one of them observes the game, which is why they must never
      // be allowed to answer "when did play start?".
      expect(pts.filter((p) => p.game_state != null)).toHaveLength(0);
    }
  });
});

// ───────────────────────────────────────────────────────────────────────────
// The rule itself.
// ───────────────────────────────────────────────────────────────────────────

describe("#7901 — every boundary stands at the time it was observed", () => {
  it("the first boundary keeps its served timestamp", () => {
    expect(boundaries()[0].timestamp).toBe(SERVED_FIRST_MARKER);
  });

  it("and is NOT at the scheduled start", () => {
    expect(Date.parse(boundaries()[0].timestamp)).not.toBe(COMMENCE_MS);
  });

  it("the first boundary is not special: EVERY boundary is a served marker time", () => {
    // The defect was one element of the series meaning something different from
    // the rest. This pins the series as a whole, so a future exception for any
    // other position fails here too.
    const served = new Set<string>(
      (WIRE.period_markers as Array<{ timestamp: string }>).map((m) => m.timestamp),
    );
    for (const b of boundaries()) {
      expect({ label: b.label, fromServed: served.has(b.timestamp) }).toEqual({
        label: b.label,
        fromServed: true,
      });
    }
  });
});

// ───────────────────────────────────────────────────────────────────────────
// 🔴 THE BEFORE ARM. Without this the suite is agreement, not a measurement:
// every assertion above would also pass on a build that had never had the
// defect, and on one where the rule was removed for the wrong reason.
//
// This is the removed rule, frozen verbatim as it stood at e37fb7dc6, replayed
// on the same payload. It is deliberately NOT imported — importing it would
// make the control track the fix and convict nothing (#7876's lesson, and
// notice 50's: a control's entire content is the defect).
// ───────────────────────────────────────────────────────────────────────────

function applyCommenceTime_asItStoodBefore7901(
  bs: PeriodBoundary[],
  commenceTime?: string,
): PeriodBoundary[] {
  if (bs.length === 0) return bs;
  const result = [...bs];
  if (commenceTime) {
    const first = result[0];
    const isFirstPeriod = /^(Q1|P1|1H|1|R1|T1|B1)$/i.test(first.label);
    if (isFirstPeriod) {
      result[0] = { ...first, timestamp: commenceTime };
    }
  }
  return result;
}

describe("#7901 — the frozen pre-fix rule reproduces the defect on this payload", () => {
  it("it moved T1 to the scheduled start, 47.6 minutes early", () => {
    const before = applyCommenceTime_asItStoodBefore7901(boundaries(), WIRE.commence_time);
    expect(before[0].timestamp).toBe(WIRE.commence_time);
    expect(before[0].label).toBe("T1");
  });

  it("and the two arms DISAGREE — so the assertions above are measuring the fix", () => {
    const after = boundaries();
    const before = applyCommenceTime_asItStoodBefore7901(after, WIRE.commence_time);
    expect(before[0].timestamp).not.toBe(after[0].timestamp);
  });

  it("it left every other boundary alone, which is why only T1 looked wrong", () => {
    const after = boundaries();
    const before = applyCommenceTime_asItStoodBefore7901(after, WIRE.commence_time);
    expect(before.slice(1).map((b) => b.timestamp)).toEqual(
      after.slice(1).map((b) => b.timestamp),
    );
  });

  it("the second, unremarked arm: it would move a leading B1 to first pitch too", () => {
    // Not reachable on this payload — recorded because the regex admits it and
    // a half-inning that begins at first pitch is a plainer falsehood than T1's.
    const leadingBottom: PeriodBoundary[] = [
      { timestamp: "2026-09-21T23:39:33.980548+00:00", label: "B1" },
      { timestamp: "2026-09-21T23:50:33.221080+00:00", label: "T2" },
    ];
    const before = applyCommenceTime_asItStoodBefore7901(leadingBottom, WIRE.commence_time);
    expect(before[0].timestamp).toBe(WIRE.commence_time);

    // And the shipped pipeline does not do that.
    const now = derivePeriodBoundaries(
      undefined,
      undefined,
      undefined,
      [
        { timestamp: "2026-09-21T23:39:33.980548+00:00", period: "Bottom 1st" },
        { timestamp: "2026-09-21T23:50:33.221080+00:00", period: "Top 2nd" },
      ],
      SPORT,
    );
    expect(now[0]).toEqual({
      timestamp: "2026-09-21T23:39:33.980548+00:00",
      label: "B1",
    });
  });
});

// ───────────────────────────────────────────────────────────────────────────
// Through the components a reader actually gets, on BOTH charts — `page.tsx`
// derives `periodBoundaries` once and hands the same array to both, so the
// defect appeared on both and a one-chart guard would see half of it.
// ───────────────────────────────────────────────────────────────────────────

function renderOdds(): string {
  return renderToStaticMarkup(
    React.createElement(
      AnalyticsProvider,
      null,
      React.createElement(OddsChart, {
        history: WIRE.history,
        homeTeam: WIRE.home_team,
        awayTeam: WIRE.away_team,
        commenceTime: WIRE.commence_time,
        espnHistory: WIRE.espn_history,
        winProbHistory: WIRE.win_prob_history,
        scoreHistory: WIRE.score_history,
        eventStatus: WIRE.status,
        sportKey: SPORT,
        periodBoundaries: boundaries(),
      } as never),
    ),
  );
}

function renderSdc(): string {
  return renderToStaticMarkup(
    React.createElement(ScoreDifferentialChart, {
      history: WIRE.history,
      homeTeam: WIRE.home_team,
      awayTeam: WIRE.away_team,
      commenceTime: WIRE.commence_time,
      scoreHistory: WIRE.score_history,
      espnHistory: WIRE.espn_history,
      eventStatus: WIRE.status,
      sportKey: SPORT,
      periodBoundaries: boundaries(),
    } as never),
  );
}

/** The instants the chart handed recharts, in x order. */
function periodTimes(markup: string): number[] {
  const m = markup.match(/data-period-times="([^"]*)"/);
  if (!m) throw new Error("wrapper did not report data-period-times");
  return m[1] === "" ? [] : m[1].split(",").map(Number);
}

function periodLabels(markup: string): string[] {
  const m = markup.match(/data-period-labels="([^"]*)"/);
  if (!m) throw new Error("wrapper did not report data-period-labels");
  return m[1] === "" ? [] : m[1].split(",");
}

const CHARTS: Array<[string, () => string]> = [
  ["OddsChart", renderOdds],
  ["ScoreDifferentialChart", renderSdc],
];

describe.each(CHARTS)("#7901 — %s draws the first marker where it was seen", (_name, render) => {
  it("reports the new channel at all", () => {
    expect(() => periodTimes(render())).not.toThrow();
  });

  it("draws at least one marker, so the assertions below are not vacuous", () => {
    expect(periodTimes(render()).length).toBeGreaterThan(0);
  });

  it("no marker is drawn at the scheduled start", () => {
    expect(periodTimes(render()).filter((t) => t === COMMENCE_MS)).toEqual([]);
  });

  it("every drawn marker is at or after the first EVIDENCE of play", () => {
    // The generalised form of the defect: a marker earlier than anything we
    // observed of the game is an unevidenced claim, whatever its label.
    for (const t of periodTimes(render())) {
      expect({ t, atOrAfterEvidence: t >= SERVED_FIRST_MS }).toEqual({
        t,
        atOrAfterEvidence: true,
      });
    }
  });

  it("and the times line up one-for-one with the labels the same chart reports", () => {
    const markup = render();
    expect(periodTimes(markup)).toHaveLength(periodLabels(markup).length);
  });
});

// ───────────────────────────────────────────────────────────────────────────
// The fixture travels with the suite. `existsSync` passes on the machine where
// the mistake is made; tracking is the thing actually being asked (ux/1429 —
// #7908 went red in CI with 15,301 tests passing and one suite that never
// started, because its specimen lived in an untracked `artifacts/` path).
// ───────────────────────────────────────────────────────────────────────────

describe("#7901 — the specimen is tracked, so CI has it too", () => {
  function isTracked(relativeToThisDir: string): boolean {
    const abs = join(__dirname, relativeToThisDir);
    const res = spawnSync("git", ["ls-files", "--error-unmatch", "--", abs], {
      cwd: __dirname,
      encoding: "utf8",
    });
    if (res.error) {
      // Cannot verify ⇒ cannot pass. A guard that quietly skips when its
      // instrument is missing is the same silence it exists to break.
      throw new Error(`could not run git to check tracking: ${res.error.message}`);
    }
    return res.status === 0;
  }

  it("the fixture this suite reads is tracked", () => {
    expect({ FIXTURE, tracked: isTracked(FIXTURE) }).toEqual({ FIXTURE, tracked: true });
  });

  it("and the predicate convicts an untracked path — the control", () => {
    expect(isTracked("fixtures/this-file-does-not-exist-7901.json")).toBe(false);
  });
});
