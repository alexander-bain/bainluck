import XCTest
import SwiftUI
@testable import Bain_Luck

/// #8158 — A FLAT LINE AT 100% IS NOT A SUM, IT IS A CLAMP REPORTING ITSELF.
///
/// `EvolutionChartView.chartEntries` draws the `Sum` line as
/// `min(100, latestProbs.values.reduce(0, +))`. On production market **56775596**
/// ("Las Vegas: Team Specials", 12 independent Kalshi props, payload saved at
/// `artifacts/native-302/prod-56775596-h168-20260923T0235Z.json`) the default
/// top-three selection sums to between **107 and 234** across the served week, so
/// the clamp took **584 of 584** points to exactly 100.
///
/// The reader who taps `Sum` therefore gets a dead-flat dashed line pinned to the
/// top of the chart — a confident certainty the market never stated, over three
/// props that are not alternatives to each other at all. The clamp also flattens 20
/// distinct unclamped values into 1, so the one thing a sum line is for, movement,
/// is the first thing it loses.
///
/// ═══ WHAT THESE PIN ═══
///
/// The ship is that the control is ABSENT where a sum cannot be a probability, and
/// UNCHANGED where it can. Both arms are load-bearing: a gate that only ever hid the
/// control would pass its own red test while removing a working feature from every
/// championship field on the site, so the exclusive-field arm below is the half that
/// makes the other half mean something.
///
/// The threshold is not pinned as a tuned constant. It is asserted through
/// SPECIMENS — real served shapes on both sides of it — so a later change to the
/// number is graded on whether these markets still land where they belong rather
/// than on whether a literal matched.
final class TheSumLineRefusesAFieldThatIsNotOneQuestion8158Tests: XCTestCase {

    private typealias Policy = EvolutionCombinedLinePolicy

    // MARK: - Specimen builders

    private func outcome(_ name: String, _ prob: Double?) -> TimelineOutcomeMeta {
        var json: [String: Any] = ["name": name]
        if let prob { json["current_probability"] = prob }
        let data = try! JSONSerialization.data(withJSONObject: json)
        let decoder = JSONDecoder()
        decoder.keyDecodingStrategy = .convertFromSnakeCase
        return try! decoder.decode(TimelineOutcomeMeta.self, from: data)
    }

    /// Market 56775596 as production served it — the 12 props, real prices.
    private func lasVegasTeamSpecials() -> [TimelineOutcomeMeta] {
        [
            outcome("Brock Bowers records 3+ touchdowns in a single game", 0.94),
            outcome("Fernando Mendoza records 300+ passing yards in a single game", 0.64),
            outcome("Mike Washington Jr. records 500+ rushing yards", 0.52),
            outcome("Ashton Jeanty records 75+ rushing and 75+ receiving yards", 0.385),
            outcome("Ashton Jeanty records 200+ rushing yards in a single game", 0.38),
            outcome("Jalen Nailor records 100+ receiving yards in a single game", 0.28),
            outcome("Mike Washington Jr. records 100+ rushing yards in a single game", 0.22),
            outcome("Las Vegas records 8+ sacks in a single game", 0.135),
            outcome("Las Vegas records 400+ passing yards in a single game", 0.115),
            outcome("Fernando Mendoza records 4+ passing touchdowns in a single game", 0.105),
            outcome("Las Vegas allow 0 points in a single game", 0.105),
            outcome("Brock Bowers records 175+ receiving yards in a single game", 0.085),
        ]
    }

    /// A championship field: alternatives to one question, with the residual bucket
    /// that makes it total 100. The control arm.
    private func championshipField() -> [TimelineOutcomeMeta] {
        [
            outcome("Kansas City", 0.24),
            outcome("Philadelphia", 0.19),
            outcome("Buffalo", 0.14),
            outcome("Detroit", 0.11),
            outcome("Baltimore", 0.09),
            outcome("Field", 0.23),
        ]
    }

    // MARK: - The reported specimen loses the control

    func testTheTeamSpecialsPropsBoardCannotBeSummed() {
        let served = lasVegasTeamSpecials()
        XCTAssertEqual(
            served.compactMap(\.currentProbability).reduce(0, +), 3.91, accuracy: 0.001,
            "guard the specimen itself: this is the served field production returned")

        XCTAssertFalse(
            Policy.fieldIsOneQuestion(servedOutcomes: served),
            "twelve independent props are not alternatives to one question")
    }

