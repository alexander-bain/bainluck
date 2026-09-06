/**
 * ITEM 6 (the chart's x-axis) and ITEM 9 (decided-match scores) — UX-P139.
 *
 * Both are "the page was missing an orientation the reader needs", and both are
 * asserted against the RENDER rather than against the pure layer, because a
 * library test stays green the day the component stops printing the feature
 * (`reference_plant_must_hit_the_render`).
 */

import React from "react";
import { renderToStaticMarkup } from "react-dom/server";

import ContenderChart from "@/components/tournament/ContenderChart";
import TournamentResults from "@/components/tournament/TournamentResults";
import {
  AXIS_LABEL_BLEED_PX,
  AXIS_LABEL_MAX_PX,
  AXIS_LABEL_NUDGE_PX,
  TIER_PLOT_PX,
  axisSpanDays,
  axisStepDays,
  axisTickStrides,
  axisTicks,
  axisWindow,
  chartGeometry,
  chartSeriesFor,
  seriesPoints,
  shortDateLabel,
  type AxisTick,
  type ChartGeometry,
} from "@/lib/contenderChart";
import {
  DRAW_ORDER,
  drawIsPriced,
  formatPrematch,
  prematchCoverage,
  prematchPercents,
  resultScoreLine,
  resultSentence,
  resultsEmptyReason,
  resultsForDraw,
  resultsImageCoverage,
  roundHeading,
  sortedResults,
  type TournamentResult,
  type TournamentResults as ResultsModel,
} from "@/lib/tournamentResults";
import type { TournamentRow } from "@/lib/tournament";

// ---------------------------------------------------------------------------
// ITEM 6 — "The chart needs x-axis orientation — dates/ticks"
// ---------------------------------------------------------------------------

function row(overrides: Partial<TournamentRow> = {}): TournamentRow {
  return {
    entity_key: "carlos-alcaraz",
    display_name: "Carlos Alcaraz",
    seed: 1,
    country: null,
    rank: 1,
    state: "live",
    probability: 0.26,
    probability_is_live: true,
    observed_at: "2026-08-27T00:00:00+00:00",
    age_hours: 0.2,
    price_state: "live",
    freshest_observed_at: "2026-08-27T00:00:00+00:00",
    freshest_age_hours: 0.2,
    stale_sources: [],
    mixed_freshness: false,
    source_count: 2,
    sources: [],
    blend_rule: "equal_weight_midpoint",
    divergent: false,
    trend: [
      { date: "2026-07-28", probability: 0.19 },
      { date: "2026-08-11", probability: 0.22 },
      { date: "2026-08-20", probability: 0.24 },
      { date: "2026-08-26", probability: 0.26 },
    ],
    trend_delta: 0.07,
    ...overrides,
  };
}

/**
 * The OPENING TAG of the `n`th element carrying `data-testid`, attributes and
 * all — the sibling of `innerHtmlOf` below, for guards that are about a cell's
 * own classes rather than its contents (live/071). Windowing the raw string
 * around the testid instead is how a class assertion silently starts reading
 * the neighbouring cell's `className`.
 */
function openTagOf(html: string, testid: string, nth = 0): string {
  const marker = `data-testid="${testid}"`;
  let from = -1;
  for (let i = 0; i <= nth; i += 1) from = html.indexOf(marker, from + 1);
  if (from < 0) throw new Error(`no ${testid}[${nth}] in the markup`);
  const open = html.lastIndexOf("<", from);
  const close = html.indexOf(">", from);
  return html.slice(open, close + 1);
}

/**
 * The inner HTML of the `n`th element carrying `data-testid`, found by walking
 * the tag depth from its opening tag to the matching close.
 *
 * 🔴 THIS EXISTS BECAUSE THE GUARD BELOW WAS VACUOUS AND **CERT-512 BLOCKED
 * ON IT**. The version it replaces compared two string positions —
 * `html.indexOf('result-player') < html.indexOf('player-avatar')` — and the
 * cert's plant re-emitted every avatar just AFTER its name cell closed, which
 * is exactly the fourth-grid-child regression the guard is named for. The
 * avatar was still later in the string than the first cell, so the whole
 * focused file stayed **GREEN at 52/52**.
 *
 * "Appears after" is not "is inside" — the same class as
 * `reference_containment_check_cannot_see_early_exit`. Containment needs the
 * element's own extent, so this walks it. `renderToStaticMarkup` emits
 * well-formed markup, and every container in this subtree is a `span`, `div`
 * or `li`, so a depth counter over the opening tag's own name is exact; `img`
 * is self-closing and never opens depth.
 *
 * Reproduced on `827c5bd9`'s own checked-out bytes and re-run against this
 * guard: `artifacts-ux-p207/battery-cert512-out.txt`.
 */
function innerHtmlOf(html: string, testid: string, nth = 0): string {
  const marker = `data-testid="${testid}"`;
  let from = -1;
  for (let i = 0; i <= nth; i += 1) from = html.indexOf(marker, from + 1);
  if (from < 0) throw new Error(`no ${testid}[${nth}] in the markup`);
  const open = html.lastIndexOf("<", from);
  const tag = /^<(\w+)/.exec(html.slice(open, open + 12))?.[1];
  if (!tag) throw new Error(`could not read the tag of ${testid}[${nth}]`);
  const start = html.indexOf(">", from) + 1;
  let depth = 1;
  let at = start;
  while (depth > 0) {
    const nextOpen = html.indexOf(`<${tag}`, at);
    const nextClose = html.indexOf(`</${tag}>`, at);
    if (nextClose < 0) throw new Error(`unbalanced <${tag}> in the markup`);
    if (nextOpen >= 0 && nextOpen < nextClose) {
      depth += 1;
      at = nextOpen + 1;
    } else {
      depth -= 1;
      if (depth === 0) return html.slice(start, nextClose);
      at = nextClose + 1;
    }
  }
  return "";
}

