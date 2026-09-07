// #3710 — A COLUMN HEADED "7d" WAS DRAWING 29 DAYS.
//
// What the shopper saw, `/politics` -> "Presidential 2028" -> Rankings, desktop
// (the column is `hideOnMobile`, so this one is invisible on a phone): the
// sparkline column headed `7d trend` over a series spanning a month.
//
// Measured on production 2026-09-06 22:23Z, `/api/politics`
// `themes.presidential.candidates[].history`:
//
//     full-length rows      10 of 14, 51 points each
//     span                  2026-08-07T22:00Z -> 2026-09-06T20:51Z = 29 days
//     largest gap           9.2 days, AT THE END of the series
//     points inside 7d      2 of 51
//
// ── WHY THE FIX IS A RELABEL AND NOT A TRUNCATION ───────────────────────────
//
// The two obvious repairs are not equivalent, and the gap's POSITION is what
// decides between them. Because the 9.2-day hole sits at the end rather than
// the middle, honouring the label — clipping the series to 7 days — would
// reduce 10 of the 14 rows to a TWO-POINT line, i.e. delete the column's
// content to make a string true. The column's data is right; its header was
// never right. So the header moves.
//
// ── WHY THE HEADER IS DERIVED AND NOT JUST CORRECTED ────────────────────────
//
// Rewriting the literal to `30d trend` fixes today and re-arms the same bug:
// the string and the served window can drift apart again in silence, exactly
// as they already did. The header is therefore computed from the timestamps it
// sits above (`seriesWindowLabel`), so the claim cannot outlive the data — and
// the day the channel really does serve a week, the column says "7d" by
// itself.
//
// Note the "7d" was not invented from nothing: the ADJACENT column, `Δ 7d`, is
// a genuine 7-day figure (`change_7d`). Two neighbouring columns described two
// different windows and only one of them was telling the truth. That column is
// deliberately left alone here — this guard must not "helpfully" catch it.
//
//   npx jest --testPathPatterns=politicsTrendHeaderNamesItsWindow3710

import fs from "node:fs";
import path from "node:path";

import { seriesWindowLabel } from "@/lib/seriesFreshness";

const HOUR = 60 * 60 * 1000;
const DAY = 24 * HOUR;

/** `n` ISO stamps ending at `end`, one every `stepMs`. */
function series(n: number, stepMs: number, end = Date.parse("2026-09-06T20:51:00Z")) {
  return Array.from({ length: n }, (_, i) =>
    new Date(end - (n - 1 - i) * stepMs).toISOString(),
  );
}

/** `n` ISO stamps spread evenly across a REAL measured interval, inclusive. */
function seriesBetween(n: number, startIso: string, endIso: string) {
  const start = Date.parse(startIso);
  const step = (Date.parse(endIso) - start) / (n - 1);
  return Array.from({ length: n }, (_, i) => new Date(start + i * step).toISOString());
}

/* ═══ 1 · the label describes the data, at the measured shape ═══════════ */

describe("#3710 · seriesWindowLabel names the window actually drawn", () => {
  test("THE REGRESSION CASE: production's 29-day, 51-point series is not '7d'", () => {
    // The exact shape measured on the issue: 51 points spanning
    // 2026-08-07T22:00Z -> 2026-09-06T20:51Z, with the 9.2-day hole at the END
    // (45 points, then the gap, then the 6 that landed after it came back).
    const history = [
      ...seriesBetween(45, "2026-08-07T22:00:00Z", "2026-08-28T02:00:00Z"),
      ...seriesBetween(6, "2026-09-06T05:50:00Z", "2026-09-06T20:51:00Z"),
    ];

    const label = seriesWindowLabel([history]);
    expect(label).toBe("29d");
    expect(label).not.toBe("7d");
  });

  test("a hole does not shrink the window — the span is the outer edges", () => {
    // The 9.2-day hole is inside the window, not a reduction of it. A reader
    // scanning the column is shown 29 days of x-axis whatever is missing from
    // the middle, and #2961's note (not this header) is what discloses the hole.
    const holed = [
      ...series(20, 8 * HOUR, Date.parse("2026-08-28T02:00:00Z")),
      ...series(2, 8 * HOUR, Date.parse("2026-09-06T05:50:00Z")),
    ];
    expect(seriesWindowLabel([holed])).toBe("15d");
  });

  test("the column speaks for its WIDEST row, not its first", () => {
    // The header labels a column of independent series. `/politics` serves
    // J.D. Vance and Ted Cruz at n=3 beside n=51 neighbours, so a header taken
    // from row 1 would understate what rows below it draw.
    const short = series(3, 8 * HOUR);
    const long = series(51, 8 * HOUR);
    expect(seriesWindowLabel([short, long])).toBe(seriesWindowLabel([long]));
    expect(seriesWindowLabel([short, long])).not.toBe(seriesWindowLabel([short]));
  });

  test("it would say '7d' if the channel ever served a week", () => {
    // The point of deriving it: the string that was wrong is a reachable,
    // correct output — not a value the fix has legislated against.
    expect(seriesWindowLabel([series(22, 8 * HOUR)])).toBe("7d");
  });
});

/* ═══ 2 · it never overstates, and never guesses ════════════════════════ */

