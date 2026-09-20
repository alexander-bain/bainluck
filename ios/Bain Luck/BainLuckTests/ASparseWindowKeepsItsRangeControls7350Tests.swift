import XCTest
import SwiftUI
@testable import Bain_Luck

/// #7350 — THE ONE STATE THAT NEEDED THE RANGE CONTROLS WAS THE ONE STATE THAT HID THEM.
///
/// Alex's physical TestFlight 1.0 (16) (`b2b08e530`), futures **59165099** —
/// *Will federal capital gains taxes be cut in 2026?* — showed
/// *"Limited price history available"* and nothing else: no chips, no chart, no way
/// forward (`artifacts/alex-phone-20260919-build16/IMG_9573.png`).
///
/// The history was already on the phone. The public route, asked for 168 hours,
/// answered with `actual_hours: 2160` and **nine** observation times reaching back
/// to August 18 — and exactly ONE of them falls inside seven days:
///
///     2026-08-18T22:00Z   2026-09-08T12:00Z   2026-09-09T16:00Z
///     2026-09-10T00:00Z   2026-09-10T04:00Z   2026-09-10T08:00Z
///     2026-09-11T20:00Z   2026-09-11T23:00Z   2026-09-19T10:00Z   ← the only recent one
///
/// The card defaults to `7d`, filters the response back to seven days, and rendered
/// its empty state whenever fewer than two points survived — **with the control bar
/// inside the other branch.** So the eight older observations the view was holding
/// in memory were unreachable, and the sentence over them said nothing about them.
///
/// ═══ WHAT THESE TESTS PIN, AND WHAT THEY DELIBERATELY DO NOT ═══
///
/// The plot still requires two points. One observation is an instant, and joining an
/// instant to nothing is the invented interval #7077 was written about — so the ship
/// is REACHABILITY (the chips survive the sparse state) and HONESTY (the sentence
/// counts what the response holds), never a line drawn through a single price.
///
/// Counts are read from the response, so "no window" and "no history" stop sharing
/// one sentence — gotcha #53, an empty answer is a shape, not an absence.
final class ASparseWindowKeepsItsRangeControls7350Tests: XCTestCase {

    private typealias Chart = EvolutionChartView

    // MARK: - The reported specimen: nine observations, one of them recent

    func testTheCapitalGainsMarketSaysWhatItHasAndWhereItIs() {
        let copy = Chart.sparseCopy(
            windowInstants: 1, totalInstants: 9, windowWord: "in the last 7 days")

        XCTAssertEqual(copy.note, "One price in the last 7 days — 8 earlier prices")
        XCTAssertEqual(
            copy.hint, "Try a longer range",
            "the eight older observations are in the response already — say they are reachable")
    }

    func testThatSpecimenIsSparseAndKeepsItsControls() {
        let body = Chart.cardBody(
            windowPoints: 1, windowInstants: 1, totalInstants: 9,
            windowWord: "in the last 7 days")

        guard case .sparse(let copy) = body else {
            return XCTFail("one point cannot be plotted as a line; the card must be sparse")
        }
        XCTAssertEqual(copy.note, "One price in the last 7 days — 8 earlier prices")
    }

    func testTheSentenceItReplacedCouldNotTellTheTwoCasesApart() {
        let hasOlderHistory = Chart.sparseCopy(
            windowInstants: 1, totalInstants: 9, windowWord: "in the last 7 days")
        let hasNothing = Chart.sparseCopy(
            windowInstants: 0, totalInstants: 0, windowWord: "in the last 7 days")

        XCTAssertNotEqual(
            hasOlderHistory.note, hasNothing.note,
            "'Limited price history available' was printed over both, and they are not the same fact")
        XCTAssertNil(hasNothing.hint, "there is nowhere to send a reader whose market has no prices")
    }

    // MARK: - True zero history

    func testAMarketWithNoPricesAtAllSaysSoAndOffersNoErrand() {
        let copy = Chart.sparseCopy(
            windowInstants: 0, totalInstants: 0, windowWord: "in the last 24 hours")

        XCTAssertEqual(copy.note, "No price history yet")
        XCTAssertNil(copy.hint)
        XCTAssertFalse(
            copy.note.contains("24 hours"),
            "naming a window implies prices exist outside it")
    }