describe("item 6 — the chart's x-axis", () => {
  const rows = [
    row(),
    row({ entity_key: "alexander-zverev", display_name: "Alexander Zverev", rank: 2,
      probability: 0.21 }),
  ];
  const selection = rows.map((r) => r.entity_key);
  const geometry = chartGeometry(chartSeriesFor(rows, selection), "ALL", 320, 96);

  /* ═══ UX-P207: THE AXIS IS A CALENDAR GRID, NOT A SAMPLE OF THE DATA ═══
   *
   * Alex, on the live page on opening day: "The x-axis in the chart is weird."
   *
   * Every contract in this block up to UX-P147 rested on one rule — an axis
   * tick must label a day something was actually read — and that rule is what
   * bent the axis. Candidates were SNAPPED to the nearest observation, so on a
   * board with a fifteen-day hole every candidate inside the hole snapped back
   * onto a tick already placed and was dropped. The surviving labels clustered
   * where the readings were dense. The tests that asserted the snapping
   * ("always bounds the window with its two real ends", "places ticks by the
   * CALENDAR, not by position in the list", "the interior ticks are calendar
   * positions") are REPLACED, not deleted: everything they were protecting —
   * one scale for the line and the ticks, no repeated dates, no invented
   * scale — is asserted below, on a rule that also survives a hole.
   */

  /** Every whole day from `from` to `to`, inclusive — a dense daily domain. */
  function dailyDates(from: string, days: number): string[] {
    const base = Math.round(Date.parse(`${from}T00:00:00Z`) / 86_400_000);
    return Array.from({ length: days }, (_unused, i) =>
      new Date((base + i) * 86_400_000).toISOString().slice(0, 10)
    );
  }

  /**
   * THE PRODUCTION MEN'S BOARD, 2026-08-31 — the payload Alex was looking at.
   * Sixteen observed dates: 1–10 Aug daily, then a FIFTEEN-DAY HOLE, then
   * 26–31 Aug. The hole is the whole reason this queue exists.
   */
  const PRODUCTION_MENS_DATES = [...dailyDates("2026-08-01", 10), ...dailyDates("2026-08-26", 6)];

  const atTier = (ticks: AxisTick[], tiers: string[]) =>
    ticks.filter((tick) => tiers.includes(tick.tier));
  const PHONE = ["major"];
  const LG = ["major", "wide"];
  const XXL = ["major", "wide", "fine"];
  /**
   * The three plot widths the tiers are spent at — MEASURED, and owned here.
   *
   * These are deliberately written out rather than imported from
   * `TIER_PLOT_PX`, and then checked against it below. A guard that reads
   * production's constant and asserts something about it agrees by
   * construction: the old `major: 358` was wrong by 17% and every assertion in
   * this file cleared "≥44px at 358px" for years while `30 Aug` and `31 Aug`
   * overprinted on the live page. The number has to come from somewhere other
   * than the code under test, and where it comes from is a ruler on a
   * production screenshot — the card's own border columns at DPR 2, less the
   * 1px borders and the `px-3.5` padding, cross-checked against the rendered
   * tick pitch in the same shot:
   *
   *   390px  → artifacts-live-073/usopen-womens.png → ~305px
   *   1024px → artifacts-live-074/usopen-lg.png     → ~486px
   *   1600px → artifacts-live-074/usopen-2xl.png    → ~817px
   */
  const PLOT_PX: Record<string, number> = { major: 305, wide: 486, fine: 817 };

  it("believes the plot is as wide as production actually draws it", () => {
    // The bug under #3520 was ONE WRONG NUMBER; this is the line that would
    // have caught it. Re-measure (see `PLOT_PX`) before touching either side.
    expect(TIER_PLOT_PX).toEqual(PLOT_PX);
    // And the pieces the pitch budget is built out of, so a change to any of
    // them has to be a deliberate one.
    expect(AXIS_LABEL_MAX_PX).toBe(32);
    expect(AXIS_LABEL_BLEED_PX).toBe(12);
    expect(AXIS_LABEL_NUDGE_PX).toBe(AXIS_LABEL_MAX_PX / 2 - AXIS_LABEL_BLEED_PX);
  });

  /**
   * A plot geometry for the x-axis assertions below.
   *
   * `ceiling` is the y-axis top (#2451) and none of these cases read it, so it
   * is pinned at `1` — the fixed 0–100 axis this file was written against —
   * which keeps every x assertion measuring exactly what it measured before
   * the ceiling existed.
   */
  const geo = (dates: string[]): ChartGeometry => ({
    dates,
    width: 320,
    height: 96,
    ceiling: 1,
  });

  /** The gaps between consecutive ticks, in viewBox units, rounded to kill float noise. */
  const gapsOf = (ticks: AxisTick[]) =>
    ticks.slice(1).map((tick, i) => Number((tick.x - ticks[i].x).toFixed(6)));

  it("PROOF ON THE PAYLOAD ALEX READ: the ticks he filed, and the ticks now", () => {
    // He filed: "1 Aug, 6 Aug, 10 Aug, then a gap to 26 Aug, 30 Aug". That is
    // the `lg` row of the shipped axis on this exact domain, reproduced in
    // `artifacts-ux-p207/axis-before.txt`: five labels at 0 / 16.7 / 30.0 /
    // 83.3 / 100 percent — gaps of 16.7, 13.3, 53.3 and 16.7. Four labels
    // crammed into the first third and half the axis empty.
    const ticks = axisTicks(geo(PRODUCTION_MENS_DATES));

    // AFTER: one weekly step, anchored on the latest reading.
    expect(ticks.map((tick) => tick.label)).toEqual([
      "3 Aug", "10 Aug", "17 Aug", "24 Aug", "31 Aug",
    ]);
    // Evenly spaced — the ship, stated as arithmetic. Every gap is 7 of 30 days.
    expect(new Set(gapsOf(ticks)).size).toBe(1);
    expect(gapsOf(ticks)[0]).toBeCloseTo((7 * 320) / 30, 6);

    // The old axis is gone, not merely rearranged: the two labels that only
    // existed because the readings were dense there are not on the axis.
    expect(ticks.map((tick) => tick.label)).not.toContain("6 Aug");
    expect(ticks.map((tick) => tick.label)).not.toContain("26 Aug");
  });

  it("labels days NOTHING WAS READ, which is what makes the hole measurable", () => {
    // The rule this reverses is the one every earlier pass protected. It has to
    // go: 17 Aug and 24 Aug are inside the fifteen-day hole and no reading
    // exists on either, and they are exactly the two labels that let a reader
    // see the hole is a fortnight rather than "some unlabelled distance".
    const ticks = axisTicks(geo(PRODUCTION_MENS_DATES));
    const unobserved = ticks.filter((tick) => !PRODUCTION_MENS_DATES.includes(tick.date));
    expect(unobserved.map((tick) => tick.label)).toEqual(["17 Aug", "24 Aug"]);

    // And the LINE still has nothing in the hole — "gaps stay gaps" is about
    // the data, and no tick invents a reading.
    const holed = [row({ trend: PRODUCTION_MENS_DATES.map((date) => ({ date, probability: 0.4 })) })];
    const drawn = seriesPoints(
      chartSeriesFor(holed, [holed[0].entity_key])[0],
      geo(PRODUCTION_MENS_DATES),
      "ALL"
    );
    const xs = drawn.split(" ").map((pair) => Number(pair.split(",")[0]));
    const holeStart = ((9 - 0) * 320) / 30; // 10 Aug
    const holeEnd = ((25 - 0) * 320) / 30; // 26 Aug
    expect(xs.some((x) => x > holeStart + 0.01 && x < holeEnd - 0.01)).toBe(false);
  });

  it("takes its step from the CALENDAR, and from the drawn window not the button", () => {
    // The directive's ask, and the reason it cannot be a table keyed on the
    // timeframe button: `ALL` on the women's board is five days.
    expect(axisStepDays(30)).toBe(7); // a month  -> weekly
    expect(axisStepDays(5)).toBe(1); //  the women's ALL -> daily
    expect(axisStepDays(6)).toBe(1); //  a week   -> daily
    expect(axisStepDays(90)).toBe(14);
    expect(axisStepDays(365)).toBe(91);
    // Only steps a reader can count in their head — never 3, 4, 5 or 6 days.
    for (let span = 1; span <= 800; span += 1) {
      expect([1, 2, 7, 14, 28, 91, 182, 364]).toContain(axisStepDays(span));
      expect(span / axisStepDays(span)).toBeLessThanOrEqual(12);
    }
  });

  it("is evenly spaced at EVERY width, over every window length — bar the one gap the pin buys", () => {
    // The defect was irregular spacing, so the guard is regular spacing — and
    // it has to hold per TIER, because a tier is what a given screen sees. An
    // axis that is even at `2xl` and ragged on a phone is the women's board
    // before this change (40% / 20% / 40%).
    //
    // #3520 CARVES OUT EXACTLY ONE EXCEPTION AND THIS GUARD PINS ITS SHAPE. The
    // oldest tick is promoted so the axis's left edge always carries a label
    // (otherwise the axis reads `31 Aug … 6 Sep` while the footer says `7d
    // shown`), and its too-close neighbour is demoted to pay for it. That makes
    // the LEFTMOST gap `(K mod S) + S` steps where every other gap is `S`. So:
    // at most two distinct gaps, the odd one out is the first, and it is
    // strictly between one and two of the others. Anything else — a ragged
    // interior, a doubled gap, three distinct widths — still fails.
    const seen = { even: 0, pinned: 0 };
    for (const span of [1, 2, 3, 5, 6, 7, 10, 12, 13, 20, 24, 30, 45, 60, 90, 120, 200, 400, 900]) {
      const dates = dailyDates("2024-01-01", span + 1);
      const ticks = axisTicks(geo(dates));
      for (const [name, tiers] of [["phone", PHONE], ["lg", LG], ["2xl", XXL]] as const) {
        const visible = atTier(ticks, tiers as string[]);
        expect(visible.length).toBeGreaterThanOrEqual(2);
        const gaps = gapsOf(visible);
        const where = `${span}d ${name}`;
        const interior = new Set(gaps.slice(1));
        if (interior.size === 0 || new Set(gaps).size === 1) {
          seen.even += 1;
          continue;
        }
        seen.pinned += 1;
        // The interior is still perfectly regular …
        expect(`${where}: ${[...interior]}`).toBe(`${where}: ${[...interior].slice(0, 1)}`);
        // … and the leftmost gap is wider, but by less than a whole extra gap.
        const [unit] = [...interior];
        expect(`${where}: ${gaps[0] > unit}`).toBe(`${where}: true`);
        expect(`${where}: ${gaps[0] < unit * 2}`).toBe(`${where}: true`);
      }
    }
    // Neither branch may go unvisited: an all-even sweep would mean the pin
    // never fires and the exception above is untested prose, and an all-pinned
    // one would mean the even-spacing rule it is an exception TO has stopped
    // being asserted anywhere.
    expect(seen.even).toBeGreaterThan(0);
    expect(seen.pinned).toBeGreaterThan(0);
  });

  it("labels the oldest drawn tick at every width, so the axis agrees with `Nd shown`", () => {
    // THE SHIP OF #3520's SECOND HALF. On the US Open's 7-day window the phone
    // stride is 2 over 7 intervals, so a stride anchored on the newest reading
    // labels 6/4/2 Sep and 31 Aug and leaves the leftmost tick — 30 Aug, the
    // day the window starts — silent. The footer next to it says `7d shown`. A
    // reader who counts the axis gets six, and the chart is arguing with itself.
    for (const span of [5, 7, 9, 10, 11, 12, 13, 20, 30, 45, 90, 200]) {
      const dates = dailyDates("2024-03-01", span + 1);
      const ticks = axisTicks(geo(dates));
      const phone = atTier(ticks, PHONE);
      // Both ends of the DRAWN axis carry a label on the narrowest screen.
      // `ticks` is oldest-first (`axisTicks` reverses on the way out).
      expect(`${span}d oldest: ${phone[0]?.date}`).toBe(`${span}d oldest: ${ticks[0].date}`);
      expect(`${span}d newest: ${phone[phone.length - 1]?.date}`).toBe(
        `${span}d newest: ${ticks[ticks.length - 1].date}`
      );
    }
  });

  it("never buys the oldest label with the newest one", () => {
    // The module's older rule — the latest reading is where the endpoint dot is
    // and must always be labelled — outranks the pin. `pinOldestLabel` refuses
    // rather than demote `k = 0`, and this is that refusal asserted on the only
    // shape that can reach it: two ticks, needing a stride of two.
    for (const span of [1, 2, 3, 5, 6, 7, 10, 30, 200, 900]) {
      const dates = dailyDates("2024-06-01", span + 1);
      const ticks = axisTicks(geo(dates));
      const newest = ticks[ticks.length - 1];
      expect(`${span}d newest tier: ${newest.tier}`).toBe(`${span}d newest tier: major`);
      expect(newest.x).toBe(320);
    }
  });

  it("anchors the grid on the LATEST reading, which is where the eye starts", () => {
    // The endpoint dot is at the right edge and is the number the reader came
    // for, so the right edge always carries a label. The left edge may not —
    // the leftmost tick can sit up to one step in, which is what a time axis
    // looks like and is not what was filed.
    for (const span of [5, 12, 29, 30, 45, 200]) {
      const dates = dailyDates("2024-03-01", span + 1);
      const ticks = axisTicks(geo(dates));
      expect(ticks[ticks.length - 1].x).toBe(320);
      expect(ticks[ticks.length - 1].date).toBe(dates[dates.length - 1]);
      expect(ticks[0].x).toBeGreaterThanOrEqual(0);
      expect(ticks[0].x).toBeLessThan((axisStepDays(span) * 320) / span);
    }
  });

  it("nests the strides, so no tier's own labels can come out ragged", () => {
    /* The set a screen shows is a UNION of two arithmetic progressions, and a
     * union of strides 3 and 2 is not a progression at all — it reads 0, 2, 3,
     * 4, 6, 8, 9. That is the defect this queue removes, reached from the other
     * side, so the rounding that prevents it is asserted here.
     *
     * ⚠️ ASSERTED THROUGH THE EXPORTED HELPER ON PURPOSE. At `MAX_INTERVALS =
     * 12` no window can drive the strides apart, so a guard written against
     * `axisTicks` would pass on every input and prove nothing — the battery's
     * P5 plant (drop the rounding) came back GREEN through that route and this
     * test is what it caught. The pitch fractions below are BELOW anything the
     * ladder can produce; they exist to exercise the arithmetic the day the
     * ladder changes.
     */
    for (const fraction of [1 / 12, 1 / 15, 1 / 18, 1 / 24, 1 / 30, 1 / 40, 1 / 60]) {
      const { major, wide, fine } = axisTickStrides(fraction);
      expect(major % wide).toBe(0);
      expect(wide % fine).toBe(0);
      expect(major).toBeGreaterThanOrEqual(wide);
      expect(wide).toBeGreaterThanOrEqual(fine);
      // …and each tier's own pitch clears 44px at the width it first appears.
      for (const [stride, px] of [[major, PLOT_PX.major], [wide, PLOT_PX.wide], [fine, PLOT_PX.fine]] as const) {
        expect(stride * fraction * px).toBeGreaterThanOrEqual(44);
      }
    }
    // The one the ladder actually reaches, spelled out: a 1/18 window wants
    // stride 3 on a phone and 2 at `lg`, and 3 is rounded to 4 so the union
    // stays a progression.
    expect(axisTickStrides(1 / 18)).toEqual({ major: 4, wide: 2, fine: 1 });
  });

  it("gets denser as the window widens, and a narrow axis is a SUBSET of a wide one", () => {
    // The property that makes widening the window feel like zooming in rather
    // than like a different chart: every label a phone shows is still there, at
    // the same position, when the desktop adds more between them.
    for (const span of [10, 12, 20, 24, 60, 120, 900]) {
      const ticks = axisTicks(geo(dailyDates("2024-05-01", span + 1)));
      const phone = atTier(ticks, PHONE);
      const lg = atTier(ticks, LG);
      for (const tick of phone) expect(lg).toContainEqual(tick);
      for (const tick of lg) expect(ticks).toContainEqual(tick);
      expect(phone.length).toBeLessThanOrEqual(lg.length);
      expect(lg.length).toBeLessThanOrEqual(ticks.length);
    }
  });

  it("never draws two labels closer than they can be read at their own width", () => {
    // 44px centre to centre: a `26 Aug` label is ~30px at `text-[9.5px]` in
    // tabular figures, plus 14px of air.
    for (const span of [1, 5, 7, 10, 12, 13, 24, 30, 45, 60, 90, 200, 400, 900]) {
      const ticks = axisTicks(geo(dailyDates("2024-07-01", span + 1)));
      for (const [tiers, px] of [[PHONE, PLOT_PX.major], [LG, PLOT_PX.wide], [XXL, PLOT_PX.fine]] as const) {
        const visible = atTier(ticks, tiers as string[]);
        for (let i = 1; i < visible.length; i += 1) {
          const apart = ((visible[i].x - visible[i - 1].x) / 320) * (px as number);
          expect(apart).toBeGreaterThanOrEqual(44);
        }
      }
      // …and the same, stated the way the render will actually see it: two
      // labels only ever share a screen from the FINER tier's width up.
      for (let i = 0; i < ticks.length; i += 1) {
        for (let j = i + 1; j < ticks.length; j += 1) {
          const px = Math.max(PLOT_PX[ticks[i].tier], PLOT_PX[ticks[j].tier]);
          expect((Math.abs(ticks[i].x - ticks[j].x) / 320) * px).toBeGreaterThanOrEqual(44);
        }
      }
    }
  });

  it("never repeats a date and never leaves the drawn window", () => {
    for (const span of [1, 2, 5, 12, 30, 91, 400]) {
      const dates = dailyDates("2025-02-01", span + 1);
      const ticks = axisTicks(geo(dates));
      expect(new Set(ticks.map((t) => t.date)).size).toBe(ticks.length);
      for (const tick of ticks) {
        expect(tick.date >= dates[0]).toBe(true);
        expect(tick.date <= dates[dates.length - 1]).toBe(true);
        expect(tick.x).toBeGreaterThanOrEqual(0);
        expect(tick.x).toBeLessThanOrEqual(320);
      }
    }
  });

  it("the LINE uses the same scale as the ticks — they cannot disagree", () => {
    // The failure this exists to stop is the one the pre-UX-P146 design
    // accepted knowingly: a tick placed by one rule and a point placed by
    // another, so the label sits where the line is not. A tick's x must be the
    // x the line WOULD have at that date, whether or not a reading exists.
    const ticks = axisTicks(geometry);
    const day = (iso: string) => Date.parse(`${iso}T00:00:00Z`) / 86_400_000;
    const first = day(geometry.dates[0]);
    const last = day(geometry.dates[geometry.dates.length - 1]);
    for (const tick of ticks) {
      expect(tick.x).toBeCloseTo(((day(tick.date) - first) * 320) / (last - first), 5);
    }
    // And where a reading DOES exist on a tick's date, the drawn point lands on
    // the rule: 26 Aug is both the last observation and the last tick.
    const drawn = seriesPoints(chartSeriesFor(rows, selection)[0], geometry, "ALL");
    const xs = drawn.split(" ").map((pair) => Number(pair.split(",")[0]));
    expect(ticks[ticks.length - 1].date).toBe("2026-08-26");
    expect(xs[xs.length - 1]).toBeCloseTo(ticks[ticks.length - 1].x, 5);
  });

  it("offers no ticks for a domain that cannot be drawn", () => {
    expect(axisTicks(geo([]))).toEqual([]);
    expect(axisTicks(geo(["2026-08-26"]))).toEqual([]);
    // A domain of two entries on the SAME day has no width to divide.
    expect(axisTicks(geo(["2026-08-26", "2026-08-26"]))).toEqual([]);
  });

  it("labels a date day-first, because the month repeats and the day does not", () => {
    expect(shortDateLabel("2026-08-26")).toBe("26 Aug");
    expect(shortDateLabel("2026-01-02")).toBe("2 Jan");
    expect(shortDateLabel("nonsense")).toBe("nonsense");
  });

  it("states how long the drawn window IS, which the buttons cannot", () => {
    // `ALL` on a field with four readings is four days, and the timeframe
    // button says `ALL` either way.
    expect(axisSpanDays(geometry)).toBe(29);
    expect(axisSpanDays(geo(["2026-08-26"]))).toBeNull();
  });

  it("names the window from the DOMAIN, not from the ticks", () => {
    // UX-P207. The ticks no longer sit on the domain's ends, so reading the
    // window off them would have told a screen reader "29 Jul to 26 Aug" while
    // the footer beside it said "29d shown" — the same disagreement this queue
    // is removing, in two modalities.
    expect(axisWindow(geometry)).toEqual({ from: "28 Jul", to: "26 Aug" });
    expect(axisWindow(geo(["2026-08-26"]))).toBeNull();
    const ticks = axisTicks(geometry);
    expect(ticks[0].label).not.toBe("28 Jul");
  });

  it("RENDERS the ticks and their labels", () => {
    const html = renderToStaticMarkup(
      <ContenderChart rows={rows} draw="mens-singles" selection={selection} onToggle={() => {}} />
    );
    expect(html).toContain('data-testid="chart-axis"');
    // 28 Jul → 26 Aug is 29 days, so a weekly step: 29 Jul, 5, 12, 19, 26 Aug.
    expect((html.match(/data-testid="chart-axis-tick"/g) ?? []).length).toBe(5);
    expect((html.match(/data-testid="chart-axis-label"/g) ?? []).length).toBe(5);
    for (const label of ["29 Jul", "5 Aug", "12 Aug", "19 Aug", "26 Aug"]) {
      expect(html).toContain(`>${label}</span>`);
    }
    expect(html).toContain('data-testid="chart-span"');
    expect(html).toContain("29d shown");
  });

  it("spends the tier at the breakpoint — one render, three densities", () => {
    // UX-P147's rule, unchanged and still load-bearing: a `wide` or `fine` tick
    // is HIDDEN below its breakpoint rather than absent from the markup. The
    // chart is server-rendered once, so the density has to come from CSS or it
    // cannot come at all.
    //
    // TWO fixtures, because one cannot show both breakpoints. A 12-day window
    // thins on the phone only (`major` 2, `wide` 2, `fine` 1 → `2xl:`); a
    // 10-day window thins on the phone and `lg` agrees with `2xl` (`major` 2,
    // `wide` 1 → `lg:`). Asserting both is what proves each CSS string is
    // reachable rather than decorative.
    for (const [span, tier, className] of [
      [12, "fine", "hidden 2xl:block"],
      [10, "wide", "hidden lg:block"],
    ] as const) {
      const dates = dailyDates("2026-08-01", span + 1);
      const dense = [row({ trend: dates.map((date) => ({ date, probability: 0.4 })) })];
      const html = renderToStaticMarkup(
        <ContenderChart
          rows={dense}
          draw="mens-singles"
          selection={dense.map((r) => r.entity_key)}
          onToggle={() => {}}
        />
      );
      expect(html).toContain('data-tier="major"');
      expect(html).toContain(`data-tier="${tier}"`);
      for (const match of html.matchAll(/<span class="([^"]*)"[^>]*data-tier="(\w+)"/g)) {
        const [, classNames, rendered] = match;
        if (rendered === "major") expect(classNames).not.toContain("hidden");
        else expect(classNames).toContain(className);
      }
    }
  });

  it("centres every label on its own rule, nudging the ends by POSITION and not by index", () => {
    // The leftmost tick is no longer AT the left edge, so an `index === 0` rule
    // would nudge a label that has no need of it. 29 Jul sits at 1 of 29 days —
    // inside the margin the bleed cannot cover — while 5 Aug is interior.
    //
    // #3520 CHANGED WHAT THE ENDS DO, NOT WHEN THEY DO IT. They used to be hard
    // left- and right-ALIGNED, a half-label shove that drove `30 Aug` into
    // `31 Aug` on production. Now every label is centred and the two ends are
    // nudged by `AXIS_LABEL_NUDGE_PX` — the sliver the strip's bleed into the
    // card padding cannot absorb. Pinning the arithmetic and not just the
    // shape: at 32px of label against 12px of bleed the nudge is 4px, and if
    // someone widens the label or narrows the bleed without re-reading
    // `LABEL_PITCH_PX` this line is what tells them.
    expect(AXIS_LABEL_NUDGE_PX).toBe(4);
    const html = renderToStaticMarkup(
      <ContenderChart rows={rows} draw="mens-singles" selection={selection} onToggle={() => {}} />
    );
    const styleFor = (label: string) => {
      const at = html.indexOf(`>${label}</span>`);
      const open = html.lastIndexOf("<span", at);
      return /style="([^"]*)"/.exec(html.slice(open, at))?.[1] ?? "";
    };
    // This window's oldest tick sits 1 of 29 days in, and 1/29 of 305px is
    // 10.5px — a 16px half-label hangs 5.5px past the rule, which the 12px
    // bleed swallows whole. So it is NOT nudged, and that is the position test
    // earning its keep: under the old half-label margin (15/358) it would have
    // been shoved, and under an index rule it would have been shoved too.
    expect(styleFor("29 Jul")).toContain("translateX(-50%)");
    expect(styleFor("29 Jul")).not.toContain("calc(-50%");
    expect(styleFor("5 Aug")).toContain("translateX(-50%)");
    expect(styleFor("12 Aug")).toContain("translateX(-50%)");
    // The newest reading IS at the right edge, always — so it always nudges.
    expect(styleFor("26 Aug")).toContain("translateX(calc(-50% + -4px))");

    // Nobody is left-aligned or right-aligned any more. Asserted as an absence
    // over the WHOLE strip, because the shove is what the bug was made of and a
    // per-label check would miss it coming back on a label this test does not
    // happen to name.
    const strip = html.slice(html.indexOf('data-testid="chart-axis"'));
    expect(strip.slice(0, strip.indexOf("</div>"))).not.toContain("translateX(-100%)");

    // A tick a whisker inside the left edge is centred with NO nudge — the
    // index rule could not tell those two apart and this one must.
    const wide = [row({ trend: dailyDates("2026-08-01", 31).map((d) => ({ date: d, probability: 0.4 })) })];
    const wideHtml = renderToStaticMarkup(
      <ContenderChart rows={wide} draw="mens-singles" selection={wide.map((r) => r.entity_key)}
        onToggle={() => {}} />
    );
    // 3 Aug is 2 of 30 days = 6.7%, outside the 1.3% margin the bleed leaves.
    const at = wideHtml.indexOf(">3 Aug</span>");
    const open = wideHtml.lastIndexOf("<span", at);
    const style = /style="([^"]*)"/.exec(wideHtml.slice(open, at))?.[1] ?? "";
    expect(style).toContain("translateX(-50%)");
    expect(style).not.toContain("calc(-50%");

    // AND THE CASE THAT FILED THE BUG: the US Open's 7-day window, where the
    // step is daily and the oldest tick lands exactly ON the left edge. Both
    // ends nudge, in opposite directions, and nothing in between does.
    const week = [row({ trend: dailyDates("2026-08-30", 8).map((d) => ({ date: d, probability: 0.4 })) })];
    const weekHtml = renderToStaticMarkup(
      <ContenderChart rows={week} draw="womens-singles" selection={week.map((r) => r.entity_key)}
        onToggle={() => {}} />
    );
    const weekStyle = (label: string) => {
      const idx = weekHtml.indexOf(`>${label}</span>`);
      const span = weekHtml.lastIndexOf("<span", idx);
      return /style="([^"]*)"/.exec(weekHtml.slice(span, idx))?.[1] ?? "";
    };
    expect(weekStyle("30 Aug")).toContain("translateX(calc(-50% + 4px))");
    expect(weekStyle("6 Sep")).toContain("translateX(calc(-50% + -4px))");
    const nudged = [...weekHtml.matchAll(/data-nudge="(-?\d+)"/g)].map((m) => m[1]);
    expect(nudged.filter((value) => value !== "0")).toEqual(["4", "-4"]);
  });

  it("labels live OUTSIDE the svg, which is non-uniformly scaled", () => {
    // `preserveAspectRatio="none"` stretches x and y independently, so SVG
    // text would be distorted. The labels are HTML positioned by the same
    // fraction of the width the tick uses.
    const html = renderToStaticMarkup(
      <ContenderChart rows={rows} draw="mens-singles" selection={selection} onToggle={() => {}} />
    );
    const svg = html.slice(html.indexOf("<svg"), html.indexOf("</svg>"));
    expect(svg).not.toContain("<text");
    expect(svg).toContain('data-testid="chart-axis-tick"');
    expect(html.indexOf('data-testid="chart-axis"')).toBeGreaterThan(html.indexOf("</svg>"));
  });

  it("says the date range in the accessible label too", () => {
    const html = renderToStaticMarkup(
      <ContenderChart rows={rows} draw="mens-singles" selection={selection} onToggle={() => {}} />
    );
    // The DOMAIN's ends, so the spoken window and the printed "29d shown"
    // describe the same thing. The first tick is 29 Jul; saying that here would
    // under-report the window by a day.
    expect(html).toContain("over 29 days, 28 Jul to 26 Aug");
  });
});