describe("#3710 · the label rounds DOWN and stays silent when it cannot know", () => {
  test("29.9 days is '29d', never '30d'", () => {
    // The whole function exists to stop a header claiming more than it holds,
    // so the rounding direction is load-bearing rather than cosmetic.
    const end = Date.parse("2026-09-06T20:51:00Z");
    const nearly30 = [new Date(end - 29.9 * DAY).toISOString(), new Date(end).toISOString()];
    expect(seriesWindowLabel([nearly30])).toBe("29d");
  });

  test("undatable, empty and single-point columns yield null, not a zero", () => {
    // gotcha #53 on a render path: absence is a response shape, not a window.
    // "0m" is technically true of a one-point column and useless as a heading,
    // so the caller is told it cannot label this rather than handed a number.
    expect(seriesWindowLabel([])).toBeNull();
    expect(seriesWindowLabel([[], null, undefined])).toBeNull();
    expect(seriesWindowLabel([["not a date", "", null]])).toBeNull();
    expect(seriesWindowLabel([["2026-09-06T20:51:00Z"]])).toBeNull();
  });

  test("junk beside real stamps is skipped, not allowed to poison the span", () => {
    // `asInstant` rejects NaN, so an unparseable entry must not read as epoch 0
    // and turn a 3-day column into a 56-year one.
    const mixed = [...series(4, DAY), "garbage", null];
    expect(seriesWindowLabel([mixed])).toBe("3d");
  });

  test("sub-day and sub-hour columns get honest compact units", () => {
    expect(seriesWindowLabel([series(2, 6 * HOUR)])).toBe("6h");
    expect(seriesWindowLabel([series(2, 20 * 60 * 1000)])).toBe("20m");
  });

  test("order does not matter — the payload is not assumed sorted", () => {
    const forward = series(5, DAY);
    expect(seriesWindowLabel([[...forward].reverse()])).toBe(seriesWindowLabel([forward]));
  });

  test("it is clock-free: a window is a span, not an age", () => {
    // Unlike its neighbours in this module, nothing here may consult `now` —
    // the header must not change because the page was left open, and an old
    // column still spanned what it spanned.
    const old = series(5, DAY, Date.parse("2024-01-01T00:00:00Z"));
    expect(seriesWindowLabel([old])).toBe("4d");
  });
});

/* ═══ 3 · the page actually uses it ═════════════════════════════════════ */

const PAGE = fs.readFileSync(
  path.join(__dirname, "..", "app", "politics", "page.tsx"),
  "utf8",
);

/**
 * The spark column's header cell.
 *
 * Located via `CandidateSpark`'s own header — the one `hideOnMobile` heading
 * that is not the Δ column. Asserted found before anything is asserted about
 * it: a source guard that quietly matches nothing is worse than no guard.
 */
const TREND_HEADER = (() => {
  const match = PAGE.match(/<span className=\{s\.hideOnMobile\}[^>]*>\s*\{?([^<]*?)\}?\s*<\/span>/g);
  if (!match) {
    throw new Error(
      "#3710 guard found no hideOnMobile header cells in app/politics/page.tsx. " +
        "If the header was restructured, re-point this guard — do not delete it.",
    );
  }
  const trend = match.find((m) => m.includes("trend") || m.includes("trendWindow"));
  if (!trend) {
    throw new Error(
      "#3710 guard found no trend-column header among the hideOnMobile cells. " +
        `Saw: ${match.join(" | ")}`,
    );
  }
  return trend;
})();

describe("#3710 · the rendered header is derived, not written down", () => {
  test("THE REGRESSION ASSERTION: the trend header carries no hardcoded window", () => {
    // This is the literal that was wrong for the column's whole life. Any
    // `<n>d` / `<n>h` spelled into the heading is the same bug re-armed,
    // because a constant cannot track a window that moves.
    expect(TREND_HEADER).not.toMatch(/\b\d+\s*[dh]\b/);
    expect(TREND_HEADER).toContain("trendWindow");
  });

  test("the header falls back to a bare noun rather than a guessed window", () => {
    // `seriesWindowLabel` returns null for an undatable column; the header must
    // then say "Trend" and claim nothing, never default to a number.
    expect(TREND_HEADER).toMatch(/"Trend"/);
  });

  test("the window is computed from the SAME histories the sparks draw", () => {
    // The failure this forbids is a header derived from one source while the
    // column is drawn from another — a fresh way to be confidently wrong.
    expect(PAGE).toMatch(
      /seriesWindowLabel\(\s*sorted\.map\(\(c\) => \(c\.history \?\? \[\]\)\.map\(\(h\) => h\.t\)\)\s*\)/,
    );
    expect(PAGE).toMatch(/<CandidateSpark history=\{c\.history\} \/>/);
  });

  test("the ADJACENT 'Δ 7d' column keeps its literal — it is a real 7-day figure", () => {
    // Scope pin, and the reason this fix is not a search-and-replace: the delta
    // column is served by `change_7d` and genuinely covers a week. Deriving its
    // header from the spark's window would make the honest column lie.
    expect(PAGE).toContain("Δ 7d");
    expect(PAGE).toMatch(/<MoveChip change=\{c\.change_7d\} \/>/);
  });
});
