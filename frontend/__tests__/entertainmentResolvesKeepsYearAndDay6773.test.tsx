/**
 * #6773 — `/entertainment` stops printing a deadline with no year, a day early.
 *
 * ═══ WHAT A READER SAW ═══
 *
 * `/entertainment` at 390px, production, found on ux/1315's LOOK pass. The card
 * MetaRow and the Cultural Moments card both ended in a grey deadline built by a
 * module-private `formatDate`:
 *
 *     function formatDate(iso: string): string {
 *       const d = new Date(iso);
 *       return d.toLocaleDateString("en-US", { month: "short", day: "numeric" });
 *     }
 *
 *     {resolves && <span>· Resolves {formatDate(resolves)}</span>}      // MetaRow
 *     Resolves {formatDate(market.resolution_date)}                     // MomentCard
 *
 * Measured on `GET /api/entertainment`, 2026-09-18, 114 rows carry a
 * `resolution_date` and every one of them is non-null:
 *
 *     40 of 114  resolve in a year that is NOT 2026 — 2027, 2028, 2030, 2099
 *      6 of 114  carry exactly `T00:00:00+00:00`, a declared calendar day
 *      0 of 114  have already passed
 *
 * So a third of the page's deadlines read as this year (#1717's misreading,
 * verbatim: "Resolves Jan 14" about January 2031), and six of them render the
 * previous day for every reader west of UTC (#4081's class). Both rules already
 * have one home in `lib/gameTimeLabel.ts`; this page had never adopted it, and
 * the authority guard could not see that it hadn't — its pattern requires a
 * quote before the word, and these two sites are JSX text. That gap is closed in
 * `__tests__/lib/resolvesLabelAuthority.test.ts` in the same change.
 *
 * ═══ WHAT THIS FILE CAN AND CANNOT PROVE ═══
 *
 * 🔴 `jest.config.js` pins `process.env.TZ = "UTC"` for the whole suite, and it
 * must (a test file's realm is built before `setupFiles`). Under UTC the
 * declared-day defect and its repair render the IDENTICAL string, so a rendered
 * assertion like `toContain("Dec 31")` is green on the broken page and proves
 * nothing about the half of the ship that broke. `declaredDeadlineKeepsItsDay4081`
 * hit this first and solved it by reading the OPTIONS handed to
 * `toLocaleDateString`; the same move is the only sound one here, so the zone arm
 * below spies through a real page render rather than asserting a day.
 *
 * The YEAR arm needs no such care — it is zone-independent, and it is the one a
 * rendered string can decide honestly.
 *
 * The rig is `entertainmentHeroLeadFillsItsCard5953`'s, deliberately: it mounts
 * the page's DEFAULT export, so the components under test stay module-local. A
 * guard that needs the production code rearranged to be testable is testing the
 * rearrangement.
 */

import { renderToStaticMarkup } from "react-dom/server";
import React from "react";
import type { EntertainmentData, EntMarketRow } from "@/lib/api";

jest.mock("swr", () => ({
  __esModule: true,
  default: () => ({
    data: (global as never as { __ENT__: EntertainmentData }).__ENT__,
    error: undefined,
  }),
}));
jest.mock("@/hooks", () => ({
  usePageTracking: () => undefined,
  useScrollDepth: () => undefined,
  useEngagementTime: () => undefined,
}));
jest.mock("@/lib/tmdb", () => ({
  hasTMDBToken: () => false,
  searchMovie: async () => null,
  posterUrl: (p: string) => p,
}));

import EntertainmentPage from "@/app/entertainment/page";

/**
 * Fixed "now", well before every future specimen and well after the past one.
 *
 * `formatResolvesLabel` defaults `now` to `Date.now()` and the page calls it
 * with one argument, so the page's clock is the ambient one. Pinning it here is
 * gotcha #44: offset FIRST, never branch on the real clock.
 */
const NOW = Date.parse("2026-09-18T12:00:00Z");

