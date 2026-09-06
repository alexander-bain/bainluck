/**
 * UX-P179 — THE GOLF PAGE STOPS ENDING THE TOUR CHAMPIONSHIP A DAY EARLY.
 *
 * ═══ WHAT THIS IS ═══
 *
 * `/api/golf` serves schedule dates as CALENDAR DATES stamped at midnight UTC.
 * Measured on the banked payload: **94 of 94** `pga_schedule` start/end pairs
 * and **3 of 3** tournament start/end pairs are exactly `T00:00:00+00:00`.
 * Nothing in that population is a time of day — a golf tournament runs Thursday
 * to Sunday, and Thursday is what the field says.
 *
 * Three of the four surfaces that print those values already knew that:
 *
 *   components/golf/UpcomingTournaments.tsx   `utcPart` → `timeZone: "UTC"`
 *   components/TournamentCard.tsx             `getUTCMonth()` / `getUTCDate()`
 *   app/categories/golf/tournaments/[slug]/   `timeZone: "UTC"`, three places
 *
 * The fourth — the banner at the top of `/categories/golf`, the first thing the
 * page says — called `toLocaleDateString` four times with no `timeZone` at all.
 * So for every reader west of Greenwich it moved each date back a day:
 *
 *   BEFORE (America/Los_Angeles)   🏌️ This Week · Aug 26 – Sat, Aug 29
 *   AFTER  (every zone)            🏌️ This Week · Aug 27 – Sun, Aug 30
 *
 * The Tour Championship 2026 runs Thu Aug 27 – Sun Aug 30. The banner told a US
 * reader it ended on the Saturday, one click above a tournament page that said
 * Sunday, and one scroll above a card in the same list that said Aug 27–30. The
 * page contradicted itself twice about the same three values.
 *
 * ═══ THE READER COUNT ═══
 *
 * 100% of loads of `/categories/golf` west of Greenwich, whenever there is a
 * current event — the banner is the first block under the header and is not
 * conditional on scroll. It is deterministic: every date in the population is
 * midnight UTC, so every date shifts, every time. `GET /api/golf` was read
 * 2026-08-29 and banked verbatim at `__tests__/fixtures/uxp179_golf_before.json`.
 *
 * ═══ WHY THE GUARDS LOOK LIKE THIS ═══
 *
 * CI runs jest under `TZ=UTC`, where a missing `timeZone` is invisible: the
 * un-pinned and the pinned component render the same bytes. UX-P178 hit this and
 * caught its regression only in the mutation harness, by re-running the suite
 * under `TZ=America/Los_Angeles`. That still happens here (14 mutations, both
 * zones) — but this file adds a guard that is TIMEZONE-INDEPENDENT, so the CI
 * gate itself goes red if the pin is ever removed: it drives the real render and
 * records the OPTIONS OBJECT of every `toLocaleDateString` call the component
 * actually makes. `assertTheSpyCanTellThemApart` proves the instrument works by
 * running the legacy component through it and watching it fail.
 *
 *   cd frontend && TZ=UTC npx jest --testPathPatterns=golfCurrentEventDateCapture
 *   cd frontend && TZ=America/Los_Angeles npx jest --testPathPatterns=golfCurrentEventDateCapture
 */

import React from "react";
import { renderToStaticMarkup } from "react-dom/server";
import fs from "node:fs";
import path from "node:path";

jest.mock("next/navigation", () => ({
  __esModule: true,
  useRouter: () => ({ push: jest.fn(), replace: jest.fn(), prefetch: jest.fn() }),
}));
jest.mock("next/link", () => ({
  __esModule: true,
  default: ({ href, children }: { href: string; children: React.ReactNode }) => (
    <a href={href}>{children}</a>
  ),
}));

import CurrentEventBanner from "@/components/golf/CurrentEventBanner";
import TournamentCard from "@/components/TournamentCard";
import { formatDateRange } from "@/components/golf/UpcomingTournaments";
import type {
  GolfCurrentEvent,
  GolfResponse,
  GolfTournament,
} from "@/lib/types";

