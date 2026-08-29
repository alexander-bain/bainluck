/**
 * #2279 — the served duel pair is ONE decision on every native surface, asserted
 * by reading the Swift and by re-running its arithmetic.
 *
 * UX-P114 gave every game-card surface `current_odds.{away,home}_rendered_percent`
 * so the two sides of one question are decided ONCE, by the server. Four native
 * surfaces adopted it. All four coalesced PER SIDE:
 *
 *     let awayPct = odds.awayRenderedPercent ?? duelFallback[0]
 *     let homePct = odds.homeRenderedPercent ?? duelFallback[1]
 *
 * A payload carrying one field and not the other therefore prints a served value
 * beside a locally derived one, which re-opens the exact 101 UX-P114 shipped to
 * close. The fields are optional because a Discover response is CACHED and this
 * build can be installed against an older deploy — a response written across a
 * partial rollout is the case the fallback exists for, and it is precisely the
 * case the per-side form gets wrong.
 *
 * 🔴 AND THE HOME-SCREEN WIDGET WAS WORSE THAN THAT, WHICH IS WHY IT IS IN HERE
 * DESPITE NOT BEING ONE OF THE THREE THE ISSUE NAMED. `BainLuckWidget` is a
 * standalone target that cannot import `RenderedPercent.swift`, so what reached it
 * from UX-P114 was the PREFERENCE and not the RULE: its fallback stayed the
 * original `Int((p * 100).rounded())` on each side independently. With the served
 * fields absent — the case its own struct comment says they are optional for — the
 * widget printed 101 on the same 8.2% of events UX-P114 measured. Fixing the
 * coalesce alone would have left that untouched and shipped as a win.
 *
 * This file lives in jest because jest is a deploy gate here and the Swift test
 * target is not reachable from CI (`contracts/rendered_percent.json` `$swift_note`
 * states the same arrangement for the contract's own Swift arm).
 */

import { readFileSync, existsSync, readdirSync, statSync } from "fs";
import { join } from "path";

import { renderedDuelPercents } from "@/lib/renderedPercent";

const REPO_ROOT = join(__dirname, "../../..");
const IOS_ROOT = join(REPO_ROOT, "ios");
const APP_ROOT = join(IOS_ROOT, "Bain Luck/Bain Luck");
const WIDGET_ROOT = join(IOS_ROOT, "Bain Luck/BainLuckWidget");

const CONTRACT = join(REPO_ROOT, "contracts/rendered_percent.json");
const SHARED = join(APP_ROOT, "Utilities/RenderedPercent.swift");
const WIDGET_CLIENT = join(WIDGET_ROOT, "WidgetAPIClient.swift");

/** The surfaces that draw a game duel and read the served pair. */
const SURFACES = [
  join(APP_ROOT, "Components/DiscoverEventCard.swift"),
  join(APP_ROOT, "Components/RelatedByTagView.swift"),
  join(APP_ROOT, "Views/MenuBarView.swift"),
];

const read = (path: string) => readFileSync(path, "utf8");

/**
 * The file with its comments and string bodies removed.
 *
 * 🔴 THIS IS NOT TIDINESS. The first run of this guard failed on THREE files and
 * every one of them was its own explanatory comment: the fix documents the defect
 * by quoting it, so a scanner that reads prose as code reports the cure as the
 * disease. The inverse — a commented-out `duelPercents(` call satisfying a
 * `toContain` — is the same mistake pointed the other way, so the POSITIVE checks
 * read this too.
 *
 * String bodies go with them because a Swift source line may legitimately contain
 * `//` inside a URL literal (`WidgetAPIClient` has one), and a naive line-comment
 * strip would delete the rest of that line and quietly shorten the scan.
 */
