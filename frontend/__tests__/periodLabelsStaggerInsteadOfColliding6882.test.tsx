// #6882 — `HT` AND `Q3` STOP READING AS ONE TOKEN ON EVERY NFL CHART, WITHOUT
// EITHER OF THEM BEING DELETED.
//
// ── WHAT THE READER SAW ──────────────────────────────────────────────────────
//
// `/events/14638444` (Bills 41 – Lions 31) at 390px, on BOTH charts:
// `HT Q3` painted as a single grey run. Third independent sighting — ux/1327 saw
// it on this event, live/349 on two others the same night and routed it to ux as
// layout. Frame: `artifacts/ux-1328/6853-after-hero.png`.
//
// ── THE MEASUREMENT, IN PIXELS, BECAUSE THAT IS WHAT COLLIDES ────────────────
//
// `tools/period-label-gap-6882.mjs` reads the painted `getBoundingClientRect()`
// of every marker label on the live page and reports the CLEAR gap between
// adjacent ones — next label's left edge minus this one's right edge:
//
//   pair     win prob   score diff
//   Q2 → HT     60.4px      64.3px
//   HT → Q3      3.4px       5.5px   ← the defect
//   Q3 → Q4     22.6px      25.4px
//
// So the crowded pair is not a wobble: it is 6.6× tighter than the next tightest
// pair on the same chart. In time it is 15.0 min on the chart's own 200.0 min
// span = 7.50%, which clears `PERIOD_LABEL_MIN_SPACING_FRACTION` (7%) by half a
// percentage point — both labels are kept, and then have nowhere to go. NFL
// halftime is structurally ~15 min and an NFL broadcast ~3.3 h, so the ratio is a
// property of the sport: every NFL game, on the one boundary a reader most needs
// distinguished.
//
// (#6882's body says 7.83%. That divided by the 191.6 min span of `espn_history`
// alone; the charts divide by their full category extent, which is 200.0 min and
// includes the pre-kickoff and post-final points those series carry. The issue's
// conclusion is unchanged and its margin was if anything generous.)
//
// ── 🪤 THE OBVIOUS FIX IS THE ONE THAT MUST NOT BE TAKEN ─────────────────────
//
// Raising `PERIOD_LABEL_MIN_SPACING_FRACTION` past ~0.079 does collapse the pair
// — by DELETING `HT`. The collapse rule kept the LATER of a too-close pair (its
// docstring: "so `HT` wins over `Q2 end`"), so here the survivor is `Q3` and
// halftime vanishes from every NFL chart. The constant is also shared by both
// charts across every sport by deliberate design (#888 / latency/467), so a move
// is simultaneously a claim about innings, halves and hockey periods.
//
// The fix is therefore a LAYOUT change with both labels kept: the later one drops
// one row. A regression that "fixed" the crowding by thinning would pass a naive
// stagger assertion while deleting the label the issue exists to protect, so the
// first thing this file pins is that the marker SET is unchanged.
//
// #7876 UPDATE — THE TRAP ABOVE SPRANG WITHOUT ANYBODY TOUCHING THE CONSTANT.
// Overtime stretched the span, which against a proportional threshold is the
// same arithmetic as raising it, and `HT` was deleted from the Chiefs–Colts
// chart exactly as predicted here. The collapse-then-stagger pair is now one
// pass, `placePeriodLabels`, which drops a marker only when BOTH rows are full;
// the separation this file pins is unchanged in substance, so every expectation
// below still reads the same numbers.
//
// ── SPECIMEN ─────────────────────────────────────────────────────────────────
//
// `GET /api/events/14638444/history`, verbatim and unsampled in every field
// either chart is handed: all 4 `period_markers`, all 732 `history`, all 180
// `espn_history`, all 17 `score_history`, all 3,550 `aggregate_line`, all 11
// `scoring_plays`, all four `win_prob_history` series. It is a large fixture on
// purpose: the stagger decision is a fraction of the CHART's span, and the span
// is whatever the drawn series make it, so a fixture with the series thinned is a
// fixture that no longer reproduces the page.

import React from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { ComposedChart, ReferenceLine, XAxis, YAxis } from "recharts";
import { readFileSync } from "fs";
import { join } from "path";

