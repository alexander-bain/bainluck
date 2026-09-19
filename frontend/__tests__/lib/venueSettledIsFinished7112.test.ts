/**
 * ux/1348 / #7112 — A GRADED MATCH STOPS BEING COUNTED AS ONE STILL BEING PLAYED.
 *
 * ═══ WHAT A READER SAW ═══
 *
 * `/sports/tennis_atp`, 390px, 2026-09-19 03:03Z: a heading reading
 * `Live & Paused 6`, and the first four cards under it said
 * `Settled · Blanch wins`, `Settled · Zheng wins`, … The two matches actually
 * being played were pushed BELOW four finished ones, and the page rendered no
 * Finished section at all. The card read `venue_settled`; the bucket read
 * `status`. Two predicates for one question.
 *
 * ═══ RED-FIRST: WHAT THE PARENT DOES WITH THIS CORPUS ═══
 *
 * This grades a CHANGE to `eventSectionKey`, not a new module, so the arms are
 * written to be RED on the parent and are labelled where that is not literally
 * possible. On the parent, `eventSectionKey("suspended", …)` returns "live"
 * unconditionally — the fourth argument does not exist — so section B's arms
 * are red by return value and section C's by bucket membership. The RENDERED
 * half, where the card's sentence and the heading above it are read out of one
 * markup string, is `__tests__/capture/leaguePageSettledIsNotLive7112.test.tsx`.
 *
 * ═══ THE CORPUS IS REAL AND ITS SHAPE IS ASSERTED ═══
 *
 * `fixtures/leagueTennisAtp.20260919-7112.json` is
 * `GET /api/events?sport=tennis_atp&limit=50` off production, captured while
 * building the repair, whole and untrimmed. Every count below is read out of it
 * rather than transcribed. Its composition — 3 venue-settled `suspended`, 2
 * `live`, 14 `scheduled` — is asserted by the control in section A, so an arm
 * cannot go vacuous if the capture is ever replaced.
 *
 * ⚠️ 🔴 THE CORPUS IS A MOMENT AND THE CLOCK IS THAT MOMENT (gotcha #44). The
 * `scheduled` rows are minutes-to-hours out from the capture; read against a
 * live wall clock they all cross `UPCOMING_GRACE_MS` and become result-less
 * rows in the live bucket, and every count here would rot with the calendar
 * rather than with the code. `CAPTURED_AT` is DERIVED from the corpus — after
 * its last started match, before its soonest fixture — and the control asserts
 * it lands there, so it cannot silently stop being the capture's own time.
 */

import realPayload from "../fixtures/leagueTennisAtp.20260919-7112.json";
import {
  eventSectionKey,
  hasNoReportedResult,
  venueSettledSummary,
  UPCOMING_GRACE_MS,
} from "@/lib/eventState";
import { buildLeagueSections as buildLeagueSectionsAt } from "@/lib/sports/leagueSections";
import { needsWiderHorizon, LEAGUE_NEAR_TERM_DAYS } from "@/lib/sports/leagueHorizon";
import type { Event } from "@/lib/types";

const REAL_EVENTS = realPayload.events as unknown as Event[];

const ms = (iso: string | null | undefined) => new Date(iso ?? "").getTime();

/**
 * The capture's own instant, derived rather than transcribed: halfway between
 * the last match that had started and the first that had not.
 */
const LAST_STARTED = Math.max(
  ...REAL_EVENTS.filter((e) => e.status !== "scheduled").map((e) => ms(e.commence_time)),
);
const SOONEST_FIXTURE = Math.min(
  ...REAL_EVENTS.filter((e) => e.status === "scheduled").map((e) => ms(e.commence_time)),
);
const CAPTURED_AT = Math.round((LAST_STARTED + SOONEST_FIXTURE) / 2);

const buildLeagueSections = (events: Event[]) => buildLeagueSectionsAt(events, CAPTURED_AT);

/** The card's own conjunction, spelled once, read by section D. */
const cardPrintsSettled = (e: Event) =>
  hasNoReportedResult(e.status, e.commence_time, CAPTURED_AT) &&
  venueSettledSummary(e.venue_settled, e.venue_settled_result) !== null;

const SETTLED = REAL_EVENTS.filter((e) => e.venue_settled === true);
const LIVE_ROWS = REAL_EVENTS.filter((e) => e.status === "live");
const SCHEDULED = REAL_EVENTS.filter((e) => e.status === "scheduled");

