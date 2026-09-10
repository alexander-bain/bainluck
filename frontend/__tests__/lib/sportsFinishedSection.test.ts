// ux/1053 — the /sports Finished section's DECISION: which finals it shows, in
// what order, and where the ones it cannot fit are.
//
// Every anchor here offsets from an injected `now` FIRST and never branches on
// the real clock (gotcha #44). `now` is a fixed local-time instant so the
// day-boundary arithmetic is deterministic wherever this runs.

import type { FeedItem } from "../../lib/types";
import { groupFeedIntoSections } from "../../lib/feedSections";
import { isStale } from "../../lib/discover/feedFreshness";
import { applyFinishedCardGuard } from "../../lib/sports/finishedCardGuard";
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

/**
 * live/122 (#4454) — THE REGRESSION THIS SECTION EXISTS TO PREVENT.
 *
 * Alex watched Shelton–Alcaraz (US Open QF, five sets, 4h36m) and could not find
 * it from the Sports tab the next morning. The backend served the card the whole
 * time — `GET /api/feed?limit=40&mode=sports` at 2026-09-09T19:22Z carried event
 * 15306813, `completed`, 16.35h past commence. The frontend deleted it.
 *
 * `applyFinishedCardGuard` ages a settled card out at 8 hours past COMMENCE, so
 * the clock starts when a match begins and not when it ends: the longer the
 * match, the less shelf life its result gets. The real specimen expired 3h24m
 * after the final point. That is the wrong way round on precisely the matches a
 * reader most wants to look back at.
 *
 * So the contract is an INTEGRATION one, and asserting `buildFinishedSection` in
 * isolation would not have caught it: settled games must never reach the guard.
 * Partition after the guard instead of before, or run the guard over the
 * partitioned list "for safety", and the section silently empties again with
 * every one of its own unit tests still green.
 */
describe("#4454 — a long marquee match is still findable the morning after", () => {
  // Local components throughout, so this holds in every timezone.
  const MORNING_AFTER = new Date(2026, 8, 9, 9, 0, 0).getTime();
  // 8pm the previous evening — the real first-ball time, 13h before the read.
  const MARQUEE = new Date(2026, 8, 8, 20, 0, 0).toISOString();
  // An afternoon final from the same day, five hours earlier.
  const EARLIER = new Date(2026, 8, 8, 15, 0, 0).toISOString();

  const marquee = eventItem({ id: 15306813, commence_time: MARQUEE, sport: "tennis_atp_us_open" });
  const earlier = eventItem({ id: 15306814, commence_time: EARLIER });
  const liveGame = eventItem({ id: 15308413, status: "live", commence_time: new Date(MORNING_AFTER - HOUR).toISOString() });

  test("THE CONTROL — the freshness guard really does delete it", () => {
    jest.useFakeTimers().setSystemTime(MORNING_AFTER);
    try {
      // 13 hours past commence against an 8-hour clock. This is the old path,
      // and it must stay red-able: if this ever stops dropping the card, the
      // test below proves nothing.
      expect(isStale(marquee)).toBe(true);
      const guarded = applyFinishedCardGuard([marquee, earlier, liveGame]);
      expect(guarded.items).not.toContain(marquee);
      expect(guarded.agedOut).toContain(marquee);
    } finally {
      jest.useRealTimers();
    }
  });

  test("settled games never reach the guard, so the marquee card survives", () => {
    jest.useFakeTimers().setSystemTime(MORNING_AFTER);
    try {
      const { finished, rest } = partitionFinishedGames([marquee, earlier, liveGame]);
      // Nothing settled is left for the guard to age out.
      expect(applyFinishedCardGuard(rest).agedOut).toEqual([]);
      expect(finished).toEqual([marquee, earlier]);

      const section = buildFinishedSection(finished, MORNING_AFTER);
      expect(section.shown).toContain(marquee);
    } finally {
      jest.useRealTimers();
    }
  });

  test("and it is the FIRST thing in the section, not merely present", () => {
    // Fable's ask, and the reason order is by recency rather than by feed score:
    // the backend ranked this card 23rd of 25. "Findable" means at the top of
    // the results, not somewhere inside them.
    const { finished } = partitionFinishedGames([earlier, marquee]);
    const section = buildFinishedSection(finished, MORNING_AFTER);
    expect(section.shown[0]).toBe(marquee);
  });
});

