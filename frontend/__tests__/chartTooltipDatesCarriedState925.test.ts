// #925 — THE HOVER TOOLTIP DATES THE STATE IT CARRIES.
//
// ── THE UNPAID CLAUSE ────────────────────────────────────────────────────────
//
// The first #925 delivery (`artifacts/other-model-chart-clients-finish`,
// REPORT.md) named it: "the hover TOOLTIP still prints a carried period/clock
// unmarked — #7860's guard pins that span to the bare helper call". #8206 paid
// the readout card and left the tooltip as it was. Codex's disposition
// (CODEX-REVIEW.md, 2026-09-23) returned it: "finish that existing clause while
// preserving #7860's clock-deduplication controls".
//
// ── WHAT THE READER SAW ──────────────────────────────────────────────────────
//
// Hovering a gap-filled minute at 8:03 PM whose clock was last seen at 8:00 PM,
// the tooltip header read `Q1 7:41` with no mark and no age — the same clock the
// card under the chart had already learned to date.
//
// ── THE SHAPE OF THE FIX ─────────────────────────────────────────────────────
//
// The period/clock span cannot change: #7860 asserts its body is exactly the
// bare `formatLiveClockLabel(...)` call, so the `~` the card uses is not
// available to the tooltip. The disclosure is therefore a SIBLING line that
// names the carried half in words — `clock as of 8:00 PM` — through one pure
// rule, `carriedStateDisclosure` (`lib/chartGameState.ts`), decided over what
// `trustedLiveClock` renders. This file drives that rule on the exact field
// shape the tooltip hands it, then reads the call site.
//
// ── RED FIRST ────────────────────────────────────────────────────────────────
//
// On master (`020544e48`) this file fails at import: `carriedStateDisclosure`
// does not exist, and the call-site arm finds no `chart-tooltip-state-as-of`.
// Logged in the delivery as `jest-tooltip-925-RED-master.txt`.

import { readFileSync } from "fs";
import { join } from "path";

import { carriedStateDisclosure, carryGameStateForward } from "@/lib/chartGameState";

const SOURCE = readFileSync(join(__dirname, "..", "components", "OddsChart.tsx"), "utf8");

const t0 = "2026-09-22T20:00:00Z";
const t3 = "2026-09-22T20:03:00Z";
const t7 = "2026-09-22T20:07:00Z";

/** The real path: carry the rows, hand the last one's fields to the rule. */
function disclose(rows: Parameters<typeof carryGameStateForward>[0]) {
  const p = carryGameStateForward(rows).at(-1)!;
  return carriedStateDisclosure({
    timestamp: p.timestamp,
    period: p._period,
    clock: p._clock,
    hasScore: p._homeScore != null && p._awayScore != null,
    periodObservedAt: p._periodObservedAt,
    clockObservedAt: p._clockObservedAt,
    scoreObservedAt: p._scoreObservedAt,
    periodApprox: p._periodApprox,
    clockApprox: p._clockApprox,
    scoreApprox: p._scoreApprox,
  });
}