    func testZeroHistoryIsStillSparseSoTheChipsStillDraw() {
        guard case .sparse = Chart.cardBody(
            windowPoints: 0, windowInstants: 0, totalInstants: 0, windowWord: "in the last 7 days")
        else {
            return XCTFail("an empty response must not fall through to the plot branch")
        }
    }

    // MARK: - One total observation

    func testASingleObservationInsideTheWindowIsNotAnInvitationToLookElsewhere() {
        let copy = Chart.sparseCopy(
            windowInstants: 1, totalInstants: 1, windowWord: "in the last 7 days")

        XCTAssertEqual(copy.note, "Only one price seen so far")
        XCTAssertNil(copy.hint, "the one price is the one you are looking at")
    }

    func testASingleObservationOLDERThanTheWindowIsReachable() {
        let copy = Chart.sparseCopy(
            windowInstants: 0, totalInstants: 1, windowWord: "in the last 24 hours")

        XCTAssertEqual(copy.note, "No prices in the last 24 hours — one earlier price")
        XCTAssertEqual(copy.hint, "Try a longer range")
    }

    func testAnEmptyWindowOverManyPricesCountsThemAll() {
        let copy = Chart.sparseCopy(
            windowInstants: 0, totalInstants: 9, windowWord: "today")

        XCTAssertEqual(copy.note, "No prices today — 9 earlier prices")
        XCTAssertEqual(copy.hint, "Try a longer range")
    }

    // MARK: - The dense healthy control

    func testADenseMarketIsUntouchedAndStillPlots() {
        XCTAssertEqual(
            Chart.cardBody(
                windowPoints: 240, windowInstants: 80, totalInstants: 80,
                windowWord: "in the last 7 days"),
            .plot,
            "the ordinary chart must not have become a sentence")
    }

    func testTwoPointsIsTheBoundaryAndBelongsToThePlot() {
        XCTAssertEqual(
            Chart.cardBody(
                windowPoints: 2, windowInstants: 2, totalInstants: 2,
                windowWord: "in the last 7 days"),
            .plot,
            "two observations are a line, and #7077 already pins how that line is labelled")

        guard case .sparse = Chart.cardBody(
            windowPoints: 1, windowInstants: 1, totalInstants: 2,
            windowWord: "in the last 7 days")
        else { return XCTFail("one point is not a line") }
    }

    /// A multi-outcome market can reach two POINTS on one INSTANT — three outcomes
    /// priced once each is `windowPoints == 3`. That is the existing plot branch's
    /// business (it draws three dots), and this ship does not move the boundary.
    func testTheBoundaryIsCountedInPointsSoMultiOutcomeMarketsAreUnchanged() {
        XCTAssertEqual(
            Chart.cardBody(
                windowPoints: 3, windowInstants: 1, totalInstants: 1,
                windowWord: "in the last 7 days"),
            .plot)
    }

    // MARK: - Arithmetic that cannot go negative or lie

    func testMoreWindowThanTotalCannotManufactureEarlierPrices() {
        let copy = Chart.sparseCopy(
            windowInstants: 5, totalInstants: 1, windowWord: "in the last 7 days")

        XCTAssertEqual(copy.note, "Only one price seen so far")
        XCTAssertNil(copy.hint, "a negative 'earlier' count must never become an errand")
    }

    func testNegativeCountsDegradeToTheHonestSentence() {
        let copy = Chart.sparseCopy(
            windowInstants: -3, totalInstants: -9, windowWord: "in the last 7 days")

        XCTAssertEqual(copy.note, "No price history yet")
        XCTAssertNil(copy.hint)
    }

