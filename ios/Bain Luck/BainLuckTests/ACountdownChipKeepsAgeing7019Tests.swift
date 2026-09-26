import XCTest
@testable import Bain_Luck

/// #7019 — THE COUNTDOWN CHIP FROZE AT THE MINUTE THE ROW WAS DRAWN.
///
/// Alex's signed-in simulator walk, build `1.0 (10)` from master `7632e7e72`,
/// 2026-09-18. One My Stuff **Upcoming** row on a session that had been open
/// since ~09:57 PDT, photographed at 11:57 PDT
/// (`artifacts/native-233b/asis-signedin-115704.png`):
///
///     MLB   ⏱ In 1d 3h                        Tomorrow 1:10 PM
///
/// Tomorrow 1:10 PM was 1d 1h 13m away. A cold relaunch of the *same build*
/// seven minutes later read `In 1d 1h` and was correct
/// (`artifacts/native-233b/b09-08-mystuff-s1600.png`), so the data was right,
/// the arithmetic was right, and the chip was two hours stale — exactly the age
/// of the open session.
///
/// ## Why the format was never the defect, and what that costs a test
///
/// `formatCountdown` read the current instant implicitly
/// (`date.timeIntervalSinceNow`). Every other input to `StatusBadge`'s
/// scheduled arm — `status`, `commenceTime` — is fixed for the life of the row,
/// so the body read nothing that ever changed and SwiftUI had no reason to
/// redraw it. **A test that only exercises the formatter cannot see this**: the
/// formatter returns the right answer for the instant it is asked about, every
/// time, frozen or not. So the claim under test here is the *recomputation* —
/// that the string is a function of an instant the view observes — and the
/// instant is now a parameter precisely so a test can vary it.
///
/// ## The class, which is wider than the photograph
///
/// #6544 fixed this same freeze on the **event hero** by wrapping that one badge
/// in a 60-second `TimelineView`. The other four `StatusBadge` call sites never
/// got one: `EventCardView` (which draws Discover, Sports **and** the My Stuff
/// row in the photograph), `SearchView` twice, and `TeamDetailView`. The tick
/// now sits on the badge, so the fix reaches all five without a call site
/// knowing about it — ``testTheFourPreviouslyFrozenCallSitesAreReachedByTheBadge``
/// is what holds that, because it is the half a unit test of the formatter can
/// never see.
final class ACountdownChipKeepsAgeing7019Tests: XCTestCase {

    // MARK: - The photographed specimen, replayed

    /// The session opened. An arbitrary fixed instant: **nothing in this file
    /// reads a wall clock**, because `now` is injected everywhere, so gotcha
    /// #44's "offset first, never anchor on a boundary" applies to the OFFSETS
    /// rather than to the anchor. Both offsets below land 13 minutes into their
    /// bucket, well clear of `formatCountdown`'s `Int(interval / 60)` rounding
    /// edge — the trap that made five of #6544's ten mutant runs fail for a
    /// reason that had nothing to do with the mutant.
    private let sessionOpened = Date(timeIntervalSince1970: 1_758_207_420)

    /// "Tomorrow 1:10 PM", 27h13m after the session opened.
    private var kickoff: Date { sessionOpened.addingTimeInterval(27 * 3_600 + 13 * 60) }

    /// 11:57 — when Alex read the stale chip.
    private var photographedAt: Date { sessionOpened.addingTimeInterval(2 * 3_600) }

    /// ⭐ THE DEFECT, AS A PAIR. One kickoff, two instants, two strings. The
    /// frozen chip was the first of these shown at the time of the second.
    func testOneKickoffReadsDifferentlyTwoHoursLater() {
        XCTAssertEqual(
            formatCountdown(from: kickoff, now: sessionOpened), "1d 3h",
            "the string the chip was still showing at 11:57 — correct only for 09:57"
        )
        XCTAssertEqual(
            formatCountdown(from: kickoff, now: photographedAt), "1d 1h",
            """
            what the cold relaunch printed, and what the open session should have \
            aged into. If these two are ever equal the specimen has stopped being \
            able to show a freeze and every class below is vacuous
            """
        )
        XCTAssertNotEqual(
            formatCountdown(from: kickoff, now: sessionOpened),
            formatCountdown(from: kickoff, now: photographedAt),
            "anti-vacuity: two hours must move this string, or there is nothing to tick for"
        )
    }

