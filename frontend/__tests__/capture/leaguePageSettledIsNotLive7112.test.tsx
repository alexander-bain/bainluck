/**
 * ux/1348 / #7112 — WHAT THE LEAGUE PAGE ACTUALLY RENDERS OVER A GRADED MATCH.
 *
 * ═══ WHY THIS FILE EXISTS BESIDE THE UNIT ONE ═══
 *
 * 🔴 THE DEFECT IS A DISAGREEMENT BETWEEN TWO THINGS ON ONE SCREEN, so the only
 * reading that can see it is one that has both in the same string. The unit
 * suite (`__tests__/lib/venueSettledIsFinished7112.test.ts`) grades the bucket
 * rule; it cannot see that the sentence `Settled · Blanch wins` is printed by
 * `EventCard` under a heading `Live & Paused`, because the heading and the
 * sentence are produced by two modules that never meet until this markup.
 *
 * Every claim below is read off the rendered HTML: the heading text, the
 * `Settled · …` sentences, and `href="/events/{id}"` for membership — which
 * `EventCard` has rendered on every arm since long before this diff, so it is
 * an arm-independent reading of what a reader scrolls past (ux/1040's rule:
 * a population filter that only exists on the child is a vacuous test).
 *
 * ═══ RED ON THE PARENT ═══
 *
 * On the parent this renders two sections — `Live & Paused 5` then `Upcoming
 * 14` — with the three graded cards at the TOP of the live one and no Finished
 * section at all. Sections B and C below are red there by heading text, by
 * membership and by order.
 *
 * ═══ THE CLOCK IS THE CAPTURE'S, NOT THE SUITE'S ═══
 *
 * `fixtures/leagueTennisAtp.20260919-7112.json` is a production snapshot, and
 * `EventCard` reads the clock for its own copy. Pinned at MODULE SCOPE, not in
 * a hook: three describes below call `render(...)` in their own body, which is
 * collection-phase code and runs before any `beforeAll` (the lesson written
 * into `leaguePageSections2948.test.tsx`, paid for once already).
 */

import React from "react";
import { renderToStaticMarkup } from "react-dom/server";
import realPayload from "../fixtures/leagueTennisAtp.20260919-7112.json";

type Row = {
  id: number;
  status: string;
  commence_time: string;
  venue_settled?: boolean;
  venue_settled_result?: string | null;
};
const REAL_EVENTS = realPayload.events as unknown as Row[];

const ms = (iso: string) => new Date(iso).getTime();
/** Derived, not transcribed — after the last started match, before the first
 *  fixture. Re-derived independently of the unit suite on purpose. */
const CAPTURED_AT = Math.round(
  (Math.max(...REAL_EVENTS.filter((e) => e.status !== "scheduled").map((e) => ms(e.commence_time))) +
    Math.min(...REAL_EVENTS.filter((e) => e.status === "scheduled").map((e) => ms(e.commence_time)))) /
    2,
);

let swrEvents: unknown;

jest.mock("swr", () => ({
  __esModule: true,
  default: (key: unknown) => {
    const k = Array.isArray(key) ? key[0] : key;
    return k === "sports"
      ? { data: { sports: [{ key: "tennis_atp", name: "ATP", group: "Tennis" }] } }
      : { data: swrEvents, error: undefined, isLoading: false, mutate: () => {} };
  },
}));

// Only the analytics seams are replaced — the ship is sectioning, not tracking.
jest.mock("@/hooks", () => ({
  __esModule: true,
  usePageTracking: () => undefined,
  useScrollDepth: () => undefined,
  useEngagementTime: () => undefined,
  useAnalytics: () => ({ trackEventCardClick: () => undefined }),
}));

jest.useFakeTimers({ now: CAPTURED_AT, doNotFake: ["nextTick"] });
afterAll(() => {
  jest.useRealTimers();
});

// eslint-disable-next-line @typescript-eslint/no-var-requires
const SportPage = require("@/app/sports/[key]/page").default;

function render(events: unknown): string {
  swrEvents = { events };
  return renderToStaticMarkup(
    React.createElement(SportPage, { params: { key: "tennis_atp" } }),
  );
}

