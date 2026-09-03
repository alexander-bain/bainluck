import fs from "fs";
import path from "path";
import {
  formatFinishedGameLabel,
  formatResolvesLabel,
  formatTournamentTimingLabel,
  formatTournamentWhenLabel,
  formatLiveClockLabel,
  isImpossibleFutureFinal,
  isPregameStatusDetail,
  TOURNAMENT_START_TRUST_DAYS,
  TOURNAMENT_START_TRUST_FUTURE_DAYS,
  trustedLiveClock,
} from "../../lib/gameTimeLabel";

/**
 * UX-P045 — a finished game must say WHEN it finished.
 *
 * Every clock here is INJECTED. Nothing is seeded relative to `Date.now()`, so a
 * run that straddles midnight cannot flip a label (gotcha #44 red-blocked two
 * deploys that way).
 */

// Monday 2026-08-10 14:00:00Z. Jest runs under TZ=UTC in CI, which is why the
// package script pins it — a local-TZ literal has red-ed master before.
const NOW = Date.parse("2026-08-10T14:00:00Z");

const YESTERDAY_GAME = "2026-08-09T20:10:00Z"; // the real Rays @ Mariners first pitch
const TODAY_GAME = "2026-08-10T01:40:00Z";
const LAST_WEEK_GAME = "2026-08-04T23:05:00Z";

describe("formatFinishedGameLabel — relative style (FeedCard + Discover)", () => {
  test("yesterday's game is named as yesterday, with the time", () => {
    expect(formatFinishedGameLabel(YESTERDAY_GAME, NOW, "relative")).toBe("Yesterday 8:10 PM");
  });

  test("a game earlier today is named as today", () => {
    expect(formatFinishedGameLabel(TODAY_GAME, NOW, "relative")).toBe("Today 1:40 AM");
  });

  test("older than yesterday falls back to a weekday + date, not a bare time", () => {
    const label = formatFinishedGameLabel(LAST_WEEK_GAME, NOW, "relative");
    expect(label).toBe("Tue, Aug 4");
    // The point of the fallback: it must still be a DATE. A bare clock time on a
    // six-day-old game is the ambiguity this whole module exists to remove.
    expect(label).not.toMatch(/\d{1,2}:\d{2}/);
  });

  test("relative is the default style", () => {
    expect(formatFinishedGameLabel(YESTERDAY_GAME, NOW)).toBe(
      formatFinishedGameLabel(YESTERDAY_GAME, NOW, "relative"),
    );
  });
});

describe("formatFinishedGameLabel — compact style preserves EventCard's output", () => {
  test("same-year finished game is month + day, with no time and no relative wording", () => {
    expect(formatFinishedGameLabel(YESTERDAY_GAME, NOW, "compact")).toBe("Aug 9");
  });

  test("a prior-year game carries the year", () => {
    expect(formatFinishedGameLabel("2025-10-30T23:05:00Z", NOW, "compact")).toBe("Oct 30, 2025");
  });

  test("compact never adopts the relative wording (this would be a silent restyle)", () => {
    const label = formatFinishedGameLabel(YESTERDAY_GAME, NOW, "compact");
    expect(label).not.toContain("Yesterday");
    expect(label).not.toContain("Today");
  });
});

describe("the impossible future-dated FINAL (L2-112 Item 2 / gotcha #14)", () => {
  // commence_time sometimes holds a Kalshi close/resolution timestamp rather than
  // a first pitch, so a settled event really can carry a future date. Printing it
  // beside a "Final" badge asserts an impossible thing.
  const FUTURE = "2026-08-12T18:00:00Z";

  test("is detected", () => {
    expect(isImpossibleFutureFinal(FUTURE, NOW)).toBe(true);
    expect(isImpossibleFutureFinal(YESTERDAY_GAME, NOW)).toBe(false);
  });

  test("renders NO date in either style, rather than a wrong one", () => {
    expect(formatFinishedGameLabel(FUTURE, NOW, "relative")).toBe("");
    expect(formatFinishedGameLabel(FUTURE, NOW, "compact")).toBe("");
  });
});

describe("degenerate input yields no date, never a crash or an 'Invalid Date'", () => {
  test.each([
    ["null", null],
    ["undefined", undefined],
    ["empty string", ""],
    ["unparseable", "not-a-timestamp"],
  ])("%s", (_label, value) => {
    expect(formatFinishedGameLabel(value as string | null | undefined, NOW, "relative")).toBe("");
    expect(formatFinishedGameLabel(value as string | null | undefined, NOW, "compact")).toBe("");
  });

  test("isImpossibleFutureFinal treats unparseable input as not-impossible", () => {
    expect(isImpossibleFutureFinal("not-a-timestamp", NOW)).toBe(false);
    expect(isImpossibleFutureFinal(null, NOW)).toBe(false);
  });
});

/**
 * THE ANTI-DRIFT GUARD — the reason this module exists.
 *
 * Three surfaces each grew their own answer to "when did this finish", and the
 * default landing page ended up with none. Extracting the logic only helps if a
 * fourth copy cannot quietly appear, so this asserts the shared module is the one
 * home for the wording and that every call site actually delegates to it.
 */
