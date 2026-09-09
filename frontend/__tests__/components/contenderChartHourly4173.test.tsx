/**
 * ═══ #4173: THE CONTENDER CHART DRAWS THE READINGS WE HOLD ═══
 *
 * The ship, in one sentence: the server publishes `trend_hourly` beside
 * `trend`, and the chart reads it — so a title race that moved in an afternoon
 * is drawn as an afternoon instead of as one daily step, and the `1D` chip
 * stops being a permanently disabled button.
 *
 * CERT-2351 blocked the backend half on exactly the right ground: the payload
 * carried the finer series and nothing rendered it, so the user-visible ship
 * did not exist. This file is the catching test that block named — *"one daily
 * point plus 3+ hourly points in 24h must render the hourly chart, enable/draw
 * `1D`, and leave the sparkline daily"* — plus a guard for each of the four
 * places the change could have gone wrong quietly.
 *
 * ⚠️ **EVERY PIN HERE ASSERTS THE POSITIVE AND BANS ITS OPPOSITE, AND THAT IS
 * NOT BELT-AND-BRACES.** The lesson was paid for on this branch: a source pin
 * reading `'"hour"' in source` was satisfied by the `.label("hour")` sitting
 * next to `date_trunc("hour", …)`, so mutating `hour` → `day` — the single
 * change that undoes the whole ship — ran GREEN while nineteen other mutants
 * went red. A pin that can be satisfied by a neighbour is not a pin. So where
 * this file asserts "the chart drew the hourly series" it also asserts "and it
 * did not draw the daily one", which is the half a collapse-to-days mutation
 * has to survive.
 */

import React from "react";
import { renderToStaticMarkup } from "react-dom/server";

import ContenderChart from "@/components/tournament/ContenderChart";
import TrendSparkline from "@/components/tournament/TrendSparkline";
import {
  HOUR_DAYS,
  NO_WINDOW_STARTS,
  axisSpan,
  axisStepDays,
  axisTickLabel,
  axisTicks,
  chartGeometry,
  chartPoints,
  chartSeries,
  isDayKey,
  pointsInTimeframe,
  rangeIsDrawable,
  seriesPoints,
  timeframeIsDrawable,
} from "@/lib/contenderChart";
import { deltaWindowNote } from "@/lib/contenderChart";
import type {
  TournamentFinePoint,
  TournamentRow,
  TournamentTrendPoint,
} from "@/lib/tournament";

const WIDTH = 320;
const HEIGHT = 96;

/** `2026-09-06` + n days, as the daily series keys them. */
function days(start: string, count: number, from = 0.2): TournamentTrendPoint[] {
  const base = Date.parse(`${start}T00:00:00Z`);
  return Array.from({ length: count }, (_, i) => ({
    date: new Date(base + i * 86_400_000).toISOString().slice(0, 10),
    probability: from + i * 0.002,
  }));
}

/** Hourly readings from an instant, as the fine series keys them. */
function hours(
  startIso: string,
  count: number,
  from = 0.3,
  step = 0.01
): TournamentFinePoint[] {
  const base = Date.parse(startIso);
  return Array.from({ length: count }, (_, i) => ({
    at: `${new Date(base + i * 3_600_000).toISOString().slice(0, 13)}:00:00Z`,
    probability: from + i * step,
  }));
}

function row(overrides: Partial<TournamentRow> = {}): TournamentRow {
  return {
    entity_key: "alcaraz",
    display_name: "Carlos Alcaraz",
    seed: 1,
    country: "ESP",
    rank: 1,
    state: "live",
    probability: 0.42,
    probability_is_live: true,
    observed_at: "2026-09-09T12:00:00+00:00",
    age_hours: 0.5,
    price_state: "live",
    freshest_observed_at: "2026-09-09T12:00:00+00:00",
    freshest_age_hours: 0.5,
    stale_sources: [],
    mixed_freshness: false,
    source_count: 2,
    sources: [],
    blend_rule: "mean",
    divergent: false,
    trend: days("2026-08-20", 20),
    trend_delta: 0.04,
    ...overrides,
  };
}

/**
 * THE SPECIMEN THE BLOCK NAMED, to the letter: one daily point, and four hourly
 * readings inside the last 24 hours.
 *
 * Deliberately the minimum rather than a realistic board — a fix that only
 * works on 300 points is a fix with an undiscovered floor, and this is the
 * shape a market that has only just started trading has.
 */
const MINIMAL = row({
  trend: [{ date: "2026-09-08", probability: 0.31 }],
  trend_hourly: hours("2026-09-09T06:00:00Z", 4, 0.31, 0.03),
});