import OddsChart from "@/components/OddsChart";
import ScoreDifferentialChart from "@/components/ScoreDifferentialChart";
// The REAL provider `app/layout.tsx` wraps the page in, not a stubbed hook, so
// what renders here is what ships. `OddsChart` calls `useAnalyticsContext`,
// which throws outside it.
import { AnalyticsProvider } from "@/components/Analytics";
import {
  collapseDuplicateTransitions,
  placePeriodLabels,
  derivePeriodBoundaries,
  PERIOD_LABEL_MIN_SPACING_FRACTION,
  PERIOD_LABEL_STAGGER_SPACING_MULTIPLE,
  PERIOD_LABEL_INK_FRACTION,
  PERIOD_LABEL_ROW_HEIGHT_PX,
  DUPLICATE_TRANSITION_WINDOW_MS,
} from "@/lib/periodMarkers";

const WIRE = JSON.parse(
  readFileSync(
    join(__dirname, "fixtures/periodLabelStagger.14638444.nfl-final.json"),
    "utf8"
  )
);

const ODDS_SOURCE = readFileSync(
  join(__dirname, "../components/OddsChart.tsx"),
  "utf8"
);
const SDC_SOURCE = readFileSync(
  join(__dirname, "../components/ScoreDifferentialChart.tsx"),
  "utf8"
);

const SPORT = "americanfootball_nfl";

/**
 * The span both charts divide by — their full category extent, which on a
 * completed event is the default "Since Start" window: `commence_time`
 * (2026-09-18T00:15:00Z) to the last plotted point (03:34:58.865Z) across every
 * series in the fixture. 199.98 min.
 *
 * It is NOT the span between the first and last period marker (104.5 min). Using
 * that narrower window puts `HT → Q3` at 14.35% and the specimen stops
 * reproducing the defect — the arithmetic silently describes a different chart.
 * Asserted against the components below, which compute their own.
 */
const CHART_SPAN_MS = Math.round(199.98108893333335 * 60_000);

/** The boundaries the page derives and hands BOTH charts. */
function boundaries() {
  return derivePeriodBoundaries(
    undefined,
    undefined,
    undefined,
    WIRE.period_markers,
    SPORT
  );
}

/**
 * recharts draws nothing inside `ResponsiveContainer` without a viewport, so a
 * server render cannot observe a `<ReferenceLine>` at all — the stagger is
 * literally invisible in the markup. Both charts report the row of each label
 * they will draw on their wrapper instead, the same channel CERT-1984 opened for
 * the count and #6658 asserts through.
 */
function labelRows(markup: string): number[] {
  const m = markup.match(/data-period-label-rows="([^"]*)"/);
  if (!m) throw new Error("wrapper did not report data-period-label-rows");
  return m[1] === "" ? [] : m[1].split(",").map(Number);
}

function periodBoundaryCount(markup: string): number {
  const m = markup.match(/data-period-boundaries="(\d+)"/);
  if (!m) throw new Error("wrapper did not report data-period-boundaries");
  return Number(m[1]);
}

function renderOdds(overrides: Record<string, unknown> = {}): string {
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
      winProbSources: WIRE.win_prob_sources,
      aggregateLine: WIRE.aggregate_line,
      scoringPlays: WIRE.scoring_plays,
      eventStatus: WIRE.status,
      periodBoundaries: boundaries(),
      ...overrides,
      } as never)
    )
  );
}

function renderSdc(overrides: Record<string, unknown> = {}): string {
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
      ...overrides,
    } as never)
  );
}

const CHARTS = [
  ["OddsChart", renderOdds],
  ["ScoreDifferentialChart", renderSdc],
] as const;

