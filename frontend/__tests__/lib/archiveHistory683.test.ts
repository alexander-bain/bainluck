/**
 * #683 — the words a chart uses for points recovered from Kalshi's archive.
 *
 * Fixtures follow calibration's documented additive contract (PR #11083 head
 * e882cb665b, not yet published): an archive point is
 * `{timestamp: <close>, probability, american_odds: null, bookmaker:
 * "kalshi_archive", provenance: "kalshi_archive", interval_start,
 * period_minutes, price_basis}`; a live point carries no `provenance`.
 * Every rule is asserted in both directions — a chart with no archive point
 * says nothing.
 */

import {
  KALSHI_ARCHIVE_PROVENANCE,
  archiveChartNote,
  archiveTooltipNote,
  isArchivePoint,
} from "@/lib/archiveHistory";
import type { FuturesHistoryPoint } from "@/lib/types";

const HOUR = 60 * 60 * 1000;
const START = Date.UTC(2026, 2, 2, 0, 0, 0); // Mar 2 2026, 00:00Z
const NOW = Date.UTC(2026, 9, 15, 20, 0, 0);
const OPTS = { timeZone: "UTC", now: NOW };

function archive(
  hourIndex: number,
  overrides: Partial<FuturesHistoryPoint> = {},
): FuturesHistoryPoint {
  const close = START + (hourIndex + 1) * HOUR;
  return {
    timestamp: new Date(close).toISOString(),
    probability: 0.41,
    american_odds: null,
    bookmaker: KALSHI_ARCHIVE_PROVENANCE,
    provenance: KALSHI_ARCHIVE_PROVENANCE,
    interval_start: new Date(close - HOUR).toISOString(),
    period_minutes: 60,
    price_basis: "traded_interval",
    ...overrides,
  };
}

function live(atMs: number): FuturesHistoryPoint {
  return {
    timestamp: new Date(atMs).toISOString(),
    probability: 0.44,
    american_odds: null,
    bookmaker: "consensus",
  };
}

const series = (...history: FuturesHistoryPoint[]) => [{ history }];
const hours = (n: number, o: Partial<FuturesHistoryPoint> = {}) =>
  Array.from({ length: n }, (_, i) => archive(i, o));

describe("isArchivePoint", () => {
  it("reads either marker the contract sets, and nothing else", () => {
    expect(isArchivePoint(archive(0))).toBe(true);
    expect(isArchivePoint({ ...archive(0), provenance: undefined })).toBe(true);
    expect(isArchivePoint({ ...archive(0), bookmaker: "consensus" })).toBe(true);
    expect(isArchivePoint(live(START))).toBe(false);
    // the venue arm's provenance is not the archive's
    expect(isArchivePoint({ ...live(START), provenance: "venue_history" })).toBe(false);
    expect(isArchivePoint(null)).toBe(false);
  });
});