/** A full board: 20 daily points, the last four days of them also hourly. */
const FULL = row({
  trend: days("2026-08-20", 20),
  trend_hourly: hours("2026-09-06T00:00:00Z", 85, 0.3, 0.001),
});

/** The same row as the site served it BEFORE #4173 — no fine series at all. */
const DAILY_ONLY = row({ trend: days("2026-08-20", 20), trend_hourly: undefined });

function html(rows: TournamentRow[]): string {
  return renderToStaticMarkup(
    <ContenderChart
      rows={rows}
      draw="mens-singles"
      selection={rows.map((r) => r.entity_key)}
      onToggle={() => {}}
    />
  );
}

/** The `1D` chip's rendered `<button …>` tag, so `disabled` can be read off it. */
function chipTag(markup: string, option: string): string {
  const match = markup.match(
    new RegExp(`<button[^>]*data-option="${option}"[^>]*>`)
  );
  if (!match) throw new Error(`no ${option} chip in the rendered chart`);
  return match[0];
}

// ───────────────────────────────────────────────────────────────────────────
// THE SHIP
// ───────────────────────────────────────────────────────────────────────────

describe("#4173 — the chart draws the hourly series", () => {
  it("draws the hourly readings, and NOT one averaged point per day", () => {
    const series = chartSeries([MINIMAL]);
    const geometry = chartGeometry(series, "ALL", WIDTH, HEIGHT);

    // THE POSITIVE: every hourly reading is a vertex.
    for (const point of MINIMAL.trend_hourly!) {
      expect(geometry.keys).toContain(point.at);
    }
    const drawn = seriesPoints(series[0], geometry, "ALL");
    expect(drawn.split(" ")).toHaveLength(1 + MINIMAL.trend_hourly!.length);

    // THE BAN, and it is the half a `date_trunc('day')` mutation must survive:
    // the four readings of 9 Sep must NOT have collapsed onto one key for that
    // day. Without this line a chart that averaged them back down to a single
    // daily point would still satisfy every assertion above about the daily
    // point that IS legitimately there.
    expect(geometry.keys).not.toContain("2026-09-09");
    expect(geometry.keys.filter((key) => key.startsWith("2026-09-09"))).toHaveLength(
      4
    );
  });

  it("enables the 1D chip, which was structurally dead before", () => {
    const fine = chartSeries([MINIMAL]);
    const coarse = chartSeries([DAILY_ONLY]);

    // THE POSITIVE: 1D draws, and draws a LINE — two vertices, not one.
    expect(rangeIsDrawable(fine, "1D", NO_WINDOW_STARTS)).toBe(true);
    expect(timeframeIsDrawable(fine, "1D")).toBe(true);
    const geometry = chartGeometry(fine, "1D", WIDTH, HEIGHT);
    expect(seriesPoints(fine[0], geometry, "1D").split(" ").length).toBeGreaterThanOrEqual(
      2
    );

    // THE CONTROL: on a daily-only board 1D is still undrawable, because one
    // point is still not a line. A change that enabled the chip unconditionally
    // would pass the assertions above and fail here.
    expect(rangeIsDrawable(coarse, "1D", NO_WINDOW_STARTS)).toBe(false);

    // And the reader can see the difference: the chip is disabled on one and
    // not on the other.
    expect(chipTag(html([MINIMAL]), "1D")).not.toContain("disabled");
    expect(chipTag(html([DAILY_ONLY]), "1D")).toContain("disabled");
  });

  it("leaves the sparkline daily and `trend_delta`'s window alone", () => {
    // The sparkline publishes how many vertices it drew. 250 of them in 52px is
    // mush, which is why both series are permanent — see `TournamentRow`.
    const spark = renderToStaticMarkup(
      <TrendSparkline trend={FULL.trend} delta={FULL.trend_delta} />
    );
    expect(spark).toContain(`data-points="${FULL.trend.length}"`);
    expect(FULL.trend).toHaveLength(20);
    // THE BAN: it must not have been handed the 85-point fine series.
    expect(spark).not.toContain(`data-points="${FULL.trend_hourly!.length}"`);

    // And the movement note still measures the DAILY history, so a 14-day delta
    // is never printed beside a 30-day line.
    expect(deltaWindowNote([FULL])).toBe("Movement since 20 Aug.");
  });
});

// ───────────────────────────────────────────────────────────────────────────
// THE FOUR PLACES IT COULD HAVE GONE WRONG QUIETLY
// ───────────────────────────────────────────────────────────────────────────