/** (heading text → the ids beneath it), in document order. */
function sectionsWithIds(markup: string): { title: string; ids: number[] }[] {
  const chunks = markup.split(/(?=<section data-league-section=")/).slice(1);
  return chunks.map((chunk) => ({
    title: (chunk.match(/data-league-section-title="[a-z]+"[^>]*>([^<]+)/)?.[1] ?? "").trim(),
    ids: [...chunk.matchAll(/href="\/events\/(\d+)"/g)].map((m) => Number(m[1])),
  }));
}

/** The ids of the cards that print the venue's verdict, read off the markup. */
function settledCardIds(markup: string): number[] {
  const cards = markup.split(/(?=href="\/events\/\d+")/);
  return cards
    .filter((c) => /Settled(?:\s|&nbsp;|<[^>]*>)*·/.test(c))
    .map((c) => Number(c.match(/^href="\/events\/(\d+)"/)?.[1]))
    .filter((n) => Number.isFinite(n));
}

const MARKUP = render(REAL_EVENTS);
const SETTLED_IDS = REAL_EVENTS.filter((e) => e.venue_settled === true).map((e) => e.id);

describe("A · CONTROL — the fixture reaches the page and the cards speak", () => {
  test("all 19 real cards render", () => {
    const ids = [...MARKUP.matchAll(/href="\/events\/(\d+)"/g)].map((m) => Number(m[1]));
    expect(new Set(ids)).toEqual(new Set(REAL_EVENTS.map((e) => e.id)));
    expect(ids).toHaveLength(19);
  });

  test("the extractor finds the three cards that print the verdict — TRUE ON THE PARENT", () => {
    // 🔴 This arm must pass on BOTH sides. It is the proof that section B is
    // grading a moved card rather than a card that stopped rendering: #7070
    // shipped this sentence and nothing here touches it.
    expect(settledCardIds(MARKUP).sort()).toEqual([...SETTLED_IDS].sort());
    expect(MARKUP).toContain("Blanch wins");
  });
});

describe("B · THE SHIP — the heading stops contradicting the card under it", () => {
  const sections = sectionsWithIds(MARKUP);

  test("the page renders three headings, Finished among them", () => {
    // Parent: ["Live & Paused", "Upcoming"] — no Finished section at all.
    expect(sections.map((s) => s.title)).toEqual(["Live Now", "Upcoming", "Finished"]);
  });

  test("BINDING: every card printing 'Settled · …' is under Finished", () => {
    const finished = sections.find((s) => s.title === "Finished")!;
    const settled = settledCardIds(MARKUP);
    expect(settled).toHaveLength(3);
    expect(settled.every((id) => finished.ids.includes(id))).toBe(true);
    expect(finished.ids.sort()).toEqual([...SETTLED_IDS].sort());
  });

  test("no card printing 'Settled · …' is under the live heading", () => {
    const live = sections.find((s) => s.title.startsWith("Live"))!;
    expect(settledCardIds(MARKUP).some((id) => live.ids.includes(id))).toBe(false);
    expect(live.ids).toHaveLength(2);
  });

  test("each heading declares its own count", () => {
    expect(MARKUP).toMatch(/Live Now<span[^>]*>2</);
    expect(MARKUP).toMatch(/Upcoming<span[^>]*>14</);
    expect(MARKUP).toMatch(/Finished<span[^>]*>3</);
  });
});

describe("C · ORDER — the matches being played are the first thing on the page", () => {
  test("the first card is one of the two live matches", () => {
    const first = Number(MARKUP.match(/href="\/events\/(\d+)"/)?.[1]);
    // Parent: a settled match, four of them ahead of both live ones.
    expect(SETTLED_IDS).not.toContain(first);
    expect(REAL_EVENTS.find((e) => e.id === first)?.status).toBe("live");
  });

  test("no settled card renders above a match still being played", () => {
    const order = [...MARKUP.matchAll(/href="\/events\/(\d+)"/g)].map((m) => Number(m[1]));
    const lastLive = Math.max(
      ...REAL_EVENTS.filter((e) => e.status === "live").map((e) => order.indexOf(e.id)),
    );
    expect(Math.min(...SETTLED_IDS.map((id) => order.indexOf(id)))).toBeGreaterThan(lastLive);
  });
});
