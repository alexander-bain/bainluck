// #7876 — A GAME THAT GOES TO OVERTIME STOPS LOSING ITS HALFTIME MARKER.
//
// ── WHAT THE READER SAW ──────────────────────────────────────────────────────
//
// `https://bainluck.com/events/14780544`, Chiefs 33–30 Colts, completed, at
// 390px. The win-probability chart's period markers read `Q2  Q3  Q4  OT`.
//
// The game had a halftime. The payload says so — five `period_markers`, the
// second of them `Halftime`. The chart drew four of the five, and the one it
// dropped was the only boundary a reader scanning a football chart is actually
// looking for.
//
// ── THE CAUSE: A THRESHOLD THAT GREW WITH THE GAME ───────────────────────────
//
// `dedupePeriodLabels` collapsed any pair closer than 7% of the chart's TOTAL
// SPAN and kept the LATER of the two. NFL halftime is structurally ~15 minutes,
// so the `HT → Q3` gap is a fixed quantity, while the threshold is not:
//
//     regulation   15.0 min gap  vs  0.07 × 191.6 = 13.4 min  → both kept
//     overtime     15.0 min gap  vs  0.07 × 215.0 = 15.05 min → HT DELETED
//
// Halftime lost by 2.4 seconds. Nobody raised the constant — OVERTIME RAISED
// THE SPAN, which against a proportional threshold is arithmetically the same
// thing. #6882's docstring had named raising it as the trap ("collapsing this
// one DELETES `HT` from every NFL chart") and the trap sprang on its own.
//
// Within a single live game this is visible without a reload: the marker is
// drawn through regulation and disappears the moment the game goes to overtime.
//
// ── WHY NOT JUST LOWER IT ────────────────────────────────────────────────────
//
// Because the bug is the SHAPE of the rule, not its value. `HT` survives while
// `15 min > threshold × span`, so every candidate constant merely names the span
// at which the bug returns — 7% fails past 214 min, 6.3% past 238 min — and
// double overtime finds the next one. `theCrossoverIsGone` below is the arm
// that pins this: it sweeps spans from regulation to a six-hour chart and
// requires halftime at every one of them. It FAILS on any pure-threshold fix,
// which is the point.
//
// ── THE REPAIR ───────────────────────────────────────────────────────────────
//
// Two passes, each answering one question, where there used to be one number
// answering both badly:
//
//   `collapseDuplicateTransitions` — "do these two markers name one moment?"
//       Span-independent, because they do or they don't regardless of how wide
//       the chart is. Measured window; see its docstring.
//
//   `placePeriodLabels` — "can this label be drawn?" A marker is kept if some
//       row's last label is a full ink-width behind it, and dropped only when
//       neither row has space. Consecutive markers need no horizontal gap when
//       they land on different rows.
//
// ── SPECIMEN ─────────────────────────────────────────────────────────────────
//
// `GET /api/events/14780544/history`, captured 2026-09-21 while the page showed
// the defect, committed VERBATIM as
// `frontend/__tests__/fixtures/periodLabelOvertime.14780544.nfl-ot.json`
// (same shape as #6882's `periodLabelStagger.14638444.nfl-final.json`).
//
// It is tracked rather than read from `artifacts/`, where it was first captured:
// that directory is untracked, so the suite could only ever pass on the laptop
// that took the capture and failed to start on CI. And it is a WIRE payload, not
// a render, so nothing here may be re-captured from a tree that already carries
// the fix — the defect is in these bytes and re-taking them would erase it.

import React from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { readFileSync } from "fs";
import { join } from "path";
import { spawnSync } from "child_process";

import { AnalyticsProvider } from "@/components/Analytics";
import OddsChart from "@/components/OddsChart";
import ScoreDifferentialChart from "@/components/ScoreDifferentialChart";
import {
  collapseDuplicateTransitions,
  placePeriodLabels,
  derivePeriodBoundaries,
  PERIOD_LABEL_MIN_SPACING_FRACTION,
  PERIOD_LABEL_MAX_ROWS,
} from "@/lib/periodMarkers";