// ---------------------------------------------------------------------------
// ITEM 9 — decided matches, with the score
// ---------------------------------------------------------------------------

function result(overrides: Partial<TournamentResult> = {}): TournamentResult {
  return {
    matchup_key: "espn:184607",
    draw: "mens-singles",
    draw_label: "Men's Singles",
    round: "Qualifying 1st Round",
    players: [
      { entity_key: "jacob-fearnley", display_name: "Jacob Fearnley", seed: null,
        is_winner: true, prematch_probability: null },
      { entity_key: "roberto-carballes-baena", display_name: "Roberto Carballes Baena",
        seed: null, is_winner: false, prematch_probability: null },
    ],
    winner_entity_key: "jacob-fearnley",
    score: "7-6, 6-3",
    completed_at: "2026-08-24T15:05Z",
    source_round: "Qualifying 1st Round",
    source: "espn",
    ...overrides,
  };
}

function results(overrides: Partial<ResultsModel> = {}): ResultsModel {
  return {
    matches: [result()],
    count: 1,
    unregistered_pairs: 0,
    winner_not_registered: 0,
    source_competitions: 199,
    source_scored: 181,
    source_errors: [],
    ...overrides,
  };
}

describe("item 9 — decided matches carry their score", () => {
  it("prints the score beside the outcome, winner first", () => {
    const html = renderToStaticMarkup(
      <TournamentResults results={results()} draw="mens-singles" />
    );
    expect(html).toContain('data-testid="result-score"');
    expect(html).toContain("7-6, 6-3");
    // Winner's row comes first and is the one marked `won`.
    const winnerIndex = html.indexOf("Jacob Fearnley");
    const loserIndex = html.indexOf("Roberto Carballes Baena");
    expect(winnerIndex).toBeLessThan(loserIndex);
    expect(html).toContain('data-outcome="won"');
    expect(html).toContain('data-outcome="lost"');
  });

  it("says WHERE the score came from", () => {
    const html = renderToStaticMarkup(
      <TournamentResults results={results()} draw="mens-singles" />
    );
    expect(html).toContain('data-testid="results-provenance"');
    expect(html).toContain("Scores from ESPN");
  });

  /* ═══ UX-P147, ALEX'S ITEM 5: THE ROW THAT SAID "no score" ═══
   *
   * He pointed at the Dimitrov qualifying final and asked for the root cause.
   * Measured against the live ESPN scoreboard 2026-08-28T00:4xZ: competition
   * 184769 is `STATUS_WALKOVER`, note "Grigor Dimitrov (BUL) bt Otto Virtanen
   * (FIN) w/o", no `linescores` on either competitor. Not an ingest gap and
   * not a render fallback — a walkover, which we were told about and threw
   * away. The same census found the mirror defect: all 8 retirements DO carry
   * equal-length line scores, so they printed as ordinary final results.
   */

  it("names a WALKOVER, instead of shrugging at its own missing data", () => {
    const html = renderToStaticMarkup(
      <TournamentResults
        results={results({
          matches: [result({ score: null, completion: "walkover" })],
        })}
        draw="mens-singles"
      />
    );
    expect(html).toContain('data-has-score="false"');
    expect(html).toContain('data-completion="walkover"');
    expect(html).toContain("walkover");
    // NOT the old wording, and not the old guess.
    expect(html).not.toContain("no score");
    expect(html).not.toContain("usually a retirement");
    // The outcome is still there — knowing who won is most of the value.
    expect(html).toContain("Jacob Fearnley");
    // And the section says it once more, counted, at the bottom.
    expect(html).toContain("1 was a walkover, with no set played");
  });

  it("MARKS a retirement's score instead of passing it off as a finished one", () => {
    // `4-6, 7-5, 3-1` is not a scoreline a completed tennis match can have. It
    // is true, it is most of what happened, and before UX-P147 it printed with
    // nothing at all to say the match was abandoned.
    const html = renderToStaticMarkup(
      <TournamentResults
        results={results({
          matches: [result({ score: "4-6, 7-5, 3-1", completion: "retired" })],
        })}
        draw="mens-singles"
      />
    );
    // The visible score is drawn in per-set chunks since live/071, so the
    // scoreline is asserted as the pieces it is drawn in — and the `ret.` rides
    // with the set it belongs to, which is the property that matters: a mark
    // that wraps onto a line of its own reads as a footnote about the match
    // rather than as "this set was abandoned".
    expect(html).toContain('<span class="whitespace-nowrap">3-1 ret.</span>');
    expect(html).toContain("4-6, 7-5, 3-1, when the loser retired");
    expect(html).toContain('data-score-kind="retired"');
    expect(html).toContain("1 ended in a retirement");
  });

  it("still refuses to guess when the source gives neither a score nor a reason", () => {
    const html = renderToStaticMarkup(
      <TournamentResults results={results({ matches: [result({ score: null })] })} draw="mens-singles" />
    );
    expect(html).toContain('data-testid="result-no-score"');
    expect(html).toContain("no score");
    // The old tooltip asserted "usually a retirement". A guess is worse than a
    // gap, because it reads more authoritative than one.
    expect(html).toContain("did not say why");
    expect(html).not.toContain("usually a retirement");
  });

  it("says nothing about completions when every match ran its course", () => {
    const html = renderToStaticMarkup(
      <TournamentResults
        results={results({ matches: [result({ completion: "final" })] })}
        draw="mens-singles"
      />
    );
    expect(html).not.toContain("results-completion-note");
    expect(html).not.toContain("walkover");
  });

  it("uses ESPN's finer round wording where the register has one bucket", () => {
    expect(roundHeading(result())).toBe("Qualifying 1st Round");
    expect(roundHeading(result({ source_round: null, round: "qualifying" }))).toBe("Qualifying");
  });

  it("orders newest first — a results list is read for what just happened", () => {
    const older = result({ matchup_key: "a", completed_at: "2026-08-24T12:00Z" });
    const newer = result({ matchup_key: "b", completed_at: "2026-08-24T18:00Z" });
    expect(sortedResults([older, newer]).map((r) => r.matchup_key)).toEqual(["b", "a"]);
  });

  it("writes the sentence a result IS, winner first, surnames only", () => {
    expect(resultSentence(result())).toBe("Fearnley beat Carballes Baena 7-6, 6-3");
    expect(resultSentence(result({ score: null }))).toBe("Fearnley beat Carballes Baena");
  });

  it("distinguishes the three empties, because they need different people", () => {
    expect(resultsEmptyReason(undefined)).toBe("Results are not loaded.");
    expect(resultsEmptyReason(results({ matches: [], source_errors: ["timeout"] })))
      .toContain("could not reach the results feed");
    expect(resultsEmptyReason(results({ matches: [], source_competitions: 199 })))
      .toContain("199 matches have finished");
    expect(resultsEmptyReason(results({ matches: [], source_competitions: 0 })))
      .toBe("No match has finished yet.");
    expect(resultsEmptyReason(results())).toBeNull();
  });

  /* ═══ UX-P147, ALEX'S ITEM 3: "raggedly aligned" ═══
   *
   * The two priors and the score have to be COLUMNS. They were not, and the
   * reason looked correct in the source: a `flex justify-between` row sizes its
   * items per line, so the prior column's right edge — and with it the score
   * column's left edge — moved with the width of each row's own score string.
   * `6-3, 6-4` is 56px and `7-6 (7-4), 3-6, 6-4` is 128px, so no two rows put
   * their numbers in the same place.
   *
   * Columns that line up ACROSS rows need one grid whose tracks every row
   * shares. That is a structural property, so this asserts the structure: one
   * grid on the list, `display: contents` rows, three tracks, and a score that
   * spans both player lines. A screenshot could not prove this and a pixel
   * assertion in jsdom would prove nothing at all — jsdom does not lay out.
   */

  it("draws the priors and the score as real columns, shared by every row", () => {
    const varied = results({
      matches: [
        withPrior(0.735, 0.265, { matchup_key: "a", score: "6-3, 6-4" }),
        withPrior(0.51, 0.49, {
          matchup_key: "b",
          score: "7-6 (7-4), 3-6, 6-4",
          completed_at: "2026-08-24T11:00Z",
        }),
      ],
      count: 2,
    });
    const html = renderToStaticMarkup(<TournamentResults results={varied} draw="mens-singles" />);

    // ONE grid, on the list, with the three tracks — not a grid per row. The
    // third track is capped on a phone and `max-content` from `sm:` up
    // (live/071); both halves are asserted below, in their own guard.
    expect(html).toContain(
      'class="grid grid-cols-[minmax(0,1fr)_max-content_fit-content(76px)] sm:grid-cols-[minmax(0,1fr)_max-content_max-content] items-center gap-x-3 lg:gap-x-4"'
    );
    // Rows are transparent to it, so their cells land in the parent's tracks.
    expect((html.match(/class="contents" data-testid="result-row"/g) ?? []).length).toBe(2);
    // The round headings are bands INSIDE the same grid. A heading outside it
    // would reset the tracks and move the next round's score column.
    expect(html).toContain('class="col-span-3 border-t');
    // The score is drawn once per match and spans both player lines, because a
    // score describes the match and not the player it sits beside.
    expect((html.match(/data-testid="result-score"/g) ?? []).length).toBe(2);
    expect((html.match(/row-span-2/g) ?? []).length).toBe(2);
    // …and the two scores that used to set two different column edges are now
    // both in the same track.
    expect(html).toContain("6-3, 6-4");
    expect(html).toContain("7-6 (7-4), 3-6, 6-4");
  });

  it("counts the coverage gap rather than letting a short list speak for it", () => {
    const html = renderToStaticMarkup(
      <TournamentResults results={results({ unregistered_pairs: 117 })} draw="mens-singles" />
    );
    expect(html).toContain("117 other finished matches");
  });

  /* ═══ live/071: THE PHONE'S NAME COLUMN, AND THE TWO THINGS THAT ATE IT ═══
   *
   * Measured on production at 390px, where the list's `ul` is 332px wide: the
   * `max-content` score track took 129.25px of it and the name track got
   * 114.16. Inside that cell the avatar and the padding cost 42px and the
   * winner's `won` badge another 33, so the winner's name span was 39px — four
   * characters — and `Stefanos Tsitsipas` printed as `Ste…`. Ten of ten names
   * on the served list were clipped, the winners' worse than the losers'.
   *
   * Neither half of the fix can be checked by rendering, because jsdom does not
   * lay out — so this asserts the two class-level properties the browser
   * measurement rests on, and each is a real revert-in-one-line failure mode:
   *
   *   1. The score track is capped BELOW `sm:` and uncapped above it. A tidy-up
   *      that collapses the pair back to one `max-content` restores the 129px
   *      column, and nothing else in the suite would notice.
   *   2. The score cell may WRAP. `fit-content(76px)` floors at min-content, so
   *      a `whitespace-nowrap` added to that cell raises its min-content to the
   *      whole score and puts the wide column straight back — with the capped
   *      track still sitting in the source looking like it works.
   *
   * The win marker is asserted the other way round: the word must survive for a
   * screen reader (`sr-only`, never `hidden`) while the phone spends 10px on a
   * tick instead of 33 on the word.
   */
  it("caps the score track on a phone and lets the score wrap into it", () => {
    const html = renderToStaticMarkup(
      <TournamentResults
        results={results({
          matches: [result({ matchup_key: "a", score: "7-6, 6-7, 6-3, 6-4" })],
        })}
        draw="mens-singles"
      />
    );
    expect(html).toContain("grid-cols-[minmax(0,1fr)_max-content_fit-content(76px)]");
    expect(html).toContain("sm:grid-cols-[minmax(0,1fr)_max-content_max-content]");

    // THE CAP'S PRECONDITION. `fit-content()` degrades to the full-width column
    // the moment the CELL cannot break, so its own opening tag is the thing to
    // read — `nowrap` on the chunks inside it is the opposite thing and is
    // asserted for, below.
    expect(openTagOf(html, "result-score")).not.toMatch(/\b(whitespace|text)-nowrap\b/);
    // The score is really in there, so the assertion above is about a cell that
    // exists rather than about an empty match. (Via the sr-only sentence: the
    // visible half is drawn in pieces.)
    expect(innerHtmlOf(html, "result-score", 0)).toContain("7-6, 6-7, 6-3, 6-4");

    // AND THE BREAK FALLS BETWEEN SETS. Measured in the capture rig before this
    // existed: the wrapped column broke `7-6, 6-` / `7, 6-3, 6-4`, because a
    // hyphen is a break opportunity and no CSS property takes it away. Each set
    // is its own `nowrap` chunk, so the only breakable thing left is the space
    // after a comma.
    const cell = innerHtmlOf(html, "result-score", 0);
    const chunks = [...cell.matchAll(/<span class="whitespace-nowrap">([^<]*)<\/span>/g)].map(
      (m) => m[1]
    );
    expect(chunks).toEqual(["7-6,", "6-7,", "6-3,", "6-4"]);
  });

  it("keeps a tiebreak with the set it belongs to when the score wraps", () => {
    // Splitting on whitespace would have been the obvious way to chunk this and
    // would put `(7-4),` on a line of its own, orphaned from the set it
    // qualifies. The comma is the boundary; the space inside a chunk is not.
    const html = renderToStaticMarkup(
      <TournamentResults
        results={results({
          matches: [result({ matchup_key: "a", score: "7-6 (7-4), 3-6, 6-4" })],
        })}
        draw="mens-singles"
      />
    );
    const chunks = [
      ...innerHtmlOf(html, "result-score", 0).matchAll(
        /<span class="whitespace-nowrap">([^<]*)<\/span>/g
      ),
    ].map((m) => m[1]);
    expect(chunks).toEqual(["7-6 (7-4),", "3-6,", "6-4"]);
  });

  it("keeps the word 'won' for a screen reader while the phone shows a tick", () => {
    const html = renderToStaticMarkup(
      <TournamentResults results={results()} draw="mens-singles" />
    );
    const marker = innerHtmlOf(html, "result-won-marker", 0);
    // The word is present and merely UNPAINTED below `sm:` — `hidden` here
    // would delete the only statement of the result an unsighted reader gets
    // from this row, which is the opposite of the ship.
    expect(marker).toContain("won");
    expect(marker).toContain("sr-only sm:not-sr-only");
    expect(marker).not.toContain('class="hidden');
    // …and the tick is decoration, so it is not read out twice.
    expect(marker).toContain('aria-hidden="true"');
    expect(marker).toContain("sm:hidden");
    // Exactly one marker per match: the loser never gets one.
    expect((html.match(/data-testid="result-won-marker"/g) ?? []).length).toBe(1);
  });
});

