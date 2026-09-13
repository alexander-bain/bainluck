import XCTest
@testable import Bain_Luck

/// #6010 — AN EIGHT-DAY-OLD IN-PLAY BLEND, SEMIBOLD, IN TEAM COLOUR.
///
/// `EventCardView`'s per-side number asked `isFinished`. A suspended row is not
/// finished, so it took the `else` and printed `current_odds` — the stale live
/// blend CERT-792 ruled off this card. Every other element had been given the
/// suspended branch one at a time: the bar (live/048), the start time and the
/// score dim (#4021, #4915). The NUMBER, the loudest thing on the card, never
/// got it.
///
/// Production specimen, found by live/210 while measuring #3016's remainder,
/// `/api/events?sport=soccer_italy_serie_a` at 2026-09-13 22:21Z — event
/// `15297959`, Torino v AS Roma, `status='suspended'`, no score:
///
///     current_odds  home 0.1525   captured_at 2026-09-05   (eight days old)
///     opening_odds  home 0.2514
///
/// Web prints **25%/75%** in grey captioned "Pre-match" after ux's `18eaceac8`;
/// this card printed **15%/85%** semibold in team colour. Second specimen on the
/// issue: Como v Parma, 88/12 against an opening 81/19. About 131 suspended rows
/// in that list's window serve a reading, and nine of twelve marquee specimens
/// are US Open doubles at 0.99/0.01 — so the card printed **99%** directly under
/// "No result reported".
///
/// ## What the fix is, and why it is not a fourth status test
///
/// The slot now asks `EventState.canStillBeGraded`. "May we print a forecast?"
/// is the exact question that helper was lifted out of `EventDetailView` to
/// answer (#4018), and a blend IS a forecast. The four states fall out of one
/// predicate instead of being enumerated, and the clock travels with it: a
/// suspended row dated in the FUTURE has not started, can still be graded, and
/// keeps its current line (#4021's Ohio State @ Texas, carried `suspended` four
/// days before kick-off).
///
/// The first two classes below are behaviour — they run the real predicate over
/// the real four states. The third is a source scan, because the routing itself
/// lives in a `View` body that no test can instantiate headlessly and CI
/// compiles no Swift (#4302); it is built like
/// `LiveCardDrawsOneSentence5868Tests`, comments stripped first so the prose
/// this fix wrote cannot satisfy a claim about code.
final class SuspendedCardPrintsPreMatch6010Tests: XCTestCase {

    /// The specimen's own clock: `commence_time` before `now`, so the suspended
    /// row has STARTED. Fixed offsets, never a branch on the wall clock
    /// (gotcha #44).
    private let kickoff = Date(timeIntervalSince1970: 1_757_000_000)
    private var afterKickoff: Date { kickoff.addingTimeInterval(8 * 24 * 3600) }
    private var beforeKickoff: Date { kickoff.addingTimeInterval(-2 * 24 * 3600) }

    // MARK: - The two states that must STOP printing a live reading

    func testTheSuspendedSpecimenPrintsNoLiveReading() {
        XCTAssertFalse(
            EventState.canStillBeGraded(
                "suspended", commenceTime: kickoff, now: afterKickoff),
            """
            Torino v AS Roma 15297959: suspended and started, so the card must \
            take the pre-match arm. While this is true the card printed the \
            0.1525 blend captured 2026-09-05.
            """
        )
    }

    /// The finished vocabulary is `completed`/`closed` and deliberately not the
    /// word "final" — `EventState.isFinished` renders those two AS Final. Naming
    /// a status the enum does not know would make this pass for the reason every
    /// unknown status passes (it falls through to the live arm), which is the
    /// opposite of what is being asserted.
    func testAFinishedRowStillPrintsNoLiveReading() {
        for status in ["completed", "closed"] {
            XCTAssertFalse(
                EventState.canStillBeGraded(
                    status, commenceTime: kickoff, now: afterKickoff),
                "\(status) took the pre-match arm before #6010 and must keep it"
            )
        }
    }

    // MARK: - The two that must be untouched

    func testLiveAndScheduledRowsKeepTheirLiveNumber() {
        for status in ["live", "scheduled", nil] {
            XCTAssertTrue(
                EventState.canStillBeGraded(
                    status, commenceTime: kickoff, now: afterKickoff),
                """
                \(status ?? "nil") must still reach probabilityWithMovement — \
                #6010 withdraws a number from two states, not from four.
                """
            )
        }
    }