describe("#925 — the tooltip's carried-state line", () => {
  // Codex's two arms, on the tooltip.
  it("a period-only observation does not erase the carried clock's age", () => {
    const d = disclose([
      { timestamp: t0, _period: "1", _clock: "7:41" },
      { timestamp: t3, _period: "1" },
    ]);
    expect(d).toEqual({ carried: "clock", asOf: "8:00 PM", text: "clock as of 8:00 PM" });
  });

  it("a clock-only observation does not present a carried period as freshly observed", () => {
    const d = disclose([
      { timestamp: t0, _period: "1", _clock: "7:41" },
      { timestamp: t3, _clock: "4:41" },
    ]);
    expect(d).toEqual({ carried: "period", asOf: "8:00 PM", text: "period as of 8:00 PM" });
  });

  it("a complete new observation has no line (control)", () => {
    expect(
      disclose([
        { timestamp: t0, _period: "1", _clock: "7:41" },
        { timestamp: t3, _period: "1", _clock: "4:41" },
      ]),
    ).toBeNull();
  });

  it("both halves carried from different minutes: the line names the OLDER", () => {
    const d = disclose([
      { timestamp: t0, _period: "1" },
      { timestamp: t3, _clock: "4:41" },
      { timestamp: t7 },
    ]);
    expect(d).toEqual({
      carried: "period and clock",
      asOf: "8:00 PM",
      text: "period and clock as of 8:00 PM",
    });
  });

  it("a carry inside the displayed minute says nothing (nothing to say)", () => {
    expect(
      disclose([
        { timestamp: "2026-09-22T20:00:10Z", _period: "1", _clock: "7:41" },
        { timestamp: "2026-09-22T20:00:50Z" },
      ]),
    ).toBeNull();
  });

  it("a score carried under an empty badge is dated by its own row; under a badge it is not", () => {
    expect(
      disclose([
        { timestamp: t0, _homeScore: 3, _awayScore: 0 },
        { timestamp: t3 },
      ]),
    ).toEqual({ carried: "score", asOf: "8:00 PM", text: "score as of 8:00 PM" });
    expect(
      disclose([
        { timestamp: t0, _homeScore: 3, _awayScore: 0 },
        { timestamp: t3, _period: "1", _clock: "4:41" },
      ]),
    ).toBeNull();
  });

  it("a carried field with no date to name draws no line (no time is invented)", () => {
    expect(
      carriedStateDisclosure({
        timestamp: t3,
        period: "1",
        clock: "7:41",
        hasScore: false,
        clockApprox: true,
        clockObservedAt: null,
      }),
    ).toBeNull();
  });

  // #7860 interaction — preserved, and its consequence for the line.
  describe("#7860 — a clock the tooltip does not print cannot date the line", () => {
    it("ESPN's period detail already spells the clock: the dropped clock is not dated", () => {
      // `9:44 - 2nd Quarter` beside `9:44` renders as the period alone (#7860
      // `alreadySpelledOut`). The clock is carried, but it is not on screen.
      expect(
        carriedStateDisclosure({
          timestamp: t3,
          period: "9:44 - 2nd Quarter",
          clock: "9:44",
          hasScore: true,
          periodObservedAt: t3,
          clockObservedAt: t0,
          periodApprox: false,
          clockApprox: true,
        }),
      ).toBeNull();
    });

    it("`Final` / `Final`: one token, judged as the period", () => {
      expect(
        carriedStateDisclosure({
          timestamp: t3,
          period: "Final",
          clock: "Final",
          hasScore: true,
          periodObservedAt: t0,
          clockObservedAt: t0,
          periodApprox: true,
          clockApprox: true,
        }),
      ).toEqual({ carried: "period", asOf: "8:00 PM", text: "period as of 8:00 PM" });
    });

    it("a clock the period does not spell is kept, and dated when carried", () => {
      expect(
        carriedStateDisclosure({
          timestamp: t3,
          period: "Halftime",
          clock: "0:00",
          hasScore: true,
          periodObservedAt: t3,
          clockObservedAt: t0,
          periodApprox: false,
          clockApprox: true,
        }),
      ).toEqual({ carried: "clock", asOf: "8:00 PM", text: "clock as of 8:00 PM" });
    });
  });

  describe("the call site — a correct helper nothing calls is not a fix", () => {
    it("renders the line as a SIBLING of the #7860-pinned span, never inside it", () => {
      expect(SOURCE).toContain('data-testid="chart-tooltip-state-as-of"');
      expect(SOURCE).toMatch(/\{carriedDisclosure && \(\s*<p[^>]*data-testid="chart-tooltip-state-as-of"[^>]*>\s*\{carriedDisclosure\.text\}\s*<\/p>\s*\)\}/);
      // #7860's span body is still the bare helper call — its own suite
      // asserts this too; repeated here so a change to either file trips both.
      const span = SOURCE.match(/\{matchingPoint\._period && \(\s*<span[^>]*>([\s\S]*?)<\/span>/);
      expect(span).not.toBeNull();
      expect((span as RegExpMatchArray)[1].trim().replace(/\s+/g, " ")).toBe(
        "{formatLiveClockLabel( matchingPoint._period as string, matchingPoint._clock as string | undefined, )}",
      );
    });

    it("feeds the rule every per-field date and flag the enrich step writes", () => {
      for (const f of [
        "_periodObservedAt",
        "_clockObservedAt",
        "_scoreObservedAt",
        "_periodApprox",
        "_clockApprox",
        "_scoreApprox",
      ]) {
        expect(SOURCE).toMatch(new RegExp(`carriedStateDisclosure\\(\\{[\\s\\S]*?matchingPoint\\.${f}[\\s\\S]*?\\}\\)`));
      }
    });
  });
});