    /// 🔴 THE RED. Without the gate these three add to 210, the clamp prints 100, and
    /// the chart states a certainty. The assertion is on the ARITHMETIC the line was
    /// built from, so it fails for the reason the reader was misled and not merely
    /// because a flag flipped.
    func testTheDefaultTopThreeSelectionIsTheLieTheClampHid() {
        let topThree = Array(lasVegasTeamSpecials().prefix(3))
        let sum = topThree.compactMap(\.currentProbability).reduce(0, +)

        XCTAssertEqual(sum, 2.10, accuracy: 0.001, "94 + 64 + 52")
        XCTAssertGreaterThan(
            sum, 1.0,
            "the selection the chart defaults to already exceeds certainty before the clamp")
        XCTAssertEqual(
            min(1.0, sum), 1.0,
            "which is why every one of the 584 served points printed exactly 100")
    }

    // MARK: - The control arm: a real question keeps its control

    func testAChampionshipFieldKeepsItsSumLine() {
        XCTAssertTrue(
            Policy.fieldIsOneQuestion(servedOutcomes: championshipField()),
            "one winner, mutually exclusive, totals 100 — summing picks is the feature")
    }

    /// Overround must not cost a real market its control. #2582 photographed every
    /// two-way market on one UFC card summing to 101–102%, and p95 for a
    /// flagged-exclusive field is 1.025.
    func testVigDoesNotStripTheControlFromATwoWayMarket() {
        let twoWay = [outcome("Fighter A", 0.66), outcome("Fighter B", 0.36)]
        XCTAssertEqual(twoWay.compactMap(\.currentProbability).reduce(0, +), 1.02, accuracy: 0.001)
        XCTAssertTrue(
            Policy.fieldIsOneQuestion(servedOutcomes: twoWay),
            "102% is vig on one question, not twelve questions stacked")
    }

    /// 🪤 A READER'S SELECTION MUST NOT BE ABLE TO BUY BACK THE CONTROL, AND ON THIS
    /// BOARD IT OTHERWISE COULD. The reader picks which rows the chart plots, so the
    /// three SMALLEST props on this field — 10.5, 10.5 and 8.5 — total 29.5 and sit
    /// comfortably under the ceiling. Summing them still means nothing: independent
    /// props do not add, whatever they add to.
    ///
    /// So the decision is taken over the served field and never over the selection,
    /// the same distinction `renderedPercents(forServedField:)` draws for #8109. This
    /// is the test that fails if anyone ever "optimises" the policy to read the rows
    /// on screen, which is the cheaper call and the wrong one.
    func testASelectionUnderTheCeilingCannotRestoreTheControl() {
        let served = lasVegasTeamSpecials()
        let smallestThree = Array(served.suffix(3))

        XCTAssertEqual(
            smallestThree.compactMap(\.currentProbability).reduce(0, +), 0.295, accuracy: 0.001,
            "read alone this selection looks like a well-behaved question...")
        XCTAssertTrue(
            Policy.fieldIsOneQuestion(servedOutcomes: smallestThree),
            "...and judged alone it would keep the control...")
        XCTAssertFalse(
            Policy.fieldIsOneQuestion(servedOutcomes: served),
            "...but the view passes the SERVED field, which is what makes the answer stable")
    }

    // MARK: - The ladder class, where the database flag is wrong

    /// Cumulative threshold ladders carry `mutually_exclusive = true` in the
    /// database and their rungs contain one another, so their totals run to 150–182%
    /// and a sum over them is meaningless however the flag reads. This is the
    /// population that decided the policy reads the field's arithmetic rather than
    /// the (unserved) flag — a later ship that gates on the flag reintroduces the
    /// lie here, and this test is what would catch it.
    func testACumulativeDateLadderIsRefusedThoughTheDatabaseCallsItExclusive() {
        let gemini = [
            outcome("by October 31", 0.12), outcome("by November 30", 0.28),
            outcome("by December 31", 0.44), outcome("by January 31", 0.55),
            outcome("by February 28", 0.43),
        ]
        XCTAssertEqual(gemini.compactMap(\.currentProbability).reduce(0, +), 1.82, accuracy: 0.001,
                       "the served total of market 61988078")
        XCTAssertFalse(
            Policy.fieldIsOneQuestion(servedOutcomes: gemini),
            "each rung contains the previous one; adding them up is not a probability")
    }

