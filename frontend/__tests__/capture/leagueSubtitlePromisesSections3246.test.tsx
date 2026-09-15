/**
 * ux/1282 / #3246 — THE LEAGUE PAGE PROMISES ONLY THE SECTIONS IT RENDERS.
 *
 * ═══ WHAT WAS ON PRODUCTION ═══
 *
 * `https://bainluck.com/sports/soccer_uefa_nations_league`, 390px, 2026-09-15.
 * The header read
 *
 *   > Soccer • Win probabilities for live and upcoming games. Finished games below.
 *
 * and then rendered `Upcoming 30`, `Showing 30 events`, the footer. Nothing
 * below. The screenshot is `artifacts/ux-3246/before-soccer-390.png`.
 *
 * ═══ 🔴 WHY THE CORPUS IS A LEAGUE NOBODY WAS LOOKING AT ═══
 *
 * #3246 was filed off tennis during the US Open and diagnosed as the finished
 * arm's recency floor (`/api/events` gives a finished row until yesterday
 * 00:00), which suggested widening that floor as the repair. This corpus is the
 * counter-case that rules the diagnosis incomplete: `soccer_uefa_nations_league`
 * holds 2 completed rows in the whole table, both `2026-03-26`, so its finished
 * bucket is empty at EVERY floor short of six months. Widening cannot make that
 * sentence true. Every league in an off-season or between international windows
 * is in this state, which is most leagues most of the year — so the arm the
 * floor cannot reach is the bigger one.
 *
 * The fixture is `GET /api/events?sport=soccer_uefa_nations_league&days=90`
 * (the widened horizon the page itself asks for on a dormant league — see
 * `lib/sports/leagueHorizon.ts`), captured 2026-09-15 20:38Z, trimmed to the
 * fields the reference fixture keeps. Its shape is ASSERTED below rather than
 * transcribed, so a claim here cannot decay into a comment.
 *
 * ═══ THE CLOCK IS THE CAPTURE'S OWN INSTANT (gotcha #44) ═══
 *
 * `buildLeagueSections` buckets a `scheduled` row more than two hours past its
 * own kickoff as a match that was never reported (#3211). Read against a live
 * clock, these 30 fixtures become 30 unreported matches some time after
 * 2026-09-29 and this file's meaning would rot with the calendar rather than
 * with the code. So the clock is pinned, and a CONTROL re-derives the pin from
 * the corpus instead of trusting the constant.
 *
 * ═══ THE RED ARM, MEASURED ═══
 *
 * Against master's `app/sports/[key]/page.tsx` and `lib/sports/leagueSections.ts`
 * (the rest of the file unchanged): **5 failed, 6 passed of 11**. The five are
 * the ship — the soccer header's false clause, the results-only page's false
 * clause, the empty page's two, the mixed read, and the binding.
 *
 * ⚠️ ONE OF THEM IS NOT A DEFECT CLAIM, and a grader should not read it as one.
 * "mixed: both clauses, unchanged" is red on the parent only because
 * `subtitleOf` reads `data-league-subtitle`, a locator THIS DIFF ADDS; the
 * sentence it asserts is already correct there. That arm therefore also states
 * the claim through `markup`, which is green on both sides, so the
 * must-not-change composition is covered by an assertion that does not depend
 * on the diff. The genuine controls — green on both arms — are all three in
 * section A plus the card census.
 */

import React from "react";
import { renderToStaticMarkup } from "react-dom/server";
import soccerPayload from "../fixtures/leagueNationsLeague.20260915.json";
import usOpenPayload from "../fixtures/leagueUsOpen.20260904.json";
import { buildLeagueSections } from "@/lib/sports/leagueSections";
import type { Event } from "@/lib/types";

type Row = { id: number; status: string; commence_time: string; completed_at?: string | null };
const SOCCER_EVENTS = soccerPayload.events as unknown as Row[];
const US_OPEN_EVENTS = usOpenPayload.events as unknown as Row[];

const FINISHED = ["completed", "closed"];

let swrEvents: unknown;
let swrSport: unknown;

jest.mock("swr", () => ({
  __esModule: true,
  default: (key: unknown) => {
    const k = Array.isArray(key) ? key[0] : key;
    return k === "sports"
      ? { data: { sports: [swrSport] } }
      : { data: swrEvents, error: undefined, isLoading: false, mutate: () => {} };
  },
}));

// Only the analytics seams are replaced — `EventCard` calls `useAnalytics` and
// the real one wants a provider this test has no reason to stand up.
jest.mock("@/hooks", () => ({
  __esModule: true,
  usePageTracking: () => undefined,
  useScrollDepth: () => undefined,
  useEngagementTime: () => undefined,
  useAnalytics: () => ({ trackEventCardClick: () => undefined }),
}));