const WIRE = JSON.parse(
  readFileSync(
    join(__dirname, "fixtures/periodLabelOvertime.14780544.nfl-ot.json"),
    "utf8"
  )
);

const SPORT = "americanfootball_nfl";

function boundaries() {
  return derivePeriodBoundaries(
    undefined,
    undefined,
    undefined,
    WIRE.commence_time,
    WIRE.period_markers,
    SPORT
  );
}

/** The layout the page actually applies, in order. */
function placed(span: number) {
  return placePeriodLabels(collapseDuplicateTransitions(boundaries()), span);
}

/** WHICH labels reach the chart, not how many — the count was four either way
 *  and said nothing about halftime. #7876 opened this channel for that reason. */
function labelNames(markup: string): string[] {
  const m = markup.match(/data-period-labels="([^"]*)"/);
  if (!m) throw new Error("wrapper did not report data-period-labels");
  return m[1] === "" ? [] : m[1].split(",");
}

function labelRows(markup: string): number[] {
  const m = markup.match(/data-period-label-rows="([^"]*)"/);
  if (!m) throw new Error("wrapper did not report data-period-label-rows");
  return m[1] === "" ? [] : m[1].split(",").map(Number);
}

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
      } as never)
    )
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
    } as never)
  );
}

const CHARTS: Array<[string, () => string]> = [
  ["OddsChart", renderOdds],
  ["ScoreDifferentialChart", renderSdc],
];

describe("#7876 — the specimen actually carries the defect", () => {
  // Strawman guards. Every assertion below is about halftime surviving; on a
  // payload with no halftime, or one whose gap was never tight, they would all
  // pass while the page still dropped the label.
  it("the payload carries five boundaries, Halftime among them", () => {
    expect(boundaries().map((b) => b.label)).toEqual(["Q2", "HT", "Q3", "Q4", "OT"]);
  });

  it("this is an OVERTIME game — the fifth marker is what stretched the span", () => {
    expect(boundaries().map((b) => b.label)).toContain("OT");
  });

  it("the HT → Q3 gap is under the old threshold, which is the whole defect", () => {
    // Stated against the chart's own span, computed the way both charts compute
    // it: `commence_time` to the last plotted point across every series. If this
    // ever stops being true the fixture has drifted and the file below is
    // describing a different chart — re-derive it, do not re-baseline it.
    const b = boundaries();
    const start = new Date(WIRE.commence_time).getTime();
    let last = start;
    for (const rows of [WIRE.history, WIRE.espn_history, WIRE.score_history]) {
      for (const r of rows ?? []) last = Math.max(last, new Date(r.timestamp).getTime());
    }
    for (const rows of Object.values(WIRE.win_prob_history ?? {})) {
      for (const r of rows as Array<{ timestamp: string }>) {
        last = Math.max(last, new Date(r.timestamp).getTime());
      }
    }
    const span = last - start;
    const htToQ3 =
      new Date(b[2].timestamp).getTime() - new Date(b[1].timestamp).getTime();

    // ~15 minutes of real halftime, and BELOW 7% of the span — so the rule that
    // used to run here deleted it.
    expect(Math.round(htToQ3 / 60_000)).toBe(15);
    expect(htToQ3).toBeLessThan(span * PERIOD_LABEL_MIN_SPACING_FRACTION);
  });
});

