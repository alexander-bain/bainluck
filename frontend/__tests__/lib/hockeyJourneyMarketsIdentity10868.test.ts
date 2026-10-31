/**
 * #10868 F1b — a hockey page's props and "All props" come only from ITS OWN
 * `/game-markets` body.
 *
 * PILLARS: TRUTH / FORMATTING / DISCOVER. SHIP: hockey props, grades and All
 * props counts stay attached to the game the reader opened.
 *
 * The rule: a held body is this game's only when its `event_id` is exactly
 * `event.id` (`ownHockeyMarkets`, numeric, no coercion, no name or time
 * matching). Another game's body reads exactly as no body: no points or
 * assists card, no story, no original, id, grade, Details or count. The page
 * decides this once (`buildHockeyJourney`); the two readers that open a body
 * (`contributionLadders`, `hockeyJourneyOriginals`) check it again themselves.
 * The event-less catalogue primitive (`catalogueMatches`) is unchanged: it
 * describes the body it is given.
 *
 * REAL retained bodies (`hockeyJourney10868.fixtures.json`, re-hashed by
 * `hockeyJourney10868.test.ts`): 15169793 Minnesota Wild 4–1 Boston Bruins
 * (finalDetail / finalHistory / finalMarkets) and 15338496 New Jersey Devils at
 * Vegas Golden Knights (pregameDetail / pregameHistory / pregameMarkets). Each
 * game's real body is the other game's FOREIGN case.
 *
 * CONSTRUCTED, and named where used:
 *   - live replays: a detail with only its `status` set to "live" (no live NHL
 *     body is retained), read at a clock after its listed start;
 *   - SAME-MATCHUP STAND-IN: a game's own body with only `event_id` relabelled to
 *     the other game's id — the same bytes under another game's id, which is
 *     what a rematch's, a playoff series game's or a twin row's body looks like
 *     to this page. It is the discriminating case for the cards: a REAL other
 *     game's body already deals no card here, because the stat filter only
 *     drops a market-name prefix that names both of the page's teams
 *     (`statLabel`, nflEventCardDeck.ts). No real rematch leak is claimed.
 *   - RELABEL CONTROL: a foreign body relabelled to this game's id (it must
 *     draw again — the id alone decides);
 *   - a body with its `event_id` removed, or served as a string.
 */

import fixtures from "./hockeyJourney10868.fixtures.json";
import type { EventDetailResponse, EventHistoryResponse } from "@/lib/types";
import type { GameMarketsResponse } from "@/lib/api";
import {
  buildHockeyJourney,
  catalogueMatches,
  contributionLadders,
  hockeyJourneyContribution,
  hockeyJourneyOriginals,
  ownHockeyMarkets,
  type HockeyJourneyHost,
  type HockeyJourneyStat,
} from "@/lib/eventPage10868/hockeyJourney";

const finalDetail = fixtures.finalDetail as unknown as EventDetailResponse;
const finalHistory = fixtures.finalHistory as unknown as EventHistoryResponse;
const finalMarkets = fixtures.finalMarkets as unknown as GameMarketsResponse;
const pregameDetail = fixtures.pregameDetail as unknown as EventDetailResponse;
const pregameHistory = fixtures.pregameHistory as unknown as EventHistoryResponse;
const pregameMarkets = fixtures.pregameMarkets as unknown as GameMarketsResponse;

const FINAL_ID = 15169793;
const PREGAME_ID = 15338496;
const STATS: HockeyJourneyStat[] = ["points", "assists"];

/** CONSTRUCTED: the same bytes with only `event_id` changed. */
const relabelled = (body: GameMarketsResponse, eventId: number) => ({ ...body, event_id: eventId }) as GameMarketsResponse;

const host = (nowMs: number): HockeyJourneyHost => ({ nowMs, hero: null, probabilityObservedAt: null });