describe("archiveChartNote", () => {
  it("says nothing about a chart that draws no archive point", () => {
    expect(archiveChartNote(series(live(START), live(START + HOUR)), OPTS)).toBeNull();
    expect(archiveChartNote([], OPTS)).toBeNull();
  });

  it("names the span from the first interval's OPEN to the last close, hourly trades", () => {
    const note = archiveChartNote(series(...hours(72)), OPTS)!;
    expect(note.text).toBe(
      "From Mar 2 to Mar 5, this line is hourly trade prices recovered from Kalshi's records, not our own live price checks.",
    );
    expect(note.from).toBe(new Date(START).toISOString());
    expect(note.through).toBe(new Date(START + 72 * HOUR).toISOString());
    expect(note.points).toBe(72);
    expect(note.whole).toBe(true);
  });

  it("quote-only intervals say there were no trades", () => {
    const note = archiveChartNote(series(...hours(30, { price_basis: "quote_only" })), OPTS)!;
    expect(note.text).toContain("hourly quoted prices (no trades) recovered");
  });

  it("mixed bases and mixed periods are named without a cadence word", () => {
    const mixed = [
      archive(0),
      archive(1, { price_basis: "quote_only" }),
      archive(2, { period_minutes: 1 }),
    ];
    expect(archiveChartNote(series(...mixed), OPTS)!.text).toContain(
      "this line is trade and quoted prices recovered",
    );
  });

  it("minute intervals read minute-by-minute; an unknown basis reads plain prices", () => {
    const minutes = hours(3, { period_minutes: 1 });
    expect(archiveChartNote(series(...minutes), OPTS)!.text).toContain("minute-by-minute trade prices");
    const unknown = hours(3, { price_basis: "something_new" });
    expect(archiveChartNote(series(...unknown), OPTS)!.text).toContain("this line is hourly prices recovered");
  });

  it("a live point inside the span turns 'this line is' into 'some points are'", () => {
    const interleaved = [...hours(10), live(START + 4.5 * HOUR)];
    const note = archiveChartNote(series(...interleaved), OPTS)!;
    expect(note.whole).toBe(false);
    expect(note.text.startsWith("Some points on Mar 2 are hourly trade prices")).toBe(true);
    // a live point AFTER the span (the market's later captures) does not.
    const after = [...hours(10), live(START + 30 * HOUR)];
    expect(archiveChartNote(series(...after), OPTS)!.whole).toBe(true);
  });

  it("counts archive points across every drawn series", () => {
    const note = archiveChartNote(
      [{ history: hours(5) }, { history: [live(START + 90 * HOUR)] }, { history: hours(2) }],
      OPTS,
    )!;
    expect(note.points).toBe(7);
  });

  it("one day reads 'On'; a year other than the reader's is printed", () => {
    expect(archiveChartNote(series(...hours(6)), OPTS)!.text.startsWith("On Mar 2, this line is")).toBe(true);
    const lastYear = archiveChartNote(series(...hours(6)), { timeZone: "UTC", now: Date.UTC(2027, 0, 3) })!;
    expect(lastYear.text.startsWith("On Mar 2, 2026, this line is")).toBe(true);
  });

  it("skips null probabilities and unparseable stamps instead of throwing", () => {
    const junk = [
      archive(0, { probability: null }),
      archive(1, { timestamp: "not a date" }),
      archive(2, { interval_start: "garbage" }),
    ];
    const note = archiveChartNote(series(...junk), OPTS)!;
    expect(note.points).toBe(1);
    // a bad interval_start falls back to the close
    expect(note.from).toBe(new Date(START + 3 * HOUR).toISOString());
    expect(archiveChartNote(series(archive(0, { probability: null })), OPTS)).toBeNull();
  });

  it("never prints a raw field string", () => {
    const all = [
      ...hours(3),
      archive(4, { price_basis: "quote_only" }),
      archive(5, { period_minutes: 1 }),
    ];
    const text = archiveChartNote(series(...all), OPTS)!.text;
    for (const raw of ["kalshi_archive", "traded_interval", "quote_only", "period_minutes", "provenance"]) {
      expect(text).not.toContain(raw);
    }
  });
});

describe("archiveTooltipNote", () => {
  it("is null when no point under the cursor is an archive point", () => {
    expect(archiveTooltipNote([live(START), live(START)])).toBeNull();
    expect(archiveTooltipNote([])).toBeNull();
  });

  it("says From / Partly from, with the cadence, and no trades when every one is a quote", () => {
    expect(archiveTooltipNote([archive(0), archive(0)])).toBe("From Kalshi's hourly record");
    expect(archiveTooltipNote([archive(0), live(START)])).toBe("Partly from Kalshi's hourly record");
    expect(archiveTooltipNote([archive(0, { price_basis: "quote_only" })])).toBe(
      "From Kalshi's hourly record · no trades",
    );
    expect(archiveTooltipNote([archive(0), archive(0, { period_minutes: 1 })])).toBe("From Kalshi's record");
  });
});
