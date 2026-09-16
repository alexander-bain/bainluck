import XCTest
@testable import Bain_Luck

/// #6528 — THE CARD SAID THE SAME FOUR WORDS TWICE, SIX POINTS APART.
///
/// `EventCardView.topBar` is one `HStack(spacing: 6)`. On its left it draws
/// `StatusBadge`, whose suspended arm prints `EventState.suspendedLabel` — "No
/// result reported" — in an orange capsule. On its right, the suspended arm
/// drew `EventState.suspendedSummary`, and that function OPENS with the same
/// constant. Whenever we hold no score, it opens and closes with it:
///
///     MMA  [⚠ No result reported]  ▮▮      No result reported   🔖
///
/// Photographed on the Sports tab at iPhone 17 width, 2026-09-16 09:19Z, the
/// single card under a heading reading "Live & Paused 1" — MMA event
/// **15310788**, Zevan Hunt v Mayton Perea, `status='suspended'`, both scores
/// null (`artifacts/native-189/02-sports.png`).
///
/// ## The population, measured before the shape was chosen
///
/// Production `db-query`, same session: of **1,788** events carrying
/// `status='suspended'` with a commence time inside 30 days, **1,786 have both
/// scores null**. So `suspendedSummary` degenerates to the bare label on
/// **99.9%** of this card's suspended rows and the duplicate is not an edge
/// case — it is what the card does. The other 2 printed "No result reported ·
/// No result reported · last score N-N", which is the same defect with a tail.
///
/// ## Why the CHIP keeps the words and this slot takes the detail
///
/// The obvious alternative is to match the web card exactly: `FeedCard.tsx`
/// draws no suspended badge at all, so its right slot is the only statement and
/// correctly carries the whole sentence. Copying that would mean suppressing
/// native's chip — and native's card family says the state in a chip (LIVE ·
/// FINAL · Settled · No result reported) and the detail on the right, for live,
/// finished and scheduled rows alike. Suspended was the one arm that put the
/// state in both slots and the detail in neither. Keeping the chip and freeing
/// the slot is this card's own grammar; removing the chip would make the one
/// state a reader may need to act on the quietest of the four.
///
/// ## The date is #6361, built on native for the first time
///
/// #6361 (web, closed) found 17 undated "No result reported" rows stacked
/// against siblings reading "Aug 18 FINAL", spanning three weeks — a reader
/// cannot age the result-less one. The phone's card is identical and its
/// finished arm four lines up already draws `formattedDate`. live/048's refusal
/// is untouched and is the reason the scan below pins WHICH date: the
/// past-tense `formattedDateString` ("Sep 15"), never `formattedDateTimeString`
/// ("Today 7:00 PM"), which would re-advertise a start time that has passed.
///
/// The behaviour classes run the real helper. The final class is a source scan,
/// because the routing lives in a `View` body no test can instantiate headlessly
/// and CI compiles no Swift (#4302); it is built like
/// `SuspendedCardPrintsPreMatch6010Tests`, comments stripped first so the prose
/// this fix wrote cannot satisfy a claim about the code it sits beside.
final class SuspendedCardSaysItOnce6528Tests: XCTestCase {

    /// Read from the constant, never restated. A test that spelled the four
    /// words itself would keep passing if the badge's wording changed and the
    /// slot's copy of it did not — which is the drift this whole file is about.
    private var label: String { EventState.suspendedLabel }

    // MARK: - The defect: the detail never repeats the badge

    /// The photographed specimen: no score, a date.
    func testTheSpecimensDetailDoesNotRepeatTheBadge() {
        let detail = EventState.suspendedCardDetail(away: nil, home: nil, date: "Sep 15")
        XCTAssertEqual(
            detail, "Sep 15",
            """
            MMA 15310788 (Hunt v Perea), both scores null: the trailing slot \
            must carry the date and nothing else. While this was \
            suspendedSummary it printed "\(label)" beside a badge already \
            saying "\(label)".
            """
        )
        XCTAssertFalse(
            detail?.contains(label) ?? false,
            "the trailing slot repeated the badge's own words"
        )
    }

    /// The 2-of-1,788 rows that carry a score. The tail is real information the
    /// badge does not have, so it survives; the label still must not.
    func testAScoredSuspendedRowKeepsItsScoreAndDropsTheLabel() {
        let detail = EventState.suspendedCardDetail(away: 3, home: 4, date: "Sep 15")
        XCTAssertEqual(detail, "last score 3-4 · Sep 15")
        XCTAssertFalse(
            detail?.contains(label) ?? false,
            "\"\(label) · last score 3-4\" beside the badge is the same duplicate with a tail"
        )
    }

    /// Score, no date. The slot still says the thing the badge cannot.
    func testAScoredRowWithNoDateStillPrintsTheScore() {
        XCTAssertEqual(
            EventState.suspendedCardDetail(away: 0, home: 2, date: nil),
            "last score 0-2",
            "a row whose commence time will not parse still has a score worth printing"
        )
    }

    /// ⭐ THE ARM A NIL-RETURNING MUTANT HIDES BEHIND. Nothing to add ⇒ nil, so
    /// the `if let` in `topBar` draws no `Text` at all. An empty string here
    /// would render a zero-width view that still takes its turn in the `HStack`
    /// and still costs the 6pt of spacing before the pin button — #4094's
    /// finding one row up, and invisible in a screenshot.
    func testNothingToAddDrawsNothing() {
        XCTAssertNil(
            EventState.suspendedCardDetail(away: nil, home: nil, date: nil),
            "with neither a score nor a date the badge has already said everything"
        )
        XCTAssertNil(
            EventState.suspendedCardDetail(away: nil, home: nil, date: ""),
            "an empty date string is not a date"
        )
    }

