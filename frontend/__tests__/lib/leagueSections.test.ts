/**
 * ux/1058 / #2948 — THE LEAGUE PAGE'S SECTION RULE.
 *
 * ═══ WHAT THIS GRADES, AND WITH WHAT ═══
 *
 * `buildLeagueSections` is a NEW module, so "revert to the parent" is a
 * collection error rather than a red arm — red-first grades a CHANGE, and this
 * is an ADDITION (ux/1019). The arms that grade it are therefore the
 * COUNTER-CASES named in the cert: the ordering mutated, the authority swapped
 * for a raw status test, and the sort direction flipped. The RENDERED half has
 * a genuine red arm and lives in
 * `__tests__/capture/leaguePageSections2948.test.tsx`.
 *
 * ═══ THE CORPUS IS REAL AND ITS SHAPE IS ASSERTED ═══
 *
 * `fixtures/leagueUsOpen.20260904.json` is `GET /api/events?sport=
 * tennis_atp_us_open&days=14` off production, captured while building the
 * repair, trimmed to the fields the page reads. Every number below is read out
 * of it rather than transcribed, so a claim cannot decay into a comment.
 *
 * ⚠️ CENSUS, AND IT IS A LIMITATION WORTH STATING: **the real payload carries no
 * live row.** The US Open match that was live when #2948 was filed had finished
 * by the time this was built. So the live-bucket arms below are SYNTHETIC and
 * say so, and the production post-deploy check cannot exercise the live arm
 * either until a match is actually in progress (ux/1032, ux/1040 — report an
 * unexercised arm as unavailable, never as passed).
 */

import realPayload from "../fixtures/leagueUsOpen.20260904.json";
import { buildLeagueSections as buildLeagueSectionsAt } from "@/lib/sports/leagueSections";
import type { Event, EventStatus } from "@/lib/types";

const REAL_EVENTS = realPayload.events as unknown as Event[];

/**
 * 🔴 #3211 — THE CORPUS IS A MOMENT, SO THE CLOCK MUST BE THAT MOMENT.
 *
 * `buildLeagueSections` used to branch on nothing time-dependent and said so in
 * its docblock. It now does: a row that still says `scheduled` more than two
 * hours after its own kickoff is not upcoming, it is a match that should have
 * been played and was never reported — which is the state 171 US Open matches
 * were in on production while being reachable from no rail at all.
 *
 * That makes this fixture's meaning depend on when you read it. The capture is
 * `GET /api/events?sport=tennis_atp_us_open&days=14` taken on 2026-09-04, and
 * against TODAY's wall clock all fifteen of its "scheduled" rows are now days
 * past their kickoff — so the module correctly buckets them as result-less, and
 * every count below would decay from "15 upcoming" to "15 unreported" purely by
 * the passage of time. That is a rotting anchor (gotcha #44), not a defect, and
 * the fix is the one that gotcha names: evaluate the snapshot at the snapshot's
 * own instant.
 *
 * Derived from the corpus rather than transcribed — after its newest Final and
 * before its soonest fixture is exactly the moment the endpoint was called —
 * and asserted to be so by the CONTROL in section A, so it cannot silently
 * stop being the capture's own time.
 */
const CAPTURED_AT = new Date("2026-09-04T14:00:00Z").getTime();

/** Every call in this file reads the corpus's own clock unless it says otherwise. */
const buildLeagueSections = (events: Event[], now: number = CAPTURED_AT) =>
  buildLeagueSectionsAt(events, now);

/** A minimal event. Nothing is defaulted that an arm needs to vary. */
function ev(
  id: number,
  status: EventStatus,
  commence_time: string,
  completed_at?: string | null,
): Event {
  return {
    id,
    external_id: `x${id}`,
    sport: "tennis_atp_us_open",
    home_team: `Home ${id}`,
    away_team: `Away ${id}`,
    commence_time,
    completed_at: completed_at ?? null,
    status,
    home_score: null,
    away_score: null,
  } as Event;
}