    /// The other direction, one minute apart rather than two hours — this is why
    /// the clock's period is sixty seconds and not five minutes. Same reasoning
    /// as #6544's `testTheCountdownChangesWithinOneMinute…`, re-asserted here
    /// against the injected clock rather than against two `Date()` calls a
    /// fraction of a second apart.
    func testAMinuteIsEnoughToMoveTheString() {
        let halfAnHourOut = sessionOpened.addingTimeInterval(35 * 60 + 30)
        XCTAssertNotEqual(
            formatCountdown(from: halfAnHourOut, now: sessionOpened),
            formatCountdown(from: halfAnHourOut, now: sessionOpened.addingTimeInterval(60)),
            """
            a minute did not move the countdown half an hour before kickoff, so \
            MinuteClock's 60-second period would be arbitrary
            """
        )
    }

    /// The expiry case, which is the reason the badge kept its `if let` instead
    /// of moving the whole arm inside a timeline closure: the *absence* of a
    /// countdown is time-dependent too, so `body` has to re-run, not just the
    /// string. A frozen chip did not merely go stale here — it kept claiming a
    /// kickoff that had already happened.
    func testOnceTheKickoffPassesThereIsNoCountdownLeftToDraw() {
        XCTAssertNotNil(
            formatCountdown(from: kickoff, now: sessionOpened),
            "anti-vacuity: there has to be a chip before its disappearance means anything"
        )
        XCTAssertNil(
            formatCountdown(from: kickoff, now: kickoff.addingTimeInterval(1)),
            "a kickoff one second ago is not a countdown"
        )
    }

    /// The default argument is the old behaviour, so none of the five call
    /// sites, and none of #6544's assertions, changed meaning when `now` became
    /// a parameter.
    func testTheDefaultInstantIsStillNow() {
        let soon = Date().addingTimeInterval(4 * 86_400 + 12 * 3_600 + 1_800)
        XCTAssertEqual(
            formatCountdown(from: soon), formatCountdown(from: soon, now: Date()),
            "omitting `now` must mean `Date()`, or existing callers silently changed"
        )
    }

    // MARK: - ⭐ The clock actually republishes

    /// The half that is not arithmetic. A `MinuteClock` that constructs a
    /// `Timer` and never fires satisfies every class above perfectly and leaves
    /// the chip exactly as frozen as it was — the mutant is "delete
    /// `RunLoop.main.add`", and only this test kills it.
    func testTheClockPublishesALaterInstantWithoutBeingAsked() {
        let seed = Date(timeIntervalSince1970: 0)
        let clock = MinuteClock(interval: 0.1, now: seed)
        defer { clock.stop() }

        XCTAssertEqual(clock.now, seed, "anti-vacuity: the clock starts where it was seeded")

        // A polling expectation rather than a `$now` subscription, because this
        // has to spin the run loop: the timer is scheduled on `RunLoop.main`,
        // and a test that merely sleeps proves the clock dead.
        let firstTick = XCTNSPredicateExpectation(
            predicate: NSPredicate { _, _ in clock.now > seed },
            object: nil
        )
        wait(for: [firstTick], timeout: 5)

        let afterFirstTick = clock.now
        XCTAssertGreaterThan(
            afterFirstTick, seed,
            """
            the clock never republished. A MinuteClock that constructs a Timer and \
            never adds it to a run loop satisfies every other class in this file \
            and leaves the chip exactly as frozen as it was
            """
        )

        // ⭐ AND A SECOND ONE. This battery's own mutant `repeats: false` passes
        // the assertion above perfectly: the chip ages once, a minute after the
        // row appears, and is then frozen for the rest of the session — the
        // original defect, delayed by sixty seconds and harder to see.
        let secondTick = XCTNSPredicateExpectation(
            predicate: NSPredicate { _, _ in clock.now > afterFirstTick },
            object: nil
        )
        wait(for: [secondTick], timeout: 5)

        XCTAssertGreaterThan(
            clock.now, afterFirstTick,
            "the clock ticked once and stopped, so every chip freezes one period in"
        )
    }