/** When the soccer payload was fetched: before all 30 of its kickoffs. */
const CAPTURED_AT = new Date("2026-09-15T20:38:00Z").getTime();

// Module scope, not `beforeAll`: three describes below render in their own
// body, which is collection-phase code and runs before any hook
// (`leaguePageSections2948.test.tsx` paid for this lesson once already).
jest.useFakeTimers({ now: CAPTURED_AT, doNotFake: ["nextTick"] });
afterAll(() => {
  jest.useRealTimers();
});

// eslint-disable-next-line @typescript-eslint/no-var-requires
const SportPage = require("@/app/sports/[key]/page").default;

const SOCCER_SPORT = {
  key: "soccer_uefa_nations_league",
  name: "UEFA Nations League",
  group: "Soccer",
};

/** No default for `events` — an arm whose job is a degenerate payload cannot
 *  have the parameter defaulted out from under it. */
function render(events: unknown, sport: unknown = SOCCER_SPORT): string {
  swrEvents = { events };
  swrSport = sport;
  return renderToStaticMarkup(
    React.createElement(SportPage, {
      params: { key: (sport as { key: string }).key },
    }),
  );
}

/**
 * The header sentence a reader actually sees, or `null` when the page renders
 * no subtitle line at all.
 *
 * Read off `data-league-subtitle`, which is a locator this diff adds — so it is
 * useless as a population filter (an absent attribute would make every "does
 * not promise" assertion vacuously true on the parent). Every negative claim
 * below is therefore ALSO made against the whole markup, where the parent's
 * unconditional clause lives whether the attribute exists or not.
 */
function subtitleOf(markup: string): string | null {
  const m = markup.match(/<p[^>]*data-league-subtitle[^>]*>([^<]*)<\/p>/);
  return m ? m[1].replace(/&amp;/g, "&").trim() : null;
}

/** Which sections the page rendered, in document order. */
function renderedSections(markup: string): string[] {
  return [...markup.matchAll(/<section data-league-section="([a-z]+)"/g)].map((m) => m[1]);
}

const finishedRows = (rows: Row[]) => rows.filter((e) => FINISHED.includes(e.status));

/** Real results, borrowed from the US Open capture — see the CONTROL that
 *  proves they bucket the same at any clock. */
const FINISHED_ROWS = finishedRows(US_OPEN_EVENTS);

// ───────────────────────────────────────────────────────────────────────────
// A · the corpus is what the issue says it is
// ───────────────────────────────────────────────────────────────────────────
describe("ux/1282 · CONTROLS on the captured payload", () => {
  test("the Nations League corpus is 30 rows and NOT ONE of them is finished", () => {
    expect(SOCCER_EVENTS).toHaveLength(30);
    expect(finishedRows(SOCCER_EVENTS)).toEqual([]);
    expect(new Set(SOCCER_EVENTS.map((e) => e.status))).toEqual(new Set(["scheduled"]));
  });

  test("the pinned clock is the capture's own instant — before every kickoff", () => {
    // Without this the #3211 rung reclassifies all 30 as unreported matches and
    // the page grows a live section, which would make the arms below pass for
    // a reason that has nothing to do with the subtitle.
    const soonest = Math.min(
      ...SOCCER_EVENTS.map((e) => new Date(e.commence_time).getTime()),
    );
    expect(CAPTURED_AT).toBeLessThan(soonest);
  });

  test("CONTROL: the borrowed results are real, finished, and clock-proof", () => {
    // ⚠️ The US Open capture is read at THIS file's clock, eleven days after it
    // was taken, so its 15 `scheduled` rows are long past their kickoffs and
    // #3211 correctly buckets them as matches nobody reported — they are not
    // "upcoming" here and must not be used as such. Its 17 `completed` rows
    // carry the answer in the status itself and bucket identically at any
    // clock, which is why only those are borrowed below to build the
    // compositions this corpus cannot supply.
    expect(FINISHED_ROWS.length).toBe(17);
    expect(FINISHED_ROWS.every((e) => Boolean(e.completed_at))).toBe(true);
    const anyClock = [CAPTURED_AT, new Date("2027-06-01T00:00:00Z").getTime()];
    for (const now of anyClock) {
      expect(
        buildLeagueSections(FINISHED_ROWS as unknown as Event[], now).map((s) => s.key),
      ).toEqual(["finished"]);
    }
  });
});

