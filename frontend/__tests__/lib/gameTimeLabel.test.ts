import fs from "fs";
import path from "path";
import {
  formatFinishedGameLabel,
  formatTournamentWhenLabel,
  isImpossibleFutureFinal,
  TOURNAMENT_START_TRUST_DAYS,
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

  test("an upcoming tournament names its start day", () => {
    expect(formatTournamentWhenLabel(DANISH, NOW_T)).toBe("Starts Thu, Aug 13");
  });

  test("one that has already teed off says so, in the past tense", () => {
    expect(formatTournamentWhenLabel(FEDEX, NOW_T)).toBe("Started Sat, Aug 8");
  });

  test("a timestamp in another year carries the year", () => {
    // "Starts Fri, Jan 14" would read as months away when it is seventeen.
    expect(formatTournamentWhenLabel(MAJOR_2027, NOW_T)).toBe("Starts Fri, Jan 14, 2028");
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

    test("no future date is ever suppressed, however distant", () => {
      // The window is a staleness rule, not a horizon. A 2030 market still says when.
      expect(formatTournamentWhenLabel("2030-04-11T00:00:00Z", NOW_T)).toBe("Starts Thu, Apr 11, 2030");
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

  test("the measured slate: 5 of 8 gain a date, 3 correctly stay silent", () => {
    const SLATE = [
      DANISH,
      "2026-07-19T18:17:17+00:00", // Majors Before 2030 — stale
      FEDEX,
      MAJOR_2027,
      "2026-08-30T00:00:00+00:00", // Portland Classic
      "2026-08-20T00:00:00+00:00", // Indianapolis
      AIG,
      MAJOR_2026,
    ];
    const labelled = SLATE.map((t) => formatTournamentWhenLabel(t, NOW_T)).filter(Boolean);
    // Before this change every one of the 8 rendered no date at all.
    expect(labelled).toHaveLength(5);
  });
});