    /// The period is not free to drift. #6544 established sixty seconds from
    /// `formatCountdown`'s own resolution, and ``testAMinuteIsEnoughToMoveTheString``
    /// re-proves that reasoning above — but nothing else would notice the
    /// default becoming 3600, and an hourly chip is stale by up to 59 minutes in
    /// the hour before kickoff, which is the hour the number is read in.
    func testTheDefaultPeriodIsStillSixtySeconds() throws {
        XCTAssertTrue(
            try code("ViewModels", "MinuteClock.swift")
                .contains("init(interval:TimeInterval=60,now:Date=Date())"),
            """
            MinuteClock's default period is no longer 60 seconds. Every behavioural \
            class in this file injects its own interval, so none of them can see this
            """
        )
    }

    /// One instance, so one subscription per chip rather than one timer per row,
    /// and it is seeded with a real instant rather than a placeholder. Asserted
    /// against the epoch and not against `timeIntervalSinceNow`: whether the
    /// main run loop has spun since the singleton was created is a property of
    /// the surrounding suite, and a guard that depends on it is flaky, not
    /// strict.
    func testTheSharedClockIsOneInstanceSeededWithARealDate() {
        XCTAssertTrue(
            MinuteClock.shared === MinuteClock.shared,
            "the shared clock is being rebuilt on each access, so every chip would hold its own timer"
        )
        XCTAssertGreaterThan(
            MinuteClock.shared.now.timeIntervalSince1970, 1_700_000_000,
            "the shared clock's instant is a real one, not an epoch placeholder"
        )
    }

    // MARK: - The source scan: the badge reads the clock, on every surface

