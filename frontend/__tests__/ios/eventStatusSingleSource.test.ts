/**
 * #4002 / #3014 — one event-status vocabulary on iOS, asserted by reading the Swift.
 *
 * `EventState` was created by live/048 to be the single source for "is this
 * event over?", because `suspended` had landed in a vocabulary every screen was
 * reading with its own inline `== "completed" || == "closed"` chain. The enum
 * shipped; the migration did not. At `origin/master` 0d5a6d11, **eleven files**
 * outside `EventState.swift` still carried a private copy, and `EventCardView`
 * was the only consumer that had been repaired — it took live/048 + CERT-786
 * and the others never did.
 *
 * So the fix applied to the original was invisible to every copy, and
 * `EventDetailView` broke four renders at once on one hero. Photographed on
 * production 2026-09-08, `bainluck://events/15298408` (Yankees @ Padres, played
 * Sep 6, final 3–4, `status='suspended'`): no status badge, no score — under a
 * navigation title reading "Yankees 3 - Padres 4" — a grey `Proj. 3-2` where
 * the score belongs, three broadcast channels, and a 1:10 PM kick-off time, two
 * days after the game ended.
 *
 * WHY THIS FILE EXISTS AND THE SWIFT TESTS DO NOT SUFFICE.
 * `EventDetailSuspendedHeroTests` proves the four gate helpers. It cannot prove
 * the view BODY calls them, and the body is where #4002 actually lived — the
 * pre-fix gates were inline expressions inside `heroSection`, invisible to
 * XCTest. A mutation run confirmed it: reverting `showsProjection(status:)` in
 * the body back to `!isFinished` leaves every Swift test green. The assertions
 * below are what kill that mutant, and they run in CI, which compiles no Swift.
 *
 * SCOPE. `IOS_ROOT` is the phone/iPad/Mac app. The watch app
 * (`ios/Bain Luck/BainLuckWatch Watch App/`) is deliberately outside it:
 * `EventState.swift` is not a member of the watch target — the target's
 * `membershipExceptions` in `project.pbxproj` pull in four `Models/*` files from
 * the shared folder and nothing else — so `WatchFeedModels.isSettled` CANNOT
 * call it. That is a real second copy and it is filed rather than hidden; see
 * the note on `WATCH_IS_OUT_OF_REACH` below.
 */

import { readFileSync, existsSync, readdirSync } from "fs";
import { join } from "path";

const IOS_ROOT = join(__dirname, "../../../ios/Bain Luck/Bain Luck");
const CANONICAL = join(IOS_ROOT, "Utilities/EventState.swift");

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
 * Tells that a file is RE-DECLARING the settled vocabulary rather than asking
 * `EventState` for it.
 *
 * Keyed on `"completed"` and never on `"closed"` alone, and that is the whole
 * precision of this scan. The two words are not interchangeable: `"closed"` is
 * ALSO a futures-market status with its own meaning, and `DiscoverView` line
 * 635 legitimately writes `f.status != "closed", f.status != "resolved"` about a
 * `FuturesMarket`. An event's settled reading always names `"completed"`, a
 * futures market's never does, so the pair-defining word is the safe tell.
 */
const REDECLARATION_TELLS: Array<[string, RegExp]> = [
  ["compares an event status against the literal \"completed\"", /==\s*"completed"/],
  ["compares an event status against the literal \"completed\"", /!=\s*"completed"/],
  ["switches on the literal \"completed\" instead of EventState.isFinished", /case\s+"completed"/],
];

/**
 * A value is not a comparison. These shapes carry the string as DATA and are
 * not a second opinion about what the status means, so the tells above are
 * written not to match them — checked, not assumed, by
 * `testTheScanDoesNotFireOnALegitimateValueUse` below:
 *
 *   SettledQuote.swift       `["completed", "closed", "settled", "final", "resolved"]`
 *                            — a MARKET settlement vocabulary, five values wide,
 *                              deliberately not the event one.
 *   FeedModels.swift         `settledStatuses.union(["completed"])` — golf
 *                            `schedule_status`, a third vocabulary again.
 *   DiscoverTournamentCard   `scheduleStatus: "completed"` in a #Preview.
 *
 * There is no allowlist in this file and that is intentional: a denylist of
 * known-good exceptions hands the claim to the first case nobody listed.
 */
