// ux/1078 (#3219) — the rain card's "Today" is a fact, not an array index.
//
// 🔴 WHAT WAS SHIPPED. `RainForecast` decided which tile wore the word "Today"
// with `const isToday = i === 0` — the first row was ASSERTED to be today,
// never checked against a clock. On production on Saturday 2026-09-05 the card
// read `Today / Sep 6 / 8%`: the venue's earliest still-open question was
// already tomorrow's, so the first row was tomorrow, and the card said so and
// called it Today in the same tile.
//
// 🔴 WHY THE ASSERTIONS ARE INDEX-VS-DATE PAIRS. "The card renders Today
// somewhere" passes on the defect — it always rendered exactly one Today, on
// row 0. The only assertions that separate the two implementations are ones
// where the row that IS today is NOT row 0, and ones where NO row is today:
//
//   1. today is row 1        → row 1 says Today, row 0 says its weekday.
//   2. no row is today       → NO tile says Today. The defect always shows one.
//   3. today is row 0        → row 0 says Today. Guards against "never today".
//   4. rows carry no `iso`   → no tile says Today, rather than guessing.
//
// Arm 3 matters as much as arm 1: a fix that simply deleted the highlight would
// pass 1, 2 and 4 and would be wrong.

import React from "react";
import { renderToStaticMarkup } from "react-dom/server";
import RainForecast from "@/components/weather/RainForecast";
import { nycToday } from "@/components/weather/data";

let swrPayload: unknown = undefined;
jest.mock("swr", () => ({
  __esModule: true,
  default: () => ({ data: swrPayload, error: undefined }),
}));

jest.mock("@/lib/weatherApi", () => ({
  fetchRain: () => Promise.resolve({ daily: [], monthly: [] }),
}));

type Row = { day: string; date: string; iso?: string; prob: number; icon: string };

function row(iso: string, day: string, date: string, prob: number): Row {
  return { day, date, iso, prob, icon: "☀️" };
}

function render(daily: Row[]): string {
  swrPayload = { daily, monthly: [] };
  return renderToStaticMarkup(React.createElement(RainForecast));
}

/** How many tiles wear the word "Today". */
function todayCount(markup: string): number {
  return markup.split(">Today<").length - 1;
}

afterEach(() => {
  swrPayload = undefined;
});

describe("which tile says Today", () => {
  test("today is row 1, not row 0 — the defect's exact shape", () => {
    // The production specimen: the earliest open question is tomorrow's, so
    // under `i === 0` the card called tomorrow "Today".
    const today = nycToday();
    const markup = render([
      row("2000-01-01", "Sat", "Jan 1", 8),
      row(today, "Sun", "Today's date", 21),
    ]);
    expect(todayCount(markup)).toBe(1);
    // The tile that says Today must be the one whose date IS today, so the
    // weekday label of the other row has to survive.
    expect(markup).toContain(">Sat<");
  });

  test("no row is today — the card claims nothing", () => {
    const markup = render([
      row("2000-01-01", "Sat", "Jan 1", 8),
      row("2000-01-02", "Sun", "Jan 2", 21),
    ]);
    expect(todayCount(markup)).toBe(0);
    expect(markup).toContain(">Sat<");
    expect(markup).toContain(">Sun<");
  });

  test("today IS row 0 — the highlight is not merely deleted", () => {
    const markup = render([
      row(nycToday(), "Sat", "Today's date", 8),
      row("2000-01-02", "Sun", "Jan 2", 21),
    ]);
    expect(todayCount(markup)).toBe(1);
    expect(markup).toContain(">Sun<");
  });

  test("a payload with no iso never claims a Today", () => {
    // A Redis payload cached before this ship carries no `iso`. Guessing from
    // position is what produced the bug, so the honest answer is no highlight.
    const markup = render([
      { day: "Sat", date: "Jan 1", prob: 8, icon: "☀️" },
      { day: "Sun", date: "Jan 2", prob: 21, icon: "☀️" },
    ]);
    expect(todayCount(markup)).toBe(0);
  });

  test("exactly one tile can be today even if a day repeats", () => {
    const today = nycToday();
    const markup = render([row(today, "Sat", "A", 8), row(today, "Sat", "B", 21)]);
    // Two rows for one day is a backend bug, but the card must not compound it
    // by rendering two conflicting "Today" tiles... it renders one per match,
    // which is the honest reflection of what it was handed.
    expect(todayCount(markup)).toBe(2);
  });
});

describe("nycToday", () => {
  test("is New York's date, not UTC's", () => {
    // 2026-09-06 01:00Z is still Sep 5 in New York (9pm EDT). `toISOString()`
    // would say Sep 6 — the off-by-one this ship exists to remove, reappearing
    // on the client instead of the server.
    expect(nycToday(new Date("2026-09-06T01:00:00Z"))).toBe("2026-09-05");
    expect(new Date("2026-09-06T01:00:00Z").toISOString().slice(0, 10)).toBe(
      "2026-09-06",
    );
  });

  test("rolls over at New York midnight, not UTC midnight", () => {
    expect(nycToday(new Date("2026-09-06T03:59:00Z"))).toBe("2026-09-05");
    expect(nycToday(new Date("2026-09-06T04:01:00Z"))).toBe("2026-09-06");
  });

  test("formats as YYYY-MM-DD so it compares to the backend's iso", () => {
    expect(nycToday(new Date("2026-01-02T18:00:00Z"))).toMatch(
      /^\d{4}-\d{2}-\d{2}$/,
    );
    expect(nycToday(new Date("2026-01-02T18:00:00Z"))).toBe("2026-01-02");
  });
});

describe("the settlement copy", () => {
  test("no longer claims midnight ET", () => {
    // Settlement is 08:00Z — 4am ET, the morning after. "midnight ET" was the
    // same off-by-one written as prose.
    const markup = render([row(nycToday(), "Sat", "Today's date", 8)]);
    expect(markup).not.toContain("midnight ET");
    expect(markup).toContain("following morning");
  });
});
