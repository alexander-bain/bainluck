/**
 * UX-P170 — THE WEATHER PAGE'S RAIN SECTION STOPS PRETENDING TO LOAD.
 *
 * ═══ WHAT THIS IS ═══
 *
 * `/weather` renders six sections. Five of them have data. The sixth — "Rain &
 * rainfall", which #2243 names as "the single most legible weather question a
 * normal person has" — was showing every visitor two broken cards:
 *
 *   LEFT  ("NYC · 7-day rain probability")
 *         `GET /api/weather/rain` returns `daily: []`. The component's guard was
 *         `daily?.length ? daily : null`, which collapses "still loading"
 *         (undefined) and "loaded, and there is nothing" ([]) into the same
 *         `null`. The 200 arrives, the list is empty, and the card renders a
 *         pulsing seven-column SKELETON — forever. Gotcha #53: an empty 200 is
 *         not an absence, it is a response shape.
 *
 *   RIGHT ("August rainfall")
 *         Three separate untruths in one card. The subtitle and the footer both
 *         hardcoded "10 cities" while ONE row rendered. The heading came from
 *         `new Date().getMonth()` — the reader's clock — while the only market
 *         that survives the freshness gate is `Rain in NYC in Nov 2026?`. And
 *         every surviving row is at 0%, so `maxMonthly` was 0 and the bar width
 *         computed `Math.max(4, 0/0)` = `NaN`, emitting `width: "NaN%"`, which
 *         the browser drops on the floor without a word.
 *
 * ═══ THE READER COUNT ═══
 *
 * 100% of loads, every load. Not a sampled or conditional path: `daily` has been
 * empty since the last NYC daily market resolved on 2026-07-22, and the payload
 * was re-pulled three times on 2026-08-29 with an identical reading each time.
 *
 * ═══ WHAT IS *NOT* FIXED HERE, DELIBERATELY ═══
 *
 * The emptiness itself is upstream. All 147 `Will it rain in NYC on%` markets
 * have resolved and 13 of the 14 open monthly markets are past the 7-day
 * freshness gate. That is a capture-side defect and is routed, not fixed. This
 * change makes the page HONEST about what it has — it does not conjure data.
 *
 * ═══ WHAT EVERY ROW HERE IS MADE OF ═══
 *
 * Every assertion below renders the SHIPPED `RainForecast` component, and the
 * empty payload is the verbatim `GET /api/weather/rain` body captured before a
 * line of the fix was written (`backend/tests/fixtures/uxp170_weather_rain.json`).
 * Nothing is drawn by hand and there is no source-level arm — a guard that reads
 * the file stays green when someone deletes the call site.
 *
 *   TZ=UTC npx jest --testPathPatterns=weatherRainHonestyCapture
 */

import React from "react";
import { renderToStaticMarkup } from "react-dom/server";
import fs from "node:fs";
import path from "node:path";
import { nycToday } from "@/components/weather/data";

const FRONTEND = path.join(__dirname, "..", "..");
const REPO = path.join(FRONTEND, "..");
const FIXTURE = path.join(
  REPO,
  "backend",
  "tests",
  "fixtures",
  "uxp170_weather_rain.json",
);

/* ── The banked production BEFORE ─────────────────────────────────────── */

type RainPayload = {
  daily: unknown[];
  monthly: { city: string; period?: string | null; prob: number; src: string; delta24h?: number }[];
};

const banked = JSON.parse(fs.readFileSync(FIXTURE, "utf8"));
const SERVED_BEFORE: RainPayload = banked.served_before;

/* ── SWR is the only thing between the component and its payload ──────── */

let swrPayload: unknown;
let swrError: unknown;

jest.mock("swr", () => ({
  __esModule: true,
  default: () => ({ data: swrPayload, error: swrError }),
}));

// eslint-disable-next-line @typescript-eslint/no-var-requires
const RainForecast = require("@/components/weather/RainForecast").default;

function render(payload: unknown, error: unknown = undefined): string {
  swrPayload = payload;
  swrError = error;
  return renderToStaticMarkup(React.createElement(RainForecast));
}

