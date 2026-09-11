/**
 * #1832 — one period-label implementation on iOS, asserted by reading the Swift.
 *
 * `normalizePeriodLabel` existed in TWO Swift files and had already drifted:
 * `ScoreDifferentialChartView`'s copy was missing the plain-ordinal inning
 * branch and all three golf branches, so the two charts stacked on the SAME
 * event page could label one period differently — or one could label it and the
 * other fall through to ESPN's raw string.
 *
 * That is gotcha #128's shape: a rule in N consumers has N verdicts, and the
 * healthy copy is what hides the broken one. This is the ratchet that stops it
 * coming back. It lives in jest because jest is a deploy gate here and the Swift
 * test target is not reachable from CI.
 */

import { readFileSync, existsSync, readdirSync } from "fs";
import { join } from "path";

const IOS_ROOT = join(__dirname, "../../../ios/Bain Luck/Bain Luck");
const CANONICAL = join(IOS_ROOT, "Utilities/PeriodLabel.swift");

/**
 * #4880 — the two targets this ratchet could never see.
 *
 * `IOS_ROOT` is ONE target deep. The watch app and the widget are SIBLINGS of
 * that directory, not children, so three of the six call sites that printed
 * `23' 23'` were structurally outside every scan in this file and always had
 * been. Measured 2026-09-10: 189 .swift in the app, 14 in the watch, 5 in the
 * widget.
 */
const WATCH_ROOT = join(__dirname, "../../../ios/Bain Luck/BainLuckWatch Watch App");
const WIDGET_ROOT = join(__dirname, "../../../ios/Bain Luck/BainLuckWidget");
const ALL_TARGET_ROOTS = [IOS_ROOT, WATCH_ROOT, WIDGET_ROOT];
const CONSUMERS = [
  join(IOS_ROOT, "Components/OddsChartView.swift"),
  join(IOS_ROOT, "Components/ScoreDifferentialChartView.swift"),
];

/**
 * #3273 — the list above is why this ratchet failed.
 *
 * It named its consumers, so it only ever watched the two files that were
 * already broken in #1832. Two MORE copies grew where it was not looking:
 * `Views/EventDetailView.swift` (Game Segments) read ESPN's clock PREFIX as the
 * period number and headed a four-quarter football game
 * `Q14 · Q8 · Q5 · Q1 … Q4`; `Components/GamePlayCardView.swift` returned the
 * raw string and printed the clock twice. An allowlist cannot catch the file
 * nobody thought to add — so the check below DISCOVERS instead.
 *
 * Comments are stripped before scanning: the fixed files legitimately discuss
 * quarters and overtime at length in their doc comments, and a substring match
 * over raw source would call that a reimplementation.
 */
function swiftFiles(dir: string): string[] {
  return readdirSync(dir, { withFileTypes: true }).flatMap((entry) => {
    const path = join(dir, entry.name);
    if (entry.isDirectory()) return swiftFiles(path);
    return entry.isFile() && entry.name.endsWith(".swift") ? [path] : [];
  });
}

