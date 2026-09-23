/**
 * #8135 — A CLOCK-ONLY AXIS LABEL IS ONLY HONEST WHILE THE READER IS STANDING
 * IN THE DOMAIN IT LABELS.
 *
 * THE DEFECT, photographed on production 2026-09-23 at 390px. `/futures/59520336`
 * holds six observations, all on the afternoon of 24 August. Its x-axis read
 * `1:48 PM · 4:03 PM · 6:19 PM`, with no date anywhere on it, over a card that
 * captioned itself "Last number 29 days ago" four lines lower. The label rule
 * branched on the SPAN of the data alone, and the span of a five-hour burst is
 * five hours whether it happened this afternoon or four weeks ago.
 *
 * ── THE ZONE IS PINNED IN THE CALL, NOT AROUND THE RUNNER ──
 *
 * Every assertion about exact text passes `TZ` explicitly. A single `TZ=` on the
 * jest process is not a guard against a zone-sensitive rule: `Intl` caches its
 * formatters before a later pin can take effect, so the mutant that drops the
 * zone survives. Passing it per call makes that mistake unexpressible here.
 */

import {
  axisTimeFormat,
  formatAxisTime,
  CLOCK_ONLY_WITHIN_MS,
} from "@/lib/chartAxisTimeLabel";

const MIN = 60 * 1000;
const HOUR = 60 * MIN;
const DAY = 24 * HOUR;

/** Pacific, because that is the zone the specimen's numbers were read in. */
const TZ = "America/Los_Angeles";

/** 2026-09-23 14:20Z — when the defect was photographed. */
const NOW = Date.UTC(2026, 8, 23, 14, 20, 0);

/** The specimen's real burst: 2026-08-24 20:16Z → 2026-08-25 01:19Z. */
const BURST_START = Date.UTC(2026, 7, 24, 20, 16, 49);
const BURST_END = Date.UTC(2026, 7, 25, 1, 19, 15);

describe("#8135 — which label shape a domain earns", () => {
  it("names the day when a short span is NOT the one the reader is in", () => {
    // The specimen. Five hours of data, four weeks old.
    expect(BURST_END - BURST_START).toBeLessThan(DAY);
    expect(axisTimeFormat(BURST_START, BURST_END, NOW)).toBe("dayClock");
  });

  it("still gives a clock-only axis to a short span the reader IS in", () => {
    // The case the old rule got right, and the one a fix must not take away:
    // five hours of data ending now reads perfectly well as bare clock times.
    expect(axisTimeFormat(NOW - 5 * HOUR, NOW, NOW)).toBe("clock");
  });

  it("is decided by the domain's START, so a span straddling two days is dated", () => {
    // A 23-hour span ending 20 hours ago passes an "ends recently" test while
    // covering 43 hours of wall clock — long enough for two ticks a day apart to
    // print the SAME clock label, which is #2885's defect reintroduced by the fix
    // for it. Proved here rather than asserted: these two instants are 24h apart
    // and are indistinguishable under `clock`.
    const end = NOW - 20 * HOUR;
    const start = end - 23 * HOUR;
    expect(formatAxisTime(start + HOUR, "clock", TZ)).toBe(
      formatAxisTime(start + HOUR + DAY, "clock", TZ),
    );
    expect(axisTimeFormat(start, end, NOW)).toBe("dayClock");
  });

  it("puts the clock/date boundary exactly one day back, and both sides of it", () => {
    // Equality is the recent side. A mutant flipping `>=` to `>` fails here and
    // nowhere else.
    expect(axisTimeFormat(NOW - CLOCK_ONLY_WITHIN_MS, NOW - HOUR, NOW)).toBe("clock");
    expect(axisTimeFormat(NOW - CLOCK_ONLY_WITHIN_MS - 1, NOW - HOUR, NOW)).toBe(
      "dayClock",
    );
    expect(CLOCK_ONLY_WITHIN_MS).toBe(DAY);
  });

  it("puts the short/long span boundary at exactly a day, and both sides of it", () => {
    // A domain exactly 24h wide is NOT short. Catches `<` -> `<=`.
    expect(axisTimeFormat(NOW - DAY, NOW, NOW)).toBe("dayHour");
    expect(axisTimeFormat(NOW - DAY + 1, NOW, NOW)).toBe("clock");
  });

  it("leaves the two branches that already carry a date exactly as they were", () => {
    // The control. This change ADDS a day to one branch; if any other moved, the
    // fix is a rewrite of the axis and not a repair of it.
    expect(axisTimeFormat(NOW - 36 * HOUR, NOW, NOW)).toBe("dayHour");
    expect(axisTimeFormat(NOW - 10 * DAY, NOW, NOW)).toBe("day");
    // ...and age does not reach them: a week-old 36h window is still `dayHour`.
    expect(axisTimeFormat(NOW - 8 * DAY, NOW - 8 * DAY + 36 * HOUR, NOW)).toBe(
      "dayHour",
    );
  });

  it("fails toward the MORE explicit label when the clock is unreadable", () => {
    // A non-finite `now` can only make the recency test false. Saying more is the
    // safe direction for a rule about ambiguity.
    expect(axisTimeFormat(NOW - HOUR, NOW, NaN)).toBe("dayClock");
  });
});

describe("#8135 — what each shape renders", () => {
  it("dates the specimen's ticks without losing their minutes", () => {
    // Minutes stay because the span is short: on a five-hour burst an hour-only
    // label collapses `3:10 PM` and `3:40 PM` onto one string.
    expect(formatAxisTime(BURST_START, "dayClock", TZ)).toBe("Aug 24, 1:16 PM");
    expect(formatAxisTime(BURST_END, "dayClock", TZ)).toBe("Aug 24, 6:19 PM");
  });

  it("renders the three pre-existing shapes byte-for-byte as before", () => {
    // The strings the old inline formatter produced, pinned so a refactor cannot
    // quietly restyle an axis nobody was asked to change.
    expect(formatAxisTime(BURST_START, "clock", TZ)).toBe("1:16 PM");
    expect(formatAxisTime(BURST_START, "dayHour", TZ)).toBe("Aug 24 1 PM");
    expect(formatAxisTime(BURST_START, "day", TZ)).toBe("Aug 24");
  });

  it("honours the zone it is given, rather than the one the process is in", () => {
    // 2026-08-24 20:16Z is the 24th in Los Angeles and the 25th in Tokyo. A
    // formatter that ignored its zone argument would print one of these twice.
    expect(formatAxisTime(BURST_START, "dayClock", TZ)).toBe("Aug 24, 1:16 PM");
    expect(formatAxisTime(BURST_START, "dayClock", "Asia/Tokyo")).toBe(
      "Aug 25, 5:16 AM",
    );
  });
});
