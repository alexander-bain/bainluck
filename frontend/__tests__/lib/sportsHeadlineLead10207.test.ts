// #10207 — /sports leads with its headlines, not with whatever happens to be live.
//
// The fixture IS Alex's 2026-10-02 slate: the anonymous served payload saved at
// intake (built_at 16:03:14Z), trimmed of pricing/image fields only. Every
// assertion runs through the real sectioner and the real Finished builder.

import type { FeedEventData, FeedItem } from "../../lib/types";
import { groupFeedIntoSections, type FeedSection } from "../../lib/feedSections";
import {
  buildFinishedSection,
  FINISHED_SECTION_CAP,
  partitionFinishedGames,
} from "../../lib/sports/finishedSection";
import { FINISHED_LOOKUP_LIMIT } from "../../lib/sports/feedKey";
import {
  headlineBand,
  isHeadlineCard,
  orderSportsGameSections,
  TOP_GAMES_CAP,
} from "../../lib/sports/headline";
import slate from "../fixtures/sportsEditorialSlate10207.20261002.json";

const BUILT_AT = Date.UTC(2026, 9, 2, 16, 3, 14);
const PAGE_ONE = slate.page_one as unknown as FeedItem[];
const FINISHED_POOL = slate.finished as unknown as FeedItem[];

const YANKEES_RAYS = 15322539;
const WHITE_SOX_GUARDIANS = 15322462;
const PADRES_BREWERS = 15322620;
const LIIGA_KARPAT = 15322389;
const STEELERS_BROWNS_TNF = 14780550;
const SHARKS_KINGS = 15319666;

function idOf(item: FeedItem): number | string {
  const d = item.data as unknown as { id?: number; key?: string };
  return d.id ?? d.key ?? "";
}

function sportOf(item: FeedItem): string {
  return (item.data as FeedEventData).sport ?? "";
}

/** The page's own path: the sectioner, minus Top Markets, as /sports does it. */
function sportsGameSections(items: FeedItem[]): FeedSection[] {
  const { rest } = partitionFinishedGames(items);
  return groupFeedIntoSections(rest).filter((s) => s.key !== "markets");
}

function eventItem(id: number, status: string, tags: string[]): FeedItem {
  return {
    type: "event",
    score: 50,
    data: {
      id,
      sport: "baseball_mlb",
      home_team: "H",
      away_team: "A",
      status,
      commence_time: new Date(BUILT_AT + 3_600_000).toISOString(),
      event_tags: tags,
    },
  } as unknown as FeedItem;
}

beforeEach(() => {
  // `isTournamentLive` reads the real clock; pin it to the moment the slate
  // was served so the golf cards file where they filed for Alex.
  jest.useFakeTimers().setSystemTime(BUILT_AT);
});
afterEach(() => jest.useRealTimers());

describe("the fixture is the slate Alex saw", () => {
  test("the ids this file names are where the intake says they were", () => {
    const ids = PAGE_ONE.map(idOf);
    expect(ids[0]).toBe(YANKEES_RAYS);
    expect(ids).toContain(WHITE_SOX_GUARDIANS);
    expect(ids).toContain(PADRES_BREWERS);
    expect(ids[19]).toBe(LIIGA_KARPAT);
    expect(FINISHED_POOL.map(idOf)).toContain(STEELERS_BROWNS_TNF);
  });

  test("THE CONTROL — the sectioner alone opens on seven minor live cards", () => {
    const sections = sportsGameSections(PAGE_ONE);
    expect(sections[0].key).toBe("live");
    // Nothing in it is a headline: tier-2 MMA, fall-series golf, tier-4 soccer
    // and Liiga. If this ever stops being true the slate no longer testifies.
    expect(sections[0].items.some(isHeadlineCard)).toBe(false);
    expect(sections[0].items.map(idOf)).toContain(LIIGA_KARPAT);
    const upcoming = sections.find((s) => s.key === "upcoming")!;
    expect(upcoming.items.map(idOf)).toContain(YANKEES_RAYS);
  });
});