function stripComments(source: string): string {
  return source
    .replace(/\/\*[\s\S]*?\*\//g, "")
    .replace(/^[ \t]*\/\/.*$/gm, "")
    .replace(/(?<!:)\/\/.*$/gm, "");
}

/**
 * Tells that a file is BUILDING a period label rather than asking for one:
 * interpolating a period prefix, or matching a period noun in code.
 */
const REIMPLEMENTATION_TELLS: Array<[string, RegExp]> = [
  ["interpolates a quarter label", /"Q\\\(/],
  ["interpolates a period label", /"P\\\(/],
  ["interpolates an overtime label", /"OT\\\(/],
  ["interpolates a half label", /\)H"/],
  ["matches the word 'quarter'", /quarter/i],
  ["matches the word 'halftime'", /halftime/i],
  ["matches the word 'overtime'", /overtime/i],
  ["matches baseball half-innings", /top\|bottom/],
];

/**
 * Files allowed to mention this vocabulary in code for a reason that is not
 * period labelling. Each needs a stated reason, so adding one is a decision.
 */
const NOT_PERIOD_PARSERS = new Map([
  [
    join(IOS_ROOT, "Components/SpecialEventMarketsView.swift"),
    "classifies MARKET NAMES ('halftime result', 'overtime') into prop groups — never labels a period",
  ],
  [
    join(IOS_ROOT, "Utilities/MarketMapRail.swift"),
    // #3925 item 2. Same reason as the entry above, and it is the reason the
    // allowlist takes a sentence rather than a path: this file reads a MARKET
    // NAME ('1st Half Total Goals O/U 1.5', '1st Quarter Total Points') to
    // decide whether that rung is scoped to the whole contest and may share an
    // axis with the others. It never renders a period, never interpolates one,
    // and has no `raw` string to normalize — the output is a list of INDICES.
    // Delegating to `PeriodLabel` would be the actual mistake: it answers
    // "what do I call ESPN's clock string", which is a different question.
    "reads MARKET NAMES for contest SCOPE ('1st Half …', '1st Quarter …') to pick which totals rungs share one ladder — returns indices, never labels a period",
  ],
]);

// The whole suite is meaningless if it is pointed at nothing — a path typo
// would otherwise read as a clean pass (the unrunnable-check failure mode).
const iosPresent = existsSync(CANONICAL);

const d = iosPresent ? describe : describe.skip;

d("iOS period labels have exactly one implementation", () => {
  const canonical = readFileSync(CANONICAL, "utf8");

  it("the canonical implementation exists and is the only definition", () => {
    expect(canonical).toContain("enum PeriodLabel");
    expect(canonical).toMatch(/static func normalize\(/);
  });

  it.each(CONSUMERS)("%s delegates rather than reimplementing", (path) => {
    const src = readFileSync(path, "utf8");
    // #4888 widened this from the literal `PeriodLabel.normalize(raw)`: both
    // chart consumers now pass the event's sport key, which the shared parser
    // consults for a BARE period number and nothing else. What this line is
    // for is that the consumer hands its RAW string to the shared parser
    // instead of reading it itself, and `normalize(raw` still says exactly
    // that — the argument list after it is not the ratchet. The ratchet is the
    // regex count below, which is what actually separates "calls the shared
    // rule" from "quietly grew its own again".
    expect(src).toMatch(/PeriodLabel\.normalize\(raw[,)]/);

    // A real reimplementation is a body full of period regexes. The delegating
    // shim has none, so counting them separates "calls the shared rule" from
    // "quietly grew its own again".
    const quarterBranches = src.match(/\[Qq\]uarter|quarter\$/g) ?? [];
    const inningBranches = src.match(/top\|bottom\|mid/g) ?? [];
    expect(quarterBranches).toHaveLength(0);
    expect(inningBranches).toHaveLength(0);
  });

  it("baseball innings render as self-explaining ordinals, not bare digits", () => {
    // Ruling 5. A chart chip strip reading "0 8" names no unit; "8th" does.
    expect(canonical).toMatch(/return inning\(/);
    expect(canonical).toMatch(/func inning<S: StringProtocol>/);
    expect(canonical).toMatch(/func ordinalSuffix/);
  });

  it("a non-positive period number yields no chip at all", () => {
    // This is where the unexplained "0" chip came from: the short-form regex
    // had a bare `\d+` arm that passed "0" straight through.
    expect(canonical).toMatch(/guard let n = Int\(digits\), n > 0 else \{ return "" \}/);
    // The bare-integer arm must no longer sit inside the pass-through regex.
    expect(canonical).not.toMatch(/\^\(Q\\d\|P\\d\|\\d\+H\|OT\\d\?\|HT\|\\d\+\)\$/);
  });

  it("no OTHER Swift file reimplements period labelling — discovered, not listed", () => {
    const offenders: string[] = [];

    for (const path of swiftFiles(IOS_ROOT)) {
      if (path === CANONICAL) continue;
      if (NOT_PERIOD_PARSERS.has(path)) continue;

      const code = stripComments(readFileSync(path, "utf8"));
      const hits = REIMPLEMENTATION_TELLS.filter(([, re]) => re.test(code)).map(([why]) => why);
      if (hits.length > 0) {
        offenders.push(`${path.slice(IOS_ROOT.length + 1)} — ${hits.join("; ")}`);
      }
    }

    expect(offenders).toEqual([]);
  });

  it("the discovery check can actually fail", () => {
    // A scan that cannot fail is the failure mode this whole file exists to
    // stop. Feed it the exact defect from #3273 and require it to fire.
    const drifted = stripComments(`
      private static func formatPeriodLabel(_ raw: String) -> String {
        if raw.lowercased().contains("quarter"), let n = firstNumber(in: raw) { return "Q\\(n)" }
        return raw
      }
    `);
    const hits = REIMPLEMENTATION_TELLS.filter(([, re]) => re.test(drifted));
    expect(hits.length).toBeGreaterThan(0);
  });

  it("the two files fixed by #3273 delegate to the shared parser", () => {
    // Named explicitly so a revert is loud rather than merely un-discovered.
    for (const [file, call] of [
      ["Views/EventDetailView.swift", "PeriodLabel.columnLabel("],
      ["Components/GamePlayCardView.swift", "PeriodLabel.normalize("],
    ]) {
      expect(readFileSync(join(IOS_ROOT, file), "utf8")).toContain(call);
    }
  });

  it("the scoreboard column vocabulary is defined once, beside normalize", () => {
    // #3273: the column label differs from the chart chip in exactly two ways
    // (innings as digits, non-periods dropped). It lives on PeriodLabel so it
    // cannot drift back into a view.
    expect(canonical).toMatch(/static func columnLabel\(/);
    expect(canonical).toMatch(/normalize\(raw\)/);
  });

  it("ordinal suffixes follow English, including the 11-13 exception", () => {
    // Transcribed from the Swift so a future edit to one must touch the other.
    const suffix = (n: number) => {
      const mod100 = n % 100;
      if (mod100 >= 11 && mod100 <= 13) return "th";
      switch (n % 10) {
        case 1:
          return "st";
        case 2:
          return "nd";
        case 3:
          return "rd";
        default:
          return "th";
      }
    };
    expect([1, 2, 3, 4, 9, 11, 12, 13, 21, 22].map((n) => `${n}${suffix(n)}`)).toEqual([
      "1st",
      "2nd",
      "3rd",
      "4th",
      "9th",
      "11th",
      "12th",
      "13th",
      "21st",
      "22nd",
    ]);
  });
});

/**
 * #4880 — a period printed BESIDE its clock, across all three targets.
 *
 * The block above asserts there is one implementation of "what do I call this
 * period string". That already held when the hero capsule read **`23' 23'`** on
 * every live soccer match, because the defect is not a second implementation —
 * it is six callers JOINING the shared label to the clock themselves, and
 * soccer serves `period` EQUAL to `game_clock` (`"25'"` / `"25'"`).
 *
 * So the tell here is the join, not the label. Two things are asserted that the
 * block above cannot: that the join happens in exactly one place, and that the
 * scan reaches the watch and the widget, where three of the six sites live.
 */
const CANONICAL_JOIN = "PeriodLabel.liveStatusText(";

/** The seven sites that printed the pair, by target. Named so a revert is loud. */
const PAIR_PRINTERS: Array<[string, string]> = [
  // #5057. The seventh, and the one the discovery scan below could not find:
  // it was a `??` FALLBACK (`espn?.period ?? espn?.gameClock`), not an array
  // literal, so `RAW_JOIN` never matched it and #4880 shipped with the macOS
  // menu bar still printing `6:34 - 4th Quarter` above a row saying `Q4 6:34`.
  // Listed here AND given its own tell (`RAW_FALLBACK`) — the name pins this
  // file, the tell makes the shape unreachable in the next one.
  [join(IOS_ROOT, "Bain_LuckApp.swift"), "the macOS menu bar TITLE"],
  [join(IOS_ROOT, "Components/StatusBadge.swift"), "the hero capsule and every feed card"],
  [join(IOS_ROOT, "Views/EventDetailView.swift"), "the nav title and share text"],
  [join(IOS_ROOT, "Views/MenuBarView.swift"), "the macOS menu bar"],
  [join(WATCH_ROOT, "WatchFeedModels.swift"), "the watch feed row's clockText"],
  [join(WATCH_ROOT, "WatchLiveView.swift"), "the watch live game row"],
  [join(WIDGET_ROOT, "WidgetAPIClient.swift"), "the widget"],
];

/**
 * An array literal holding BOTH halves of the pair — `[event.espn?.period,
 * event.espn?.gameClock]` — which is the exact shape all six sites had. The
 * `[^\]]*` bound keeps it to one literal so an unrelated `period` earlier in the
 * file cannot pair with a `gameClock` later.
 */
const RAW_JOIN = /\[[^\]]*\bperiod\b[^\]]*\bgameClock\b[^\]]*\]/;

/**
 * #5057 — the OTHER way to reach the pair, which `RAW_JOIN` is blind to.
 *
 * `let period = best.espn?.period ?? best.espn?.gameClock ?? ""` never doubles
 * anything, so it survived #4880 untouched and kept printing ESPN's raw period
 * on the macOS menu bar title. Coalescing the two is still a surface deciding
 * for itself what to say about the clock, which is the half of the rule that
 * produced the defect — the ONE difference from `RAW_JOIN` is the failure mode,
 * not the ownership.
 *
 * Ordered: `period` … `??` … `gameClock`. The five delegating call sites read
 * `period: …, gameClock: …) ?? ""` — their `??` comes AFTER both names — so
 * this does not fire on them. Verified across all four targets: one hit, which
 * was the defect.
 */
const RAW_FALLBACK = /\bperiod\b[^\n]*\?\?[^\n]*\bgameClock\b/;

const iosTargetsPresent = ALL_TARGET_ROOTS.every((root) => existsSync(root));
const t = iosTargetsPresent ? describe : describe.skip;

t("a live period is printed beside its clock in exactly one place (#4880)", () => {
  it("the shared rule takes BOTH strings, because only it can see the collision", () => {
    const canonical = readFileSync(CANONICAL, "utf8");
    expect(canonical).toMatch(/static func liveStatusText\(period: String\?, gameClock: String\?\)/);
    // Equality, not containment. `liveBadgeLabel` strips a clock PREFIX, which
    // is what football sends; soccer's period IS the clock, with no separator
    // to find, and that is the case the old guard could not express.
    expect(canonical).toMatch(/caseInsensitiveCompare\(clock\)/);
  });

  it.each(PAIR_PRINTERS)("%s delegates the join (%s)", (path) => {
    const src = readFileSync(path, "utf8");
    expect(src).toContain(CANONICAL_JOIN);
  });

  it("no Swift file in ANY target joins the pair itself — discovered, not listed", () => {
    const offenders: string[] = [];

    for (const root of ALL_TARGET_ROOTS) {
      for (const path of swiftFiles(root)) {
        if (path === CANONICAL) continue;
        const code = stripComments(readFileSync(path, "utf8"));
        if (RAW_JOIN.test(code)) {
          offenders.push(`${path} — joins period to gameClock instead of calling liveStatusText`);
        }
        // #5057. Coalescing the pair is the same decision as joining it.
        if (RAW_FALLBACK.test(code)) {
          offenders.push(
            `${path} — falls back from period to gameClock itself; use liveStatusText`
          );
        }
        // `liveBadgeLabel` is handed ONE string and cannot see what is printed
        // next to it. Outside the canonical file, asking for it is asking for
        // the half of the rule that produced this defect.
        if (/liveBadgeLabel/.test(code)) {
          offenders.push(`${path} — calls liveBadgeLabel directly; use liveStatusText`);
        }
      }
    }

    expect(offenders).toEqual([]);
  });

  it("the watch and the widget are actually reached", () => {
    // The blind spot itself, asserted. If a refactor moves these directories
    // the scan above must fail loudly rather than silently scan nothing —
    // "an empty scan reads as a clean pass" is this file's own thesis.
    for (const root of [WATCH_ROOT, WIDGET_ROOT]) {
      expect(swiftFiles(root).length).toBeGreaterThan(0);
    }
    expect(swiftFiles(WATCH_ROOT).some((p) => p.endsWith("WatchLiveView.swift"))).toBe(true);
    expect(swiftFiles(WIDGET_ROOT).some((p) => p.endsWith("WidgetAPIClient.swift"))).toBe(true);
  });

  it("the join check can actually fail", () => {
    // Feed it the exact code that shipped `23' 23'`.
    const drifted = stripComments(`
      let parts = [event.espn?.period, event.espn?.gameClock].compactMap { $0 }
      return parts.joined(separator: " ")
    `);
    expect(RAW_JOIN.test(drifted)).toBe(true);
  });

  it("the fallback check can actually fail — and does not fire on delegation", () => {
    // #5057. Both directions, because a tell that cannot fail is worthless and
    // a tell that fires on the FIX is worse: it would push the next author
    // back to hand-rolling the pair to get a green suite.
    const drifted = stripComments(`
      let period = best.espn?.period ?? best.espn?.gameClock ?? ""
    `);
    expect(RAW_FALLBACK.test(drifted)).toBe(true);

    const delegating = stripComments(`
      period: PeriodLabel.liveStatusText(
          period: event.espn?.period, gameClock: event.espn?.gameClock) ?? "",
    `);
    expect(RAW_FALLBACK.test(delegating)).toBe(false);
  });
});