const ids = (events: Event[]) => events.map((e) => e.id);
const sectionKeys = (events: Event[]) => buildLeagueSections(events).map((s) => s.key);

// ───────────────────────────────────────────────────────────────────────────
// A · the real payload: the defect, and what the rule does to it
// ───────────────────────────────────────────────────────────────────────────
describe("ux/1058 · the shipped payload is the defect", () => {
  test("CONTROL: the corpus is the real endpoint's order, ascending by commence_time", () => {
    const times = REAL_EVENTS.map((e) => new Date(e.commence_time).getTime());
    expect(times.length).toBe(32);
    expect([...times].sort((a, b) => a - b)).toEqual(times);
  });

  test("the payload puts 17 finished games ahead of the first upcoming one", () => {
    const firstUpcoming = REAL_EVENTS.findIndex((e) => e.status === "scheduled");
    expect(firstUpcoming).toBe(17);
    const finishedAbove = REAL_EVENTS.slice(0, firstUpcoming).filter((e) =>
      ["completed", "closed"].includes(e.status),
    ).length;
    // This is the bug, stated as a property of the input: without a partition,
    // 17 of the 32 cards a reader scrolls past are games already over.
    expect(finishedAbove).toBe(17);
  });

  test("CENSUS: the real payload carries no live row, so live arms are synthetic", () => {
    const live = REAL_EVENTS.filter(
      (e) => !["completed", "closed", "scheduled"].includes(e.status),
    );
    expect(live).toEqual([]);
  });

  test("CONTROL: CAPTURED_AT really is the corpus's own instant (#3211)", () => {
    // Every count in this file is read at this clock, so the clock has to be
    // the one the endpoint was called at — after the newest result, before the
    // soonest fixture. Derived from the corpus, so it cannot drift into a
    // number that merely happens to make the suite green.
    const newestFinished = Math.max(
      ...REAL_EVENTS.filter((e) => e.status === "completed").map((e) =>
        new Date(e.completed_at ?? e.commence_time).getTime(),
      ),
    );
    const soonestScheduled = Math.min(
      ...REAL_EVENTS.filter((e) => e.status === "scheduled").map((e) =>
        new Date(e.commence_time).getTime(),
      ),
    );
    expect(CAPTURED_AT).toBeGreaterThan(newestFinished);
    expect(CAPTURED_AT).toBeLessThan(soonestScheduled);
  });
});

describe("ux/1058 · the rule over the real payload", () => {
  const sections = buildLeagueSections(REAL_EVENTS);

  test("emits Upcoming then Finished, and no empty live section", () => {
    expect(sections.map((s) => s.key)).toEqual(["upcoming", "finished"]);
    expect(sections.map((s) => s.title)).toEqual(["Upcoming", "Finished"]);
  });

  test("every card is kept — the partition loses nothing", () => {
    const rendered = sections.flatMap((s) => s.events);
    expect(rendered).toHaveLength(REAL_EVENTS.length);
    expect(new Set(ids(rendered))).toEqual(new Set(ids(REAL_EVENTS)));
  });

  test("counts split 15 upcoming / 17 finished", () => {
    expect(sections.map((s) => s.events.length)).toEqual([15, 17]);
  });

  test("NOT ONE finished game renders above an upcoming one", () => {
    const rendered = sections.flatMap((s) => s.events);
    const lastUpcoming = rendered.map((e) => e.status).lastIndexOf("scheduled");
    const firstFinished = rendered.findIndex((e) =>
      ["completed", "closed"].includes(e.status),
    );
    expect(firstFinished).toBeGreaterThan(lastUpcoming);
    // …and concretely: the reader's first card is a game still to play.
    expect(rendered[0].status).toBe("scheduled");
  });

  test("upcoming runs soonest-first", () => {
    const t = sections[0].events.map((e) => new Date(e.commence_time).getTime());
    expect([...t].sort((a, b) => a - b)).toEqual(t);
  });

  test("finished runs most-recent-first, on completed_at", () => {
    const finished = sections[1].events;
    // The preference is exercised by real data, not only by a synthetic row.
    expect(finished.every((e) => Boolean(e.completed_at))).toBe(true);
    const t = finished.map((e) => new Date(e.completed_at as string).getTime());
    expect([...t].sort((a, b) => b - a)).toEqual(t);
  });
});

