// #7860 — THE WIN-PROBABILITY TOOLTIP PRINTED THE GAME CLOCK TWICE.
//
// ── WHAT THE READER SAW ──────────────────────────────────────────────────────
//
// `bainluck.com/events/14780544` (KC 33–30 IND, an overtime NFL final), 390px,
// 2026-09-21. Hovering the chart, the tooltip's header row:
//
//     Chiefs 10 – 13 Colts        9:44 - 2nd Quarter 9:44
//     Chiefs 17 – 20 Colts        Halftime 0:00
//     Chiefs 30 – 27 Colts        5:09 - OT 5:09
//
// and at the whistle:
//
//     Chiefs 33 – 30 Colts        Final Final
//
// ESPN's period DETAIL already spells the clock — `period: "9:44 - 2nd Quarter"`
// arrives beside `game_clock: "9:44"` — and the card appended the second field to
// the first. Measured by hovering the real production chart (not by reading the
// payload): `tools/chart-tooltip-clip-1833.mjs` reported the rendered card text
// verbatim at five pointer positions.
//
// Reach, over the served payloads of four completed games:
//
//     KC–IND (NFL)                454 of 487 rows   93%
//     Minnesota–Chicago (NHL)      64 of 127 rows   50%
//     Edmonton–Winnipeg (NHL)      68 of 135 rows   50%
//
// It is worst where the card is already in trouble: this is the header row of a
// 278×444–477px tooltip that overflows its own plot vertically by 79px (#7848),
// on the surface #1833 narrowed to stop it being painted off the phone edge.
//
// ── WHY THERE IS NO NEW RULE IN THE FIX ──────────────────────────────────────
//
// `trustedLiveClock` (lib/gameTimeLabel.ts, #6684) has decided exactly this
// question since it was written, and three surfaces already route through it —
// EventCard, FeedCard and the event-page header. Its two clauses are the two
// shapes above: `alreadySpelledOut` (a clock-shaped token the period already
// contains) and `repeatsPeriod` ("Final" beside "Final"). The chart tooltip was
// the one call site still concatenating by hand, so the fix is to delete the
// hand-rolled concatenation, not to write a fourth copy of the rule.
//
// THE CALL-SITE ARM BELOW IS THE LOAD-BEARING HALF. `formatLiveClockLabel` was
// already correct and already tested; a suite that only drove the helper would
// have passed against the broken component every day it shipped. #7839's guard
// learned this the same way.

import { readFileSync } from "fs";
import { join } from "path";
import { formatLiveClockLabel, trustedLiveClock } from "@/lib/gameTimeLabel";

const SOURCE = readFileSync(
  join(__dirname, "..", "components", "OddsChart.tsx"),
  "utf8",
);

/**
 * Every distinct `(period, game_clock)` pair the three games above served, as
 * `espn_history` gave them. Captured while the defect was live, so the file IS
 * the specimen — 113 of its 247 rows print a repeat and 134 do not, which is
 * what makes it able to fail in both directions rather than only one.
 */
const SPECIMENS: { rows: { period: string; clock: string | null; event_id: number }[] } =
  JSON.parse(
    readFileSync(
      join(__dirname, "fixtures", "chartTooltipPeriodClock7860.json"),
      "utf8",
    ),
  );

/** What the component printed before the fix. Kept so the two are compared, not asserted apart. */
const previousRule = (period: string, clock: string | null): string =>
  period + (clock ? ` ${clock}` : "");

