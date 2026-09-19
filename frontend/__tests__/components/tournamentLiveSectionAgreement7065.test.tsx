// #7065 — A `● LIVE` CARD MUST NOT BE FILED UNDER `📅 Upcoming`.
//
// ═══ WHAT A READER SAW ═══
//
// `https://bainluck.com/sports` at 390px, 2026-09-18 23:33Z, production commit
// `6044e4b4`. Under the heading `📅 Upcoming 8`, the FIRST card:
//
//     🏌 PGA Tour   ● LIVE
//     Biltmore Championship Asheville
//     27.9%  Neal Shipley — Leader +25.0 pts today
//
// One screen, two answers. The "Live Now 10" section above it did not contain it.
//
// ═══ WHY IT COULD NOT HAVE BEEN OTHERWISE ═══
//
// Two predicates decided "is this tournament live" and only one read evidence
// that exists. `TournamentCard._isLive` decided on the schedule WINDOW; the
// section bucketers in `lib/feedSections.ts` and `app/my-stuff/page.tsx` decided
// on `schedule_status === "in-progress"` ALONE — a string this repo had already
// measured as never occurring (`__tests__/capture/
// golfTournamentCardLiveWindowCapture.test.tsx:54`, 0 of 94 `pga_schedule` rows
// and 0 of 7 tournaments, 2026-08-29). It is 0 of 7 in the fixture below and was
// 0 of 2 on `GET /api/feed?limit=100` at 2026-09-19T01:57Z, re-measured for this
// fix rather than inherited.
//
// A dead test makes its `else` unconditional: NO tournament could reach Live Now
// on those surfaces, whatever it was doing. So this is not a boundary bug that
// needs the right clock to see — the two answers could never agree.
//
// ═══ WHAT THE FIX IS, AND WHAT IT DELIBERATELY IS NOT ═══
//
// `_isLive`'s body moved to `lib/tournamentLive.ts` UNCHANGED and all three
// readers call it. The badge's semantics are untouched on purpose — section 4
// is what proves that, by requiring the shared function to agree with a verbatim
// copy of the pre-fix body on every tournament in the banked payload at eight
// clocks. Deciding what "live" SHOULD mean is a different ship from making one
// page stop contradicting itself, and the card's meaning is the one that was
// already right.
//
// ═══ THE INSTRUMENT IS PROVEN BEFORE IT IS TRUSTED ═══
//
// `theLegacyBucketerIsWrongInExactlyThisWay` runs the verbatim pre-fix bucketer
// through the identical probe and REQUIRES it to come back broken — the card
// saying LIVE while the section says upcoming. A discriminator nobody has
// watched discriminate is a decoration (UX-P180's rule, and this file inherits
// it along with the harness).
//
// Both directions per gotcha #43: every "must reach Live Now" case has a sibling
// that must NOT, because a bucketer that sent every tournament to Live Now would
// satisfy the first half and break the product.
//
// ═══ ONE LIMIT, STATED ═══
//
// Section 5 asserts My Stuff's copy at the SOURCE, not through a render. That
// page needs auth, SWR and pinned-entity hooks to mount, and #2060's lesson is
// that a source grep cannot tell a rendered field from a declared one — so the
// source assertion here claims only what it can: that this surface no longer
// carries its own copy of the dead predicate. The behaviour it then inherits is
// what sections 1–4 prove.
//
//   cd frontend && npx jest --testPathPatterns=tournamentLiveSectionAgreement7065

import React from "react";
import { renderToStaticMarkup } from "react-dom/server";
import fs from "fs";
import path from "path";

import FeedCard from "@/components/FeedCard";
import { groupFeedIntoSections } from "@/lib/feedSections";
import { isTournamentLive } from "@/lib/tournamentLive";
import type { FeedItem, FeedTournamentData, GolfResponse, GolfTournament } from "@/lib/types";

jest.mock("next/link", () => {
  const ReactLib = require("react");
  return {
    __esModule: true,
    default: ({ href, children, ...props }: { href: string; children: React.ReactNode }) =>
      ReactLib.createElement("a", { href, ...props }, children),
  };
});

jest.mock("@/components/Analytics", () => ({
  useAnalyticsContext: () => ({ track: () => {} }),
}));

import golfBefore from "../fixtures/uxp179_golf_before.json";

const SERVED = golfBefore as unknown as GolfResponse;

function tournament(key: string): GolfTournament {
  const t = SERVED.tournaments.find((x) => x.key === key);
  if (!t) throw new Error(`fixture no longer carries ${key}`);
  return t;
}