    /// Comments stripped, then all whitespace removed. Stripped for
    /// `HeroSaysTheCountdownOnce6544Tests`' reason: a scan that reads the whole
    /// file is satisfied by the prose this fix wrote beside the line it checks,
    /// and then passes forever for the wrong reason.
    private func code(_ directory: String, _ file: String) throws -> String {
        let url = URL(fileURLWithPath: #filePath)
            .deletingLastPathComponent()   // BainLuckTests
            .deletingLastPathComponent()   // Bain Luck (project dir)
            .appendingPathComponent("Bain Luck")
            .appendingPathComponent(directory)
            .appendingPathComponent(file)
        return try String(contentsOf: url, encoding: .utf8)
            .split(separator: "\n", omittingEmptySubsequences: false)
            .map { line -> String in
                guard let slashes = line.range(of: "//") else { return String(line) }
                return String(line[line.startIndex..<slashes.lowerBound])
            }
            .joined(separator: "\n")
            .filter { !$0.isWhitespace }
    }

    private func badgeCode() throws -> String { try code("Components", "StatusBadge.swift") }

    /// Anti-vacuity: if this fails, every scan below is asserting about the
    /// wrong file, or about nothing.
    func testTheScansCanSeeTheFilesTheyAreAbout() throws {
        XCTAssertTrue(
            try badgeCode().contains("structStatusBadge:View{"),
            "the scan is not reading StatusBadge.swift"
        )
        for (directory, file) in Self.previouslyFrozenCallSites {
            XCTAssertTrue(
                try code(directory, file).contains("StatusBadge("),
                "\(file) no longer draws a StatusBadge, so its row in this class proves nothing"
            )
        }
    }

    /// ⭐ THE SEAM NO BEHAVIOURAL TEST CAN REACH. `StatusBadge.body` is a
    /// `ViewBuilder` chain; there is no headless way to render it and read the
    /// string, and CI compiles no Swift (#4302). Both halves are pinned
    /// positively — the property that makes the view a subscriber, and the
    /// argument that makes the arm read it — because either one alone compiles
    /// and draws correctly exactly once.
    func testTheBadgeSubscribesToTheClockAndDrawsAgainstIt() throws {
        let code = try badgeCode()
        XCTAssertTrue(
            code.contains("@ObservedObjectvarclock=MinuteClock.shared"),
            """
            StatusBadge no longer observes MinuteClock. Without the subscription \
            nothing invalidates this view, so the chip is frozen again however \
            the countdown is computed
            """
        )
        // #8841 — the arm may route through `StatusBadge.countdownText`, which
        // withholds the chip on an unannounced start. That helper takes `now`
        // with NO default, so dropping the argument there does not compile, and
        // it must hand that instant on to `formatCountdown` rather than let the
        // default read `Date()` — both halves pinned, or the seam moves inward.
        let viaHelper =
            code.contains("StatusBadge.countdownText(commenceTime:commenceTime,startIsTbd:startIsTbd,now:clock.now)")
            && code.contains("startIsTbd:Bool,now:Date)->String?{")
            && code.contains("formatCountdown(from:date,now:now)")
        XCTAssertTrue(
            code.contains("formatCountdown(from:date,now:clock.now)") || viaHelper,
            """
            the scheduled arm stopped passing the observed instant. \
            `formatCountdown(from:)` defaults `now` to `Date()`, so dropping the \
            argument COMPILES, draws the right number once, and never ages — \
            which is #7019 exactly
            """
        )
        XCTAssertFalse(
            code.contains("let clock = MinuteClock.shared".filter { !$0.isWhitespace }),
            """
            the clock is held as a plain `let`. A reference without @ObservedObject \
            reads the instant at render and subscribes to nothing
            """
        )
    }

    /// The chip still says the words, so the class above cannot pass by the
    /// scheduled arm having been deleted (#4478's lesson, and #6528's). This
    /// duplicates one line of #6544 on purpose: that file's premise is the
    /// hero's centre column having been emptied, and this one's is a chip that
    /// ages — neither should be able to go green on a chip that is gone.
    func testTheChipStillSaysTheCountdownAndStillVanishesWhenThereIsNone() throws {
        let code = try badgeCode()
        XCTAssertTrue(code.contains("Text(\"In\\(countdown)\")"), "the scheduled arm stopped printing the countdown")
        XCTAssertTrue(
            code.contains("}else{EmptyView()}"),
            """
            the arm lost the branch it takes once the kickoff passes. It has to be \
            `EmptyView` and not an empty container: EventCardView's top bar is an \
            HStack(spacing: 6) with no Spacer, so a zero-content element there \
            leaves a visible hole where the chip was
            """
        )
    }

    /// Every surface that drew a frozen chip, named. `EventCardView` is the one
    /// in the photograph — My Stuff's Upcoming section routes through
    /// `feedSection` → `feedRow` → `EventCardView` — and the others are the same
    /// defect nobody had photographed yet.
    private static let previouslyFrozenCallSites: [(String, String)] = [
        ("Components", "EventCardView.swift"),
        ("Views", "SearchView.swift"),
        ("Views", "TeamDetailView.swift"),
    ]

    /// ⭐ DOES THE FIX REACH THE READER? The four frozen call sites are fixed by
    /// *not* having been edited: they draw `StatusBadge`, and the badge now
    /// ticks. This class states that as an assertion rather than leaving it as
    /// an assumption, and it fails the day someone "fixes" a surface by giving
    /// it a private countdown of its own — which is how the hero and the rows
    /// came to disagree in the first place.
    func testTheFourPreviouslyFrozenCallSitesAreReachedByTheBadge() throws {
        for (directory, file) in Self.previouslyFrozenCallSites {
            let code = try code(directory, file)
            XCTAssertFalse(
                code.contains("formatCountdown("),
                """
                \(file) formats a countdown of its own. The number then has two \
                authors again and only one of them observes the clock
                """
            )
            XCTAssertFalse(
                code.contains("\"In\\("),
                "\(file) is printing its own \"In …\" countdown instead of letting the chip say it"
            )
        }
    }

    /// The My Stuff row in the photograph, pinned end to end, so "EventCardView
    /// is the specimen's component" is checked rather than remembered.
    func testTheMyStuffUpcomingRowIsDrawnByEventCardView() throws {
        let myStuff = try code("Views", "MyStuffView.swift")
        XCTAssertTrue(
            myStuff.contains("feedSection(title:\"Upcoming\""),
            "My Stuff no longer has the Upcoming section the chip was photographed in"
        )
        XCTAssertTrue(
            myStuff.contains("EventCardView("),
            """
            My Stuff's rows are no longer EventCardView, so this issue's specimen \
            path has moved and the call-site class above may no longer cover it
            """
        )
    }
}