/** The four shapes the live payload actually contains, one row each. */
const SPECIMENS = {
  /** 40 of 114 — the year-omission population. `Jan 14` read as this January. */
  otherYear: "2027-01-14T15:00:00+00:00",
  /** 6 of 114 — a declared calendar day; local conversion moves it back a day. */
  declaredDay: "2026-12-31T00:00:00+00:00",
  /** 68 of 114 — a genuine instant, which must KEEP local conversion. */
  instant: "2026-10-02T23:59:00+00:00",
  /** 0 of 114 today, but the authority's past-date rule now reaches this page. */
  past: "2025-11-04T15:00:00+00:00",
} as const;

function market(over: Partial<EntMarketRow> = {}): EntMarketRow {
  return {
    q: "Will Dune: Part Three be delayed?",
    market_id: 1,
    kind: "market",
    src: "kalshi",
    prob: 0.42,
    delta_24h: 0.01,
    top_outcomes: [{ name: "Yes", prob: 0.42, delta_24h: 0.01 }],
    outcome_count: 4,
    volume_24h: 67000,
    resolution_date: SPECIMENS.otherYear,
    image_url: null,
    hook: null,
    ...over,
  } as EntMarketRow;
}

function entData(
  trending: EntMarketRow[],
  culturalMoments: EntMarketRow[] = [],
): EntertainmentData {
  const empty = { count: 0, side_markets: [] };
  return {
    total_markets: 1002,
    updated_at: "2026-09-18T11:30:00Z",
    trending,
    themes: {
      music: {
        ...empty,
        spotify_race: [],
        billboard_watch: [],
        billboard_groups: [],
        album_drops: [],
        artist_streaming: [],
      },
      movies_tv: {
        ...empty,
        rt_groups: [],
        rt_markets: [],
        box_office_groups: [],
        box_office: [],
        reality_tv: [],
      },
      tech_culture: { count: 0, markets: [] },
    },
    cultural_moments: culturalMoments,
    by_source: { kalshi: 0, polymarket: 0 },
  } as EntertainmentData;
}

/**
 * 🪤 `TrendingHero` opens `if (!markets || markets.length < 2) return null`, so
 * a one-row fixture renders NO MetaRow at all and every assertion over an empty
 * list passes vacuously — including "a past date prints nothing", which is
 * exactly the arm that would be lying. Two rows is the hero's own floor; the
 * live grid draws five.
 */
function pair(resolutionDate: string): EntMarketRow[] {
  return [
    market({ market_id: 1, resolution_date: resolutionDate }),
    market({
      market_id: 2,
      q: "Oscar Winner: Best Picture",
      resolution_date: resolutionDate,
    }),
  ];
}

/** Mount the real page at a pinned clock and hand back its markup as text. */
function renderPage(
  trending: EntMarketRow[],
  culturalMoments: EntMarketRow[] = [],
): string {
  const spy = jest.spyOn(Date, "now").mockReturnValue(NOW);
  try {
    (global as never as { __ENT__: EntertainmentData }).__ENT__ = entData(
      trending,
      culturalMoments,
    );
    return renderToStaticMarkup(React.createElement(EntertainmentPage));
  } finally {
    spy.mockRestore();
  }
}

/**
 * The rendered `metaRow` blocks, which is where an orphaned separator would sit.
 *
 * Scoped deliberately: the page HEAD has a legitimate `<span>·</span>` of its
 * own between "1,002 active markets" and "Updated 30 min ago", and the footer
 * has another. A page-wide search for the character answers a different
 * question and fails on healthy markup.
 */
function metaRowBlocks(html: string): string[] {
  return [...html.matchAll(/<div class="metaRow">([\s\S]*?)<\/div>/g)].map((m) => m[1]);
}