describe("#4173 — the splice keeps the history the fine series does not cover", () => {
  it("ALL still spans the DAILY window, not the fine one", () => {
    const points = chartPoints(FULL);

    // 20 daily points, of which 17 predate the fine window, plus 85 hourly.
    expect(points).toHaveLength(17 + 85);
    expect(points[0].at).toBe("2026-08-20");
    expect(points[points.length - 1].at).toBe("2026-09-09T12:00:00Z");

    const span = axisSpan(chartGeometry(chartSeries([FULL]), "ALL", WIDTH, HEIGHT));
    expect(span?.short).toBe("21d");

    // THE BAN: reading only `trend_hourly` would have been a resolution gain
    // paid for with 16 silent days of history, on the one chip whose name
    // promises the opposite.
    expect(span?.short).not.toBe("4d");
  });

  it("draws the overlap ONCE — the daily mean is not stacked on its own hours", () => {
    const keys = chartPoints(FULL).map((p) => p.at);
    // 6-9 Sep are covered hourly, so no bare day key for them survives.
    for (const day of ["2026-09-06", "2026-09-07", "2026-09-08"]) {
      expect(keys).not.toContain(day);
      expect(keys.some((key) => key.startsWith(`${day}T`))).toBe(true);
    }
    // And the days BEFORE the fine window are still there, as days.
    expect(keys).toContain("2026-09-05");
    expect(keys.filter((key) => !isDayKey(key))).toHaveLength(85);
  });
});

describe("#4173 — a timeframe over instants is a duration, not a bucket count", () => {
  it("1D over instants takes the last 24 HOURS", () => {
    const points = chartPoints(FULL);
    const window = pointsInTimeframe(points, "1D");

    // The last reading is 9 Sep 12:00Z, so the window opens at 8 Sep 12:00Z —
    // 25 hourly stamps inclusive.
    expect(window).toHaveLength(25);
    expect(window[0].at).toBe("2026-09-08T12:00:00Z");

    // THE BAN: the day-bucket convention is `(days - 1)`, which for 1D is ZERO
    // milliseconds. Applied to instants it takes only readings at the very last
    // instant, so the chip would go from permanently disabled to permanently
    // empty — a different bug wearing the same fix.
    expect(window).not.toHaveLength(1);
  });

  it("keeps the `days - 1` bucket convention over DAY keys", () => {
    const daily = chartPoints(DAILY_ONLY);
    // 1W over day keys is seven day-stamps, not eight. Unchanged by #4173.
    expect(pointsInTimeframe(daily, "1W")).toHaveLength(7);
    expect(pointsInTimeframe(daily, "1D")).toHaveLength(1);
  });
});

