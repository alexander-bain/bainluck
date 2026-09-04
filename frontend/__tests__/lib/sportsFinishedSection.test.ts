// ux/1053 — the /sports Finished section's DECISION: which finals it shows, in
// what order, and where the ones it cannot fit are.
//
// Every anchor here offsets from an injected `now` FIRST and never branches on
// the real clock (gotcha #44). `now` is a fixed local-time instant so the
// day-boundary arithmetic is deterministic wherever this runs.

import type { FeedItem } from "../../lib/types";
import { groupFeedIntoSections } from "../../lib/feedSections";
import {
  buildFinishedSection,
  FINISHED_SECTION_CAP,
  leagueResultsLinks,
  partitionFinishedGames,
} from "../../lib/sports/finishedSection";

// 2026-09-03, 13:20 local. Chosen to match the shop Alex ran, and stated as
// local components so "yesterday" means yesterday in the reader's timezone
// rather than in whichever one the runner happens to sit in.
const NOW = new Date(2026, 8, 3, 13, 20, 0).getTime();
const HOUR = 60 * 60 * 1000;

function eventItem(over: Record<string, unknown> = {}, score = 50): FeedItem {
  return {
    type: "event",
    score,
    data: {
      id: 1,
      external_id: "x",
      sport: "baseball_mlb",
      sport_name: "MLB",
      home_team: "Home",
      away_team: "Away",
      commence_time: new Date(NOW - 3 * HOUR).toISOString(),
      status: "completed",
      home_score: 3,
      away_score: 1,
      ...over,
    },
  } as unknown as FeedItem;
}

function futuresItem(id: number): FeedItem {
  return {
    type: "futures",
    score: 10,
    data: { id, name: "Who wins?", status: "open" },
  } as unknown as FeedItem;
}

describe("partitionFinishedGames — D27: the AUTHORITY says finished, nothing else", () => {
  test("completed and closed games come out; live, scheduled and suspended stay", () => {
    const completed = eventItem({ id: 1, status: "completed" });
    const closed = eventItem({ id: 2, status: "closed" });
    const live = eventItem({ id: 3, status: "live" });
    const scheduled = eventItem({ id: 4, status: "scheduled" });
    // live/048: `suspended` asserts NO outcome. Filing it under Finished would
    // claim a result nobody reported — the exact lie that state exists to refuse.
    const suspended = eventItem({ id: 5, status: "suspended" });

    const { finished, rest } = partitionFinishedGames([
      completed,
      live,
      closed,
      scheduled,
      suspended,
    ]);

    expect(finished).toEqual([completed, closed]);
    expect(rest).toEqual([live, scheduled, suspended]);
  });

  test("a near-certain OPEN game is not finished — a price is not an authority", () => {
    const nearCertain = eventItem({
      id: 9,
      status: "live",
      current_odds: { home_probability: 0.995, away_probability: 0.005 },
    });
    expect(partitionFinishedGames([nearCertain]).finished).toEqual([]);
  });

  test("a settled FUTURES market is not a game and stays with the guard", () => {
    const market = futuresItem(77);
    const { finished, rest } = partitionFinishedGames([market]);
    expect(finished).toEqual([]);
    expect(rest).toEqual([market]);
  });

  test("the rest keeps payload order — the feed's ranking survives the split", () => {
    const a = futuresItem(1);
    const b = eventItem({ id: 2, status: "live" });
    const c = futuresItem(3);
    expect(partitionFinishedGames([a, b, c]).rest).toEqual([a, b, c]);
  });
});