describe("A · CONTROL — the corpus is the shape every arm below assumes", () => {
  test("19 rows: 3 venue-settled suspended, 2 live, 14 scheduled", () => {
    expect(REAL_EVENTS).toHaveLength(19);
    expect(SETTLED).toHaveLength(3);
    expect(SETTLED.every((e) => e.status === "suspended")).toBe(true);
    expect(LIVE_ROWS).toHaveLength(2);
    expect(SCHEDULED).toHaveLength(14);
  });

  test("every settled row names a winner — the badge-alone arm is SYNTHETIC below", () => {
    expect(SETTLED.map((e) => e.venue_settled_result)).toEqual([
      "Blanch wins",
      "Lammons / Withrow wins",
      "Zheng wins",
    ]);
  });

  test("the 16 unsettled rows carry NEITHER key — absence is the producer's contract", () => {
    const rest = REAL_EVENTS.filter((e) => e.venue_settled !== true);
    expect(rest).toHaveLength(16);
    expect(rest.every((e) => e.venue_settled === undefined)).toBe(true);
    expect(rest.every((e) => e.venue_settled_result === undefined)).toBe(true);
  });

  test("the derived clock is the capture's own instant", () => {
    expect(CAPTURED_AT).toBeGreaterThan(LAST_STARTED);
    expect(CAPTURED_AT).toBeLessThan(SOONEST_FIXTURE);
    // …and no fixture has yet crossed the grace window, so none of the 14 is
    // an unreported match at this instant. Without this the corpus would read
    // as 14 more live rows and section C would pass on the wrong population.
    expect(
      SCHEDULED.every((e) => ms(e.commence_time) >= CAPTURED_AT - UPCOMING_GRACE_MS),
    ).toBe(true);
  });
});

describe("B · THE LADDER — the new rung, and everything it must not touch", () => {
  const settled = { venue_settled: true, venue_settled_result: "Blanch wins" };
  const suspendedAt = (settlement?: unknown) =>
    eventSectionKey("suspended", "2026-09-18T22:00:00+00:00", CAPTURED_AT, settlement as never);

  test("THE SHIP: a venue-graded suspended row is finished", () => {
    // Parent: "live".
    expect(suspendedAt(settled)).toBe("finished");
  });

  test("a graded row with NO result — the 16 prop-grade rows — is finished too", () => {
    // The badge stands alone on these (`venueSettledSummary` returns the label
    // without a sentence). They are settled; keying on the card's own predicate
    // keeps them consistent rather than inventing a third state.
    expect(suspendedAt({ venue_settled: true, venue_settled_result: null })).toBe("finished");
  });

  test("`venue_settled: false` — we asked, nothing graded it — stays live", () => {
    expect(suspendedAt({ venue_settled: false, venue_settled_result: null })).toBe("live");
  });

  test("the keys absent entirely stays live", () => {
    expect(suspendedAt({})).toBe("live");
  });

  test("CERT-786's bare ladder is untouched: no fourth argument, no change", () => {
    expect(suspendedAt(undefined)).toBe("live");
    expect(eventSectionKey("suspended")).toBe("live");
  });

  test("a row being PLAYED cannot be moved by a stray flag", () => {
    // `hasNoReportedResult` is false for `live`, which is the half of the
    // conjunction that keeps the rung off every row with a better answer. A
    // rung keyed on `venue_settled` alone would file a live match as finished.
    expect(
      eventSectionKey("live", "2026-09-19T01:00:00+00:00", CAPTURED_AT, settled),
    ).toBe("live");
  });

  test("#3211's grace window survives: a fixture not yet due is still upcoming", () => {
    const soon = new Date(CAPTURED_AT + 60 * 60 * 1000).toISOString();
    expect(eventSectionKey("scheduled", soon, CAPTURED_AT, settled)).toBe("upcoming");
  });

  test("…and a graded row that never left `scheduled` IS a result", () => {
    const longPast = new Date(CAPTURED_AT - UPCOMING_GRACE_MS - 1).toISOString();
    expect(eventSectionKey("scheduled", longPast, CAPTURED_AT, settled)).toBe("finished");
    // The same row ungraded stays where #3211 put it.
    expect(eventSectionKey("scheduled", longPast, CAPTURED_AT)).toBe("live");
  });

  test("an already-finished status is finished either way", () => {
    expect(eventSectionKey("completed", null, CAPTURED_AT, settled)).toBe("finished");
    expect(eventSectionKey("completed", null, CAPTURED_AT)).toBe("finished");
  });
});