describe("#7876 — halftime survives, and the chart it is on says so", () => {
  it("keeps all five markers, with HT on the top row and Q3 dropped", () => {
    const span = 225 * 60_000;
    expect(placed(span).map((r) => [r.label, r.labelRow])).toEqual([
      ["Q2", 0],
      ["HT", 0],
      ["Q3", 1],
      ["Q4", 0],
      ["OT", 0],
    ]);
  });

  it.each(CHARTS)("%s draws HT, in order, on the real render", (_name, render) => {
    // The helper being right is not the ship: a correct rule called by nobody
    // renders the same chart. This reads what the COMPONENT reports, computing
    // its own span from the payload.
    const names = labelNames(render());
    expect(names).toContain("HT");
    expect(names).toEqual(["Q2", "HT", "Q3", "Q4", "OT"]);
  });

  it.each(CHARTS)("%s puts HT where a reader looks — the top row", (_name, render) => {
    // Not cosmetic. The old collapse's survivor was `Q3`; a fix that kept `HT`
    // but demoted it under `Q3` would be re-enacting that choice quietly.
    const markup = render();
    const rows = labelRows(markup);
    expect(rows[labelNames(markup).indexOf("HT")]).toBe(0);
  });

  it.each(CHARTS)("%s never needs a row the render cannot draw", (_name, render) => {
    expect(Math.max(...labelRows(render()))).toBeLessThanOrEqual(
      PERIOD_LABEL_MAX_ROWS - 1
    );
  });
});

describe("#7876 — the crossover is gone, not moved", () => {
  // THE ARM THAT REJECTS A LOWERED CONSTANT. Any pure-threshold repair still has
  // a span at which `15 min < threshold × span`, so it fails somewhere in this
  // sweep. A regulation chart is ~190 min and the Chiefs–Colts chart 225; 360
  // min is a double-overtime game plus a pre-game window, and is past anything
  // this endpoint serves — the whole 14780544 payload, every series, spans 225
  // minutes and starts at `commence_time`.
  //
  // THE SWEEP STOPS AT 360 BECAUSE THE NEW RULE DOES HAVE A LIMIT, and it is a
  // density limit rather than an arithmetic cliff — stated here rather than
  // trimmed out of sight. See `theDensityLimitIsMeasured` below.
  const SPANS = [120, 190, 215, 225, 260, 300, 360].map((m) => m * 60_000);

  it.each(SPANS)("halftime is still drawn at a span of %ims", (span) => {
    expect(placed(span).map((r) => r.label)).toContain("HT");
  });

  it.each(SPANS)("and so is every other boundary the payload carried (%ims)", (span) => {
    // Five markers need 5 × 12.6% = 63% of one row, so nothing here is close to
    // the density at which dropping is correct. A repair that saved halftime by
    // sacrificing `Q4` would pass the arm above and fail this one.
    expect(placed(span).map((r) => r.label)).toEqual(["Q2", "HT", "Q3", "Q4", "OT"]);
  });

  it("the density limit is measured, and halftime outlives Q3 past it", () => {
    // HONEST BOUND. Two rows hold 2 × (1 / 12.6%) ≈ 15 labels spread evenly, but
    // these five sit inside 145 minutes, so on a very wide chart they cluster and
    // something must go. Measured by sweeping this specimen minute by minute:
    // all five are drawn up to a 396-minute span — 6.6 hours, nearly twice the
    // longest NFL broadcast and 1.8× anything the history endpoint serves.
    //
    // What matters more than the number is WHICH label goes first. Past the
    // limit the chart sheds `Q3` and KEEPS `HT`, because halftime is placed
    // before its crowded neighbour and the later marker is the one that loses
    // the row. The old rule did the exact opposite at 215 minutes, and that was
    // #7876. So the failure mode past the limit is the tidier chart, not the
    // original bug arriving later.
    const labelsAt = (min: number) => placed(min * 60_000).map((r) => r.label);

    expect(labelsAt(396)).toEqual(["Q2", "HT", "Q3", "Q4", "OT"]);
    expect(labelsAt(397)).not.toEqual(["Q2", "HT", "Q3", "Q4", "OT"]);
    // Past it, halftime survives and its crowded neighbour is the casualty.
    for (const span of [400, 440, 480, 500]) {
      expect(labelsAt(span)).toContain("HT");
      expect(labelsAt(span)).not.toContain("Q3");
    }
  });

  it("the old rule really does fail this sweep — the control", () => {
    // Without this, the sweep above could be passing because the specimen is
    // easy rather than because the rule changed. The pre-#7876 collapse, frozen
    // verbatim, loses halftime from 215 min upward.
    const preUx7876 = (span: number) => {
      const minSpacing = span * PERIOD_LABEL_MIN_SPACING_FRACTION;
      const out: Array<{ timestamp: string; label: string }> = [];
      for (const b of boundaries()) {
        const t = new Date(b.timestamp).getTime();
        if (out.length > 0) {
          const prevT = new Date(out[out.length - 1].timestamp).getTime();
          if (t - prevT < minSpacing) {
            out[out.length - 1] = b;
            continue;
          }
        }
        out.push(b);
      }
      return out.map((x) => x.label);
    };

    // Regulation-length: the old rule was fine, which is why this shipped for
    // months without anybody seeing it.
    expect(preUx7876(190 * 60_000)).toContain("HT");
    // The game as it actually rendered: halftime gone.
    expect(preUx7876(225 * 60_000)).not.toContain("HT");
    expect(preUx7876(225 * 60_000)).toEqual(["Q2", "Q3", "Q4", "OT"]);
    // And lowering the constant only moves the cliff — at 6.3% it arrives at a
    // longer span rather than never.
    const lowered = (span: number) => {
      const minSpacing = span * 0.063;
      const out: Array<{ timestamp: string; label: string }> = [];
      for (const b of boundaries()) {
        const t = new Date(b.timestamp).getTime();
        if (out.length > 0) {
          const prevT = new Date(out[out.length - 1].timestamp).getTime();
          if (t - prevT < minSpacing) {
            out[out.length - 1] = b;
            continue;
          }
        }
        out.push(b);
      }
      return out.map((x) => x.label);
    };
    expect(lowered(225 * 60_000)).toContain("HT");
    expect(lowered(300 * 60_000)).not.toContain("HT");
  });
});