/** Every "Resolves …" the page printed, read out of the rendered markup. */
function resolvesLines(html: string): string[] {
  // Tags become the separator, so a match runs to the end of its own TEXT
  // NODE and no further. Splitting on spaces would truncate the label at
  // "Resolves" and every assertion below would pass on a bare word.
  const text = html.replace(/<[^>]*>/g, "\n");
  return [...text.matchAll(/Resolves[^\n]*/g)].map((m) => m[0].trim());
}

describe("#6773 — the deadline on /entertainment carries its year", () => {
  it("prints the YEAR on a row that does not resolve this year", () => {
    const lines = resolvesLines(renderPage(pair(SPECIMENS.otherYear)));

    expect(lines).toEqual(["Resolves Jan 14, 2027", "Resolves Jan 14, 2027"]);
  });

  it("NON-VACUITY — the old private formatter's output is no longer the label", () => {
    // `formatDate` returned exactly "Jan 14" for this wire value, and the label
    // was that string with the word in front. Asserting the new string alone
    // would also pass if the page had simply stopped rendering the row, so pin
    // the removed shape too: a deadline that ENDS after the day number.
    const lines = resolvesLines(renderPage(pair(SPECIMENS.otherYear)));

    expect(lines).not.toHaveLength(0);
    expect(lines).not.toContain("Resolves Jan 14");
    for (const line of lines) expect(line).toMatch(/, \d{4}$/);
  });

  it("the Cultural Moments card carries it too — the second call site", () => {
    // MomentCard is a different component with its own copy of the old bug, so
    // a fix proven only through MetaRow would leave half the page behind.
    const moment = market({ market_id: 99, q: "Honey Deuce sales record?" });
    const html = renderPage([], [moment]);
    const lines = resolvesLines(html);

    expect(html).toContain("Honey Deuce sales record?");
    expect(lines).toHaveLength(1);
    expect(lines[0]).toBe("Resolves Jan 14, 2027");
  });

  it("a row whose date has GONE prints nothing, and leaves no orphan separator", () => {
    // The behaviour that arrived with the authority. The old guard was on the
    // wire value, so moving to a label that can be "" without moving the guard
    // would have rendered a bare "· " in the meta row.
    const past = market({ market_id: 3, q: "Gone moment", resolution_date: SPECIMENS.past });
    const html = renderPage(pair(SPECIMENS.past), [past]);

    expect(resolvesLines(html)).toEqual([]);

    // 🔴 The line above is NOT enough on its own, and the gap is the whole point
    // of this test. Had the guard stayed on `resolution_date` while the body
    // rendered a label that can be "", the row would emit a bare `<span>· </span>`
    // — no "Resolves" for the scan to find, and a lone grey dot for the reader.
    // Stated as an invariant that also holds on the healthy page below: a meta
    // row shows the separator IF AND ONLY IF it has a deadline to separate.
    const rows = metaRowBlocks(html);
    expect(rows).not.toHaveLength(0);
    for (const row of rows) expect(row).not.toContain("·");

    // ...and MomentCard's equivalent — an empty right-aligned chip in its header.
    expect(html).toContain("Gone moment");
    expect(html).not.toMatch(/margin-left:auto[^>]*><\/div>/);
  });

  it("CONTROL — the separator IS there when there is a deadline to separate", () => {
    // The other direction of the invariant above, without which "no · anywhere"
    // would be satisfied by a row that had stopped rendering the label at all.
    const rows = metaRowBlocks(renderPage(pair(SPECIMENS.otherYear)));

    expect(rows).not.toHaveLength(0);
    for (const row of rows) {
      expect(row).toContain("·");
      expect(row).toContain("Resolves Jan 14, 2027");
    }
  });

  it("CONTROL — a future row on the same page still prints, so the arm above is real", () => {
    // Both directions (gotcha #43): if the past-date arm passed because the
    // fixture never reaches a MetaRow at all, this fails.
    const lines = resolvesLines(
      renderPage([
        market({ market_id: 1, resolution_date: SPECIMENS.past }),
        market({ market_id: 2, q: "Oscar Winner: Best Picture", resolution_date: SPECIMENS.instant }),
      ]),
    );

    expect(lines).toEqual(["Resolves Oct 2, 2026"]);
  });

  it("the page constructs no deadline of its own — one authority, one string", () => {
    // Belt to the tree-scanning guard's braces: that one fails if a private
    // formatter comes BACK; this one fails if the page keeps calling the
    // authority but wraps its output in prose of its own again.
    const lines = resolvesLines(
      renderPage([
        market({ market_id: 1 }),
        market({ market_id: 2, q: "Next James Bond film", resolution_date: SPECIMENS.instant }),
      ]),
    );

    for (const line of lines) expect(line).toMatch(/^Resolves [A-Z][a-z]{2} \d{1,2}, \d{4}$/);
  });
});