// ---------------------------------------------------------------------------
// ITEM 12 — the doubles section is built and waiting
// ---------------------------------------------------------------------------

describe("item 12 — doubles and mixed doubles are accepted, not special-cased", () => {
  it("knows all five draws, singles first", () => {
    expect([...DRAW_ORDER]).toEqual([
      "mens-singles", "womens-singles", "mens-doubles", "womens-doubles", "mixed-doubles",
    ]);
  });

  it("marks the doubles draws as not-yet-priced without hiding them", () => {
    // Censused 2026-08-26: zero US Open doubles markets at either source. The
    // section is ready; the markets are not.
    expect(drawIsPriced("mens-singles")).toBe(true);
    expect(drawIsPriced("mixed-doubles")).toBe(false);
  });

  it("renders a doubles result with no code change the day one arrives", () => {
    const doubles = results({
      matches: [
        result({
          matchup_key: "espn:190001",
          draw: "mixed-doubles",
          draw_label: "Mixed Doubles",
          round: "Round of 16",
          source_round: "Round of 16",
          players: [
            { entity_key: "a-b", display_name: "Hunter / Krawczyk", seed: 2,
              is_winner: true, prematch_probability: null },
            { entity_key: "c-d", display_name: "Siniakova / Zhang", seed: null,
              is_winner: false, prematch_probability: null },
          ],
          winner_entity_key: "a-b",
          score: "6-4, 7-5",
        }),
      ],
    });
    const html = renderToStaticMarkup(
      <TournamentResults results={doubles} draw="mixed-doubles" />
    );
    expect(html).toContain('data-draw="mixed-doubles"');
    expect(html).toContain("Mixed Doubles");
    expect(html).toContain("Hunter / Krawczyk");
    expect(html).toContain("6-4, 7-5");
  });

  it("stays out of the way for an unpriced draw with nothing played", () => {
    const html = renderToStaticMarkup(
      <TournamentResults
        results={results({ matches: [], source_competitions: 0 })}
        draw="womens-doubles"
      />
    );
    expect(html).toBe("");
  });

  it("filters strictly by draw — a men's result never leaks into the women's tab", () => {
    const both = results({
      matches: [result(), result({ matchup_key: "w", draw: "womens-singles" })],
      count: 2,
    });
    expect(resultsForDraw(both, "mens-singles")).toHaveLength(1);
    expect(resultsForDraw(both, "womens-singles")).toHaveLength(1);
    const html = renderToStaticMarkup(<TournamentResults results={both} draw="womens-singles" />);
    expect(html).toContain('data-count="1"');
  });
});