describe("#7876 — both charts read the rule at their call site", () => {
  const ODDS_SOURCE = readFileSync(
    join(__dirname, "../components/OddsChart.tsx"),
    "utf8"
  );
  const SDC_SOURCE = readFileSync(
    join(__dirname, "../components/ScoreDifferentialChart.tsx"),
    "utf8"
  );

  it.each([
    ["OddsChart", ODDS_SOURCE],
    ["ScoreDifferentialChart", SDC_SOURCE],
  ])("%s runs BOTH passes, in order", (name, src) => {
    // A chart that placed labels without collapsing duplicates first would print
    // "end of the 2nd" stacked over "Top 3rd" on every baseball page — the pass
    // order is the contract, so it is asserted rather than assumed.
    const collapseAt = src.indexOf("collapseDuplicateTransitions(");
    const placeAt = src.indexOf("placePeriodLabels(");
    expect({ name, collapsed: collapseAt >= 0, placed: placeAt >= 0 }).toEqual({
      name,
      collapsed: true,
      placed: true,
    });
    expect(collapseAt).toBeLessThan(placeAt);
  });

  it.each([
    ["OddsChart", ODDS_SOURCE],
    ["ScoreDifferentialChart", SDC_SOURCE],
  ])("%s keeps no private copy of either number", (name, src) => {
    // #6658's lesson: a private copy is how one chart missed UX-P022 entirely.
    expect({ name, hit: /DUPLICATE_TRANSITION_WINDOW_MS\s*=/.test(src) }).toEqual({
      name,
      hit: false,
    });
    expect({ name, hit: /PERIOD_LABEL_INK_FRACTION\s*=/.test(src) }).toEqual({
      name,
      hit: false,
    });
    expect({ name, hit: /chartDuration\s*\*\s*0\.\d+/.test(src) }).toEqual({
      name,
      hit: false,
    });
  });
});