describe("#4173 — the axis may not tick finer than the domain it labels", () => {
  it("gives a day-keyed board its daily ticks, whatever the span", () => {
    // `axisStepDays`' floor DEFAULTS to a day, which is the compatibility
    // promise: every rung below one is unreachable unless a caller asks.
    expect(axisStepDays(3)).toBe(1);
    expect(axisStepDays(30)).toBe(7);
    expect(axisStepDays(5)).toBe(1);

    const geometry = chartGeometry(chartSeries([DAILY_ONLY]), "ALL", WIDTH, HEIGHT);
    for (const tick of axisTicks(geometry, "ALL", "UTC")) {
      expect(isDayKey(tick.at)).toBe(true);
      // THE BAN: a board with 20 readings must not sprout labels naming times
      // nothing was read at.
      expect(tick.label).not.toMatch(/AM|PM/);
    }
  });

  it("gives an instant-keyed board sub-day ticks when the window is narrow", () => {
    expect(axisStepDays(3, HOUR_DAYS)).toBe(6 / 24);
    expect(axisStepDays(0.5, HOUR_DAYS)).toBe(1 / 24);
    // A wide window keeps its calendar step even over instants.
    expect(axisStepDays(30, HOUR_DAYS)).toBe(7);

    const geometry = chartGeometry(chartSeries([MINIMAL]), "1D", WIDTH, HEIGHT);
    const ticks = axisTicks(geometry, "1D", "UTC");
    expect(ticks.length).toBeGreaterThanOrEqual(2);
    expect(ticks.some((tick) => /AM|PM/.test(tick.label))).toBe(true);
    // Every tick inside the plot it labels, and the newest on the right edge.
    for (const tick of ticks) {
      expect(tick.x).toBeGreaterThanOrEqual(0);
      expect(tick.x).toBeLessThanOrEqual(WIDTH);
    }
    expect(ticks[ticks.length - 1].x).toBe(WIDTH);
  });

  it("names the DAY at a day boundary, so two midnights are distinguishable", () => {
    // An hours-only axis over three days reads `12 AM · 6 AM · 12 PM · 6 PM ·
    // 12 AM …` and a reader cannot tell the Tuesday midnight from the Thursday.
    expect(axisTickLabel("2026-09-09T00:00:00Z", 6 / 24, "UTC")).toBe("9 Sep");
    expect(axisTickLabel("2026-09-09T17:00:00Z", 6 / 24, "UTC")).toBe("5 PM");
    // A daily-or-coarser step always names the day, whatever the instant is.
    expect(axisTickLabel("2026-09-09T17:00:00Z", 1, "UTC")).toBe("9 Sep");
    expect(axisTickLabel("2026-09-09", 7, "UTC")).toBe("9 Sep");
  });

  it("labels an instant in the READER's clock, not in UTC (UX-P260)", () => {
    // The same moment, two readers. 17:00Z is 10 AM in Los Angeles, and a tick
    // telling a Californian their price moved at 5 PM is the chart lying about
    // when — the exact error #2624 was filed for.
    expect(axisTickLabel("2026-09-09T17:00:00Z", 6 / 24, "UTC")).toBe("5 PM");
    expect(
      axisTickLabel("2026-09-09T17:00:00Z", 6 / 24, "America/Los_Angeles")
    ).toBe("10 AM");

    // And the reader's own MIDNIGHT names the reader's own DAY, which is not
    // always the UTC key's day. This is the case that discriminates: 8 Sep
    // 15:00Z is midnight in Tokyo on the NINTH, so a label built from
    // `key.slice(0, 10)` would print `8 Sep` under a tick standing at the start
    // of the 9th.
    expect(axisTickLabel("2026-09-08T15:00:00Z", 6 / 24, "Asia/Tokyo")).toBe(
      "9 Sep"
    );
    expect(axisTickLabel("2026-09-08T15:00:00Z", 6 / 24, "UTC")).toBe("3 PM");

    // Los Angeles is behind UTC, so its midnight shares the UTC day — and an
    // instant four hours into the UTC 9th is still the evening of the 8th
    // there, which is an hour label and not a day one.
    expect(
      axisTickLabel("2026-09-09T07:00:00Z", 6 / 24, "America/Los_Angeles")
    ).toBe("9 Sep");
    expect(
      axisTickLabel("2026-09-09T04:00:00Z", 6 / 24, "America/Los_Angeles")
    ).toBe("9 PM");
  });
});

describe("#4173 — a window under a day has a length a day count cannot state", () => {
  it("says `18h shown`, never `0d shown`", () => {
    const geometry = chartGeometry(
      chartSeries([row({ trend: [], trend_hourly: hours("2026-09-09T00:00:00Z", 19) })]),
      "ALL",
      WIDTH,
      HEIGHT
    );
    const span = axisSpan(geometry);
    expect(span?.short).toBe("18h");
    expect(span?.spoken).toBe("18 hours");
    // THE BAN: `axisSpanDays` rounds, and rounding 18 hours to days is what put
    // a footer on the page contradicting the line above it.
    expect(span?.short).not.toBe("0d");
    expect(html([row({ trend: [], trend_hourly: hours("2026-09-09T00:00:00Z", 19) })]))
      .toContain("18h shown");
  });

  it("still says `Nd shown` for a window of days", () => {
    const geometry = chartGeometry(chartSeries([DAILY_ONLY]), "ALL", WIDTH, HEIGHT);
    expect(axisSpan(geometry)?.short).toBe("19d");
    expect(axisSpan(geometry)?.spoken).toBe("19 days");
  });
});

describe("#4173 — a payload without the fine series draws exactly what it drew before", () => {
  it("falls back to `trend`, and the two renders agree everywhere else", () => {
    expect(chartPoints(DAILY_ONLY).every((point) => isDayKey(point.at))).toBe(true);
    expect(chartPoints(DAILY_ONLY)).toHaveLength(20);

    // An EMPTY fine series is the same case as an absent one — a backend that
    // loaded no series (the `rest`-only build) serves `[]`, not `undefined`.
    expect(chartPoints(row({ trend_hourly: [] }))).toEqual(
      chartPoints(DAILY_ONLY)
    );

    const markup = html([DAILY_ONLY]);
    expect(markup).toContain('data-testid="chart-axis-label"');
    expect(markup).toContain("19d shown");
  });
});