describe("#7860 — the chart tooltip's period/clock line", () => {
  it("never prints a token that is already on the line", () => {
    const repeats: string[] = [];
    for (const { period, clock } of SPECIMENS.rows) {
      const rendered = formatLiveClockLabel(period, clock ?? undefined);
      if (!clock) continue;
      // The clock may appear once (inside the period detail). Twice is the defect.
      const occurrences = rendered.split(clock).length - 1;
      if (occurrences > 1) repeats.push(`${period!} + ${clock} -> ${rendered}`);
    }
    expect(repeats).toEqual([]);
  });

  it("says 'Final', not 'Final Final'", () => {
    expect(formatLiveClockLabel("Final", "Final")).toBe("Final");
    // The pair is real, not invented: it is in the fixture.
    expect(
      SPECIMENS.rows.some((r) => r.period === "Final" && r.clock === "Final"),
    ).toBe(true);
  });

  it("changes ONLY rows that carried a repeat, and leaves the rest byte-identical", () => {
    let changed = 0;
    for (const { period, clock } of SPECIMENS.rows) {
      const before = previousRule(period, clock);
      const after = formatLiveClockLabel(period, clock ?? undefined);
      if (before === after) continue;
      changed += 1;
      // A change may only ever be a DELETION of the trailing clock — never a
      // rewrite, a reorder, or a new word.
      expect(before).toBe(`${after} ${clock}`);
    }
    // Both arms are exercised by real rows: some change, most of the corpus does not.
    expect(changed).toBeGreaterThan(50);
    expect(changed).toBeLessThan(SPECIMENS.rows.length);
  });

  it("KEEPS a clock the period does not already spell — the refusal arm", () => {
    // A running period keeps a clock it does not already spell.
    expect(formatLiveClockLabel("3rd Quarter", "4:12")).toBe("3rd Quarter 4:12");
    // These are real rows from the same fixture. They were kept here as
    // "Halftime 0:00" until #8937 made that second decision: a break has no
    // running clock (rule 6), so the stopped clock goes and the break stays.
    for (const period of ["Halftime", "End of 3rd Quarter", "End of OT"]) {
      expect(SPECIMENS.rows.some((r) => r.period === period)).toBe(true);
      expect(formatLiveClockLabel(period, "0:00")).toBe(period);
    }
    // And a shape no NFL/NHL row has, which is exactly why it is asserted here:
    // a soccer clock is not spelled inside its period.
    expect(formatLiveClockLabel("2nd Half", "67'")).toBe("2nd Half 67'");
  });

  it("deletes a clock through the SPORT arm only for a sport that declares none", () => {
    // #10414 — this arm used to assert that NO sport key reached the tooltip, so
    // the arm could never fire. That was #7860's honest scope (the component had
    // no key then), and it is why every MLB tooltip still read `Top 9th 0:00`
    // after #6684. The key is passed now. What must still hold: a CLOCKED sport
    // keeps its clock, and an absent key changes nothing.
    expect(trustedLiveClock("Bottom 8th", "3:21").gameClock).toBe("3:21");
    expect(formatLiveClockLabel("2:00 - 4th Quarter", "1:00")).toBe(
      "2:00 - 4th Quarter 1:00",
    );
    expect(formatLiveClockLabel("3rd Quarter", "4:12", " ", "americanfootball_nfl")).toBe(
      "3rd Quarter 4:12",
    );
    expect(formatLiveClockLabel("Top 9th", "0:00", " ", "baseball_mlb")).toBe("Top 9th");
  });

  describe("the call site — a correct helper nothing calls is not a fix", () => {
    it("routes the tooltip's period line through formatLiveClockLabel", () => {
      expect(SOURCE).toContain(
        'import { formatLiveClockLabel } from "@/lib/gameTimeLabel"',
      );
      expect(SOURCE).toMatch(
        /formatLiveClockLabel\(\s*matchingPoint\._period as string,\s*matchingPoint\._clock as string \| undefined,\s*" ",\s*sportKey,?\s*\)/,
      );
    });

    it("has no hand-rolled period+clock concatenation left in the tooltip's span", () => {
      // The exact expression that shipped the defect.
      expect(SOURCE).not.toMatch(
        /matchingPoint\._clock\s*\?\s*`\s*\$\{matchingPoint\._clock as string\}`/,
      );

      // Scoped, because a file-wide search cannot tell a JOIN from two fields
      // merely being near each other: `_period` and `_clock` legitimately sit on
      // adjacent lines in the type declaration and twice in the enrichment loop.
      // So read the span that renders the line and require its whole body to be
      // the helper call.
      const span = SOURCE.match(
        /\{matchingPoint\._period && \(\s*<span[^>]*>([\s\S]*?)<\/span>/,
      );
      expect(span).not.toBeNull();
      const body = (span as RegExpMatchArray)[1].trim();
      expect(body.startsWith("{formatLiveClockLabel(")).toBe(true);
      expect(body.endsWith(")}")).toBe(true);
      // Nothing is appended after the call — the `${_clock}` tail is what the
      // reader was reading twice.
      expect(body.replace(/\s+/g, " ")).toBe(
        '{formatLiveClockLabel( matchingPoint._period as string, matchingPoint._clock as string | undefined, " ", sportKey, )}',
      );
    });

    it("keeps the outer `_period` guard, so the change is a deletion and not a widening", () => {
      // Without it, a point with a clock and no period would start rendering a
      // bare "9:44" where today nothing renders.
      expect(SOURCE).toMatch(/\{matchingPoint\._period && \(/);
    });
  });
});