/** Window Thu 2026-08-27 → Sun 2026-08-30, and 10 golfers moving ≥1pp. */
const TOUR_CHAMPIONSHIP = tournament("tour_championship");
/** Window Thu 2026-09-03 → Sun 2026-09-06, ZERO movement: the window is sole decider. */
const OMEGA = tournament("omega_european_masters");
/** No window, 3 golfers moving ≥1pp — the price-signal arm says live. */
const ASIA = tournament("asia_masters_2026");
/** No window, no movement — nothing says live, so nothing may file it as live. */
const MAJOR_2027 = tournament("golfers_to_win_a_pga_tour_major_in_2027");

/**
 * The specimen in the photograph, verbatim from `GET /api/feed?limit=100` at
 * 2026-09-19T01:57Z. `schedule_status: "upcoming"` beside a window that opened
 * two days ago is the contradiction IN THE PAYLOAD that the card already knew
 * to ignore and the bucketer did not.
 */
const BILTMORE: FeedTournamentData = {
  key: "biltmore_championship_asheville",
  name: "Biltmore Championship Asheville",
  slug: "biltmore-championship-asheville",
  tour: "pga",
  tour_label: "PGA Tour",
  is_major: false,
  venue: "The Cliffs at Walnut Cove",
  location: null,
  start_date: "2026-09-17T00:00:00+00:00",
  end_date: "2026-09-20T00:00:00+00:00",
  schedule_status: "upcoming",
  commence_time: "2026-09-12T16:01:00+00:00",
  resolution_date: "2026-09-20T00:00:00+00:00",
  golfers: [
    { name: "Neal Shipley", probability: 0.279, rank: 1, movement_24h: 0.2535 },
    { name: "Chris Gotterup", probability: 0.121, rank: 2, movement_24h: 0.2076 },
    { name: "Ryan Gerard", probability: 0.084, rank: 3, movement_24h: null },
  ],
  market_ids: [1],
  source_count: 1,
  is_marquee: false,
  marquee_whathit: false,
};

/** Inside Biltmore's window — the minute of the photograph. */
const DURING_BILTMORE = "2026-09-18T23:33:00Z";

function at<T>(now: string, fn: () => T): T {
  jest.useFakeTimers({ now: new Date(now) });
  try {
    return fn();
  } finally {
    jest.useRealTimers();
  }
}

function toFeedData(t: GolfTournament): FeedTournamentData {
  return {
    key: t.key,
    name: t.name,
    slug: t.slug,
    tour: t.tour,
    tour_label: t.tour_label,
    is_major: t.is_major,
    venue: t.venue,
    location: t.location,
    start_date: t.start_date,
    end_date: t.end_date,
    schedule_status: t.schedule_status,
    commence_time: t.commence_time,
    resolution_date: t.resolution_date,
    golfers: t.golfers.map((g) => ({
      name: g.name,
      probability: g.probability,
      rank: g.rank,
      movement_24h: g.movement_24h,
    })),
    market_ids: t.market_ids,
    source_count: 1,
  };
}

function item(data: FeedTournamentData): FeedItem {
  return { type: "tournament", score: 50, reason: "", headline: "", data } as unknown as FeedItem;
}

/**
 * The live badge. `animate-pulse` is the pulsing dot and nothing else in this
 * card is — reading the label out of that element rather than out of the whole
 * card matters, because the card also prints leaderboard prose like
 * "End of Round 3" that a looser probe mistakes for the badge (UX-P180's note).
 */
const BADGE = /animate-pulse"><\/span>([^<]*)<\/span>/;

/** Renders the REAL /sports leaf: FeedCard's adapter into the real TournamentCard. */
function cardSaysLive(data: FeedTournamentData, now: string): boolean {
  const markup = at(now, () => renderToStaticMarkup(<FeedCard item={item(data)} />));
  return BADGE.test(markup);
}

/** Runs the REAL bucketer on the SAME payload and reports which section took it. */
function sectionKeyFor(data: FeedTournamentData, now: string): string {
  const sections = at(now, () => groupFeedIntoSections([item(data)]));
  const holder = sections.find((s) => s.items.length > 0);
  if (!holder) throw new Error("the bucketer dropped the tournament entirely");
  return holder.key;
}

/* ═══════════════════════════════════════════════════════════════════════ */
/* 1 · THE PREMISE — the string the bucketer tested for does not occur, so   */
/*     its `else` was unconditional.                                         */
/* ═══════════════════════════════════════════════════════════════════════ */

