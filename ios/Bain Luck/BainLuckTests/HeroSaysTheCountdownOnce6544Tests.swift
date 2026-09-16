import XCTest
@testable import Bain_Luck

/// #6544 — THE EVENT HERO SAID THE SAME COUNTDOWN TWICE, 250 POINTS APART.
///
/// `bainluck://events/14780544` (Indianapolis Colts @ Kansas City Chiefs, Sun
/// Sep 20 5:20 PM PDT), photographed on the iPhone 17 simulator against master
/// `95794d896`, built and installed, 2026-09-16 11:42Z
/// (`artifacts/native-190/05-event-nfl-upcoming.png`):
///
///     [⏱ In 4d 12h]                    📺 NBC   Sep 20 at 5:20 PM
///
///        COLTS       28% – 72%       CHIEFS
///                  Win Probability ▮▮
///                    Proj. 21–27
///                    In 4d 12h                 ← the second copy
///
/// The chip is `StatusBadge`'s scheduled arm; the second copy was a bare `Text`
/// in `EventDetailView`'s centre column. Both called the one `formatCountdown`
/// (`FormattingUtilities.swift:71`) with the one `commenceTime`, so they could
/// not disagree — it was a verbatim duplicate by construction, not a rounding
/// accident this fixture happens to hit.
///
/// ## Why the chip is the copy that stays
///
/// #6528's rule, one surface up: the state lives in `StatusBadge` — it is what
/// says LIVE / FINAL / Settled / "In 4d 12h" on cards, search rows and team
/// schedules alike — and the other slot carries only what the chip cannot say.
/// The centre column is the probability column ("28% – 72%", "Win Probability",
/// "Proj. 21–27"), and the meta row beside the chip already holds the date and
/// the broadcast, so there was nothing left for the slot to carry. It is gone
/// rather than refilled. The hero's own comment had named the arrangement all
/// along: `// Top meta row: status badge + countdown + broadcast + date`.
///
/// ## The regression the deletion could have shipped, and the class that stops it
///
/// The deleted `Text` read a `countdownText` @State that a view-wide 60-second
/// `Timer` wrote, and it was that state's ONLY reader. SwiftUI re-renders a
/// view only when the body read the value that changed, so removing the
/// duplicate on its own would have frozen the chip at whatever it said when the
/// page appeared — a page left open over lunch still reading "In 4d 12h". The
/// tick now sits on the chip itself as a `TimelineView`, and
/// ``testTheChipStillTicks`` is the guard, because a later reader has every
/// reason to think a `TimelineView` wrapping one badge is decorative.
///
/// The first three classes run real helpers. The last is a source scan, because
/// the routing lives in a `View` body no test can instantiate headlessly and CI
/// compiles no Swift (#4302); it is built like
/// `SuspendedCardSaysItOnce6528Tests` — comments stripped first, so the prose
/// this fix wrote cannot satisfy a claim about the code it sits beside.
final class HeroSaysTheCountdownOnce6544Tests: XCTestCase {

    /// A commence time far enough out that `formatCountdown` draws the
    /// photographed `Nd Nh` shape, anchored off the test's own clock rather
    /// than a wall date — `formatCountdown` measures against `now` and takes no
    /// injected clock, so an absolute anchor here would expire (gotcha #44).
    ///
    /// 🔴 THE EXTRA THIRTY MINUTES ARE THE WHOLE POINT, and this file's own
    /// mutation battery is what found it. At a flat `4d 12h` the anchor sits
    /// exactly ON `formatCountdown`'s rounding boundary: the function takes
    /// `Int(interval / 60)`, and 388,800 s is 6,480.0 minutes to the last bit,
    /// so whether the microseconds that elapse between constructing this date
    /// and reading it push the quotient below 6,480 decides between "4d 12h"
    /// and "4d 11h" — two calls a fraction of a second apart disagreed, and
    /// `testBothCopiesWereTheSameString` failed on five of ten mutant runs for
    /// a reason that had nothing to do with the mutant. Offsetting into the
    /// MIDDLE of the bucket buys half an hour of slack in both directions
    /// (gotcha #44: offset first, and never anchor on the boundary itself).
    private var futureKickoff: Date {
        Date().addingTimeInterval(4 * 86_400 + 12 * 3_600 + 1_800)
    }
    private var pastKickoff: Date { Date().addingTimeInterval(-3 * 3_600) }

