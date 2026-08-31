/**
 * UX-P180 — THE GOLF TOURNAMENT CARD STOPS GOING DARK DURING ITS OWN FINAL ROUND
 * (and stops pulsing LIVE for a tournament that finished yesterday).
 *
 * ═══ WHAT THIS IS ═══
 *
 * `/api/golf` serves schedule dates as CALENDAR DATES stamped at midnight UTC.
 * Measured on the banked payload: 188 of 188 `pga_schedule` stamps and 6 of 6
 * tournament windows are exactly `T00:00:00+00:00`. Nothing in that population
 * is a time of day — a golf tournament runs Thursday to Sunday, and Thursday is
 * what the field says.
 *
 * `_isLive` in `components/TournamentCard.tsx` compared `now` against those raw
 * midnight instants:
 *
 *     return now >= new Date(t.start_date) && now <= new Date(t.end_date);
 *
 * so the window CLOSED at the start of the final day. The card went dark — no
 * pulse, just a date range — for the whole of the final round. That is wrong in
 * every timezone, UTC included. The root is that a calendar date is a DAY when
 * it is COMPARED, not only when it is PRINTED.
 *
 * The second symptom shares the function but not the arm. The window was the
 * LAST of three fallbacks, so it was unreachable whenever any golfer had moved
 * ≥1pp in 24h — and residual 24h movement outlives a tournament by a day. A
 * finished tournament therefore kept a pulsing red LIVE dot. The sibling
 * deciders of this same boundary that EXIST ON MASTER treat the window as a
 * VETO instead:
 *
 *   app/categories/golf/tournaments/[slug]/page.tsx  isTournamentLive  (end +1d)
 *   app/categories/golf/tournaments/[slug]/page.tsx  isCompleted       (end +24h)
 *
 * `_isLive` was the outlier. It now agrees with them.
 *
 * ⚠️ A THIRD SIBLING EXISTS BUT IS NOT ON MASTER.
 * `components/golf/CurrentEventBanner.tsx` (UX-P179, same window, end +24h) is
 * stranded on the unmerged `program/ux-125` stack. This file was authored above
 * it and carried a fifth section asserting that the card and the banner retire
 * the tournament at the SAME instant, driven through both real components on one
 * payload. That section cannot run here, so it was removed rather than weakened
 * — and `theBannerAgreementIsOwed` below FAILS the moment the banner lands, so
 * the agreement is restored by whoever lands it instead of being lost. See
 * section 5.
 *
 * ═══ THE READER COUNT ═══
 *
 * SIX call sites of this card across FIVE files — `app/categories/golf/page.tsx`,
 * `app/sport/[sport]/page.tsx`, three in `app/sport/[sport]/[league]/page.tsx`,
 * and `components/FeedCard.tsx` (the Discover feed). Five of the six pass no
 * `whatHit`, so nothing suppressed the stale pulse on those surfaces.
 *
 * Measured on `GET /api/golf` and `GET /api/feed?limit=100`, 2026-08-29:
 *
 *   - `schedule_status === "in-progress"` NEVER occurs: 0 of 94 `pga_schedule`
 *     rows and 0 of 7 tournaments. The first arm of `_isLive` is dead in
 *     production, so the window and the price signal decide everything.
 *   - 3 of the 7 served tournaments carry a schedule window; ALL of their
 *     stamps are midnight UTC, so all three lose their final day.
 *   - 1 of those 3 (Omega European Masters) has ZERO golfers moving ≥1pp, so
 *     the window is already its sole decider — unconditionally, today, on both
 *     `/api/golf` and the Discover feed, which served 7 tournament cards.
 *
 * The payload is banked verbatim at `__tests__/fixtures/uxp179_golf_before.json`
 * (UX-P179's, re-read 2026-08-29 and confirmed identical on every field that
 * decides the window; only the volatile per-golfer movement counts had drifted).
 *
 * ═══ WHY THE GUARDS LOOK LIKE THIS ═══
 *
 * Unlike UX-P179's, this defect is NOT hidden by `TZ=UTC` — both symptoms are
 * instant comparisons, so they are wrong in every zone and the CI gate can see
 * them directly. The suite is still run under both zones, because the component
 * is date-adjacent and the next edit may not be.
 *
 * The boundary is probed by RENDERING THE REAL CARD at frozen clocks and reading
 * what it said, not by reading the branch — that is how UX-P179 found its second
 * symptom and how this queue found both of these.
 * `theLegacyCardIsWrongInExactlyThisWay` proves the instrument by running the
 * verbatim pre-fix component through the identical probe and requiring it to
 * come back broken. A discriminator nobody has watched discriminate is a
 * decoration.
 *
 *   cd frontend && TZ=UTC npx jest --testPathPatterns=golfTournamentCardLiveWindow
 *   cd frontend && TZ=America/Los_Angeles npx jest --testPathPatterns=golfTournamentCardLiveWindow
 */