/** Every outcome and market id a body serves, as the strings a rendered model would carry. */
function servedIds(body: GameMarketsResponse): string[] {
  const ids = new Set<string>();
  const visit = (value: unknown, key?: string) => {
    if (Array.isArray(value)) {
      for (const v of value) visit(v, key);
    } else if (value && typeof value === "object") {
      for (const [k, v] of Object.entries(value as Record<string, unknown>)) visit(v, k);
    } else if (typeof value === "number" && key && /(_market_ids?|contributor_outcome_ids)$/.test(key)) {
      ids.add(String(value));
    }
  };
  visit(body);
  return [...ids];
}

interface PhaseCase {
  label: string;
  phase: "before" | "live" | "final";
  event: EventDetailResponse;
  history: EventHistoryResponse;
  own: GameMarketsResponse;
  foreign: GameMarketsResponse;
  otherId: number;
  nowMs: number;
}

const CASES: PhaseCase[] = [
  {
    label: "before the start (15338496, real)",
    phase: "before",
    event: pregameDetail,
    history: pregameHistory,
    own: pregameMarkets,
    foreign: finalMarkets,
    otherId: FINAL_ID,
    nowMs: Date.parse("2026-10-30T20:13:55Z"),
  },
  {
    label: "during play (15338496, CONSTRUCTED status-only live replay)",
    phase: "live",
    event: { ...pregameDetail, status: "live" } as EventDetailResponse,
    history: pregameHistory,
    own: pregameMarkets,
    foreign: finalMarkets,
    otherId: FINAL_ID,
    nowMs: Date.parse("2026-10-30T22:30:00Z"),
  },
  {
    label: "during play (15169793, CONSTRUCTED status-only live replay)",
    phase: "live",
    event: { ...finalDetail, status: "live" } as EventDetailResponse,
    history: finalHistory,
    own: finalMarkets,
    foreign: pregameMarkets,
    otherId: PREGAME_ID,
    nowMs: Date.parse("2026-10-04T02:00:00Z"),
  },
  {
    label: "after the final (15169793, real)",
    phase: "final",
    event: finalDetail,
    history: finalHistory,
    own: finalMarkets,
    foreign: pregameMarkets,
    otherId: PREGAME_ID,
    nowMs: Date.parse("2026-10-11T04:56:41Z"),
  },
];

describe("#10868 F1b — whose markets body this is", () => {
  it("is decided by the exact numeric event_id alone", () => {
    expect(finalMarkets.event_id).toBe(FINAL_ID);
    expect(pregameMarkets.event_id).toBe(PREGAME_ID);
    expect(ownHockeyMarkets(finalMarkets, finalDetail)).toBe(finalMarkets);
    expect(ownHockeyMarkets(pregameMarkets, pregameDetail)).toBe(pregameMarkets);
    expect(ownHockeyMarkets(pregameMarkets, finalDetail)).toBeNull();
    expect(ownHockeyMarkets(finalMarkets, pregameDetail)).toBeNull();
    expect(ownHockeyMarkets(null, finalDetail)).toBeNull();
    expect(ownHockeyMarkets(undefined, finalDetail)).toBeNull();
    const { event_id: dropped, ...noId } = finalMarkets; // CONSTRUCTED: the id removed
    expect(dropped).toBe(FINAL_ID);
    expect(ownHockeyMarkets(noId as unknown as GameMarketsResponse, finalDetail)).toBeNull();
    const textId = { ...finalMarkets, event_id: String(FINAL_ID) } as unknown as GameMarketsResponse; // CONSTRUCTED
    expect(ownHockeyMarkets(textId, finalDetail)).toBeNull();
  });

  it("leaves the event-less catalogue primitive describing the body it is given (option A)", () => {
    // `catalogueMatches` knows no event; ownership is its event-aware caller's.
    expect(catalogueMatches(pregameMarkets, finalDetail.status, Date.parse("2026-10-11T04:56:41Z")).length).toBeGreaterThan(0);
  });
});