    /// Every status that reaches the hero and is neither `live` nor finished.
    /// `scheduled` is the literal the badge's default arm passes on; the others
    /// are what the wire actually carries for a fixture that has not kicked off.
    private let pregameStatuses = ["scheduled", "postponed", "suspended", "delayed", "", "unknown"]

    // MARK: - The duplicate was verbatim, and it could not have been anything else

    /// One `formatCountdown`, one `commenceTime` ⇒ one string. The chip and the
    /// deleted `Text` differed only in the view they sat in.
    func testBothCopiesWereTheSameString() {
        let kickoff = futureKickoff
        guard let once = formatCountdown(from: kickoff),
              let twice = formatCountdown(from: kickoff) else {
            return XCTFail("formatCountdown returned nil for a kickoff four days out")
        }
        XCTAssertEqual(
            "In \(once)", "In \(twice)",
            "the two hero copies read the same function with the same input"
        )
        XCTAssertEqual(
            once, "4d 12h",
            "the specimen's shape, and it is exact now that the anchor is off the boundary"
        )
    }

    // MARK: - ⭐ Whenever the deleted copy drew, the chip drew — no arrangement lost

    /// The deleted arm's gate was: a countdown exists (a future commence time),
    /// `status != "live"`, and `!EventState.isFinished(status)`. Under those
    /// three, `heroStatusBadge` cannot reach its live arm, its finished arm, its
    /// venue-settled arm or its suspended arm — every one of the latter two
    /// requires the commence time to be in the PAST — so it falls through to the
    /// arm that draws the chip. This is the fact that made the deletion safe,
    /// and it is asserted against the real predicates rather than read off the
    /// chain by eye.
    func testEveryStateThatDrewTheDeletedCopyStillDrawsTheChip() {
        let kickoff = futureKickoff
        XCTAssertNotNil(
            formatCountdown(from: kickoff),
            "anti-vacuity: with no countdown the deleted arm never drew and this proves nothing"
        )
        for status in pregameStatuses {
            XCTAssertFalse(
                EventState.isFinished(status),
                "\(status) must not be finished, or the deleted arm never drew for it either"
            )
            XCTAssertFalse(
                EventState.isSuspendedAndStarted(status, commenceTime: kickoff),
                """
                \(status): the badge took the suspended arm for a fixture that has \
                not kicked off, so the chip would say "\(EventState.suspendedLabel)" \
                while the countdown it replaced is gone (#4021's clause is what \
                holds this shut)
                """
            )
            XCTAssertFalse(
                EventState.showsVenueSettledVerdict(
                    status, venueSettled: true, commenceTime: kickoff),
                """
                \(status): the badge took #6381's settled arm before reaching the \
                countdown, on a fixture that has not started. venueSettled is \
                passed TRUE here on purpose — the weakest case for the claim
                """
            )
        }
    }

    /// The other direction, so the class above is not passing because nothing
    /// ever draws: once the clock is past the kickoff there is no countdown for
    /// either copy to print, which is why the suspended and settled arms are
    /// free to own that side of the fence.
    func testOnceTheGameHasStartedNeitherCopyHadACountdown() {
        XCTAssertNil(
            formatCountdown(from: pastKickoff),
            "a kickoff three hours ago is not a countdown"
        )
        XCTAssertTrue(
            EventState.isSuspendedAndStarted("suspended", commenceTime: pastKickoff),
            "and THAT side of the fence is the suspended arm's, uncontested"
        )
    }

    // MARK: - ⭐ The chip has to keep ageing

    /// Why the tick is sixty seconds and not five minutes: `formatCountdown`
    /// resolves to the minute all the way down to `<1m`, so a coarser interval
    /// shows a reader a stale minute in the hour when the number matters most.
    func testTheCountdownChangesWithinOneMinuteSoTheTickIsSixtySeconds() {
        let base = Date().addingTimeInterval(35 * 60 + 30)
        guard let now = formatCountdown(from: base),
              let aMinuteLater = formatCountdown(from: base.addingTimeInterval(-60)) else {
            return XCTFail("formatCountdown returned nil half an hour before kickoff")
        }
        XCTAssertNotEqual(
            now, aMinuteLater,
            """
            \(now) vs \(aMinuteLater): if a minute did not move this string the \
            TimelineView period would be arbitrary. It moves, so 60 is the \
            coarsest interval that never shows a stale number
            """
        )
    }