describe("#7876 — it is not an overtime bug: a regulation game loses HT at the whistle", () => {
  // ── WHAT THE WALK SAW ──────────────────────────────────────────────────────
  //
  // Rams 28–6 Giants, `/events/14780545`, Monday night, photographed at 390px
  // every 20 minutes on a page that was NEVER RELOADED (notice 42). The marker
  // strip, frame by frame, straight out of `artifacts/ux-1426/mnf/*.json`:
  //
  //     02:01Z  cycle 5   Q2 HT Q3
  //     02:21Z  cycle 6   Q2 HT Q3
  //     02:41Z  cycle 7   Q2 HT Q3 Q4
  //     03:01Z  cycle 8   Q2 HT Q3 Q4
  //     03:22Z  FINAL     Q2    Q3 Q4      ← halftime gone
  //     03:32Z  final+10  Q2    Q3 Q4      ← still gone, no reload
  //
  // This game never went to overtime. A reader watching the fourth quarter had
  // the halftime boundary on the chart, looked up at the whistle, and it was
  // gone — nothing they did, no page load in between.
  //
  // ── WHY THE ISSUE'S OWN ARITHMETIC MISSED IT ───────────────────────────────
  //
  // #7876 reasoned from a halftime of "structurally ~15 minutes", which puts the
  // crossover at 15 / 0.07 = 214 min and therefore out of reach of a regulation
  // game. But halftime is not a structural constant — it is an OBSERVED gap
  // between two `espn_state` boundaries, and here it was 12 minutes. That moves
  // the crossover to 12 / 0.07 = 171 min, which is an ordinary NFL broadcast:
  //
  //     span 166 min (cycle 8, live)   7% = 11.6 min  <  12 min gap  → HT kept
  //     span 192 min (at the whistle)  7% = 13.5 min  >  12 min gap  → HT DELETED
  //
  // So the overtime specimen was the one that got noticed, not the boundary of
  // the defect. Every NFL game whose observed halftime runs short of 7% of its
  // finished span loses the marker, and the span only ever grows, so the loss
  // always lands at or near the whistle — the moment the chart is most read.
  //
  // The arms below pin BOTH numbers, because a fix that kept this game's HT by
  // lowering the constant would just relocate the cliff again.
  const REG = JSON.parse(
    readFileSync(
      join(__dirname, "fixtures/periodLabelRegulation.14780545.nfl-final.json"),
      "utf8"
    )
  );

  const regBoundaries = () =>
    derivePeriodBoundaries(
      undefined,
      undefined,
      undefined,
      REG.commence_time,
      REG.period_markers,
      SPORT
    );

  /** The pre-#7876 collapse, frozen verbatim — the same control the overtime
   *  sweep uses, run against the regulation payload. */
  function preUx7876(span: number): string[] {
    const minSpacing = span * PERIOD_LABEL_MIN_SPACING_FRACTION;
    const out: Array<{ timestamp: string; label: string }> = [];
    for (const b of regBoundaries()) {
      const t = new Date(b.timestamp).getTime();
      if (out.length > 0) {
        const prevT = new Date(out[out.length - 1].timestamp).getTime();
        if (t - prevT < minSpacing) {
          out[out.length - 1] = b;
          continue;
        }
      }
      out.push(b);
    }
    return out.map((x) => x.label);
  }

  const LIVE_SPAN = 166 * 60_000; // cycle 8, 03:01Z, HT on the page
  const FINAL_SPAN = 192 * 60_000; // at the whistle, HT gone

  it("this game has no overtime, and its halftime is 12 minutes, not 15", () => {
    // The strawman guard for the whole block. If the fixture ever drifts to a
    // payload with an `OT` marker or a 15-minute halftime, every assertion below
    // becomes a restatement of the overtime case and proves nothing new.
    const labels = regBoundaries().map((b) => b.label);
    expect(labels).toEqual(["Q2", "HT", "Q3", "Q4"]);
    expect(labels).not.toContain("OT");

    const ts = regBoundaries().map((b) => new Date(b.timestamp).getTime());
    expect(Math.round((ts[2] - ts[1]) / 60_000)).toBe(12);
  });

  it("the old rule reproduces the walk exactly — kept live, dropped at the whistle", () => {
    // Not "the old rule is capable of dropping HT" — that was already known.
    // This is the specific pair of spans the page passed through on Monday
    // night, and the outputs are what the camera recorded at each of them.
    expect(preUx7876(LIVE_SPAN)).toEqual(["Q2", "HT", "Q3", "Q4"]);
    expect(preUx7876(FINAL_SPAN)).toEqual(["Q2", "Q3", "Q4"]);
  });

  it("the crossover sits inside regulation, which is the part #7876 understated", () => {
    // 12 min / 7% = 171.4 min. Stated as the two sides of the boundary rather
    // than as the quotient, so this fails if the constant or the gap moves.
    expect(preUx7876(171 * 60_000)).toContain("HT");
    expect(preUx7876(172 * 60_000)).not.toContain("HT");
  });

  it("the new rule keeps all four at every span this game passed through", () => {
    for (const min of [120, 166, 172, 175, 192, 240, 300, 360]) {
      expect(
        placePeriodLabels(
          collapseDuplicateTransitions(regBoundaries()),
          min * 60_000
        ).map((r) => r.label)
      ).toEqual(["Q2", "HT", "Q3", "Q4"]);
    }
  });

  it("and both charts draw HT on the real render of this payload", () => {
    // The helper being right is not the ship, same as the overtime arms above.
    const render = (Chart: unknown) =>
      renderToStaticMarkup(
        React.createElement(
          AnalyticsProvider,
          null,
          React.createElement(Chart as never, {
            history: REG.history,
            homeTeam: REG.home_team,
            awayTeam: REG.away_team,
            commenceTime: REG.commence_time,
            espnHistory: REG.espn_history,
            winProbHistory: REG.win_prob_history,
            scoreHistory: REG.score_history,
            eventStatus: REG.status,
            sportKey: SPORT,
            periodBoundaries: regBoundaries(),
          } as never)
        )
      );

    for (const Chart of [OddsChart, ScoreDifferentialChart]) {
      expect(labelNames(render(Chart))).toEqual(["Q2", "HT", "Q3", "Q4"]);
    }
  });
});