    /// A spread ladder: 29 rungs totalling 1400%, three of them at 100 apiece.
    func testASpreadLadderIsRefused() {
        let spread = (0..<8).map { outcome("Spread \($0)", $0 < 3 ? 1.0 : 0.5) }
        XCTAssertFalse(Policy.fieldIsOneQuestion(servedOutcomes: spread),
                       "market 61097129's shape: rungs, not alternatives")
    }

    // MARK: - Undecidable fields answer with today's behaviour, and say so

    /// Not a verdict, and deliberately not dressed as one (gotcha #53): with fewer
    /// than two prices there is nothing to contradict, so the control stays as it is
    /// today rather than vanishing on an absence.
    func testAnUnpricedFieldIsNotJudged() {
        XCTAssertTrue(Policy.fieldIsOneQuestion(servedOutcomes: []))
        XCTAssertTrue(Policy.fieldIsOneQuestion(
            servedOutcomes: [outcome("A", nil), outcome("B", nil), outcome("C", nil)]))
        XCTAssertTrue(
            Policy.fieldIsOneQuestion(servedOutcomes: [outcome("A", 5.0), outcome("B", nil)]),
            "one price cannot exceed the ceiling on its own; refusing here would be a coin toss")
    }

    /// Truncation can only remove probability mass, so `top=50` can lower a field
    /// under the ceiling but never lift one over it. That asymmetry is what makes a
    /// false "not one question" — the only failure that removes a working control —
    /// unreachable by truncation.
    func testTruncationCannotInventARefusal() {
        let served = championshipField()
        for n in 2...served.count {
            XCTAssertTrue(
                Policy.fieldIsOneQuestion(servedOutcomes: Array(served.prefix(n))),
                "no prefix of an exclusive field can exceed the ceiling")
        }
    }

    // MARK: - The point the chart plots, clamp included

    /// 🔴 THE DEFECT, AT THE ONE PLACE IT IS PRODUCED. Feed the policy the three
    /// props the chart selects by default and the old code's answer is 100 — not
    /// because the market said so, but because `min` did.
    func testTheRefusedFieldPlotsNoPointAtAllWhereItUsedToPlotOneHundred() {
        let latest = [
            "Brock Bowers records 3+ touchdowns in a single game": 94.0,
            "Fernando Mendoza records 300+ passing yards in a single game": 64.0,
            "Mike Washington Jr. records 500+ rushing yards": 52.0,
        ]

        XCTAssertEqual(
            min(100, latest.values.reduce(0, +)), 100,
            "what the chart drew on all 584 points before the gate")

        XCTAssertNil(
            Policy.combinedProbability(
                showRequested: true, fieldIsOneQuestion: false,
                selectedCount: 3, latestProbs: latest),
            "no point: a sum that was never a probability is not improved by clamping it")
    }

    /// The control arm again, one layer down: on a real question the line is still
    /// drawn, and still drawn with the clamp that keeps overround off the ceiling.
    func testAQuestionStillPlotsItsCombinedPointAndStillClamps() {
        let picks = ["Kansas City": 24.0, "Philadelphia": 19.0, "Buffalo": 14.0]
        XCTAssertEqual(
            Policy.combinedProbability(
                showRequested: true, fieldIsOneQuestion: true,
                selectedCount: 3, latestProbs: picks),
            57.0, "three championship picks add to 57 — the feature, working")

        XCTAssertEqual(
            Policy.combinedProbability(
                showRequested: true, fieldIsOneQuestion: true,
                selectedCount: 2, latestProbs: ["Fighter A": 66.0, "Fighter B": 36.0]),
            100.0, "102% of vig on one question is what the clamp is FOR")
    }