describe("buildFinishedSection — today's finals first, then yesterday's", () => {
  test("the order is by day then recency, and it is NOT the order it was handed", () => {
    // The control that makes this test mean something: the input arrives in the
    // feed's SCORE order, which is a different order from the answer. A fixture
    // already sorted correctly would pass against a `buildFinishedSection` that
    // did nothing at all.
    const yesterdayEarly = eventItem({ id: 1, commence_time: iso(-30 * HOUR) }, 99);
    const todayLate = eventItem({ id: 2, commence_time: iso(-1 * HOUR) }, 10);
    const yesterdayLate = eventItem({ id: 3, commence_time: iso(-20 * HOUR) }, 80);
    const todayEarly = eventItem({ id: 4, commence_time: iso(-12 * HOUR) }, 40);

    const input = [yesterdayEarly, yesterdayLate, todayEarly, todayLate];
    expect(ids(input)).toEqual([1, 3, 4, 2]);

    const { shown } = buildFinishedSection(input, NOW);
    expect(ids(shown)).toEqual([2, 4, 3, 1]);
  });

  test("the cap holds one screen back and says which cards it held", () => {
    const items = Array.from({ length: FINISHED_SECTION_CAP + 2 }, (_, i) =>
      eventItem({ id: i + 1, commence_time: iso(-(i + 1) * HOUR) }),
    );
    const section = buildFinishedSection(items, NOW);

    expect(section.shown).toHaveLength(FINISHED_SECTION_CAP);
    expect(section.cappedMore).toBe(true);
    expect(
      section.dropped.filter((d) => d.reason === "finished_section_cap"),
    ).toHaveLength(2);
    // The cards it kept are the most recent ones, not the first ones handed in.
    expect(ids(section.shown)).toEqual([1, 2, 3, 4]);
  });

  test("under the cap, nothing is declared — an uncounted cap reads as coverage", () => {
    const section = buildFinishedSection([eventItem({ id: 1 })], NOW);
    expect(section.cappedMore).toBe(false);
    expect(section.dropped).toEqual([]);
  });

  test("older than yesterday is out, and says so", () => {
    const twoDaysAgo = eventItem({ id: 1, commence_time: iso(-50 * HOUR) });
    const yesterday = eventItem({ id: 2, commence_time: iso(-26 * HOUR) });
    const section = buildFinishedSection([twoDaysAgo, yesterday], NOW);

    expect(ids(section.shown)).toEqual([2]);
    expect(section.dropped).toEqual([
      { item: twoDaysAgo, reason: "finished_older_than_yesterday" },
    ]);
  });

  test("a FINAL dated in the future has no day to file it under (gotcha #14)", () => {
    // `commence_time` sometimes holds a Kalshi close/resolution stamp, which can
    // be a future instant on an already-settled row. The card renders no date
    // for it; the section refuses to sort it under "today" for the same reason.
    const impossible = eventItem({ id: 1, commence_time: iso(+3 * HOUR) });
    const section = buildFinishedSection([impossible], NOW);

    expect(section.shown).toEqual([]);
    expect(section.dropped).toEqual([{ item: impossible, reason: "finished_undated" }]);
  });

  test("an unparseable commence_time is undated, never NaN-sorted to the top", () => {
    const broken = eventItem({ id: 1, commence_time: "not a date" });
    const good = eventItem({ id: 2, commence_time: iso(-2 * HOUR) });
    const section = buildFinishedSection([broken, good], NOW);
    expect(ids(section.shown)).toEqual([2]);
    expect(section.dropped[0].reason).toBe("finished_undated");
  });
});

describe("the sections /sports is left with — Finished cannot sit above Upcoming", () => {
  // The position claim, proved where it is provable. /sports renders
  // `groupFeedIntoSections(<the partitioned rest>)` and then the Finished rail
  // AFTER it, so "below Live Now and Upcoming" holds iff the sectioner can no
  // longer produce a finished bucket. That is a fact about the composition, and
  // it is the half a screenshot cannot pin: on a payload with no upcoming games
  // the two orderings look identical.
  test("no `finished` bucket survives the partition, and live/upcoming keep their order", () => {
    const items = [
      eventItem({ id: 1, status: "completed" }),
      eventItem({ id: 2, status: "scheduled", commence_time: iso(+6 * HOUR) }),
      eventItem({ id: 3, status: "live" }),
      eventItem({ id: 4, status: "closed" }),
      futuresItem(5),
    ];
    const { rest, finished } = partitionFinishedGames(items);

    expect(groupFeedIntoSections(rest).map((s) => s.key)).toEqual([
      "live",
      "upcoming",
      "markets",
    ]);
    // …and the finals are not lost, they are the rail's population.
    expect(ids(finished)).toEqual([1, 4]);
  });

  test("the CONTROL: without the partition the sectioner still files them above Upcoming", () => {
    // The arm that makes the test above mean something. This is the shipped
    // behaviour on every OTHER surface (Discover, /categories/*, My Stuff) and
    // it must not change — `groupFeedIntoSections` was not touched.
    const items = [
      eventItem({ id: 1, status: "completed" }),
      eventItem({ id: 2, status: "scheduled", commence_time: iso(+6 * HOUR) }),
      eventItem({ id: 3, status: "live" }),
    ];
    expect(groupFeedIntoSections(items).map((s) => s.key)).toEqual([
      "live",
      "finished",
      "upcoming",
    ]);
  });
});