// ───────────────────────────────────────────────────────────────────────────
// B · the shared authority — SYNTHETIC, because the corpus has no live row
// ───────────────────────────────────────────────────────────────────────────
describe("ux/1058 · the bucket comes from eventState, not from this module", () => {
  test("a suspended match is LIVE and is never filed under Finished", () => {
    const sections = buildLeagueSections([
      ev(1, "suspended" as EventStatus, "2026-09-04T01:00:00Z"),
      ev(2, "completed", "2026-09-03T01:00:00Z", "2026-09-03T03:00:00Z"),
    ]);
    expect(sections.map((s) => s.key)).toEqual(["live", "finished"]);
    expect(ids(sections[0].events)).toEqual([1]);
    expect(ids(sections[1].events)).toEqual([2]);
  });

  test("the live heading reads the bucket rather than asserting Live Now", () => {
    const paused = buildLeagueSections([ev(1, "suspended" as EventStatus, "2026-09-04T01:00:00Z")]);
    expect(paused[0].title).toBe("Live & Paused");
    const playing = buildLeagueSections([ev(1, "live" as EventStatus, "2026-09-04T01:00:00Z")]);
    expect(playing[0].title).toBe("Live Now");
  });

  test("#3211: a scheduled row past its own kickoff is NOT upcoming", () => {
    // The specimen's shape: a US Open row stamped midnight UTC by a Kalshi
    // ticker, still `scheduled` two days later because nothing ever settled it.
    // Filing it under "Upcoming" claims a match that should already have been
    // played is about to begin — the fall-through `lib/eventState` opens by
    // naming as the quieter lie.
    const sections = buildLeagueSections([
      ev(1, "scheduled", "2026-09-02T00:00:00Z"),
      ev(2, "scheduled", "2026-09-05T00:00:00Z"),
    ]);
    expect(sections.map((s) => s.key)).toEqual(["live", "upcoming"]);
    expect(ids(sections[0].events)).toEqual([1]);
    expect(ids(sections[1].events)).toEqual([2]);
    // …and the heading does not claim anyone is watching it.
    expect(sections[0].title).toBe("Live & Paused");
  });

  test("#3211: the boundary is the grace, asserted from BOTH sides", () => {
    // A test that only checks "two days ago" would pass over any floor at all.
    const kickoff = new Date("2026-09-04T12:00:00Z").getTime();
    const justInside = kickoff + 2 * 60 * 60 * 1000 - 60_000;
    const justOutside = kickoff + 2 * 60 * 60 * 1000 + 60_000;
    const row = [ev(1, "scheduled", "2026-09-04T12:00:00Z")];

    expect(buildLeagueSections(row, justInside).map((s) => s.key)).toEqual([
      "upcoming",
    ]);
    expect(buildLeagueSections(row, justOutside).map((s) => s.key)).toEqual([
      "live",
    ]);
  });

  test("#3211: a LIVE row is unaffected, however long it has been running", () => {
    // The control that keeps the arm above from being a rule about elapsed time
    // rather than about the `scheduled` word. A five-set match is still live.
    const sections = buildLeagueSections(
      [ev(1, "live" as EventStatus, "2026-09-04T06:00:00Z")],
      new Date("2026-09-04T14:00:00Z").getTime(),
    );
    expect(sections.map((s) => s.key)).toEqual(["live"]);
    expect(sections[0].title).toBe("Live Now");
  });

  test("an unrecognised status is UPCOMING, never Finished", () => {
    // `as unknown as` because these are deliberately OUTSIDE `EventStatus` —
    // that is the point of the arm: an unrecognised status must land in
    // upcoming rather than being read as a result.
    for (const status of ["postponed", "", "wat"] as unknown as EventStatus[]) {
      expect(sectionKeys([ev(1, status, "2026-09-09T01:00:00Z")])).toEqual(["upcoming"]);
    }
  });

  test("live sits above upcoming, which sits above finished", () => {
    expect(
      sectionKeys([
        ev(1, "completed", "2026-09-01T00:00:00Z", "2026-09-01T02:00:00Z"),
        ev(2, "scheduled", "2026-09-09T00:00:00Z"),
        ev(3, "live" as EventStatus, "2026-09-04T00:00:00Z"),
      ]),
    ).toEqual(["live", "upcoming", "finished"]);
  });
});