import React from "react";
import { renderToStaticMarkup } from "react-dom/server";

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

import TournamentCard from "@/components/TournamentCard";
import type {
  GolfCurrentEvent,
  GolfResponse,
  GolfTournament,
} from "@/lib/types";

// eslint-disable-next-line @typescript-eslint/no-var-requires
const TournamentCardLegacy =
  require("../fixtures/uxp180TournamentCardLegacy").default;

import golfBefore from "../fixtures/uxp179_golf_before.json";

const SERVED = golfBefore as unknown as GolfResponse;

function tournament(key: string): GolfTournament {
  const t = SERVED.tournaments.find((x) => x.key === key);
  if (!t) throw new Error(`fixture no longer carries ${key}`);
  return t;
}

/**
 * Tour Championship, Thu 2026-08-27 → Sun 2026-08-30. Golfers ARE moving, so
 * before this fix the price arm decided and the window never ran.
 */
const TOUR_CHAMPIONSHIP = tournament("tour_championship");
/**
 * Omega European Masters, Thu 2026-09-03 → Sun 2026-09-06. ZERO golfers moving,
 * so the window is already the sole decider — this is the unconditional case.
 */
const OMEGA = tournament("omega_european_masters");
/** The same Tour Championship, in the shape the banner is served. */
const CURRENT = SERVED.current_event as GolfCurrentEvent;

const WINDOWLESS = SERVED.tournaments.filter((t) => !(t.start_date && t.end_date));

function at<T>(now: string, fn: () => T): T {
  jest.useFakeTimers({ now: new Date(now) });
  try {
    return fn();
  } finally {
    jest.useRealTimers();
  }
}

function markup(Component: unknown, t: GolfTournament): string {
  return renderToStaticMarkup(
    React.createElement(Component as React.FC, { tournament: t } as never),
  );
}

/**
 * The live badge, and its label. `animate-pulse` appears exactly twice in the
 * component — the main card's badge and `CupCard`'s — and both ARE the live dot,
 * so the dot's presence is precisely "this card is claiming to be live right
 * now". Reading the label out of the same element rather than out of the whole
 * card matters: the card also prints leaderboard prose like "End of Round 3",
 * which a looser probe mistakes for the badge.
 */
const BADGE = /animate-pulse"><\/span>([^<]*)<\/span>/;

function badgeLabel(Component: unknown, t: GolfTournament, now: string): string | null {
  const m = at(now, () => markup(Component, t)).match(BADGE);
  return m ? m[1] : null;
}

function saysLive(Component: unknown, t: GolfTournament, now: string): boolean {
  return badgeLabel(Component, t, now) !== null;
}