describe("#7065 · the premise", () => {
  it("`schedule_status === 'in-progress'` occurs 0 times in the banked payload", () => {
    expect(SERVED.tournaments).toHaveLength(7);
    expect(
      SERVED.tournaments.filter((t) => t.schedule_status === "in-progress"),
    ).toHaveLength(0);
  });

  it("the photographed specimen says `upcoming` while its own window is open", () => {
    // This is the contradiction the card already resolved correctly. If the
    // payload is ever fixed upstream this assertion is what says so.
    expect(BILTMORE.schedule_status).toBe("upcoming");
    const start = new Date(BILTMORE.start_date as string).getTime();
    const end = new Date(BILTMORE.end_date as string).getTime() + 86400000;
    const now = new Date(DURING_BILTMORE).getTime();
    expect(now).toBeGreaterThanOrEqual(start);
    expect(now).toBeLessThan(end);
  });
});

/* ═══════════════════════════════════════════════════════════════════════ */
/* 2 · THE INVARIANT — one payload, both consumers, and they agree.          */
/* ═══════════════════════════════════════════════════════════════════════ */

describe("#7065 · the card and the section it is filed under cannot disagree", () => {
  const CASES: { label: string; data: FeedTournamentData; now: string; live: boolean }[] = [
    {
      label: "the photographed Biltmore card, inside its window",
      data: BILTMORE,
      now: DURING_BILTMORE,
      live: true,
    },
    {
      label: "Tour Championship on its FINAL day (the UX-P180 boundary)",
      data: toFeedData(TOUR_CHAMPIONSHIP),
      now: "2026-08-30T18:00:00Z",
      live: true,
    },
    {
      label: "Omega, no movement at all, mid-window — the window is sole decider",
      data: toFeedData(OMEGA),
      now: "2026-09-04T12:00:00Z",
      live: true,
    },
    {
      label: "Asia Masters — no window, price signal says live",
      data: toFeedData(ASIA),
      now: DURING_BILTMORE,
      live: true,
    },
    {
      label: "Biltmore BEFORE its window opens",
      data: BILTMORE,
      now: "2026-09-15T12:00:00Z",
      live: false,
    },
    {
      label: "Tour Championship the day AFTER its last day — finished, not live",
      data: toFeedData(TOUR_CHAMPIONSHIP),
      now: "2026-08-31T12:00:00Z",
      live: false,
    },
    {
      label: "a season-long futures row — no window, no movement, never live",
      data: toFeedData(MAJOR_2027),
      now: DURING_BILTMORE,
      live: false,
    },
  ];

  it.each(CASES)("$label", ({ data, now, live }) => {
    const badge = cardSaysLive(data, now);
    const section = sectionKeyFor(data, now);

    // The claim under test, stated as one sentence: whatever the badge says,
    // the heading above it says the same.
    expect(badge).toBe(live);
    expect(section === "live").toBe(live);

    // And said again as the reader's own complaint, so a future edit that
    // flipped BOTH in the same wrong direction still has to face this line.
    if (badge) expect(section).toBe("live");
    else expect(section).not.toBe("live");
  });

  it("a live tournament actually reaches Live Now alongside a live game", () => {
    // Gotcha #43, the adjacent-surface direction: the fix must not empty
    // Upcoming or crowd out the section's existing occupants.
    const notYet = { ...BILTMORE, start_date: "2026-09-25T00:00:00+00:00", end_date: "2026-09-28T00:00:00+00:00" };
    const sections = at(DURING_BILTMORE, () =>
      groupFeedIntoSections([item(BILTMORE), item(notYet)]),
    );
    const live = sections.find((s) => s.key === "live");
    const upcoming = sections.find((s) => s.key === "upcoming");
    expect(live?.items).toHaveLength(1);
    expect(upcoming?.items).toHaveLength(1);
    expect((live?.items[0].data as FeedTournamentData).key).toBe(BILTMORE.key);
  });
});

/* ═══════════════════════════════════════════════════════════════════════ */
/* 3 · THE INSTRUMENT — the pre-fix bucketer must come back broken.          */
/* ═══════════════════════════════════════════════════════════════════════ */

