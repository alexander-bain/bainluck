// #3829 — THE MATCH PAGE MUST NOT PRINT A CLOCK THE HUB CALLS TBD.
//
// ── WHAT THE READER SAW ──────────────────────────────────────────────────────
//
// Production `27c827b1`, 390px, 2026-09-07. Frances Tiafoe v Alex Michelsen,
// US Open men's quarter-final, `event_id 15306225`.
//
//     /tournaments/us-open, QF tab:   TOMORROW · TBD · MEN'S SINGLES
//     /events/15306225, same match:   Starts in 1d 8h    Sep 8, 2026 · 11:30 AM EDT
//
// One fixture, two surfaces, two answers — and the confident one was wrong. All
// four quarter-finals shared a single fabricated `2026-09-08T15:30:00Z`; four
// matches cannot begin at 11:30 on two courts.
//
// ── THE MECHANISM ────────────────────────────────────────────────────────────
//
// ESPN files a tennis fixture on the scoreboard the moment its round is drawn,
// carrying midnight-local as a placeholder, and grants a real hour only when
// the courts are assigned. `start_is_tbd` is ESPN's own word for which of the
// two you are holding, and the hub has honoured it since Q463. The flag simply
// never travelled to the match page: `GET /api/events/{id}` carries
// `commence_time` and nothing else start-shaped, so the page had nothing to
// gate on. A serve-time renderer needs EVERY input to the label to travel, not
// just the clock one — the backend half of this ship puts `start_is_tbd` on
// `/api/tournaments/by-event/{id}`, which this page already calls.
//
// ── WHY THESE TWO FUNCTIONS ──────────────────────────────────────────────────
//
// A Next.js page may not carry named exports, so the pure seam is the only
// thing a guard can hold — the same reason `shouldShowRefreshCountdown` was
// lifted into `eventKeyStats` by #3802, which fixed the adjacent defect in the
// very same header. Rendering the page to reach this string would mean standing
// up SWR, the analytics hooks and a full event payload to assert on one label.
//
// Assertions are TIMEZONE-INDEPENDENT by construction: they test for the
// PRESENCE OR ABSENCE OF A CLOCK, never for a particular hour. A guard that
// pinned "11:30 AM EDT" would be a guard that fails in CI and passes in New
// York, which is worse than no guard at all.

import { readFileSync } from "fs";
import { join } from "path";

import {
  startClockState,
  formatEventStartLabel,
  type StartClockState,
} from "@/lib/eventKeyStats";

/** Any "H:MM" — the thing the reader must not see when we do not know it. */
const A_CLOCK = /\d{1,2}:\d{2}/;

/**
 * The four US Open quarter-finals from #3829 and their shared placeholder, and
 * one R16 control taken from the SAME payload at the same moment: ESPN had
 * published its hour (`15:00Z`) and its `start_is_tbd` was `false`.
 */
const QF_PLACEHOLDER = "2026-09-08T15:30:00+00:00";
const R16_REAL_START = "2026-09-07T15:00:00+00:00";

describe("#3829 startClockState — which of the three answers", () => {
  it("suppresses the clock for a fixture the authority says has no time", () => {
    expect(
      startClockState({
        startIsTbd: true,
        isTournamentSport: true,
        tournamentResolved: true,
      })
    ).toBe("tbd");
  });

  it("KEEPS the clock for a tennis fixture with a real published hour", () => {
    // THE CONTROL, and a strong one: same tournament, same endpoint, same
    // request, same code path as the four broken rows — differing only in the
    // fact under test. A control that is an MLB game proves only that the
    // tennis branch was never entered.
    expect(
      startClockState({
        startIsTbd: false,
        isTournamentSport: true,
        tournamentResolved: true,
      })
    ).toBe("clock");
  });

  it("KEEPS the clock when the fixture is not on today's order of play", () => {
    // `null` is the ordinary answer for every FINISHED match — it has long
    // since fallen off the slate — and a finished match's start time is
    // perfectly well known. Reading `null` as "no time" would strip the real
    // time off every completed match in the draw, which is a new bug in
    // exchange for the old one.
    expect(
      startClockState({
        startIsTbd: null,
        isTournamentSport: true,
        tournamentResolved: true,
      })
    ).toBe("clock");
  });

  it("holds while a tournament sport's answer is still in flight", () => {
    // THE FAIL DIRECTION. Before the fetch resolves we do not know, and an
    // unknown start must never render as a known one. A clock that paints
    // confidently and is then yanked is the same lie told briefly.
    expect(
      startClockState({
        startIsTbd: undefined,
        isTournamentSport: true,
        tournamentResolved: false,
      })
    ).toBe("pending");
  });

  it("never holds for a sport that does not ask — the whole rest of the site", () => {
    // An MLB page issues no `by-event` request at all, so `tournamentResolved`
    // is permanently false for it. An unscoped hold would blank the start time
    // on every non-tournament event on the site, forever.
    expect(
      startClockState({
        startIsTbd: undefined,
        isTournamentSport: false,
        tournamentResolved: false,
      })
    ).toBe("clock");
  });

  it("treats a non-boolean flag as no evidence, not as truth", () => {
    // A serialisation slip that put the string "false" on the wire would be
    // truthy in JS and would silently strip the clock off a match that has one.
    for (const junk of ["true", "false", 1, 0, {}] as unknown[]) {
      expect(
        startClockState({
          startIsTbd: junk as boolean,
          isTournamentSport: true,
          tournamentResolved: true,
        })
      ).toBe("clock");
    }
  });
});