// ---------------------------------------------------------------------------
// UX-P146 — a finished match shows what the market said BEFORE it
//
// Alex, on the UX-P145 desktop artifact: "finished outcomes on the right must
// show their PRE-MATCH probabilities alongside the result — a result without
// the prior probability is half the story on a probability product."
// ---------------------------------------------------------------------------

/** The same fixture with a real prior on both sides. */
function withPrior(winner: number, loser: number, overrides: Partial<TournamentResult> = {}) {
  const base = result(overrides);
  return {
    ...base,
    players: base.players.map((player) => ({
      ...player,
      prematch_probability: player.is_winner ? winner : loser,
    })),
  };
}

describe("UX-P146 — the prior beside the result", () => {
  it("prints each player's pre-match number on their own line", () => {
    const html = renderToStaticMarkup(
      <TournamentResults results={results({ matches: [withPrior(0.62, 0.38)] })} draw="mens-singles" />
    );
    expect((html.match(/data-testid="result-prematch"/g) ?? []).length).toBe(2);
    expect(html).toContain("62%");
    expect(html).toContain("38%");
    // The machine-readable half, for the sentinels and the cert.
    expect(html).toContain('data-prematch="0.62"');
    expect(html).toContain('data-prematch="0.38"');
  });

  it("the upset is legible, which is the whole reason for the column", () => {
    // Production, men's qualifying second round 2026-08-26: Colton Smith went
    // in at 39.5% and won. Without the prior that row says "somebody beat
    // somebody"; with it, it is the most interesting row on the page.
    const html = renderToStaticMarkup(
      <TournamentResults results={results({ matches: [withPrior(0.395, 0.605)] })} draw="mens-singles" />
    );
    const winnerRow = html.slice(html.indexOf('data-outcome="won"'), html.indexOf('data-outcome="lost"'));
    // 39, not 40 — see the item-4 block below. This is the exact row Alex read
    // off the UX-P146 artifact as "40/61".
    expect(winnerRow).toContain("39%");
    expect(winnerRow).toContain("won");
  });

  /* ═══ UX-P147, ALEX'S ITEM 4: A PAIR ALWAYS SUMS TO 100 ═══
   *
   * "probabilities sum to 101% on most rows (74/27, 40/61, 60/41, 67/34).
   * Round complementarily so a pair always sums to 100 — and check whether the
   * underlying pair is normalized at all."
   *
   * It is: all twelve priors on `payload-2026-08-27.json` arrive summing to
   * exactly 1.000. The 101 was made at the last step, by rounding both halves
   * of a `.5` boundary up.
   */

  it("rounds the pair ONCE, so the two priors on a row cannot sum to 101", () => {
    // The four rows Alex read off the artifact, all of which summed to 101.
    const cases: Array<[number, number, string, string]> = [
      [0.735, 0.265, "74%", "26%"],
      [0.395, 0.605, "39%", "61%"],
      [0.595, 0.405, "60%", "40%"],
      [0.665, 0.335, "67%", "33%"],
    ];
    for (const [winner, loser, winnerPct, loserPct] of cases) {
      const percents = prematchPercents(withPrior(winner, loser));
      const values = Object.values(percents) as number[];
      expect(values[0] + values[1]).toBe(100);
      const html = renderToStaticMarkup(
        <TournamentResults
          results={results({ matches: [withPrior(winner, loser)] })}
          draw="mens-singles"
        />
      );
      expect(html).toContain(`>${winnerPct}<`);
      expect(html).toContain(`>${loserPct}<`);
    }
  });

  it("keeps the FAVOURITE's number and derives the underdog's from it", () => {
    // Both sides sit on `.5` here, so half-up rounding took both to 51 and 50.
    // Only one number may be rounded; the favourite is the one that survives,
    // because it is the one a reader is looking at.
    expect(prematchPercents(withPrior(0.495, 0.505))).toEqual({
      "jacob-fearnley": 49,
      "roberto-carballes-baena": 51,
    });
  });

  it("does not invent a complement when only one side has a prior", () => {
    // There is nothing to derive from, and `100 − 62` would be a number no
    // market ever quoted, printed under a real player's name.
    const oneSided = result({
      players: [
        { entity_key: "a", display_name: "A", seed: null, is_winner: true,
          prematch_probability: 0.62 },
        { entity_key: "b", display_name: "B", seed: null, is_winner: false,
          prematch_probability: null },
      ],
      winner_entity_key: "a",
    });
    expect(prematchPercents(oneSided)).toEqual({ a: 62, b: null });
  });

  it("shows NOTHING where we held no market — never a zero, never a dash", () => {
    // 64 of 76 production results are this case. A `0%` here would say the
    // market called the winner impossible, and an em dash in a probability
    // column reads as a number we lost.
    const html = renderToStaticMarkup(
      <TournamentResults results={results()} draw="mens-singles" />
    );
    expect(html).not.toContain('data-testid="result-prematch"');
    expect(html).not.toContain('data-testid="results-prematch-note"');
    // …and the result itself is untouched by the absence.
    expect(html).toContain("7-6, 6-3");
    expect(html).toContain("Jacob Fearnley");
  });

  it("states the coverage when only some rows have a prior", () => {
    const mixed = results({
      matches: [withPrior(0.62, 0.38), result({ matchup_key: "espn:2" })],
      count: 2,
    });
    const html = renderToStaticMarkup(<TournamentResults results={mixed} draw="mens-singles" />);
    expect(html).toContain('data-with-prematch="1"');
    expect(html).toContain('data-total="2"');
    expect(html).toContain("1 of 2");
  });

  it("does not state a coverage ratio when every row has one", () => {
    // "2 of 2" is noise. The note still explains WHAT the number is, because
    // that part is owed whether or not anything is missing.
    const all = results({
      matches: [withPrior(0.62, 0.38), withPrior(0.7, 0.3, { matchup_key: "espn:2" })],
      count: 2,
    });
    const html = renderToStaticMarkup(<TournamentResults results={all} draw="mens-singles" />);
    expect(html).toContain('data-testid="results-prematch-note"');
    expect(html).toContain("before the match started");
    expect(html).not.toContain("2 of 2");
  });

  it("the coverage is counted over THIS draw, not the payload's all-draws total", () => {
    // A footnote reading "12 of 76" under a list of 24 is a footnote about a
    // different list — which is what reading the payload's counter would give.
    const both = results({
      matches: [
        withPrior(0.62, 0.38),
        result({ matchup_key: "w1", draw: "womens-singles" }),
        result({ matchup_key: "w2", draw: "womens-singles" }),
      ],
      count: 3,
      with_prematch: 1,
    });
    const html = renderToStaticMarkup(<TournamentResults results={both} draw="mens-singles" />);
    expect(html).toContain('data-total="1"');
    expect(html).not.toContain('data-total="3"');
  });

  it("never rounds a real prior to 0% or 100%", () => {
    // Through `formatProbabilityPercent` (UX-P046), not a local Math.round: a
    // 0.4% prior printed as `0%` says the market called it impossible.
    expect(formatPrematch(0.004)).toBe("<1%");
    expect(formatPrematch(0.996)).toBe(">99%");
    expect(formatPrematch(0.62)).toBe("62%");
    expect(formatPrematch(null)).toBeNull();
    expect(formatPrematch(undefined)).toBeNull();
    expect(formatPrematch(Number.NaN)).toBeNull();
  });

  it("prematchCoverage counts MATCHES, not players", () => {
    // ux/1034 A3 added two more counts to this shape — WHY each priorless row
    // has no prior. The claim this test was written for is the pair below and
    // is unchanged: one MATCH has a prior, not two players.
    const two = [withPrior(0.62, 0.38), result({ matchup_key: "espn:2" })];
    const counted = prematchCoverage(two);
    expect(counted.withPrior).toBe(1);
    expect(counted.total).toBe(2);
    expect(prematchCoverage([])).toEqual({
      withPrior: 0,
      total: 0,
      heldWithoutOpening: 0,
      untied: 0,
    });
  });
});