describe("#7065 · theLegacyBucketerIsWrongInExactlyThisWay", () => {
  /** `lib/feedSections.ts:124-131` before this fix, verbatim. */
  function legacySectionKeyFor(data: FeedTournamentData): string {
    const td = data as unknown as Record<string, unknown>;
    return td.schedule_status === "in-progress" ? "live" : "upcoming";
  }

  it("files the photographed LIVE card under upcoming — the defect, reproduced", () => {
    expect(cardSaysLive(BILTMORE, DURING_BILTMORE)).toBe(true);
    expect(legacySectionKeyFor(BILTMORE)).toBe("upcoming");
    // The fixed bucketer, same payload, same minute.
    expect(sectionKeyFor(BILTMORE, DURING_BILTMORE)).toBe("live");
  });

  it("could not have filed ANY of these tournaments as live, whatever they were doing", () => {
    const all = [BILTMORE, ...SERVED.tournaments.map(toFeedData)];
    expect(all.every((t) => legacySectionKeyFor(t) === "upcoming")).toBe(true);
    // ...while the shared decider separates them, which is what makes the
    // assertion above a finding rather than an accident of this fixture.
    const fixed = at(DURING_BILTMORE, () => all.map((t) => isTournamentLive(t)));
    expect(fixed).toContain(true);
    expect(fixed).toContain(false);
  });
});

/* ═══════════════════════════════════════════════════════════════════════ */
/* 4 · FIDELITY — the badge did not change meaning when its body moved.      */
/* ═══════════════════════════════════════════════════════════════════════ */

describe("#7065 · the extracted decider is the pre-fix one, arm for arm", () => {
  /** `components/TournamentCard.tsx::_isLive` before this fix, verbatim. */
  function legacyIsLive(t: GolfTournament | FeedTournamentData): boolean {
    const now = new Date();
    if (t.start_date && t.end_date) {
      const start = new Date(t.start_date);
      const endOfLastDay = new Date(new Date(t.end_date).getTime() + 86400000);
      return now >= start && now < endOfLastDay;
    }
    if (t.schedule_status === "in-progress") return true;
    return t.golfers.some(
      (g) => g.movement_24h !== null && Math.abs(g.movement_24h as number) >= 0.01,
    );
  }

  const CLOCKS = [
    "2026-08-26T23:59:00Z", // the instant before Tour Championship opens
    "2026-08-27T00:00:00Z", // the instant it opens
    "2026-08-30T00:00:00Z", // the start of its final day (UX-P180's regression)
    "2026-08-30T23:59:00Z", // the end of its final day
    "2026-08-31T00:00:00Z", // the instant it retires
    "2026-09-04T12:00:00Z",
    DURING_BILTMORE,
    "2026-09-25T12:00:00Z",
  ];

  it("agrees with the pre-fix body on every tournament at every clock", () => {
    const population = [BILTMORE, ...SERVED.tournaments.map(toFeedData)];
    let disagreements = 0;
    let liveVerdicts = 0;
    for (const now of CLOCKS) {
      at(now, () => {
        for (const t of population) {
          const before = legacyIsLive(t);
          const after = isTournamentLive(t);
          if (before !== after) disagreements += 1;
          if (after) liveVerdicts += 1;
        }
      });
    }
    expect(disagreements).toBe(0);
    // A predicate that answered `false` everywhere would also disagree zero
    // times with itself, so the population has to actually exercise both.
    expect(liveVerdicts).toBeGreaterThan(0);
    expect(liveVerdicts).toBeLessThan(CLOCKS.length * population.length);
  });
});

/* ═══════════════════════════════════════════════════════════════════════ */
/* 5 · THE THIRD READER — My Stuff no longer carries its own copy.           */
/* ═══════════════════════════════════════════════════════════════════════ */

describe("#7065 · no surface keeps a private copy of the dead predicate", () => {
  const read = (p: string) =>
    fs.readFileSync(path.join(__dirname, "..", "..", p), "utf8");

  it.each([
    ["app/my-stuff/page.tsx"],
    ["lib/feedSections.ts"],
  ])("%s decides the tournament bucket with the shared function", (file) => {
    const src = read(file);
    expect(src).toContain('from "@/lib/tournamentLive"');
    expect(src).toContain("isTournamentLive(td)");
    // The dead string may still be NAMED in the comment that explains why it is
    // dead; what it may not be is the thing an `if` is branching on.
    expect(src).not.toMatch(/if\s*\(\s*td\.schedule_status\s*===\s*"in-progress"\s*\)/);
  });

  it("the shared decider is the only place the bucket decision lives", () => {
    const src = read("lib/tournamentLive.ts");
    expect(src).toContain("export function isTournamentLive");
    // The price-signal threshold, the one constant a careless edit would round.
    expect(src).toContain("0.01");
  });
});