describe("#6882 — the specimen actually carries the collision", () => {
  // Strawman guard. Every assertion below is about a pair being crowded; on a
  // fixture whose markers are evenly spread they would all pass vacuously while
  // the page still printed `HT Q3`.
  it("derives the four NFL markers, HT among them", () => {
    expect(boundaries().map((b) => b.label)).toEqual(["Q2", "HT", "Q3", "Q4"]);
  });

  it("carries the crowded pair: 59.5 / 15.0 / 30.0 minutes between markers", () => {
    // Stated in MINUTES, which is a fact about the specimen alone and needs no
    // model of how either chart computes its span.
    const b = boundaries();
    const gaps = b
      .slice(1)
      .map(
        (x, i) =>
          (new Date(x.timestamp).getTime() -
            new Date(b[i].timestamp).getTime()) /
          60_000
      );
    expect(gaps.map((g) => Math.round(g * 10) / 10)).toEqual([59.5, 15.0, 30.0]);
    // HT → Q3 is the tight one and it is not marginally tight — the next pair is
    // twice its width. That is the 3.4px the probe measured, in time terms.
    expect(Math.min(...gaps)).toBe(gaps[1]);
    expect(Math.min(gaps[0], gaps[2]) / gaps[1]).toBeGreaterThanOrEqual(2);
  });

  it("the chart span is the one measured on the page, and nothing is collapsed at it", () => {
    // `CHART_SPAN_MS` is the number every fraction below divides by, so it is
    // pinned: if the fixture ever drifts, the arithmetic in this file stops
    // describing the page and these tests must be re-derived, not re-baselined.
    const b = boundaries();
    const fractions = b
      .slice(1)
      .map(
        (x, i) =>
          (new Date(x.timestamp).getTime() -
            new Date(b[i].timestamp).getTime()) /
          CHART_SPAN_MS
      );

    // 29.75% / 7.50% / 15.00%. Every pair clears the collapse threshold, so the
    // defect is entirely about SURVIVORS — there is nothing here for a thinning
    // rule to do, which is exactly why raising it would have to delete a label.
    expect(placePeriodLabels(b, CHART_SPAN_MS)).toHaveLength(b.length);
    for (const f of fractions) {
      expect(f).toBeGreaterThan(PERIOD_LABEL_MIN_SPACING_FRACTION);
    }
    // HT → Q3 clears the 7% collapse threshold by 1.07× — half a percentage
    // point — and then paints 3.4px from its neighbour.
    expect(fractions[1]).toBeCloseTo(0.075, 3);
    expect(fractions[1] / PERIOD_LABEL_MIN_SPACING_FRACTION).toBeLessThan(1.1);
  });
});