// ---------------------------------------------------------------------------
// UX-P206 — the finished-match rows show the player's face
// ---------------------------------------------------------------------------
//
// Alex, 2026-08-30, on the live Tournament tab: "player faces missing". The
// board and the match list read the register's pinned block; this section
// refused images on a census of a source it is not fed by, and so became the
// one list on that tab drawn without people on it.
//
// Asserted at the RENDER and not on `avatarKind`, because a pure-layer test
// stays green the day the component stops printing the avatar
// (`reference_plant_must_hit_the_render`).

const FACE = "https://upload.wikimedia.org/fearnley.jpg";
const FLAG = "https://a.espncdn.com/gbr.png";

function withFaces(): ResultsModel {
  return results({
    matches: [
      result({
        players: [
          { entity_key: "jacob-fearnley", display_name: "Jacob Fearnley", seed: null,
            is_winner: true, prematch_probability: null,
            image: { url: FACE, flag_url: FLAG } },
          { entity_key: "roberto-carballes-baena", display_name: "Roberto Carballes Baena",
            seed: null, is_winner: false, prematch_probability: null,
            image: { url: null, flag_url: "https://a.espncdn.com/esp.png" } },
        ],
      }),
    ],
    player_slots: 2,
    with_face: 1,
    with_flag: 1,
  });
}

