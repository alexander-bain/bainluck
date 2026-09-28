/**
 * ux — #9265: A CALLED-OFF GAME IS NOT "LIVE & PAUSED".
 *
 * ═══ WHAT A READER SAW ═══
 *
 * `/sports/baseball_mlb`, 390px, 2026-09-28 02:2xZ: the page opened on
 * `Live & Paused 1`. The only card under it was Orioles @ Yankees (15319530),
 * called off that morning and never started; the card itself read
 * `Postponed · Sep 27`. Nothing on the page was live or paused.
 *
 * ═══ RED-FIRST ═══
 *
 * On the parent `eventSectionKey("suspended", …)` returns "live" for every
 * suspended row, so section B's ship arm is red by return value and section
 * C's by bucket membership and heading.
 *
 * ═══ THE CORPUS IS REAL ═══
 *
 * `fixtures/leagueBaseballMlb.20260928-9265.json` is
 * `GET /api/events?sport=baseball_mlb&days=14` off production, the league
 * page's own request, captured 02:57Z while building this. Its composition is
 * asserted in section A so no arm can go vacuous if it is replaced. The clock
 * is derived from it (gotcha #44), between the last started game and the
 * soonest fixture.
 */

import realPayload from "../fixtures/leagueBaseballMlb.20260928-9265.json";
import { eventSectionKey, UPCOMING_GRACE_MS } from "@/lib/eventState";
import { authorityStoppageLabel } from "@/lib/gameTimeLabel";
import { buildLeagueSections, leagueSectionKey } from "@/lib/sports/leagueSections";
import { needsWiderHorizon } from "@/lib/sports/leagueHorizon";
import type { Event } from "@/lib/types";

const REAL_EVENTS = realPayload.events as unknown as Event[];
const ms = (iso: string | null | undefined) => new Date(iso ?? "").getTime();

const LAST_STARTED = Math.max(
  ...REAL_EVENTS.filter((e) => e.status !== "scheduled").map((e) => ms(e.commence_time)),
);
const SOONEST_FIXTURE = Math.min(
  ...REAL_EVENTS.filter((e) => e.status === "scheduled").map((e) => ms(e.commence_time)),
);
const CAPTURED_AT = Math.round((LAST_STARTED + SOONEST_FIXTURE) / 2);

const CALLED_OFF = REAL_EVENTS.filter((e) => e.status === "suspended");
const COMPLETED = REAL_EVENTS.filter((e) => e.status === "completed");
const SCHEDULED = REAL_EVENTS.filter((e) => e.status === "scheduled");

describe("A · CONTROL — the corpus is the shape every arm below assumes", () => {
  test("24 rows: 17 completed, 6 scheduled, 1 suspended", () => {
    expect(REAL_EVENTS).toHaveLength(24);
    expect(COMPLETED).toHaveLength(17);
    expect(SCHEDULED).toHaveLength(6);
    expect(CALLED_OFF).toHaveLength(1);
  });

  test("the suspended row is the specimen: 15319530, ESPN says Postponed, no score", () => {
    const [row] = CALLED_OFF;
    expect(row.id).toBe(15319530);
    expect(row.espn?.period).toBe("Postponed");
    expect(authorityStoppageLabel(row.espn?.period)).toBe("Postponed");
    expect(row.away_score ?? null).toBeNull();
    expect(row.home_score ?? null).toBeNull();
  });

  test("the derived clock is the capture's own instant", () => {
    expect(CAPTURED_AT).toBeGreaterThan(LAST_STARTED);
    expect(CAPTURED_AT).toBeLessThan(SOONEST_FIXTURE);
    expect(
      SCHEDULED.every((e) => ms(e.commence_time) >= CAPTURED_AT - UPCOMING_GRACE_MS),
    ).toBe(true);
  });
});

describe("B · THE LADDER — the new rung, and what it must not touch", () => {
  const at = (status: string, settlement?: unknown) =>
    eventSectionKey(status, "2026-09-27T17:05:00+00:00", CAPTURED_AT, settlement as never);

  test("THE SHIP: a suspended row with a stoppage label is finished", () => {
    // Parent: "live".
    expect(at("suspended", { stoppage: "Postponed" })).toBe("finished");
    expect(at("suspended", { stoppage: "Canceled" })).toBe("finished");
  });

  test("a suspended row with no label stays live — CERT-786's paused match", () => {
    expect(at("suspended", { stoppage: null })).toBe("live");
    expect(at("suspended", {})).toBe("live");
    expect(at("suspended")).toBe("live");
  });

  test("a label on a row being PLAYED cannot move it", () => {
    expect(at("live", { stoppage: "Postponed" })).toBe("live");
  });

  test("a label on a scheduled row does not jump #3211's ladder", () => {
    const soon = new Date(CAPTURED_AT + 60 * 60 * 1000).toISOString();
    expect(eventSectionKey("scheduled", soon, CAPTURED_AT, { stoppage: "Postponed" })).toBe(
      "upcoming",
    );
  });

  test("the league helper resolves the label from espn.period itself", () => {
    const row = CALLED_OFF[0];
    expect(leagueSectionKey(row, CAPTURED_AT)).toBe("finished");
    // A live period left on a suspended row is not a stoppage word (#8810's
    // exact allowlist), so that row stays in the paused bucket.
    const wentDark = { ...row, espn: { ...row.espn, period: "Top 7th" } } as Event;
    expect(leagueSectionKey(wentDark, CAPTURED_AT)).toBe("live");
    const noEspn = { ...row, espn: undefined } as Event;
    expect(leagueSectionKey(noEspn, CAPTURED_AT)).toBe("live");
  });
});

describe("C · THE LEAGUE PAGE — the headings a reader scrolls past", () => {
  const sections = buildLeagueSections(REAL_EVENTS, CAPTURED_AT);
  const byKey = new Map(sections.map((s) => [s.key, s]));

  test("THE SHIP: no Live & Paused section on a day nothing is live", () => {
    // Parent: ["Live & Paused", "Upcoming", "Finished"].
    expect(sections.map((s) => s.title)).toEqual(["Upcoming", "Finished"]);
    expect(byKey.has("live")).toBe(false);
  });

  test("BINDING: the called-off game is still on the page, under Finished", () => {
    const finishedIds = byKey.get("finished")?.events.map((e) => e.id) ?? [];
    expect(finishedIds).toContain(15319530);
    expect(finishedIds).toHaveLength(COMPLETED.length + 1);
    expect(byKey.get("upcoming")?.events.map((e) => e.id).sort()).toEqual(
      SCHEDULED.map((e) => e.id).sort(),
    );
  });

  test("…and a paused match still gets its heading beside it", () => {
    // The rung must not have emptied the bucket by accident: the same row
    // without its stoppage word is the paused match CERT-786 was written for.
    const paused = { ...CALLED_OFF[0], espn: undefined } as Event;
    const withPaused = buildLeagueSections([...COMPLETED, paused], CAPTURED_AT);
    expect(withPaused[0].title).toBe("Live & Paused");
    expect(withPaused[0].events.map((e) => e.id)).toEqual([15319530]);
  });

  test("the horizon agrees: a called-off game is not the league playing now", () => {
    // Parent: the suspended row read as live and answered `false` on its own.
    // With only it and finished games, nothing is still to play.
    expect(needsWiderHorizon([...COMPLETED, ...CALLED_OFF], CAPTURED_AT)).toBe(true);
    const paused = { ...CALLED_OFF[0], espn: undefined } as Event;
    expect(needsWiderHorizon([...COMPLETED, paused], CAPTURED_AT)).toBe(false);
  });
});