const LEGITIMATE_VALUE_USES = [
  `    static let settledStatuses: Set<String> = ["completed", "closed", "settled", "final", "resolved"]`,
  `        settledStatuses.union(["completed"])`,
  `                    marqueeWhathit: true, scheduleStatus: "completed") {`,
  `                   f.status != "closed", f.status != "resolved",`,
];

/**
 * The watch app keeps `var isSettled: Bool { status == "completed" || status ==
 * "closed" }` (`WatchFeedModels.swift:118`) and this scan cannot ask it to
 * stop, because the file it would delegate to is not in its target. Recorded as
 * a constant rather than an allowlist entry so it is a stated fact about target
 * membership and not a suppression: the day `EventState.swift` joins the watch
 * target, widen `IOS_ROOT`.
 */
const WATCH_IS_OUT_OF_REACH =
  "ios/Bain Luck/BainLuckWatch Watch App/WatchFeedModels.swift — EventState.swift is not a member of the watch target";

// A path typo would otherwise read as a clean pass — the unrunnable-check
// failure mode this whole file exists to stop.
const iosPresent = existsSync(CANONICAL);
const d = iosPresent ? describe : describe.skip;

d("iOS reads one event-status vocabulary", () => {
  const canonical = () => readFileSync(CANONICAL, "utf8");
  const detail = () => readFileSync(join(IOS_ROOT, "Views/EventDetailView.swift"), "utf8");
  const badge = () => readFileSync(join(IOS_ROOT, "Components/StatusBadge.swift"), "utf8");

  it("the canonical vocabulary exists", () => {
    expect(canonical()).toMatch(/static func isFinished\(_ status: String\?\) -> Bool/);
    expect(canonical()).toMatch(/static func isSuspended\(_ status: String\?\) -> Bool/);
    expect(canonical()).toMatch(/static let suspendedLabel = "No result reported"/);
  });

  it("no OTHER Swift file in the app decides the settled vocabulary — discovered, not listed", () => {
    const offenders: string[] = [];

    for (const path of swiftFiles(IOS_ROOT)) {
      if (path === CANONICAL) continue;
      const code = stripComments(readFileSync(path, "utf8"));

      for (const [index, line] of code.split("\n").entries()) {
        const hits = REDECLARATION_TELLS.filter(([, re]) => re.test(line)).map(([why]) => why);
        if (hits.length > 0) {
          offenders.push(
            `${path.slice(IOS_ROOT.length + 1)}:${index + 1} — ${hits[0]} — ${line.trim()}`
          );
        }
      }
    }

    expect(offenders).toEqual([]);
  });

  describe("the four renders #4002 broke, wired in the BODY where XCTest cannot see them", () => {
    it("the score gate asks the helper instead of restating (isLive || isFinished)", () => {
      // THE mutant. `(isLive || isFinished) && …` compiles, reads right, keeps
      // every Swift test green, and is exactly what drew no score on a 3–4 game.
      expect(detail()).toMatch(
        /let hasScore = EventDetailView\.showsScore\(\n\s*status: event\.status, away: event\.awayScore, home: event\.homeScore\)/
      );
      expect(stripComments(detail())).not.toMatch(/hasScore = \(isLive \|\| isFinished\)/);
    });

    it("the projection gate asks the helper instead of restating !isFinished", () => {
      expect(detail()).toMatch(
        /EventDetailView\.showsProjection\(\n\s*status: event\.status, commenceTime: event\.commenceTime\?\.asDate\)/
      );
      // The pre-fix gate, verbatim. Its absence is the assertion.
      expect(stripComments(detail())).not.toMatch(
        /projectedAwayScore,\s*\n\s*!isFinished \{/
      );
    });

    it("both broadcast chips are gated, the hero's and Game Info's", () => {
      // Two separate renders of the same channel list, one scroll apart. Fixing
      // only the hero leaves the promise on the page.
      expect(detail()).toMatch(
        /if let broadcast = event\.espn\?\.broadcast,\n\s*EventDetailView\.showsBroadcast\(\n\s*status: event\.status, commenceTime: event\.commenceTime\?\.asDate\) \{/
      );
      expect(detail()).toMatch(/let showsBroadcast = event\.espn\?\.broadcast != nil\n\s*&& EventDetailView\.showsBroadcast\(\n\s*status: event\.status, commenceTime: event\.commenceTime\?\.asDate\)/);
      expect(detail()).toMatch(/if let broadcast = event\.espn\?\.broadcast, showsBroadcast \{/);
    });

    it("the hero badge has a suspended arm, and it is reached before the pregame default", () => {
      // Order is the whole rule. The default hands StatusBadge the literal
      // "scheduled" plus a commenceTime in the past; formatCountdown returns nil
      // for a past date, so the badge fell through to EmptyView and the match
      // wore no label at all. A suspended arm placed AFTER the default is dead.
      const body = detail();
      const suspendedArm = body.indexOf("} else if EventState.isSuspendedAndStarted(");
      const pregameDefault = body.indexOf(`StatusBadge(status: "scheduled", commenceTime: event.commenceTime)`);
      expect(suspendedArm).toBeGreaterThan(-1);
      expect(pregameDefault).toBeGreaterThan(suspendedArm);
    });

    it("the Game Info time chip stops calling a played match a kick-off", () => {
      // "Sep 4 at 2:00 AM" is the identical sentence this chip prints for a
      // fixture next week.
      expect(detail()).toMatch(/\} else if isSuspended \{/);
      expect(detail()).toMatch(/Text\("Started \\\(date, format: \.dateTime\.month\(\.abbreviated\)\.day\(\)\) at/);
    });

    it("the page's own predicates delegate", () => {
      expect(detail()).toMatch(/private var isFinished: Bool \{ EventState\.isFinished\(vm\.event\?\.status\) \}/);
      expect(detail()).toMatch(
        /private var isSuspended: Bool \{\n\s*EventState\.isSuspendedAndStarted\(\n\s*vm\.event\?\.status, commenceTime: vm\.event\?\.commenceTime\?\.asDate\)\n\s*\}/
      );
    });
  });

  it("the badge renders the shared label rather than inventing the word Suspended", () => {
    // `EventState.suspendedLabel` is "No result reported" and the reason is
    // written where it is defined: the same status covers a rain delay and a
    // source going dark, and only one of those is a stoppage anybody reported.
    expect(badge()).toMatch(/EventState\.isSuspendedAndStarted\(status, commenceTime: commenceTime\?\.asDate\)/);
    expect(badge()).toMatch(/Text\(EventState\.suspendedLabel\)/);
    expect(stripComments(badge())).not.toMatch(/Text\("Suspended"\)/);
  });

  describe("#4021 — the suspended TREATMENT asks the clock, not just the status", () => {
    // `suspended` is a status, not a phase. Event 416569 (Ohio State @ Texas)
    // carried it four days BEFORE kick-off — exactly one such row, measured by
    // lane1b/084 and again independently. The first draft of this ship routed
    // every suspended row to the settled treatment and was, on that one row, a
    // REGRESSION against master: master's pregame default produced a correct
    // "In 4d" countdown, because `formatCountdown` only returns nil for a PAST
    // date. These assertions are what stop that draft coming back.

    it("no surface renders the suspended TREATMENT from the bare status", () => {
      // Discovered, not listed. `isSuspended` alone is legitimate for BUCKETING
      // (which grid section, what the section header is called) — a future-dated
      // row in the live bucket is harmless. It is not legitimate for a per-card
      // claim that no result arrived.
      const TREATMENT_TELLS: Array<[string, RegExp]> = [
        ["prints the suspended label", /EventState\.suspendedLabel/],
        ["prints the suspended summary", /EventState\.suspendedSummary/],
      ];
      const offenders: string[] = [];

      for (const path of swiftFiles(IOS_ROOT)) {
        if (path === CANONICAL) continue;
        const code = stripComments(readFileSync(path, "utf8"));
        const drawsTreatment = TREATMENT_TELLS.some(([, re]) => re.test(code));
        if (!drawsTreatment) continue;
        // A file that draws the treatment must decide it with the clock.
        if (!/isSuspendedAndStarted\(/.test(code)) {
          offenders.push(
            `${path.slice(IOS_ROOT.length + 1)} — draws the suspended treatment but never calls isSuspendedAndStarted`
          );
        }
      }

      expect(offenders).toEqual([]);
    });

    it("the bare status test survives, and only where the question is about a LIST", () => {
      // `EventState.isSuspended` alone is correct for a collection-level question
      // — "does this section contain a paused match?", which decides a section
      // TITLE and cannot mislabel an individual card. It is wrong for a per-item
      // claim. The structural difference is `.contains {`, so that is what this
      // tests, rather than listing the three view models by name.
      const offenders: string[] = [];

      for (const path of swiftFiles(IOS_ROOT)) {
        if (path === CANONICAL) continue;
        const lines = stripComments(readFileSync(path, "utf8")).split("\n");
        for (const [i, line] of lines.entries()) {
          if (!/EventState\.isSuspended\(/.test(line)) continue;
          if (/isSuspendedAndStarted\(/.test(line)) continue;
          // The predicate may sit on the line under the `.contains {`.
          const context = [lines[i - 1] ?? "", line].join(" ");
          if (/\.contains \{/.test(context)) continue;
          // FILE AND CODE, NOT LINE NUMBER — see the note on the pin below.
          offenders.push(`${path.slice(IOS_ROOT.length + 1)} — ${line.trim()}`);
        }
      }

      // An exact-set PIN, not an allowlist: a new offender fails this, and so
      // does removing one of these without editing the list. ONE line survives,
      // for a stated reason.
      //
      // THE PIN IS FILE + CODE AND DELIBERATELY CARRIES NO LINE NUMBER (changed
      // by #3978, which broke this test without changing any of the code it is
      // about). The original pinned `EventDetailView.swift:490`, so adding nine
      // lines of comment anywhere above `showsScore` failed a guard whose whole
      // subject was elsewhere. A number that moves when untouched code moves is
      // not part of the claim — the claim is "exactly these two readings
      // survive, in these two files" — and a guard that cries wolf on unrelated
      // edits is a guard someone eventually edits carelessly to make it green.
      // Nothing is lost: the offending line's own text is in the message, so
      // locating a genuine new offender is one grep.
      //
      // 1. `ShareCardRenderer` WAS the second entry and is GONE — #4044, closed
      //    2026-09-10. It now reads `isSuspendedAndStarted` off a `commenceTime`
      //    threaded through `renderEventCard` (one construction site, not the
      //    "every construction site" the carve-out feared), and it prints
      //    `EventState.suspendedLabel.uppercased()` instead of its own "PAUSED".
      //    The carve-out worked exactly as designed: the pin made the debt
      //    un-forgettable, and paying it required editing this list.
      //
      // 2. `showsScore` is NOT the suspended treatment — it is the opposite. The
      //    treatment claims no result arrived; this draws a score we actually
      //    hold, and drawing a real score is never the wrong answer. It needs no
      //    clock because the scores ARE the evidence the game started: a fixture
      //    four days out has none, so the future-dated row cannot reach it.
      expect(offenders).toEqual([
        'Views/EventDetailView.swift — return status == "live" || EventState.isFinished(status) || EventState.isSuspended(status)',
      ]);
    });

    it("every renderEventCard call site hands it a commenceTime", () => {
      // #4044. `commenceTime` has no default on `renderEventCard`, so Swift
      // already refuses a caller that omits it — but CI compiles no Swift
      // (#4302), so that refusal is not a gate here. A caller passing a literal
      // `nil` compiles fine and silently restores the clockless behaviour on the
      // one surface whose output leaves the app, which is what this catches.
      const offenders: string[] = [];

      for (const path of swiftFiles(IOS_ROOT)) {
        const code = stripComments(readFileSync(path, "utf8"));
        const idx = code.indexOf("ShareCardRenderer.renderEventCard(");
        if (idx === -1) continue;
        const call = code.slice(idx, idx + 900);
        // Written as two POSITIVE tests, not as `commenceTime:\s*[^n]`. That
        // form looks like "an argument that is not nil" and matches
        // `commenceTime: nil` anyway: `\s*` backtracks to zero characters and
        // `[^n]` then happily eats the SPACE. The mutant that passes a literal
        // nil survived it, which is the only reason this comment exists.
        if (!/commenceTime:/.test(call)) {
          offenders.push(`${path.slice(IOS_ROOT.length + 1)} — renderEventCard with no commenceTime at all`);
        } else if (/commenceTime:\s*nil\b/.test(call)) {
          offenders.push(`${path.slice(IOS_ROOT.length + 1)} — renderEventCard hands commenceTime a literal nil`);
        }
      }

      expect(offenders).toEqual([]);
      // The scan must be finding the one caller — an empty filter passes forever.
      const callers = swiftFiles(IOS_ROOT).filter((p) =>
        stripComments(readFileSync(p, "utf8")).includes("ShareCardRenderer.renderEventCard(")
      );
      expect(callers.map((p) => p.slice(IOS_ROOT.length + 1))).toEqual([
        "Components/DiscoverEventCard.swift",
      ]);
    });

    it("every StatusBadge call site hands it a commenceTime", () => {
      // THE leak that made this more than a one-view fix. Three of the five call
      // sites passed a bare `event.status`, so the new suspended arm would have
      // put "No result reported" on a search row and a team schedule row for a
      // game four days out. A call site without a `commenceTime:` is that bug.
      const CALLERS = [
        "Views/SearchView.swift",
        "Views/TeamDetailView.swift",
        "Components/EventCardView.swift",
        "Views/EventDetailView.swift",
      ];
      const offenders: string[] = [];

      for (const rel of CALLERS) {
        const code = stripComments(readFileSync(join(IOS_ROOT, rel), "utf8"));
        // Match a StatusBadge(...) invocation and check the argument list.
        // `(?<![A-Za-z])` or this also matches `heroStatusBadge(` and the
        // `private func heroStatusBadge(_ event:)` declaration — both of which
        // it then reports as call sites missing an argument they cannot take.
        for (const m of code.matchAll(/(?<![A-Za-z])StatusBadge\(([^)]*)\)/g)) {
          const args = m[1];
          // A LITERAL status is pinned to one arm and a reader can check it at a
          // glance; only an expression the compiler cannot narrow needs the date.
          if (/status: "/.test(args)) continue;
          if (!args.includes("commenceTime:")) {
            offenders.push(`${rel} — StatusBadge(${args.trim().replace(/\s+/g, " ")})`);
          }
        }
      }

      expect(offenders).toEqual([]);
    });

    it("the card and the page make the SAME clock-gated reading", () => {
      // #4002 exists because these two held separate opinions about `suspended`.
      // Fixing one and not the other is the same mistake with the roles swapped.
      const card = readFileSync(join(IOS_ROOT, "Components/EventCardView.swift"), "utf8");
      expect(card).toMatch(
        /private var isSuspended: Bool \{\n\s*EventState\.isSuspendedAndStarted\(\n\s*event\.status, commenceTime: event\.commenceTime\?\.asDate\)/
      );
      expect(detail()).toMatch(/EventState\.isSuspendedAndStarted\(\n\s*vm\.event\?\.status/);
    });

    it("the vocabulary keeps BOTH readings, and says which is which", () => {
      // Deleting the plain `isSuspended` would push bucketing onto the clock too,
      // which is a different and unasked-for change.
      expect(canonical()).toMatch(/static func isSuspended\(_ status: String\?\) -> Bool/);
      expect(canonical()).toMatch(
        /static func isSuspendedAndStarted\(\n\s*_ status: String\?, commenceTime: Date\?, now: Date = Date\(\)\n\s*\) -> Bool/
      );
      expect(canonical()).toMatch(/static func hasStarted\(commenceTime: Date\?, now: Date = Date\(\)\) -> Bool/);
    });
  });

  it("the discovery check fires on the REAL pre-fix source", () => {
    // Not a synthetic that merely proves the regex can match: every line below
    // is copied verbatim from origin/master 0d5a6d11, one per file that carried
    // a copy. A guard is only proven by the code it was built to catch.
    const prefix = [
      `    private var isFinished: Bool { vm.event?.status == "completed" || vm.event?.status == "closed" }`,
      `        if event.status == "completed" || event.status == "closed" {`,
      `    private var isDone: Bool { eventStatus == "completed" || eventStatus == "closed" }`,
      `    private var isFinished: Bool { eventStatus == "completed" || eventStatus == "closed" }`,
      `        status == "live" || status == "completed" || status == "closed"`,
      `        } else if status == "completed" || status == "closed" {`,
      `        guard status == "completed" || status == "closed" else { return nil }`,
      `        if (status == "completed" || status == "closed"), let endDate = gameEndDate {`,
      `            if event.status == "completed" || event.status == "closed" {`,
      `            if e.status == "completed" || e.status == "closed" {`,
      `                          e.status != "completed", e.status != "closed" {`,
      `                Text(event.status == "live" ? (event.espn?.period ?? "LIVE") : (event.status == "completed" || event.status == "closed" ? "FINAL" : "VS"))`,
      `                   (event.status == "live" || event.status == "completed" || event.status == "closed") {`,
      `        case "completed", "closed":`,
    ];
    for (const line of prefix) {
      const hits = REDECLARATION_TELLS.filter(([, re]) => re.test(stripComments(line)));
      expect(hits.length).toBeGreaterThan(0);
    }
  });

  it("the scan does NOT fire on a legitimate value use", () => {
    // The inverse hazard, and the reason the tell is keyed on "completed" and
    // never on "closed": a scan that flags a futures status or a Set literal
    // becomes a nuisance and gets suppressed. Each of these is a DIFFERENT
    // vocabulary that happens to share a word.
    for (const line of LEGITIMATE_VALUE_USES) {
      const hits = REDECLARATION_TELLS.filter(([, re]) => re.test(stripComments(line)));
      expect([line, hits]).toEqual([line, []]);
    }
  });

  it("the scan does NOT fire on the delegation that replaced them", () => {
    const delegation = `    private var isDone: Bool { EventState.isFinished(eventStatus) }`;
    expect(REDECLARATION_TELLS.filter(([, re]) => re.test(stripComments(delegation)))).toEqual([]);
  });

  it("stripping comments does not blind the scan to real code", () => {
    const withTrailingComment = `        if event.status == "completed" || event.status == "closed" { // over`;
    expect(
      REDECLARATION_TELLS.some(([, re]) => re.test(stripComments(withTrailingComment)))
    ).toBe(true);
  });

  it("the watch copy is recorded as out of reach, not silently skipped", () => {
    // The scan's own blind spot, named. If this file ever moves into the shared
    // folder the constant stops matching and this test says so.
    const watch = join(__dirname, "../../../", WATCH_IS_OUT_OF_REACH.split(" — ")[0]);
    expect(existsSync(watch)).toBe(true);
    expect(readFileSync(watch, "utf8")).toMatch(/var isSettled: Bool/);
    expect(existsSync(join(IOS_ROOT, "../BainLuckWatch Watch App/EventState.swift"))).toBe(false);
  });
});

/**
 * #4018 — THE THREE MARKET CARDS ASKED "IS IT OVER?" WHERE THEY MEANT "CAN A
 * FINAL STILL ARRIVE?".
 *
 * #4002 fixed that distinction for the HERO and this file's opening block guards
 * it. One scroll below the hero, `MarketMapView`, `TotalPointsSpectrumView` and
 * `PlayerPropsCardView` each carried their own `EventState.isFinished` copy — so
 * on `15301312`, an NPB game abandoned four days earlier, the Runs map still read
 * **`PROJECTION 4.8`**. 184 suspended games carried a projection over the 7 days
 * to 2026-09-08.
 *
 * WHY THESE ASSERTIONS AND NOT SWIFT ONES, MEASURED RATHER THAN ASSUMED. The
 * predicate and the rail gate are pure and are proved in
 * `BainLuckTests/SuspendedProjectionTests.swift`. The WIRING is not: a mutation
 * run on 2026-09-09 hardcoded `MarketMapView.canStillBeGraded` to `true` and
 * removed `TotalPointsSpectrumView`'s strip gate, and **both mutants survived the
 * entire 1,814-test Swift suite** — the same blindness this file's header
 * describes for #4002, in the same place, one card lower. These two assertions
 * are what kill them, and CI runs them.
 */
describe("#4018 — a card stops forecasting a game that can never be graded", () => {
  const read = (rel: string) => stripComments(readFileSync(join(IOS_ROOT, rel), "utf8"));

  const MAP = "Components/MarketMapView.swift";
  const SPECTRUM = "Components/TotalPointsSpectrumView.swift";
  const DETAIL = "Views/EventDetailView.swift";

  it("the predicate is reachable and is the shared one", () => {
    // Reachability first: every assertion below is a regex over source, and a
    // path typo would make all of them vacuous.
    expect(read(MAP).length).toBeGreaterThan(1000);
    expect(read(SPECTRUM).length).toBeGreaterThan(1000);
    expect(stripComments(readFileSync(CANONICAL, "utf8"))).toMatch(
      /static func canStillBeGraded\(/,
    );
  });

  it.each([
    ["MarketMapView", MAP],
    ["TotalPointsSpectrumView", SPECTRUM],
  ])("%s derives the gate from EventState, never from a literal", (_name, rel) => {
    const code = read(rel);
    // KILLS THE MUTANT: `private var canStillBeGraded: Bool { true }`.
    expect(code).toMatch(
      /private var canStillBeGraded: Bool \{\s*EventState\.canStillBeGraded\(eventStatus, commenceTime: commenceTime\)\s*\}/,
    );
    // …and the clock actually reaches it, rather than defaulting to nil forever.
    expect(code).toMatch(/var commenceTime: Date\? = nil/);
  });

  it("every projection marker on the map reads the gate, and none reads isDone", () => {
    const code = read(MAP);
    const gated = code.match(/drawsPregameMarker\(canStillBeGraded: canStillBeGraded\)/g) ?? [];
    expect(gated.length).toBeGreaterThanOrEqual(4);
    // The old question, in the one place it was asked. `isDone` itself stays —
    // it is the SETTLED test and #4018 deliberately does not touch it.
    expect(code).not.toMatch(/drawsPregameMarker\(isDone:/);
  });

  it("the rail gate returns the answer it is given", () => {
    // KILLS THE MUTANT: `-> Bool { true }`. Stated positively as well, because a
    // ban-shaped assertion cannot see the gate being deleted outright.
    const rail = stripComments(readFileSync(join(IOS_ROOT, "Utilities/MarketMapRail.swift"), "utf8"));
    expect(rail).toMatch(
      /static func drawsPregameMarker\(canStillBeGraded: Bool\) -> Bool \{\s*canStillBeGraded\s*\}/,
    );
  });

  it("the spectrum's projection strip is gated, not just its layout flag", () => {
    // KILLS THE MUTANT: `if isPre {`. The gate is deliberately NOT folded into
    // `isPre`, which also picks minimal-vs-full layout — so the scan has to see
    // the strip's own condition rather than the flag's definition.
    expect(read(SPECTRUM)).toMatch(/if isPre, canStillBeGraded \{/);
  });

  it("the spectrum's LAYOUT CHOICE is gated too, or the strip gate is bypassed", () => {
    // 🔴 THE HALF THAT WAS MISSING, AND THE AFTER-SCREENSHOT CAUGHT IT.
    // `TotalPointsSpectrumView.body` picks `minimalView` on
    // `thresholds.count < 5 && isPre`, and `isPre` is TRUE for an abandoned game
    // — it is neither live nor finished. So a suspended match holding fewer than
    // five rungs never reached `projectionStrip`'s gate at all: it drew
    // `minimalView`, which is nothing but a pre-game forecast, and went on
    // reading **`PRE-GAME LINE 5.5`** with a 99% clearance bar over an NPB game
    // that started Sep 9 and was never graded
    // (`artifacts-native-090/after4018-npb.png` — the frame is the fix's OWN
    // after-shot, with the Runs-map tile correctly gone and this one still there).
    //
    // KILLS THE MUTANT: reverting to `thresholds.count < 5 && isPre`.
    const code = read(SPECTRUM);
    expect(code).toMatch(/else if thresholds\.count < 5, isPre, canStillBeGraded \{/);
    // Steering to `fullView` is only honest if the ladder it lands on stops
    // captioning every rung `PRE-GAME` — otherwise the fix trades one false
    // pre-game line for four. Asserted here rather than in its own block because
    // the two lines are one change: neither is correct without the other.
    expect(code).toMatch(
      /if canStillBeGraded \|\| isDone,\s*let caption = MarketMapRail\.spectrumRungCaption\(/,
    );
    // Stated as a ban as well: the `&&` form cannot come back by itself, and a
    // positive-only assertion would still pass if someone added a second,
    // ungated branch beside it.
    expect(code).not.toMatch(/thresholds\.count < 5 && isPre/);
  });

  it("the event page hands both cards a commence time", () => {
    // The wiring the two components cannot assert about themselves: a defaulted
    // `commenceTime` of nil is treated as "started", so a call site that forgets
    // it would suppress projections on unplayed fixtures instead of abandoned
    // ones — the #4021 direction, and the expensive one.
    const detail = read(DETAIL);
    for (const component of ["MarketMapView", "TotalPointsSpectrumView"]) {
      const call = detail.slice(detail.indexOf(`${component}(`));
      expect(call.slice(0, 400)).toMatch(/commenceTime: event\.commenceTime\?\.asDate,/);
    }
  });

  it("the hero and the cards share one definition", () => {
    // #4002's helper is now a delegation. If someone re-inlines it, the hero and
    // the cards can disagree about `suspended` again, which is the whole defect.
    expect(read(DETAIL)).toMatch(
      // NOTE the parameter list contains `Date()`, so a `[^)]*` span stops short
      // of it and the assertion silently never matches. Non-greedy to `-> Bool`.
      /static func showsProjection\([\s\S]*?\) -> Bool \{\s*EventState\.canStillBeGraded\(status, commenceTime: commenceTime, now: now\)\s*\}/,
    );
  });

  it("the props card captions its rungs from EventState, not a literal", () => {
    // #4018's THIRD card. It was left out until Alex ruled, because unlike the
    // other two it prints the MARKET's price for a prop — a real quote, not our
    // projection — so suppressing it was a product decision, not a bug fix. The
    // call went to Alex as three options
    // (`alex-inbox/an-abandoned-games-cards-two-wording-calls.md`) and he ruled
    // C on Thu 2026-09-10 (D120, via Fable-5): keep the numbers, change three
    // words. The number stays; only the caption is state-dependent now.
    //
    // WHY A SOURCE SCAN. `SuspendedProjectionTests` proves the helper returns
    // the right two strings. It cannot prove the view BODY calls it — that is
    // exactly the #4002 mutant this file exists to kill — and CI compiles no
    // Swift. Re-inlining `Text("chance of hitting")` leaves every Swift test
    // green and is caught only here.
    const props = read("Components/PlayerPropsCardView.swift");
    expect(props).toMatch(
      /Text\(EventState\.propsChanceCaption\(\s*eventStatus, commenceTime: commenceTime\s*\)\)/,
    );
    expect(props).not.toMatch(/Text\("chance of hitting"\)/);
  });

  it("the props card is handed the clock, not just the status", () => {
    // The #4021 clause, asserted at the CALL SITE. `propsChanceCaption` asks
    // `isSuspendedAndStarted`, so a `commenceTime` that never travels leaves it
    // permanently nil — and nil means "started", which would caption a
    // future-dated suspended fixture "last quoted chance". The Swift test pins
    // the helper's behaviour; this pins that `EventDetailView` actually passes
    // the date, which no XCTest can see.
    expect(read("Components/PlayerPropsCardView.swift")).toMatch(
      /var commenceTime: Date\?/,
    );
    // Anchored on the `boxScore:` line, which is unique to THIS call site.
    // A `PlayerPropsCardView\([\s\S]*?commenceTime:` span would run past the
    // closing paren and match the NEXT call's date — three sibling views on
    // this screen are passed the same expression.
    expect(read(DETAIL)).toMatch(
      /commenceTime: event\.commenceTime\?\.asDate,\s*boxScore: vm\.relatedFutures\?\.boxScore/,
    );
  });
});