describe("anti-drift: one home for the finished-game label", () => {
  const FRONTEND = path.resolve(__dirname, "../..");
  const CALL_SITES = [
    "components/FeedCard.tsx",
    "components/EventCard.tsx",
    "components/discover/EventCard.tsx",
    // UX-P049 — the fourth surface. Added to the guard in the same commit that
    // added the call site, because a delegate that is not asserted is a copy
    // waiting to happen; that is the whole lesson of this describe block.
    "components/discover/TournamentCard.tsx",
  ];

  const read = (rel: string) => fs.readFileSync(path.join(FRONTEND, rel), "utf8");

  test.each(CALL_SITES)("%s imports the shared label module", (rel) => {
    expect(read(rel)).toMatch(/from ["']@\/lib\/gameTimeLabel["']/);
  });

  test.each(CALL_SITES)("%s does not re-implement the relative wording", (rel) => {
    const src = read(rel);
    expect(src).not.toContain("Yesterday ");
  });

  test.each(CALL_SITES)("%s does not re-implement the future-final guard", (rel) => {
    // The two old copies both spelled it as a raw getTime() comparison against a
    // local `now`. A new one would mean the guard has forked again.
    expect(read(rel)).not.toMatch(/getTime\(\)\s*>\s*now\.getTime\(\)/);
  });

  test("the word 'Yesterday' lives in exactly one lib module", () => {
    const libDir = path.join(FRONTEND, "lib");
    const owners: string[] = [];
    const walk = (dir: string) => {
      for (const entry of fs.readdirSync(dir, { withFileTypes: true })) {
        const full = path.join(dir, entry.name);
        if (entry.isDirectory()) walk(full);
        else if (/\.tsx?$/.test(entry.name) && fs.readFileSync(full, "utf8").includes("Yesterday")) {
          owners.push(path.relative(FRONTEND, full));
        }
      }
    };
    walk(libDir);
    expect(owners).toEqual(["lib/gameTimeLabel.ts"]);
  });
});

/**
 * UX-P049 — a tournament card must say WHEN, and must stay silent when its
 * timestamp is not a start date.
 *
 * Same discipline as above: every clock is INJECTED (gotcha #44). The specimens
 * are the real 2026-08-10 15:40 PT production slate, when tournaments were 8 of
 * the 20 cards on the default landing page.
 */
describe("formatTournamentWhenLabel", () => {
  // Monday 2026-08-10 22:40:00Z (15:40 PT), the measured slate's instant.
  const NOW_T = Date.parse("2026-08-10T22:40:00Z");

  // Verbatim from the production payload.
  const DANISH = "2026-08-13T00:00:00+00:00"; // 3 days out
  const FEDEX = "2026-08-08T16:01:09+00:00"; // 2 days ago
  const AIG = "2026-08-02T18:58:17+00:00"; // 8 days ago — outside the window
  const MAJOR_2026 = "2026-06-22T00:57:03+00:00"; // 7 weeks ago — not a start date
  const MAJOR_2027 = "2028-01-14T15:00:00+00:00"; // another year

  /**
   * The eight cards the default landing page actually rendered at NOW_T, verbatim
   * from `GET /api/feed?limit=20&offset=0&event_pct=0.15` — the exact params
   * `app/discover/page.tsx` ships. Feed items were 21; the other 13 are concepts
   * the client suppresses as empty envelopes, so these 8 ARE the landing page.
   *
   * UX-P050 adds `resolution_date`, which was on the wire on 8 of 8 all along and
   * read by no branch of the card.
   */
  const SLATE = [
    { name: "Danish Golf Championship", commence: DANISH, resolution: "2026-08-30T00:00:00+00:00" },
    { name: "Golfers To Win A Pga Tour Major Before 2030", commence: "2026-07-19T18:17:17+00:00", resolution: "2030-07-07T14:00:00+00:00" },
    { name: "Fedex St Jude Championship", commence: FEDEX, resolution: "2026-08-16T00:00:00+00:00" },
    { name: "Golfers To Win A Pga Tour Major In 2027", commence: MAJOR_2027, resolution: "2028-01-14T15:00:00+00:00" },
    { name: "The Standard Portland Classic", commence: "2026-08-30T00:00:00+00:00", resolution: "2026-08-30T00:00:00+00:00" },
    { name: "Indianapolis", commence: "2026-08-20T00:00:00+00:00", resolution: "2026-08-23T00:00:00+00:00" },
    { name: "Aig Women S Open Womens", commence: AIG, resolution: "2026-08-16T00:00:00+00:00" },
    { name: "Golfers To Win A Pga Tour Major In 2026", commence: MAJOR_2026, resolution: "2026-12-31T15:00:00+00:00" },
  ];

  test("an upcoming tournament names its start day", () => {
    expect(formatTournamentWhenLabel(DANISH, NOW_T)).toBe("Starts Thu, Aug 13");
  });

  test("one that has already teed off says so, in the past tense", () => {
    expect(formatTournamentWhenLabel(FEDEX, NOW_T)).toBe("Started Sat, Aug 8");
  });

  test("a timestamp in another year carries the year", () => {
    // "Starts Thu, Jan 14" would read as five months away when it is seventeen.
    // UX-P050 moved this case off MAJOR_2027 (+521d), which is now suppressed as
    // not-a-start-date; a real tournament five months out still names its year.
    expect(formatTournamentWhenLabel("2027-01-14T15:00:00+00:00", NOW_T)).toBe(
      "Starts Thu, Jan 14, 2027",
    );
  });

  describe("the stale-timestamp window — the trap this exists for", () => {
    test("a season-long futures market's stale timestamp renders NOTHING", () => {
      // "Golfers To Win A PGA Tour Major In 2026". Printing "Started Mon, Jun 22"
      // would state something false to fix a card that was merely silent.
      expect(formatTournamentWhenLabel(MAJOR_2026, NOW_T)).toBe("");
    });

    test("8 days past is outside the window", () => {
      expect(formatTournamentWhenLabel(AIG, NOW_T)).toBe("");
    });

    test("the boundary is inclusive on the trusted side (gotcha #43, both directions)", () => {
      const justInside = new Date(NOW_T - (TOURNAMENT_START_TRUST_DAYS * 86_400_000 - 60_000));
      const justOutside = new Date(NOW_T - (TOURNAMENT_START_TRUST_DAYS * 86_400_000 + 60_000));
      expect(formatTournamentWhenLabel(justInside.toISOString(), NOW_T)).not.toBe("");
      expect(formatTournamentWhenLabel(justOutside.toISOString(), NOW_T)).toBe("");
    });

  });

  /**
   * UX-P050. THIS BLOCK REPLACES AN ASSERTION THAT PINNED THE BLIND SPOT.
   *
   * The suite previously asserted "no future date is ever suppressed, however
   * distant", on the reasoning that the window is a staleness rule and not a
   * horizon. That reasoning protected the wrong thing: the trap the backward
   * window exists for — a season-long market whose commence_time is really a
   * resolution timestamp — is not a property of the PAST, and the identical lie
   * walked in through the future. "Golfers To Win A PGA Tour Major In 2027"
   * printed "Starts Fri, Jan 14, 2028" on the default landing page.
   */
  describe("the forward window — the same trap, entering from the other side", () => {
    test("a season-long market dated years out no longer claims a start", () => {
      expect(formatTournamentWhenLabel(MAJOR_2027, NOW_T)).toBe("");
    });

    test("both directions, at the boundary (gotcha #43)", () => {
      const justInside = new Date(NOW_T + (TOURNAMENT_START_TRUST_FUTURE_DAYS * 86_400_000 - 60_000));
      const justOutside = new Date(NOW_T + (TOURNAMENT_START_TRUST_FUTURE_DAYS * 86_400_000 + 60_000));
      expect(formatTournamentWhenLabel(justInside.toISOString(), NOW_T)).not.toBe("");
      expect(formatTournamentWhenLabel(justOutside.toISOString(), NOW_T)).toBe("");
    });

    test("the two genuine upcoming tournaments on the slate keep their dates", () => {
      // The whole risk of a forward bound is silencing a real tournament. These
      // are the only two on the measured slate that are actually scheduled.
      expect(formatTournamentWhenLabel("2026-08-30T00:00:00+00:00", NOW_T)).not.toBe(""); // +19d
      expect(formatTournamentWhenLabel("2026-08-20T00:00:00+00:00", NOW_T)).not.toBe(""); // +9d
    });
  });

  describe("relative wording", () => {
    test("later today", () => {
      expect(formatTournamentWhenLabel("2026-08-10T23:30:00Z", NOW_T)).toBe("Starts today");
    });
    test("earlier today", () => {
      expect(formatTournamentWhenLabel("2026-08-10T09:00:00Z", NOW_T)).toBe("Started today");
    });
    test("tomorrow", () => {
      expect(formatTournamentWhenLabel("2026-08-11T14:00:00Z", NOW_T)).toBe("Starts tomorrow");
    });
    test("yesterday", () => {
      expect(formatTournamentWhenLabel("2026-08-09T14:00:00Z", NOW_T)).toBe("Started yesterday");
    });
  });

  describe("absent and unusable inputs render nothing, never a placeholder", () => {
    test.each([null, undefined, "", "not-a-date"])("%p", (input) => {
      expect(formatTournamentWhenLabel(input as string | null | undefined, NOW_T)).toBe("");
    });
  });

  test("the measured slate: 4 of 8 have a trustworthy START date", () => {
    const labelled = SLATE.map((t) => formatTournamentWhenLabel(t.commence, NOW_T)).filter(Boolean);
    // UX-P049 recorded 5 here. UX-P050 removes one of them, and removing it is the
    // point: the fifth was MAJOR_2027's false "Starts Fri, Jan 14, 2028". Before
    // UX-P049 all 8 rendered no date; 4 now carry a start they can stand behind,
    // and the other 4 are picked up by the resolution fallback below.
    expect(labelled).toHaveLength(4);
  });

  /**
   * UX-P050 Item 2 — the discriminator #1700 concluded did not exist.
   */
  describe("formatResolvesLabel", () => {
    test("a four-year question says which year decides it", () => {
      expect(formatResolvesLabel("2030-07-07T14:00:00+00:00", NOW_T)).toBe(
        "Resolves Jul 7, 2030",
      );
    });

    test("the year is printed even when it is the current one", () => {
      // "Resolves Dec 31" invites the reader to supply a year, and on a card whose
      // siblings resolve in 2028 and 2030 that guess is worth stating for them.
      expect(formatResolvesLabel("2026-12-31T15:00:00+00:00", NOW_T)).toBe(
        "Resolves Dec 31, 2026",
      );
    });

    test("a resolution date that has passed says NOTHING", () => {
      // The card must not print "Resolves <a date that has gone>" — and must not
      // conclude settlement from it either. `resolution_date` is the SCHEDULED
      // resolution, not an observed one.
      expect(formatResolvesLabel("2026-08-01T00:00:00+00:00", NOW_T)).toBe("");
    });

    test.each([null, undefined, "", "not-a-date"])(
      "absent or unusable input renders nothing: %p",
      (input) => {
        expect(formatResolvesLabel(input as string | null | undefined, NOW_T)).toBe("");
      },
    );
  });

  describe("formatTournamentTimingLabel — fallback, never a second line", () => {
    test("a real start date wins; the resolution date stays off the card", () => {
      const label = formatTournamentTimingLabel(null, DANISH, "2026-08-30T00:00:00+00:00", NOW_T);
      expect(label).toBe("Starts Thu, Aug 13");
      expect(label).not.toContain("Resolves");
    });

    test("no trustworthy start date falls back to when the question is decided", () => {
      expect(formatTournamentTimingLabel(null, MAJOR_2026, "2026-12-31T15:00:00+00:00", NOW_T)).toBe(
        "Resolves Dec 31, 2026",
      );
    });

    test("the false 'Starts Fri, Jan 14, 2028' becomes a true 'Resolves'", () => {
      expect(formatTournamentTimingLabel(null, MAJOR_2027, "2028-01-14T15:00:00+00:00", NOW_T)).toBe(
        "Resolves Jan 14, 2028",
      );
    });

    test("neither usable renders nothing rather than a placeholder", () => {
      expect(formatTournamentTimingLabel(null, MAJOR_2026, null, NOW_T)).toBe("");
      expect(formatTournamentTimingLabel(null, null, "2020-01-01T00:00:00+00:00", NOW_T)).toBe("");
    });

    /**
     * THE ACCEPTANCE. Card-by-card over the exact eight, so a future change that
     * moves one of them has to say which one and why.
     */
    test("the measured slate: 8 of 8 now carry a timing line, 0 of them false", () => {
      const rendered = SLATE.map((t) => formatTournamentTimingLabel(null, t.commence, t.resolution, NOW_T));
      expect(rendered).toEqual([
        "Starts Thu, Aug 13",   // Danish Golf Championship — unchanged
        "Resolves Jul 7, 2030", // Majors Before 2030        — was ""
        "Started Sat, Aug 8",   // FedEx St Jude             — unchanged
        "Resolves Jan 14, 2028",// Majors In 2027            — was "Starts Fri, Jan 14, 2028"
        "Starts Sun, Aug 30",   // Portland Classic          — unchanged
        "Starts Thu, Aug 20",   // Indianapolis              — unchanged
        "Resolves Aug 16, 2026",// AIG Women's Open          — was ""
        "Resolves Dec 31, 2026",// Majors In 2026            — was ""
      ]);
      expect(rendered.filter(Boolean)).toHaveLength(8);
    });

    test("the four cards that already read correctly are untouched (both directions)", () => {
      const unchanged = SLATE.filter((t) => formatTournamentWhenLabel(t.commence, NOW_T));
      expect(unchanged.map((t) => t.name)).toEqual([
        "Danish Golf Championship",
        "Fedex St Jude Championship",
        "The Standard Portland Classic",
        "Indianapolis",
      ]);
      for (const t of unchanged) {
        expect(formatTournamentTimingLabel(null, t.commence, t.resolution, NOW_T)).toBe(
          formatTournamentWhenLabel(t.commence, NOW_T),
        );
      }
    });
  });
});

/**
 * UX-P051 (#1710) — a live game's clock says what period it is, or says nothing.
 *
 * The specimens are the real two live games on the default landing page at
 * 2026-08-10 ~17:00 PT, read from BOTH `/api/feed?limit=60` and
 * `/api/events/{id}`. One of the two was inside the window this fixes.
 */
describe("the live clock — ESPN's PRE-GAME sentence is not a period", () => {
  /** Event 15192197, Toronto Tempo @ Atlanta Dream (WNBA). status live, 0–0. */
  const WNBA_PREGAME = {
    period: "Mon, August 10th at 8:00 PM EDT",
    game_clock: "0.0",
  };
  /** Event 15187586, Phillies @ Cardinals (MLB). Genuinely in progress. */
  const MLB_INGAME = { period: "Bottom 1st", game_clock: undefined };
  /**
   * THE SAME EVENT 15192197, re-read ~20 minutes later, once ESPN caught up.
   * This is the proof that every game passes through the pre-game window — and
   * it exposed the opposite defect: basketball details EMBED the clock.
   */
  const WNBA_INGAME = { period: "10:00 - 1st Quarter", game_clock: "10:00" };

  describe("isPregameStatusDetail", () => {
    test("the measured production specimen is recognised", () => {
      expect(isPregameStatusDetail(WNBA_PREGAME.period)).toBe(true);
    });

    test.each([
      "Sun, September 7th at 1:00 PM EDT",
      "Tue, August 11th at 10:05 PM PDT",
      "Sat, October 4th at 12:30 AM GMT",
      "Scheduled",
      "scheduled",
    ])("%s reads as pre-game", (detail) => {
      expect(isPregameStatusDetail(detail)).toBe(true);
    });

    /**
     * The other direction, and it is the one that matters — suppression is the
     * sharp edge. Every real in-game/settled detail ESPN emits must survive.
     */
    test.each([
      "Bottom 1st",
      "Top 9th",
      "Q3 4:22",
      "4:22 - 3rd Quarter",
      "1st Quarter",
      "2nd Half",
      "End of 3rd",
      "End of 1st Half",
      "End of Regulation",
      "Halftime",
      "Overtime",
      "Rain Delay",
      "Delayed",
      "Postponed",
      "Final",
      "Final/OT",
      "Final/10",
      "Shootout",
    ])("%s is NOT pre-game", (detail) => {
      expect(isPregameStatusDetail(detail)).toBe(false);
    });

    test("absent, empty and whitespace details are not claimed as pre-game", () => {
      expect(isPregameStatusDetail(null)).toBe(false);
      expect(isPregameStatusDetail(undefined)).toBe(false);
      expect(isPregameStatusDetail("")).toBe(false);
      expect(isPregameStatusDetail("   ")).toBe(false);
    });
  });

  describe("trustedLiveClock — the clock goes with the period", () => {
    /**
     * Dropping only the period is exactly what left the Sports tab printing a
     * bare "0.0": both fields come from the same ESPN status payload, so if the
     * period says the game has not started, "0.0" is a default and not a clock.
     */
    test("a pre-game period takes its 0.0 clock down with it", () => {
      expect(trustedLiveClock(WNBA_PREGAME.period, WNBA_PREGAME.game_clock)).toEqual({
        period: "",
        gameClock: "",
      });
    });

    test("a real in-game payload passes through untouched", () => {
      expect(trustedLiveClock("Q3", "4:22")).toEqual({ period: "Q3", gameClock: "4:22" });
      expect(trustedLiveClock(MLB_INGAME.period, MLB_INGAME.game_clock)).toEqual({
        period: "Bottom 1st",
        gameClock: "",
      });
    });

    test("missing fields become empty strings, never 'undefined' on screen", () => {
      expect(trustedLiveClock(null, null)).toEqual({ period: "", gameClock: "" });
      expect(trustedLiveClock(undefined, "8:42")).toEqual({ period: "", gameClock: "8:42" });
    });

    /**
     * The second rule, from the same event once ESPN caught up. Without this,
     * joining the two fields would print "10:00 - 1st Quarter 10:00".
     */
    test("a clock already spelled inside the period is not repeated", () => {
      expect(trustedLiveClock(WNBA_INGAME.period, WNBA_INGAME.game_clock)).toEqual({
        period: "10:00 - 1st Quarter",
        gameClock: "",
      });
      expect(trustedLiveClock("4:22 - 3rd Quarter", "4:22")).toEqual({
        period: "4:22 - 3rd Quarter",
        gameClock: "",
      });
    });

    /**
     * And the other direction — the dedup must not eat a real clock on a
     * coincidental substring. A loose test would delete "1" because "Bottom 1st"
     * contains the character.
     */
    test("a clock that is not clock-shaped is never deleted as a duplicate", () => {
      expect(trustedLiveClock("Bottom 1st", "1")).toEqual({
        period: "Bottom 1st",
        gameClock: "1",
      });
      expect(trustedLiveClock("2nd Half", "2")).toEqual({ period: "2nd Half", gameClock: "2" });
    });

    test("a genuinely distinct clock survives beside its period", () => {
      expect(trustedLiveClock("1st Quarter", "8:42")).toEqual({
        period: "1st Quarter",
        gameClock: "8:42",
      });
    });

    /**
     * live/055 (#2815) — the third rule, and the case the shape gate above could
     * not see.
     *
     * The rule-2 dedup is gated on CLOCK_TOKEN_RE precisely so it cannot delete
     * "1" out of "Bottom 1st" (the test directly above). That gate is correct
     * and it is also why a settled game slipped through: production event
     * 15293206 ships `period: "Final"` with `game_clock: "Final"` — identical,
     * and neither of them clock-shaped — so the event page's chart footer
     * printed "Final Final 3 - 8".
     *
     * Exact equality needs no shape gate: two fields carrying the same string
     * cannot be two facts. Nothing wider than equality, deliberately — a
     * substring test over arbitrary strings would re-open the false positive
     * the gate above exists to prevent, which is why that test runs beside this.
     */
    test("a clock that merely repeats the period verbatim is dropped", () => {
      expect(trustedLiveClock("Final", "Final")).toEqual({
        period: "Final",
        gameClock: "",
      });
      // Trimmed and case-insensitive: the same word is the same word.
      expect(trustedLiveClock("Final", " final ")).toEqual({
        period: "Final",
        gameClock: "",
      });
      expect(trustedLiveClock("Halftime", "Halftime")).toEqual({
        period: "Halftime",
        gameClock: "",
      });
    });

    test("the verbatim-repeat rule does not fire on a merely similar clock", () => {
      // "Final/OT" is not "Final". Two different strings are two facts, and this
      // rule is equality only — it must leave them both standing.
      expect(trustedLiveClock("Final/OT", "Final")).toEqual({
        period: "Final/OT",
        gameClock: "Final",
      });
      expect(trustedLiveClock("Final", "0:00")).toEqual({
        period: "Final",
        gameClock: "0:00",
      });
    });
  });

  /**
   * THE ACCEPTANCE, surface by surface, over the one production payload — so a
   * future change that moves any of the four has to say which and why.
   *
   * Each row reproduces its caller's own composition. The BEFORE column is what
   * the pre-patch expression produced, transcribed from the code it replaced.
   */
  describe("the four surfaces, on event 15192197", () => {
    const discover = (p?: string, c?: string) => formatLiveClockLabel(p, null) || "Live";
    const sportsTab = (p?: string, c?: string) => formatLiveClockLabel(p, c) || "LIVE";
    const eventChip = (p?: string, c?: string, hl?: string) =>
      formatLiveClockLabel(p, c) || hl || "LIVE";
    const detailPage = (p?: string, c?: string) => formatLiveClockLabel(p, c, " · ") || "LIVE";

    const { period, game_clock } = WNBA_PREGAME;

    test("Discover (default landing page): the 30-character sentence is gone", () => {
      // BEFORE: "Mon, August 10th at 8:00 PM EDT"
      expect(discover(period, game_clock)).toBe("Live");
    });

    test("Sports tab: the orphaned bare clock is gone", () => {
      // BEFORE: "0.0" — the length<=10 heuristic dropped the period and kept the clock.
      expect(sportsTab(period, game_clock)).toBe("LIVE");
    });

    test("search / my-stuff chip: sentence + clock is gone", () => {
      // BEFORE: "Mon, August 10th at 8:00 PM EDT 0.0"
      expect(eventChip(period, game_clock)).toBe("LIVE");
      // The chip's own highlight fallback still wins over the generic word.
      expect(eventChip(period, game_clock, "Close game")).toBe("Close game");
    });

    test("event detail page: sentence · clock is gone", () => {
      // BEFORE: "Mon, August 10th at 8:00 PM EDT · 0.0"
      expect(detailPage(period, game_clock)).toBe("LIVE");
    });

    /**
     * Both directions, gotcha #43. A genuine in-game payload must not move —
     * this is a suppression, and a suppression that changes a healthy card is a
     * regression. The one deliberate exception is stated in its own test below.
     */
    test("the genuinely-live MLB game is byte-identical on the three cards", () => {
      expect(discover(MLB_INGAME.period, MLB_INGAME.game_clock)).toBe("Bottom 1st");
      expect(sportsTab(MLB_INGAME.period, MLB_INGAME.game_clock)).toBe("Bottom 1st");
      expect(eventChip(MLB_INGAME.period, MLB_INGAME.game_clock)).toBe("Bottom 1st");
    });

    test("a period-plus-distinct-clock payload is byte-identical on all four", () => {
      expect(discover("Q3", "4:22")).toBe("Q3");
      expect(sportsTab("Q3", "4:22")).toBe("Q3 4:22");
      expect(eventChip("Q3", "4:22")).toBe("Q3 4:22");
      expect(detailPage("Q3", "4:22")).toBe("Q3 · 4:22");
    });

    /**
     * THE ONE DELIBERATE BEHAVIOUR CHANGE, stated rather than buried. The detail
     * page required BOTH fields before printing either, which was never a
     * principle — and with duplicate clocks now dropped it would have made the
     * badge read "LIVE" on every NBA/WNBA game. Both rows below are live
     * production payloads.
     */
    describe("event detail page: the both-required rule is replaced", () => {
      test("basketball no longer repeats the clock it already spelled", () => {
        // BEFORE: "10:00 - 1st Quarter · 10:00"
        expect(detailPage(WNBA_INGAME.period, WNBA_INGAME.game_clock)).toBe("10:00 - 1st Quarter");
      });

      test("baseball now says the inning instead of the generic word", () => {
        // BEFORE: "LIVE" — `period && game_clock` was false, so a real period was thrown away.
        expect(detailPage(MLB_INGAME.period, MLB_INGAME.game_clock)).toBe("Bottom 1st");
      });
    });

    /**
     * The same duplicate, on the two card surfaces that have been printing it all
     * along — and the reason the Sports tab could not simply start joining the
     * fields: it would have adopted the duplicate rather than the fix.
     */
    test("no surface repeats a clock the period already contains", () => {
      const { period, game_clock } = WNBA_INGAME;
      expect(discover(period, game_clock)).toBe("10:00 - 1st Quarter");
      // BEFORE: "10:00" — the character-count heuristic dropped the period instead.
      expect(sportsTab(period, game_clock)).toBe("10:00 - 1st Quarter");
      // BEFORE: "10:00 - 1st Quarter 10:00"
      expect(eventChip(period, game_clock)).toBe("10:00 - 1st Quarter");
    });

    /**
     * The fix in the OTHER direction. The Sports tab's length heuristic silently
     * dropped every period longer than ten characters, so these games showed a
     * bare clock with no period at all.
     */
    test.each([
      ["1st Quarter", "8:42", "1st Quarter 8:42"],
      ["End of 1st Half", "0:00", "End of 1st Half 0:00"],
      ["End of Regulation", "0:00", "End of Regulation 0:00"],
    ])("Sports tab now keeps the real long label %s", (p, c, expected) => {
      expect(p.length).toBeGreaterThan(10); // the old heuristic's cut-off
      expect(sportsTab(p, c)).toBe(expected);
    });
  });
});

/**
 * UX-P051 — the anti-drift guard IS the deliverable.
 *
 * Four surfaces each grew their own answer to "may I believe this clock", and
 * they disagreed for as long as all four existed. Extracting the rule only helps
 * if a fifth copy cannot appear, so this asserts that no renderer reads the raw
 * fields for display.
 */
describe("anti-drift: one home for the live-clock trust rule", () => {
  const FRONTEND = path.resolve(__dirname, "../..");
  const LIVE_CLOCK_SITES = [
    "components/FeedCard.tsx",
    "components/EventCard.tsx",
    "components/discover/EventCard.tsx",
    "app/events/[id]/page.tsx",
  ];

  const read = (rel: string) => fs.readFileSync(path.join(FRONTEND, rel), "utf8");

  test.each(LIVE_CLOCK_SITES)("%s imports the shared module", (rel) => {
    expect(read(rel)).toMatch(/from ["']@\/lib\/gameTimeLabel["']/);
  });

  /**
   * The raw fields may still be READ — something has to hand them to the module.
   * What must never happen again is a site reading them and then deciding for
   * itself, so every occurrence has to sit on a line that passes them straight
   * through. That is the difference between a delegate and a fifth copy.
   */
  const RAW_FIELD_RE = /espn\??\.\s*(?:period|game_clock)/;
  const DELEGATES_RE = /trustedLiveClock|formatLiveClockLabel/;

  test.each(LIVE_CLOCK_SITES)("%s only reads the raw espn clock to delegate it", (rel) => {
    const offenders = read(rel)
      .split("\n")
      .map((line, i) => ({ line, n: i + 1 }))
      .filter(({ line }) => RAW_FIELD_RE.test(line) && !DELEGATES_RE.test(line))
      // A comment explaining the rule is not a second implementation of it.
      .filter(({ line }) => !/^\s*(?:\/\/|\*|\/\*)/.test(line));
    expect(offenders.map((o) => `${rel}:${o.n}`)).toEqual([]);
  });

  /**
   * live/055 (#2815) — WHY THE SCAN ABOVE COULD NOT SEE THE EIGHTH COPY.
   *
   * `RAW_FIELD_RE` keys on `espn?.period` / `espn?.game_clock`, which is the
   * shape the four CARD surfaces read. `components/GamePlayCard.tsx` — the
   * event page's chart footer — reads the same two facts off a different
   * carrier: `ActiveChartPoint.period` / `.clock`, assembled by `OddsChart`
   * from the snapshot series. It was therefore never in scope of the guard,
   * and it duly grew its own raw `[period, clock].join(" ")`, which printed
   * "Final Final 3 - 8" on every settled game.
   *
   * The lesson is about the guard, not the card: an anti-drift scan pinned to
   * ONE field name only protects the callers that spell it that way. This
   * covers the chart-point carrier so a ninth copy cannot arrive through it.
   */
  const CHART_POINT_SITES = ["components/GamePlayCard.tsx"];
  /** `point.period` / `point.clock` — but never `point.clockApprox`, a real separate fact. */
  const CHART_CLOCK_RE = /\bpoint\??\.\s*(?:period|clock)\b/;

  test.each(CHART_POINT_SITES)("%s imports the shared module", (rel) => {
    expect(read(rel)).toMatch(/from ["']@\/lib\/gameTimeLabel["']/);
  });

  test.each(CHART_POINT_SITES)("%s only reads the raw chart clock to delegate it", (rel) => {
    const offenders = read(rel)
      .split("\n")
      .map((line, i) => ({ line, n: i + 1 }))
      .filter(({ line }) => CHART_CLOCK_RE.test(line) && !DELEGATES_RE.test(line))
      .filter(({ line }) => !/^\s*(?:\/\/|\*|\/\*)/.test(line));
    expect(offenders.map((o) => `${rel}:${o.n}`)).toEqual([]);
  });

  /**
   * The scan above is only worth its line count if it can FAIL. It reads real
   * files, so a typo'd path or a renamed field would make it pass over nothing
   * at all — the vacuous-guard trap. This asserts the matcher actually fires on
   * the pre-fix expression, which is the exact text `GamePlayCard` used to hold.
   */
  test("the chart-clock matcher fires on the shape it is meant to catch", () => {
    const preFix = [
      "  const periodDisplay = formatPeriod(point.period);",
      '  const clockText = point.clock ? `${point.clockApprox ? "~" : ""}${point.clock}` : "";',
    ];
    expect(preFix.filter((l) => CHART_CLOCK_RE.test(l) && !DELEGATES_RE.test(l))).toHaveLength(2);
    // ...and does NOT fire on the approximate-clock flag, a genuinely separate field.
    expect(CHART_CLOCK_RE.test("point.clockApprox ? 1 : 0")).toBe(false);
  });

  test("the length heuristic that guessed at this is gone", () => {
    // The single site that had any guard used the period's character count as a
    // proxy for its meaning. Nothing may key on that again.
    expect(read("components/FeedCard.tsx")).not.toMatch(/period\.length/);
  });

  /**
   * The rule itself must live in exactly one module. `at 8:00 PM` is the shape
   * the classifier keys on; a second file matching on it means the rule forked.
   */
  test("the pre-game sentence rule lives in exactly one lib module", () => {
    const owners: string[] = [];
    const walk = (dir: string) => {
      for (const entry of fs.readdirSync(dir, { withFileTypes: true })) {
        const full = path.join(dir, entry.name);
        if (entry.isDirectory()) walk(full);
        else if (/\.tsx?$/.test(entry.name) && fs.readFileSync(full, "utf8").includes("PREGAME_START_SENTENCE_RE")) {
          owners.push(path.relative(FRONTEND, full));
        }
      }
    };
    walk(path.join(FRONTEND, "lib"));
    expect(owners).toEqual(["lib/gameTimeLabel.ts"]);
  });
});

/**
 * C270 P1 — a date-only resolution date must render its DECLARED calendar day.
 *
 * `new Date("2026-12-31")` parses as UTC midnight; `toLocaleDateString` then
 * renders that instant in the browser's zone, so everyone west of UTC saw
 * "Resolves Dec 30, 2026". Golf produces this shape live — DataGolf's semantic
 * `end_date` string is written straight into `resolution_date`.
 *
 * ── HOW THIS SUITE IS BUILT, AND WHY IT LOOKS LIKE TWO TESTS OF ONE THING ──
 *
 * The obvious test — set `process.env.TZ = "America/Los_Angeles"` and assert —
 * DOES NOT WORK, and it fails in the dangerous direction. Node fixes the zone
 * at first `Date` use, so an in-test assignment is ignored and the case simply
 * re-asserts whatever zone the runner already had. Written that way it passes
 * in CI (UTC) forever while claiming to cover Pacific: a test that reports
 * green for a reason unrelated to what it says it checks. That is the same
 * species as the bug itself, which is precisely how the bug survived.
 *
 * So the coverage is split, deliberately:
 *
 *   1. BEHAVIOUR, in the ambient zone. Meaningful when a human runs the suite
 *      in a negative-offset zone (verified: 4/4 of these fail in Pacific with
 *      the fix reverted, printing exactly Dec 30 / Feb 28).
 *   2. THE MECHANISM, zone-independent. Asserts the formatter *asks for* UTC on
 *      a date-only value and does not on a timestamp. This one catches a
 *      regression in CI's UTC, where the behavioural cases cannot.
 */
describe("formatResolvesLabel — semantic dates survive the timezone (C270 P1)", () => {
  const NOW = Date.UTC(2026, 7, 11);

  it.each([
    ["2026-12-31", "Resolves Dec 31, 2026"],
    // A leap day is the cruellest version: the off-by-one crosses a month AND
    // lands on a date that does not exist in most years.
    ["2028-02-29", "Resolves Feb 29, 2028"],
  ])("%s renders as its declared day in the ambient zone", (input, expected) => {
    expect(formatResolvesLabel(input, NOW)).toBe(expected);
  });

  it("asks for UTC on a date-only value — the guard CI can actually see", () => {
    const spy = jest.spyOn(Date.prototype, "toLocaleDateString");
    try {
      formatResolvesLabel("2026-12-31", NOW);
      expect(spy).toHaveBeenCalledWith([], expect.objectContaining({ timeZone: "UTC" }));
    } finally {
      spy.mockRestore();
    }
  });

  it("does NOT force UTC on a timestamp — that one really is an instant", () => {
    // The both-directions half (gotcha #43): over-applying the fix would answer
    // "when does this resolve, my time" in the wrong zone for real timestamps.
    const spy = jest.spyOn(Date.prototype, "toLocaleDateString");
    try {
      formatResolvesLabel("2026-12-31T18:00:00Z", NOW);
      const opts = spy.mock.calls[0]?.[1] ?? {};
      expect(opts).not.toHaveProperty("timeZone");
    } finally {
      spy.mockRestore();
    }
  });
});