describe("C · THE LEAGUE PAGE — the buckets a reader scrolls past", () => {
  const sections = buildLeagueSections(REAL_EVENTS);
  const byKey = new Map(sections.map((s) => [s.key, s]));

  test("THE SHIP: three settled matches move out of the live bucket", () => {
    // Parent: live holds 5 and there is no finished section at all.
    expect(byKey.get("live")?.events).toHaveLength(2);
    expect(byKey.get("finished")?.events).toHaveLength(3);
    expect(byKey.get("upcoming")?.events).toHaveLength(14);
  });

  test("BINDING: each bucket holds its OWN rows, not just the right counts", () => {
    expect(byKey.get("finished")?.events.map((e) => e.id).sort()).toEqual(
      SETTLED.map((e) => e.id).sort(),
    );
    expect(byKey.get("live")?.events.map((e) => e.id).sort()).toEqual(
      LIVE_ROWS.map((e) => e.id).sort(),
    );
  });

  test("the page grows a Finished section it did not render", () => {
    expect(sections.map((s) => s.title)).toEqual(["Live Now", "Upcoming", "Finished"]);
  });

  test("…and the live heading stops saying 'Paused' over matches that are over", () => {
    // `liveSectionTitle` reads the bucket. With the graded rows gone, nothing
    // left in it has an unreported result, so the header is plainly "Live Now"
    // — on the parent it read "Live & Paused 6".
    expect(byKey.get("live")?.title).toBe("Live Now");
  });

  test("the results sort most-recent-first on `commence_time`, having no `completed_at`", () => {
    const finished = byKey.get("finished")!.events;
    expect(finished.every((e) => e.completed_at == null)).toBe(true);
    const times = finished.map((e) => ms(e.commence_time));
    expect(times).toEqual([...times].sort((a, b) => b - a));
  });

  test("the two matches being played render ABOVE the three that are over", () => {
    const order = sections.flatMap((s) => s.events.map((e) => e.id));
    const lastLive = Math.max(...LIVE_ROWS.map((e) => order.indexOf(e.id)));
    const firstSettled = Math.min(...SETTLED.map((e) => order.indexOf(e.id)));
    expect(firstSettled).toBeGreaterThan(lastLive);
  });
});

describe("D · PARITY — the section and the card read one predicate", () => {
  test("every row whose CARD prints 'Settled · …' is in the Finished bucket", () => {
    const finishedIds = new Set(
      buildLeagueSections(REAL_EVENTS)
        .find((s) => s.key === "finished")!
        .events.map((e) => e.id),
    );
    const printing = REAL_EVENTS.filter(cardPrintsSettled);
    // Not vacuous: the corpus carries three of them.
    expect(printing).toHaveLength(3);
    expect(printing.every((e) => finishedIds.has(e.id))).toBe(true);
  });

  test("and no row the card says nothing about was moved", () => {
    const silent = REAL_EVENTS.filter((e) => !cardPrintsSettled(e));
    const finishedIds = new Set(
      buildLeagueSections(REAL_EVENTS)
        .find((s) => s.key === "finished")!
        .events.map((e) => e.id),
    );
    expect(silent.some((e) => finishedIds.has(e.id))).toBe(false);
  });
});

describe("E · THE HORIZON — the same page's other reader of the same ladder", () => {
  /** A fixture `days` out from the capture, in the shape the module reads. */
  const fixtureIn = (days: number, id: number): Event =>
    ({
      id,
      status: "scheduled",
      commence_time: new Date(CAPTURED_AT + days * 86_400_000).toISOString(),
    }) as unknown as Event;

  test("CONTROL: a league with a game this week is never widened", () => {
    expect(needsWiderHorizon(REAL_EVENTS, CAPTURED_AT)).toBe(false);
  });

  test("THE SHIP: three finished matches do not make a league look like it is playing", () => {
    // Parent: the three graded rows bucket as "live", so this returns false and
    // the page never asks for the wider window — a league whose only "live"
    // rows are matches that finished last night reads as in season.
    const dormant = [...SETTLED, fixtureIn(LEAGUE_NEAR_TERM_DAYS + 1, 991)];
    expect(needsWiderHorizon(dormant, CAPTURED_AT)).toBe(true);
  });

  test("…and a match actually in progress still stops the widening", () => {
    const playing = [...SETTLED, ...LIVE_ROWS, fixtureIn(LEAGUE_NEAR_TERM_DAYS + 1, 992)];
    expect(needsWiderHorizon(playing, CAPTURED_AT)).toBe(false);
  });
});
