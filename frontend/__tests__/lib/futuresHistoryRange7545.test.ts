// #7545 — guards for the futures page's reader-chosen history rungs.
//
// The defect these pin: the page derived ONE window on mount and offered no
// control, so months of served history were unreachable and the span moved on
// its own. Measured on production 2026-09-20 — /futures/112921 served 161 points
// at the 168h default and 4,527 at hours=8760 (back to 2026-02-19); /futures/171
// was read twice at hours=168 and answered actual_hours=720 once and 168 the
// other time.

import {
  FUTURES_ALL_FALLBACK_HOURS,
  FUTURES_ALL_MAX_HOURS,
  FUTURES_ALL_MIN_HOURS,
  FUTURES_FIXED_RANGE_HOURS,
  FUTURES_RANGE_CHIPS,
  FUTURES_RANGE_KEYS,
  defaultFuturesRange,
  futuresRangeHours,
  futuresRangeSpanWords,
  isFuturesRangeKey,
  rangeCoverageNote,
} from "@/lib/futuresHistoryRange";
import { CHART_RANGES } from "@/lib/chartWindow";

// A fixed clock. Gotcha #44: offset from this, never branch on the real one.
const NOW = Date.parse("2026-09-20T18:00:00.000Z");
const HOUR = 60 * 60 * 1000;
const hoursAgo = (h: number) => new Date(NOW - h * HOUR).toISOString();

describe("#7545 the chips reuse the shared vocabulary", () => {
  it("offers exactly week / month / all, narrowest first", () => {
    expect(FUTURES_RANGE_KEYS).toEqual(["1W", "1M", "all"]);
    expect(FUTURES_RANGE_CHIPS.map((c) => c.key)).toEqual(["1W", "1M", "all"]);
  });

  it("takes every chip from CHART_RANGES rather than re-declaring a label", () => {
    // If a chip's label were written here instead of read from the shared list,
    // this page's "1M" could drift from the "1M" the two event-concept charts
    // show for the same key.
    for (const chip of FUTURES_RANGE_CHIPS) {
      expect(CHART_RANGES).toContain(chip);
    }
  });

  it("does not offer the two shared rungs this page has no data shape for", () => {
    const keys = FUTURES_RANGE_CHIPS.map((c) => c.key);
    expect(keys).not.toContain("1D");
    expect(keys).not.toContain("since_start");
  });
});

describe("#7545 isFuturesRangeKey guards a reader-editable URL", () => {
  it.each(["1W", "1M", "all"])("accepts %s", (k) => {
    expect(isFuturesRangeKey(k)).toBe(true);
  });

  it.each([
    ["a real ChartRangeKey this page does not offer", "1D"],
    ["the other one", "since_start"],
    ["wrong case", "1w"],
    ["junk", "../../etc"],
    ["empty", ""],
  ])("rejects %s", (_why, v) => {
    expect(isFuturesRangeKey(v)).toBe(false);
  });

  it("rejects non-strings without throwing", () => {
    for (const v of [null, undefined, 7, {}, ["1W"]]) {
      expect(isFuturesRangeKey(v)).toBe(false);
    }
  });
});

describe("#7545 futuresRangeHours", () => {
  it("maps the fixed rungs to the windows they are named for", () => {
    expect(futuresRangeHours("1W", null, NOW)).toBe(168);
    expect(futuresRangeHours("1M", null, NOW)).toBe(720);
    expect(FUTURES_FIXED_RANGE_HOURS).toEqual({ "1W": 168, "1M": 720 });
  });

  it("ignores created_at for the fixed rungs — a week is a week", () => {
    expect(futuresRangeHours("1W", hoursAgo(9000), NOW)).toBe(168);
  });

  // THE REGRESSION THIS SHIP EXISTS FOR. The old settled-market branch capped at
  // 4320h and called it the full life. 112921 opened 2026-02-19, which is ~5,100
  // hours before this clock, and its prices go all the way back.
  it("reaches PAST the old 4320h cap for a market older than 180 days", () => {
    const taiwanOpen = "2026-02-19T01:41:04.420888+00:00";
    const hours = futuresRangeHours("all", taiwanOpen, NOW);
    expect(hours).toBeGreaterThan(4320);
    // the open, plus the 24h of slack, and nothing invented beyond it
    const expected = Math.ceil((NOW - Date.parse(taiwanOpen)) / HOUR + 24);
    expect(hours).toBe(expected);
  });

  it("floors 'all' at a month so a market opened this morning still draws", () => {
    expect(futuresRangeHours("all", hoursAgo(3), NOW)).toBe(FUTURES_ALL_MIN_HOURS);
  });

  it("caps 'all' so one ancient market cannot ask for everything", () => {
    expect(futuresRangeHours("all", hoursAgo(500_000), NOW)).toBe(FUTURES_ALL_MAX_HOURS);
  });

  it("falls back to a WIDE window when the market will not say when it opened", () => {
    for (const bad of [null, undefined, "", "not-a-date"]) {
      const hours = futuresRangeHours("all", bad, NOW);
      // Asserted against a literal, not against FUTURES_ALL_FALLBACK_HOURS:
      // comparing the constant to itself is an assertion that cannot fail, and
      // the whole point of the fallback is that an unknown open must not quietly
      // collapse "All" back to a narrow window.
      expect(hours).toBe(8760);
      expect(hours).toBeGreaterThan(FUTURES_FIXED_RANGE_HOURS["1M"]);
    }
    expect(FUTURES_ALL_FALLBACK_HOURS).toBe(8760);
  });

  it("treats a created_at in the future as unknown, never as a negative window", () => {
    const hours = futuresRangeHours("all", hoursAgo(-500), NOW);
    expect(hours).toBe(8760);
    expect(hours).toBeGreaterThan(0);
  });
});

