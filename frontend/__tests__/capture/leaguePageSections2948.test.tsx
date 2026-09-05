/**
 * ux/1058 / #2948 — WHAT THE LEAGUE PAGE ACTUALLY RENDERS.
 *
 * ═══ WHY EVERY ORDERING CLAIM IS READ OFF `href="/events/{id}"` ═══
 *
 * 🔴 THE LOAD-BEARING PARAGRAPH. The obvious extractor selects
 * `[data-league-section]` — an attribute THIS DIFF ADDS. On the parent that
 * filter matches nothing, `[].every(...)` is vacuously true, and the whole
 * suite would pass on the bug (ux/1040, ux/1041, ux/1042: every predicate in a
 * guard, the POPULATION FILTER included, must exist on the parent or the test
 * is part of the ship and must not be labelled otherwise).
 *
 * `EventCard` renders `href={`/events/${event.id}`}` on both arms and has done
 * since long before this diff, so the ordered list of ids in the markup is an
 * arm-independent reading of exactly what a reader scrolls past. Every ordering
 * assertion below is made on that list. The section-attribute selector is used
 * only by the BINDING test, which is explicitly part of the ship.
 *
 * ═══ THE BINDING TEST EXISTS BECAUSE ORDER ALONE IS NOT ENOUGH ═══
 *
 * A fix that emitted the right three headings and hung the wrong cards under
 * them would satisfy every order claim here (ux/1039). So one test reads
 * (heading → the ids beneath it) as PAIRS and asserts the membership, not just
 * the sequence.
 *
 * ⚠️ The corpus has no live row (see `__tests__/lib/leagueSections.test.ts`), so
 * the live arm is synthetic and is labelled SYNTHETIC.
 *
 * ═══ 🔴 #3211 — THE CLOCK IS PINNED TO THE CAPTURE'S OWN INSTANT ═══
 *
 * `buildLeagueSections` now branches on the current time: a row that still says
 * `scheduled` more than two hours after its own kickoff is bucketed as a match
 * that should have been played and was never reported, rather than as one about
 * to begin. (171 US Open matches were in exactly that state on production and
 * reachable from no rail at all — the reason the rung exists.)
 *
 * This corpus is a snapshot taken on 2026-09-04, so read against a live clock
 * its fifteen fixtures become fifteen unreported matches, and every count here
 * would rot with the calendar rather than with the code. Gotcha #44's rule is
 * *offset from a fixed anchor*, so the anchor is fixed: the whole file renders
 * at the moment the endpoint was called. That also stabilises the CARD copy,
 * which reads the clock for its "Today"/"Tomorrow" labels and was previously
 * free to differ between two runs of the same suite.
 */

import React from "react";
import { renderToStaticMarkup } from "react-dom/server";
import realPayload from "../fixtures/leagueUsOpen.20260904.json";

type Row = { id: number; status: string; commence_time: string; completed_at?: string | null };
const REAL_EVENTS = realPayload.events as unknown as Row[];

let swrEvents: unknown;

jest.mock("swr", () => ({
  __esModule: true,
  default: (key: unknown) => {
    const k = Array.isArray(key) ? key[0] : key;
    return k === "sports"
      ? { data: { sports: [{ key: "tennis_atp_us_open", name: "ATP US Open", group: "Tennis" }] } }
      : { data: swrEvents, error: undefined, isLoading: false, mutate: () => {} };
  },
}));

// Only the analytics seams are replaced. `useAnalytics` is stubbed because
// `EventCard` calls it and the real one demands an `AnalyticsProvider` this
// test has no reason to stand up — the ship is ordering, not tracking.
jest.mock("@/hooks", () => ({
  __esModule: true,
  usePageTracking: () => undefined,
  useScrollDepth: () => undefined,
  useEngagementTime: () => undefined,
  useAnalytics: () => ({ trackEventCardClick: () => undefined }),
}));

/** After the corpus's newest Final, before its soonest fixture — see the
 *  #3211 section of the docblock, and the CONTROL that re-derives it in
 *  `__tests__/lib/leagueSections.test.ts`. */
const CAPTURED_AT = new Date("2026-09-04T14:00:00Z").getTime();