describe("leagueResultsLinks — where 'more' goes", () => {
  const sports = [
    {
      slug: "baseball",
      name: "Baseball",
      leagues: [{ slug: "mlb", name: "MLB", sport_keys: ["baseball_mlb"] }],
      showcase_events: [],
    },
    {
      slug: "tennis",
      name: "Tennis",
      leagues: [
        { slug: "atp", name: "ATP Tour", sport_keys: ["tennis_atp"] },
        { slug: "wta", name: "WTA Tour", sport_keys: ["tennis_wta"] },
      ],
      showcase_events: [],
    },
  ] as never;

  test("an exact key resolves to its league page", () => {
    expect(leagueResultsLinks([eventItem({ sport: "baseball_mlb" })], sports)).toEqual([
      { label: "MLB", href: "/sport/baseball/mlb" },
    ]);
  });

  test("a tournament key resolves through its tour — tennis_atp_us_open → ATP Tour", () => {
    expect(
      leagueResultsLinks([eventItem({ sport: "tennis_atp_us_open" })], sports),
    ).toEqual([{ label: "ATP Tour", href: "/sport/tennis/atp" }]);
  });

  test("a league the register does not know contributes NO link", () => {
    // UX-P062 register E5: never a link that goes nowhere. Measured on the
    // 2026-09-03 payload, `soccer_switzerland_superleague` is exactly this case.
    expect(
      leagueResultsLinks([eventItem({ sport: "soccer_switzerland_superleague" })], sports),
    ).toEqual([]);
  });

  test("one league named once, however many of its results were capped away", () => {
    const links = leagueResultsLinks(
      [
        eventItem({ id: 1, sport: "baseball_mlb" }),
        eventItem({ id: 2, sport: "baseball_mlb" }),
        eventItem({ id: 3, sport: "tennis_wta_us_open" }),
      ],
      sports,
    );
    expect(links).toEqual([
      { label: "MLB", href: "/sport/baseball/mlb" },
      { label: "WTA Tour", href: "/sport/tennis/wta" },
    ]);
  });

  test("the list stops at the limit — a declaration is a sentence, not a nav bar", () => {
    const links = leagueResultsLinks(
      [
        eventItem({ id: 1, sport: "baseball_mlb" }),
        eventItem({ id: 2, sport: "tennis_atp" }),
        eventItem({ id: 3, sport: "tennis_wta" }),
      ],
      sports,
      2,
    );
    expect(links.map((l) => l.label)).toEqual(["MLB", "ATP Tour"]);
  });

  test("no register yet — no links, and the caller still declares its cap", () => {
    expect(leagueResultsLinks([eventItem({ sport: "baseball_mlb" })], undefined)).toEqual(
      [],
    );
  });

  test("the longest registered key wins a prefix contest", () => {
    const overlapping = [
      {
        slug: "tennis",
        name: "Tennis",
        leagues: [
          { slug: "atp", name: "ATP Tour", sport_keys: ["tennis"] },
          { slug: "wta", name: "WTA Tour", sport_keys: ["tennis_wta"] },
        ],
        showcase_events: [],
      },
    ] as never;
    expect(
      leagueResultsLinks([eventItem({ sport: "tennis_wta_us_open" })], overlapping),
    ).toEqual([{ label: "WTA Tour", href: "/sport/tennis/wta" }]);
  });
});

function iso(offsetMs: number): string {
  return new Date(NOW + offsetMs).toISOString();
}

function ids(items: FeedItem[]): number[] {
  return items.map((i) => (i.data as { id: number }).id);
}