    func testTheCountIsNeverPrintedAsAWordItDoesNotHave() {
        XCTAssertEqual(
            Chart.sparseCopy(windowInstants: 0, totalInstants: 2, windowWord: "in the last 7 days").note,
            "No prices in the last 7 days — 2 earlier prices")
        XCTAssertEqual(
            Chart.sparseCopy(windowInstants: 1, totalInstants: 2, windowWord: "in the last 7 days").note,
            "One price in the last 7 days — one earlier price",
            "singular and plural are both written, so neither reads as a template")
    }

    /// 🔴 `cardBody` gates on POINTS; this sentence counts INSTANTS. They diverge —
    /// `chartEntries` emits nothing for a timeline entry whose only outcomes are
    /// `Field` (filtered) or past `topFilter` — so a sparse card CAN hold two or
    /// more instants. The first cut read `inWindow` as a ternary and called every
    /// such window "One price".
    func testAWindowHoldingSeveralPricesIsNotCalledOne() {
        let copy = Chart.sparseCopy(
            windowInstants: 3, totalInstants: 9, windowWord: "in the last 7 days")

        XCTAssertEqual(copy.note, "3 prices in the last 7 days — 6 earlier prices")
        XCTAssertEqual(copy.hint, "Try a longer range")
        XCTAssertFalse(
            copy.note.hasPrefix("One price"),
            "three observations must never be reported as one")
    }

    /// The same divergence with nothing older: the old code fell past the `earlier`
    /// guard and printed "No price history yet" over a response holding nine prices
    /// — the exact sentence #7350 exists to stop (gotcha #53).
    func testAFullWindowWithNothingOlderStillCountsWhatItHas() {
        let copy = Chart.sparseCopy(
            windowInstants: 4, totalInstants: 4, windowWord: "in the last 7 days")

        XCTAssertEqual(copy.note, "4 prices seen so far")
        XCTAssertNil(copy.hint, "there is nothing older to reach")
        XCTAssertNotEqual(
            copy.note, "No price history yet",
            "four prices are not an absence")
    }

    // MARK: - The window's own name

    func testEachChipIsNamedInASentenceAReaderCanHold() {
        XCTAssertEqual(Chart.windowWord(for: .week), "in the last 7 days")
        XCTAssertEqual(Chart.windowWord(for: .day), "in the last 24 hours")
        XCTAssertEqual(Chart.windowWord(for: .today), "today")
        XCTAssertEqual(Chart.windowWord(for: .tournament), "during this event")
    }

    func testNoWindowWordIsTheChipsOwnLabel() {
        for range in EvolutionTimeRange.allCases {
            let word = Chart.windowWord(for: range)
            XCTAssertFalse(
                word.contains(range.rawValue),
                "\(range.rawValue) reads as a chip, not as a phrase inside a sentence")
            XCTAssertFalse(
                word.contains(EvolutionRangeVocabulary.genericWidestWindow),
                "'6M' in prose is the same borrowed-vocabulary defect #7077 fixed on the chip")
        }
    }

    /// The widest range has no cutoff, so its window IS the whole response: when it
    /// is sparse there are never "earlier prices" to name, and the word is unused.
    ///
    /// The note is asserted in full, not just probed for the absent word: this case
    /// used to return "No price history yet" over NINE prices and still satisfy both
    /// checks below, so a bare `XCTAssertFalse` is exactly the guard that let it sit.
    func testTheWidestRangeNeverNeedsItsWord() {
        let copy = Chart.sparseCopy(
            windowInstants: 9, totalInstants: 9, windowWord: Chart.windowWord(for: .season))

        XCTAssertEqual(copy.note, "9 prices seen so far")
        XCTAssertFalse(copy.note.contains("in this range"))
        XCTAssertNil(copy.hint)
    }

    /// The tap-driven journey (`AReaderCanReachOlderPricesFromASparseChart7350Tests`)
    /// has to name the widest chip to press it, and its target does not link the app
    /// module — so it restates the string. This is the pin that stops the two copies
    /// drifting: change the word here and the journey goes red in this file first.
    func testTheJourneysCopyOfTheWidestChipStillMatchesTheApps() {
        XCTAssertEqual(
            EvolutionRangeVocabulary.genericWidestWindow, "6M",
            "BainLuckUITests presses a button with this exact label")
    }