function visibleText(m: string): string {
  return m
    .replace(/<[^>]*>/g, " ")
    .replace(/&middot;/g, "·")
    .replace(/&#x27;|&apos;/g, "'")
    .replace(/&amp;/g, "&")
    .replace(/\s+/g, " ")
    .trim();
}

/* ═══════════════════════════════════════════════════════════════════════ */
/* 1 · THE PREMISE — the served population really is calendar dates, and the  */
/*     window really is what decides.                                         */
/* ═══════════════════════════════════════════════════════════════════════ */

describe("UX-P180 · the premise, measured on the banked payload", () => {
  it("every tournament window is a pair of midnight-UTC calendar dates — 6 of 6", () => {
    const windows = SERVED.tournaments
      .filter((t) => t.start_date && t.end_date)
      .flatMap((t) => [t.start_date as string, t.end_date as string]);
    expect(windows).toHaveLength(6);
    expect(windows.every((s) => s.endsWith("T00:00:00+00:00"))).toBe(true);
  });

  it("`schedule_status === 'in-progress'` never occurs, so the first arm is dead", () => {
    // 0 of 94 schedule rows and 0 of 7 tournaments. This is why the window and
    // the price signal decide everything, and why `_currentRound` is
    // unreachable in production (see the last test in this file).
    const schedule = SERVED.pga_schedule ?? [];
    expect(schedule).toHaveLength(94);
    expect(
      schedule.filter((e) => (e as { schedule_status?: string }).schedule_status === "in-progress"),
    ).toHaveLength(0);
    expect(SERVED.tournaments).toHaveLength(7);
    expect(
      SERVED.tournaments.filter((t) => t.schedule_status === "in-progress"),
    ).toHaveLength(0);
  });

  it("Omega European Masters has no price movement, so the window is its SOLE decider", () => {
    const moved = OMEGA.golfers.filter(
      (g) => g.movement_24h !== null && Math.abs(g.movement_24h) >= 0.01,
    );
    expect(moved).toHaveLength(0);
    expect(OMEGA.start_date).toBe("2026-09-03T00:00:00+00:00");
    expect(OMEGA.end_date).toBe("2026-09-06T00:00:00+00:00");
  });

  it("Tour Championship IS moving, so before this fix the window never ran for it", () => {
    const moved = TOUR_CHAMPIONSHIP.golfers.filter(
      (g) => g.movement_24h !== null && Math.abs(g.movement_24h) >= 0.01,
    );
    expect(moved.length).toBeGreaterThan(0);
    expect(TOUR_CHAMPIONSHIP.start_date).toBe("2026-08-27T00:00:00+00:00");
    expect(TOUR_CHAMPIONSHIP.end_date).toBe("2026-08-30T00:00:00+00:00");
  });
});

/* ═══════════════════════════════════════════════════════════════════════ */
/* 2 · THE BOUNDARY — the shipped card, rendered across it.                   */
/* ═══════════════════════════════════════════════════════════════════════ */

describe("UX-P180 · the shipped card is live for the whole of its final day", () => {
  it("Omega: dark before the start day begins", () => {
    expect(saysLive(TournamentCard, OMEGA, "2026-09-02T23:59:00Z")).toBe(false);
  });

  it("Omega: live from the first instant of the start day", () => {
    // The window must OPEN on the start day, not before it — a card that is
    // simply always live would pass every other test in this block.
    expect(saysLive(TournamentCard, OMEGA, "2026-09-03T00:00:00Z")).toBe(true);
  });

  it("Omega: live on the eve of the final day", () => {
    expect(saysLive(TournamentCard, OMEGA, "2026-09-05T23:59:00Z")).toBe(true);
  });

  it("Omega: STILL LIVE one minute into the final day — this is the defect", () => {
    // Pre-fix this returned false: `now <= end` with `end` at midnight UTC.
    expect(saysLive(TournamentCard, OMEGA, "2026-09-06T00:01:00Z")).toBe(true);
  });

  it("Omega: STILL LIVE during the final round itself", () => {
    expect(saysLive(TournamentCard, OMEGA, "2026-09-06T18:00:00Z")).toBe(true);
  });

  it("Omega: dark once the final day is over", () => {
    expect(saysLive(TournamentCard, OMEGA, "2026-09-07T00:00:00Z")).toBe(false);
  });

  it("Omega prints its dates whenever it is not live, and hides them when it is", () => {
    expect(visibleText(at("2026-09-02T12:00:00Z", () => markup(TournamentCard, OMEGA))))
      .toContain("Sep 3–6");
    expect(visibleText(at("2026-09-06T18:00:00Z", () => markup(TournamentCard, OMEGA))))
      .not.toContain("Sep 3–6");
  });
});

describe("UX-P180 · the window vetoes the price signal", () => {
  it("Tour Championship: dark the day BEFORE it starts, despite live movement", () => {
    // The price arm is unconditional and has no date gate of its own; the
    // window is what stops it claiming a tournament that has not begun.
    expect(saysLive(TournamentCard, TOUR_CHAMPIONSHIP, "2026-08-26T12:00:00Z")).toBe(false);
  });

  it("Tour Championship: live during Sunday's final round", () => {
    expect(saysLive(TournamentCard, TOUR_CHAMPIONSHIP, "2026-08-30T18:00:00Z")).toBe(true);
  });

  it("Tour Championship: dark the day AFTER, despite residual 24h movement", () => {
    // `movement_24h` on the Monday covers Sunday's final round — the highest-
    // movement window of the week — so without the veto the stale pulse was
    // not a rare case but the normal one.
    expect(saysLive(TournamentCard, TOUR_CHAMPIONSHIP, "2026-08-31T00:00:00Z")).toBe(false);
  });
});

/* ═══════════════════════════════════════════════════════════════════════ */
/* 3 · THE INSTRUMENT — prove the probe can tell a broken card from a fixed   */
/*     one, by running the verbatim pre-fix component through it.             */
/* ═══════════════════════════════════════════════════════════════════════ */

describe("UX-P180 · theLegacyCardIsWrongInExactlyThisWay", () => {
  it("the legacy card goes DARK during Omega's final round, where the shipped one is live", () => {
    expect(saysLive(TournamentCardLegacy, OMEGA, "2026-09-06T18:00:00Z")).toBe(false);
    expect(saysLive(TournamentCard, OMEGA, "2026-09-06T18:00:00Z")).toBe(true);
  });

  it("the legacy card still PULSES the day after the Tour Championship ended", () => {
    expect(saysLive(TournamentCardLegacy, TOUR_CHAMPIONSHIP, "2026-08-31T12:00:00Z")).toBe(true);
    expect(saysLive(TournamentCard, TOUR_CHAMPIONSHIP, "2026-08-31T12:00:00Z")).toBe(false);
  });

  it("the legacy card pulses a day BEFORE the Tour Championship started", () => {
    expect(saysLive(TournamentCardLegacy, TOUR_CHAMPIONSHIP, "2026-08-26T12:00:00Z")).toBe(true);
    expect(saysLive(TournamentCard, TOUR_CHAMPIONSHIP, "2026-08-26T12:00:00Z")).toBe(false);
  });
});

/* ═══════════════════════════════════════════════════════════════════════ */
/* 4 · THE CONTROL — the population this fix must NOT touch.                  */
/* ═══════════════════════════════════════════════════════════════════════ */

describe("UX-P180 · the windowless population is untouched", () => {
  it("4 of the 7 served tournaments carry no window at all", () => {
    expect(WINDOWLESS).toHaveLength(4);
  });

  it.each(WINDOWLESS.map((t) => [t.key, t] as const))(
    "%s renders byte-identically before and after the fix",
    (_key, t) => {
      // A veto keyed on `start_date && end_date` must be invisible to rows that
      // have neither. These are long-horizon futures and the two mis-filed
      // non-golf markets; they are still decided by the price signal alone.
      const now = "2026-08-29T20:39:00Z";
      expect(at(now, () => markup(TournamentCard, t))).toBe(
        at(now, () => markup(TournamentCardLegacy, t)),
      );
    },
  );

  it.each([
    ["a start with no end", { start_date: "2026-08-27T00:00:00+00:00", end_date: null }],
    ["an end with no start", { start_date: null, end_date: "2026-08-30T00:00:00+00:00" }],
  ])("half a window (%s) is not a window — it falls through to the price signal", (_label, dates) => {
    // No tournament in the served population carries exactly ONE of the two
    // dates, so this case is invisible to every other test in this file — the
    // mutation harness found the hole by flipping the `&&` to `||`, which
    // survived. A half-window must behave like no window at all: `new Date(null)`
    // is the epoch, and letting it reach the arithmetic would silently pin the
    // card dark forever.
    const moving = { ...TOUR_CHAMPIONSHIP, ...dates } as GolfTournament;
    const still = {
      ...moving,
      golfers: moving.golfers.map((g) => ({ ...g, movement_24h: null })),
    } as GolfTournament;
    // Well outside any window either date could describe.
    const now = "2027-01-01T12:00:00Z";
    expect(saysLive(TournamentCard, moving, now)).toBe(true);
    expect(saysLive(TournamentCard, still, now)).toBe(false);
  });
});

/* ═══════════════════════════════════════════════════════════════════════ */
/* 5 · THE AGREEMENT — one payload, two real layers.                          */
/* ═══════════════════════════════════════════════════════════════════════ */

describe("UX-P180 · the card holds the window the banner will have to agree with", () => {
  // The banner and the card read the SAME tournament out of the SAME
  // `/api/golf` response — `current_event` and `tournaments[0]` — and each was
  // free to decide its own boundary. The banner is not on master (see the
  // header), so what is asserted here is the half that CAN be: that the two
  // payload shapes describe one tournament, and that the card's boundary is
  // exactly the one the banner already chose (end + 24h). When the banner
  // lands, the cross-component agreement goes back — enforced below.

  it("the two payload shapes describe the same tournament", () => {
    // Pure payload, no component: this is the premise the agreement rests on,
    // and it is the part that can silently drift while nobody is looking.
    expect(CURRENT.name).toBe(TOUR_CHAMPIONSHIP.name);
    expect(CURRENT.start_date).toBe(TOUR_CHAMPIONSHIP.start_date);
    expect(CURRENT.end_date).toBe(TOUR_CHAMPIONSHIP.end_date);
  });

  it.each([
    ["2026-08-29T23:59:00Z", "the eve of the final day"],
    ["2026-08-30T00:01:00Z", "one minute into the final day"],
    ["2026-08-30T18:00:00Z", "the final round itself"],
    ["2026-08-30T23:59:00Z", "the last minute of the final day"],
  ])("at %s (%s) the card is live", (now) => {
    expect(saysLive(TournamentCard, TOUR_CHAMPIONSHIP, now)).toBe(true);
  });

  it("the card retires it at the end of the final day, not the start", () => {
    expect(saysLive(TournamentCard, TOUR_CHAMPIONSHIP, "2026-08-31T00:00:00Z")).toBe(false);
  });

  it("theBannerAgreementIsOwed — this FAILS the day CurrentEventBanner lands", () => {
    // ⚠️ NOT a skip and NOT a try/catch that shrugs. A conditional test that
    // quietly does nothing is the "present but not what runs" failure this
    // lane has now hit in four costumes; the countermeasure is to make the
    // omission LOUD at exactly the moment it stops being justified.
    //
    // WHEN THIS FAILS, DO NOT DELETE IT. Restore the cross-component agreement
    // from `program/ux-125` @ daa0e617 — render CurrentEventBanner and
    // TournamentCard on this one payload and require them to retire the
    // tournament at the same instant — then remove this test.
    let bannerExists = true;
    try {
      require.resolve("@/components/golf/CurrentEventBanner");
    } catch {
      bannerExists = false;
    }
    expect({
      bannerOnMaster: bannerExists,
      restore: "the card/banner agreement from ux-125 @ daa0e617",
    }).toEqual({
      bannerOnMaster: false,
      restore: "the card/banner agreement from ux-125 @ daa0e617",
    });
  });
});

/* ═══════════════════════════════════════════════════════════════════════ */
/* 6 · WHAT THIS QUEUE DELIBERATELY DID NOT FIX.                              */
/* ═══════════════════════════════════════════════════════════════════════ */

describe("UX-P180 · `_currentRound` is unreachable, and that is why it is untouched", () => {
  it("no served tournament can ever render a `Round N` badge", () => {
    // The badge reads `Round N` only when `schedule_status === "in-progress"`,
    // which never occurs (see the premise block). `_currentRound` divides by the
    // same midnight-UTC instant this fix corrected, so it carries the same
    // latent error — but it has no reader, so fixing it would be unmeasured.
    // Parked as UX-P180-1. If this test ever fails, the arm has come alive and
    // `_currentRound` needs the same treatment as `_isLive`.
    for (const t of SERVED.tournaments) {
      // Read the BADGE, not the card: the card legitimately prints leaderboard
      // prose such as "End of Round 3", which is not this claim.
      const label = badgeLabel(TournamentCard, t, "2026-08-29T20:39:00Z");
      expect(label === null || label === "LIVE").toBe(true);
    }
  });
});