    /// #4021's specimen, kept pointing the other way: the withdrawal is gated on
    /// the CLOCK as well as the status, so a suspended row nobody has played yet
    /// keeps the current line its countdown belongs beside.
    func testASuspendedRowBeforeKickoffKeepsItsCurrentLine() {
        XCTAssertTrue(
            EventState.canStillBeGraded(
                "suspended", commenceTime: kickoff, now: beforeKickoff),
            """
            Ohio State @ Texas carried 'suspended' four days BEFORE kick-off; \
            that row has not started and is still pregame.
            """
        )
    }

    /// A suspended row cannot name a winner, so the arm it now lands in cannot
    /// colour one. This is what makes reusing `preGameOddsLabel` safe rather
    /// than merely convenient: its upset-orange and favourite-grey branches both
    /// read `outcome`, and `resolve` rejects anything `isFinished` rejects.
    func testASuspendedRowNamesNoWinnerSoThePreMatchArmStaysGrey() {
        let outcome = EventOutcome.resolve(
            status: "suspended", homeScore: 2, awayScore: 0)
        XCTAssertEqual(
            outcome, .undecided,
            "a partial score on an abandoned match is not a result (#4018)"
        )
        XCTAssertFalse(outcome.won(isAway: false), "no verdict on a row with none")
        XCTAssertFalse(outcome.won(isAway: true), "no verdict on a row with none")
    }

    // MARK: - The source scan: the real view is wired to the predicate above

    /// Comments stripped, then ALL whitespace removed.
    ///
    /// Stripped because a scan that reads the whole file is satisfied by the
    /// prose this fix wrote beside the line it checks, and then passes forever
    /// for the wrong reason (`LiveCardDrawsOneSentence5868Tests` says so first).
    /// Dense rather than space-collapsed because the claims below span line
    /// breaks in the real source: collapsing to single spaces would make every
    /// expectation encode where the author happened to wrap, so a reformat that
    /// changed nothing would read as the defect returning.
    private func cardCode() throws -> String {
        let url = URL(fileURLWithPath: #filePath)
            .deletingLastPathComponent()   // BainLuckTests
            .deletingLastPathComponent()   // Bain Luck (project dir)
            .appendingPathComponent("Bain Luck")
            .appendingPathComponent("Components")
            .appendingPathComponent("EventCardView.swift")
        return try String(contentsOf: url, encoding: .utf8)
            .split(separator: "\n", omittingEmptySubsequences: false)
            .map { line -> String in
                guard let slashes = line.range(of: "//") else { return String(line) }
                return String(line[line.startIndex..<slashes.lowerBound])
            }
            .joined(separator: "\n")
            .filter { !$0.isWhitespace }
    }

    /// Anti-vacuity: if this fails, every scan below is asserting about the
    /// wrong file, or about nothing.
    func testTheScanCanSeeTheFileItIsAbout() throws {
        let code = try cardCode()
        XCTAssertTrue(
            code.contains("privatefuncpreGameOddsLabel(forside:TeamSide)"),
            "the scan is not reading EventCardView.swift"
        )
        XCTAssertTrue(
            code.contains("privatefuncprobabilityWithMovement(forside:TeamSide)"),
            "the scan is not reading EventCardView.swift"
        )
    }

    func testTheSlotRoutesOnTheGradablePredicateAndNotOnIsFinished() throws {
        let code = try cardCode()
        XCTAssertTrue(
            code.contains(
                "ifcanStillBeGraded{probabilityWithMovement(for:side)}"
                + "else{preGameOddsLabel(for:side)}"),
            """
            the per-side slot is not routed on canStillBeGraded. Before #6010 it \
            read `if isFinished { preGameOddsLabel(for: side) } else { \
            probabilityWithMovement(for: side) }`, which sent every suspended \
            row to the live blend.
            """
        )
        XCTAssertFalse(
            code.contains("ifisFinished{preGameOddsLabel(for:side)}"),
            "the pre-#6010 routing is back"
        )
    }

    /// The view's predicate must be the shared one. An inline
    /// `isFinished || isSuspended` would pass the scan above and would be the
    /// fourth private copy of a question #4018 already answered once.
    func testTheViewsPredicateDelegatesToEventState() throws {
        let code = try cardCode()
        XCTAssertTrue(
            code.contains(
                "privatevarcanStillBeGraded:Bool{EventState.canStillBeGraded("
                + "event.status,commenceTime:event.commenceTime?.asDate)}"),
            """
            canStillBeGraded must delegate to EventState, passing the commence \
            time — dropping it would re-break #4021's future-dated suspended row.
            """
        )
    }
}