describe("#7545 defaultFuturesRange preserves what the derived window reached for", () => {
  it("opens a settled market on its whole life", () => {
    expect(defaultFuturesRange({ status: "resolved" }, NOW)).toBe("all");
  });

  it("treats a past resolution_date as settled even without the status", () => {
    expect(
      defaultFuturesRange({ resolution_date: hoursAgo(10) }, NOW)
    ).toBe("all");
  });

  it("does not treat a FUTURE resolution_date as settled", () => {
    expect(
      defaultFuturesRange({ resolution_date: hoursAgo(-10), updated_at: hoursAgo(1) }, NOW)
    ).toBe("1W");
  });

  it("opens a market that has gone quiet on a month", () => {
    expect(defaultFuturesRange({ updated_at: hoursAgo(100) }, NOW)).toBe("1M");
  });

  it("opens an actively-priced market on a week", () => {
    expect(defaultFuturesRange({ updated_at: hoursAgo(2) }, NOW)).toBe("1W");
  });

  it("holds the 72h boundary", () => {
    expect(defaultFuturesRange({ updated_at: hoursAgo(72) }, NOW)).toBe("1W");
    expect(defaultFuturesRange({ updated_at: hoursAgo(73) }, NOW)).toBe("1M");
  });

  it("opens on a week when there is no market yet", () => {
    expect(defaultFuturesRange(null, NOW)).toBe("1W");
    expect(defaultFuturesRange({}, NOW)).toBe("1W");
  });
});

describe("#7545 rangeCoverageNote reconciles the chip with what arrived", () => {
  it("says nothing when the API served the window that was asked for", () => {
    expect(rangeCoverageNote(168, 168)).toBeNull();
  });

  it("says nothing when the API served LESS — that is coverage, not a widening", () => {
    expect(rangeCoverageNote(4320, 900)).toBeNull();
  });

  // /futures/171, read at hours=168, answered actual_hours=720.
  it("names both windows when the backend widened past the chosen rung", () => {
    expect(rangeCoverageNote(168, 720)).toBe(
      "Too few prices in 7 days — showing 30 days."
    );
  });

  it("stays silent when the API does not report an actual window", () => {
    expect(rangeCoverageNote(168, null)).toBeNull();
    expect(rangeCoverageNote(168, undefined)).toBeNull();
    expect(rangeCoverageNote(168, NaN)).toBeNull();
  });

  it("does not report a sub-hour rounding difference as a widening", () => {
    expect(rangeCoverageNote(168, 168.4)).toBeNull();
  });

  it("refuses a nonsense request rather than dividing by it", () => {
    expect(rangeCoverageNote(0, 720)).toBeNull();
    expect(rangeCoverageNote(-5, 720)).toBeNull();
    expect(rangeCoverageNote(NaN, 720)).toBeNull();
  });

  it("never prints a bare enum key or snake_case at a reader", () => {
    const note = rangeCoverageNote(168, 2160);
    expect(note).not.toMatch(/_|1W|1M|actual_hours/);
  });
});

describe("#7545 futuresRangeSpanWords names the window the empty state is about", () => {
  it("names the fixed rungs in days", () => {
    expect(futuresRangeSpanWords("1W", null, NOW)).toBe("the last 7 days");
    expect(futuresRangeSpanWords("1M", null, NOW)).toBe("the last 30 days");
  });

  it("does not claim a day count for 'all'", () => {
    expect(futuresRangeSpanWords("all", hoursAgo(5000), NOW)).toBe(
      "this market's history"
    );
  });
});