describe("#7876 — every file this suite reads travels with it", () => {
  // THE GUARD FOR THE CLASS THAT COST THIS SUITE A RED CI.
  //
  // The first version of this file read its specimen out of the capture tree it
  // was measured in, which is untracked. That is invisible to the author — the
  // bytes are right there on the laptop — and invisible to a local jest run, a
  // local build and a local typecheck. It surfaces only on a fresh checkout,
  // where the suite does not fail an assertion but FAILS TO START: `ENOENT`,
  // "Test suite failed to run", 989 other suites green around it.
  //
  // So the property asserted here is not "the file exists" — it existed all
  // along. It is "git will hand this file to a machine that has never seen this
  // laptop". That is the difference between the two, and it is the only form of
  // this check that can fail in the place where the mistake is made.
  const READS = [
    "fixtures/periodLabelOvertime.14780544.nfl-ot.json",
    "fixtures/periodLabelRegulation.14780545.nfl-final.json",
    "../components/OddsChart.tsx",
    "../components/ScoreDifferentialChart.tsx",
  ];

  /** Tracked ⇒ a fresh clone has it. Spawns git rather than stat-ing, because
   *  presence on this disk is exactly the thing that is not being asked. */
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

  it.each(READS)("%s is tracked", (rel) => {
    expect({ rel, tracked: isTracked(rel) }).toEqual({ rel, tracked: true });
  });

  it("and the predicate convicts the path this suite used to read — the control", () => {
    // Without this arm, `isTracked` returning `true` unconditionally — a wrong
    // `git` invocation, a swallowed non-zero status — would pass every arm above.
    // This is the exact path the red run died on. It is present on the laptop
    // that captured it and tracked by nothing, so it separates the two questions
    // on the machine where they are easiest to confuse.
    const capturedButNotCommitted = "../../artifacts/ux-1423/history.14780544.raw.json";
    expect(isTracked(capturedButNotCommitted)).toBe(false);
  });
});