describe.each(CASES)("#10868 F1b — $label", (c) => {
  const sameMatchup = relabelled(c.own, c.otherId); // CONSTRUCTED same-matchup stand-in
  const build = (gameMarkets: GameMarketsResponse | null) =>
    buildHockeyJourney({ event: c.event, history: c.history, gameMarkets, host: host(c.nowMs) });

  it("this game's own body still deals both cards and lists its originals", () => {
    for (const stat of STATS) {
      const card = hockeyJourneyContribution(stat, c.event, c.own, c.nowMs);
      expect(card).not.toBeNull();
      expect(card!.phase).toBe(c.phase);
      expect(contributionLadders(stat, c.event, c.own).length).toBeGreaterThan(0);
    }
    expect(hockeyJourneyOriginals(c.event, c.own, c.nowMs).originals.length).toBeGreaterThan(0);
  });

  it("cards: this matchup's rows under another game's id read as no body (CONSTRUCTED same-matchup stand-in)", () => {
    for (const stat of STATS) {
      expect(contributionLadders(stat, c.event, sameMatchup)).toEqual([]);
      expect(hockeyJourneyContribution(stat, c.event, sameMatchup, c.nowMs)).toBeNull();
      expect(hockeyJourneyContribution(stat, c.event, sameMatchup, c.nowMs)).toEqual(
        hockeyJourneyContribution(stat, c.event, null, c.nowMs),
      );
    }
  });

  it("cards: a real other game's body reads as no body (already empty through the team filter; not the guard's proof)", () => {
    for (const stat of STATS) {
      expect(contributionLadders(stat, c.event, c.foreign)).toEqual([]);
      expect(hockeyJourneyContribution(stat, c.event, c.foreign, c.nowMs)).toBeNull();
    }
  });

  it("All props: a real other game's body is exactly no body — no original, id, grade, Details or count", () => {
    const foreign = hockeyJourneyOriginals(c.event, c.foreign, c.nowMs);
    const missing = hockeyJourneyOriginals(c.event, null, c.nowMs);
    expect(foreign).toEqual(missing);
    expect(foreign.originals).toEqual([]);
    expect(foreign.context).toBeNull();
    expect(foreign.scope).toBe(`nhl:${c.event.id}:${c.phase}:originals`);
    const text = JSON.stringify(foreign);
    const ids = servedIds(c.foreign);
    expect(ids.length).toBeGreaterThan(0);
    for (const id of ids) expect(text).not.toContain(id);
    // The same-matchup stand-in too.
    expect(hockeyJourneyOriginals(c.event, sameMatchup, c.nowMs)).toEqual(missing);
  });

  it("All props control: the same foreign bytes under this game's id list originals again (CONSTRUCTED relabel)", () => {
    const control = hockeyJourneyOriginals(c.event, relabelled(c.foreign, c.event.id), c.nowMs);
    expect(control.originals.length).toBeGreaterThan(0);
  });

  it("the composed page with another game's body is the page with none; its own chance, history and About stand", () => {
    const missing = build(null);
    const own = build(c.own);
    for (const body of [c.foreign, sameMatchup]) {
      const page = build(body);
      expect(page).toEqual(missing);
      expect([page.points, page.assists, page.stories, page.originals.originals, page.copy.allPropsLabel]).toEqual([
        null,
        null,
        [],
        [],
        null,
      ]);
      expect(page.headline).toEqual(own.headline);
      expect(page.history).toEqual(own.history);
      expect(page.about).toEqual(own.about);
    }
    expect(own.points).not.toBeNull();
    expect(own.assists).not.toBeNull();
    expect(own.originals.originals.length).toBeGreaterThan(0);
    expect(own.copy.allPropsLabel).not.toBeNull();
    // RELABEL CONTROL at page level: the same-matchup bytes under this game's id are the own page.
    expect(build(relabelled(sameMatchup, c.event.id))).toEqual(own);
  });
});