describe("#4676 / D109 — the section orders by when games ENDED", () => {
  // The production T+30 board, 2026-09-10 03:56Z. Real ids, real clocks.
  // Local components so the day arithmetic holds in every timezone.
  const T_PLUS_30 = new Date(2026, 8, 9, 20, 56, 0).getTime();

  function at(hh: number, mm: number, ss = 0) {
    return new Date(2026, 8, 9, hh, mm, ss).toISOString();
  }

  // began 17:20 local, ENDED 20:26 — the most recently finished game on the
  // board, and the 6th-most recently STARTED.
  const nflOpener = eventItem({
    id: 14780138,
    sport: "americanfootball_nfl",
    commence_time: at(17, 20),
    ended_at: at(20, 26, 32),
  });
  const royals = eventItem({
    id: 15308323,
    commence_time: at(16, 40),
    ended_at: at(20, 3, 5),
  });
  const whiteSox = eventItem({
    id: 15308302,
    commence_time: at(16, 40),
    ended_at: at(19, 44, 4),
  });
  const chicagoFire = eventItem({
    id: 15298466,
    sport: "soccer_usa_mls",
    commence_time: at(17, 30),
    ended_at: at(19, 39, 7),
  });
  const houstonDynamo = eventItem({
    id: 15298467,
    sport: "soccer_usa_mls",
    commence_time: at(17, 30),
    ended_at: at(19, 38, 7),
  });

  // The three that complete the board. Without them the opener is only 3rd by
  // start and the cap does not bite — the control below would pass vacuously.
  const atleticoGoianiense = eventItem({
    id: 15301241,
    sport: "soccer_brazil_serie_b",
    commence_time: at(17, 29),
    ended_at: at(19, 37, 55),
  });
  const austinFc = eventItem({
    id: 15298430,
    sport: "soccer_usa_mls",
    commence_time: at(17, 30),
    ended_at: at(19, 37, 5),
  });
  const minnesotaUnited = eventItem({
    id: 15298473,
    sport: "soccer_usa_mls",
    commence_time: at(17, 30),
    ended_at: at(19, 36, 6),
  });

  // All eight, in the order the feed delivered them (by SCORE), so the
  // sectioner is never handed a list already sorted the way it must produce.
  const BOARD = [
    nflOpener,
    royals,
    whiteSox,
    chicagoFire,
    houstonDynamo,
    atleticoGoianiense,
    austinFc,
    minnesotaUnited,
  ];

  test("THE CONTROL — by START the opener is 6th, which the cap of 4 turns into missing", () => {
    // Not a re-implementation of the old sort for its own sake: without this,
    // the assertion below passes just as well against a board where the two
    // orderings happen to agree, and proves nothing.
    const byStart = [...BOARD].sort(
      (a, b) =>
        new Date((b.data as FeedItem["data"] & { commence_time: string }).commence_time).getTime() -
        new Date((a.data as FeedItem["data"] & { commence_time: string }).commence_time).getTime(),
    );
    expect(byStart.slice(0, FINISHED_SECTION_CAP)).not.toContain(nflOpener);
  });

  test("test_finished_section_uses_delivered_end_time_for_day_order_and_cap", () => {
    const { finished } = partitionFinishedGames(BOARD);
    const section = buildFinishedSection(finished, T_PLUS_30);

    // Through the REAL sectioner, not a local copy of its rule.
    expect(section.shown[0]).toBe(nflOpener);
    expect(section.shown.slice(0, 4)).toEqual([
      nflOpener,
      royals,
      whiteSox,
      chicagoFire,
    ]);
    expect(section.shown).toHaveLength(FINISHED_SECTION_CAP);
    expect(section.cappedMore).toBe(true);
  });

  test("a card with no ended_at still sorts, on its kickoff", () => {
    // The field is present-only and a cached payload can predate the deploy
    // that added it. An unstamped card must not vanish or NaN to the top.
    const unstamped = eventItem({ id: 999, commence_time: at(20, 40) });
    const { finished } = partitionFinishedGames([nflOpener, unstamped]);
    const section = buildFinishedSection(finished, T_PLUS_30);

    expect(section.shown).toHaveLength(2);
    // 20:40 kickoff reads as later than the opener's 20:26 finish.
    expect(section.shown[0]).toBe(unstamped);
  });

  test("a BATCHED end time is broken by the later kickoff, not left arbitrary", () => {
    // Three MLS rows shared completed_at 04:45:41.647571 to the microsecond on
    // 2026-09-10 — one sweep closing several games at once.
    const batched = at(19, 45, 41);
    const early = eventItem({ id: 501, commence_time: at(17, 0), ended_at: batched });
    const late = eventItem({ id: 502, commence_time: at(17, 30), ended_at: batched });

    const { finished } = partitionFinishedGames([early, late]);
    const section = buildFinishedSection(finished, T_PLUS_30);

    expect(section.shown).toEqual([late, early]);
  });

  test("the day bucket is the day it ENDED, and that decides whether it survives the window", () => {
    // Kicks off 10:30pm on the 8th, ends 1:15am on the 9th; read on the 10th.
    // By its START it is TWO days old and falls outside
    // FINISHED_SECTION_MAX_DAY_OFFSET, so it would be dropped as
    // `finished_older_than_yesterday`. By its END it is yesterday, and stays.
    //
    // Deliberately chosen to straddle the window boundary rather than merely to
    // reorder: an assertion about position would pass either way here, which is
    // the trap the rest of this describe block had to be checked against.
    const lateNight = eventItem({
      id: 601,
      commence_time: new Date(2026, 8, 8, 22, 30).toISOString(),
      ended_at: new Date(2026, 8, 9, 1, 15).toISOString(),
    });
    const twoDaysOn = new Date(2026, 8, 10, 9, 0).getTime();

    const { finished } = partitionFinishedGames([lateNight]);
    const section = buildFinishedSection(finished, twoDaysOn);

    expect(section.shown).toContain(lateNight);
    expect(section.dropped).toEqual([]);
  });
});