describe("#3829 formatEventStartLabel — what the reader actually reads", () => {
  it("prints NO clock for the quarter-final that reported the bug", () => {
    const label = formatEventStartLabel(QF_PLACEHOLDER, "tbd");
    expect(label).not.toMatch(A_CLOCK);
    expect(label).toContain("TBD");
  });

  it("still names the DAY, because the day is real", () => {
    // ESPN files the fixture on the day it will be played and withholds only
    // the hour. Dropping the whole line would throw away a fact we hold — and
    // "we don't know when" is a worse answer than "tomorrow, time TBA" on the
    // page a reader opened precisely to find out when something happens.
    expect(formatEventStartLabel(QF_PLACEHOLDER, "tbd")).toMatch(/\w{3} \d+, \d{4}/);
  });

  it("says the same word the hub row says", () => {
    // `TournamentMatches.formatMatchTime` has printed `${day} · TBD` since
    // Q463. Two surfaces describing one fixture in two vocabularies is a
    // smaller version of the same defect.
    expect(formatEventStartLabel(QF_PLACEHOLDER, "tbd")).toMatch(/ · TBD$/);
  });

  it("prints the clock unchanged for the R16 control", () => {
    const label = formatEventStartLabel(R16_REAL_START, "clock");
    expect(label).toMatch(A_CLOCK);
    expect(label).not.toContain("TBD");
  });

  it("defaults to printing the clock when no state is supplied", () => {
    // The default is load-bearing: every non-tournament caller of this helper
    // must behave exactly as the page did before #3829.
    expect(formatEventStartLabel(R16_REAL_START)).toBe(
      formatEventStartLabel(R16_REAL_START, "clock")
    );
    expect(formatEventStartLabel(R16_REAL_START)).toMatch(A_CLOCK);
  });

  it("prints the day alone while pending — no clock and no premature TBD", () => {
    const label = formatEventStartLabel(QF_PLACEHOLDER, "pending");
    expect(label).not.toMatch(A_CLOCK);
    expect(label).not.toContain("TBD");
    expect(label).toMatch(/\w{3} \d+, \d{4}/);
  });

  it("returns empty rather than 'Invalid Date' for an unparseable stamp", () => {
    for (const state of ["clock", "tbd", "pending"] as StartClockState[]) {
      expect(formatEventStartLabel("not a date", state)).toBe("");
    }
  });
});

describe("#3829 the countdown is suppressed by the same state", () => {
  // The header ran BOTH halves of the lie: it printed the fabricated minute AND
  // counted down to it ("Starts in 1d 8h"). The page derives its countdown
  // suppression from `startClockState(...) !== "clock"`, so the two cannot
  // drift apart into a page that hides the clock and still counts to it.
  it("every state that hides the clock also stops the countdown", () => {
    const hides = (state: StartClockState) => state !== "clock";
    expect(hides("tbd")).toBe(true);
    expect(hides("pending")).toBe(true);
    expect(hides("clock")).toBe(false);
  });

  it("the page wires the countdown to that same predicate", () => {
    // A source scan, because the countdown lives in a `useEffect` inside a
    // default-exported page component. It is here to catch the specific
    // regression of someone gating the LABEL and forgetting the CLOCK — which
    // is how the bug reads to a reader either way.
    //
    // COMMENTS ARE STRIPPED FIRST, AND THAT IS THE WHOLE TEST. The first draft
    // scanned the raw source and SURVIVED the mutation it exists to catch:
    // deleting `hideStartClock` from the effect's condition left the sentence
    // "`hideStartClock` joins it" in the explanatory comment six lines above,
    // and the guard read that instead. A guard that a comment can satisfy is a
    // guard that passes for the wrong reason.
    const raw = readFileSync(
      join(process.cwd(), "app/events/[id]/page.tsx"),
      "utf8"
    );
    const code = raw
      .replace(/\/\*[\s\S]*?\*\//g, "")
      .replace(/^\s*\/\/.*$/gm, "");

    expect(code).toContain('const hideStartClock = startClock !== "clock"');

    // The condition the effect actually branches on — the text between `if (`
    // and the `setGameCountdown("")` that clears the clock.
    const clearsIt = code.indexOf('setGameCountdown("")');
    expect(clearsIt).toBeGreaterThan(-1);
    const condition = code.slice(code.lastIndexOf("if (", clearsIt), clearsIt);
    expect(condition).toContain("hideStartClock");
    // And the state it is derived from must be a dependency, or the effect
    // never re-runs when the tournament answer lands.
    const deps = code.slice(clearsIt, clearsIt + 700);
    expect(deps).toContain("hideStartClock]");
  });
});