// eslint-disable-next-line @typescript-eslint/no-var-requires
const CurrentEventBannerLegacy =
  require("../fixtures/uxp179GolfCurrentEventBannerLegacy").default;

import golfBefore from "../fixtures/uxp179_golf_before.json";

const SERVED = golfBefore as unknown as GolfResponse;
const CURRENT = SERVED.current_event as GolfCurrentEvent;

/** Mid-tournament: Saturday afternoon UTC, inside Aug 27 → Aug 30. */
const DURING = new Date("2026-08-29T20:39:00Z");
/** Two days before the Tour Championship's Thursday start. */
const BEFORE_START = new Date("2026-08-25T12:00:00Z");
/** After the last day has fully elapsed. */
const AFTER_END = new Date("2026-09-02T12:00:00Z");

function at(now: Date, fn: () => string): string {
  jest.useFakeTimers({ now });
  try {
    return fn();
  } finally {
    jest.useRealTimers();
  }
}

function render(
  Component: unknown,
  event: GolfCurrentEvent,
): string {
  return renderToStaticMarkup(
    React.createElement(Component as React.FC, {
      event,
      historyData: null,
    } as never),
  );
}

function visibleText(markup: string): string {
  return markup
    .replace(/<[^>]*>/g, " ")
    .replace(/&middot;/g, "·")
    .replace(/&#x27;|&apos;/g, "'")
    .replace(/&amp;/g, "&")
    .replace(/\s+/g, " ")
    .trim();
}

/**
 * Record the options object of every `toLocaleDateString` the render performs.
 *
 * This is the timezone-independent half. A rendered-output assertion cannot see
 * a missing `timeZone` under `TZ=UTC`; a call-level one can, in every zone.
 * It is not a source grep — nothing here reads a file. It drives the shipped
 * component and inspects the calls that component really made, so it also goes
 * red if someone deletes the date from the banner entirely (zero calls).
 */
function dateFormatOptions(fn: () => unknown): Array<Intl.DateTimeFormatOptions | undefined> {
  const seen: Array<Intl.DateTimeFormatOptions | undefined> = [];
  const original = Date.prototype.toLocaleDateString;
  Date.prototype.toLocaleDateString = function (
    this: Date,
    locales?: string | string[],
    options?: Intl.DateTimeFormatOptions,
  ): string {
    seen.push(options);
    return original.call(this, locales, options);
  };
  try {
    fn();
  } finally {
    Date.prototype.toLocaleDateString = original;
  }
  return seen;
}

/* ═══════════════════════════════════════════════════════════════════════ */

describe("UX-P179 · the banked payload really is a population of calendar dates", () => {
  it("every pga_schedule date is midnight UTC — 94 of 94, both ends", () => {
    const schedule = SERVED.pga_schedule ?? [];
    expect(schedule).toHaveLength(94);
    const stamps = schedule.flatMap((e) => [e.start_date, e.end_date]);
    expect(stamps).toHaveLength(188);
    expect(stamps.every((s) => typeof s === "string")).toBe(true);
    expect(
      stamps.filter((s) => (s as string).endsWith("T00:00:00+00:00")),
    ).toHaveLength(188);
  });

  it("every tournament that carries a schedule window carries it the same way", () => {
    const windows = SERVED.tournaments
      .filter((t) => t.start_date && t.end_date)
      .flatMap((t) => [t.start_date as string, t.end_date as string]);
    // Three of the seven tournaments have a window; the other four are
    // long-horizon futures with a resolution date and no schedule.
    expect(windows).toHaveLength(6);
    expect(windows.every((s) => s.endsWith("T00:00:00+00:00"))).toBe(true);
  });

  it("the current event is the Tour Championship, Thu Aug 27 to Sun Aug 30", () => {
    expect(CURRENT.name).toBe("Tour Championship");
    expect(CURRENT.start_date).toBe("2026-08-27T00:00:00+00:00");
    expect(CURRENT.end_date).toBe("2026-08-30T00:00:00+00:00");
    // The weekday claim above is what the reader is told, so pin it.
    expect(new Date(CURRENT.start_date as string).getUTCDay()).toBe(4); // Thursday
    expect(new Date(CURRENT.end_date as string).getUTCDay()).toBe(0); // Sunday
  });
});

describe("UX-P179 · the banner prints the day the data states, in every zone", () => {
  /**
   * ⚠️ These are FIXED LITERALS, not a zone swap — jest has already warmed V8's
   * zone cache by the time a test body runs, so an in-process `process.env.TZ`
   * assignment proves nothing. The mutation harness runs this whole file under
   * both `TZ=UTC` and `TZ=America/Los_Angeles`; under the un-pinned banner the
   * Los Angeles run rendered "Aug 26 – Sat, Aug 29" and went red on the first.
   */
  it("mid-tournament, the window reads Aug 27 – Sun, Aug 30", () => {
    const text = at(DURING, () => visibleText(render(CurrentEventBanner, CURRENT)));
    expect(text).toContain("This Week");
    expect(text).toContain("Aug 27 – Sun, Aug 30");
    expect(text).not.toContain("Aug 26");
    expect(text).not.toContain("Sat, Aug 29");
  });

  it("before it starts, the same window reads Aug 27 – Aug 30", () => {
    const text = at(BEFORE_START, () =>
      visibleText(render(CurrentEventBanner, CURRENT)),
    );
    expect(text).toContain("This Week");
    expect(text).toContain("Aug 27 – Aug 30");
    expect(text).not.toContain("Aug 26");
  });

  it("a resolution-date-only event inside a week reads its own day", () => {
    const resolutionOnly: GolfCurrentEvent = {
      ...CURRENT,
      start_date: null,
      end_date: null,
      resolution_date: "2026-09-06T00:00:00+00:00",
      top_golfers: [],
    };
    const text = at(new Date("2026-09-01T12:00:00Z"), () =>
      visibleText(render(CurrentEventBanner, resolutionOnly)),
    );
    expect(text).toContain("Ends Sun, Sep 6");
    expect(text).not.toContain("Sep 5");
  });

  it("a resolution-date-only event further out reads its own day too", () => {
    const resolutionOnly: GolfCurrentEvent = {
      ...CURRENT,
      start_date: null,
      end_date: null,
      resolution_date: "2026-10-04T00:00:00+00:00",
      top_golfers: [],
    };
    const text = at(new Date("2026-09-01T12:00:00Z"), () =>
      visibleText(render(CurrentEventBanner, resolutionOnly)),
    );
    expect(text).toContain("Oct 4");
    expect(text).not.toContain("Oct 3");
  });
});

describe("UX-P179 · a calendar date is a DAY when it is compared, not just printed", () => {
  /**
   * The second symptom of the same root. `end_date` is the tournament's last
   * DAY, stamped at midnight UTC. Comparing `now` against that raw instant
   * retired the tournament at the START of its final day — measured on the
   * shipped payload, the banner read "🏌️ Just Finished" from
   * 2026-08-30T00:01:00Z, i.e. 5:01pm PT on the SATURDAY, and kept saying it for
   * the whole of Sunday's final round, with the date dropped entirely.
   *
   * These are absolute instants, so they assert identically in every zone.
   */
  const cases: Array<[string, string]> = [
    ["2026-08-27T00:00:00Z", "This Week"], // the Thursday, the moment it opens
    ["2026-08-29T20:39:00Z", "This Week"], // Saturday afternoon
    ["2026-08-30T00:01:00Z", "This Week"], // ⚠️ read "Just Finished" before
    ["2026-08-30T12:00:00Z", "This Week"], // ⚠️ Sunday, the final round
    ["2026-08-30T23:59:00Z", "This Week"], // ⚠️ the last minute of the last day
    ["2026-08-31T00:00:00Z", "Just Finished"], // the day after — over
    ["2026-09-02T12:00:00Z", "Just Finished"],
  ];

  for (const [now, expected] of cases) {
    it(`at ${now} the banner says "${expected}"`, () => {
      const text = at(new Date(now), () =>
        visibleText(render(CurrentEventBanner, CURRENT)),
      );
      expect(text).toContain(expected);
    });
  }

  it("the window opens ON the start day, not the day before", () => {
    // The pre-start branch prints the bare range; the in-window branch adds the
    // weekday. So the SHAPE of the label is what says which branch ran, and it
    // is the only thing that can catch a boundary that opens early.
    const eve = at(new Date("2026-08-26T12:00:00Z"), () =>
      visibleText(render(CurrentEventBanner, CURRENT)),
    );
    expect(eve).toContain("Aug 27 – Aug 30");
    expect(eve).not.toContain("Sun, Aug 30");

    const opened = at(new Date("2026-08-27T00:00:00Z"), () =>
      visibleText(render(CurrentEventBanner, CURRENT)),
    );
    expect(opened).toContain("Aug 27 – Sun, Aug 30");
  });

  it("the window keeps printing its dates through the whole final day", () => {
    // "Just Finished" also drops the date, so the regression removed the days
    // as well as mislabelling the status.
    const text = at(new Date("2026-08-30T12:00:00Z"), () =>
      visibleText(render(CurrentEventBanner, CURRENT)),
    );
    expect(text).toContain("Aug 27 – Sun, Aug 30");
  });

  it("the legacy component really did retire it a day early", () => {
    // The instrument, shown failing. Without this the case above is a claim.
    const text = at(new Date("2026-08-30T12:00:00Z"), () =>
      visibleText(render(CurrentEventBannerLegacy, CURRENT)),
    );
    expect(text).toContain("Just Finished");
    expect(text).not.toContain("Aug 30");
  });

  it("a one-day event is live for its own day and no longer", () => {
    const oneDay: GolfCurrentEvent = {
      ...CURRENT,
      start_date: "2026-09-05T00:00:00+00:00",
      end_date: "2026-09-05T00:00:00+00:00",
    };
    expect(
      at(new Date("2026-09-05T18:00:00Z"), () =>
        visibleText(render(CurrentEventBanner, oneDay)),
      ),
    ).toContain("This Week");
    expect(
      at(new Date("2026-09-06T00:00:00Z"), () =>
        visibleText(render(CurrentEventBanner, oneDay)),
      ),
    ).toContain("Just Finished");
  });
});

describe("UX-P179 · the pin is asserted at the CALL, so TZ=UTC can see it too", () => {
  it("every date the banner formats is pinned to UTC", () => {
    const options = dateFormatOptions(() =>
      at(DURING, () => render(CurrentEventBanner, CURRENT)),
    );
    // Two calls in the live branch — start and end.
    expect(options).toHaveLength(2);
    for (const o of options) {
      expect(o).toBeDefined();
      expect(o?.timeZone).toBe("UTC");
    }
  });

  it("...on the resolution-date branches as well", () => {
    for (const resolution_date of [
      "2026-09-06T00:00:00+00:00",
      "2026-10-04T00:00:00+00:00",
    ]) {
      const options = dateFormatOptions(() =>
        at(new Date("2026-09-01T12:00:00Z"), () =>
          render(CurrentEventBanner, {
            ...CURRENT,
            start_date: null,
            end_date: null,
            resolution_date,
            top_golfers: [],
          }),
        ),
      );
      expect(options).toHaveLength(1);
      expect(options[0]?.timeZone).toBe("UTC");
    }
  });

  it("...and the pre-start branch", () => {
    const options = dateFormatOptions(() =>
      at(BEFORE_START, () => render(CurrentEventBanner, CURRENT)),
    );
    expect(options).toHaveLength(2);
    expect(options.every((o) => o?.timeZone === "UTC")).toBe(true);
  });

  it("assertTheSpyCanTellThemApart — the legacy component fails this guard", () => {
    // An instrument that cannot fail is not an instrument. The verbatim pre-fix
    // component is run through the identical spy and must come back un-pinned.
    const options = dateFormatOptions(() =>
      at(DURING, () => render(CurrentEventBannerLegacy, CURRENT)),
    );
    expect(options).toHaveLength(2);
    expect(options.every((o) => o?.timeZone === undefined)).toBe(true);
  });
});

describe("UX-P179 · the page's four renderers of these values now agree", () => {
  /**
   * Redundancy is not coupling, so the agreement is asserted on ONE payload
   * driven through the REAL components. The shapes differ on purpose — the
   * banner writes "Aug 27 – Sun, Aug 30", the card writes "Aug 27–30", the
   * schedule row writes "Aug 27 – 30" — so what is compared is the set of
   * calendar days each one names, which is the thing that was disagreeing.
   */
  function days(label: string): string[] {
    return (label.match(/[A-Z][a-z]{2} \d{1,2}|\b\d{1,2}\b/g) || []).map((m) =>
      m.trim(),
    );
  }

  const tourChampionship = SERVED.tournaments.find(
    (t) => t.name === "Tour Championship",
  ) as GolfTournament;

  it("the fixture really does carry the same tournament twice", () => {
    expect(tourChampionship).toBeDefined();
    expect(tourChampionship.start_date).toBe(CURRENT.start_date);
    expect(tourChampionship.end_date).toBe(CURRENT.end_date);
  });

  it("the banner and the schedule row name the same two days", () => {
    const banner = at(BEFORE_START, () =>
      visibleText(render(CurrentEventBanner, CURRENT)),
    );
    const row = formatDateRange(CURRENT.start_date, CURRENT.end_date) as string;
    // UpcomingTournaments collapses a same-month range to "Aug 27 – 30".
    expect(row).toBe("Aug 27 – 30");
    expect(banner).toContain("Aug 27");
    expect(days(row)).toEqual(["Aug 27", "30"]);
  });

  it("the tournament card in the same list names the same two days", () => {
    // `TournamentCard` hides its date while a tournament is live, so the
    // comparison is made at a moment when both surfaces speak.
    const markup = at(BEFORE_START, () =>
      renderToStaticMarkup(
        React.createElement(TournamentCard, {
          tournament: { ...tournamentWithoutMovement(tourChampionship) },
        }),
      ),
    );
    expect(visibleText(markup)).toContain("Aug 27–30");
  });

  it("the detail page's own idiom lands on the same two days", () => {
    // `app/categories/golf/tournaments/[slug]/page.tsx` renders the pair with
    // `timeZone: "UTC"` inline. Reproducing the call is the point: if this ever
    // stops matching the banner, one of the two surfaces has drifted.
    const start = new Date(CURRENT.start_date as string).toLocaleDateString(
      "en-US",
      { month: "short", day: "numeric", timeZone: "UTC" },
    );
    const end = new Date(CURRENT.end_date as string).toLocaleDateString(
      "en-US",
      { month: "short", day: "numeric", year: "numeric", timeZone: "UTC" },
    );
    expect(start).toBe("Aug 27");
    expect(end).toBe("Aug 30, 2026");
    const banner = at(DURING, () =>
      visibleText(render(CurrentEventBanner, CURRENT)),
    );
    expect(banner).toContain("Aug 27");
    expect(banner).toContain("Aug 30");
  });
});

describe("UX-P179 · CONTROL — the extraction changed no markup and no branch", () => {
  /**
   * The banner moved out of the route file so a test could render it at all.
   * Under `TZ=UTC` the pin is a no-op, so at any clock where the boundary fix
   * does not apply, legacy and shipped must be BYTE IDENTICAL — that is what
   * proves the move itself carried nothing with it.
   *
   * ⚠️ Stated precisely, because this queue ships TWO changes: the three clocks
   * below are all clocks at which the un-pinned legacy and the fixed component
   * choose the SAME branch, so any difference there would be the move. The one
   * clock where they must DIFFER is asserted separately, immediately after.
   */
  const inUTC = Intl.DateTimeFormat().resolvedOptions().timeZone === "UTC";

  it("in UTC, the moved component is byte-identical to the one it replaced", () => {
    if (!inUTC) {
      // Say so rather than passing quietly: a control that skips in silence is
      // indistinguishable from one that ran.
      expect(Intl.DateTimeFormat().resolvedOptions().timeZone).not.toBe("UTC");
      return;
    }
    for (const now of [DURING, BEFORE_START, AFTER_END]) {
      expect(at(now, () => render(CurrentEventBanner, CURRENT))).toBe(
        at(now, () => render(CurrentEventBannerLegacy, CURRENT)),
      );
    }
  });

  it("...and they DIFFER on the final day, which is the boundary fix", () => {
    // Zone-independent: an absolute instant on the tournament's last day.
    const now = new Date("2026-08-30T12:00:00Z");
    expect(at(now, () => render(CurrentEventBanner, CURRENT))).not.toBe(
      at(now, () => render(CurrentEventBannerLegacy, CURRENT)),
    );
  });

  it("every non-date branch is untouched: status, venue, count, favorite", () => {
    const text = at(DURING, () => visibleText(render(CurrentEventBanner, CURRENT)));
    expect(text).toContain("This Week");
    expect(text).toContain(`${CURRENT.golfer_count} golfers with odds`);
    if (CURRENT.venue) expect(text).toContain(CURRENT.venue);
    if (CURRENT.top_golfers?.length) {
      expect(text).toContain("Favorite");
      expect(text).toContain(CURRENT.top_golfers[0].name);
    }
  });

  it("after the window closes the banner says so and prints no window", () => {
    const text = at(AFTER_END, () => visibleText(render(CurrentEventBanner, CURRENT)));
    expect(text).toContain("Just Finished");
    expect(text).not.toContain("Aug 27");
    expect(text).not.toContain("Aug 30");
  });

  it("an event with no dates at all still renders, and claims none", () => {
    const dateless: GolfCurrentEvent = {
      ...CURRENT,
      start_date: null,
      end_date: null,
      resolution_date: null,
      top_golfers: [],
    };
    const text = at(DURING, () => visibleText(render(CurrentEventBanner, dateless)));
    expect(text).toContain(CURRENT.name);
    expect(text).not.toMatch(/Aug|Sep|Oct/);
  });
});

describe("UX-P179 · the call site still exists", () => {
  /**
   * The guards above render the component directly, and a component nobody
   * mounts renders nothing for nobody. `/categories/golf` fetches in a
   * `useEffect`, so `renderToStaticMarkup` only ever produces its loading state
   * and there is no way to assert the mounted banner from this suite — and
   * `@testing-library/react` is not a dependency of this repo. So the call site
   * is asserted as text, deliberately and narrowly, as the complement to the
   * render-driven guards rather than a substitute for them.
   */
  it("app/categories/golf/page.tsx imports the banner and mounts it", () => {
    const page = fs.readFileSync(
      path.join(__dirname, "..", "..", "app", "categories", "golf", "page.tsx"),
      "utf8",
    );
    expect(page).toContain(
      'import CurrentEventBanner from "@/components/golf/CurrentEventBanner";',
    );
    expect(page).toContain("<CurrentEventBanner");
    // And the old inline copy is gone, so there is exactly one of them.
    expect(page).not.toContain("function CurrentEventBanner(");
  });
});

/** `TournamentCard` treats 24h movement as "live"; strip it to reach the date. */
function tournamentWithoutMovement(t: GolfTournament): GolfTournament {
  return {
    ...t,
    schedule_status: "upcoming",
    golfers: (t.golfers || []).map((g) => ({ ...g, movement_24h: null })),
  };
}