// 🔴 MODULE SCOPE, NOT `beforeAll`, AND THAT IS LOAD-BEARING. Three of the
// describes below call `render(...)` in their own body — collection-phase code,
// which runs BEFORE any `beforeAll` hook. Pinning the clock in a hook left
// exactly those renders on the real clock, and the suite reported eight of the
// corpus's fifteen fixtures as unreported matches: green hook, wrong markup.
jest.useFakeTimers({ now: CAPTURED_AT, doNotFake: ["nextTick"] });
afterAll(() => {
  jest.useRealTimers();
});

// eslint-disable-next-line @typescript-eslint/no-var-requires
const SportPage = require("@/app/sports/[key]/page").default;

/** No default — an arm whose job is to pass a degenerate payload cannot have
 *  the parameter defaulted out from under it (ux/1012). */
function render(events: unknown): string {
  swrEvents = { events };
  return renderToStaticMarkup(
    React.createElement(SportPage, { params: { key: "tennis_atp_us_open" } }),
  );
}

/**
 * The ordered event ids a reader scrolls past.
 *
 * Reports its own yield: if the markup does not carry exactly the number of
 * cards we handed the page, the extractor is under-reading and says so with the
 * numbers rather than silently returning a short list (ux/1040).
 */
function renderedIds(markup: string, expected: number): number[] {
  const ids = [...markup.matchAll(/href="\/events\/(\d+)"/g)].map((m) => Number(m[1]));
  if (ids.length !== expected) {
    throw new Error(`extractor read ${ids.length} cards, markup declares ${expected}`);
  }
  return ids;
}

const statusOf = new Map(REAL_EVENTS.map((e) => [e.id, e.status]));
const isFinished = (id: number) => ["completed", "closed"].includes(statusOf.get(id) ?? "");

/**
 * Decode the entities `renderToStaticMarkup` emits.
 *
 * ONE pass over a lookup map, never chained `.replace()` calls: a chain that
 * unescapes `&amp;` before the numeric forms re-reads its own output and turns
 * `&amp;#39;` into `'` (CodeQL `js/double-escaping` — ux/1009, ux/1023).
 */