describe("orderSportsGameSections — section priority on the real slate", () => {
  test("the page opens on Top Games, led by the MLB postseason", () => {
    const sections = orderSportsGameSections(sportsGameSections(PAGE_ONE));
    expect(sections[0].key).toBe("top-games");
    const top = sections[0].items.map(idOf);
    expect(top.length).toBeLessThanOrEqual(TOP_GAMES_CAP);
    expect(top.slice(0, 2)).toEqual([YANKEES_RAYS, WHITE_SOX_GUARDIANS]);
    expect(sections[0].items.every(isHeadlineCard)).toBe(true);
  });

  test("THE CONTROL — the first four upcoming headlines in served order drop a postseason game", () => {
    const upcoming = sportsGameSections(PAGE_ONE).find((s) => s.key === "upcoming")!;
    const servedFirstFour = upcoming.items.filter(isHeadlineCard).slice(0, TOP_GAMES_CAP).map(idOf);
    expect(servedFirstFour).toContain(SHARKS_KINGS);
    expect(servedFirstFour).not.toContain(PADRES_BREWERS);
  });

  test("postseason headlines take the Top Games slots before a regular-season one", () => {
    const sections = orderSportsGameSections(sportsGameSections(PAGE_ONE));
    const top = sections[0].items.map(idOf);
    expect(top).toContain(PADRES_BREWERS);
    expect(top).not.toContain(SHARKS_KINGS);
    expect(sections[0].items.every((item) => headlineBand(item) === 0)).toBe(true);
  });

  test("Live Now is second, whole — the minor live slate stays one scroll away", () => {
    const before = sportsGameSections(PAGE_ONE).find((s) => s.key === "live")!;
    const sections = orderSportsGameSections(sportsGameSections(PAGE_ONE));
    expect(sections[1].key).toBe("live");
    expect(sections[1].items.map(idOf).sort()).toEqual(before.items.map(idOf).sort());
  });

  test("lifted cards are MOVED, not copied, and nothing is lost", () => {
    const before = sportsGameSections(PAGE_ONE).flatMap((s) => s.items.map(idOf));
    const after = orderSportsGameSections(sportsGameSections(PAGE_ONE)).flatMap((s) =>
      s.items.map(idOf),
    );
    expect(after).toHaveLength(before.length);
    expect(new Set(after)).toEqual(new Set(before));
  });

  test("the rest of Upcoming keeps its served order", () => {
    const before = sportsGameSections(PAGE_ONE).find((s) => s.key === "upcoming")!;
    const sections = orderSportsGameSections(sportsGameSections(PAGE_ONE));
    const lifted = new Set(sections[0].items.map(idOf));
    const after = sections.find((s) => s.key === "upcoming")!;
    expect(after.items.map(idOf)).toEqual(
      before.items.map(idOf).filter((id) => !lifted.has(id)),
    );
    expect(after.count).toBe(after.items.length);
  });
});

describe("orderSportsGameSections — the two slates it must leave alone", () => {
  test("a live headline keeps Live Now first, and leads inside it", () => {
    const minorLive = eventItem(1, "live", ["tier:4", "sport:hockey"]);
    const majorLive = eventItem(2, "live", ["tier:1", "importance:playoff"]);
    const majorNext = eventItem(3, "scheduled", ["tier:1", "importance:playoff"]);
    const sections = orderSportsGameSections(
      sportsGameSections([minorLive, majorNext, majorLive]),
    );
    expect(sections.map((s) => s.key)).toEqual(["live", "upcoming"]);
    expect(sections[0].items.map(idOf)).toEqual([2, 1]);
  });

  test("Top Games: postseason first in served order, regular-season headlines fill what is left", () => {
    const regular = eventItem(1, "scheduled", ["tier:1", "importance:regular_season"]);
    const playoffA = eventItem(2, "scheduled", ["tier:1", "importance:playoff"]);
    const minor = eventItem(3, "scheduled", ["tier:4"]);
    const playoffB = eventItem(4, "scheduled", ["tier:1", "importance:playoff"]);
    const sections = orderSportsGameSections(
      sportsGameSections([regular, playoffA, minor, playoffB]),
    );
    expect(sections[0].key).toBe("top-games");
    expect(sections[0].items.map(idOf)).toEqual([2, 4, 1]);
    expect(sections[1].items.map(idOf)).toEqual([3]);
  });

  test("a quiet slate invents nothing — no headline, no Top Games, same order", () => {
    const sections = sportsGameSections([
      eventItem(1, "live", ["tier:4"]),
      eventItem(2, "scheduled", ["tier:3"]),
    ]);
    expect(orderSportsGameSections(sections)).toEqual(sections);
  });

  test("an exhibition is not a headline even at tier 1", () => {
    expect(isHeadlineCard(eventItem(1, "scheduled", ["tier:1", "importance:exhibition"]))).toBe(
      false,
    );
  });

  test("a Grand Slam match is a headline; a tour-stop match is not (#4454)", () => {
    expect(isHeadlineCard(eventItem(1, "completed", ["sport:tennis", "tier:2"]))).toBe(true);
    expect(isHeadlineCard(eventItem(2, "completed", ["sport:tennis", "tier:4"]))).toBe(false);
    // Tier 2 outside tennis (NCAAF, MLS, WNBA regular season) is not.
    expect(isHeadlineCard(eventItem(3, "completed", ["sport:football", "tier:2"]))).toBe(false);
  });
});