// ───────────────────────────────────────────────────────────────────────────
// C · ordering, purity, degenerate input
// ───────────────────────────────────────────────────────────────────────────
describe("ux/1058 · ordering and purity", () => {
  test("the caller's array is not sorted in place", () => {
    const input = [
      ev(1, "scheduled", "2026-09-09T00:00:00Z"),
      ev(2, "scheduled", "2026-09-05T00:00:00Z"),
    ];
    const before = ids(input);
    buildLeagueSections(input);
    expect(ids(input)).toEqual(before);
  });

  test("an empty bucket emits no section, and no input emits nothing", () => {
    expect(sectionKeys([ev(1, "scheduled", "2026-09-09T00:00:00Z")])).toEqual(["upcoming"]);
    expect(buildLeagueSections([])).toEqual([]);
  });

  test("equal times keep payload order — seven US Open fixtures share one slot", () => {
    const same = "2026-09-05T15:00:00Z";
    const input = [7, 6, 5, 4, 3, 2, 1].map((n) => ev(n, "scheduled", same));
    expect(ids(buildLeagueSections(input)[0].events)).toEqual([7, 6, 5, 4, 3, 2, 1]);
    // And the real payload's own seven-way tie is untouched by the sort.
    const tied = REAL_EVENTS.filter((e) => e.commence_time === "2026-09-05T15:00:00+00:00");
    expect(tied.length).toBeGreaterThan(1);
    const upcoming = buildLeagueSections(REAL_EVENTS)[0].events;
    expect(ids(upcoming.filter((e) => e.commence_time === "2026-09-05T15:00:00+00:00"))).toEqual(
      ids(tied),
    );
  });

  test("an undated row sorts LAST rather than scattering, in both directions", () => {
    const up = buildLeagueSections([
      ev(1, "scheduled", "" as unknown as string),
      ev(2, "scheduled", "2026-09-09T00:00:00Z"),
    ])[0];
    expect(ids(up.events)).toEqual([2, 1]);

    const fin = buildLeagueSections([
      ev(3, "completed", "" as unknown as string, null),
      ev(4, "completed", "2026-09-03T00:00:00Z", "2026-09-03T02:00:00Z"),
    ])[0];
    expect(ids(fin.events)).toEqual([4, 3]);
  });

  test("finished prefers completed_at over commence_time", () => {
    // 5 started FIRST but finished LAST, so it must render first.
    const sections = buildLeagueSections([
      ev(6, "completed", "2026-09-03T20:00:00Z", "2026-09-03T21:00:00Z"),
      ev(5, "completed", "2026-09-03T10:00:00Z", "2026-09-03T23:00:00Z"),
    ]);
    expect(ids(sections[0].events)).toEqual([5, 6]);
  });

  test("a finished row with no completed_at falls back to commence_time", () => {
    const sections = buildLeagueSections([
      ev(7, "completed", "2026-09-03T10:00:00Z", null),
      ev(8, "completed", "2026-09-03T20:00:00Z", null),
    ]);
    expect(ids(sections[0].events)).toEqual([8, 7]);
  });
});