/** Strip tags so assertions read what a PERSON reads, not what React emitted. */
function visibleText(markup: string): string {
  return markup
    .replace(/<[^>]*>/g, " ")
    .replace(/&ldquo;|&rdquo;/g, '"')
    .replace(/&middot;/g, "·")
    .replace(/&#x27;|&apos;/g, "'")
    .replace(/&amp;/g, "&")
    .replace(/\s+/g, " ")
    .trim();
}

const SKELETON = "animate-pulse";

/* ═══════════════════════════════════════════════════════════════════════ */

describe("UX-P170 · the banked BEFORE is genuinely the broken state", () => {
  test("the fixture really is empty-daily and one-row-monthly", () => {
    expect(SERVED_BEFORE.daily).toEqual([]);
    expect(SERVED_BEFORE.monthly).toHaveLength(1);
    expect(SERVED_BEFORE.monthly[0].city).toBe("NYC");
    expect(SERVED_BEFORE.monthly[0].prob).toBe(0);
  });

  test("the population census is banked alongside it", () => {
    expect(banked._daily_population.rows).toBe(147);
    expect(banked._daily_population.all_status).toBe("resolved");
    expect(banked._monthly_population.open_rows).toBe(14);
    expect(banked._monthly_population.fresh_rows).toBe(1);
  });
});

describe("UX-P170 · loading and loaded-empty stop being the same thing", () => {
  test("STILL LOADING (undefined) keeps the skeletons — that part was right", () => {
    const markup = render(undefined);
    expect(markup).toContain(SKELETON);
    expect(visibleText(markup)).not.toContain("No live rain markets right now");
  });

  test("LOADED-AND-EMPTY renders no skeleton anywhere", () => {
    const markup = render(SERVED_BEFORE);
    // The left card is empty in the banked payload; the right card has a row.
    // Neither may pulse.
    expect(markup).not.toContain(SKELETON);
  });

  test("the left card says what is happening instead of pulsing", () => {
    const text = visibleText(render(SERVED_BEFORE));
    expect(text).toContain("No live rain markets right now");
    // UX-P219: the second line still has to be THERE — that is what this row
    // has always been about — but it no longer promises a refill. The sentence
    // it used to pin, "…appear here when they reopen", broke ruling 142 and was
    // the whole of `app/weather`'s entry in the copy-ban debt list. Its
    // replacement, and the other three cards that said the same thing, are
    // guarded per-card in `weatherEmptyStatesStateWhatTheyAre.test.tsx`.
    // Smart quotes, not `"`: this file's `visibleText` replaces the `&ldquo;`
    // ENTITY, but `renderToStaticMarkup` has already resolved it to the
    // character by then, so the replacement never fires. Asserting the
    // character is asserting what the reader is served.
    expect(text).toContain("This card tracks daily “will it rain?” questions.");
    expect(text).not.toContain("appear here");
  });

  test("a fully empty payload gives BOTH cards an honest state", () => {
    const text = visibleText(render({ daily: [], monthly: [] }));
    expect(text).toContain("No live rain markets right now");
    expect(text).toContain("No live rainfall markets right now");
    expect(render({ daily: [], monthly: [] })).not.toContain(SKELETON);
  });

  test("a real fetch error still reads as an error, not as emptiness", () => {
    const text = visibleText(render(undefined, new Error("boom")));
    expect(text).toContain("Failed to load rain data");
    expect(text).toContain("Failed to load monthly data");
    expect(text).not.toContain("No live rain markets right now");
  });
});

describe("UX-P170 · the card stops claiming cities it does not have", () => {
  test("BEFORE's one row is no longer described as ten cities", () => {
    const text = visibleText(render(SERVED_BEFORE));
    expect(text).not.toContain("10 cities");
    expect(text).toContain("1 city");
  });

  test("the count is the real count, and it is plural when it should be", () => {
    const many = {
      daily: [],
      monthly: [
        { city: "NYC", period: "Aug 2026", prob: 61, src: "kalshi" },
        { city: "Miami", period: "Aug 2026", prob: 44, src: "kalshi" },
        { city: "Denver", period: "Aug 2026", prob: 12, src: "kalshi" },
      ],
    };
    const text = visibleText(render(many));
    expect(text).toContain("3 cities");
    expect(text).not.toContain("3 city");
    expect(text).not.toContain("10 cities");
  });

  test("the footer agrees with the subtitle rather than contradicting it", () => {
    const text = visibleText(render(SERVED_BEFORE));
    expect(text).toContain("Kalshi · 1 city");
    // One card, one number: the two must not disagree.
    expect(text.match(/1 city/g)).toHaveLength(2);
  });

  test("no count is claimed before the count is known", () => {
    const text = visibleText(render(undefined));
    expect(text).not.toMatch(/\d+ (city|cities)/);
  });
});

describe("UX-P170 · the month is read off the market, not off the clock", () => {
  test("the heading no longer asserts the reader's current month", () => {
    const text = visibleText(render(SERVED_BEFORE));
    expect(text).toContain("Monthly rainfall");
    const monthNames = [
      "January", "February", "March", "April", "May", "June",
      "July", "August", "September", "October", "November", "December",
    ];
    for (const m of monthNames) {
      expect(text).not.toContain(`${m} rainfall`);
    }
  });

  test("the row prints the period the market actually resolves for", () => {
    const november = {
      daily: [],
      monthly: [{ city: "NYC", period: "Nov 2026", prob: 0, src: "kalshi", delta24h: 0 }],
    };
    const text = visibleText(render(november));
    expect(text).toContain("NYC");
    expect(text).toContain("Nov 2026");
  });

  test("a row with no parseable period degrades to the city alone, not to 'null'", () => {
    const noPeriod = {
      daily: [],
      monthly: [{ city: "NYC", period: null, prob: 30, src: "kalshi" }],
    };
    const text = visibleText(render(noPeriod));
    expect(text).toContain("NYC");
    expect(text).not.toContain("null");
    expect(text).not.toContain("undefined");
  });
});

describe("UX-P170 · an all-zero field no longer emits an invalid bar width", () => {
  test("BEFORE's single 0% row does not produce NaN%", () => {
    const markup = render(SERVED_BEFORE);
    expect(markup).not.toContain("NaN");
  });

  test("every rendered bar width is a finite percentage", () => {
    const allZero = {
      daily: [],
      monthly: [
        { city: "NYC", period: "Nov 2026", prob: 0, src: "kalshi" },
        { city: "Miami", period: "Aug 2026", prob: 0, src: "kalshi" },
      ],
    };
    const markup = render(allZero);
    expect(markup).not.toContain("NaN");
    // Percentage widths only — SourceBadge's dot is a fixed `6px` and is not a
    // bar. A broken bar would still be caught here: `NaN%` ends in `%`.
    const widths = [...markup.matchAll(/width:\s*([^;"]+%)/g)].map((m) => m[1].trim());
    expect(widths.length).toBeGreaterThan(0);
    for (const w of widths) {
      expect(w).toMatch(/^[\d.]+%$/);
      expect(Number.isFinite(parseFloat(w))).toBe(true);
    }
  });

  test("a healthy field still scales the bars against its own maximum", () => {
    const healthy = {
      daily: [],
      monthly: [
        { city: "NYC", period: "Aug 2026", prob: 80, src: "kalshi" },
        { city: "Denver", period: "Aug 2026", prob: 40, src: "kalshi" },
      ],
    };
    const markup = render(healthy);
    // 80 is the max → 100%; 40 is half of it → 50%. The floor must not flatten it.
    expect(markup).toContain("width:100%");
    expect(markup).toContain("width:50%");
  });
});

describe("UX-P170 · the parts of the section that were fine stay fine", () => {
  test("a populated 7-day series still renders its seven days", () => {
    // ux/1078 (#3219): the rows carry `iso` and the first one is dated today.
    // This test asserts a populated series still paints, and it used to read
    // "Today" off row 0 by position — which is the bug that shipped, and which
    // made the card call tomorrow "Today" once today's market closed. A row
    // now earns the word by matching the date in New York, so the fixture has
    // to say which day it is rather than rely on being first.
    const week = {
      daily: [
        { day: "Mon", date: "Sep 1", iso: nycToday(), prob: 20, icon: "☁" },
        { day: "Tue", date: "Sep 2", iso: "2026-09-02", prob: 65, icon: "☂" },
      ],
      monthly: SERVED_BEFORE.monthly,
    };
    const text = visibleText(render(week));
    expect(text).toContain("Today");
    expect(text).toContain("Tue");
    expect(text).toContain("65%");
    expect(text).not.toContain("No live rain markets right now");
  });

  test("the section still identifies itself and its source", () => {
    const text = visibleText(render(SERVED_BEFORE));
    expect(text).toContain("Rain & rainfall");
    expect(text).toContain("NYC · 7-day rain probability");
    expect(text).toContain("Kalshi");
  });
});