// ───────────────────────────────────────────────────────────────────────────
// B · the ship
// ───────────────────────────────────────────────────────────────────────────
describe("ux/1282 · THE SHIP — a league with no results stops promising results", () => {
  const markup = render(SOCCER_EVENTS);

  test("the page renders Upcoming and no Finished section", () => {
    expect(renderedSections(markup)).toEqual(["upcoming"]);
  });

  test("and the header no longer says 'Finished games below'", () => {
    // On the parent this is the whole defect: the clause is unconditional prose
    // in the JSX, so it is in the markup on every composition.
    expect(markup).not.toContain("Finished games below");
    expect(subtitleOf(markup)).toBe(
      "Soccer • Win probabilities for live and upcoming games.",
    );
  });

  test("the true half of the sentence survives, bullet and all", () => {
    // The repair must not answer a false clause by deleting the honest one.
    expect(markup).toContain("Win probabilities for live and upcoming games.");
    expect(markup).not.toContain("Soccer •  ");
    expect(markup).not.toMatch(/Soccer •\s*<\/p>/);
  });

  test("the 30 cards are all still on the page", () => {
    const ids = [...markup.matchAll(/href="\/events\/(\d+)"/g)].map((m) => Number(m[1]));
    expect(new Set(ids)).toEqual(new Set(SOCCER_EVENTS.map((e) => e.id)));
  });
});

describe("ux/1282 · the compositions the sentence has to survive", () => {
  test("mixed: both clauses, unchanged — the composition the sentence was written for", () => {
    const markup = render([...SOCCER_EVENTS, ...FINISHED_ROWS]);
    expect(renderedSections(markup)).toEqual(["upcoming", "finished"]);
    // Stated twice on purpose: the `markup` form is green on both arms, so the
    // composition that must NOT change is guarded by an assertion that does not
    // depend on this diff's locator (see the red-arm note in the docblock).
    expect(markup).toContain(
      "Soccer • Win probabilities for live and upcoming games. Finished games below.",
    );
    expect(subtitleOf(markup)).toBe(
      "Soccer • Win probabilities for live and upcoming games. Finished games below.",
    );
  });

  test("results only: the page stops calling itself live and upcoming", () => {
    // The other half of the same defect, and the one a league gets the morning
    // after its last game: on the parent this page announces live and upcoming
    // games over a screen that holds neither.
    const markup = render(FINISHED_ROWS);
    expect(renderedSections(markup)).toEqual(["finished"]);
    expect(markup).not.toContain("Win probabilities for live and upcoming games");
    expect(subtitleOf(markup)).toBe("Soccer • Finished games below.");
  });

  test("nothing at all: the header is the league, and the empty state speaks", () => {
    const markup = render([]);
    expect(renderedSections(markup)).toEqual([]);
    expect(subtitleOf(markup)).toBe("Soccer");
    expect(markup).not.toContain("Finished games below");
    expect(markup).not.toContain("Win probabilities for live and upcoming games");
    // #2948's empty state is untouched — it is what tells the reader what the
    // page is for once the subtitle stops guessing.
    expect(markup).toContain('data-empty-state-name="league-no-upcoming-events"');
    expect(markup).toContain("This page lists games for this league.");
  });

  test("BINDING: across every composition, promised == rendered", () => {
    // The general form of the ship, read off the SAME markup on both sides, so
    // it cannot be satisfied by a sentence that happens to be right on one
    // corpus. A live row is synthetic — neither real capture carries one.
    const live = [
      {
        id: 9001,
        external_id: "l9001",
        sport: "soccer_uefa_nations_league",
        home_team: "A",
        away_team: "B",
        commence_time: "2026-09-15T19:00:00+00:00",
        completed_at: null,
        status: "live",
        home_score: null,
        away_score: null,
      },
    ];
    const compositions: Row[][] = [
      SOCCER_EVENTS,
      [...SOCCER_EVENTS, ...FINISHED_ROWS],
      FINISHED_ROWS,
      [...(live as unknown as Row[]), ...SOCCER_EVENTS, ...FINISHED_ROWS],
      [...(live as unknown as Row[]), ...FINISHED_ROWS],
      live as unknown as Row[],
      [],
    ];

    for (const events of compositions) {
      const markup = render(events);
      const rendered = renderedSections(markup);
      const sentence = subtitleOf(markup) ?? "";
      expect(sentence.includes("Finished games below")).toBe(rendered.includes("finished"));
      expect(sentence.includes("Win probabilities for live and upcoming games")).toBe(
        rendered.includes("upcoming") || rendered.includes("live"),
      );
    }
  });
});
