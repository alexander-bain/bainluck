import fs from "fs";
import path from "path";
import {
  formatFinishedGameLabel,
  formatTournamentResolvesLabel,
  formatTournamentTimingLabel,
  formatTournamentWhenLabel,
  isImpossibleFutureFinal,
  TOURNAMENT_START_TRUST_DAYS,
  TOURNAMENT_START_TRUST_FUTURE_DAYS,
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
  describe("formatTournamentResolvesLabel", () => {
    test("a four-year question says which year decides it", () => {
      expect(formatTournamentResolvesLabel("2030-07-07T14:00:00+00:00", NOW_T)).toBe(
        "Resolves Jul 7, 2030",
      );
    });

    test("the year is printed even when it is the current one", () => {
      // "Resolves Dec 31" invites the reader to supply a year, and on a card whose
      // siblings resolve in 2028 and 2030 that guess is worth stating for them.
      expect(formatTournamentResolvesLabel("2026-12-31T15:00:00+00:00", NOW_T)).toBe(
        "Resolves Dec 31, 2026",
      );
    });

    test("a resolution date that has passed says NOTHING", () => {
      // The card must not print "Resolves <a date that has gone>" — and must not
      // conclude settlement from it either. `resolution_date` is the SCHEDULED
      // resolution, not an observed one.
      expect(formatTournamentResolvesLabel("2026-08-01T00:00:00+00:00", NOW_T)).toBe("");
    });

    test.each([null, undefined, "", "not-a-date"])(
      "absent or unusable input renders nothing: %p",
      (input) => {
        expect(formatTournamentResolvesLabel(input as string | null | undefined, NOW_T)).toBe("");
      },
    );
  });

  describe("formatTournamentTimingLabel — fallback, never a second line", () => {
    test("a real start date wins; the resolution date stays off the card", () => {
      const label = formatTournamentTimingLabel(DANISH, "2026-08-30T00:00:00+00:00", NOW_T);
      expect(label).toBe("Starts Thu, Aug 13");
      expect(label).not.toContain("Resolves");
    });

    test("no trustworthy start date falls back to when the question is decided", () => {
      expect(formatTournamentTimingLabel(MAJOR_2026, "2026-12-31T15:00:00+00:00", NOW_T)).toBe(
        "Resolves Dec 31, 2026",
      );
    });

    test("the false 'Starts Fri, Jan 14, 2028' becomes a true 'Resolves'", () => {
      expect(formatTournamentTimingLabel(MAJOR_2027, "2028-01-14T15:00:00+00:00", NOW_T)).toBe(
        "Resolves Jan 14, 2028",
      );
    });

    test("neither usable renders nothing rather than a placeholder", () => {
      expect(formatTournamentTimingLabel(MAJOR_2026, null, NOW_T)).toBe("");
      expect(formatTournamentTimingLabel(null, "2020-01-01T00:00:00+00:00", NOW_T)).toBe("");
    });

    /**
     * THE ACCEPTANCE. Card-by-card over the exact eight, so a future change that
     * moves one of them has to say which one and why.
     */
    test("the measured slate: 8 of 8 now carry a timing line, 0 of them false", () => {
      const rendered = SLATE.map((t) => formatTournamentTimingLabel(t.commence, t.resolution, NOW_T));
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
        expect(formatTournamentTimingLabel(t.commence, t.resolution, NOW_T)).toBe(
          formatTournamentWhenLabel(t.commence, NOW_T),
        );
      }
    });
  });
});