describe("#6882 — the stagger fires on exactly the crowded pair", () => {
  it("drops Q3 a row and leaves the other three on the top row", () => {
    const b = boundaries();
    const rowed = placePeriodLabels(b, CHART_SPAN_MS);

    expect(rowed.map((r) => [r.label, r.labelRow])).toEqual([
      ["Q2", 0],
      ["HT", 0],
      ["Q3", 1],
      ["Q4", 0],
    ]);
  });

  it("keeps the EARLIER label on the top row, so HT stays where a reader looks", () => {
    // Not cosmetic preference. The collapse the 🪤 above rejects would have kept
    // `Q3` and deleted `HT`; if the stagger also demoted `HT` it would be
    // re-enacting that choice in a quieter way.
    const b = boundaries();
    const rowed = placePeriodLabels(b, CHART_SPAN_MS);
    expect(rowed.find((r) => r.label === "HT")!.labelRow).toBe(0);
  });

  it("changes NOTHING about which markers are drawn", () => {
    // The whole point of the fix. A stagger that thinned would be the rejected
    // collapse wearing a different name. Asserted against the DERIVED list, not
    // against a pre-thinned one — under #7876 there is no thinning pass in front
    // of the layout any more, so this now says the stronger thing: everything
    // the page derived reaches the chart.
    const b = boundaries();
    const rowed = placePeriodLabels(b, CHART_SPAN_MS);

    expect(rowed.map((r) => r.label)).toEqual(b.map((k) => k.label));
    expect(rowed.map((r) => r.timestamp)).toEqual(b.map((k) => k.timestamp));
  });

  it("leaves a comfortably-spaced ladder entirely on the top row", () => {
    // The negative control the fixture cannot provide: markers an hour apart on a
    // six-hour chart have no crowding to fix, and a rule that staggered them
    // would be adding disorder, not removing it.
    const roomy = Array.from({ length: 6 }, (_, i) => ({
      timestamp: new Date(Date.UTC(2026, 8, 18, i, 0, 0)).toISOString(),
      label: `P${i + 1}`,
    }));
    const span = 5 * 60 * 60 * 1000;
    expect(
      placePeriodLabels(roomy, span).map((r) => r.labelRow)
    ).toEqual([0, 0, 0, 0, 0, 0]);
  });

  it("alternates rather than running away when three markers are all crowded", () => {
    // Two rows, never a third — the render has no offset for one. Under #7876
    // the guarantee is direct rather than inherited from a collapse that ran
    // first: a marker is placed on the lowest row whose last label is a full
    // ink-width away, and if neither row has one it is not drawn at all. So the
    // row index cannot exceed `PERIOD_LABEL_MAX_ROWS - 1` by construction, and
    // this pins that the implementation really alternates rather than running
    // away. 8 min on a 100 min span is 8% — inside the 12.6% ink, so every
    // consecutive pair here is genuinely crowded.
    const span = 100 * 60 * 1000;
    const crowded = [0, 8, 16, 24].map((m) => ({
      timestamp: new Date(Date.UTC(2026, 8, 18, 0, m, 0)).toISOString(),
      label: `M${m}`,
    }));
    const rows = placePeriodLabels(crowded, span).map((r) => r.labelRow);
    expect(rows).toEqual([0, 1, 0, 1]);
    expect(Math.max(...rows)).toBeLessThanOrEqual(1);
  });

  it("a pair inside one label's ink staggers, and a pair outside it does not", () => {
    // The multiple is what makes the ink wider than the old collapse threshold.
    // At ≤ 1 the ink would be narrower than 7%, and #7876's claim — that the old
    // rule deleted markers the layout could always have drawn — would be false.
    expect(PERIOD_LABEL_STAGGER_SPACING_MULTIPLE).toBeGreaterThan(1);

    const span = 60 * 60 * 1000;
    const justInside = PERIOD_LABEL_MIN_SPACING_FRACTION * 1.01;
    const justOutside =
      PERIOD_LABEL_MIN_SPACING_FRACTION *
      PERIOD_LABEL_STAGGER_SPACING_MULTIPLE *
      1.01;
    const pair = (fraction: number) => [
      { timestamp: new Date(0).toISOString(), label: "A" },
      { timestamp: new Date(span * fraction).toISOString(), label: "B" },
    ];
    expect(placePeriodLabels(pair(justInside), span)[1].labelRow).toBe(1);
    expect(placePeriodLabels(pair(justOutside), span)[1].labelRow).toBe(0);
  });
});