describe("#6773 — the declared day survives the page's render", () => {
  /**
   * The zone arm. Read the note at the top: under the suite's pinned `TZ=UTC` a
   * rendered day is identical before and after the repair, so what is asserted
   * is the OPTIONS the page's render hands `toLocaleDateString` — which is the
   * exact line #4081 got wrong, and is visible under any harness zone.
   *
   * The spy wraps the real method rather than replacing it, so the page still
   * renders and a throw inside the formatter would still surface.
   */
  const real = Date.prototype.toLocaleDateString;
  let seen: Intl.DateTimeFormatOptions[] = [];

  beforeEach(() => {
    seen = [];
    // eslint-disable-next-line no-extend-native
    Date.prototype.toLocaleDateString = function (
      this: Date,
      locales?: unknown,
      options?: Intl.DateTimeFormatOptions,
    ) {
      seen.push(options ?? {});
      return real.call(this, locales as string | string[] | undefined, options);
    } as typeof Date.prototype.toLocaleDateString;
  });

  afterEach(() => {
    // eslint-disable-next-line no-extend-native
    Date.prototype.toLocaleDateString = real;
  });

  /**
   * 🪤 The spy catches EVERY `toLocaleDateString` the page makes, and the page
   * footer makes one of its own — `new Date().toLocaleDateString()`, the "as of"
   * stamp, with no options at all. A blanket `for (const o of seen)` therefore
   * fails on the footer no matter what the deadline did, and the obvious repair
   * (assert `seen[0]`) silently depends on render order.
   *
   * So the deadline calls are identified by the authority's own signature: it is
   * the only caller here that asks for a YEAR. The footer stamp is then a free
   * control — it must stay un-pinned, or this change quietly moved an unrelated
   * date on the page into a zone the reader is not in.
   */
  const dated = () => seen.filter((o) => o.year === "numeric");
  const pinned = () => dated().filter((o) => o.timeZone === "UTC");

  it("pins UTC for a `T00:00:00+00:00` deadline — the 6 rows that read a day early", () => {
    renderPage(pair(SPECIMENS.declaredDay));

    expect(dated()).toHaveLength(2);
    expect(pinned()).toHaveLength(2);
  });

  it("CONTROL — a real instant on the same page keeps LOCAL conversion", () => {
    // Without this, pinning UTC unconditionally would pass the arm above and
    // silently move every genuine close time into a zone the reader is not in.
    renderPage(pair(SPECIMENS.instant));

    expect(dated()).toHaveLength(2);
    expect(pinned()).toHaveLength(0);
  });

  it("the Cultural Moments card makes the same choice", () => {
    renderPage([], [market({ resolution_date: SPECIMENS.declaredDay })]);

    expect(dated()).toHaveLength(1);
    expect(pinned()).toHaveLength(1);
  });

  it("CONTROL — the page's own footer stamp is NOT pinned to UTC", () => {
    // The blast radius of the change, stated as an assertion: exactly one
    // option-less call (the "as of" date), and it stays local.
    renderPage(pair(SPECIMENS.declaredDay));

    const footer = seen.filter((o) => o.year === undefined);
    expect(footer).toHaveLength(1);
    expect(footer[0].timeZone).toBeUndefined();
  });
});