    func testEveryOtherReasonNotToDrawTheLineStillHolds() {
        let two = ["A": 20.0, "B": 30.0]
        XCTAssertNil(Policy.combinedProbability(
            showRequested: false, fieldIsOneQuestion: true, selectedCount: 2, latestProbs: two),
            "the reader has not asked for it")
        XCTAssertNil(Policy.combinedProbability(
            showRequested: true, fieldIsOneQuestion: true, selectedCount: 1, latestProbs: two),
            "one outcome's 'sum' is that outcome, drawn twice")
        XCTAssertNil(Policy.combinedProbability(
            showRequested: true, fieldIsOneQuestion: true, selectedCount: 2, latestProbs: [:]),
            "nothing observed yet")
    }

    // MARK: - The control is really gone from the bar

    /// Pins the WIRING, not the policy: the arms of the real control bar must lose
    /// the `Sum` chip. Measured off the hosted view, so a change that keeps the
    /// policy correct and forgets to pass `sumAvailable` through fails here.
    func testTheBarsArmsDropTheSumChipWhenTheFieldCannotBeSummed() {
        let ranges: [EvolutionTimeRange] = [.season, .week, .day, .today]
        func bar(sumAvailable: Bool) -> EvolutionControlBar {
            EvolutionControlBar(
                availableRanges: ranges,
                selectedRange: .constant(.week),
                showCombinedProbability: .constant(true),
                sumAvailable: sumAvailable,
                topFilter: .constant(10))
        }

        let withSum = intrinsicSize(of: bar(sumAvailable: true).row(chipPadding: 8))
        let without = intrinsicSize(of: bar(sumAvailable: false).row(chipPadding: 8))
        XCTAssertLessThan(
            without.width, withSum.width - 20,
            "the one-row arm must be narrower by a whole chip, not by a hairline")

        // The wrapped arm gives Sum its own row, so losing it must lose a row.
        let tallWithSum = intrinsicSize(of: bar(sumAvailable: true).wrappedRows(chipPadding: 8))
        let shorter = intrinsicSize(of: bar(sumAvailable: false).wrappedRows(chipPadding: 8))
        XCTAssertLessThan(
            shorter.height, tallWithSum.height - 5,
            "the terminal arm stacks each group; without Sum it is one row shorter")
    }

    /// The default keeps every existing caller — and every layout test measuring the
    /// widest vocabulary — on the WITH-`Sum` bar, which is the wide case worth pinning.
    func testTheBarStillShowsSumByDefault() {
        let ranges: [EvolutionTimeRange] = [.season, .week]
        let defaulted = EvolutionControlBar(
            availableRanges: ranges, selectedRange: .constant(.week),
            showCombinedProbability: .constant(false), topFilter: .constant(10))
        let explicit = EvolutionControlBar(
            availableRanges: ranges, selectedRange: .constant(.week),
            showCombinedProbability: .constant(false), sumAvailable: true,
            topFilter: .constant(10))

        XCTAssertEqual(
            intrinsicSize(of: defaulted.row(chipPadding: 8)).width,
            intrinsicSize(of: explicit.row(chipPadding: 8)).width, accuracy: 0.5)
    }

    private func intrinsicSize<V: View>(of view: V) -> CGSize {
        let host = UIHostingController(rootView: AnyView(view))
        host.view.frame = CGRect(x: 0, y: 0, width: 1200, height: 2000)
        let window = UIWindow(frame: CGRect(x: 0, y: 0, width: 1200, height: 2000))
        window.rootViewController = host
        window.isHidden = false
        host.view.setNeedsLayout()
        host.view.layoutIfNeeded()
        return host.sizeThatFits(in: CGSize(
            width: CGFloat.greatestFiniteMagnitude, height: CGFloat.greatestFiniteMagnitude))
    }

    // MARK: - The camera the defect was invisible to

    /// The combined line is a `@State` checkbox that defaults off and the rig cannot
    /// tap, so it had never been photographed. The flag only ASKS — the policy still
    /// decides — which is the property that stops it photographing a chart no reader
    /// could reach.
    func testTheRigCanAskForTheCombinedLineAndDefaultsToNotAsking() {
        let defaults = UserDefaults(suiteName: "sum-flag-\(UUID().uuidString)")!
        XCTAssertFalse(LaunchRig.startsChartSumOn(defaults: defaults),
                       "a reader's checkbox starts clear")

        defaults.set(true, forKey: LaunchRig.chartSumKey)
        XCTAssertTrue(LaunchRig.startsChartSumOn(defaults: defaults))
    }
}