describe("buildFinishedSection — headline finals take the slots first", () => {
  test("THE CONTROL — by day and recency alone, last night's TNF final is capped away", () => {
    // The same function, with the tags stripped, is the pre-#10207 order.
    const untagged = FINISHED_POOL.map(
      (item) => ({ ...item, data: { ...item.data, event_tags: [] } }) as unknown as FeedItem,
    );
    const section = buildFinishedSection(untagged, BUILT_AT);
    expect(section.shown.map(idOf)).not.toContain(STEELERS_BROWNS_TNF);
  });

  test("with the tags, the NFL and MLB postseason finals are shown and no tour-stop tennis is", () => {
    const section = buildFinishedSection(FINISHED_POOL, BUILT_AT);
    expect(section.shown).toHaveLength(FINISHED_SECTION_CAP);
    expect(section.shown.map(idOf)).toContain(STEELERS_BROWNS_TNF);
    expect(section.shown.map(sportOf)).toContain("baseball_mlb");
    expect(section.shown.every(isHeadlineCard)).toBe(true);
    expect(section.shown.map(sportOf).some((s) => s.startsWith("tennis_"))).toBe(false);
  });

  test("the finals it held back are still declared, with the cap's reason", () => {
    const section = buildFinishedSection(FINISHED_POOL, BUILT_AT);
    expect(section.cappedMore).toBe(true);
    const capped = section.dropped.filter((d) => d.reason === "finished_section_cap");
    expect(capped.map((d) => sportOf(d.item)).some((s) => s.startsWith("tennis_"))).toBe(true);
  });

  test("a postseason final outranks a later-ending regular-season headline", () => {
    const series = eventItem(1, "completed", ["tier:1", "importance:playoff"]);
    const regular = eventItem(2, "completed", ["tier:1", "importance:regular_season"]);
    (series.data as FeedEventData).ended_at = new Date(BUILT_AT - 3 * 3_600_000).toISOString();
    (regular.data as FeedEventData).ended_at = new Date(BUILT_AT - 1 * 3_600_000).toISOString();
    const section = buildFinishedSection([regular, series], BUILT_AT);
    expect(section.shown.map(idOf)).toEqual([1, 2]);
  });

  test("on the real slate the MLB postseason final is shown", () => {
    const section = buildFinishedSection(FINISHED_POOL, BUILT_AT);
    expect(section.shown.map(idOf)).toContain(15322407);
  });

  test("two headline finals still order by when they ENDED, not by tier", () => {
    const slam = {
      ...eventItem(1, "completed", ["sport:tennis", "tier:2"]),
    } as FeedItem;
    (slam.data as FeedEventData).ended_at = new Date(BUILT_AT - 1 * 3_600_000).toISOString();
    const ballgame = eventItem(2, "completed", ["tier:1"]);
    (ballgame.data as FeedEventData).ended_at = new Date(BUILT_AT - 2 * 3_600_000).toISOString();
    (ballgame.data as FeedEventData).commence_time = new Date(BUILT_AT - 5 * 3_600_000).toISOString();
    (slam.data as FeedEventData).commence_time = new Date(BUILT_AT - 5 * 3_600_000).toISOString();
    const section = buildFinishedSection([ballgame, slam], BUILT_AT);
    expect(section.shown.map(idOf)).toEqual([1, 2]);
  });
});

describe("the deferred lookup reaches the headline finals it is now ordering", () => {
  test("its window clears the MLB postseason final's measured position", () => {
    // Anonymous `include_futures=false` read, 2026-10-02 ~16:40Z: TNF at 45,
    // the Phillies–Braves postseason final at 60. A 40-deep window — the old
    // value — carried neither, so headline-first had nothing to put first.
    const MLB_POSTSEASON_FINAL_POSITION = 60;
    expect(FINISHED_LOOKUP_LIMIT).toBeGreaterThan(MLB_POSTSEASON_FINAL_POSITION);
  });
});
