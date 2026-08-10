import fs from "fs";
import path from "path";
import {
  formatFinishedGameLabel,
  isImpossibleFutureFinal,
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