describe("UX-P206 — a finished match draws its players", () => {
  it("renders an avatar for BOTH sides of the row", () => {
    const html = renderToStaticMarkup(
      <TournamentResults results={withFaces()} draw="mens-singles" />
    );
    // Two avatars, one per player — not one for the winner and a gap where the
    // loser should be, which is what a `player.is_winner &&` would produce and
    // which would read as an ingest gap rather than a layout choice.
    expect(html.split('data-testid="player-avatar"').length - 1).toBe(2);
    expect(html).toContain(FACE);
  });

  it("draws the FACE when one is pinned and the FLAG when one is not", () => {
    const html = renderToStaticMarkup(
      <TournamentResults results={withFaces()} draw="mens-singles" />
    );
    expect(html).toContain('data-kind="face"');
    expect(html).toContain('data-kind="flag"');
    expect(html).toContain("https://a.espncdn.com/esp.png");
  });

  it("attaches each avatar to the RIGHT player", () => {
    const html = renderToStaticMarkup(
      <TournamentResults results={withFaces()} draw="mens-singles" />
    );
    /* A face under the wrong name is the worst failure this page has: instant,
     * confident, and something the reader cannot check.
     *
     * THIS ASSERTION WAS WRITTEN TWICE. The first version pinned the FACE
     * avatar to Fearnley's name and passed a plant that fed EVERY avatar
     * `players[0].display_name` — Fearnley is `players[0]`, so the one pairing
     * it checked was the one the plant happened to leave correct. A guard that
     * only inspects the row's first player cannot see a bug that mislabels the
     * second. Both cells are walked now, each against its OWN entity.
     */
    const cells = html
      .split('data-testid="result-player"')
      .slice(1)
      .map((chunk) => chunk.slice(0, chunk.indexOf('data-testid="result-player"') + 1 || undefined));
    expect(cells).toHaveLength(2);
    const expected: Record<string, string> = {
      "jacob-fearnley": "Jacob Fearnley",
      "roberto-carballes-baena": "Roberto Carballes Baena",
    };
    for (const cell of cells) {
      const entity = /data-entity="([^"]+)"/.exec(cell)?.[1];
      const avatarName = /data-entity-name="([^"]+)"/.exec(cell)?.[1];
      expect(entity).toBeDefined();
      expect(avatarName).toBe(expected[entity as string]);
    }
  });

  it("falls through to initials rather than throwing on an old cached payload", () => {
    // `image` is optional on the type precisely so a payload written before the
    // field existed still renders. Undefined, not null — the shape a stale
    // cache actually has.
    const html = renderToStaticMarkup(
      <TournamentResults results={results()} draw="mens-singles" />
    );
    expect(html).toContain('data-kind="initials"');
    expect(html).toContain("JF");
    // And the row is intact. A missing face never costs a result.
    expect(html).toContain("7-6, 6-3");
  });


  it("keeps the three grid tracks — the avatar rides INSIDE the name cell", () => {
    // UX-P147's columns are the reason this section is legible. An avatar added
    // as a fourth grid child would silently re-flow every prior and every score
    // one track to the right, on every row.
    const html = renderToStaticMarkup(
      <TournamentResults results={withFaces()} draw="mens-singles" />
    );
    expect(html).toContain("sm:grid-cols-[minmax(0,1fr)_max-content_max-content]");

    // CONTAINMENT, WALKED — see `innerHtmlOf`. BOTH cells, because an avatar
    // that only escapes the loser's cell is the same defect on half the rows,
    // and inspecting the row's first player is how the sibling guard in this
    // file was vacuous once already.
    const cells = [0, 1].map((nth) => innerHtmlOf(html, "result-player", nth));
    for (const cell of cells) {
      expect(cell).toContain('data-testid="player-avatar"');
    }
    // …and NOTHING is loose in the row outside a name cell, which is what a
    // fourth grid child IS. Every avatar the row draws is accounted for by the
    // two cells — the containment check above cannot see an EXTRA one.
    const row = innerHtmlOf(html, "result-row");
    const count = (chunk: string) =>
      (chunk.match(/data-testid="player-avatar"/g) ?? []).length;
    expect(count(row)).toBe(2);
    expect(cells.reduce((total, cell) => total + count(cell), 0)).toBe(count(row));
  });
});

describe("UX-P206 — ruling 8's coverage gate is computed, not remembered", () => {
  it("reads the payload's own counters", () => {
    expect(resultsImageCoverage(withFaces())).toEqual({
      slots: 2,
      withImage: 2,
      withFace: 1,
      fraction: 1,
    });
  });

  it("counts a FLAG as covered — that is what makes the column uniform", () => {
    const flagsOnly = results({ player_slots: 4, with_face: 0, with_flag: 4 });
    expect(resultsImageCoverage(flagsOnly)).toMatchObject({
      withImage: 4,
      withFace: 0,
      fraction: 1,
    });
  });

  it("returns null for NOT MEASURED, which is not the same as zero", () => {
    // Gotcha #53: an absent counter and a counter reading 0 are different
    // facts, and a gate that conflates them fails open on an old cache.
    expect(resultsImageCoverage(results())).toBeNull();
    expect(resultsImageCoverage(null)).toBeNull();
    expect(resultsImageCoverage(results({ player_slots: 0 }))).toBeNull();
    const measuredZero = results({ player_slots: 4, with_face: 0, with_flag: 0 });
    expect(resultsImageCoverage(measuredZero)).toMatchObject({ fraction: 0 });
  });
});