function code(path: string): string {
  const src = read(path);
  let out = "";
  let i = 0;
  let inString = false;
  let inLine = false;
  let blockDepth = 0;
  while (i < src.length) {
    const c = src[i];
    const next = src[i + 1];
    if (inLine) {
      if (c === "\n") {
        inLine = false;
        out += c;
      }
      i += 1;
    } else if (blockDepth > 0) {
      if (c === "/" && next === "*") {
        blockDepth += 1;
        i += 2;
      } else if (c === "*" && next === "/") {
        blockDepth -= 1;
        i += 2;
      } else {
        if (c === "\n") out += c;
        i += 1;
      }
    } else if (inString) {
      if (c === "\\") i += 2;
      else {
        if (c === '"') inString = false;
        i += 1;
      }
    } else if (c === "/" && next === "/") {
      inLine = true;
      i += 2;
    } else if (c === "/" && next === "*") {
      blockDepth = 1;
      i += 2;
    } else if (c === '"') {
      inString = true;
      out += c;
      i += 1;
    } else {
      out += c;
      i += 1;
    }
  }
  return out;
}

function swiftFilesUnder(dir: string): string[] {
  const out: string[] = [];
  for (const entry of readdirSync(dir)) {
    const full = join(dir, entry);
    if (statSync(full).isDirectory()) out.push(...swiftFilesUnder(full));
    else if (entry.endsWith(".swift")) out.push(full);
  }
  return out;
}

// ---------------------------------------------------------------------------
// The suite is meaningless pointed at nothing. A path typo would otherwise read
// as a clean pass, so the paths are asserted as a TEST rather than used to skip.
// ---------------------------------------------------------------------------

describe("#2279 — the files this guard reads all exist", () => {
  it.each([CONTRACT, SHARED, WIDGET_CLIENT, ...SURFACES])("%s", (path) => {
    expect(existsSync(path)).toBe(true);
  });

  it("the iOS tree really does contain Swift to scan", () => {
    expect(swiftFilesUnder(IOS_ROOT).length).toBeGreaterThan(100);
  });
});

// ---------------------------------------------------------------------------
// 1. The shape, read as source. This is the ratchet: it catches a REINTRODUCTION
//    anywhere in the tree, including on a surface that does not exist yet.
// ---------------------------------------------------------------------------

describe("#2279 — no native surface coalesces the served pair per side", () => {
  const files = swiftFilesUnder(IOS_ROOT);

  it("scans the whole iOS tree, not a hand-listed subset", () => {
    // The list above is what must be POSITIVELY correct; this scan is what stops
    // a fifth surface repeating the defect. A narrowed scan would show up as a
    // shorter file count rather than as a failure, so the count is asserted.
    expect(files.length).toBeGreaterThan(100);
    expect(files.some((f) => f.includes("BainLuckWidget"))).toBe(true);
    expect(files.some((f) => f.includes("Bain Luck/Bain Luck/Views"))).toBe(true);
  });

  it.each(files.map((f) => [f.slice(IOS_ROOT.length + 1), f]))(
    "%s does not fall back per side",
    (_label, path) => {
      const src = code(path);
      // `x.awayRenderedPercent ?? <anything>` is the defect, whatever the right
      // hand side is: it decides one side of the pair on its own.
      const perSide = src.match(/(away|home)RenderedPercent\s*\?\?/g) ?? [];
      expect(perSide).toHaveLength(0);
    },
  );
});