describe("#6882 — both components read the rule at their call sites", () => {
  // The helper existing is not the ship. A correct helper called by nobody
  // renders the same crowded chart, so these assert what the COMPONENTS report.
  it.each(CHARTS)("%s reports the staggered row set", (_name, render) => {
    // The whole claim, on the component, computing its own span: four markers
    // drawn, and the third — `Q3`, by the label order pinned above — one row
    // down. Both charts, because the crowding is on both (3.4px and 5.5px) and a
    // fix to one is half a fix.
    expect(labelRows(render())).toEqual([0, 0, 1, 0]);
  });

  it.each(CHARTS)("%s draws one row per marker it draws", (_name, render) => {
    const markup = render();
    expect(labelRows(markup)).toHaveLength(periodBoundaryCount(markup));
  });

  it.each(CHARTS)("%s still draws all four markers (nothing thinned)", (_name, render) => {
    expect(periodBoundaryCount(render())).toBe(4);
  });

  it.each(CHARTS)("%s passes the row through to the label as dy", (_name, _render) => {
    // SSR cannot observe the `<ReferenceLine>`, so the wiring from `labelRow` to
    // the rendered offset is asserted on the source. `dy` is the channel because
    // recharts keeps it through `filterProps` (it is an SVG text attribute) and
    // `Text` adds it to y; `position` alone cannot express a vertical row.
    const src = _name === "OddsChart" ? ODDS_SOURCE : SDC_SOURCE;
    expect(src).toMatch(/dy:\s*\(\(b as \{ labelRow\?: number \}\).labelRow \|\| 0\) \* PERIOD_LABEL_ROW_HEIGHT_PX/);
    expect(src).toMatch(/placePeriodLabels\(/);
  });

  it("neither chart re-implements the stagger privately", () => {
    // #6658's lesson, one rule up: a private copy is how the score differential
    // chart missed UX-P022 entirely and printed `TB2` / `T5T6`.
    for (const [name, src] of [
      ["OddsChart", ODDS_SOURCE],
      ["ScoreDifferentialChart", SDC_SOURCE],
    ] as const) {
      expect({ name, hit: /PERIOD_LABEL_STAGGER_SPACING_MULTIPLE\s*=/.test(src) }).toEqual({
        name,
        hit: false,
      });
      expect({ name, hit: /PERIOD_LABEL_ROW_HEIGHT_PX\s*=\s*\d/.test(src) }).toEqual({
        name,
        hit: false,
      });
    }
  });

  it("the drop is a whole line, not a hairline", () => {
    // A row height under the label's own font size would overlap the row above
    // and the fix would read as a rendering fault rather than a layout. Both
    // charts label at 10–11px.
    expect(PERIOD_LABEL_ROW_HEIGHT_PX).toBeGreaterThanOrEqual(12);
  });
});

describe("#6882 — what it does to a sport that is not football", () => {
  // MEASURED, NOT ASSUMED. `tools/period-label-gap-6882.mjs` on the #6658
  // baseball specimen (`/events/15313139`, Reds–Dodgers) at 390px:
  //
  //   T1 → T3  35.0px   T3 → T4   9.3px   T4 → B6  50.4px
  //   B6 → B7  15.9px   B7 → T9  39.6px
  //
  // `T3 → T4` at 9.3px of clear air is ~10.2% of the 252px plot once the 16.3px
  // label is added back, which is INSIDE the 7%–12.6% band. So this ship is not
  // NFL-only: it staggers a tight inning pair too, and `B6 → B7` (15.9px,
  // ~12.8%) sits just outside and does not. That is the rule doing what it says
  // rather than a surprise, but it is a wider reach than the issue title
  // suggests and it is written down here so nobody rediscovers it on a page.
  //
  // What must hold on a dense ladder is the INVARIANT, not a row vector: two
  // rows are enough, nothing is dropped, and no two labels sharing a row are
  // close enough to touch.
  const MLB = JSON.parse(
    readFileSync(
      join(__dirname, "fixtures/periodLabelSpacing.15313139.mlb-live.json"),
      "utf8"
    )
  );

  /** What the page hands the layout: derived, then with the markers that name
   *  one moment twice removed (#7876's semantic pass, which has no span in it). */
  function mlbRowed(span: number) {
    const b = derivePeriodBoundaries(
      undefined,
      undefined,
      undefined,
      MLB.period_markers,
      "baseball_mlb"
    );
    return { kept: collapseDuplicateTransitions(b), span };
  }

  // The chart span is unknown here (this fixture belongs to another file), so
  // the invariants are checked across a SWEEP of plausible spans rather than one
  // — which is stronger: it says the layout is sound at every chart length, not
  // just at the one this game happened to have.
  const SPANS = [60, 90, 120, 180, 240, 360].map((m) => m * 60_000);

  it.each(SPANS)("never needs a third row (span %ims)", (span) => {
    const { kept } = mlbRowed(span);
    const rows = placePeriodLabels(kept, span).map((r) => r.labelRow);
    expect(rows.length).toBeGreaterThan(0);
    expect([...new Set(rows)].every((r) => r === 0 || r === 1)).toBe(true);
  });

  /**
   * THE RULE AS IT STOOD BEFORE #7876, frozen. Not a reimplementation to keep in
   * step — a BEFORE control, snapshotted while the defect was live, so "the new
   * rule draws more of the ladder" is a measurement and not a claim. It is never
   * updated; if it ever needs to change, it has stopped being the before.
   */
  function preUx7876(labels: Array<{ timestamp: string; label: string }>, span: number) {
    const minSpacing = span * PERIOD_LABEL_MIN_SPACING_FRACTION;
    const deduped: Array<{ timestamp: string; label: string }> = [];
    for (const b of labels) {
      const t = new Date(b.timestamp).getTime();
      if (deduped.length > 0) {
        const prevT = new Date(deduped[deduped.length - 1].timestamp).getTime();
        if (t - prevT < minSpacing) {
          deduped[deduped.length - 1] = b;
          continue;
        }
      }
      deduped.push(b);
    }
    return deduped;
  }

  it.each(SPANS)("drops an inning only where the old rule dropped more (span %ims)", (span) => {
    // "Drops nothing" was true when a collapse pass ran in front of the layout
    // and the layout only assigned rows. There is no such pass now, so the
    // honest property is the ship itself: the ladder a reader gets is never
    // thinner than the one the old rule gave them, and on a dense chart it is
    // dramatically fuller — 15313139 went from 6 drawn labels to 12.
    const { kept } = mlbRowed(span);
    const now = placePeriodLabels(kept, span);
    const before = preUx7876(
      derivePeriodBoundaries(
        undefined, undefined, undefined, MLB.period_markers, "baseball_mlb",
      ),
      span,
    );
    expect(now.length).toBeGreaterThanOrEqual(before.length);
  });

  it.each(SPANS)("draws a subsequence of what it was handed, in order (span %ims)", (span) => {
    // The layout may drop, but it may never reorder or invent. A marker out of
    // order is the `T9 left of T1` class (L2-163) arriving from a new direction.
    const { kept } = mlbRowed(span);
    const drawn = placePeriodLabels(kept, span).map((r) => r.timestamp);
    const handed = kept.map((k) => k.timestamp);
    let i = 0;
    for (const ts of drawn) {
      i = handed.indexOf(ts, i);
      expect(i).toBeGreaterThanOrEqual(0);
      i += 1;
    }
  });

  it.each(SPANS)("leaves no two labels sharing a row too close to read (span %ims)", (span) => {
    // The property the whole ship is for, and under #7876 it is the rule's own
    // definition rather than a consequence of two thresholds lining up: a marker
    // is only placed on a row whose last label is a full ink-width behind it.
    // This is the assertion that would catch a "fix" that bought halftime back
    // by letting labels touch.
    const { kept } = mlbRowed(span);
    const rowed = placePeriodLabels(kept, span);
    const band = span * PERIOD_LABEL_INK_FRACTION;

    for (const row of [0, 1]) {
      const onRow = rowed.filter((r) => r.labelRow === row);
      for (let i = 1; i < onRow.length; i++) {
        const gap =
          new Date(onRow[i].timestamp).getTime() -
          new Date(onRow[i - 1].timestamp).getTime();
        expect(gap).toBeGreaterThanOrEqual(band);
      }
    }
  });

  it("the same invariant holds on the NFL specimen", () => {
    const rowed = placePeriodLabels(boundaries(), CHART_SPAN_MS);
    const band = CHART_SPAN_MS * PERIOD_LABEL_INK_FRACTION;
    for (const row of [0, 1]) {
      const onRow = rowed.filter((r) => r.labelRow === row);
      for (let i = 1; i < onRow.length; i++) {
        expect(
          new Date(onRow[i].timestamp).getTime() -
            new Date(onRow[i - 1].timestamp).getTime()
        ).toBeGreaterThanOrEqual(band);
      }
    }
  });
});

describe("#6882 — `dy` really is a vertical offset, in recharts' own hands", () => {
  // The one link neither component test can reach. Both charts size themselves
  // through `ResponsiveContainer`, which draws NOTHING without a viewport, so a
  // server render of either one proves the row was computed and says nothing
  // about whether it moved any ink. `dy` survives only because it is in
  // recharts' `SVGElementPropKeys` allowlist and `Text` adds it to `y` — two
  // internals, either of which a version bump could change silently, leaving the
  // stagger computed, asserted, green and invisible.
  //
  // So this renders recharts directly at a FIXED size (the one way to get real
  // geometry out of a server render) and reads the painted `y`.
  /** recharts numbers its `clipPath` ids from a module-global counter, so two
   *  identical charts rendered in one process never produce identical bytes. */
  const stableIds = (markup: string) => markup.replace(/recharts\d+-clip/g, "clip");

  // JSX rather than `React.createElement`: recharts widens `XAxis.defaultProps.type`
  // to `string`, which no `createElement` overload accepts, and the resulting
  // TS2769 is a typing wart in the library, not a fact about this chart.
  function chart(label: Record<string, unknown>): string {
    return renderToStaticMarkup(
      <ComposedChart width={400} height={200} data={[{ x: "a", v: 1 }, { x: "b", v: 2 }]}>
        <XAxis dataKey="x" />
        <YAxis />
        <ReferenceLine x="a" label={label} />
      </ComposedChart>
    );
  }

  function labelY(dy: number): number {
    const markup = chart({ value: "Q3", position: "insideTopLeft", dy });
    // `y` is emitted BEFORE `class` on the element, so the tag is matched whole
    // and the attribute read out of it — an ordered pattern silently found
    // nothing and read as "the label is absent".
    const tag = markup.match(/<text[^>]*recharts-label[^>]*>/);
    if (!tag) throw new Error(`no label text in markup: ${markup.slice(0, 400)}`);
    const y = tag[0].match(/\sy="([\d.]+)"/);
    if (!y) throw new Error(`label carries no y: ${tag[0]}`);
    return Number(y[1]);
  }

  it("moves the label down by exactly the row height", () => {
    expect(labelY(PERIOD_LABEL_ROW_HEIGHT_PX) - labelY(0)).toBe(
      PERIOD_LABEL_ROW_HEIGHT_PX
    );
  });

  it("row 0 leaves the label exactly where it was before the fix", () => {
    // The no-op half, and the reason this ship is safe to land on every sport at
    // once: an unstaggered marker — which is all of them on a baseball, soccer or
    // hockey page — must render byte-identically to the pre-fix code.
    expect(
      stableIds(chart({ value: "Q3", position: "insideTopLeft", dy: 0 }))
    ).toBe(stableIds(chart({ value: "Q3", position: "insideTopLeft" })));
  });
});

describe("#6882 — the case the collapse rule existed for still collapses", () => {
  it("still keeps the LATER of a genuinely too-close pair", () => {
    // The pair the old docstring named: "End of Q2" 30 seconds before
    // "Halftime". #7876 removed the proportional collapse, and this is the check
    // that it removed the arithmetic and not the JUDGEMENT — two markers naming
    // one moment must still resolve to the later one, or the fix has traded a
    // deleted halftime for a doubled one.
    const kept = collapseDuplicateTransitions([
      { timestamp: "2026-09-16T22:40:00Z", label: "Q2 end" },
      { timestamp: "2026-09-16T22:40:30Z", label: "HT" },
      { timestamp: "2026-09-16T23:40:00Z", label: "Q3" },
    ]);
    expect(kept.map((k) => k.label)).toEqual(["HT", "Q3"]);
  });

  it("collapses that pair at EVERY chart length, which the old rule could not", () => {
    // The #7876 defect in one assertion. The old rule read this pair as a
    // fraction of the span, so on a long chart it also swallowed halftime and on
    // a short one it stopped swallowing "Q2 end". The replacement asks a question
    // with no span in it, so the answer cannot move.
    const pair = [
      { timestamp: "2026-09-16T22:40:00Z", label: "Q2 end" },
      { timestamp: "2026-09-16T22:40:30Z", label: "HT" },
    ];
    expect(collapseDuplicateTransitions(pair).map((k) => k.label)).toEqual(["HT"]);
    // …and it leaves a real boundary alone at every length, including the one
    // that deleted halftime from Chiefs–Colts.
    const real = [
      { timestamp: "2026-09-21T01:49:40Z", label: "HT" },
      { timestamp: "2026-09-21T02:04:41Z", label: "Q3" },
    ];
    expect(collapseDuplicateTransitions(real).map((k) => k.label)).toEqual(["HT", "Q3"]);
  });

  it("the threshold the trap was written about has not moved", () => {
    // Kept as a pin even though nothing compares a gap to it any more: it is the
    // term `PERIOD_LABEL_INK_FRACTION` is written in, so moving it silently
    // rescales the layout.
    expect(PERIOD_LABEL_MIN_SPACING_FRACTION).toBe(0.07);
    expect(PERIOD_LABEL_INK_FRACTION).toBeCloseTo(0.126, 6);
  });

  it("the duplicate window sits in the measured gap between the two clusters", () => {
    // 120s is the widest duplicate and 240s the tightest real boundary across
    // the four payloads the constant was derived from. A window outside that
    // corridor is either re-enacting #7876 or letting a moment be named twice.
    expect(DUPLICATE_TRANSITION_WINDOW_MS).toBeGreaterThan(120_000);
    expect(DUPLICATE_TRANSITION_WINDOW_MS).toBeLessThan(240_000);
  });
});