    /// CERT-752's partial-line trap, carried through the lift. One side known
    /// is not a score, and "last score 3-" is worse than silence.
    func testAPartialScoreIsNotAScore() {
        XCTAssertNil(EventState.lastScoreFragment(away: 3, home: nil))
        XCTAssertNil(EventState.lastScoreFragment(away: nil, home: 4))
        XCTAssertEqual(
            EventState.suspendedCardDetail(away: 3, home: nil, date: "Sep 15"),
            "Sep 15",
            "a half score must not reach the card; the date still may"
        )
    }

    // MARK: - The sibling that must NOT change

    /// ⭐ `DiscoverEventCard` is the other caller and it has NO `StatusBadge`:
    /// its corner chip says "PAUSED", a different word, so its body line is the
    /// only place the four words live and must keep saying them whole. This is
    /// the arm that stops the fix being applied one card too wide — the mistake
    /// #4107 named, where this pair of cards gets fixed one at a time.
    func testTheDiscoverSummaryStillSaysTheWholeSentence() {
        XCTAssertEqual(EventState.suspendedSummary(away: nil, home: nil), label)
        XCTAssertEqual(
            EventState.suspendedSummary(away: 3, home: 4),
            "\(label) · last score 3-4",
            "Discover's card has no badge to lean on — it still prints the state"
        )
    }

    // MARK: - The source scan: the view is wired to the helper above

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

    private func cardCode() throws -> String {
        try code("Components", "EventCardView.swift")
    }

    private func badgeCode() throws -> String {
        try code("Components", "StatusBadge.swift")
    }

    /// Anti-vacuity: if these fail, every scan below is asserting about the
    /// wrong file, or about nothing.
    func testTheScansCanSeeTheFilesTheyAreAbout() throws {
        XCTAssertTrue(
            try cardCode().contains("privatevartopBar:someView{"),
            "the scan is not reading EventCardView.swift"
        )
        XCTAssertTrue(
            try badgeCode().contains("structStatusBadge:View{"),
            "the scan is not reading StatusBadge.swift"
        )
    }

    /// The card's trailing slot calls the detail helper, with the PAST-TENSE
    /// date, and binds it — so nothing is drawn when it returns nil.
    func testTheTrailingSlotCallsTheDetailHelperWithThePastTenseDate() throws {
        let code = try cardCode()
        XCTAssertTrue(
            code.contains(
                "elseifisSuspended,letdetail=EventState.suspendedCardDetail("
                + "away:event.awayScore,home:event.homeScore,date:formattedDateString)"),
            """
            the suspended arm of topBar is not wired to suspendedCardDetail with \
            formattedDateString. Before #6528 it read \
            `Text(EventState.suspendedSummary(away:home:))`, which repeated the \
            badge verbatim on 1,786 of 1,788 rows.
            """
        )
        XCTAssertFalse(
            code.contains("Text(EventState.suspendedSummary("),
            "this card must never print the summary again — that string opens with the badge"
        )
        XCTAssertFalse(
            code.contains("date:formattedDateTimeString"),
            """
            live/048: a suspended row must not advertise a start time. The \
            past-tense date is the finished arm's primitive; "Today 7:00 PM" on \
            a match already abandoned is the upcoming fall-through that arm \
            exists to refuse.
            """
        )
    }

    /// ⭐ THE FACT THAT MAKES THE DELETION SAFE, PINNED WHERE IT LIVES. This fix
    /// removes the words from the slot because the badge already says them. If
    /// the badge's suspended arm is ever deleted or re-worded off the constant,
    /// that stops being true and the state is stated NOWHERE on the card — an
    /// omission, which no ban on the slot could ever see (#4478's lesson, from
    /// #2279 missing #3049).
    func testTheBadgeStillSaysTheWordsTheSlotStoppedSaying() throws {
        let code = try badgeCode()
        XCTAssertTrue(
            code.contains("Text(EventState.suspendedLabel)"),
            """
            StatusBadge no longer prints suspendedLabel, so #6528's premise is \
            gone: EventCardView's trailing slot was emptied on the strength of \
            this badge saying it.
            """
        )
        XCTAssertTrue(
            code.contains("elseifEventState.isSuspendedAndStarted(status,commenceTime:commenceTime?.asDate)"),
            "the badge's suspended arm must keep the clock in its test (#4021)"
        )
    }

    /// Both halves of the row must open and close together. They agree only
    /// because they ask the same question of the same two inputs; an inline
    /// status check in either place would let the slot draw a date while the
    /// badge drew nothing, leaving a bare "Sep 15" on an unexplained card.
    func testTheCardAndTheBadgeShareOnePredicate() throws {
        XCTAssertTrue(
            try cardCode().contains(
                "privatevarisSuspended:Bool{EventState.isSuspendedAndStarted("
                + "event.status,commenceTime:event.commenceTime?.asDate)}"),
            "the card's isSuspended must stay delegated to the predicate the badge uses"
        )
        // And the shared predicate really does move together across the clock.
        let kickoff = Date(timeIntervalSince1970: 1_757_000_000)
        XCTAssertTrue(
            EventState.isSuspendedAndStarted(
                "suspended", commenceTime: kickoff, now: kickoff.addingTimeInterval(3600)))
        XCTAssertFalse(
            EventState.isSuspendedAndStarted(
                "suspended", commenceTime: kickoff, now: kickoff.addingTimeInterval(-3600)),
            "#4021: a suspended row dated in the future is pregame, and neither half draws"
        )
    }
}