describe("#2279 — every surface routes the choice through one decision", () => {
  it.each(SURFACES.map((f) => [f.slice(APP_ROOT.length + 1), f]))(
    "%s calls duelPercents with both served values",
    (_label, path) => {
      const src = code(path);
      expect(src).toContain("duelPercents(");
      // 🔴 SIDE-SPECIFIC ON PURPOSE. A bare `/servedAway:/` passes a call that
      // hands the HOME field to the away parameter, which is a silent transpose
      // that still sums to 100. Nothing else in this suite can see a Swift-level
      // transpose — jest cannot execute Swift — so the pinned text IS the check.
      expect(src).toMatch(/servedAway:[^\n]*awayRenderedPercent/);
      expect(src).toMatch(/servedHome:[^\n]*homeRenderedPercent/);
      expect(src).not.toMatch(/servedAway:[^\n]*homeRenderedPercent/);
      expect(src).not.toMatch(/servedHome:[^\n]*awayRenderedPercent/);
      // Same reasoning for the unpack: `duelPercents` returns `[away, home]`.
      expect(src).toMatch(/awayPct = duel\[0\]/);
      expect(src).toMatch(/homePct = duel\[1\]/);
      // It must not keep a second, private opinion about the pair alongside it.
      expect(src).not.toMatch(/Int\(\([^)]*\* 100\)\.rounded\(\)\)/);
    },
  );

  it("the shared decision is both-served-or-neither and lives in one file", () => {
    const src = code(SHARED);
    expect(src).toMatch(/nonisolated func duelPercents\(/);
    expect(src).toMatch(
      /if let servedAway, let servedHome \{\s*\n\s*return \[servedAway, servedHome\]/,
    );
    expect(src).toMatch(
      /return renderedDuelPercents\(away: awayProbability, home: homeProbability\)/,
    );
    // Exactly one definition in the tree.
    const definitions = swiftFilesUnder(IOS_ROOT).filter((f) =>
      /func duelPercents\(/.test(code(f)),
    );
    expect(definitions).toEqual([SHARED]);
  });

  it("the menu bar only trusts the served pair when the pair CAME from current_odds", () => {
    // 🔴 The menu bar's probability falls back to `openingOdds`. The served
    // percents describe `currentOdds` and nothing else, so reading them on that
    // branch prints one source's rounding beside another source's probability —
    // and it still sums to 100, so no sum guard can see it.
    const src = code(join(APP_ROOT, "Views/MenuBarView.swift"));
    expect(src).toMatch(/let fromCurrentOdds = odds\?\.homeProbability != nil/);
    expect(src).toMatch(/servedAway: fromCurrentOdds \? odds\?\.awayRenderedPercent : nil/);
    expect(src).toMatch(/servedHome: fromCurrentOdds \? odds\?\.homeRenderedPercent : nil/);
    // The flag has to be read BEFORE the guard that may substitute openingOdds,
    // or it describes the wrong branch.
    expect(src.indexOf("let fromCurrentOdds")).toBeLessThan(
      src.indexOf("?? event.openingOdds?.homeProbability"),
    );
    // And the pair rule is the last word: no third-tier re-derivation.
    expect(src).toMatch(/guard let awayPct = duel\[0\], let homePct = duel\[1\] else \{ return nil \}/);
  });
});

// ---------------------------------------------------------------------------
// 2. The behaviour. Shape alone would pass a `duelPercents` that ignored its
//    arguments, so the decision is re-run here over cases only the correct rule
//    produces.
// ---------------------------------------------------------------------------

/** Transcription of `duelPercents` in `Utilities/RenderedPercent.swift`. */
function duelPercents(
  away: number | null,
  home: number | null,
  servedAway: number | null,
  servedHome: number | null,
): Array<number | null> {
  if (servedAway != null && servedHome != null) return [servedAway, servedHome];
  return renderedDuelPercents(away, home);
}

describe("#2279 — both served or neither, in values", () => {
  // 0.505 / 0.495 is the row the issue names: the served home is 51 and a naively
  // derived away is 50, and 51 + 50 = 101.
  const AWAY = 0.495;
  const HOME = 0.505;

  it("the local rule already agrees with itself on this pair", () => {
    expect(renderedDuelPercents(AWAY, HOME)).toEqual([49, 51]);
  });

  it("both served — the served pair is used verbatim", () => {
    // 30/70 is deliberately NOT what the local rule produces for this pair, so a
    // reading that ignored the payload would answer 49/51 and be caught. (LAT-P119's
    // M7 survived because its served values happened to equal the local ones.)
    expect(duelPercents(AWAY, HOME, 30, 70)).toEqual([30, 70]);
  });

  it("only home served — the pair falls back WHOLE, not per side", () => {
    expect(duelPercents(AWAY, HOME, null, 70)).toEqual([49, 51]);
    // The defect: [50, 70]-shaped answers, where one side is served and the other
    // is derived. Whatever else it is, the answer may not mix the two.
    expect(duelPercents(AWAY, HOME, null, 70)).not.toEqual([49, 70]);
  });

  it("only away served — same, from the other direction", () => {
    expect(duelPercents(AWAY, HOME, 30, null)).toEqual([49, 51]);
    expect(duelPercents(AWAY, HOME, 30, null)).not.toEqual([30, 51]);
  });

  it("neither served — the contract rule answers", () => {
    expect(duelPercents(AWAY, HOME, null, null)).toEqual([49, 51]);
  });

  it("a partial payload can never sum to anything but 100", () => {
    // Every half-percent home value is a 101 under the old per-side form.
    for (let n = 1; n < 100; n += 1) {
      const home = (n + 0.5) / 100;
      const away = 1 - home;
      const servedHome = renderedDuelPercents(away, home)[1];
      for (const [sa, sh] of [
        [null, servedHome],
        [servedHome === null ? null : 100 - servedHome, null],
        [null, null],
      ] as Array<[number | null, number | null]>) {
        const [a, h] = duelPercents(away, home, sa, sh);
        expect(a).not.toBeNull();
        expect(h).not.toBeNull();
        expect((a as number) + (h as number)).toBe(100);
      }
    }
  });
});

// ---------------------------------------------------------------------------
// 3. The widget's transcription. It cannot import the shared rule, so the rule is
//    re-derived there — and this is what stops the copy drifting.
// ---------------------------------------------------------------------------

/** Transcription of the fallback in `BainLuckWidget/WidgetAPIClient.swift`. */
function widgetDerivedPercents(home: number): [number, number] {
  const away = 1 - home;
  const leaderIsHome = home >= away;
  const leaderPct = Math.round((leaderIsHome ? home : away) * 100);
  return leaderIsHome ? [100 - leaderPct, leaderPct] : [leaderPct, 100 - leaderPct];
}

describe("#2279 — the widget's fallback IS the shared rule", () => {
  it("the Swift the transcription above claims to mirror is still there", () => {
    const src = code(WIDGET_CLIENT);
    expect(src).toMatch(/let leaderIsHome = homeProbability >= awayProbability/);
    expect(src).toMatch(
      /let leaderPct = Int\(\s*\n\s*\(\(leaderIsHome \? homeProbability : awayProbability\) \* 100\)\.rounded\(\)\s*\n\s*\)/,
    );
    expect(src).toMatch(/let derivedHomePct = leaderIsHome \? leaderPct : 100 - leaderPct/);
    expect(src).toMatch(/let derivedAwayPct = leaderIsHome \? 100 - leaderPct : leaderPct/);
    expect(src).toMatch(/let bothServed = servedHomePct != nil && servedAwayPct != nil/);
    expect(src).toMatch(/homeProb: bothServed \? servedHomePct! : derivedHomePct/);
    expect(src).toMatch(/awayProb: bothServed \? servedAwayPct! : derivedAwayPct/);
    // And the trap is gone: `Int(_:)` on a non-finite Double aborts the process.
    expect(src).toMatch(/homeProbability\.isFinite/);
  });

  it("agrees with renderedDuelPercents on every half-percent, where the defect lived", () => {
    for (let n = 0; n < 100; n += 1) {
      const home = (n + 0.5) / 100;
      const [away, homePct] = widgetDerivedPercents(home);
      expect([away, homePct]).toEqual(renderedDuelPercents(1 - home, home));
      expect(away + homePct).toBe(100);
    }
  });

  it("agrees on every duel row of the contract, re-derived the widget's way", () => {
    const contract = JSON.parse(read(CONTRACT));
    const rows = contract.duel_cases as Array<{
      away: number | null;
      home: number | null;
      percents: Array<number | null>;
      naive: Array<number | null>;
    }>;
    expect(rows.length).toBeGreaterThanOrEqual(10);

    let discriminating = 0;
    for (const row of rows) {
      if (row.home == null) continue;
      // The widget always builds its away side as `1 - home`, so the row is
      // re-derived that way rather than taken as served.
      const home = row.home;
      const derived = widgetDerivedPercents(home);
      expect(derived).toEqual(renderedDuelPercents(1 - home, home));
      const naive = [Math.round((1 - home) * 100), Math.round(home * 100)];
      if (naive[0] + naive[1] !== 100) {
        // A row the OLD widget got wrong. The new one must not.
        discriminating += 1;
        expect(derived).not.toEqual(naive);
        expect(derived[0] + derived[1]).toBe(100);
      }
    }
    // If no contract row discriminates, this test proves nothing — say so loudly
    // rather than pass. (The 0.505/0.495 family is what puts rows in this class.)
    expect(discriminating).toBeGreaterThan(0);
  });
});