    // MARK: - The seam a pure suite cannot see

    /// ⚠️ EVERY ASSERTION ABOVE MEASURES A RULE, AND THE DEFECT WAS NOT IN A RULE —
    /// it was in WHERE the control bar sat in a `@ViewBuilder`. A body returning an
    /// opaque type cannot be called, so a mutant that puts `controlBar` back inside
    /// the plot branch, or reverts the empty state to the old sentence, leaves every
    /// test above green. Same shape as #7077's own seam test, and the same answer:
    /// scan the call site, anchored on the line the reader's pixels come from, with
    /// comments stripped so the prose explaining the fix cannot satisfy it.
    func testTheCardACTUALLYDrawsTheControlsInTheSparseState() throws {
        let chart = try code(named: "Bain Luck/Components/EvolutionChartView.swift")

        // Whitespace-collapsed, so the anchor survives a re-indent but not a move:
        // what is pinned is the ORDER — the sparse case, then the stack, then the
        // chips — which is the whole of #7350.
        let flat = chart.split(whereSeparator: \.isWhitespace).joined(separator: " ")
        XCTAssertTrue(
            flat.contains("case .sparse(let copy): VStack(spacing: 0) { controlBar"),
            "the sparse card must draw the range chips — that IS #7350")
        XCTAssertTrue(
            chart.contains("emptyState(copy.note, hint: copy.hint)"),
            "…over the counted sentence, not a literal typed into the body")
        XCTAssertTrue(
            chart.contains("switch Self.cardBody("),
            "the branch must be decided by the rule this suite tests")

        XCTAssertFalse(
            chart.contains("emptyState(\"Limited price history available\")"),
            "the pre-fix state: one sentence for two facts, and no way out of it")
        XCTAssertFalse(
            chart.contains("chartEntries.count >= 2"),
            "the pre-fix branch that owned the controls")
    }

    /// The cadence line is its own defect and its own assertion: it was printed
    /// unconditionally under every non-retryable empty state, including over nine
    /// observations spread across a month. A poll schedule is not a promise, and the
    /// ban is on the CLAIM, so it is checked over the whole file with comments gone
    /// rather than at one call site.
    func testNoScreenPromisesAPriceCadenceTheDataCannotSupport() throws {
        let chart = try code(named: "Bain Luck/Components/EvolutionChartView.swift")
        let claim = try NSRegularExpression(
            pattern: #"Text\(\s*"[^"]*(update|refresh)[^"]*(hour|minute|min)"#,
            options: [.caseInsensitive])

        XCTAssertEqual(
            claim.numberOfMatches(
                in: chart, range: NSRange(chart.startIndex..., in: chart)),
            0,
            "a cadence read off the poll schedule and printed as a promise to the reader")

        for hint in [
            Chart.sparseCopy(windowInstants: 1, totalInstants: 9, windowWord: "in the last 7 days").hint,
            Chart.sparseCopy(windowInstants: 0, totalInstants: 0, windowWord: "in the last 7 days").hint,
            Chart.sparseCopy(windowInstants: 1, totalInstants: 1, windowWord: "in the last 7 days").hint,
        ] {
            guard let hint else { continue }
            XCTAssertFalse(
                hint.lowercased().contains("hour") || hint.lowercased().contains("minute"),
                "the replacement line must not smuggle the same promise back in: \(hint)")
        }
    }

    private func code(named path: String) throws -> String {
        let root = URL(fileURLWithPath: #filePath)
            .deletingLastPathComponent()      // BainLuckTests
            .deletingLastPathComponent()      // Bain Luck (project dir)
        let source = try String(
            contentsOf: root.appendingPathComponent(path), encoding: .utf8)
        let stripped = source
            .split(separator: "\n", omittingEmptySubsequences: false)
            .filter { !$0.trimmingCharacters(in: .whitespaces).hasPrefix("//") }
            .joined(separator: "\n")
        XCTAssertTrue(
            stripped.contains("struct EvolutionChartView"),
            "the comment strip left nothing to scan in \(path)")
        return stripped
    }
}