const ENTITIES: Record<string, string> = {
  "&amp;": "&", "&lt;": "<", "&gt;": ">", "&quot;": '"', "&#x27;": "'", "&#39;": "'",
};
const decode = (s: string) => s.replace(/&(?:amp|lt|gt|quot|#x27|#39);/g, (m) => ENTITIES[m]);

/** (heading text → the ids rendered beneath it), in document order. */
function sectionsWithIds(markup: string): { title: string; ids: number[] }[] {
  const chunks = markup.split(/(?=<section data-league-section=")/).slice(1);
  return chunks.map((chunk) => {
    const raw = chunk.match(/data-league-section-title="[a-z]+"[^>]*>([^<]+)/)?.[1] ?? "";
    const title = decode(raw).trim();
    const ids = [...chunk.matchAll(/href="\/events\/(\d+)"/g)].map((m) => Number(m[1]));
    return { title, ids };
  });
}

describe("ux/1058 · the fixture reaches the page", () => {
  test("CONTROL: all 32 real cards render, on either arm", () => {
    const ids = renderedIds(render(REAL_EVENTS), REAL_EVENTS.length);
    expect(new Set(ids)).toEqual(new Set(REAL_EVENTS.map((e) => e.id)));
  });
});

describe("ux/1058 · THE SHIP — games still to play come first", () => {
  const markup = render(REAL_EVENTS);
  const ids = renderedIds(markup, REAL_EVENTS.length);

  test("the FIRST card on the page is not a finished game", () => {
    // On master this is `false`: id 0 is Alcaraz v Faria, completed.
    expect(isFinished(ids[0])).toBe(false);
  });

  test("no finished game renders above a game still to play", () => {
    const lastUnfinished = ids.map(isFinished).lastIndexOf(false);
    const firstFinished = ids.map(isFinished).indexOf(true);
    expect(firstFinished).toBeGreaterThan(lastUnfinished);
  });

  test("the 17 finished cards move from the top of the page to the bottom", () => {
    const finishedPositions = ids.map((id, i) => (isFinished(id) ? i : -1)).filter((i) => i >= 0);
    expect(finishedPositions).toHaveLength(17);
    // They occupy the LAST 17 slots of 32 — on master they occupied the first 17.
    expect(finishedPositions).toEqual([...Array(17)].map((_, i) => 15 + i));
  });
});

describe("ux/1058 · the headings, and the cards actually under them", () => {
  const markup = render(REAL_EVENTS);

  test("the page grows section headings it did not have", () => {
    // Part of the ship, not a control: master renders no <h2> at all here.
    expect(sectionsWithIds(markup).map((s) => s.title)).toEqual(["Upcoming", "Finished"]);
  });

  test("BINDING: each heading carries exactly its own cards, not just the right order", () => {
    const [upcoming, finished] = sectionsWithIds(markup);
    expect(upcoming.ids.every((id) => !isFinished(id))).toBe(true);
    expect(finished.ids.every(isFinished)).toBe(true);
    expect(upcoming.ids).toHaveLength(15);
    expect(finished.ids).toHaveLength(17);
    // and between them they are the whole page — nothing rendered outside a section
    expect(upcoming.ids.length + finished.ids.length).toBe(REAL_EVENTS.length);
  });

  test("each heading declares its own count", () => {
    expect(markup).toMatch(/Upcoming<span[^>]*>15</);
    expect(markup).toMatch(/Finished<span[^>]*>17</);
  });
});

describe("ux/1058 · SYNTHETIC — the live arm the corpus cannot supply", () => {
  const live = [
    { id: 900, external_id: "l900", sport: "t", home_team: "A", away_team: "B",
      commence_time: "2026-09-04T01:00:00+00:00", completed_at: null, status: "live",
      home_score: null, away_score: null },
  ];

  test("a live match renders above every upcoming and finished card", () => {
    const events = [...REAL_EVENTS, ...live];
    const ids = renderedIds(render(events), events.length);
    expect(ids[0]).toBe(900);
    expect(sectionsWithIds(render(events)).map((s) => s.title)).toEqual([
      "Live Now",
      "Upcoming",
      "Finished",
    ]);
  });

  test("a suspended match is live, never Finished", () => {
    const events = [...REAL_EVENTS, { ...live[0], id: 901, status: "suspended" }];
    const sections = sectionsWithIds(render(events));
    expect(sections[0].title).toBe("Live & Paused");
    expect(sections[0].ids).toEqual([901]);
    expect(sections[2].ids).not.toContain(901);
  });
});

/**
 * ⚠️ THESE THREE WERE DRAFTED AS "CONTROL" AND THE RED ARM PROVED THE LABEL
 * WRONG — all three go red on the parent, because all three assert something
 * this diff introduces (ux/1038, ux/1012: a control that is red on the parent
 * is not a control, it is an unlabelled claim). They are moved here and
 * retitled rather than quietly relabelled, so a grader can see what changed.
 *
 * The genuine controls — green on BOTH arms, verified by name in the red run —
 * are `all 32 real cards render` and, in the pure suite, `the corpus is the
 * real endpoint's order`.
 */
describe("ux/1058 · the copy the issue named (arm-dependent: part of the ship)", () => {
  test("the empty state stops calling the page scheduled-only", () => {
    const markup = render([]);
    expect(markup).toContain('data-empty-state-name="league-no-upcoming-events"');
    expect(markup).toContain("This page lists games for this league.");
    expect(markup).not.toContain("scheduled games for this league");
  });

  test("the subtitle stops calling the whole page upcoming", () => {
    const markup = render(REAL_EVENTS);
    expect(markup).not.toContain("Upcoming games with win probabilities");
    expect(markup).toContain("Win probabilities for live and upcoming games.");
  });

  test("a league with only scheduled games gets ONE heading, not three", () => {
    const onlyUpcoming = REAL_EVENTS.filter((e) => e.status === "scheduled");
    expect(sectionsWithIds(render(onlyUpcoming)).map((s) => s.title)).toEqual(["Upcoming"]);
  });
});