    // MARK: - The source scan: one countdown, in the chip, still ticking

    /// Comments stripped, then all whitespace removed. Stripped because a scan
    /// that reads the whole file is satisfied by the prose this fix wrote beside
    /// the line it checks, and then passes forever for the wrong reason.
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

    private func heroCode() throws -> String {
        try code("Views", "EventDetailView.swift")
    }

    private func badgeCode() throws -> String {
        try code("Components", "StatusBadge.swift")
    }

    /// Anti-vacuity: if these fail, every scan below is asserting about the
    /// wrong file, or about nothing.
    func testTheScansCanSeeTheFilesTheyAreAbout() throws {
        XCTAssertTrue(
            try heroCode().contains("structEventDetailView:View{"),
            "the scan is not reading EventDetailView.swift"
        )
        XCTAssertTrue(
            try badgeCode().contains("structStatusBadge:View{"),
            "the scan is not reading StatusBadge.swift"
        )
    }

    /// The ban. `"In\(` is the interpolated prefix both copies used and it is
    /// tighter than it looks: the two surviving `"In` literals in this file are
    /// "Individual sportsbooks", whose next character is a `d`.
    func testTheHeroNeverPrintsACountdownItself() throws {
        let code = try heroCode()
        XCTAssertFalse(
            code.contains("\"In\\("),
            """
            EventDetailView is printing a countdown again. The chip six lines \
            into the meta row is already saying it — that is the whole of #6544
            """
        )
        XCTAssertFalse(
            code.contains("formatCountdown("),
            """
            the hero is formatting a countdown of its own. Whatever it does with \
            the result, the number now has two authors again and StatusBadge is \
            the one that draws it
            """
        )
    }

    /// ⭐ THE OMISSION A BAN CANNOT SEE. A file that prints no countdown passes
    /// the class above perfectly, and an upcoming game with no countdown at all
    /// is a worse hero than one that says it twice. So the surviving copy is
    /// pinned where it lives, positively — #4478's lesson, and #6528's.
    func testTheChipStillSaysTheWordsTheCentreColumnStoppedSaying() throws {
        let code = try badgeCode()
        XCTAssertTrue(
            code.contains("Text(\"In\\(countdown)\")"),
            """
            StatusBadge's scheduled arm no longer prints the countdown, so \
            #6544's premise is gone: the hero's centre column was emptied on the \
            strength of this chip saying it
            """
        )
        XCTAssertTrue(
            code.contains("elseifstatus==\"scheduled\"{"),
            "the arm the hero's default branch routes to must still exist"
        )
        XCTAssertTrue(
            try heroCode().contains("StatusBadge(status:\"scheduled\",commenceTime:event.commenceTime,"),
            """
            heroStatusBadge stopped routing an un-live, unfinished, un-started \
            event to the scheduled badge, which is the only thing now drawing the \
            countdown on this page
            """
        )
    }

    /// ⭐ THE TICK. The chip derives its text from `commenceTime` on each render
    /// and nothing else on a pregame page re-renders it — the refresh ring is
    /// live-only (`showsRefreshCountdown`). Delete this wrapper and the chip
    /// freezes at the minute the page opened, silently, on the one state whose
    /// entire content is a clock.
    func testTheChipStillTicks() throws {
        let code = try heroCode()
        XCTAssertTrue(
            code.contains("TimelineView(.periodic(from:.now,by:60)){_in"
                          + "heroStatusBadge(event)}"),
            """
            the hero's status chip is no longer inside a 60-second TimelineView. \
            It looks like a decorative wrapper around one badge and it is not: \
            it is the only thing that re-renders "In 4d 12h" after the page \
            appears, now that the centre column's duplicate — which used to be \
            the sole reader of a 60-second Timer's @State — is gone
            """
        )
        XCTAssertFalse(
            EventDetailView.showsRefreshCountdown(status: "scheduled"),
            """
            a pregame page has no refresh ring, so nothing else on it re-renders \
            on a clock. If this ever becomes true the TimelineView is still \
            correct, but this test's reasoning needs re-reading
            """
        )
    }
}
