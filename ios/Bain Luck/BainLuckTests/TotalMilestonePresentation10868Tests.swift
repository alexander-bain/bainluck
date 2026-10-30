import SwiftUI
import XCTest
@testable import Bain_Luck

/// #10868 — a game total's milestone chances as one stateless, sport-neutral
/// profile across pregame, live and final.
///
/// The view is SwiftUI and is not rasterised here. What is asserted is the
/// rules it defers to: which readings each phase shows, the exact-id
/// selection, the action each control carries, the timing it may show, the
/// quantity domain, the plot model, the label planning and the spoken text.
/// Nothing here claims a rendered fit.
///
/// ARCHIVED raw values come from Minnesota–Boston, event 15169793, market
/// 63539066, as copied in `shipping-adoption-20261027/TOTAL-GOALS-RETAINED-CASES.json`
/// (sha256 14d0c9d6…c6daab6d). Keys are `nhl-15169793-game-markets.json:totals:0…8`;
/// coordinates 2…10 are the owner's conversion of original Over 1.5…9.5.
///   pregame (prototype before record, all @ 2026-10-03T23:54:43.297293Z):
///     2+ 0.98 · 3+ 0.975 · 4+ 0.87 · 5+ 0.795 · 6+ 0.585 · 7+ 0.475 ·
///     8+ 0.265 · 9+ 0.18 · 10+ 0.085
///   stage "Late second period" 2026-10-04T01:45:25Z, 2–1 (3 goals), 4:09 left;
///     6+ reading 0.465 @ 01:26:57.585124Z
///   stage "Early third period" 02:14:50Z, 3–1 (4 goals), 16:36 left;
///     retained readings before it @ 02:12:43.340805Z
///   stage "Third period · probabilities updated" 02:16:52Z, 3–1 (4 goals),
///     14:34 left; readings @ 02:16:43.377040Z: 2+/3+/4+ 0.995 · 5+ 0.925 ·
///     6+ 0.565 · 7+ 0.34 · 8+ 0.145 · 9+ 0.075 · 10+ 0.05
///   final Minnesota 4–1 Boston, 5 goals, observed 05:59:38.451734Z;
///     original results true for 2…5, false for 6…10; original settled
///     over_probability 1.0 / 0.0 (not a chance).
///
/// CONSTRUCTED owner inputs (this leaf does not resolve them): every display
/// string, PT clock and time/source line; the threshold → count coordinates;
/// titles and labels; result words; count units, clocks and rule labels; the
/// movement and performance strings; ticks and domains; which stage reading the
/// owner admits; the reached/withheld/unavailable states; the projection (this
/// hockey record has none qualified); and the malformed, duplicate,
/// out-of-range, arbitrary-quantity and crowded cases. Checkpoints are
/// reconstructed archive evidence, not proof of historical app arrival.
final class TotalMilestonePresentation10868Tests: XCTestCase {

    // MARK: Fixtures

    private static func key(_ index: Int) -> String { "nhl-15169793-game-markets.json:totals:\(index)" }

    private static func obs(_ probability: Double, _ text: String, _ time: String?, _ detail: String) -> TotalMilestoneObservation10868 {
        TotalMilestoneObservation10868(probability: probability, text: text, timeText: time, accessibilityDetail: detail)
    }

    /// ARCHIVED pregame values (prototype before record), CONSTRUCTED text.
    private static let pregame: [(Double, String)] = [
        (0.98, "98%"), (0.975, "97.5%"), (0.87, "87%"), (0.795, "79.5%"), (0.585, "58.5%"),
        (0.475, "47.5%"), (0.265, "26.5%"), (0.18, "18%"), (0.085, "8.5%"),
    ]
    private static let pregameDetail = "Oct 3, 4:54 PM PT · Kalshi"

    /// ARCHIVED readings @ 02:16:43Z (7:16 PM PT), CONSTRUCTED text.
    private static let updated: [(Double, String)] = [
        (0.995, "99.5%"), (0.995, "99.5%"), (0.995, "99.5%"), (0.925, "92.5%"), (0.565, "56.5%"),
        (0.34, "34%"), (0.145, "14.5%"), (0.075, "7.5%"), (0.05, "5%"),
    ]
    private static let updatedDetail = "Oct 3, 7:16 PM PT · Kalshi consensus"

    private static let noReading = TotalMilestoneCurrent10868.unavailable("No in-game reading")
    private static let pending = TotalMilestoneResult10868.unconfirmed("Result unconfirmed")

    private static func row(
        _ index: Int,
        before: TotalMilestoneObservation10868?? = nil,
        current: TotalMilestoneCurrent10868 = noReading,
        performance: String? = nil,
        result: TotalMilestoneResult10868 = pending,
        quantity: Double? = nil,
        id: String? = nil
    ) -> TotalMilestoneRow10868 {
        let count = index + 2
        let saved = pregame[index]
        return TotalMilestoneRow10868(
            id: id ?? key(index),
            quantity: quantity ?? Double(count),
            quantityLabel: "\(count)+",
            title: "\(count)+ goals",
            before: before ?? obs(saved.0, saved.1, "4:54 PM", pregameDetail),
            beforeMissing: "Unavailable",
            current: current,
            performance: performance,
            result: result
        )
    }

    private static let chanceTicks = [
        TotalMilestoneTick10868(value: 0, text: "0%"),
        TotalMilestoneTick10868(value: 0.5, text: "50%"),
        TotalMilestoneTick10868(value: 1, text: "100%"),
    ]
    private static let goalTicks = [2.0, 4, 6, 8, 10].map { TotalMilestoneTick10868(value: $0, text: "\(Int($0))") }

    private static func input(
        _ phase: TotalMilestonePhase10868,
        _ milestones: [TotalMilestoneRow10868],
        selected: String? = key(4),
        actual: TotalMilestoneActual10868? = nil,
        projection: TotalMilestoneProjection10868? = nil,
        domain: TotalMilestoneDomain10868? = nil,
        quantityTicks: [TotalMilestoneTick10868] = goalTicks,
        timing: TotalMilestoneTiming10868? = nil
    ) -> TotalMilestoneInput10868 {
        TotalMilestoneInput10868(
            phase: phase,
            eyebrow: "TOTAL GOALS · BOTH TEAMS",
            title: phase == .final ? "How many goals felt likely?" : "Room for more goals?",
            chartTitle: "Chance of reaching each total",
            quantityAxisTitle: "Total goals in the game",
            milestones: milestones,
            selectedMilestoneID: selected,
            actual: actual,
            projection: projection,
            quantityDomain: domain,
            quantityTicks: quantityTicks,
            chanceTicks: chanceTicks,
            timing: timing
        )
    }

    private static func count(_ value: Double, _ text: String, clock: String?, rule: String?, detail: String) -> TotalMilestoneActual10868 {
        .count(TotalMilestoneCount10868(quantity: value, text: text, unit: "goals", clock: clock, ruleLabel: rule,
                                        accessibilityDetail: detail))
    }

    /// Stage "Third period · probabilities updated": 3–1, 4 goals, 14:34 left.
    private static let fourSoFar = count(4, "4", clock: "3rd · 14:34 left", rule: "4 so far",
                                         detail: "as of 7:16 PM PT, 3rd period, 14:34 left · ESPN")
    /// Final 4–1, 5 goals, observed 10:59 PM PT.
    private static let finalFive = count(5, "5", clock: "Final · 10:59 PM", rule: "5 final",
                                         detail: "final score observed Oct 3, 10:59 PM PT · ESPN")

    /// Every pregame mark, plus the owner's later inputs that must stay hidden before play.
    private static var allSupplied: [TotalMilestoneRow10868] {
        (0..<9).map { i in
            row(i,
                current: .recorded(obs(updated[i].0, updated[i].1, "7:16 PM", updatedDetail), movement: "Movement"),
                performance: "Performance",
                result: i <= 3 ? .reached("Reached") : .missed("Missed"))
        }
    }

    /// The owner's admission at the 02:16:52Z stage: 2+…4+ reached by the
    /// count, 5+…10+ recorded at 02:16:43Z.
    private static var updatedStage: [TotalMilestoneRow10868] {
        (0..<9).map { i in
            if i <= 2 { return row(i, current: .reached("Reached")) }
            let movement = i == 4 ? "−2 percentage points since pregame" : nil
            return row(i, current: .recorded(obs(updated[i].0, updated[i].1, "7:16 PM", updatedDetail), movement: movement),
                       performance: i == 4 ? "2 more needed" : nil)
        }
    }

    /// Final: original results (2…5 true, 6…10 false); settled 1.0/0.0 supplied as a "current" to prove it is ignored.
    private static var finalRows: [TotalMilestoneRow10868] {
        (0..<9).map { i in
            let settled = i <= 3 ? 1.0 : 0.0
            return row(i,
                       current: .recorded(obs(settled, settled == 1 ? "100%" : "0%", "Settled", "settled"), movement: nil),
                       performance: i == 4 ? "Finished 1 short" : nil,
                       result: i <= 3 ? .reached("Reached") : .missed("Missed"))
        }
    }

    private static let size = CGSize(width: 300, height: 180)
    private static let inset = TotalMilestoneGeometry10868.plotInset

    // MARK: Before

    func testBeforeShowsOnlyPregameChancesAndHidesEverythingLater() {
        let input = Self.input(.before, Self.allSupplied, actual: Self.finalFive,
                               projection: Self.projection(5.8))
        let selected = try! XCTUnwrap(input.selection.milestone)
        XCTAssertEqual(input.beforeReading(selected), .value(Self.obs(0.585, "58.5%", "4:54 PM", Self.pregameDetail)))
        XCTAssertNil(input.secondReading(selected))
        XCTAssertNil(input.currentReading(selected))
        XCTAssertNil(input.movement(selected))
        XCTAssertNil(input.performance(selected))
        XCTAssertNil(input.result(selected))
        XCTAssertNil(input.actualPresentation, "no count before play, and no invented zero")
        XCTAssertNil(input.visibleActualQuantity)
        XCTAssertNil(input.visibleProjection)
        XCTAssertEqual(input.annotations.map(\.kind), [.selection])
        let model = try! XCTUnwrap(input.plotModel(size: Self.size, inset: Self.inset))
        XCTAssertEqual(model.marks.count, 9)
        XCTAssertTrue(model.marks.allSatisfy { $0.kind == .pregame })
        XCTAssertNil(model.actualX)
        XCTAssertNil(model.projectionX)
        XCTAssertFalse(input.accessibilityComparison(for: selected).contains("Movement"))
        XCTAssertFalse(input.accessibilityComparison(for: selected).contains("Reached"))
    }

    func testBeforeKeepsOwnerOrderAndPosition() {
        let input = Self.input(.before, (0..<9).map { Self.row($0) })
        XCTAssertEqual(input.milestones.map(\.id), (0..<9).map(Self.key))
        XCTAssertEqual(input.selection.index, 4)
        XCTAssertEqual(input.positionText, "6+ · 5 of 9")
        XCTAssertEqual(input.domain, TotalMilestoneDomain10868(lower: 2, upper: 10))
    }

    // MARK: During

    func testDuringSeparatesBaselineCurrentCountAndResult() {
        let rows = Self.updatedStage.enumerated().map { i, row in
            TotalMilestoneRow10868(id: row.id, quantity: row.quantity, quantityLabel: row.quantityLabel, title: row.title,
                                   before: row.before, beforeMissing: row.beforeMissing, current: row.current,
                                   performance: row.performance, result: i <= 3 ? .reached("Reached") : .missed("Missed"))
        }
        let input = Self.input(.during, rows, actual: Self.fourSoFar)
        let six = try! XCTUnwrap(input.selection.milestone)
        XCTAssertEqual(input.beforeReading(six), .value(Self.obs(0.585, "58.5%", "4:54 PM", Self.pregameDetail)))
        XCTAssertEqual(input.secondReading(six), .current(.chance(Self.obs(0.565, "56.5%", "7:16 PM", Self.updatedDetail))))
        XCTAssertEqual(input.movement(six), "−2 percentage points since pregame")
        XCTAssertEqual(input.performance(six), "2 more needed")
        XCTAssertNil(input.result(six), "a supplied result is not shown during play")
        XCTAssertEqual(input.actualPresentation?.title, "Count so far")
        XCTAssertEqual(input.visibleActualQuantity, 4)
        XCTAssertEqual(input.annotations.map(\.kind), [.selection, .actual])
        XCTAssertEqual(input.annotations.last?.text, "4 so far")

        let model = try! XCTUnwrap(input.plotModel(size: Self.size, inset: Self.inset))
        let sixMarks = model.marks.filter { $0.index == 4 }
        XCTAssertEqual(sixMarks.map(\.kind), [.pregame, .current])
        XCTAssertTrue(sixMarks.allSatisfy(\.selected))
        XCTAssertEqual(sixMarks[0].point.x, sixMarks[1].point.x, "both marks sit on the same quantity")
        XCTAssertEqual(model.actualX, model.marks.first { $0.index == 2 }?.point.x, "the count rule sits on the quantity axis at 4")
    }

    func testDuringReadingAndCountKeepTheirOwnClocks() {
        // Stage "Late second period" 01:45:25Z (6:45 PM PT), 3 goals; owner admits the 01:26:57Z (6:26 PM PT) 6+ reading.
        let reading = Self.obs(0.465, "46.5%", "6:26 PM", "Oct 3, 6:26 PM PT · Kalshi consensus")
        let rows = (0..<9).map { i in Self.row(i, current: i == 4 ? .recorded(reading, movement: nil) : Self.noReading) }
        let three = Self.count(3, "3", clock: "2nd · 4:09 left", rule: "3 so far",
                               detail: "as of 6:45 PM PT, 2nd period, 4:09 left · ESPN")
        let input = Self.input(.during, rows, actual: three)
        let six = try! XCTUnwrap(input.selection.milestone)
        let comparison = input.accessibilityComparison(for: six)
        XCTAssertTrue(comparison.contains("Recorded in-game chance: 46.5%, Oct 3, 6:26 PM PT"))
        XCTAssertTrue(comparison.contains("Pregame chance: 58.5%, Oct 3, 4:54 PM PT"))
        XCTAssertFalse(comparison.contains("6:45"))
        let actual = input.accessibilityActual(try! XCTUnwrap(input.actualPresentation))
        XCTAssertEqual(actual, "3 goals, as of 6:45 PM PT, 2nd period, 4:09 left · ESPN")
        XCTAssertFalse(actual.contains("6:26"))
        guard case .count(let count)? = input.actual else { return XCTFail("count expected") }
        XCTAssertEqual(count.clock, "2nd · 4:09 left")
        XCTAssertEqual(reading.timeText, "6:26 PM")
    }

    func testReachedReadsAsActualSoFarNotAChanceOr100() {
        let input = Self.input(.during, Self.updatedStage, selected: Self.key(2), actual: Self.fourSoFar)
        let four = try! XCTUnwrap(input.selection.milestone)
        XCTAssertEqual(input.currentReading(four), .actual("Reached"))
        XCTAssertEqual(input.currentReading(four)?.title, "Actual so far")
        XCTAssertNil(input.currentFraction(four))
        XCTAssertFalse(input.showsCurrentKey(four))
        let model = try! XCTUnwrap(input.plotModel(size: Self.size, inset: Self.inset))
        XCTAssertEqual(model.marks.filter { $0.index == 2 }.map(\.kind), [.pregame])
        let spoken = input.accessibilityComparison(for: four)
        XCTAssertTrue(spoken.contains("Actual so far: Reached"))
        XCTAssertFalse(spoken.contains("100%"))
        XCTAssertNil(input.result(four))
    }

    func testWithheldAndUnavailableKeepOwnerWordsAndDrawNoMark() {
        // Stage "Early third period" 02:14:50Z: the owner withholds the 02:12:43Z readings after the goal.
        let rows = (0..<9).map { i -> TotalMilestoneRow10868 in
            if i <= 2 { return Self.row(i, current: .reached("Reached")) }
            if i == 8 { return Self.row(i, current: .unavailable("No in-game reading")) }
            return Self.row(i, current: .withheld("No update since goal"))
        }
        let four = Self.count(4, "4", clock: "3rd · 16:36 left", rule: "4 so far", detail: "as of 7:14 PM PT, 3rd period, 16:36 left · ESPN")
        let input = Self.input(.during, rows, actual: four)
        let six = try! XCTUnwrap(input.selection.milestone)
        XCTAssertEqual(input.currentReading(six), .chanceStatus("No update since goal"))
        XCTAssertEqual(input.currentReading(six)?.title, "In-game chance")
        XCTAssertNil(input.movement(six))
        XCTAssertEqual(input.currentReading(rows[8]), .chanceStatus("No in-game reading"))
        let model = try! XCTUnwrap(input.plotModel(size: Self.size, inset: Self.inset))
        XCTAssertTrue(model.marks.allSatisfy { $0.kind == .pregame })
        XCTAssertTrue(input.showsChartKey == false, "no filled marks, so no filled key")
        XCTAssertTrue(input.accessibilityComparison(for: six).contains("In-game chance: No update since goal"))
    }

    func testCountUnavailableIsWordsNeverZero() {
        let input = Self.input(.during, Self.updatedStage, actual: .unavailable("Count unavailable"))
        XCTAssertEqual(input.actualPresentation?.actual, .unavailable("Count unavailable"))
        XCTAssertNil(input.visibleActualQuantity)
        XCTAssertFalse(input.annotations.contains { $0.kind == .actual })
        XCTAssertEqual(input.accessibilityActual(try! XCTUnwrap(input.actualPresentation)), "Count unavailable")
        XCTAssertNil(input.plotModel(size: Self.size, inset: Self.inset)?.actualX)
    }

    func testChartKeyOnlyWhenTheComparisonLacksTheFilledKey() {
        let recorded = Self.input(.during, Self.updatedStage, selected: Self.key(4), actual: Self.fourSoFar)
        XCTAssertFalse(recorded.showsChartKey)
        let reached = Self.input(.during, Self.updatedStage, selected: Self.key(0), actual: Self.fourSoFar)
        XCTAssertTrue(reached.showsChartKey)
        XCTAssertEqual(reached.chartKey, Self.bothKeys, "a selection without a recorded reading leaves the filled marks unnamed")
        XCTAssertFalse(Self.input(.before, Self.allSupplied).showsChartKey)
    }

    // MARK: Chart key (Design R2)

    private static let pregameKey = TotalMilestoneChartKey10868(pregame: true, recorded: false)
    private static let recordedKey = TotalMilestoneChartKey10868(pregame: false, recorded: true)
    private static let bothKeys = TotalMilestoneChartKey10868(pregame: true, recorded: true)
    private static let missingID = "nhl-15169793-game-markets.json:totals:99"

    /// The same rows under no, a missing and a duplicated selection. The
    /// duplicate appends a second row carrying key(4).
    private static func unresolved(
        _ phase: TotalMilestonePhase10868,
        _ rows: [TotalMilestoneRow10868],
        actual: TotalMilestoneActual10868? = nil
    ) -> [(name: String, input: TotalMilestoneInput10868)] {
        var duplicated = rows
        duplicated.append(rows[4])
        return [
            ("nil", input(phase, rows, selected: nil, actual: actual)),
            ("missing", input(phase, rows, selected: missingID, actual: actual)),
            ("duplicate", input(phase, duplicated, selected: key(4), actual: actual)),
        ]
    }

    func testBeforeWithoutAResolvedSelectionStillNamesTheHollowMarks() {
        let rows = (0..<9).map { Self.row($0) }
        for (name, input) in Self.unresolved(.before, rows) {
            XCTAssertNil(input.selection.milestone, name)
            XCTAssertTrue(input.drawsPregameMarks, name)
            XCTAssertFalse(input.drawsCurrentMarks, name)
            XCTAssertEqual(input.chartKey, Self.pregameKey, name)
            XCTAssertGreaterThanOrEqual(input.milestones.count, 9, "\(name): every original row stays")
        }
        XCTAssertNil(Self.input(.before, rows).chartKey, "a valid selection's ringed mark already names the series")
    }

    func testFinalWithoutAResolvedSelectionStillNamesTheHollowMarks() {
        // Design's specimen: finalRows, selected nil, final count 5.
        for (name, input) in Self.unresolved(.final, Self.finalRows, actual: Self.finalFive) {
            XCTAssertNil(input.selection.milestone, name)
            XCTAssertEqual(input.chartKey, Self.pregameKey, "\(name): the settled 1.0/0.0 is never a filled key")
            XCTAssertEqual(input.actualPresentation?.title, "Final count", name)
            let model = try! XCTUnwrap(input.plotModel(size: Self.size, inset: Self.inset), name)
            XCTAssertTrue(model.marks.allSatisfy { $0.kind == .pregame }, name)
            XCTAssertFalse(model.marks.contains(where: \.selected), name)
        }
        XCTAssertNil(Self.input(.final, Self.finalRows, actual: Self.finalFive).chartKey,
                     "the valid compact comparison is unchanged")
    }

    func testDuringWithoutAResolvedSelectionNamesBothDrawnSeries() {
        for (name, input) in Self.unresolved(.during, Self.updatedStage, actual: Self.fourSoFar) {
            XCTAssertNil(input.selection.milestone, name)
            XCTAssertTrue(input.drawsPregameMarks && input.drawsCurrentMarks, name)
            XCTAssertEqual(input.chartKey, Self.bothKeys, name)
        }
    }

    func testDuringPregameOnlyNamesOnlyTheHollowMarks() {
        // Stage "Early third period": every in-game reading withheld, unavailable or reached.
        let rows = (0..<9).map { i -> TotalMilestoneRow10868 in
            if i <= 2 { return Self.row(i, current: .reached("Reached")) }
            if i == 8 { return Self.row(i, current: .unavailable("No in-game reading")) }
            return Self.row(i, current: .withheld("No update since goal"))
        }
        for (name, input) in Self.unresolved(.during, rows, actual: Self.fourSoFar) {
            XCTAssertFalse(input.drawsCurrentMarks, name)
            XCTAssertEqual(input.chartKey, Self.pregameKey, "\(name): no filled key without filled marks")
        }
        XCTAssertNil(Self.input(.during, rows, actual: Self.fourSoFar).chartKey,
                     "the comparison's own hollow key already names the series")
    }

    func testDuringCurrentOnlyNamesOnlyTheFilledMarks() {
        // CONSTRUCTED: no pregame price at all; 5+…10+ recorded at 02:16:43Z.
        let rows = (0..<9).map { i -> TotalMilestoneRow10868 in
            let current: TotalMilestoneCurrent10868 = i <= 2
                ? .reached("Reached")
                : .recorded(Self.obs(Self.updated[i].0, Self.updated[i].1, "7:16 PM", Self.updatedDetail), movement: nil)
            return Self.row(i, before: .some(nil), current: current)
        }
        for (name, input) in Self.unresolved(.during, rows, actual: Self.fourSoFar) {
            XCTAssertFalse(input.drawsPregameMarks, name)
            XCTAssertTrue(input.drawsCurrentMarks, name)
            XCTAssertEqual(input.chartKey, Self.recordedKey, "\(name): no hollow key without hollow marks")
        }
        XCTAssertNil(Self.input(.during, rows, actual: Self.fourSoFar).chartKey, "6+ is recorded, so its comparison names it")
        XCTAssertEqual(Self.input(.during, rows, selected: Self.key(0), actual: Self.fourSoFar).chartKey, Self.recordedKey,
                       "a reached selection names no filled mark")
        let spoken = Self.input(.during, rows, selected: nil, actual: Self.fourSoFar).accessibilityChartLabel
        XCTAssertFalse(spoken.contains("Hollow"))
        XCTAssertTrue(spoken.contains("Filled marks are recorded in-game chances."))
    }

    func testMixedDrawnSeriesWithASelectionMissingItsOwnMark() {
        // Before: the selected 6+ has no pregame price, so no ring names the hollow series.
        var rows = (0..<9).map { Self.row($0) }
        rows[4] = Self.row(4, before: .some(nil))
        XCTAssertEqual(Self.input(.before, rows).chartKey, Self.pregameKey)
        // Before: the selected row's quantity is undrawable, so no ring either.
        var invalid = (0..<9).map { Self.row($0) }
        invalid[4] = Self.row(4, quantity: -1)
        XCTAssertEqual(Self.input(.before, invalid).chartKey, Self.pregameKey)
        // During: filled marks drawn elsewhere, the selected 6+ only withheld.
        var mixed = Self.updatedStage
        mixed[4] = Self.row(4, current: .withheld("No update since goal"))
        let input = Self.input(.during, mixed, actual: Self.fourSoFar)
        XCTAssertNotNil(input.selection.milestone)
        XCTAssertEqual(input.chartKey, Self.bothKeys)
    }

    func testQuantityStripHasNoChanceKey() {
        let noChance = (0..<9).map { Self.row($0, before: .some(nil), result: $0 <= 3 ? .reached("Reached") : .missed("Missed")) }
        for phase in [TotalMilestonePhase10868.before, .during, .final] {
            var cases = Self.unresolved(phase, noChance, actual: Self.finalFive)
            cases.append((name: "valid", input: Self.input(phase, noChance)))
            for (name, input) in cases {
                XCTAssertTrue(input.isQuantityStrip, "\(phase) \(name)")
                XCTAssertNil(input.chartKey, "\(phase) \(name)")
            }
        }
    }

    // MARK: Final

    func testFinalSixPlusBaselineAgainstFiveAndMissed() {
        let input = Self.input(.final, Self.finalRows, actual: Self.finalFive)
        let six = try! XCTUnwrap(input.selection.milestone)
        XCTAssertEqual(input.beforeReading(six), .value(Self.obs(0.585, "58.5%", "4:54 PM", Self.pregameDetail)))
        XCTAssertEqual(input.secondReading(six), .result(.missed("Missed")))
        XCTAssertEqual(input.performance(six), "Finished 1 short")
        XCTAssertEqual(input.actualPresentation?.title, "Final count")
        XCTAssertEqual(input.visibleActualQuantity, 5)
        XCTAssertEqual(input.annotations.first { $0.kind == .actual }?.text, "5 final")
        XCTAssertEqual(input.accessibilityComparison(for: six),
                       "Pregame chance: 58.5%, Oct 3, 4:54 PM PT · Kalshi; Final result: Missed; Finished 1 short")
        let five = input.milestones[3]
        XCTAssertEqual(input.secondReading(five), .result(.reached("Reached")))
    }

    func testFinalNeverShowsSettledPricesAsChances() {
        let input = Self.input(.final, Self.finalRows, actual: Self.finalFive)
        for milestone in input.milestones {
            XCTAssertNil(input.currentReading(milestone))
            XCTAssertNil(input.currentFraction(milestone))
            XCTAssertNil(input.movement(milestone))
            XCTAssertFalse(input.accessibilityComparison(for: milestone).contains("100%"))
            XCTAssertFalse(input.accessibilityComparison(for: milestone).contains("Settled"))
        }
        let model = try! XCTUnwrap(input.plotModel(size: Self.size, inset: Self.inset))
        XCTAssertEqual(model.marks.count, 9)
        XCTAssertTrue(model.marks.allSatisfy { $0.kind == .pregame })
    }

    func testKnownResultWithUnknownCountStaysDistinct() {
        let input = Self.input(.final, Self.finalRows, selected: Self.key(3), actual: .unavailable("Exact final count unavailable"))
        let five = try! XCTUnwrap(input.selection.milestone)
        XCTAssertEqual(input.secondReading(five), .result(.reached("Reached")))
        XCTAssertEqual(input.actualPresentation?.actual, .unavailable("Exact final count unavailable"))
        XCTAssertNil(input.visibleActualQuantity)
        XCTAssertNil(input.plotModel(size: Self.size, inset: Self.inset)?.actualX)
    }

    func testUnconfirmedResultStaysStatusAndIsNotDerivedFromTheCount() {
        let rows = (0..<9).map { Self.row($0, result: Self.pending) }
        let input = Self.input(.final, rows, actual: Self.finalFive)
        let six = try! XCTUnwrap(input.selection.milestone)
        guard case .result(let result)? = input.secondReading(six) else { return XCTFail("result expected") }
        XCTAssertFalse(result.isAdmitted)
        XCTAssertEqual(result.text, "Result unconfirmed")
        XCTAssertEqual(input.secondReading(input.milestones[0]), .result(Self.pending), "a count of 5 does not settle 2+")
    }

    // MARK: Selection and callbacks

    func testMissingSelectionSelectsNobodyAndKeepsEveryRow() {
        let input = Self.input(.during, Self.updatedStage, selected: "nhl-15169793-game-markets.json:totals:99", actual: Self.fourSoFar)
        XCTAssertEqual(input.selection, .missing("nhl-15169793-game-markets.json:totals:99"))
        XCTAssertEqual(input.selectionNotice, "Selected milestone unavailable.")
        XCTAssertNil(input.selection.milestone)
        XCTAssertNil(input.stepAction(1, canSelect: true))
        XCTAssertNil(input.detailsAction(canOpenDetails: true))
        XCTAssertEqual(input.positionText, "9 milestones")
        let model = try! XCTUnwrap(input.plotModel(size: Self.size, inset: Self.inset))
        XCTAssertNil(model.selectionX)
        XCTAssertFalse(model.marks.contains(where: \.selected))
        XCTAssertEqual(Set(model.marks.map(\.index)), Set(0..<9))
        XCTAssertFalse(input.annotations.contains { $0.kind == .selection })
        XCTAssertEqual(input.accessibilityChartValue, "Selected milestone unavailable.")
    }

    func testDuplicateSelectionSelectsNobodyAndPreservesRows() {
        var rows = (0..<9).map { Self.row($0) }
        rows.append(Self.row(4, id: Self.key(4)))
        let input = Self.input(.before, rows, selected: Self.key(4),
                               timing: TotalMilestoneTiming10868(milestoneID: Self.key(4), title: "6+ goals · timing", lines: ["Recorded 4:54 PM"]))
        XCTAssertEqual(input.selection, .duplicate(Self.key(4)))
        XCTAssertEqual(input.selectionNotice, "Selected milestone unavailable.")
        XCTAssertNil(input.timingPresentation(hasBinding: false))
        XCTAssertNil(input.stepAction(-1, canSelect: true))
        XCTAssertEqual(input.milestones.count, 10)
        XCTAssertEqual(input.positionText, "10 milestones")
        XCTAssertFalse(try! XCTUnwrap(input.plotModel(size: Self.size, inset: Self.inset)).marks.contains(where: \.selected))
    }

    func testNoSelectionIsNotAFailure() {
        let input = Self.input(.before, (0..<9).map { Self.row($0) }, selected: nil)
        XCTAssertEqual(input.selection, .none)
        XCTAssertNil(input.selectionNotice)
        XCTAssertEqual(input.accessibilityChartValue, "No milestone selected")
    }

    func testCallbacksCarryExactOriginalIDs() {
        let input = Self.input(.final, Self.finalRows, actual: Self.finalFive)
        XCTAssertEqual(input.stepAction(-1, canSelect: true), .select(Self.key(3)))
        XCTAssertEqual(input.stepAction(1, canSelect: true), .select(Self.key(5)))
        XCTAssertEqual(input.detailsAction(canOpenDetails: true), .details(Self.key(4)))
        XCTAssertEqual(input.selectAction(id: Self.key(8), canSelect: true), .select(Self.key(8)))
        let first = Self.input(.final, Self.finalRows, selected: Self.key(0))
        XCTAssertNil(first.stepAction(-1, canSelect: true), "no wrap, no substitute")
        let last = Self.input(.final, Self.finalRows, selected: Self.key(8))
        XCTAssertNil(last.stepAction(1, canSelect: true))

        var selected: [String] = []
        var details: [String] = []
        let onSelect: (String) -> Void = { selected.append($0) }
        let onDetails: (String) -> Void = { details.append($0) }
        input.stepAction(1, canSelect: true)?.perform(onSelect: onSelect, onDetails: onDetails)
        input.detailsAction(canOpenDetails: true)?.perform(onSelect: onSelect, onDetails: onDetails)
        XCTAssertEqual(selected, [Self.key(5)])
        XCTAssertEqual(details, [Self.key(4)])
    }

    func testNoCallbackMeansNoAction() {
        let input = Self.input(.during, Self.updatedStage, actual: Self.fourSoFar)
        XCTAssertNil(input.stepAction(1, canSelect: false))
        XCTAssertNil(input.selectAction(id: Self.key(0), canSelect: false))
        XCTAssertNil(input.detailsAction(canOpenDetails: false))
    }

    // MARK: Geometry

    func testZeroIsARealMarkAndMissingOrInvalidIsNot() {
        XCTAssertEqual(TotalMilestoneGeometry10868.fraction(0), 0)
        XCTAssertEqual(TotalMilestoneGeometry10868.fraction(1), 1)
        XCTAssertNil(TotalMilestoneGeometry10868.fraction(1.2))
        XCTAssertNil(TotalMilestoneGeometry10868.fraction(-0.01))
        XCTAssertNil(TotalMilestoneGeometry10868.fraction(.nan))
        XCTAssertNil(TotalMilestoneGeometry10868.fraction(.infinity))
        let rows = [
            Self.row(0, before: .some(Self.obs(0, "0%", nil, "constructed"))),
            Self.row(1, before: .some(nil)),
            Self.row(2, before: .some(Self.obs(1.2, "120%", nil, "constructed"))),
            Self.row(3, before: .some(Self.obs(.nan, "—", nil, "constructed"))),
            Self.row(4, before: .some(Self.obs(1, "100%", nil, "constructed"))),
        ]
        let input = Self.input(.before, rows, selected: Self.key(4))
        let model = try! XCTUnwrap(input.plotModel(size: Self.size, inset: Self.inset))
        XCTAssertEqual(model.marks.map(\.index), [0, 4])
        XCTAssertEqual(model.marks[0].point.y, Self.size.height - Self.inset, accuracy: 0.001, "0% sits on the inset baseline")
        XCTAssertEqual(model.marks[1].point.y, Self.inset, accuracy: 0.001)
        XCTAssertEqual(model.baselineY, Self.size.height - Self.inset, accuracy: 0.001)
        // Endpoint marks and the selected ring stay inside the plot on both axes.
        let ring = TotalMilestoneGeometry10868.ringRadius + 1
        for mark in model.marks {
            XCTAssertGreaterThanOrEqual(mark.point.x - ring, 0)
            XCTAssertLessThanOrEqual(mark.point.x + ring, Self.size.width)
            XCTAssertGreaterThanOrEqual(mark.point.y - ring, 0)
            XCTAssertLessThanOrEqual(mark.point.y + ring, Self.size.height)
        }
        XCTAssertEqual(input.beforeReading(rows[1]), .missing("Unavailable"))
        XCTAssertEqual(input.beforeReading(rows[2]), .value(Self.obs(1.2, "120%", nil, "constructed")), "the owner's text is kept")
        XCTAssertEqual(input.milestones.count, 5)
    }

    func testInvalidQuantitiesKeepRowsWithoutMarks() {
        let rows = [
            Self.row(0),
            Self.row(1, quantity: -1),
            Self.row(2, quantity: .nan),
            Self.row(3, quantity: .infinity),
            Self.row(4),
        ]
        let input = Self.input(.before, rows, selected: Self.key(1))
        XCTAssertEqual(input.domain, TotalMilestoneDomain10868(lower: 2, upper: 6))
        let model = try! XCTUnwrap(input.plotModel(size: Self.size, inset: Self.inset))
        XCTAssertEqual(model.marks.map(\.index), [0, 4])
        XCTAssertNil(model.selectionX)
        XCTAssertTrue(input.annotations.isEmpty, "an undrawable selection has no direct label")
        XCTAssertEqual(input.selection.index, 1, "still selectable and reachable")
        XCTAssertEqual(input.stepAction(1, canSelect: true), .select(Self.key(2)))
    }

    func testDomainIsTheSameWhateverIsSelected() {
        let rows = (0..<9).map { Self.row($0) }
        let points = [Self.key(0), Self.key(8), nil].map { selected -> [CGPoint] in
            Self.input(.before, rows, selected: selected).plotModel(size: Self.size, inset: Self.inset)!.marks.map(\.point)
        }
        XCTAssertEqual(points[0], points[1])
        XCTAssertEqual(points[1], points[2])
        XCTAssertEqual(points[0].first?.x ?? 0, Self.inset, accuracy: 0.001)
        XCTAssertEqual(points[0].last?.x ?? 0, Self.size.width - Self.inset, accuracy: 0.001)
        XCTAssertEqual(Self.input(.before, rows, domain: TotalMilestoneDomain10868(lower: 0, upper: 12)).domain,
                       TotalMilestoneDomain10868(lower: 0, upper: 12))
        XCTAssertEqual(Self.input(.before, rows, domain: TotalMilestoneDomain10868(lower: 9, upper: 3)).domain,
                       TotalMilestoneDomain10868(lower: 2, upper: 10), "a reversed range is ignored")
        XCTAssertEqual(Self.input(.before, rows, domain: TotalMilestoneDomain10868(lower: .nan, upper: 40)).domain,
                       TotalMilestoneDomain10868(lower: 2, upper: 10), "a non-finite range is ignored")
    }

    func testDomainIncludesTheVisibleCountAndProjectionOnly() {
        let rows = (0..<9).map { Self.row($0, result: .missed("Missed")) }
        let twelve = Self.count(12, "12", clock: nil, rule: "12 final", detail: "constructed")
        XCTAssertEqual(Self.input(.final, rows, actual: twelve).domain?.upper, 12)
        XCTAssertEqual(Self.input(.before, rows, actual: twelve).domain?.upper, 10, "a count hidden before play does not stretch the axis")
        XCTAssertEqual(Self.input(.final, rows, projection: Self.projection(0.5)).domain?.lower, 0.5)
        XCTAssertEqual(Self.input(.during, rows, projection: Self.projection(0.5)).domain?.lower, 2)
    }

    func testArbitraryQuantitiesAndTicks() {
        let quantities: [Double] = [0, 0.5, 37, 120]
        let rows = quantities.enumerated().map { i, q in Self.row(i, quantity: q) }
        let ticks = [0.0, 60, 120, 500, -5, .nan].map { TotalMilestoneTick10868(value: $0, text: "t\($0)") }
        let input = Self.input(.before, rows, selected: Self.key(3), quantityTicks: ticks)
        XCTAssertEqual(input.domain, TotalMilestoneDomain10868(lower: 0, upper: 120))
        XCTAssertEqual(input.placedQuantityTicks.map(\.value), [0, 60, 120])
        let model = try! XCTUnwrap(input.plotModel(size: Self.size, inset: Self.inset))
        XCTAssertEqual(model.marks.count, 4)
        XCTAssertEqual(model.selectionX ?? 0, Self.size.width - Self.inset, accuracy: 0.001)

        let single = Self.input(.before, [Self.row(0, quantity: 7)], selected: Self.key(0))
        XCTAssertEqual(single.plotModel(size: Self.size, inset: Self.inset)?.marks.first?.point.x ?? 0,
                       Self.size.width / 2, accuracy: 0.001, "a one-value axis centres its milestone")
        XCTAssertEqual(TotalMilestoneGeometry10868.x(7, domain: TotalMilestoneDomain10868(lower: 0, upper: 10), width: 0, inset: 12), nil)
    }

    func testCrowdedAndEndpointLabelsReflowIntoLanes() {
        // Selected 5+ and the final count 5 share one position; a long label sits at the far end.
        let sizes = [CGSize(width: 30, height: 14), CGSize(width: 46, height: 14), CGSize(width: 80, height: 14)]
        let plan = TotalMilestoneGeometry10868.rows(centers: [120, 120, 299], sizes: sizes, extent: 300, growsUp: true)
        XCTAssertEqual(plan.frames.count, 3)
        for (a, b) in [(0, 1), (0, 2), (1, 2)] {
            XCTAssertFalse(plan.frames[a].intersects(plan.frames[b]), "\(a) and \(b) overlap")
        }
        XCTAssertTrue(plan.frames.allSatisfy { $0.minX >= 0 && $0.maxX <= 300 }, "endpoint labels stay inside")
        XCTAssertEqual(plan.frames[2].maxX, 300, accuracy: 0.001)
        XCTAssertEqual(plan.frames[0].midX, 120, accuracy: 0.001, "the first keeps its position; it is not shifted")
        XCTAssertEqual(plan.frames[1].midX, 120, accuracy: 0.001, "the collision moves up a lane, not sideways")
        XCTAssertEqual(plan.frames[0].maxY, plan.depth, accuracy: 0.001, "lane 0 sits against the plot below")
        XCTAssertGreaterThan(plan.depth, 14)

        let oversize = TotalMilestoneGeometry10868.rows(centers: [10, 150], sizes: [CGSize(width: 400, height: 30), CGSize(width: 20, height: 14)],
                                                       extent: 300, growsUp: false)
        XCTAssertEqual(oversize.frames[0].minX, 0)
        XCTAssertFalse(oversize.frames[0].intersects(oversize.frames[1]), "an oversize label has a lane of its own")
    }

    func testChartPlanSharesThePlotScaleAndKeepsPlotHeight() {
        let domain = TotalMilestoneDomain10868(lower: 2, upper: 10)
        let chanceSizes = [CGSize(width: 22, height: 13), CGSize(width: 28, height: 13), CGSize(width: 34, height: 13), CGSize(width: 28, height: 13)]
        let plan = TotalMilestoneGeometry10868.chartPlan(
            width: 340, plotHeight: 180, inset: Self.inset, domain: domain,
            chanceFractions: [0, 0.5, 1, 0.52], chanceSizes: chanceSizes,
            annotationValues: [6, 5], annotationSizes: [CGSize(width: 28, height: 14), CGSize(width: 44, height: 14)],
            tickValues: [2, 4, 6, 8, 10], tickSizes: Array(repeating: CGSize(width: 12, height: 14), count: 5))
        XCTAssertEqual(plan.plot.height, 180)
        XCTAssertGreaterThan(plan.plot.minX, 34, "crowded chance labels take a second column, never a smaller font")
        XCTAssertFalse(plan.chanceLabels[1].intersects(plan.chanceLabels[3]))
        XCTAssertTrue(plan.chanceLabels.allSatisfy { $0.maxX <= plan.plot.minX })
        for (label, fraction) in zip(plan.chanceLabels, [0, 0.5, 1, 0.52]) {
            let gridline = try! XCTUnwrap(TotalMilestoneGeometry10868.y(fraction, height: 180, inset: Self.inset))
            XCTAssertEqual(label.midY, plan.plot.minY + gridline, accuracy: 0.001, "each label sits on its gridline")
        }
        let six = try! XCTUnwrap(TotalMilestoneGeometry10868.x(6, domain: domain, width: plan.plot.width, inset: Self.inset))
        XCTAssertEqual(plan.annotations[0].midX, plan.plot.minX + six, accuracy: 0.001)
        XCTAssertTrue(plan.annotations.allSatisfy { $0.maxY <= plan.plot.minY })
        XCTAssertFalse(plan.annotations[0].intersects(plan.annotations[1]))
        XCTAssertTrue(plan.quantityTicks.allSatisfy { $0.minY >= plan.plot.maxY })
        XCTAssertEqual(plan.size.height, plan.quantityTicks.map(\.maxY).max() ?? 0, accuracy: 0.001)

        let unselected = TotalMilestoneGeometry10868.chartPlan(
            width: 340, plotHeight: 180, inset: Self.inset, domain: domain,
            chanceFractions: [0, 0.5, 1, 0.52], chanceSizes: chanceSizes,
            annotationValues: [], annotationSizes: [],
            tickValues: [2, 4, 6, 8, 10], tickSizes: Array(repeating: CGSize(width: 12, height: 14), count: 5))
        XCTAssertEqual(unselected.plot.width, plan.plot.width, "the selection's label never changes the x scale")
    }

    func testNoChanceOffersMilestonesOnAQuantityStrip() {
        let rows = (0..<9).map { Self.row($0, before: .some(nil), result: $0 <= 3 ? .reached("Reached") : .missed("Missed")) }
        let input = Self.input(.final, rows, actual: Self.finalFive)
        XCTAssertTrue(input.isQuantityStrip)
        XCTAssertTrue(input.placedChanceTicks.isEmpty, "no misleading probability axis")
        let model = try! XCTUnwrap(input.plotModel(size: CGSize(width: 300, height: 40), inset: Self.inset))
        XCTAssertTrue(model.isStrip)
        XCTAssertTrue(model.marks.isEmpty)
        XCTAssertTrue(model.gridlines.isEmpty)
        XCTAssertEqual(model.milestoneTicks.count, 9)
        XCTAssertNotNil(model.actualX)
        XCTAssertNotNil(model.selectionX)
        XCTAssertTrue(input.accessibilityChartLabel.contains("no chances are shown"))
        XCTAssertFalse(input.accessibilityChartLabel.contains("Hollow"))
        XCTAssertEqual(input.secondReading(input.milestones[4]), .result(.missed("Missed")))
    }

    func testProjectionIsAQuantityApartFromEveryChance() {
        // CONSTRUCTED: this hockey record has no qualified projection.
        let input = Self.input(.final, Self.finalRows, actual: Self.finalFive, projection: Self.projection(5.8))
        XCTAssertEqual(input.visibleProjection?.text, "5.8 goals")
        XCTAssertEqual(input.annotations.map(\.kind), [.selection, .actual, .projection])
        let model = try! XCTUnwrap(input.plotModel(size: Self.size, inset: Self.inset))
        XCTAssertNotNil(model.projectionX)
        XCTAssertNotEqual(model.projectionX, model.actualX)
        XCTAssertEqual(model.marks.count, 9, "a projection never adds a probability mark")
        XCTAssertEqual(input.accessibilityProjection(try! XCTUnwrap(input.visibleProjection)),
                       "5.8 goals, recorded Oct 3, 4:50 PM PT · constructed; 0.8 goals below projection")
        XCTAssertTrue(input.accessibilityChartLabel.contains("The dashed rule is a projection, not a chance."))
        XCTAssertNil(Self.input(.during, Self.updatedStage, actual: Self.fourSoFar, projection: Self.projection(5.8)).visibleProjection)

        let invalid = Self.input(.final, Self.finalRows, actual: Self.finalFive, projection: Self.projection(.nan))
        XCTAssertNotNil(invalid.visibleProjection, "the owner's words still show")
        XCTAssertNil(invalid.plotModel(size: Self.size, inset: Self.inset)?.projectionX)
        XCTAssertFalse(invalid.annotations.contains { $0.kind == .projection })
    }

    private static func projection(_ value: Double) -> TotalMilestoneProjection10868 {
        TotalMilestoneProjection10868(quantity: value, title: "Pregame projection", text: "5.8 goals", clock: "4:50 PM",
                                      ruleLabel: "5.8 projected", comparison: "0.8 goals below projection",
                                      accessibilityDetail: "recorded Oct 3, 4:50 PM PT · constructed")
    }

    // MARK: Timing, disclosure and spoken text

    func testTimingBelongsToTheExactSelectedMilestone() {
        let timing = TotalMilestoneTiming10868(milestoneID: Self.key(4), title: "6+ goals · timing",
                                              lines: ["Pregame 4:54 PM · Kalshi", "In-game 7:16 PM · Kalshi consensus"])
        let six = Self.input(.during, Self.updatedStage, actual: Self.fourSoFar, timing: timing)
        XCTAssertEqual(six.timingPresentation(hasBinding: true), .disclosure(timing))
        XCTAssertEqual(six.timingPresentation(hasBinding: false), .expanded(timing))
        let five = Self.input(.during, Self.updatedStage, selected: Self.key(3), actual: Self.fourSoFar, timing: timing)
        XCTAssertNil(five.timingPresentation(hasBinding: true), "another milestone's timing never shows")
    }

    @MainActor
    func testPageOwnedTimingFlagPassesThroughUntouched() {
        var expanded = false
        let binding = Binding(get: { expanded }, set: { expanded = $0 })
        let view = TotalMilestonePresentation10868(input: Self.input(.final, Self.finalRows, actual: Self.finalFive),
                                                    onSelect: { _ in }, onDetails: { _ in }, timingExpanded: binding)
        XCTAssertNotNil(view.timingExpanded)
        XCTAssertFalse(expanded)
        if let flag = view.timingExpanded { flag.wrappedValue = true }
        XCTAssertTrue(expanded, "the page owns the flag")
        let unbound = TotalMilestonePresentation10868(input: view.input)
        XCTAssertNil(unbound.timingExpanded)
        XCTAssertNil(unbound.onSelect)
    }

    func testSpokenTextNamesPhaseReadingsCountAndResultDistinctly() {
        let before = Self.input(.before, Self.allSupplied, actual: Self.finalFive)
        XCTAssertEqual(before.accessibilityHeader, "TOTAL GOALS · BOTH TEAMS. Room for more goals?. Before play")
        XCTAssertEqual(before.accessibilityChartLabel, "Chance of reaching each total Hollow marks are pregame chances.")

        let during = Self.input(.during, Self.updatedStage, actual: Self.fourSoFar)
        XCTAssertTrue(during.accessibilityHeader.hasSuffix("During play"))
        XCTAssertEqual(during.accessibilityChartLabel,
                       "Chance of reaching each total Hollow marks are pregame chances. Filled marks are recorded in-game chances. The solid rule is the count, not a chance.")
        XCTAssertEqual(during.accessibilityChartValue,
                       "6+ goals. Pregame chance: 58.5%, Oct 3, 4:54 PM PT · Kalshi; Recorded in-game chance: 56.5%, Oct 3, 7:16 PM PT · Kalshi consensus; Change since pregame: −2 percentage points since pregame; 2 more needed")
        XCTAssertEqual(during.accessibilityActual(try! XCTUnwrap(during.actualPresentation)),
                       "4 goals, as of 7:16 PM PT, 3rd period, 14:34 left · ESPN")

        let final = Self.input(.final, Self.finalRows, actual: Self.finalFive)
        XCTAssertTrue(final.accessibilityHeader.hasSuffix("Final"))
        XCTAssertTrue(final.accessibilityChartValue.contains("Final result: Missed"))
        XCTAssertFalse(final.accessibilityChartValue.contains("Recorded in-game"))

        XCTAssertEqual(TotalMilestoneAccessibilityID10868.comparison(Self.key(4)),
                       "totalMilestone10868.comparison.nhl-15169793-game-markets.json:totals:4")
        XCTAssertEqual(TotalMilestoneAccessibilityID10868.details(Self.key(4)),
                       "totalMilestone10868.details.nhl-15169793-game-markets.json:totals:4")
    }

    // MARK: Original milestones strip — soccer (Valladolid–Albacete)

    // ARCHIVED from `shipping-adoption-20261027/SOCCER-GOAL-MILESTONE-RETAINED-CASES.json`,
    // event 15325054 (liveSoccer.json sha256 d835ccdf…, soccerFinal.json 05de3275…):
    //   totals:64353423:242143183 Over 2.5 → 3+ · pregame_pin 0.50 @ 11:47:12.330899Z
    //   totals:64353425:242143187 Over 4.5 → 5+ · pregame_pin 0.13 @ 11:47:12.057085Z
    //   totals:64536538:242765587 Over 5.5 → 6+ · pregame_pin 0.06 @ 11:47:12.068367Z
    //   live 4–0 @ 12:54:19Z, clock null, every current null, result pending; the raw
    //   published 0.15 for all three is withheld and must never appear.
    //   final 5–0, completed 13:57:41Z; 3+ won, 5+ won, 6+ lost (prop-<market>.json).
    //   The 2.5 → 3 / 4.5 → 5 / 5.5 → 6 coordinates are the approved reference's,
    //   supplied here, never derived. No projection is admitted.
    // CONSTRUCTED: every display string, PT clock and detail line, the reached /
    // unavailable / withheld words, result words, and the current-chance,
    // void-like, zero, missing, duplicate and long-title cases.

    private static let soccerIDs = ["totals:64353423:242143183", "totals:64353425:242143187", "totals:64536538:242765587"]
    private static let soccerPregame: [(quantity: Double, probability: Double, text: String, at: String)] = [
        (3, 0.5, "50%", "2026-10-12T11:47:12.330899Z"),
        (5, 0.13, "13%", "2026-10-12T11:47:12.057085Z"),
        (6, 0.06, "6%", "2026-10-12T11:47:12.068367Z"),
    ]

    private static func soccerRow(
        _ index: Int,
        before: TotalMilestoneObservation10868?? = nil,
        current: TotalMilestoneCurrent10868 = .unavailable("Current chance unavailable"),
        result: TotalMilestoneResult10868 = .unconfirmed("Result pending"),
        title: String? = nil,
        id: String? = nil
    ) -> TotalMilestoneRow10868 {
        let saved = soccerPregame[index]
        let label = "\(Int(saved.quantity))+"
        return TotalMilestoneRow10868(
            id: id ?? soccerIDs[index],
            quantity: saved.quantity,
            quantityLabel: label,
            title: title ?? "\(label) goals",
            before: before ?? obs(saved.probability, saved.text, "4:47 AM", "Oct 12, 4:47 AM PT · pregame pin \(saved.at)"),
            beforeMissing: "No pre-match chance",
            current: current,
            performance: nil,
            result: result
        )
    }

    private static func soccerInput(
        _ phase: TotalMilestonePhase10868,
        _ rows: [TotalMilestoneRow10868],
        selected: String? = soccerIDs[1],
        actual: TotalMilestoneActual10868? = nil
    ) -> TotalMilestoneInput10868 {
        TotalMilestoneInput10868(
            phase: phase, eyebrow: "GOAL MILESTONES", title: "Room for more goals?",
            chartTitle: "Chance of reaching each total", quantityAxisTitle: "Total goals in the match",
            milestones: rows, selectedMilestoneID: selected, actual: actual, projection: nil,
            quantityDomain: TotalMilestoneDomain10868(lower: 0, upper: 7),
            quantityTicks: [0.0, 3, 5, 6].map { TotalMilestoneTick10868(value: $0, text: $0 == 0 ? "0" : "\(Int($0))+") },
            chanceTicks: chanceTicks, timing: nil
        )
    }

    /// Live 4–0: 3+ is reached in play (performance, market result pending); 5+ and 6+ have no current chance.
    private static var soccerLive: [TotalMilestoneRow10868] {
        [soccerRow(0, current: .reached("Reached")), soccerRow(1), soccerRow(2)]
    }

    /// Final 5–0 with each result independently recorded; a settled 1.0/0.0 is supplied as a "current" to prove it is ignored.
    private static var soccerFinal: [TotalMilestoneRow10868] {
        let results: [TotalMilestoneResult10868] = [.reached("Won"), .reached("Won"), .missed("Lost")]
        return (0..<3).map { i in
            let settled = i < 2 ? 1.0 : 0.0
            return soccerRow(i, current: .recorded(obs(settled, settled == 1 ? "100%" : "0%", "Settled", "settled"), movement: nil),
                             result: results[i])
        }
    }

    private static let soccerFour = count(4, "4", clock: nil, rule: "4 so far", detail: "as of Oct 12, 5:54 AM PT · score capture")
    private static let soccerFive = count(5, "5", clock: "Final", rule: "5 actual", detail: "final, observed Oct 12, 6:57 AM PT")

    func testStripBeforePlayShowsEachOriginalPregameChanceWithItsOwnClockAndNothingLater() {
        // Later inputs supplied to prove they stay hidden before play.
        let rows = (0..<3).map { i in
            Self.soccerRow(i, current: .recorded(Self.obs(0.9, "90%", "5:54 AM", "constructed current"), movement: "Movement"),
                           result: .reached("Won"))
        }
        let input = Self.soccerInput(.before, rows, actual: Self.soccerFive)
        let entries = input.stripEntries
        XCTAssertEqual(entries.map(\.milestone.id), Self.soccerIDs, "exact originals, owner order")
        XCTAssertEqual(entries.map(\.milestone.title), ["3+ goals", "5+ goals", "6+ goals"])
        for (entry, saved) in zip(entries, Self.soccerPregame) {
            XCTAssertEqual(entry.pregame, .value(Self.obs(saved.probability, saved.text, "4:47 AM",
                                                          "Oct 12, 4:47 AM PT · pregame pin \(saved.at)")))
            XCTAssertNil(entry.second, "no current, actual or result before play")
            XCTAssertFalse(entry.pregameMark, "the comparison carries no key mark before play, so neither does the strip")
            XCTAssertFalse(entry.currentMark)
            let spoken = input.accessibilityStripValue(entry)
            XCTAssertTrue(spoken.contains(saved.at), "each original keeps its own pin clock")
            XCTAssertFalse(spoken.contains("90%"))
            XCTAssertFalse(spoken.contains("Won"))
        }
        XCTAssertEqual(entries.map(\.selected), [false, true, false])
        XCTAssertEqual(input.accessibilityStripValue(entries[0]),
                       "Pregame chance: 50%, Oct 12, 4:47 AM PT · pregame pin 2026-10-12T11:47:12.330899Z")
        XCTAssertNil(input.actualPresentation)
    }

    func testStripDuringPlayKeepsEveryNonselectedStateReadableAndNeverRevivesTheWithheldPrice() {
        let input = Self.soccerInput(.during, Self.soccerLive, actual: Self.soccerFour)
        let entries = input.stripEntries
        XCTAssertEqual(entries.count, 3)
        XCTAssertEqual(entries[0].second, .current(.actual("Reached")))
        XCTAssertEqual(entries[1].second, .current(.chanceStatus("Current chance unavailable")))
        XCTAssertEqual(entries[2].second, .current(.chanceStatus("Current chance unavailable")))
        XCTAssertEqual(entries.map(\.selected), [false, true, false])
        XCTAssertTrue(entries.allSatisfy(\.pregameMark), "during play the pregame figure carries the hollow key")
        XCTAssertFalse(entries.contains(where: \.currentMark), "no current chance, no filled mark")
        let reached = input.accessibilityStripValue(entries[0])
        XCTAssertTrue(reached.contains("Actual so far: Reached"), "reaching 3 in play is performance")
        XCTAssertFalse(reached.contains("Won"), "a reached threshold is not settlement")
        XCTAssertFalse(reached.contains("100%"))
        for entry in entries {
            let spoken = input.accessibilityStripValue(entry)
            XCTAssertFalse(spoken.contains("15%"), "the withheld published 15% never appears")
            XCTAssertFalse(spoken.contains("Result pending"), "a result is not shown during play")
        }
        XCTAssertEqual(input.accessibilityStripValue(entries[2]),
                       "Pregame chance: 6%, Oct 12, 4:47 AM PT · pregame pin 2026-10-12T11:47:12.068367Z; In-game chance: Current chance unavailable")
        // The selected comparison and the separate count are retained.
        XCTAssertEqual(input.secondReading(try! XCTUnwrap(input.selection.milestone)),
                       .current(.chanceStatus("Current chance unavailable")))
        XCTAssertEqual(input.actualPresentation?.title, "Count so far")
        XCTAssertEqual(input.visibleActualQuantity, 4)
    }

    func testStripDuringPlayShowsAnAdmittedCurrentChanceAndWithheldStateApart() {
        // CONSTRUCTED: an admitted 5+ current chance and a withheld 6+.
        let rows = [
            Self.soccerRow(0, current: .reached("Reached")),
            Self.soccerRow(1, current: .recorded(Self.obs(0.62, "62%", "5:55 AM", "Oct 12, 5:55 AM PT · constructed"),
                                                 movement: "+49 points since pregame")),
            Self.soccerRow(2, current: .withheld("No update since goal")),
        ]
        let input = Self.soccerInput(.during, rows, selected: Self.soccerIDs[0], actual: Self.soccerFour)
        let entries = input.stripEntries
        XCTAssertEqual(entries[1].second, .current(.chance(Self.obs(0.62, "62%", "5:55 AM", "Oct 12, 5:55 AM PT · constructed"))))
        XCTAssertTrue(entries[1].currentMark, "a nonselected recorded chance still carries the filled key")
        XCTAssertFalse(entries[1].selected)
        XCTAssertEqual(entries[2].second, .current(.chanceStatus("No update since goal")))
        XCTAssertFalse(entries[2].currentMark)
        XCTAssertEqual(input.accessibilityStripValue(entries[1]),
                       "Pregame chance: 13%, Oct 12, 4:47 AM PT · pregame pin 2026-10-12T11:47:12.057085Z; Recorded in-game chance: 62%, Oct 12, 5:55 AM PT · constructed")
        XCTAssertFalse(input.accessibilityStripValue(entries[1]).contains("+49"), "movement stays with the selected comparison")
    }

    func testStripAfterTheFinalPairsEachPregameChanceWithItsRecordedResult() {
        let input = Self.soccerInput(.final, Self.soccerFinal, actual: Self.soccerFive)
        let entries = input.stripEntries
        XCTAssertEqual(entries.map(\.second), [.result(.reached("Won")), .result(.reached("Won")), .result(.missed("Lost"))])
        XCTAssertEqual(entries.map(\.pregame), (0..<3).map { input.beforeReading(input.milestones[$0]) })
        XCTAssertFalse(entries.contains(where: \.currentMark), "a settled 1.0/0.0 is never a chance")
        XCTAssertFalse(entries.contains(where: \.pregameMark))
        for entry in entries {
            let spoken = input.accessibilityStripValue(entry)
            XCTAssertFalse(spoken.contains("100%"))
            XCTAssertFalse(spoken.contains("Settled"))
        }
        XCTAssertEqual(input.accessibilityStripValue(entries[2]),
                       "Pregame chance: 6%, Oct 12, 4:47 AM PT · pregame pin 2026-10-12T11:47:12.068367Z; Final result: Lost")
        // The selected comparison is retained: 13% against Won, and the final count apart.
        let five = try! XCTUnwrap(input.selection.milestone)
        XCTAssertEqual(input.secondReading(five), .result(.reached("Won")))
        XCTAssertEqual(input.actualPresentation?.title, "Final count")
        XCTAssertNil(input.visibleProjection, "no projection admitted in this fixture")
    }

    func testStripUnresolvedResultIsStatusNotALoss() {
        // CONSTRUCTED: 6+ unconfirmed, and a void-like word, at a final count of 5.
        let rows = [
            Self.soccerRow(0, result: .reached("Won")),
            Self.soccerRow(1, result: .unconfirmed("Voided")),
            Self.soccerRow(2, result: .unconfirmed("Result pending")),
        ]
        let input = Self.soccerInput(.final, rows, actual: Self.soccerFive)
        let entries = input.stripEntries
        guard case .result(let voided)? = entries[1].second, case .result(let pending)? = entries[2].second else {
            return XCTFail("results expected")
        }
        XCTAssertFalse(voided.isAdmitted)
        XCTAssertFalse(pending.isAdmitted)
        XCTAssertEqual(pending.text, "Result pending", "a count of 5 never settles 6+ as lost")
        XCTAssertFalse(input.accessibilityStripValue(entries[2]).contains("Lost"))
    }

    func testStripKnownZeroIsAFigureAndMissingIsWords() {
        // CONSTRUCTED: 5+ at a real 0%, 6+ with no pregame chance.
        let rows = [
            Self.soccerRow(0),
            Self.soccerRow(1, before: .some(Self.obs(0, "0%", "4:47 AM", "constructed zero"))),
            Self.soccerRow(2, before: .some(nil)),
        ]
        let input = Self.soccerInput(.during, rows, actual: Self.soccerFour)
        let entries = input.stripEntries
        XCTAssertEqual(entries[1].pregame, .value(Self.obs(0, "0%", "4:47 AM", "constructed zero")))
        XCTAssertTrue(entries[1].pregameMark, "0% is a drawn mark")
        XCTAssertEqual(entries[2].pregame, .missing("No pre-match chance"))
        XCTAssertFalse(entries[2].pregameMark, "no key mark beside a missing figure")
        XCTAssertEqual(input.stripEntries.count, 3, "a missing input keeps its original")
    }

    func testStripRefusesMissingAndDuplicateSelectionsButKeepsEveryOriginal() {
        let missing = Self.soccerInput(.final, Self.soccerFinal, selected: "totals:64353423:999", actual: Self.soccerFive)
        XCTAssertEqual(missing.stripEntries.count, 3)
        XCTAssertFalse(missing.stripEntries.contains(where: \.selected))
        XCTAssertEqual((0..<3).map { missing.stripAction(index: $0, canSelect: true) }, Self.soccerIDs.map { TotalMilestoneAction10868?.some(.select($0)) })

        // CONSTRUCTED: a second row carrying 5+'s id.
        var rows = Self.soccerFinal
        rows.append(Self.soccerRow(1))
        let duplicate = Self.soccerInput(.final, rows, selected: Self.soccerIDs[1], actual: Self.soccerFive)
        XCTAssertEqual(duplicate.selection, .duplicate(Self.soccerIDs[1]))
        XCTAssertEqual(duplicate.stripEntries.count, 4, "both duplicates stay visible")
        XCTAssertFalse(duplicate.stripEntries.contains(where: \.selected))
        XCTAssertNil(duplicate.stripAction(index: 1, canSelect: true), "a duplicated id can only resolve nobody")
        XCTAssertNil(duplicate.stripAction(index: 3, canSelect: true))
        XCTAssertEqual(duplicate.stripAction(index: 0, canSelect: true), .select(Self.soccerIDs[0]))
        XCTAssertEqual(duplicate.stripAction(index: 2, canSelect: true), .select(Self.soccerIDs[2]))
        XCTAssertNil(duplicate.stripAction(index: 4, canSelect: true))
        XCTAssertNil(duplicate.stripAction(index: -1, canSelect: true))
    }

    func testStripActionCarriesTheExactOriginalAndNothingWithoutACallback() {
        let input = Self.soccerInput(.during, Self.soccerLive, actual: Self.soccerFour)
        XCTAssertEqual(input.stripAction(index: 2, canSelect: true), .select("totals:64536538:242765587"))
        XCTAssertEqual(input.stripAction(index: 1, canSelect: true), .select("totals:64353425:242143187"),
                       "the already-selected original passes the same id back; the page decides")
        for index in 0..<3 {
            XCTAssertNil(input.stripAction(index: index, canSelect: false), "no callback, no strip action")
        }
        var selected: [String] = []
        input.stripAction(index: 0, canSelect: true)?.perform(onSelect: { selected.append($0) }, onDetails: { _ in XCTFail("not details") })
        XCTAssertEqual(selected, ["totals:64353423:242143183"])
        // Previous and next survive beside the strip.
        XCTAssertEqual(input.stepAction(1, canSelect: true), .select(Self.soccerIDs[2]))
        XCTAssertEqual(input.stepAction(-1, canSelect: true), .select(Self.soccerIDs[0]))
        XCTAssertEqual(TotalMilestoneAccessibilityID10868.option(Self.soccerIDs[0]),
                       "totalMilestone10868.option.totals:64353423:242143183")
    }

    func testStripChartKeyAndProfileAreUnchanged() {
        // R2: the selected 5+ ring names the hollow series before play and after the final.
        XCTAssertNil(Self.soccerInput(.before, (0..<3).map { Self.soccerRow($0) }).chartKey)
        XCTAssertNil(Self.soccerInput(.final, Self.soccerFinal, actual: Self.soccerFive).chartKey)
        XCTAssertEqual(Self.soccerInput(.final, Self.soccerFinal, selected: nil, actual: Self.soccerFive).chartKey, Self.pregameKey)
        let live = Self.soccerInput(.during, Self.soccerLive, actual: Self.soccerFour)
        XCTAssertNil(live.chartKey, "pregame only, named by the comparison's hollow key")
        let model = try! XCTUnwrap(live.plotModel(size: Self.size, inset: Self.inset))
        XCTAssertEqual(model.marks.count, 3)
        XCTAssertTrue(model.marks.allSatisfy { $0.kind == .pregame })
        XCTAssertEqual(live.domain, TotalMilestoneDomain10868(lower: 0, upper: 7))
    }

    // MARK: Original milestones strip — layout

    func testStripFitsThreeSoccerOptionsInOneRowAtPhoneWidth() {
        // 327 pt is a 375 pt phone's card content; each option needs 100 pt whole.
        let columns = TotalMilestoneGeometry10868.stripColumns(count: 3, width: 327, spacing: 8, minimumCellWidth: 96) { $0 >= 100 }
        XCTAssertEqual(columns, 3)
        let cell = TotalMilestoneGeometry10868.stripCellWidth(columns: columns, width: 327, spacing: 8)
        let plan = TotalMilestoneGeometry10868.stripFrames(columns: columns, cellWidth: cell, heights: [70, 82, 70], spacing: 8)
        XCTAssertEqual(Set(plan.frames.map(\.minY)), [0], "all three together")
        XCTAssertEqual(plan.frames.map(\.height), [82, 82, 82], "a row's cells line up")
        XCTAssertEqual(plan.size.width, 327, accuracy: 0.001)
        XCTAssertTrue(plan.frames.allSatisfy { $0.width >= 44 && $0.height >= 44 })
    }

    func testStripLongTextAndLargeTypeWrapIntoVisibleRowsNeverHidden() {
        // A long owner title or large type needs 150 pt whole: two columns, the third wraps.
        let two = TotalMilestoneGeometry10868.stripColumns(count: 3, width: 327, spacing: 8, minimumCellWidth: 96) { $0 >= 150 }
        XCTAssertEqual(two, 2)
        let cell = TotalMilestoneGeometry10868.stripCellWidth(columns: two, width: 327, spacing: 8)
        let plan = TotalMilestoneGeometry10868.stripFrames(columns: two, cellWidth: cell, heights: [90, 120, 90], spacing: 8)
        XCTAssertEqual(plan.frames.count, 3, "nothing is dropped")
        XCTAssertEqual(plan.frames[2].minX, 0)
        XCTAssertEqual(plan.frames[2].minY, 128, accuracy: 0.001)
        XCTAssertEqual(plan.size.height, 218, accuracy: 0.001)
        // Wider than any column count allows: one column, where the text wraps.
        XCTAssertEqual(TotalMilestoneGeometry10868.stripColumns(count: 3, width: 327, spacing: 8, minimumCellWidth: 96) { $0 >= 400 }, 1)
        // Accessibility sizes: one column even when more would fit.
        XCTAssertEqual(TotalMilestoneGeometry10868.stripColumns(count: 3, width: 700, spacing: 8, minimumCellWidth: 96,
                                                                maximumColumns: 1) { _ in true }, 1)
        // A scaled minimum cell width reduces columns instead of shrinking the cells.
        XCTAssertEqual(TotalMilestoneGeometry10868.stripColumns(count: 3, width: 327, spacing: 8, minimumCellWidth: 140) { _ in true }, 2)
        XCTAssertEqual(TotalMilestoneGeometry10868.stripColumns(count: 0, width: 327, spacing: 8, minimumCellWidth: 96) { _ in true }, 0)
        XCTAssertTrue(TotalMilestoneGeometry10868.stripFrames(columns: 2, cellWidth: 100, heights: [], spacing: 8).frames.isEmpty)
    }

    func testStripLongTitleIsKeptWhole() {
        let long = "6 or more goals in the match, both teams combined"
        let rows = [Self.soccerRow(0), Self.soccerRow(1), Self.soccerRow(2, title: long)]
        let input = Self.soccerInput(.before, rows)
        XCTAssertEqual(input.stripEntries[2].milestone.title, long, "the owner's full words, never abbreviated")
        XCTAssertEqual(input.accessibilityStripValue(input.stripEntries[2]).hasPrefix("Pregame chance: 6%"), true)
    }

    // MARK: Original milestones strip — the existing nine-row hockey packet

    func testStripCarriesAllNineHockeyOriginalsInOwnerOrder() {
        let input = Self.input(.during, Self.updatedStage, actual: Self.fourSoFar)
        let entries = input.stripEntries
        XCTAssertEqual(entries.map(\.milestone.id), (0..<9).map(Self.key), "no filter, ranking or cap")
        XCTAssertEqual(entries.map(\.index), Array(0..<9))
        XCTAssertEqual(entries.map(\.selected), (0..<9).map { $0 == 4 })
        for i in 0...2 {
            XCTAssertEqual(entries[i].second, .current(.actual("Reached")))
            XCTAssertFalse(entries[i].currentMark)
        }
        for i in 3...8 {
            XCTAssertEqual(entries[i].second,
                           .current(.chance(Self.obs(Self.updated[i].0, Self.updated[i].1, "7:16 PM", Self.updatedDetail))))
            XCTAssertTrue(entries[i].currentMark)
        }
        XCTAssertEqual((0..<9).map { input.stripAction(index: $0, canSelect: true) }, (0..<9).map { TotalMilestoneAction10868?.some(.select(Self.key($0))) })
        // Nine options at phone width: three columns of three, every one visible.
        let columns = TotalMilestoneGeometry10868.stripColumns(count: 9, width: 327, spacing: 8, minimumCellWidth: 96) { $0 >= 90 }
        XCTAssertEqual(columns, 3)
        let cell = TotalMilestoneGeometry10868.stripCellWidth(columns: columns, width: 327, spacing: 8)
        let plan = TotalMilestoneGeometry10868.stripFrames(columns: columns, cellWidth: cell, heights: Array(repeating: 96, count: 9), spacing: 8)
        XCTAssertEqual(plan.frames.count, 9)
        for (a, b) in zip(plan.frames, plan.frames.dropFirst()) where a.minY == b.minY {
            XCTAssertLessThan(a.maxX, b.minX, "owner order left to right")
        }
        XCTAssertTrue(plan.frames.allSatisfy { $0.minX >= 0 && $0.maxX <= 327.001 })
        XCTAssertEqual(Set(plan.frames.map(\.minY)).count, 3)
        // The existing selected comparison, stepper, key and Details are unchanged.
        XCTAssertNil(input.chartKey)
        XCTAssertEqual(input.positionText, "6+ · 5 of 9")
        XCTAssertEqual(input.detailsAction(canOpenDetails: true), .details(Self.key(4)))
    }

    func testStripOnAQuantityStripStillShowsEveryOriginalInWords() {
        let rows = (0..<9).map { Self.row($0, before: .some(nil), result: $0 <= 3 ? .reached("Reached") : .missed("Missed")) }
        let input = Self.input(.final, rows, actual: Self.finalFive)
        XCTAssertTrue(input.isQuantityStrip)
        let entries = input.stripEntries
        XCTAssertEqual(entries.count, 9)
        XCTAssertTrue(entries.allSatisfy { $0.pregame == .missing("Unavailable") })
        XCTAssertFalse(entries.contains { $0.pregameMark || $0.currentMark })
        XCTAssertEqual(entries[3].second, .result(.reached("Reached")))
        XCTAssertEqual(entries[4].second, .result(.missed("Missed")))
    }

    // MARK: Hull City–Everton goal outlook (opt-in probability stems)

    // ARCHIVED from `shipping-adoption-20261027/HULL-GOAL-OUTLOOK-RETAINED-CASES.json`
    // (sha256 4a87773b…d9637), event 15311089, commence 2026-10-11T13:00:00Z:
    //   totals:0 Over 0.5  → 1+ · 0.915  @ 04:30:03.087634Z · absent from the final capture
    //   totals:1 Over 1.5  → 2+ · 0.735  @ 00:44:02.148003Z · final Won (api_settlement)
    //   totals:3 Under 3.5 → 4+ · raw 0.055, clock capped_to_sibling → no pregame mark · absent
    //   totals:4 Under 4.5 → 5+ · raw 0.055, clock capped_to_sibling → no pregame mark · unconfirmed
    //   totals:6 Under 6.5 → 7+ · 0.0135 @ 03:03:47.775761Z · unconfirmed
    //   totals:7 Under 7.5 → 8+ · 0.0065 @ 03:50:45.297728Z · unconfirmed
    //   totals:8 Under 8.5 → 9+ · 0.003  @ 02:53:47.910032Z · unconfirmed
    //   (all clocks 2026-10-11, UTC). Final Hull 2–2 Everton, 4 goals, ESPN observed
    //   2026-10-11T18:58:58.746035Z. Each value is the owner's over-axis reading of
    //   "at least N goals", never the chance of the original Under contract. No 3+ or 6+
    //   is offered. No in-game chance, live count, result-arrival time or projection is
    //   retained; latest quotes are not current. The 1,2,4,5,7,8,9 coordinates and the
    //   performance lines are the owner's, copied from the packet, never derived here.
    // CONSTRUCTED: every display string ("91.5%", "1.4%", …), PT clock and detail line,
    // the "Original … : result unconfirmed / won" wording, the in-game chances, live
    // count and their words, and the zero, 100%, invalid, overlap and enlarged cases.

    private typealias HullCase = (key: Int, quantity: Double, original: String, probability: Double?, text: String,
                                  clock: String, at: String)

    private static let hull: [HullCase] = [
        (0, 1, "Over 0.5", 0.915, "91.5%", "9:30 PM", "2026-10-11T04:30:03.087634Z"),
        (1, 2, "Over 1.5", 0.735, "73.5%", "5:44 PM", "2026-10-11T00:44:02.148003Z"),
        (3, 4, "Under 3.5", nil, "", "", ""),
        (4, 5, "Under 4.5", nil, "", "", ""),
        (6, 7, "Under 6.5", 0.0135, "1.4%", "8:03 PM", "2026-10-11T03:03:47.775761Z"),
        (7, 8, "Under 7.5", 0.0065, "0.7%", "8:50 PM", "2026-10-11T03:50:45.297728Z"),
        (8, 9, "Under 8.5", 0.003, "0.3%", "7:53 PM", "2026-10-11T02:53:47.910032Z"),
    ]
    private static func hullKey(_ original: Int) -> String { "soccer-15311089-game-markets.json:totals:\(original)" }
    private static let hullIDs = hull.map { hullKey($0.key) }
    private static let hullMissing = "Verified pre-match observation time unavailable"
    private static let hullNoCurrent = TotalMilestoneCurrent10868.unavailable("Current chance unavailable")
    private static let hullWon = TotalMilestoneResult10868.reached("Original Over 1.5: won")
    private static let hullPerformance = [
        "Actual final 4 goals; 1+ milestone reached; this is performance, not settlement",
        "Actual final 4 goals; 2+ milestone reached; this is performance, not settlement",
        "Actual final 4 goals; 4+ milestone reached; this is performance, not settlement",
        "Actual final 4 goals; 5+ milestone not reached; this is performance, not settlement",
        "Actual final 4 goals; 7+ milestone not reached; this is performance, not settlement",
        "Actual final 4 goals; 8+ milestone not reached; this is performance, not settlement",
        "Actual final 4 goals; 9+ milestone not reached; this is performance, not settlement",
    ]

    private static func hullDetail(_ saved: HullCase) -> String {
        "Oct 10, \(saved.clock) PT · Polymarket · original \(saved.original) · pin \(saved.at)"
    }

    private static func hullPregame(_ index: Int) -> TotalMilestoneObservation10868? {
        let saved = hull[index]
        return saved.probability.map { obs($0, saved.text, saved.clock, hullDetail(saved)) }
    }

    private static func hullRow(
        _ index: Int,
        before: TotalMilestoneObservation10868?? = nil,
        current: TotalMilestoneCurrent10868 = hullNoCurrent,
        performance: String? = nil,
        result: TotalMilestoneResult10868? = nil
    ) -> TotalMilestoneRow10868 {
        let saved = hull[index]
        let label = "\(Int(saved.quantity))+"
        return TotalMilestoneRow10868(
            id: hullKey(saved.key),
            quantity: saved.quantity,
            quantityLabel: label,
            title: "\(label) total goals",
            before: before ?? hullPregame(index),
            beforeMissing: hullMissing,
            current: current,
            performance: performance,
            result: result ?? .unconfirmed("Original \(saved.original): result unconfirmed")
        )
    }

    private static func hullInput(
        _ phase: TotalMilestonePhase10868,
        _ rows: [TotalMilestoneRow10868],
        selected: String? = hullKey(1),
        actual: TotalMilestoneActual10868? = nil,
        style: TotalMilestoneMarkStyle10868 = .stems
    ) -> TotalMilestoneInput10868 {
        TotalMilestoneInput10868(
            phase: phase, eyebrow: "BOTH TEAMS · FULL MATCH", title: "How many goals?",
            chartTitle: "Chance of at least each goal total", quantityAxisTitle: "Total goals in the match",
            milestones: rows, selectedMilestoneID: selected, actual: actual, projection: nil,
            quantityDomain: nil,
            quantityTicks: hull.map { TotalMilestoneTick10868(value: $0.quantity, text: "\(Int($0.quantity))+") },
            chanceTicks: chanceTicks, timing: nil, markStyle: style
        )
    }

    /// Final: only Over 1.5 is independently Won; the latest quotes (1.0 for
    /// Over 1.5, 0.0005 for the matched Unders) are supplied as a "current" to
    /// prove none becomes a chance.
    private static var hullFinal: [TotalMilestoneRow10868] {
        let latest: [Double?] = [nil, 1.0, nil, 0.0005, 0.0005, 0.0005, 0.0005]
        return (0..<7).map { i in
            let current: TotalMilestoneCurrent10868 = latest[i].map { quote -> TotalMilestoneCurrent10868 in
                .recorded(obs(quote, quote == 1 ? "100%" : "0.05%", "Latest", "latest quote, not current"), movement: nil)
            } ?? hullNoCurrent
            return hullRow(i, current: current, performance: hullPerformance[i], result: i == 1 ? hullWon : nil)
        }
    }

    private static let hullFinalFour = count(4, "4", clock: "Final · 11:58 AM", rule: "Final 4",
                                             detail: "Hull City 2–2 Everton, observed Oct 11, 11:58 AM PT · ESPN")
    private static let hullStemsSentence =
        "Each stem rises from the zero line to one pregame mark; the marks are separate readings, not a curve."

    func testHullStemsAreOptInAndEveryExistingConsumerKeepsPlainMarks() {
        let rows = (0..<7).map { Self.hullRow($0) }
        let dots = Self.hullInput(.before, rows, style: .dots)
        let stems = Self.hullInput(.before, rows)
        let dotModel = try! XCTUnwrap(dots.plotModel(size: Self.size, inset: Self.inset))
        let stemModel = try! XCTUnwrap(stems.plotModel(size: Self.size, inset: Self.inset))
        XCTAssertTrue(dotModel.stems.isEmpty)
        XCTAssertEqual(stemModel.stems.count, 5)
        XCTAssertEqual(dotModel.marks, stemModel.marks, "stems add no mark and move none")
        XCTAssertEqual(dotModel.gridlines, stemModel.gridlines)
        XCTAssertEqual(dotModel.baselineY, stemModel.baselineY)
        XCTAssertEqual(dots.domain, stems.domain)
        XCTAssertFalse(dots.accessibilityChartLabel.contains("stem"))
        XCTAssertTrue(stems.accessibilityChartLabel.contains(Self.hullStemsSentence))
        // The existing hockey and Valladolid consumers pass no style and draw no stems.
        let hockey = Self.input(.during, Self.updatedStage, actual: Self.fourSoFar)
        XCTAssertEqual(hockey.markStyle, .dots)
        XCTAssertTrue(try! XCTUnwrap(hockey.plotModel(size: Self.size, inset: Self.inset)).stems.isEmpty)
        let valladolid = Self.soccerInput(.final, Self.soccerFinal, actual: Self.soccerFive)
        XCTAssertEqual(valladolid.markStyle, .dots)
        XCTAssertTrue(try! XCTUnwrap(valladolid.plotModel(size: Self.size, inset: Self.inset)).stems.isEmpty)
    }

    func testHullBeforeKeepsSevenOriginalsFiveStemsAndNoMarkForTheCappedPair() {
        // Later inputs supplied to prove they stay hidden before play.
        let rows = (0..<7).map { i in
            Self.hullRow(i, current: .recorded(Self.obs(0.9, "90%", "11:58 AM", "constructed later"), movement: "Movement"),
                         performance: Self.hullPerformance[i], result: .reached("Constructed later result"))
        }
        let input = Self.hullInput(.before, rows, actual: Self.hullFinalFour)
        XCTAssertEqual(input.milestones.map(\.id), Self.hullIDs, "seven exact originals, owner order")
        XCTAssertEqual(input.milestones.map(\.quantity), [1, 2, 4, 5, 7, 8, 9])
        XCTAssertFalse(input.milestones.contains { $0.quantity == 3 || $0.quantity == 6 }, "no 3+ or 6+ is offered or inferred")
        XCTAssertFalse(input.milestones.contains { $0.quantityLabel == "3+" || $0.quantityLabel == "6+" })
        let entries = input.stripEntries
        XCTAssertEqual(entries.map(\.milestone.title),
                       ["1+ total goals", "2+ total goals", "4+ total goals", "5+ total goals", "7+ total goals",
                        "8+ total goals", "9+ total goals"])
        for (index, entry) in entries.enumerated() {
            let saved = Self.hull[index]
            if let probability = saved.probability {
                XCTAssertEqual(entry.pregame, .value(Self.obs(probability, saved.text, saved.clock, Self.hullDetail(saved))))
                XCTAssertTrue(input.accessibilityStripValue(entry).contains(saved.at), "each baseline keeps its own clock")
            } else {
                XCTAssertEqual(entry.pregame, .missing(Self.hullMissing), "\(saved.original): capped clock, no baseline")
            }
            XCTAssertNil(entry.second, "no current, actual or result before play")
            let spoken = input.accessibilityStripValue(entry)
            XCTAssertFalse(spoken.contains("5.5%"), "the capped raw 0.055 is evidence only, never shown")
            XCTAssertFalse(spoken.contains("90%"))
            XCTAssertFalse(spoken.contains("Constructed later result"))
        }
        XCTAssertEqual(Set(Self.hull.compactMap { $0.probability == nil ? nil : $0.at }).count, 5, "five distinct recorded clocks")
        XCTAssertNil(input.beforeFraction(input.milestones[2]))
        XCTAssertNil(input.beforeFraction(input.milestones[3]))

        let model = try! XCTUnwrap(input.plotModel(size: Self.size, inset: Self.inset))
        XCTAssertEqual(model.marks.map(\.index), [0, 1, 4, 5, 6])
        XCTAssertTrue(model.marks.allSatisfy { $0.kind == .pregame })
        XCTAssertEqual(model.stems.map(\.index), [0, 1, 4, 5, 6], "4+ and 5+ have no mark and no stem")
        let zero = try! XCTUnwrap(TotalMilestoneGeometry10868.y(0, height: Self.size.height, inset: Self.inset))
        for (stem, mark) in zip(model.stems, model.marks) {
            XCTAssertEqual(stem.x, mark.point.x, "a stem shares its mark's x")
            XCTAssertEqual(stem.markY, mark.point.y, "and ends at its mark")
            XCTAssertEqual(stem.baselineY, zero, "from the 0% line")
        }
        XCTAssertEqual(model.stems.map(\.markY),
                       [0.915, 0.735, 0.0135, 0.0065, 0.003].map { TotalMilestoneGeometry10868.y($0, height: Self.size.height, inset: Self.inset)! },
                       "the five raw admitted values on the fixed scale, never complemented or rescaled")
        // Later inputs stay hidden.
        XCTAssertNil(input.actualPresentation)
        XCTAssertNil(model.actualX)
        XCTAssertNil(input.performance(input.milestones[2]))
        XCTAssertNil(input.chartKey, "the selected 2+ ring names the hollow series")
    }

    func testHullAtLeastChanceIsNotTheOriginalUnderContract() {
        let input = Self.hullInput(.final, Self.hullFinal, selected: Self.hullKey(6), actual: Self.hullFinalFour)
        let seven = try! XCTUnwrap(input.selection.milestone)
        XCTAssertEqual(seven.title, "7+ total goals", "the chance names the milestone")
        XCTAssertEqual(input.beforeFraction(seven), 0.0135, "the owner's at-least reading, never the Under's complement")
        XCTAssertEqual(input.secondReading(seven), .result(.unconfirmed("Original Under 6.5: result unconfirmed")))
        XCTAssertEqual(input.accessibilityComparison(for: seven),
                       "Pregame chance: 1.4%, Oct 10, 8:03 PM PT · Polymarket · original Under 6.5 · pin 2026-10-11T03:03:47.775761Z; Final result: Original Under 6.5: result unconfirmed; Actual final 4 goals; 7+ milestone not reached; this is performance, not settlement")
        // 4 goals reached 4+, but the original Under 3.5 result stays unconfirmed.
        let four = input.milestones[2]
        guard case .result(let result)? = input.secondReading(four) else { return XCTFail("result expected") }
        XCTAssertFalse(result.isAdmitted, "a reached milestone is not an original win")
        XCTAssertEqual(result.text, "Original Under 3.5: result unconfirmed")
        XCTAssertEqual(input.performance(four), "Actual final 4 goals; 4+ milestone reached; this is performance, not settlement")
        XCTAssertEqual(input.milestones.filter { $0.result.isAdmitted }.map(\.id), [Self.hullKey(1)],
                       "no Under result is attached to any milestone")
        XCTAssertEqual(input.detailsAction(canOpenDetails: true), .details(Self.hullKey(6)), "Details opens the exact original Under 6.5")
    }

    func testHullFinalSixUnconfirmedOneWonStemsAndTheSeparateFinalFour() {
        let input = Self.hullInput(.final, Self.hullFinal, actual: Self.hullFinalFour)
        let results = input.stripEntries.compactMap { entry -> TotalMilestoneResult10868? in
            if case .result(let result)? = entry.second { return result }
            return nil
        }
        XCTAssertEqual(results.count, 7)
        XCTAssertEqual(results[1], Self.hullWon)
        XCTAssertEqual(results.filter { !$0.isAdmitted }.count, 6, "six original results unconfirmed")
        XCTAssertEqual(input.actualPresentation?.title, "Final count")
        XCTAssertEqual(input.visibleActualQuantity, 4)
        XCTAssertEqual(input.annotations.map(\.kind), [.selection, .actual])
        XCTAssertEqual(input.annotations.last?.text, "Final 4")
        XCTAssertEqual(input.accessibilityActual(try! XCTUnwrap(input.actualPresentation)),
                       "4 goals, Hull City 2–2 Everton, observed Oct 11, 11:58 AM PT · ESPN")
        XCTAssertNil(input.visibleProjection, "no projection is admitted")

        let model = try! XCTUnwrap(input.plotModel(size: Self.size, inset: Self.inset))
        XCTAssertEqual(model.stems.count, 5, "the pregame stems stay after the final")
        XCTAssertTrue(model.marks.allSatisfy { $0.kind == .pregame }, "no latest quote becomes a current mark")
        XCTAssertNil(model.projectionX)
        let domain = try! XCTUnwrap(input.domain)
        XCTAssertEqual(model.actualX, TotalMilestoneGeometry10868.x(4, domain: domain, width: Self.size.width, inset: Self.inset))
        XCTAssertFalse(model.stems.contains { $0.x == model.actualX }, "4+ has no admitted baseline; the rule stands alone")
        for entry in input.stripEntries {
            let spoken = input.accessibilityStripValue(entry)
            XCTAssertFalse(spoken.contains("100%"))
            XCTAssertFalse(spoken.contains("0.05%"))
            XCTAssertFalse(spoken.contains("Latest"))
            XCTAssertFalse(entry.currentMark)
        }
        let two = try! XCTUnwrap(input.selection.milestone)
        XCTAssertEqual(input.beforeReading(two), .value(try! XCTUnwrap(Self.hullPregame(1))))
        XCTAssertEqual(input.secondReading(two), .result(Self.hullWon))
        XCTAssertEqual(input.performance(two), Self.hullPerformance[1])
        XCTAssertNil(input.chartKey, "the selected 2+ ring names the hollow series")
    }

    func testHullAbsentOriginalsStayReachableWithTheirExactActions() {
        // totals:0 (Over 0.5) and totals:3 (Under 3.5) are absent from the final capture.
        let input = Self.hullInput(.final, Self.hullFinal, selected: Self.hullKey(3), actual: Self.hullFinalFour)
        XCTAssertEqual(input.stripEntries.count, 7)
        XCTAssertEqual((0..<7).map { input.stripAction(index: $0, canSelect: true) },
                       Self.hullIDs.map { TotalMilestoneAction10868?.some(.select($0)) })
        XCTAssertEqual(input.selection.index, 2)
        XCTAssertEqual(input.positionText, "4+ · 3 of 7")
        XCTAssertEqual(input.stepAction(-1, canSelect: true), .select(Self.hullKey(1)))
        XCTAssertEqual(input.stepAction(1, canSelect: true), .select(Self.hullKey(4)))
        XCTAssertEqual(input.detailsAction(canOpenDetails: true), .details(Self.hullKey(3)))
        var selected: [String] = []
        var details: [String] = []
        input.stripAction(index: 0, canSelect: true)?.perform(onSelect: { selected.append($0) }, onDetails: { details.append($0) })
        input.detailsAction(canOpenDetails: true)?.perform(onSelect: { selected.append($0) }, onDetails: { details.append($0) })
        XCTAssertEqual(selected, [Self.hullKey(0)])
        XCTAssertEqual(details, [Self.hullKey(3)])
        XCTAssertNil(input.stripAction(index: 0, canSelect: false), "no callback, no action")
        XCTAssertNil(input.detailsAction(canOpenDetails: false))

        // The withheld 4+ is selectable, in words, with no mark, ring or stem.
        let four = try! XCTUnwrap(input.selection.milestone)
        let model = try! XCTUnwrap(input.plotModel(size: Self.size, inset: Self.inset))
        let domain = try! XCTUnwrap(input.domain)
        XCTAssertEqual(model.selectionX, TotalMilestoneGeometry10868.x(4, domain: domain, width: Self.size.width, inset: Self.inset))
        XCTAssertFalse(model.marks.contains(where: \.selected))
        XCTAssertFalse(model.stems.contains { $0.index == 2 })
        XCTAssertEqual(input.chartKey, Self.pregameKey, "no ring names the hollow series, so the key does")
        XCTAssertEqual(input.accessibilityComparison(for: four),
                       "Pregame chance: Verified pre-match observation time unavailable; Final result: Original Under 3.5: result unconfirmed; Actual final 4 goals; 4+ milestone reached; this is performance, not settlement")

        // Seven originals at phone width: three columns, nothing hidden; one column at accessibility sizes.
        let columns = TotalMilestoneGeometry10868.stripColumns(count: 7, width: 327, spacing: 8, minimumCellWidth: 96) { $0 >= 100 }
        XCTAssertEqual(columns, 3)
        let cell = TotalMilestoneGeometry10868.stripCellWidth(columns: columns, width: 327, spacing: 8)
        let plan = TotalMilestoneGeometry10868.stripFrames(columns: columns, cellWidth: cell, heights: Array(repeating: 96, count: 7), spacing: 8)
        XCTAssertEqual(plan.frames.count, 7)
        XCTAssertEqual(Set(plan.frames.map(\.minY)).count, 3)
        XCTAssertEqual(TotalMilestoneGeometry10868.stripColumns(count: 7, width: 327, spacing: 8, minimumCellWidth: 96,
                                                                maximumColumns: 1) { _ in true }, 1)
    }

    func testHullDuringConstructedChancesStayApartFromStemsAndTheCount() {
        // CONSTRUCTED: no in-game chance or live count is retained for this match.
        let live = Self.count(2, "2", clock: "52'", rule: "2 so far", detail: "constructed: as of Oct 11, 6:52 AM PT, 52nd minute")
        let reading = { (p: Double, text: String) in Self.obs(p, text, "6:52 AM", "Oct 11, 6:52 AM PT · constructed") }
        let rows = [
            Self.hullRow(0, current: .reached("Reached")),
            Self.hullRow(1, current: .reached("Reached")),
            Self.hullRow(2, current: .withheld("No update since goal")),
            Self.hullRow(3),
            Self.hullRow(4, current: .recorded(reading(0.04, "4%"), movement: "Up since pregame")),
            Self.hullRow(5, current: .recorded(reading(0.02, "2%"), movement: nil)),
            Self.hullRow(6),
        ]
        let input = Self.hullInput(.during, rows, selected: Self.hullKey(6), actual: live)
        let seven = try! XCTUnwrap(input.selection.milestone)
        XCTAssertEqual(input.beforeReading(seven), .value(try! XCTUnwrap(Self.hullPregame(4))))
        XCTAssertEqual(input.secondReading(seven), .current(.chance(reading(0.04, "4%"))))
        XCTAssertTrue(input.showsCurrentKey(seven))
        XCTAssertNil(input.result(seven))
        XCTAssertEqual(input.actualPresentation?.title, "Count so far")
        XCTAssertEqual(input.visibleActualQuantity, 2)
        XCTAssertNil(input.chartKey, "the selected comparison names both series")

        let model = try! XCTUnwrap(input.plotModel(size: Self.size, inset: Self.inset))
        XCTAssertEqual(model.stems.map(\.index), [0, 1, 4, 5, 6], "stems follow the pregame marks only")
        let current = model.marks.filter { $0.kind == .current }
        XCTAssertEqual(current.map(\.index), [4, 5])
        for mark in current {
            let stem = try! XCTUnwrap(model.stems.first { $0.index == mark.index })
            let pregame = try! XCTUnwrap(model.marks.first { $0.index == mark.index && $0.kind == .pregame })
            XCTAssertEqual(stem.x, mark.point.x, "the same quantity")
            XCTAssertEqual(stem.markY, pregame.point.y, "the stem ends at the pregame mark")
            XCTAssertNotEqual(stem.markY, mark.point.y, "never at the in-game one")
        }
        let entries = input.stripEntries
        XCTAssertEqual(entries[0].second, .current(.actual("Reached")), "reached is performance")
        XCTAssertEqual(entries[2].second, .current(.chanceStatus("No update since goal")))
        XCTAssertEqual(entries[3].second, .current(.chanceStatus("Current chance unavailable")), "missing current stays explicit")
        XCTAssertEqual(entries[3].pregame, .missing(Self.hullMissing))
        XCTAssertFalse(entries[3].pregameMark)
        XCTAssertTrue(entries[4].pregameMark && entries[4].currentMark, "equal hollow and filled keys")
        XCTAssertFalse(input.accessibilityStripValue(entries[0]).contains("won"))
        XCTAssertEqual(input.accessibilityChartLabel,
                       "Chance of at least each goal total Hollow marks are pregame chances. \(Self.hullStemsSentence) Filled marks are recorded in-game chances. The solid rule is the count, not a chance.")
        XCTAssertEqual(input.accessibilityComparison(for: seven),
                       "Pregame chance: 1.4%, Oct 10, 8:03 PM PT · Polymarket · original Under 6.5 · pin 2026-10-11T03:03:47.775761Z; Recorded in-game chance: 4%, Oct 11, 6:52 AM PT · constructed; Change since pregame: Up since pregame")
    }

    func testHullStemGeometryZeroOverlapEndpointsEnlargedAndSelectionInvariant() {
        // CONSTRUCTED: 100% at 1+, a quoted 0% at 4+ (under the final rule), 120% at 5+ and NaN at 7+.
        let rows = [
            Self.hullRow(0, before: .some(Self.obs(1, "100%", nil, "constructed"))),
            Self.hullRow(1),
            Self.hullRow(2, before: .some(Self.obs(0, "0%", nil, "constructed zero"))),
            Self.hullRow(3, before: .some(Self.obs(1.2, "120%", nil, "constructed invalid"))),
            Self.hullRow(4, before: .some(Self.obs(.nan, "—", nil, "constructed invalid"))),
            Self.hullRow(5),
            Self.hullRow(6),
        ]
        let input = Self.hullInput(.final, rows, actual: Self.hullFinalFour)
        // Phone, enlarged plot height, and a narrow plot.
        for size in [Self.size, CGSize(width: 300, height: 260), CGSize(width: 248, height: 180)] {
            let model = try! XCTUnwrap(input.plotModel(size: size, inset: Self.inset))
            let zero = try! XCTUnwrap(TotalMilestoneGeometry10868.y(0, height: size.height, inset: Self.inset))
            XCTAssertEqual(model.stems.map(\.index), [0, 1, 2, 5, 6], "invalid chances have no stem")
            let zeroStem = try! XCTUnwrap(model.stems.first { $0.index == 2 })
            XCTAssertEqual(zeroStem.markY, zeroStem.baselineY, "a quoted 0% keeps its mark, with a zero-length stem")
            XCTAssertTrue(model.marks.contains { $0.index == 2 && $0.point.y == zero })
            XCTAssertEqual(model.actualX, zeroStem.x, "the final rule and the 4+ stem share x; both are kept")
            XCTAssertEqual(model.stems.first { $0.index == 0 }?.markY ?? 0, Self.inset, accuracy: 0.001, "100% at the top inset")
            for stem in model.stems {
                let mark = try! XCTUnwrap(model.marks.first { $0.index == stem.index && $0.kind == .pregame })
                XCTAssertEqual(CGPoint(x: stem.x, y: stem.markY), mark.point)
                XCTAssertEqual(stem.baselineY, model.baselineY)
                XCTAssertLessThanOrEqual(stem.markY, stem.baselineY)
                XCTAssertGreaterThanOrEqual(stem.x, Self.inset - 0.001)
                XCTAssertLessThanOrEqual(stem.x, size.width - Self.inset + 0.001)
                XCTAssertGreaterThanOrEqual(stem.markY, Self.inset - 0.001)
                XCTAssertLessThanOrEqual(stem.baselineY, size.height - Self.inset + 0.001)
            }
        }
        // A selection, none, or a missing one never moves a stem or the domain.
        let selections: [String?] = [Self.hullKey(0), Self.hullKey(8), nil, "soccer-15311089-game-markets.json:totals:2"]
        let inputs = selections.map { Self.hullInput(.final, rows, selected: $0, actual: Self.hullFinalFour) }
        let stems = inputs.map { $0.plotModel(size: Self.size, inset: Self.inset)!.stems }
        XCTAssertEqual(stems[0], stems[1])
        XCTAssertEqual(stems[1], stems[2])
        XCTAssertEqual(stems[2], stems[3])
        XCTAssertTrue(inputs.allSatisfy { $0.domain == TotalMilestoneDomain10868(lower: 1, upper: 9) })
    }

    func testHullQuantityStripHasNoStems() {
        let rows = (0..<7).map { Self.hullRow($0, before: .some(nil)) }
        for phase in [TotalMilestonePhase10868.before, .during, .final] {
            let input = Self.hullInput(phase, rows, actual: phase == .final ? Self.hullFinalFour : nil)
            XCTAssertTrue(input.isQuantityStrip, "\(phase)")
            let model = try! XCTUnwrap(input.plotModel(size: CGSize(width: 300, height: 40), inset: Self.inset))
            XCTAssertTrue(model.isStrip)
            XCTAssertTrue(model.stems.isEmpty, "\(phase): no probability, no stem")
            XCTAssertTrue(model.marks.isEmpty)
            XCTAssertEqual(model.milestoneTicks.count, 7)
            XCTAssertFalse(input.accessibilityChartLabel.contains("stem"))
            XCTAssertEqual(input.stripEntries.count, 7, "every original stays")
        }
    }

    func testHullSpokenTextNamesStemsBaselinesResultsAndPerformanceApart() {
        let before = Self.hullInput(.before, (0..<7).map { Self.hullRow($0) })
        XCTAssertEqual(before.accessibilityChartLabel,
                       "Chance of at least each goal total Hollow marks are pregame chances. \(Self.hullStemsSentence)")
        XCTAssertEqual(before.accessibilityChartValue,
                       "2+ total goals. Pregame chance: 73.5%, Oct 10, 5:44 PM PT · Polymarket · original Over 1.5 · pin 2026-10-11T00:44:02.148003Z")
        XCTAssertEqual(before.accessibilityStripValue(before.stripEntries[3]),
                       "Pregame chance: Verified pre-match observation time unavailable")

        let final = Self.hullInput(.final, Self.hullFinal, actual: Self.hullFinalFour)
        XCTAssertEqual(final.accessibilityHeader, "BOTH TEAMS · FULL MATCH. How many goals?. Final")
        XCTAssertEqual(final.accessibilityChartLabel,
                       "Chance of at least each goal total Hollow marks are pregame chances. \(Self.hullStemsSentence) The solid rule is the count, not a chance.")
        XCTAssertEqual(final.accessibilityStripValue(final.stripEntries[3]),
                       "Pregame chance: Verified pre-match observation time unavailable; Final result: Original Under 4.5: result unconfirmed")
        XCTAssertEqual(final.accessibilityStripValue(final.stripEntries[1]),
                       "Pregame chance: 73.5%, Oct 10, 5:44 PM PT · Polymarket · original Over 1.5 · pin 2026-10-11T00:44:02.148003Z; Final result: Original Over 1.5: won")
        XCTAssertEqual(final.accessibilityChartValue,
                       "2+ total goals. Pregame chance: 73.5%, Oct 10, 5:44 PM PT · Polymarket · original Over 1.5 · pin 2026-10-11T00:44:02.148003Z; Final result: Original Over 1.5: won; Actual final 4 goals; 2+ milestone reached; this is performance, not settlement")
        // Each baseline keeps its own clock, and the count keeps its own.
        let clocks = final.stripEntries.compactMap { entry -> String? in
            if case .value(let observation) = entry.pregame { return observation.accessibilityDetail }
            return nil
        }
        XCTAssertEqual(Set(clocks).count, 5)
        XCTAssertFalse(clocks.contains { $0.contains("11:58") })
        XCTAssertTrue(final.accessibilityActual(try! XCTUnwrap(final.actualPresentation)).contains("11:58 AM PT"))
    }

    // MARK: Explicit original-contract results (#10868 R1)
    // CONSTRUCTED display cases only: no captured settlement backs any won or
    // lost below, and no production binding is credited.

    private static let contractFinalOne = count(1, "1", clock: "Final · constructed", rule: "Final 1",
                                                detail: "constructed final 1, not a capture")
    private static let contractFinalFive = count(5, "5", clock: "Final · constructed", rule: "Final 5",
                                                 detail: "constructed final 5, not a capture")
    private static let contractFinalEight = count(8, "8", clock: "Final · constructed", rule: "Final 8",
                                                  detail: "constructed final 8, not a capture")
    private static let contractFiveSoFar = count(5, "5", clock: "2nd half · constructed", rule: "5 so far",
                                                 detail: "constructed 5 so far, not a capture")

    /// The seven Hull originals; every result not supplied stays unconfirmed.
    private static func contractInput(
        _ phase: TotalMilestonePhase10868,
        results: [Int: TotalMilestoneResult10868],
        performance: [Int: String] = [:],
        current: [Int: TotalMilestoneCurrent10868] = [:],
        selected: Int,
        actual: TotalMilestoneActual10868?
    ) -> TotalMilestoneInput10868 {
        let rows = (0..<7).map { i in
            hullRow(i, current: current[i] ?? hullNoCurrent, performance: performance[i], result: results[i])
        }
        return hullInput(phase, rows, selected: hullKey(hull[selected].key), actual: actual)
    }

    /// The result a strip entry carries — the same value its glyph is drawn from.
    private static func stripResult(_ entry: TotalMilestoneStripEntry10868) -> TotalMilestoneResult10868? {
        if case .result(let result)? = entry.second { return result }
        return nil
    }

    func testContractResultMarksKeepTheExistingCasesAndTheSevenRetainedOriginals() {
        // The existing cases draw what they drew: a check, a cross, nothing.
        XCTAssertEqual(TotalMilestoneResult10868.reached("Reached").mark, .check)
        XCTAssertEqual(TotalMilestoneResult10868.missed("Missed").mark, .cross)
        XCTAssertNil(TotalMilestoneResult10868.unconfirmed("Result unconfirmed").mark)
        XCTAssertEqual(TotalMilestoneResult10868.won("Original Under 4.5: won").mark, .check)
        XCTAssertEqual(TotalMilestoneResult10868.lost("Original Under 4.5: lost").mark, .cross)
        XCTAssertEqual(TotalMilestoneResult10868.won("Original Under 4.5: won").text, "Original Under 4.5: won")
        XCTAssertEqual(TotalMilestoneResult10868.lost("Original Under 4.5: lost").text, "Original Under 4.5: lost")
        XCTAssertTrue(TotalMilestoneResult10868.won("Won").isAdmitted)
        XCTAssertTrue(TotalMilestoneResult10868.lost("Lost").isAdmitted)
        // The seven retained originals are untouched: only Over 1.5 Won, six unconfirmed.
        let final = Self.hullInput(.final, Self.hullFinal, actual: Self.hullFinalFour)
        let results = final.stripEntries.map(Self.stripResult)
        XCTAssertEqual(results.compactMap { $0 }.count, 7)
        XCTAssertEqual(results[1], Self.hullWon)
        XCTAssertEqual(results.map { $0?.mark }, [nil, .check, nil, nil, nil, nil, nil])
        XCTAssertEqual(results.filter { $0?.isAdmitted == true }.count, 1)
    }

    func testContractUnderWonStaysBesideAFivePlusMilestoneNotReached() {
        let won = TotalMilestoneResult10868.won("Original Under 4.5: won")
        let input = Self.contractInput(.final, results: [3: won], performance: [3: Self.hullPerformance[3]],
                                       selected: 3, actual: Self.hullFinalFour)
        let five = input.milestones[3]
        XCTAssertEqual(five.id, Self.hullKey(4))
        XCTAssertEqual(input.secondReading(five), .result(won), "the selected comparison shows the owner's result")
        let entry = input.stripEntries[3]
        XCTAssertEqual(entry.second, .result(won), "the strip shows the same result")
        XCTAssertEqual(Self.stripResult(entry)?.mark, .check, "a check beside the Under's win, not a cross")
        XCTAssertTrue(won.isAdmitted)
        XCTAssertEqual(input.performance(five),
                       "Actual final 4 goals; 5+ milestone not reached; this is performance, not settlement")
        XCTAssertEqual(input.accessibilityStripValue(entry),
                       "Pregame chance: Verified pre-match observation time unavailable; Final result: Original Under 4.5: won")
        XCTAssertEqual(input.accessibilityChartValue,
                       "5+ total goals. Pregame chance: Verified pre-match observation time unavailable; Final result: Original Under 4.5: won; Actual final 4 goals; 5+ milestone not reached; this is performance, not settlement")
        // Only the supplied result is admitted; nothing is complemented onto a sibling.
        XCTAssertEqual(input.stripEntries.map { Self.stripResult($0)?.mark }, [nil, nil, nil, .check, nil, nil, nil])
        XCTAssertEqual(input.milestones.filter { $0.result.isAdmitted }.map(\.id), [Self.hullKey(4)])
    }

    func testContractUnderLostStaysBesideAFivePlusMilestoneReached() {
        let lost = TotalMilestoneResult10868.lost("Original Under 4.5: lost")
        let reached = "Actual final 5 goals; 5+ milestone reached; this is performance, not settlement"
        let input = Self.contractInput(.final, results: [3: lost], performance: [3: reached],
                                       selected: 3, actual: Self.contractFinalFive)
        let five = input.milestones[3]
        XCTAssertEqual(input.secondReading(five), .result(lost))
        let entry = input.stripEntries[3]
        XCTAssertEqual(entry.second, .result(lost))
        XCTAssertEqual(Self.stripResult(entry)?.mark, .cross, "a cross beside the Under's loss, not a check")
        XCTAssertTrue(lost.isAdmitted)
        XCTAssertEqual(input.performance(five), reached)
        XCTAssertEqual(input.visibleActualQuantity, 5)
        XCTAssertEqual(input.accessibilityActual(try! XCTUnwrap(input.actualPresentation)),
                       "5 goals, constructed final 5, not a capture")
        XCTAssertEqual(input.accessibilityStripValue(entry),
                       "Pregame chance: Verified pre-match observation time unavailable; Final result: Original Under 4.5: lost")
        XCTAssertEqual(input.accessibilityChartValue,
                       "5+ total goals. Pregame chance: Verified pre-match observation time unavailable; Final result: Original Under 4.5: lost; \(reached)")
        XCTAssertEqual(input.stripEntries.map { Self.stripResult($0)?.mark }, [nil, nil, nil, .cross, nil, nil, nil])
    }

    func testContractOverWonAndLostReadLikeTheirWordsAndUnknownHasNoMark() {
        let won = TotalMilestoneResult10868.won("Original Over 1.5: won")
        let overWon = Self.contractInput(.final, results: [1: won], performance: [1: Self.hullPerformance[1]],
                                         selected: 1, actual: Self.hullFinalFour)
        XCTAssertEqual(overWon.secondReading(overWon.milestones[1]), .result(won))
        XCTAssertEqual(overWon.stripEntries[1].second, .result(won))
        XCTAssertEqual(Self.stripResult(overWon.stripEntries[1])?.mark, .check)
        // The retained `.reached` wording of the same win reads and sounds identical.
        let retained = Self.hullInput(.final, Self.hullFinal, actual: Self.hullFinalFour)
        XCTAssertEqual(Self.stripResult(retained.stripEntries[1])?.mark, Self.stripResult(overWon.stripEntries[1])?.mark)
        XCTAssertEqual(retained.accessibilityStripValue(retained.stripEntries[1]),
                       overWon.accessibilityStripValue(overWon.stripEntries[1]))
        XCTAssertEqual(retained.accessibilityChartValue, overWon.accessibilityChartValue)

        let lost = TotalMilestoneResult10868.lost("Original Over 1.5: lost")
        let short = "Actual final 1 goal; 2+ milestone not reached; this is performance, not settlement"
        let overLost = Self.contractInput(.final, results: [1: lost], performance: [1: short],
                                          selected: 1, actual: Self.contractFinalOne)
        XCTAssertEqual(overLost.secondReading(overLost.milestones[1]), .result(lost))
        XCTAssertEqual(overLost.stripEntries[1].second, .result(lost))
        XCTAssertEqual(Self.stripResult(overLost.stripEntries[1])?.mark, .cross)
        XCTAssertEqual(overLost.accessibilityChartValue,
                       "2+ total goals. Pregame chance: 73.5%, Oct 10, 5:44 PM PT · Polymarket · original Over 1.5 · pin 2026-10-11T00:44:02.148003Z; Final result: Original Over 1.5: lost; \(short)")

        let unknown = Self.contractInput(.final, results: [:], performance: [1: Self.hullPerformance[1]],
                                         selected: 1, actual: Self.hullFinalFour)
        let pending = try! XCTUnwrap(Self.stripResult(unknown.stripEntries[1]))
        XCTAssertEqual(pending, .unconfirmed("Original Over 1.5: result unconfirmed"))
        XCTAssertFalse(pending.isAdmitted)
        XCTAssertNil(pending.mark, "unknown gets neither a check nor a cross")
        XCTAssertEqual(unknown.secondReading(unknown.milestones[1]), .result(pending))
        XCTAssertEqual(unknown.accessibilityStripValue(unknown.stripEntries[1]),
                       "Pregame chance: 73.5%, Oct 10, 5:44 PM PT · Polymarket · original Over 1.5 · pin 2026-10-11T00:44:02.148003Z; Final result: Original Over 1.5: result unconfirmed")
        XCTAssertTrue(unknown.stripEntries.allSatisfy { Self.stripResult($0)?.mark == nil })
    }

    func testContractResultIsHiddenBeforeAndDuringPlay() {
        let results: [Int: TotalMilestoneResult10868] = [1: .won("Original Over 1.5: won"),
                                                         3: .lost("Original Under 4.5: lost")]
        for phase in [TotalMilestonePhase10868.before, .during] {
            let input = Self.contractInput(phase, results: results, selected: 3, actual: nil)
            for milestone in input.milestones {
                XCTAssertNil(input.result(milestone), "\(phase): \(milestone.id)")
            }
            XCTAssertTrue(input.stripEntries.allSatisfy { Self.stripResult($0) == nil }, "\(phase)")
            XCTAssertFalse(input.accessibilityChartValue.contains(TotalMilestoneInput10868.resultTitle), "\(phase)")
            for entry in input.stripEntries {
                let spoken = input.accessibilityStripValue(entry)
                XCTAssertFalse(spoken.contains(": won") || spoken.contains(": lost"), "\(phase): \(spoken)")
            }
        }
        let before = Self.contractInput(.before, results: results, selected: 3, actual: nil)
        XCTAssertTrue(before.milestones.allSatisfy { before.secondReading($0) == nil })
        let during = Self.contractInput(.during, results: results, selected: 3, actual: nil)
        XCTAssertEqual(during.secondReading(during.milestones[3]), .current(.chanceStatus("Current chance unavailable")))
    }

    func testContractResultIsIndependentOfInGamePerformance() {
        let lost = TotalMilestoneResult10868.lost("Original Under 4.5: lost")
        let soFar = "5 so far; 5+ milestone reached; this is performance, not settlement"
        // During play the existing in-game Reached stays performance; it is not a contract result.
        let during = Self.contractInput(.during, results: [3: lost], performance: [3: soFar],
                                        current: [3: .reached("Reached")], selected: 3, actual: Self.contractFiveSoFar)
        let five = during.milestones[3]
        XCTAssertEqual(during.currentReading(five), .actual("Reached"))
        XCTAssertEqual(during.secondReading(five), .current(.actual("Reached")))
        XCTAssertNil(during.result(five))
        XCTAssertEqual(during.stripEntries[3].second, .current(.actual("Reached")))
        XCTAssertNil(Self.stripResult(during.stripEntries[3]))
        XCTAssertEqual(during.accessibilityChartValue,
                       "5+ total goals. Pregame chance: Verified pre-match observation time unavailable; Actual so far: Reached; \(soFar)")

        // After the final the owner's result shows, and the in-game Reached is not read.
        let final = Self.contractInput(.final, results: [3: lost], performance: [3: soFar],
                                       current: [3: .reached("Reached")], selected: 3, actual: Self.contractFinalFive)
        XCTAssertNil(final.currentReading(final.milestones[3]))
        XCTAssertEqual(final.secondReading(final.milestones[3]), .result(lost))
        XCTAssertEqual(Self.stripResult(final.stripEntries[3])?.mark, .cross)

        // An Under win beside an in-game Reached that the owner supplied still reads as won.
        let won = TotalMilestoneResult10868.won("Original Under 4.5: won")
        let wonFinal = Self.contractInput(.final, results: [3: won], current: [3: .reached("Reached")],
                                          selected: 3, actual: Self.hullFinalFour)
        XCTAssertEqual(wonFinal.secondReading(wonFinal.milestones[3]), .result(won))
        XCTAssertEqual(Self.stripResult(wonFinal.stripEntries[3])?.mark, .check)
    }

    func testContractGradeDoesNotMoveWhenTheActualChanges() {
        // The owner's grade is shown as given; a different count re-grades nothing.
        let won = TotalMilestoneResult10868.won("Original Under 6.5: won")
        let four = Self.contractInput(
            .final, results: [4: won],
            performance: [4: "Actual final 4 goals; 7+ milestone not reached; this is performance, not settlement"],
            selected: 4, actual: Self.hullFinalFour)
        let eight = Self.contractInput(
            .final, results: [4: won],
            performance: [4: "Actual final 8 goals; 7+ milestone reached; this is performance, not settlement"],
            selected: 4, actual: Self.contractFinalEight)
        XCTAssertEqual(four.secondReading(four.milestones[4]), .result(won))
        XCTAssertEqual(eight.secondReading(eight.milestones[4]), .result(won))
        XCTAssertEqual(four.stripEntries.map(\.second), eight.stripEntries.map(\.second))
        XCTAssertEqual(Self.stripResult(four.stripEntries[4])?.mark, .check)
        XCTAssertEqual(Self.stripResult(eight.stripEntries[4])?.mark, .check)
        XCTAssertEqual(four.accessibilityStripValue(four.stripEntries[4]),
                       eight.accessibilityStripValue(eight.stripEntries[4]))
        // Only the count and the owner's performance line differ.
        XCTAssertNotEqual(four.actualPresentation, eight.actualPresentation)
        XCTAssertEqual(four.visibleActualQuantity, 4)
        XCTAssertEqual(eight.visibleActualQuantity, 8)
        XCTAssertTrue(eight.accessibilityChartValue.hasSuffix("Final result: Original Under 6.5: won; Actual final 8 goals; 7+ milestone reached; this is performance, not settlement"))
    }
}

/// #10868 — after the final, the actual total games beside the opening market
/// line, with every original contract's own pregame chance and result.
///
/// As above, the view is not rasterised, type-checked or run under VoiceOver
/// here. What is asserted is the rules it defers to: the final-only gate, the
/// line's own channel, the selection-independent axis, the exact-id actions,
/// the tick and label planning and the spoken text. Nothing here claims a
/// rendered fit.
///
/// ARCHIVED raw values come from Fokina–Tiafoe, event 15327291, as copied in
/// `shipping-adoption-20261027/TENNIS-TOTAL-GAMES-RETAINED-CASES.json`
/// (sha256 6686d986…dbe2e9):
///   final 2–1 sets, games 18–18, 36 games; ESPN score captured
///     2026-10-11T17:06:47.950466Z
///   opening market line 22.5 games; opening time null; source not proved by
///     the retained field
///   verified start 2026-10-11T12:50:00Z
///   Polymarket Over originals, pregame consensus @ 2026-10-11T12:45:25.328389Z:
///     market 65138607 / outcome 244929349 "Match O/U 21.5" · 0.64  · own result true
///     market 65123147 / outcome 244876655 "Match O/U 22.5" · 0.525 · own result true
///     market 65123148 / outcome 244876657 "Match O/U 23.5" · 0.445 · own result true
///   raw final quote 1.0 each (clob_authoritative), observed 14:06:15.499070Z,
///     14:54:06.778032Z and 14:54:06.778032Z — neither a pregame chance nor a
///     settlement time.
///
/// CONSTRUCTED owner inputs (this leaf does not resolve them): the action ids
/// (the packet's own `constructed_owner_action_id`), the owner-qualified
/// coordinates 22/23/24 for the discrete Over 21.5/22.5/23.5 contracts, every
/// display string, PT clock and detail line, the "Won" words, the 0–40 domain
/// and ticks, the opening-line words, label and note, the "+13.5" difference
/// words, and every missing, invalid, blank, repeated, withdrawn, NaN,
/// coincident and long-text case.
final class TotalMilestoneLineComparison10868Tests: XCTestCase {

    // MARK: Retained owner associations — explicit, never a fallback

    private struct RetainedOriginal {
        let actionID: String
        let marketID: Int
        let outcomeID: Int
        /// The owner's title naming the original's own literal threshold.
        let title: String
        /// The owner-qualified discrete coordinate; never derived here.
        let coordinate: Double
        let label: String
        let pregame: Double
        let pregameText: String
        let finalQuote: Double
        let quoteClock: String
    }

    private static let retained: [RetainedOriginal] = [
        RetainedOriginal(actionID: "constructed:15327291:polymarket:65138607:244929349", marketID: 65138607, outcomeID: 244929349,
                         title: "Over 21.5 games", coordinate: 22, label: "22+", pregame: 0.64, pregameText: "64%",
                         finalQuote: 1.0, quoteClock: "7:06 AM"),
        RetainedOriginal(actionID: "constructed:15327291:polymarket:65123147:244876655", marketID: 65123147, outcomeID: 244876655,
                         title: "Over 22.5 games", coordinate: 23, label: "23+", pregame: 0.525, pregameText: "52.5%",
                         finalQuote: 1.0, quoteClock: "7:54 AM"),
        RetainedOriginal(actionID: "constructed:15327291:polymarket:65123148:244876657", marketID: 65123148, outcomeID: 244876657,
                         title: "Over 23.5 games", coordinate: 24, label: "24+", pregame: 0.445, pregameText: "44.5%",
                         finalQuote: 1.0, quoteClock: "7:54 AM"),
    ]
    private static let retainedIDs = retained.map(\.actionID)
    /// 12:45:25Z is 5:45 AM PDT; the verified 12:50Z start is 5:50 AM PDT.
    private static let pregameClock = "5:45 AM"
    private static let pregameDetail = "Oct 11, 5:45 AM PT · Polymarket consensus · before the verified 5:50 AM PT start"
    private static let missingWords = "Unavailable"
    private static let won = TotalMilestoneResult10868.won("Won")
    private static let noCurrent = TotalMilestoneCurrent10868.unavailable("No in-game reading")

    private static func obs(_ probability: Double, _ text: String, _ time: String?, _ detail: String) -> TotalMilestoneObservation10868 {
        TotalMilestoneObservation10868(probability: probability, text: text, timeText: time, accessibilityDetail: detail)
    }

    /// Original `index`'s own retained pregame observation and clock.
    private static func retainedPregame(_ index: Int) -> TotalMilestoneObservation10868 {
        let saved = retained[index]
        return obs(saved.pregame, saved.pregameText, pregameClock, pregameDetail)
    }

    /// Original `index`, every field from its own retained association.
    private static func retainedRow(
        _ index: Int,
        before: TotalMilestoneObservation10868?? = nil,
        current: TotalMilestoneCurrent10868 = noCurrent,
        result: TotalMilestoneResult10868 = won
    ) -> TotalMilestoneRow10868 {
        let saved = retained[index]
        return TotalMilestoneRow10868(
            id: saved.actionID,
            quantity: saved.coordinate,
            quantityLabel: saved.label,
            title: saved.title,
            before: before ?? retainedPregame(index),
            beforeMissing: missingWords,
            current: current,
            performance: nil,
            result: result
        )
    }

    private static var retainedRows: [TotalMilestoneRow10868] { (0..<3).map { retainedRow($0) } }

    /// A constructed original: every field passed, nothing borrowed from the retained packet.
    private static func constructedRow(id: String, title: String, quantity: Double,
                                       before: TotalMilestoneObservation10868?,
                                       result: TotalMilestoneResult10868 = .unconfirmed("Result unconfirmed")) -> TotalMilestoneRow10868 {
        TotalMilestoneRow10868(id: id, quantity: quantity, quantityLabel: "constructed", title: title, before: before,
                               beforeMissing: missingWords, current: noCurrent, performance: nil, result: result)
    }

    /// 36 games; 17:06:47Z is 10:06 AM PDT. The capture is not the finish time.
    private static let retainedActual = TotalMilestoneActual10868.count(TotalMilestoneCount10868(
        quantity: 36, text: "36", unit: "games", clock: "Score captured 10:06 AM", ruleLabel: "36 actual",
        accessibilityDetail: "Fokina 2–1 Tiafoe in sets, games 18–18 · ESPN score captured Oct 11, 10:06 AM PT"))

    private static func constructedCount(_ quantity: Double, _ text: String) -> TotalMilestoneActual10868 {
        .count(TotalMilestoneCount10868(quantity: quantity, text: text, unit: "games", clock: nil,
                                        ruleLabel: "\(text) actual", accessibilityDetail: "constructed count"))
    }

    /// 22.5 games, opening time unknown in the retained field.
    private static let retainedLine = constructedLine(quantity: 22.5, time: .unknown("Opening time unavailable"))

    private static func constructedLine(quantity: Double, time: TotalMilestoneLineTime10868) -> TotalMilestoneOpeningLine10868 {
        TotalMilestoneOpeningLine10868(quantity: quantity, text: "22.5", unit: "games", title: "Opening market line",
                                       markLabel: "22.5 opening", time: time,
                                       note: "A market threshold, not a projected score",
                                       accessibilityDetail: "opening source not recorded")
    }

    private static let retainedDifference = TotalMilestoneLineDifference10868(
        figure: "+13.5", caption: "games above opening line", spoken: "+13.5 games above the opening line")
    private static let retainedDomain = TotalMilestoneDomain10868(lower: 0, upper: 40)
    private static let gameTicks = [0.0, 10, 20, 30, 40].map { TotalMilestoneTick10868(value: $0, text: "\(Int($0))") }
    private static let invitationWords = "Choose a contract to see its pregame chance"
    private static let plotSize = CGSize(width: 327, height: 36)
    private static let inset = TotalMilestoneGeometry10868.plotInset

    private static func comparison(
        _ phase: TotalMilestonePhase10868 = .final,
        rows: [TotalMilestoneRow10868] = retainedRows,
        selected: String? = retainedIDs[1],
        actual: TotalMilestoneActual10868? = retainedActual,
        projection: TotalMilestoneProjection10868? = nil,
        domain: TotalMilestoneDomain10868? = retainedDomain,
        ticks: [TotalMilestoneTick10868] = gameTicks,
        timing: TotalMilestoneTiming10868? = nil,
        line: TotalMilestoneOpeningLineState10868 = .line(retainedLine),
        difference: TotalMilestoneLineDifference10868? = retainedDifference,
        shareUnit: Bool = true,
        invitation: String? = invitationWords
    ) -> TotalMilestoneLineComparisonInput10868 {
        TotalMilestoneLineComparisonInput10868(
            profile: TotalMilestoneInput10868(
                phase: phase,
                eyebrow: "TOTAL GAMES · ACTUAL VS OPENING LINE",
                title: "A longer match than the line",
                chartTitle: nil,
                quantityAxisTitle: "Total games in the match",
                milestones: rows,
                selectedMilestoneID: selected,
                actual: actual,
                projection: projection,
                quantityDomain: domain,
                quantityTicks: ticks,
                chanceTicks: [],
                timing: timing
            ),
            openingLine: line,
            difference: difference,
            quantitiesShareUnit: shareUnit,
            originalsTitle: "Original contracts",
            invitation: invitation
        )
    }

    private static func x(_ quantity: Double, width: CGFloat = plotSize.width) -> CGFloat? {
        TotalMilestoneGeometry10868.x(quantity, domain: retainedDomain, width: width, inset: inset)
    }

    // MARK: The retained originals

    func testTheThreeRetainedOriginalsKeepTheirExactIdentitiesChancesAndOwnResults() {
        let input = Self.comparison()
        XCTAssertEqual(Self.retainedIDs, [
            "constructed:15327291:polymarket:65138607:244929349",
            "constructed:15327291:polymarket:65123147:244876655",
            "constructed:15327291:polymarket:65123148:244876657",
        ])
        XCTAssertEqual(Self.retained.map(\.marketID), [65138607, 65123147, 65123148])
        XCTAssertEqual(Self.retained.map(\.outcomeID), [244929349, 244876655, 244876657])
        XCTAssertEqual(input.originals.map(\.index), [0, 1, 2], "owner order, none filtered or ranked")
        XCTAssertEqual(input.originals.map(\.milestone.id), Self.retainedIDs)
        XCTAssertEqual(input.originals.map(\.milestone.title), ["Over 21.5 games", "Over 22.5 games", "Over 23.5 games"])
        XCTAssertEqual(input.originals.map(\.pregame), (0..<3).map { TotalMilestoneReading10868.value(Self.retainedPregame($0)) })
        XCTAssertEqual(input.originals.compactMap { entry -> String? in
            if case .value(let observation) = entry.pregame { return observation.text }
            return nil
        }, ["64%", "52.5%", "44.5%"])
        XCTAssertTrue((0..<3).allSatisfy { Self.retainedPregame($0).timeText == "5:45 AM" }, "each original keeps its own pregame clock")
        XCTAssertEqual(input.originals.map(\.second), Array(repeating: TotalMilestoneSecondReading10868?.some(.result(Self.won)), count: 3))
        XCTAssertEqual(input.originals.map { $0.milestone.result.mark }, [.check, .check, .check])
        XCTAssertEqual(input.originals.map(\.selected), [false, true, false])
        XCTAssertEqual(input.selection.milestone?.id, Self.retainedIDs[1])
        XCTAssertEqual(input.selection.milestone?.title, "Over 22.5 games", "the subject names its own threshold")
        XCTAssertEqual(input.selectedReading, .value(Self.retainedPregame(1)))
        XCTAssertEqual(input.actualPresentation, TotalMilestoneActualPresentation10868(title: "Final count", actual: Self.retainedActual))
        XCTAssertEqual(input.visibleActualQuantity, 36)
        XCTAssertEqual(input.visibleDifference, Self.retainedDifference)
    }

    // MARK: The line is a threshold, not a projection

    func testTheOpeningLineIsItsOwnChannelAndNeverTheProjection() {
        // A projection the profile happens to hold, outside the owner range.
        let projection = TotalMilestoneProjection10868(quantity: 55, title: "Pregame projection", text: "55 games", clock: nil,
                                                       ruleLabel: "55 projected", comparison: "19 games below projection",
                                                       accessibilityDetail: "constructed projection")
        let input = Self.comparison(projection: projection)
        XCTAssertNotNil(input.profile.visibleProjection, "the profile still carries it; this card never reads it")
        XCTAssertEqual(input.line, Self.retainedLine)
        XCTAssertEqual(input.visibleLineQuantity, 22.5)
        XCTAssertEqual(input.domain, Self.retainedDomain, "55 never widens the axis")
        XCTAssertEqual(input.markLabels.map(\.kind), [.openingLine, .actual])
        XCTAssertEqual(input.markLabels.map(\.text), ["22.5 opening", "36 actual"])
        XCTAssertEqual(input.visibleDifference, Self.retainedDifference)
        let model = try! XCTUnwrap(input.plotModel(size: Self.plotSize, inset: Self.inset))
        XCTAssertEqual(try! XCTUnwrap(model.lineX), try! XCTUnwrap(Self.x(22.5)), accuracy: 0.001)
        let spoken = [input.accessibilityPlotLabel, input.accessibilityPlotValue, input.accessibilityLineValue ?? "",
                      input.accessibilityActualValue ?? ""].joined(separator: " ")
        XCTAssertFalse(spoken.contains("55"))
        XCTAssertFalse(spoken.contains("Pregame projection"))
        XCTAssertTrue(input.accessibilityPlotLabel.contains("a threshold, not a chance and not a projection"))
    }

    func testTheBenchmarkDomainAndAxisDoNotMoveWithTheSelection() {
        let inputs = Self.retainedIDs.map { Self.comparison(selected: $0) } + [Self.comparison(selected: nil)]
        XCTAssertEqual(inputs.map { $0.selection.milestone?.title }, ["Over 21.5 games", "Over 22.5 games", "Over 23.5 games", nil])
        let first = inputs[0]
        let model = first.plotModel(size: Self.plotSize, inset: Self.inset)
        XCTAssertNotNil(model)
        for input in inputs {
            XCTAssertEqual(input.visibleLineQuantity, 22.5, "the opening line stays 22.5 whichever original is selected")
            XCTAssertEqual(input.domain, Self.retainedDomain)
            XCTAssertEqual(input.plotModel(size: Self.plotSize, inset: Self.inset), model)
            XCTAssertEqual(input.markLabels, first.markLabels)
            XCTAssertEqual(input.placedQuantityTicks.map(\.value), [0, 10, 20, 30, 40])
            XCTAssertEqual(input.visibleDifference, Self.retainedDifference)
            XCTAssertEqual(input.accessibilityPlotValue, first.accessibilityPlotValue)
        }
        // Without the owner range: the originals' 22…24, the line and the count — still one domain.
        for id in Self.retainedIDs {
            XCTAssertEqual(Self.comparison(selected: id, domain: nil).domain, TotalMilestoneDomain10868(lower: 22, upper: 36))
        }
    }

    func testLiteralThresholdsAndQualifiedCoordinatesStayDistinct() {
        let input = Self.comparison()
        XCTAssertEqual(input.profile.milestones.map(\.quantity), [22, 23, 24], "the owner's coordinates, used as given")
        XCTAssertEqual(input.line?.quantity, 22.5)
        XCTAssertFalse(input.profile.milestones.contains { $0.quantity == 22.5 }, "Over 22.5 is not moved onto the line")
        let model = try! XCTUnwrap(input.plotModel(size: Self.plotSize, inset: Self.inset))
        XCTAssertNotEqual(model.lineX, Self.x(23), "the line is drawn at 22.5, not at the Over 22.5 coordinate")
        XCTAssertEqual(input.markLabels.map(\.quantity), [22.5, 36], "no original is drawn on the quantity axis")
        XCTAssertEqual(input.originals.count, 3, "no synthetic Under, no complement")
        XCTAssertFalse(input.originals.contains { $0.milestone.title.contains("Under") })
    }

    // MARK: Missing and invalid inputs

    func testAMissingOrInvalidLineKeepsTheCountAndOriginalsAndDropsTheDifference() {
        let unavailable = Self.comparison(line: .unavailable("Opening line unavailable"))
        XCTAssertNil(unavailable.line)
        XCTAssertEqual(unavailable.lineUnavailable, "Opening line unavailable")
        XCTAssertNil(unavailable.visibleLineQuantity)
        XCTAssertNil(unavailable.visibleDifference, "no orphan difference")
        XCTAssertEqual(unavailable.visibleActualQuantity, 36)
        XCTAssertTrue(unavailable.showsPlot)
        let model = try! XCTUnwrap(unavailable.plotModel(size: Self.plotSize, inset: Self.inset))
        XCTAssertNil(model.lineX)
        XCTAssertNotNil(model.actualX)
        XCTAssertNil(model.distance)
        XCTAssertEqual(unavailable.markLabels.map(\.kind), [.actual])
        XCTAssertEqual(unavailable.accessibilityLineValue, "Opening line unavailable")
        XCTAssertFalse(try! XCTUnwrap(unavailable.accessibilityActualValue).contains("+13.5"))
        XCTAssertFalse(unavailable.accessibilityPlotLabel.contains("hollow circle"))
        XCTAssertEqual(unavailable.originals.count, 3)
        XCTAssertEqual(unavailable.originalAction(index: 0, canSelect: true), .select(Self.retainedIDs[0]))

        for bad in [-1.0, .nan, .infinity] {
            let invalid = Self.comparison(line: .line(Self.constructedLine(quantity: bad, time: .unknown("Opening time unavailable"))))
            XCTAssertNotNil(invalid.line, "the owner's words stay")
            XCTAssertNil(invalid.visibleLineQuantity)
            XCTAssertNil(invalid.visibleDifference)
            XCTAssertEqual(invalid.domain, Self.retainedDomain)
            XCTAssertNil(try! XCTUnwrap(invalid.plotModel(size: Self.plotSize, inset: Self.inset)).lineX)
            XCTAssertEqual(invalid.markLabels.map(\.kind), [.actual])
            XCTAssertEqual(invalid.accessibilityLineValue?.hasPrefix("22.5 games, opening source not recorded"), true)
            XCTAssertFalse(invalid.accessibilityPlotValue.contains("Opening market line"))
        }
    }

    func testAMissingOrInvalidCountKeepsTheLineAndOriginalsAndDropsTheDifference() {
        let unavailable = Self.comparison(actual: .unavailable("Final count unavailable"))
        XCTAssertEqual(unavailable.actualPresentation,
                       TotalMilestoneActualPresentation10868(title: "Final count", actual: .unavailable("Final count unavailable")))
        XCTAssertNil(unavailable.visibleActualQuantity)
        XCTAssertNil(unavailable.visibleDifference)
        XCTAssertEqual(unavailable.visibleLineQuantity, 22.5)
        let model = try! XCTUnwrap(unavailable.plotModel(size: Self.plotSize, inset: Self.inset))
        XCTAssertNotNil(model.lineX)
        XCTAssertNil(model.actualX)
        XCTAssertNil(model.distance)
        XCTAssertEqual(unavailable.markLabels.map(\.kind), [.openingLine])
        XCTAssertEqual(unavailable.accessibilityActualValue, "Final count unavailable", "words, never zero")
        XCTAssertFalse(unavailable.accessibilityPlotLabel.contains("solid rule"))
        XCTAssertEqual(unavailable.originals.count, 3)

        let absent = Self.comparison(actual: nil)
        XCTAssertNil(absent.actualPresentation)
        XCTAssertNil(absent.visibleDifference)
        XCTAssertEqual(absent.visibleLineQuantity, 22.5)

        for bad in [-3.0, .nan] {
            let invalid = Self.comparison(actual: Self.constructedCount(bad, "36"))
            XCTAssertNotNil(invalid.actualPresentation, "the owner's figure stays")
            XCTAssertNil(invalid.visibleActualQuantity)
            XCTAssertNil(invalid.visibleDifference)
            XCTAssertEqual(invalid.markLabels.map(\.kind), [.openingLine])
        }

        let neither = Self.comparison(actual: .unavailable("Final count unavailable"), line: .unavailable("Opening line unavailable"))
        XCTAssertFalse(neither.showsPlot, "no empty axis")
        XCTAssertNil(neither.plotModel(size: Self.plotSize, inset: Self.inset))
        XCTAssertTrue(neither.placedQuantityTicks.isEmpty)
        XCTAssertEqual(neither.originals.count, 3, "the originals stay useful")
    }

    func testUnadmittedUnitsDrawNoSharedAxisOrDifference() {
        let input = Self.comparison(shareUnit: false)
        XCTAssertNil(input.domain)
        XCTAssertFalse(input.showsPlot)
        XCTAssertNil(input.plotModel(size: Self.plotSize, inset: Self.inset))
        XCTAssertTrue(input.placedQuantityTicks.isEmpty)
        XCTAssertTrue(input.markLabels.isEmpty)
        XCTAssertNil(input.visibleLineQuantity)
        XCTAssertNil(input.visibleActualQuantity)
        XCTAssertNil(input.visibleDifference)
        XCTAssertEqual(input.line, Self.retainedLine, "the line's words stay")
        XCTAssertNotNil(input.actualPresentation, "the count's words stay")
        XCTAssertEqual(input.accessibilityActualValue,
                       "36 games, Fokina 2–1 Tiafoe in sets, games 18–18 · ESPN score captured Oct 11, 10:06 AM PT")
        XCTAssertEqual(input.originals.count, 3)
        XCTAssertEqual(input.detailsAction(canOpenDetails: true), .details(Self.retainedIDs[1]))
    }

    func testAnUnknownOpeningTimeStaysUnknown() {
        let input = Self.comparison()
        XCTAssertEqual(input.line?.time, .unknown("Opening time unavailable"))
        let spoken = try! XCTUnwrap(input.accessibilityLineValue)
        XCTAssertEqual(spoken, "22.5 games, opening source not recorded; Opening time unavailable; A market threshold, not a projected score")
        XCTAssertFalse(spoken.contains("5:45"), "never the pregame clock")
        XCTAssertFalse(spoken.contains("5:50"), "never the start")
        XCTAssertFalse(spoken.contains("10:06"), "never the score capture")
        let clocked = Self.comparison(line: .line(Self.constructedLine(quantity: 22.5, time: .clock("Oct 10, 9:00 PM PT"))))
        XCTAssertEqual(clocked.line?.time.text, "Oct 10, 9:00 PM PT", "an owner clock is shown as given")
    }

    // MARK: Final only

    func testTheCardIsFinalOnlyAndTheLifecycleProfileIsUnchanged() {
        let timing = TotalMilestoneTiming10868(milestoneID: Self.retainedIDs[1], title: "Over 22.5 games · pregame timing",
                                               lines: ["Recorded Oct 11, 5:45 AM PT"])
        for phase in [TotalMilestonePhase10868.before, .during] {
            let input = Self.comparison(phase, timing: timing)
            XCTAssertFalse(input.isPresented)
            XCTAssertEqual(input.selection, .none)
            XCTAssertNil(input.selectionNotice)
            XCTAssertNil(input.selectedReading)
            XCTAssertNil(input.actualPresentation)
            XCTAssertNil(input.line)
            XCTAssertNil(input.lineUnavailable)
            XCTAssertNil(input.visibleLineQuantity)
            XCTAssertNil(input.visibleActualQuantity)
            XCTAssertNil(input.visibleDifference)
            XCTAssertNil(input.domain)
            XCTAssertFalse(input.showsPlot)
            XCTAssertTrue(input.markLabels.isEmpty)
            XCTAssertTrue(input.placedQuantityTicks.isEmpty)
            XCTAssertTrue(input.originals.isEmpty)
            XCTAssertNil(input.originalAction(index: 0, canSelect: true))
            XCTAssertNil(input.detailsAction(canOpenDetails: true))
            XCTAssertFalse(input.showsInvitation(canSelect: true, canOpenDetails: true))
            XCTAssertNil(input.timingPresentation(hasBinding: false))
            XCTAssertNil(input.accessibilitySelectedValue)
            XCTAssertNil(input.accessibilityActualValue)
            XCTAssertNil(input.accessibilityLineValue)
            // The profile it wraps keeps its own lifecycle for that phase.
            XCTAssertEqual(input.profile.selection.milestone?.id, Self.retainedIDs[1])
            XCTAssertEqual(input.profile.stripEntries.count, 3)
            XCTAssertEqual(input.profile.stripAction(index: 0, canSelect: true), .select(Self.retainedIDs[0]))
        }
        XCTAssertNil(Self.comparison(.before).profile.actualPresentation)
        XCTAssertEqual(Self.comparison(.during).profile.actualPresentation?.title, "Count so far")
        XCTAssertTrue(Self.comparison(.final).isPresented)
    }

    // MARK: Exact original interactions

    func testOriginalControlsHandBackExactIDsThroughTheProfilesOwnHelpers() {
        let timing = TotalMilestoneTiming10868(milestoneID: Self.retainedIDs[1], title: "Over 22.5 games · pregame timing",
                                               lines: ["Recorded Oct 11, 5:45 AM PT, before the verified 5:50 AM PT start"])
        let input = Self.comparison(timing: timing)
        for index in 0..<3 {
            XCTAssertEqual(input.originalAction(index: index, canSelect: true), .select(Self.retainedIDs[index]))
            XCTAssertEqual(input.originalAction(index: index, canSelect: true), input.profile.stripAction(index: index, canSelect: true))
        }
        XCTAssertNil(input.originalAction(index: 3, canSelect: true))
        XCTAssertNil(input.originalAction(index: -1, canSelect: true))
        XCTAssertEqual(input.detailsAction(canOpenDetails: true), .details(Self.retainedIDs[1]))
        XCTAssertEqual(input.detailsAction(canOpenDetails: true), input.profile.detailsAction(canOpenDetails: true))
        XCTAssertEqual(input.timingPresentation(hasBinding: true), .disclosure(timing))
        XCTAssertEqual(input.timingPresentation(hasBinding: false), .expanded(timing))

        var selected: [String] = []
        var details: [String] = []
        let onSelect: (String) -> Void = { selected.append($0) }
        let onDetails: (String) -> Void = { details.append($0) }
        input.originalAction(index: 2, canSelect: true)?.perform(onSelect: onSelect, onDetails: onDetails)
        input.detailsAction(canOpenDetails: true)?.perform(onSelect: onSelect, onDetails: onDetails)
        XCTAssertEqual(selected, [Self.retainedIDs[2]])
        XCTAssertEqual(details, [Self.retainedIDs[1]])
        XCTAssertEqual(input.selection.milestone?.id, Self.retainedIDs[1], "the page decides what is selected")
    }

    func testBlankRepeatedAndWithdrawnHeldIDsOpenNothing() {
        for held in ["", "   ", "\n"] {
            let rows = Self.retainedRows + [Self.constructedRow(id: held, title: "Over 24.5 games", quantity: 25,
                                                                before: Self.obs(0.3, "30%", nil, "constructed"))]
            let timing = TotalMilestoneTiming10868(milestoneID: held, title: "timing", lines: ["constructed"])
            let input = Self.comparison(rows: rows, selected: held, timing: timing)
            XCTAssertEqual(input.profile.selection.index, 3, "the profile alone resolves the blank id; the card refuses it")
            XCTAssertEqual(input.selection, .missing(held))
            XCTAssertEqual(input.selectionNotice, "Selected milestone unavailable.")
            XCTAssertNil(input.selectedReading)
            XCTAssertNil(input.detailsAction(canOpenDetails: true))
            XCTAssertNil(input.timingPresentation(hasBinding: false))
            XCTAssertFalse(input.originals.contains(where: \.selected))
            XCTAssertEqual(input.originals.count, 4, "the blank original stays named")
            XCTAssertNil(input.originalAction(index: 3, canSelect: true))
            XCTAssertEqual(input.originalAction(index: 0, canSelect: true), .select(Self.retainedIDs[0]))
        }

        let repeated = Self.retainedRows + [Self.constructedRow(id: Self.retainedIDs[1], title: "Over 22.5 games (repeat)", quantity: 23,
                                                                 before: Self.obs(0.5, "50%", nil, "constructed"))]
        let duplicate = Self.comparison(rows: repeated)
        XCTAssertEqual(duplicate.selection, .duplicate(Self.retainedIDs[1]))
        XCTAssertNil(duplicate.detailsAction(canOpenDetails: true))
        XCTAssertFalse(duplicate.originals.contains(where: \.selected))
        XCTAssertNil(duplicate.originalAction(index: 1, canSelect: true))
        XCTAssertNil(duplicate.originalAction(index: 3, canSelect: true))
        XCTAssertEqual(duplicate.originalAction(index: 0, canSelect: true), .select(Self.retainedIDs[0]))
        XCTAssertEqual(duplicate.originalAction(index: 2, canSelect: true), .select(Self.retainedIDs[2]))

        let withdrawn = Self.comparison(rows: [Self.retainedRow(0), Self.retainedRow(2)])
        XCTAssertEqual(withdrawn.selection, .missing(Self.retainedIDs[1]))
        XCTAssertEqual(withdrawn.originals.map(\.milestone.id), [Self.retainedIDs[0], Self.retainedIDs[2]])
        XCTAssertFalse(withdrawn.originals.contains(where: \.selected), "no neighbour is elected")
        XCTAssertNil(withdrawn.detailsAction(canOpenDetails: true))
        XCTAssertNil(withdrawn.selectedReading)
        XCTAssertEqual(withdrawn.visibleLineQuantity, 22.5)
        XCTAssertEqual(withdrawn.domain, Self.retainedDomain)
    }

    func testBlankAndRepeatedOriginalIDsStayNamedButHandBackNothing() {
        let rows = [
            Self.constructedRow(id: "", title: "Constructed blank", quantity: 22, before: Self.obs(0.6, "60%", nil, "constructed")),
            Self.constructedRow(id: " \t", title: "Constructed whitespace", quantity: 23, before: nil),
            Self.constructedRow(id: "constructed:repeat", title: "Constructed repeat A", quantity: 24, before: nil),
            Self.constructedRow(id: "constructed:repeat", title: "Constructed repeat B", quantity: 25, before: nil),
            Self.constructedRow(id: "constructed:unique", title: "Constructed unique", quantity: 26, before: nil),
        ]
        let input = Self.comparison(rows: rows, selected: "constructed:unique")
        XCTAssertEqual(input.originals.map(\.milestone.title),
                       ["Constructed blank", "Constructed whitespace", "Constructed repeat A", "Constructed repeat B", "Constructed unique"])
        XCTAssertEqual((0..<5).map { input.originalAction(index: $0, canSelect: true) },
                       [nil, nil, nil, nil, .select("constructed:unique")])
        XCTAssertEqual(input.detailsAction(canOpenDetails: true), .details("constructed:unique"))
    }

    func testWithoutCallbacksTheCardIsStaticAndAsksForNoTap() {
        let input = Self.comparison()
        XCTAssertTrue((0..<3).allSatisfy { input.originalAction(index: $0, canSelect: false) == nil })
        XCTAssertNil(input.detailsAction(canOpenDetails: false))
        XCTAssertFalse(input.showsInvitation(canSelect: false, canOpenDetails: false))
        XCTAssertEqual(input.originals.count, 3, "the same information, static")
        XCTAssertEqual(input.selection.milestone?.id, Self.retainedIDs[1])
    }

    func testTheTapInvitationNeedsADisplayedControlThatCanAct() {
        let input = Self.comparison()
        XCTAssertTrue(input.showsInvitation(canSelect: true, canOpenDetails: false))
        XCTAssertTrue(input.showsInvitation(canSelect: false, canOpenDetails: true), "the selected Details is a displayed action")
        XCTAssertFalse(Self.comparison(invitation: nil).showsInvitation(canSelect: true, canOpenDetails: true))

        // Callbacks exist, but no displayed control can act: a blank and a repeated id, and the held id is repeated.
        let rows = [
            Self.constructedRow(id: "", title: "Constructed blank", quantity: 22, before: nil),
            Self.constructedRow(id: "constructed:repeat", title: "Constructed repeat A", quantity: 23, before: nil),
            Self.constructedRow(id: "constructed:repeat", title: "Constructed repeat B", quantity: 24, before: nil),
        ]
        let dead = Self.comparison(rows: rows, selected: "constructed:repeat")
        XCTAssertFalse(dead.showsInvitation(canSelect: true, canOpenDetails: true))
        XCTAssertEqual(dead.originals.count, 3)
    }

    func testMissingAndZeroChancesStillAct() {
        let rows = [
            Self.retainedRow(0, before: .some(nil)),
            Self.retainedRow(1, before: .some(Self.obs(0, "0%", "5:45 AM", "constructed zero"))),
            Self.retainedRow(2, before: .some(Self.obs(.nan, "—", nil, "constructed invalid"))),
        ]
        let input = Self.comparison(rows: rows, selected: Self.retainedIDs[0])
        XCTAssertEqual(input.originals[0].pregame, .missing("Unavailable"))
        XCTAssertEqual(input.originals[1].pregame, .value(Self.obs(0, "0%", "5:45 AM", "constructed zero")), "0% is a real reading")
        XCTAssertEqual(input.selectedReading, .missing("Unavailable"))
        XCTAssertEqual(input.accessibilitySelectedValue, "Pregame chance: Unavailable")
        for index in 0..<3 {
            XCTAssertEqual(input.originalAction(index: index, canSelect: true), .select(Self.retainedIDs[index]))
        }
        XCTAssertEqual(input.detailsAction(canOpenDetails: true), .details(Self.retainedIDs[0]))
        XCTAssertEqual(input.domain, Self.retainedDomain, "no chance moves the axis")
        XCTAssertEqual(input.visibleLineQuantity, 22.5)
        XCTAssertEqual(input.originals.map(\.second), Array(repeating: TotalMilestoneSecondReading10868?.some(.result(Self.won)), count: 3))
    }

    func testANaNLaterObservationKeepsAValidOriginalReachable() {
        let later = TotalMilestoneCurrent10868.recorded(Self.obs(.nan, "—", "Later", "constructed later quote"), movement: nil)
        let rows = (0..<3).map { Self.retainedRow($0, current: $0 == 1 ? later : Self.noCurrent) }
        XCTAssertNotEqual(rows[1], rows[1], "NaN makes the row unequal to itself, so whole-row equality would lose it")
        let input = Self.comparison(rows: rows)
        XCTAssertEqual(input.selection.index, 1)
        XCTAssertEqual(input.selection.milestone?.id, Self.retainedIDs[1])
        XCTAssertTrue(input.originals[1].selected)
        XCTAssertEqual(input.originalAction(index: 1, canSelect: true), .select(Self.retainedIDs[1]))
        XCTAssertEqual(input.detailsAction(canOpenDetails: true), .details(Self.retainedIDs[1]))
        XCTAssertEqual(input.selectedReading, .value(Self.retainedPregame(1)), "the later quote never becomes the chance")
        XCTAssertEqual(input.originals[1].second, .result(Self.won))
        XCTAssertTrue(input.showsInvitation(canSelect: true, canOpenDetails: true))
    }

    func testTheRawFinalQuoteNeverBecomesAPregameChanceOrAResult() {
        let rows = (0..<3).map { index -> TotalMilestoneRow10868 in
            let saved = Self.retained[index]
            let quote = Self.obs(saved.finalQuote, "100%", saved.quoteClock, "latest quote, not a pregame chance")
            return Self.retainedRow(index, current: .recorded(quote, movement: nil), result: .unconfirmed("Result unconfirmed"))
        }
        let input = Self.comparison(rows: rows)
        XCTAssertEqual(input.originals.map(\.pregame), (0..<3).map { TotalMilestoneReading10868.value(Self.retainedPregame($0)) })
        XCTAssertEqual(input.selectedReading, .value(Self.retainedPregame(1)))
        XCTAssertEqual(input.originals.map(\.second),
                       Array(repeating: TotalMilestoneSecondReading10868?.some(.result(.unconfirmed("Result unconfirmed"))), count: 3),
                       "a 1.0 quote does not grade an original")
        XCTAssertTrue(input.originals.allSatisfy { $0.milestone.result.mark == nil })
        let spoken = input.originals.map { input.profile.accessibilityStripValue($0) }.joined(separator: " ")
            + (input.accessibilitySelectedValue ?? "") + input.accessibilityPlotValue
        XCTAssertFalse(spoken.contains("100%"))
        XCTAssertFalse(spoken.contains("7:06"))
        XCTAssertFalse(spoken.contains("7:54"))
    }

    // MARK: Readable quantity layout

    func testTickLabelsStepDownByMeasuredFitAndTheDirectLabelsStay() {
        let domain = Self.retainedDomain
        let values = [0.0, 10, 20, 30, 40]
        let small = Array(repeating: CGFloat(20), count: 5)
        let large = Array(repeating: CGFloat(60), count: 5)
        // 20 pt labels with a 6 pt gap need 26 pt per 10 games: 4 × 26 + 2 × 12 = 128 pt.
        XCTAssertEqual(TotalMilestoneLineGeometry10868.minimumTickWidth(values: values, widths: small, domain: domain,
                                                                         inset: Self.inset, gap: 6), 128, accuracy: 0.5)
        let sizes = small.map { CGSize(width: $0, height: 14) }
        let roomy = TotalMilestoneLineGeometry10868.tickFrames(values: values, sizes: sizes, domain: domain, width: 129, inset: Self.inset)
        XCTAssertTrue(TotalMilestoneLineGeometry10868.ticksFit(roomy, width: 129, gap: 6))
        let tight = TotalMilestoneLineGeometry10868.tickFrames(values: values, sizes: sizes, domain: domain, width: 120, inset: Self.inset)
        XCTAssertFalse(TotalMilestoneLineGeometry10868.ticksFit(tight, width: 120, gap: 6))
        XCTAssertTrue(roomy.allSatisfy { $0.minX >= 0 && $0.maxX <= 129 }, "end labels stay inside")

        XCTAssertEqual(TotalMilestoneLineGeometry10868.tickStrides(count: 5), [1, 2, 3, 4])
        XCTAssertEqual(TotalMilestoneLineGeometry10868.tickStrides(count: 1), [1])
        XCTAssertEqual(TotalMilestoneLineGeometry10868.tickStrides(count: 0), [])
        XCTAssertEqual(TotalMilestoneLineGeometry10868.tickSubset(count: 5, stride: 2), [0, 2, 4])
        XCTAssertEqual(TotalMilestoneLineGeometry10868.tickSubset(count: 5, stride: 4), [0, 4])

        func fitted(_ widths: [CGFloat], _ width: CGFloat) -> Int? {
            TotalMilestoneLineGeometry10868.fittedTickStride(values: values, widths: widths, domain: domain, width: width,
                                                            inset: Self.inset, gap: 6)
        }
        XCTAssertEqual(fitted(small, 327), 1, "every tick at phone width")
        XCTAssertEqual(fitted(small, 100), 2, "every second tick, never smaller text")
        // Enlarged 60 pt labels: the end labels clamp inside, so all five need 360 pt.
        XCTAssertEqual(TotalMilestoneLineGeometry10868.minimumTickWidth(values: values, widths: large, domain: domain,
                                                                         inset: Self.inset, gap: 6), 360, accuracy: 0.5)
        XCTAssertEqual(fitted(large, 400), 1)
        XCTAssertEqual(fitted(large, 327), 2)
        XCTAssertEqual(fitted(large, 130), 4, "just the first and last")
        XCTAssertNil(fitted(large, 100), "no ticks rather than overlapping ones")
        XCTAssertEqual(TotalMilestoneLineGeometry10868.minimumTickWidth(values: [10, 10], widths: [20, 20], domain: domain,
                                                                         inset: Self.inset, gap: 6), .infinity)

        // With no ticks at all, the direct labels still carry both exact quantities.
        let input = Self.comparison()
        XCTAssertEqual(input.markLabels.map(\.text), ["22.5 opening", "36 actual"])
        let outside = Self.comparison(ticks: [TotalMilestoneTick10868(value: -10, text: "-10"), TotalMilestoneTick10868(value: 20, text: "20"),
                                              TotalMilestoneTick10868(value: 50, text: "50"), TotalMilestoneTick10868(value: .nan, text: "?")])
        XCTAssertEqual(outside.placedQuantityTicks.map(\.text), ["20"], "only ticks the domain can place, in owner order")
    }

    func testNearCoincidentAndEndMarkLabelsKeepTheirOwnSpace() {
        let input = Self.comparison()
        let labelSizes = [CGSize(width: 84, height: 16), CGSize(width: 64, height: 16)]
        let plan = TotalMilestoneGeometry10868.chartPlan(
            width: 327, plotHeight: 36, inset: Self.inset, domain: input.domain,
            chanceFractions: [], chanceSizes: [],
            annotationValues: input.markLabels.map(\.quantity), annotationSizes: labelSizes,
            tickValues: [], tickSizes: [])
        XCTAssertEqual(plan.plot.minX, 0, "no chance axis: the axis spans the card")
        XCTAssertEqual(plan.plot.width, 327)
        XCTAssertEqual(plan.plot.height, 36)
        XCTAssertFalse(plan.annotations[0].intersects(plan.annotations[1]))
        XCTAssertEqual(plan.annotations[0].midX, try! XCTUnwrap(Self.x(22.5)), accuracy: 0.001)
        XCTAssertTrue(plan.annotations.allSatisfy { $0.maxY <= plan.plot.minY })

        // A count on the line: both labels keep their position, one lane up.
        let coincident = Self.comparison(actual: Self.constructedCount(22.5, "22.5"))
        XCTAssertEqual(coincident.markLabels.map(\.quantity), [22.5, 22.5])
        let model = try! XCTUnwrap(coincident.plotModel(size: Self.plotSize, inset: Self.inset))
        XCTAssertEqual(model.lineX, model.actualX)
        XCTAssertEqual(model.distance, TotalMilestoneLineSpan10868(lower: try! XCTUnwrap(model.lineX), upper: try! XCTUnwrap(model.lineX)))
        let stacked = TotalMilestoneGeometry10868.chartPlan(
            width: 327, plotHeight: 36, inset: Self.inset, domain: coincident.domain,
            chanceFractions: [], chanceSizes: [],
            annotationValues: coincident.markLabels.map(\.quantity), annotationSizes: labelSizes,
            tickValues: [], tickSizes: [])
        XCTAssertFalse(stacked.annotations[0].intersects(stacked.annotations[1]))
        XCTAssertEqual(stacked.annotations[0].midX, stacked.annotations[1].midX, accuracy: 0.001)

        // A count at the far end keeps its label inside the card.
        let end = Self.comparison(actual: Self.constructedCount(40, "40"))
        let endPlan = TotalMilestoneGeometry10868.chartPlan(
            width: 327, plotHeight: 36, inset: Self.inset, domain: end.domain,
            chanceFractions: [], chanceSizes: [],
            annotationValues: end.markLabels.map(\.quantity), annotationSizes: labelSizes,
            tickValues: [], tickSizes: [])
        XCTAssertTrue(endPlan.annotations.allSatisfy { $0.minX >= 0 && $0.maxX <= 327 })

        // Enlarged text wrapped to the axis width keeps a lane of its own.
        let wrapped = TotalMilestoneGeometry10868.chartPlan(
            width: 200, plotHeight: 36, inset: Self.inset, domain: input.domain,
            chanceFractions: [], chanceSizes: [],
            annotationValues: input.markLabels.map(\.quantity),
            annotationSizes: [CGSize(width: 200, height: 44), CGSize(width: 96, height: 22)],
            tickValues: [], tickSizes: [])
        XCTAssertFalse(wrapped.annotations[0].intersects(wrapped.annotations[1]))
        XCTAssertTrue(wrapped.annotations.allSatisfy { $0.maxY <= wrapped.plot.minY })
    }

    func testLongOwnerWordsAreKeptWholeAndOriginalsWrapInsteadOfHiding() {
        let long = "Over 22.5 games in the match, both players combined, across every set played"
        let rows = [Self.retainedRow(0),
                    Self.constructedRow(id: "constructed:long-title", title: long, quantity: 23,
                                        before: Self.obs(0.525, "52.5%", "5:45 AM", "constructed"), result: Self.won),
                    Self.retainedRow(2)]
        let input = Self.comparison(rows: rows, selected: "constructed:long-title")
        XCTAssertEqual(input.selection.milestone?.title, long, "the owner's full words, never abbreviated")
        XCTAssertEqual(input.originals[1].milestone.title, long)
        XCTAssertEqual(input.originalAction(index: 1, canSelect: true), .select("constructed:long-title"))
        XCTAssertEqual(TotalMilestoneGeometry10868.stripColumns(count: 3, width: 327, spacing: 8, minimumCellWidth: 96) { $0 >= 100 }, 3)
        XCTAssertEqual(TotalMilestoneGeometry10868.stripColumns(count: 3, width: 327, spacing: 8, minimumCellWidth: 96) { $0 >= 180 }, 1,
                       "a long title takes one column rather than being cut")
        XCTAssertEqual(TotalMilestoneGeometry10868.stripColumns(count: 3, width: 700, spacing: 8, minimumCellWidth: 96,
                                                                maximumColumns: 1) { _ in true }, 1, "accessibility sizes")
        let plan = TotalMilestoneGeometry10868.stripFrames(columns: 1, cellWidth: 327, heights: [80, 140, 80], spacing: 8)
        XCTAssertEqual(plan.frames.count, 3, "no original is hidden")
        XCTAssertTrue(plan.frames.allSatisfy { $0.width >= 44 && $0.height >= 44 })
    }

    // MARK: Spoken text

    func testSpokenChanceLineCountResultAndClockStayDistinct() {
        let input = Self.comparison()
        XCTAssertEqual(input.accessibilityHeader, "TOTAL GAMES · ACTUAL VS OPENING LINE. A longer match than the line. Final")
        XCTAssertEqual(input.accessibilitySelectedValue,
                       "Pregame chance: 52.5%, Oct 11, 5:45 AM PT · Polymarket consensus · before the verified 5:50 AM PT start")
        XCTAssertEqual(input.accessibilityActualValue,
                       "36 games, Fokina 2–1 Tiafoe in sets, games 18–18 · ESPN score captured Oct 11, 10:06 AM PT; +13.5 games above the opening line")
        XCTAssertEqual(input.accessibilityLineValue,
                       "22.5 games, opening source not recorded; Opening time unavailable; A market threshold, not a projected score")
        XCTAssertEqual(input.accessibilityPlotLabel,
                       "Total games in the match The hollow circle is the opening market line: a threshold, not a chance and not a projection. "
                       + "The solid rule is the count, not a chance. The band between them is the distance from the line to the count.")
        XCTAssertEqual(input.accessibilityPlotValue, "Opening market line: 22.5 games; Final count: 36 games; +13.5 games above the opening line")
        XCTAssertEqual(input.originals.map { input.profile.accessibilityStripValue($0) }, [
            "Pregame chance: 64%, \(Self.pregameDetail); Final result: Won",
            "Pregame chance: 52.5%, \(Self.pregameDetail); Final result: Won",
            "Pregame chance: 44.5%, \(Self.pregameDetail); Final result: Won",
        ])
        XCTAssertEqual(TotalMilestoneLineAccessibilityID10868.option(Self.retainedIDs[0]),
                       "totalMilestoneLine10868.option.constructed:15327291:polymarket:65138607:244929349")
        XCTAssertEqual(TotalMilestoneLineAccessibilityID10868.details(Self.retainedIDs[1]),
                       "totalMilestoneLine10868.details.constructed:15327291:polymarket:65123147:244876655")
    }
}

/// #10868 — during play, the games so far beside each original's own literal
/// threshold, with every exact Under original's own pre-match chance, current
/// state and market result.
///
/// The view is SwiftUI and is not rasterised here. What is asserted is the
/// rules it defers to: the phase gate, the exact identities, each panel's
/// titled channels and result, the threshold associations, the shared axis,
/// the actions, the label and panel planning and the spoken text. Nothing here
/// claims a rendered fit.
///
/// RETAINED raw values come from Fils–van de Zandschulp, event 15327807,
/// verified start 2026-10-12T10:55Z, as copied in
/// `shipping-adoption-20261027/TENNIS-LIVE-TOTAL-GAMES-RETAINED-CASES.json`
/// (sha256 250c4ff7…5be8f):
///   score captured 12:20:44.471140Z — sets 0–1, set 1 5–7, set 2 3–3, games
///     8–10, 18 games in all. Separate owner inputs; nothing here sums them,
///     and the capture is not a set boundary.
///   Polymarket 65197799 / outcome 245152784 "Under 22.5 games": 0.55 and
///   Polymarket 65197800 / outcome 245152786 "Under 23.5 games": 0.605, both
///     exact Under history observations @ 07:54:53.005454Z, before the start;
///     no complement. Current "No recent price"; "Result pending"; no projection.
///   Historical only, never a baseline or a current chance: last quotes 0.535
///     and 0.55, the later detail's 0.73 and missing reading, the later
///     opening_probability 0.545, and the feed's over_probability 0.465 / 0.45
///     (the opposite side).
///
/// CONSTRUCTED owner inputs (this leaf does not resolve them): the action ids,
/// the profile coordinates 23/24 (deliberately not the thresholds), the
/// threshold associations, labels and marks, every display string, PT clock
/// and detail line, the subtotal names, the 0–30 domain and ticks, the channel
/// titles, key, note, invitation and unresolved words, and every admitted
/// current chance, won/lost result, reached state, missing, invalid, foreign,
/// blank, repeated, withdrawn, NaN, extra, near and long-text case.
final class TotalMilestoneThresholdLive10868Tests: XCTestCase {

    // MARK: Retained owner associations — explicit, never a fallback

    private struct RetainedOriginal {
        let actionID: String
        let marketID: Int
        let outcomeID: Int
        /// The owner's title naming the original's own literal threshold.
        let title: String
        /// The owner's literal threshold and its label; never derived here.
        let threshold: Double
        let thresholdLabel: String
        let mark: TotalMilestoneThresholdMark10868
        let baseline: Double
        let baselineText: String
        /// A constructed profile coordinate, deliberately not the threshold.
        let profileCoordinate: Double
    }

    private static let homeMark = TotalMilestoneThresholdMark10868(shape: .circle, tone: .primary)
    private static let awayMark = TotalMilestoneThresholdMark10868(shape: .circle, tone: .secondary)

    private static let retained: [RetainedOriginal] = [
        RetainedOriginal(actionID: "constructed:15327807:polymarket:65197799:245152784", marketID: 65197799, outcomeID: 245152784,
                         title: "Under 22.5 games", threshold: 22.5, thresholdLabel: "22.5", mark: homeMark,
                         baseline: 0.55, baselineText: "55%", profileCoordinate: 23),
        RetainedOriginal(actionID: "constructed:15327807:polymarket:65197800:245152786", marketID: 65197800, outcomeID: 245152786,
                         title: "Under 23.5 games", threshold: 23.5, thresholdLabel: "23.5", mark: awayMark,
                         baseline: 0.605, baselineText: "60.5%", profileCoordinate: 24),
    ]
    private static let retainedIDs = retained.map(\.actionID)
    /// 07:54:53Z is 12:54 AM PDT; the verified 10:55Z start is 3:55 AM PDT.
    private static let baselineClock = "12:54 AM"
    private static let baselineDetail = "Oct 12, 12:54 AM PT · Polymarket Under history · before the verified 3:55 AM PT start"
    private static let noRecentPrice = TotalMilestoneCurrent10868.unavailable("No recent price")
    private static let pending = TotalMilestoneResult10868.unconfirmed("Result pending")
    private static let missingWords = "Unavailable"
    /// Figures that may never become a baseline or a current chance here.
    private static let historicalOnly = ["53.5%", "73%", "54.5%", "46.5%", "45%", "39.5%"]

    private static func obs(_ probability: Double, _ text: String, _ time: String?, _ detail: String) -> TotalMilestoneObservation10868 {
        TotalMilestoneObservation10868(probability: probability, text: text, timeText: time, accessibilityDetail: detail)
    }

    /// Original `index`'s own retained pre-match observation and clock.
    private static func baseline(_ index: Int) -> TotalMilestoneObservation10868 {
        obs(retained[index].baseline, retained[index].baselineText, baselineClock, baselineDetail)
    }

    /// Original `index`, every field from its own retained association.
    private static func retainedRow(
        _ index: Int,
        title: String? = nil,
        before: TotalMilestoneObservation10868?? = nil,
        current: TotalMilestoneCurrent10868 = noRecentPrice,
        result: TotalMilestoneResult10868 = pending
    ) -> TotalMilestoneRow10868 {
        let saved = retained[index]
        return TotalMilestoneRow10868(
            id: saved.actionID,
            quantity: saved.profileCoordinate,
            quantityLabel: "constructed",
            title: title ?? saved.title,
            before: before ?? baseline(index),
            beforeMissing: missingWords,
            current: current,
            performance: nil,
            result: result
        )
    }

    private static var retainedRows: [TotalMilestoneRow10868] { (0..<2).map { retainedRow($0) } }

    /// A constructed original: every field passed, nothing borrowed from the retained packet.
    private static func constructedRow(id: String, title: String, quantity: Double = 0,
                                       before: TotalMilestoneObservation10868?,
                                       current: TotalMilestoneCurrent10868 = noRecentPrice,
                                       result: TotalMilestoneResult10868 = pending) -> TotalMilestoneRow10868 {
        TotalMilestoneRow10868(id: id, quantity: quantity, quantityLabel: "constructed", title: title, before: before,
                               beforeMissing: missingWords, current: current, performance: nil, result: result)
    }

    /// 12:20:44Z is 5:20 AM PDT. The capture is the count's own clock, not a set end.
    private static let actualDetail = "Fils 0–1 van de Zandschulp in sets; set 1 5–7, set 2 3–3 · score captured Oct 12, 5:20 AM PT"
    private static let retainedActual = TotalMilestoneActual10868.count(TotalMilestoneCount10868(
        quantity: 18, text: "18", unit: "games", clock: "Score captured 5:20 AM", ruleLabel: "18 actual",
        accessibilityDetail: actualDetail))

    private static func constructedCount(_ quantity: Double, _ text: String) -> TotalMilestoneActual10868 {
        .count(TotalMilestoneCount10868(quantity: quantity, text: text, unit: "games", clock: nil,
                                        ruleLabel: "\(text) actual", accessibilityDetail: "constructed count"))
    }

    /// Original `index`'s own threshold association, or a constructed variant of it.
    private static func threshold(_ index: Int, quantity: Double? = nil, label: String? = nil) -> TotalMilestoneThreshold10868 {
        let saved = retained[index]
        return TotalMilestoneThreshold10868(originalID: saved.actionID, quantity: quantity ?? saved.threshold,
                                            label: label ?? saved.thresholdLabel, mark: saved.mark)
    }

    private static var retainedThresholds: [TotalMilestoneThreshold10868] { (0..<2).map { threshold($0) } }
    private static let retainedSubtotals = [TotalMilestoneSubtotal10868(text: "8", name: "Fils"),
                                            TotalMilestoneSubtotal10868(text: "10", name: "Zandschulp")]

    private static func ownerWords(
        note: String? = "Circles mark total-game thresholds, not projected final scores. The match is unfinished.",
        invitation: String? = "Choose a contract to see its details",
        subtotalsTitle: String? = "Games won"
    ) -> TotalMilestoneThresholdWords10868 {
        TotalMilestoneThresholdWords10868(beforeTitle: "Pre-match chance", currentTitle: "Current chance",
                                          thresholdKey: "Original market thresholds", originalsTitle: "Original Under contracts",
                                          note: note, invitation: invitation, unresolved: "Original contract unavailable",
                                          subtotalsTitle: subtotalsTitle)
    }

    private static let retainedDomain = TotalMilestoneDomain10868(lower: 0, upper: 30)
    private static let gameTicks = [0.0, 10, 20, 30].map { TotalMilestoneTick10868(value: $0, text: "\(Int($0))") }
    private static let plotSize = CGSize(width: 327, height: 40)
    private static let inset = TotalMilestoneGeometry10868.plotInset

    private static func timing(_ id: String) -> TotalMilestoneTiming10868 {
        TotalMilestoneTiming10868(milestoneID: id, title: "Pre-match chance timing",
                                  lines: ["Recorded Oct 12, 12:54 AM PT, before the verified 3:55 AM PT start"])
    }

    private static func live(
        _ phase: TotalMilestonePhase10868 = .during,
        rows: [TotalMilestoneRow10868] = retainedRows,
        selected: String? = nil,
        actual: TotalMilestoneActual10868? = retainedActual,
        projection: TotalMilestoneProjection10868? = nil,
        domain: TotalMilestoneDomain10868? = retainedDomain,
        ticks: [TotalMilestoneTick10868] = gameTicks,
        timing: TotalMilestoneTiming10868? = nil,
        thresholds: [TotalMilestoneThreshold10868] = retainedThresholds,
        subtotals: [TotalMilestoneSubtotal10868] = retainedSubtotals,
        shareUnit: Bool = true,
        words: TotalMilestoneThresholdWords10868 = ownerWords()
    ) -> TotalMilestoneThresholdLiveInput10868 {
        TotalMilestoneThresholdLiveInput10868(
            profile: TotalMilestoneInput10868(
                phase: phase,
                eyebrow: "TOTAL GAMES · STILL IN PLAY",
                title: "18 games played so far",
                chartTitle: nil,
                quantityAxisTitle: "Total games in the match",
                milestones: rows,
                selectedMilestoneID: selected,
                actual: actual,
                projection: projection,
                quantityDomain: domain,
                quantityTicks: ticks,
                chanceTicks: [],
                timing: timing
            ),
            thresholds: thresholds,
            subtotals: subtotals,
            quantitiesShareUnit: shareUnit,
            words: words
        )
    }

    private static func x(_ quantity: Double) -> CGFloat? {
        TotalMilestoneGeometry10868.x(quantity, domain: retainedDomain, width: plotSize.width, inset: inset)
    }

    private static func barWidth(_ probability: Double, track: CGFloat = 140) -> CGFloat? {
        TotalMilestoneThresholdLiveInput10868.barWidth(probability, track: track)
    }

    // MARK: The retained originals

    func testTheTwoRetainedUnderOriginalsKeepTheirExactIdentitiesAndOwnPreMatchChances() {
        let input = Self.live()
        XCTAssertTrue(input.isPresented)
        XCTAssertEqual(Self.retainedIDs, [
            "constructed:15327807:polymarket:65197799:245152784",
            "constructed:15327807:polymarket:65197800:245152786",
        ])
        XCTAssertEqual(Self.retained.map(\.marketID), [65197799, 65197800])
        XCTAssertEqual(Self.retained.map(\.outcomeID), [245152784, 245152786])
        let panels = input.panels
        XCTAssertEqual(panels.map(\.index), [0, 1], "owner order, none filtered or ranked")
        XCTAssertEqual(panels.map(\.milestone.id), Self.retainedIDs)
        XCTAssertEqual(panels.map(\.milestone.title), ["Under 22.5 games", "Under 23.5 games"])
        XCTAssertEqual(panels.map(\.isResolved), [true, true])
        XCTAssertEqual(panels.map(\.channels), [
            [.chance(title: "Pre-match chance", observation: Self.baseline(0)), .status(title: "Current chance", text: "No recent price")],
            [.chance(title: "Pre-match chance", observation: Self.baseline(1)), .status(title: "Current chance", text: "No recent price")],
        ])
        XCTAssertEqual(input.profile.milestones.map { $0.before?.probability }, [0.55, 0.605])
        XCTAssertEqual(input.profile.milestones.map { $0.before?.text }, ["55%", "60.5%"])
        XCTAssertEqual(input.profile.milestones.map { $0.before?.timeText }, ["12:54 AM", "12:54 AM"], "each keeps its own baseline clock")
        XCTAssertEqual(panels.map(\.result), [Self.pending, Self.pending])
        XCTAssertEqual(panels.map { $0.result?.mark }, [nil, nil], "pending has no loss glyph")
        XCTAssertEqual(panels.map { $0.result?.isAdmitted }, [false, false])
        XCTAssertEqual(panels.map(\.threshold?.label), ["22.5", "23.5"])
        XCTAssertEqual(panels.map(\.mark), [Self.homeMark, Self.awayMark])
        XCTAssertEqual(panels.map(\.movement), [nil, nil])
        XCTAssertEqual(panels.map(\.selected), [false, false], "no held original in the retained capture")
    }

    func testLaterQuotesOpeningProbabilityAndTheOverSideNeverBecomeABaselineOrCurrent() {
        let input = Self.live()
        let spoken = ([input.accessibilityPlotLabel, input.accessibilityPlotValue, input.accessibilityActualValue ?? "",
                       input.accessibilitySubtotals] + input.panels.map { input.accessibilityPanelValue($0) }).joined(separator: " ")
        for later in Self.historicalOnly {
            XCTAssertFalse(spoken.contains(later), "\(later) is historical or the opposite side")
        }
        // The second original's later 55% quote never replaces its own 60.5% baseline.
        XCTAssertEqual(input.panels[1].channels.first, .chance(title: "Pre-match chance", observation: Self.baseline(1)))
        XCTAssertTrue(input.panels.allSatisfy { panel in
            if case .status(let title, let text)? = panel.channels.last { return title == "Current chance" && text == "No recent price" }
            return false
        }, "no quote becomes current")
        XCTAssertEqual(input.panels.map(\.channels.count), [2, 2])
    }

    func testTheCompositionIsDuringOnlyAndTheLifecycleProfileAndFinalLineStayUnchanged() {
        for phase in [TotalMilestonePhase10868.before, .final] {
            let input = Self.live(phase, selected: Self.retainedIDs[0], timing: Self.timing(Self.retainedIDs[0]))
            XCTAssertFalse(input.isPresented)
            XCTAssertEqual(input.panels, [])
            XCTAssertEqual(input.placements, [])
            XCTAssertEqual(input.labels, [])
            XCTAssertNil(input.domain)
            XCTAssertFalse(input.showsPlot)
            XCTAssertNil(input.plotModel(size: Self.plotSize, inset: Self.inset))
            XCTAssertNil(input.actualPresentation)
            XCTAssertEqual(input.visibleSubtotals, [])
            XCTAssertEqual(input.selection, TotalMilestoneSelection10868.none)
            XCTAssertNil(input.threshold(forOriginalAt: 0))
            XCTAssertNil(input.panelAction(index: 0, canSelect: true))
            XCTAssertNil(input.detailsAction(canOpenDetails: true))
            XCTAssertNil(input.timingPresentation(hasBinding: false))
            XCTAssertFalse(input.showsInvitation(canSelect: true, canOpenDetails: true))
        }
        let during = Self.live(selected: Self.retainedIDs[0])
        XCTAssertNil(during.profile.result(during.profile.milestones[0]), "the profile's result helper stays final-only")
        XCTAssertEqual(during.panels[0].result, Self.pending, "the row's own result, shown directly")
        XCTAssertEqual(during.profile.markStyle, .dots)
        XCTAssertEqual(during.profile.actualPresentation?.title, "Count so far")
        XCTAssertNil(during.profile.visibleProjection)
        XCTAssertEqual(during.profile.domain, Self.retainedDomain, "the lifecycle profile keeps its own domain rule")
        let line = TotalMilestoneLineComparisonInput10868(profile: during.profile, openingLine: .unavailable("Opening line unavailable"),
                                                          difference: nil, quantitiesShareUnit: true,
                                                          originalsTitle: "Original contracts", invitation: nil)
        XCTAssertFalse(line.isPresented, "the final-only line comparison is not forced into play")
        XCTAssertEqual(line.originals, [])
        XCTAssertNil(line.domain)
    }

    // MARK: Count and subtotals

    func testTheActualEighteenAndTheNamedSubtotalsAreSeparateOwnerInputs() {
        let input = Self.live()
        XCTAssertEqual(input.actualPresentation, TotalMilestoneActualPresentation10868(title: "Count so far", actual: Self.retainedActual))
        XCTAssertEqual(input.visibleActualQuantity, 18)
        XCTAssertEqual(input.visibleSubtotals, Self.retainedSubtotals)
        XCTAssertEqual(input.visibleSubtotals.map(\.text), ["8", "10"])
        XCTAssertEqual(input.accessibilitySubtotals, "Games won: Fils 8, Zandschulp 10")
        if case .count(let count)? = input.profile.actual {
            XCTAssertEqual(count.clock, "Score captured 5:20 AM", "a capture clock, not a set boundary")
        } else {
            XCTFail("retained count")
        }
        // Constructed subtotals that do not add up are shown as given and move nothing else.
        let odd = Self.live(subtotals: [TotalMilestoneSubtotal10868(text: "7", name: "Fils"),
                                        TotalMilestoneSubtotal10868(text: "7", name: "Zandschulp")])
        XCTAssertEqual(odd.visibleSubtotals.map(\.text), ["7", "7"])
        XCTAssertEqual(odd.visibleActualQuantity, 18)
        XCTAssertEqual(odd.domain, input.domain)
        XCTAssertEqual(odd.labels, input.labels)
        XCTAssertEqual(odd.panels, input.panels)
        // A constructed count leaves the subtotals untouched; no subtotals leave the count alone.
        let moved = Self.live(actual: Self.constructedCount(19, "19"))
        XCTAssertEqual(moved.visibleSubtotals, Self.retainedSubtotals)
        XCTAssertEqual(moved.visibleActualQuantity, 19)
        let none = Self.live(subtotals: [])
        XCTAssertEqual(none.visibleSubtotals, [])
        XCTAssertEqual(none.actualPresentation, input.actualPresentation)
        XCTAssertEqual(Self.live(words: Self.ownerWords(subtotalsTitle: nil)).accessibilitySubtotals, "Fils 8, Zandschulp 10")
    }

    // MARK: Literal thresholds on the shared axis

    func testLiteralThresholdsArePlacedApartFromTheProfilesQualifiedCoordinatesAndAnyProjection() {
        let projection = TotalMilestoneProjection10868(quantity: 26, title: "Pregame projection", text: "26 games", clock: nil,
                                                       ruleLabel: "26 projected", comparison: nil,
                                                       accessibilityDetail: "constructed projection")
        let input = Self.live(projection: projection, domain: nil)
        XCTAssertEqual(input.profile.milestones.map(\.quantity), [23, 24], "the owner's qualified coordinates, never read here")
        XCTAssertEqual(input.placements.map(\.index), [0, 1])
        XCTAssertEqual(input.placements.map(\.quantity), [22.5, 23.5])
        XCTAssertEqual(input.domain, TotalMilestoneDomain10868(lower: 18, upper: 23.5), "neither 24 nor the projection's 26 widens it")
        XCTAssertEqual(input.labels.map(\.text), ["22.5", "23.5", "18 actual"])
        XCTAssertEqual(input.labels.map(\.quantity), [22.5, 23.5, 18])
        XCTAssertEqual(input.labels.map(\.kind), [.threshold(Self.homeMark), .threshold(Self.awayMark), .actual])
        let owned = Self.live(projection: projection)
        let model = try! XCTUnwrap(owned.plotModel(size: Self.plotSize, inset: Self.inset))
        XCTAssertEqual(model.marks.map(\.index), [0, 1])
        XCTAssertEqual(model.marks.map(\.mark), [Self.homeMark, Self.awayMark])
        XCTAssertEqual(model.marks[0].x, try! XCTUnwrap(Self.x(22.5)), accuracy: 0.001)
        XCTAssertEqual(model.marks[1].x, try! XCTUnwrap(Self.x(23.5)), accuracy: 0.001)
        XCTAssertNotEqual(model.marks[0].x, try! XCTUnwrap(Self.x(23)), "22.5 is not moved onto the 23 coordinate")
        XCTAssertEqual(try! XCTUnwrap(model.actualX), try! XCTUnwrap(Self.x(18)), accuracy: 0.001)
        XCTAssertEqual(model.axisY, 20)
        XCTAssertEqual(model.ruleTop, 6)
        XCTAssertEqual(model.ruleBottom, 34)
        let spoken = owned.accessibilityPlotLabel + " " + owned.accessibilityPlotValue
        XCTAssertFalse(spoken.contains("26 projected"))
        XCTAssertFalse(spoken.contains("Pregame projection"))
        XCTAssertTrue(owned.accessibilityPlotLabel.contains("not chances and not projected final scores"))
        XCTAssertNil(owned.profile.visibleProjection)
    }

    func testTheDomainAndMarksDoNotMoveWithTheSelection() {
        let selections: [String?] = [nil, Self.retainedIDs[0], Self.retainedIDs[1]]
        let inputs = selections.map { Self.live(selected: $0) }
        XCTAssertEqual(inputs.map { $0.selection.index }, [nil, 0, 1])
        let first = inputs[0]
        let model = try! XCTUnwrap(first.plotModel(size: Self.plotSize, inset: Self.inset))
        for input in inputs {
            XCTAssertEqual(input.domain, Self.retainedDomain)
            XCTAssertEqual(input.labels, first.labels)
            XCTAssertEqual(input.placements.map(\.quantity), [22.5, 23.5])
            let other = try! XCTUnwrap(input.plotModel(size: Self.plotSize, inset: Self.inset))
            XCTAssertEqual(other.marks.map(\.x), model.marks.map(\.x))
            XCTAssertEqual(other.actualX, model.actualX)
            XCTAssertEqual(input.accessibilityPlotValue, first.accessibilityPlotValue)
            XCTAssertEqual(input.panels.map(\.channels), first.panels.map(\.channels))
        }
        XCTAssertEqual(inputs[1].placements.map(\.selected), [true, false])
        XCTAssertEqual(inputs[2].panels.map(\.selected), [false, true])
        for id in selections {
            XCTAssertEqual(Self.live(selected: id, domain: nil).domain, TotalMilestoneDomain10868(lower: 18, upper: 23.5))
        }
    }

    func testUnadmittedUnitsDrawNoSharedAxisButKeepEveryLabelledReading() {
        let input = Self.live(shareUnit: false)
        XCTAssertNil(input.domain)
        XCTAssertFalse(input.showsPlot)
        XCTAssertFalse(input.drawsThresholds)
        XCTAssertNil(input.plotModel(size: Self.plotSize, inset: Self.inset))
        XCTAssertEqual(input.placements, [])
        XCTAssertEqual(input.labels, [])
        XCTAssertEqual(input.placedQuantityTicks, [])
        XCTAssertNil(input.visibleActualQuantity)
        XCTAssertEqual(input.accessibilityPlotValue, "")
        XCTAssertEqual(input.actualPresentation?.actual, Self.retainedActual, "the count keeps its own labelled block")
        XCTAssertEqual(input.visibleSubtotals, Self.retainedSubtotals)
        XCTAssertEqual(input.panels.map(\.mark), [nil, nil])
        XCTAssertEqual(input.panels.map(\.threshold?.label), ["22.5", "23.5"], "each association still names its threshold")
        XCTAssertEqual(input.panels.map(\.channels), Self.live().panels.map(\.channels))
        XCTAssertEqual(input.panels.map(\.result), [Self.pending, Self.pending])
        XCTAssertTrue(input.accessibilityPanelValue(input.panels[0]).hasSuffix("Market threshold: 22.5"))
        XCTAssertEqual(input.panelAction(index: 0, canSelect: true), .select(Self.retainedIDs[0]))
    }

    // MARK: Missing and invalid inputs

    func testAMissingOrInvalidThresholdKeepsTheActualAndItsOriginalsChances() {
        for bad in [Double.nan, -1, .infinity] {
            let input = Self.live(domain: nil, thresholds: [Self.threshold(0, quantity: bad), Self.threshold(1)])
            XCTAssertEqual(input.placements.map(\.index), [1])
            XCTAssertNil(input.panels[0].mark)
            XCTAssertEqual(input.panels[0].threshold?.label, "22.5", "its association stays; it just draws nothing")
            XCTAssertEqual(input.panels[0].channels, Self.live().panels[0].channels)
            XCTAssertEqual(input.panelAction(index: 0, canSelect: true), .select(Self.retainedIDs[0]))
            XCTAssertEqual(input.visibleActualQuantity, 18)
            XCTAssertEqual(input.domain, TotalMilestoneDomain10868(lower: 18, upper: 23.5))
            XCTAssertEqual(input.labels.map(\.text), ["23.5", "18 actual"])
        }
        let absent = Self.live(domain: nil, thresholds: [Self.threshold(1)])
        XCTAssertNil(absent.panels[0].threshold)
        XCTAssertNil(absent.panels[0].mark)
        XCTAssertEqual(absent.placements.map(\.index), [1])
        XCTAssertEqual(absent.panels.map(\.milestone.title), ["Under 22.5 games", "Under 23.5 games"], "the unplaced original stays named")
        let none = Self.live(domain: nil, thresholds: [])
        XCTAssertEqual(none.placements, [])
        XCTAssertTrue(none.showsPlot, "the count alone still draws")
        XCTAssertFalse(none.drawsThresholds)
        XCTAssertEqual(none.domain, TotalMilestoneDomain10868(lower: 18, upper: 18))
        XCTAssertFalse(none.accessibilityPlotLabel.contains("Hollow marks"))
    }

    func testAnUnavailableActualKeepsTheThresholdsAndChances() {
        let unavailable = Self.live(actual: .unavailable("Score unavailable"))
        XCTAssertEqual(unavailable.actualPresentation,
                       TotalMilestoneActualPresentation10868(title: "Count so far", actual: .unavailable("Score unavailable")))
        XCTAssertNil(unavailable.visibleActualQuantity)
        XCTAssertEqual(unavailable.accessibilityActualValue, "Score unavailable")
        XCTAssertEqual(unavailable.placements.map(\.quantity), [22.5, 23.5])
        XCTAssertEqual(unavailable.labels.map(\.kind), [.threshold(Self.homeMark), .threshold(Self.awayMark)])
        XCTAssertEqual(unavailable.domain, Self.retainedDomain)
        XCTAssertNil(try! XCTUnwrap(unavailable.plotModel(size: Self.plotSize, inset: Self.inset)).actualX)
        XCTAssertFalse(unavailable.accessibilityPlotLabel.contains("solid rule"))
        XCTAssertEqual(unavailable.panels.map(\.channels), Self.live().panels.map(\.channels))
        XCTAssertEqual(Self.live(actual: .unavailable("Score unavailable"), domain: nil).domain,
                       TotalMilestoneDomain10868(lower: 22.5, upper: 23.5))
        let invalid = Self.live(actual: Self.constructedCount(.nan, "—"), domain: nil)
        XCTAssertNil(invalid.visibleActualQuantity)
        XCTAssertEqual(invalid.domain, TotalMilestoneDomain10868(lower: 22.5, upper: 23.5))
        XCTAssertEqual(invalid.labels.map(\.text), ["22.5", "23.5"])
        let absent = Self.live(actual: nil)
        XCTAssertNil(absent.actualPresentation)
        XCTAssertEqual(absent.placements.count, 2)
        XCTAssertEqual(absent.visibleSubtotals, Self.retainedSubtotals, "subtotals are their own owner input")
    }

    func testCurrentChanceResultAndCountStaySeparate() {
        let reading = Self.obs(0.4, "40%", "5:21 AM", "constructed in-game reading")
        let recorded = TotalMilestoneCurrent10868.recorded(reading, movement: "15 pts lower than pre-match")
        let won = TotalMilestoneResult10868.won("Original Under 22.5: won")
        let rows = [Self.retainedRow(0, current: recorded, result: won),
                    Self.retainedRow(1, current: .withheld("No update since the last game"))]
        let input = Self.live(rows: rows)
        XCTAssertEqual(input.panels[0].channels, [.chance(title: "Pre-match chance", observation: Self.baseline(0)),
                                                  .chance(title: "Current chance", observation: reading)])
        XCTAssertEqual(input.panels[0].movement, "15 pts lower than pre-match")
        XCTAssertEqual(input.panels[0].result, won)
        XCTAssertEqual(input.panels[0].result?.mark, .check)
        XCTAssertEqual(input.panels[1].channels.last, .status(title: "Current chance", text: "No update since the last game"))
        XCTAssertNil(input.panels[1].movement)
        XCTAssertEqual(input.panels[1].result, Self.pending)
        XCTAssertEqual(input.accessibilityPanelValue(input.panels[0]),
                       "Pre-match chance: 55%, \(Self.baselineDetail); Current chance: 40%, constructed in-game reading; "
                       + "Change since pregame: 15 pts lower than pre-match; Original market result: Original Under 22.5: won; "
                       + "Market threshold: 22.5")
        // Moving the count past both thresholds moves no chance and no result.
        let past = Self.live(rows: rows, actual: Self.constructedCount(25, "25"))
        XCTAssertEqual(past.panels.map(\.channels), input.panels.map(\.channels))
        XCTAssertEqual(past.panels.map(\.result), [won, Self.pending])
        // A different result moves neither the count nor the chances.
        let lost = Self.live(rows: [Self.retainedRow(0, current: recorded, result: .lost("Original Under 22.5: lost")), rows[1]])
        XCTAssertEqual(lost.visibleActualQuantity, 18)
        XCTAssertEqual(lost.panels.map(\.channels), input.panels.map(\.channels))
        XCTAssertEqual(lost.panels[0].result?.mark, .cross)
        // A reached state is the count's own words, never a chance or 100%.
        let reached = Self.live(rows: [Self.retainedRow(0, current: .reached("Reached")), Self.retainedRow(1)])
        XCTAssertEqual(reached.panels[0].channels.last, .status(title: "Actual so far", text: "Reached"))
        XCTAssertFalse(reached.accessibilityPanelValue(reached.panels[0]).contains("100%"))
    }

    func testUnavailableIsNeverZeroAndAGenuineZeroKeepsItsBar() {
        XCTAssertEqual(try! XCTUnwrap(Self.barWidth(0.55)), 77, accuracy: 0.001)
        XCTAssertEqual(try! XCTUnwrap(Self.barWidth(0.605)), 84.7, accuracy: 0.001)
        XCTAssertEqual(try! XCTUnwrap(Self.barWidth(1)), 140, accuracy: 0.001)
        XCTAssertEqual(Self.barWidth(0), 0, "a real 0% keeps its place on the scale")
        for invalid in [Double.nan, -0.01, 1.2, .infinity] {
            XCTAssertNil(Self.barWidth(invalid), "never clamped")
        }
        XCTAssertNil(Self.barWidth(0.55, track: 0))
        XCTAssertNil(Self.barWidth(0.55, track: .nan))
        let zero = Self.obs(0, "0%", "12:54 AM", "constructed zero")
        let input = Self.live(rows: [Self.retainedRow(0, before: .some(nil)), Self.retainedRow(1, before: zero)])
        XCTAssertEqual(input.panels[0].channels.first, .status(title: "Pre-match chance", text: "Unavailable"))
        XCTAssertEqual(input.panels[0].channels.last, .status(title: "Current chance", text: "No recent price"))
        XCTAssertFalse(input.accessibilityPanelValue(input.panels[0]).contains("0%"))
        XCTAssertEqual(input.panels[1].channels.first, .chance(title: "Pre-match chance", observation: zero))
        XCTAssertEqual(input.panelAction(index: 0, canSelect: true), .select(Self.retainedIDs[0]), "a missing chance still opens its original")
        XCTAssertEqual(input.panelAction(index: 1, canSelect: true), .select(Self.retainedIDs[1]))
        let outOfRange = Self.obs(1.2, "120%", nil, "constructed out of range")
        let out = Self.live(rows: [Self.retainedRow(0, before: outOfRange), Self.retainedRow(1)])
        guard case .chance(_, let observation)? = out.panels[0].channels.first else { return XCTFail("figure kept") }
        XCTAssertEqual(observation.text, "120%", "the owner's figure is kept")
        XCTAssertNil(Self.barWidth(observation.probability), "but no bar is drawn for it")
    }

    // MARK: Identity

    func testForeignRepeatedAndMultiplyClaimedThresholdsLendNothing() {
        let thresholds = [
            TotalMilestoneThreshold10868(originalID: "constructed:foreign-original", quantity: 50, label: "50", mark: Self.homeMark),
            Self.threshold(0),
            Self.threshold(0, quantity: 29, label: "29"),
            Self.threshold(1),
            TotalMilestoneThreshold10868(originalID: "", quantity: 27, label: "27", mark: Self.awayMark),
        ]
        let input = Self.live(domain: nil, thresholds: thresholds)
        XCTAssertNil(input.threshold(forOriginalAt: 0), "two claims: neither is chosen")
        XCTAssertNil(input.panels[0].threshold)
        XCTAssertNil(input.panels[0].mark)
        XCTAssertEqual(input.placements.map(\.index), [1])
        XCTAssertEqual(input.placements.map(\.threshold.label), ["23.5"])
        XCTAssertEqual(input.domain, TotalMilestoneDomain10868(lower: 18, upper: 23.5), "no foreign, blank or rival quantity widens the axis")
        XCTAssertEqual(input.labels.map(\.text), ["23.5", "18 actual"])
        XCTAssertEqual(input.panels.count, 2, "no association becomes an original")
        XCTAssertEqual(input.panels[0].channels, Self.live().panels[0].channels, "the original itself stays whole")
        XCTAssertEqual(input.panelAction(index: 0, canSelect: true), .select(Self.retainedIDs[0]))
        XCTAssertFalse(input.accessibilityPanelValue(input.panels[0]).contains("Market threshold"))
        let near = Self.live(thresholds: [
            TotalMilestoneThreshold10868(originalID: Self.retainedIDs[0] + " ", quantity: 22.5, label: "22.5", mark: Self.homeMark),
            Self.threshold(1),
        ])
        XCTAssertNil(near.threshold(forOriginalAt: 0), "a near-match id is not the original")
        XCTAssertEqual(near.placements.map(\.index), [1])
    }

    func testBlankAndRepeatedOriginalsStayNamedWithoutChannelsOrActions() {
        let rows = [
            Self.retainedRow(0),
            Self.constructedRow(id: "   ", title: "Blank-id original", before: Self.obs(0.3, "30%", "12:54 AM", "constructed")),
            Self.constructedRow(id: "constructed:dup", title: "Repeated A", before: Self.obs(0.56, "56%", "12:54 AM", "constructed"),
                                result: .won("Won")),
            Self.constructedRow(id: "constructed:dup", title: "Repeated B", before: Self.obs(0.3, "30%", "12:54 AM", "constructed"),
                                result: .lost("Lost")),
            Self.retainedRow(1),
        ]
        let thresholds = Self.retainedThresholds + [
            TotalMilestoneThreshold10868(originalID: "   ", quantity: 21.5, label: "21.5", mark: Self.homeMark),
            TotalMilestoneThreshold10868(originalID: "constructed:dup", quantity: 24.5, label: "24.5", mark: Self.awayMark),
        ]
        let input = Self.live(rows: rows, domain: nil, thresholds: thresholds)
        XCTAssertEqual(input.panels.map(\.milestone.title),
                       ["Under 22.5 games", "Blank-id original", "Repeated A", "Repeated B", "Under 23.5 games"],
                       "every original stays named, in owner order")
        XCTAssertEqual(input.panels.map(\.isResolved), [true, false, false, false, true])
        for index in [1, 2, 3] {
            let panel = input.panels[index]
            XCTAssertEqual(panel.channels, [])
            XCTAssertNil(panel.result)
            XCTAssertNil(panel.threshold)
            XCTAssertNil(panel.mark)
            XCTAssertNil(panel.movement)
            XCTAssertFalse(panel.selected)
            XCTAssertEqual(input.accessibilityPanelValue(panel), "Original contract unavailable")
            XCTAssertNil(input.panelAction(index: index, canSelect: true))
        }
        XCTAssertEqual(input.placements.map(\.index), [0, 4])
        XCTAssertEqual(input.domain, TotalMilestoneDomain10868(lower: 18, upper: 23.5))
        XCTAssertEqual(input.panelAction(index: 0, canSelect: true), .select(Self.retainedIDs[0]))
        XCTAssertEqual(input.panelAction(index: 4, canSelect: true), .select(Self.retainedIDs[1]))
        let repeated = Self.live(rows: rows, selected: "constructed:dup")
        XCTAssertEqual(repeated.selection, .duplicate("constructed:dup"))
        XCTAssertTrue(repeated.panels.allSatisfy { !$0.selected })
        XCTAssertNil(repeated.detailsAction(canOpenDetails: true))
        XCTAssertEqual(Self.live(rows: rows, selected: "   ").selection, .missing("   "))
    }

    func testANaNObservationKeepsAValidOriginalReachable() {
        let nanRow = Self.retainedRow(0, before: Self.obs(.nan, "55%", "12:54 AM", "constructed NaN geometry"),
                                      current: .recorded(Self.obs(.nan, "—", nil, "constructed"), movement: nil))
        XCTAssertNotEqual(nanRow, nanRow, "NaN breaks whole-row equality, so membership is by id only")
        let timing = Self.timing(Self.retainedIDs[0])
        let input = Self.live(rows: [nanRow, Self.retainedRow(1)], selected: Self.retainedIDs[0], timing: timing)
        XCTAssertTrue(input.panels[0].isResolved)
        XCTAssertEqual(input.selection.index, 0)
        XCTAssertTrue(input.panels[0].selected)
        XCTAssertEqual(input.panels[0].mark, Self.homeMark, "its threshold still places")
        XCTAssertEqual(input.panelAction(index: 0, canSelect: true), .select(Self.retainedIDs[0]))
        XCTAssertEqual(input.detailsAction(canOpenDetails: true), .details(Self.retainedIDs[0]))
        XCTAssertEqual(input.timingPresentation(hasBinding: false), .expanded(timing))
        guard case .chance(_, let observation)? = input.panels[0].channels.first else { return XCTFail("figure kept") }
        XCTAssertEqual(observation.text, "55%")
        XCTAssertNil(Self.barWidth(observation.probability), "no bar for a chance the scale cannot place")
    }

    func testWithdrawnAndBlankHeldIDsSelectNobody() {
        let plain = Self.live()
        for held in ["constructed:withdrawn", "", "  "] {
            let input = Self.live(selected: held, timing: Self.timing(Self.retainedIDs[0]))
            XCTAssertNil(input.selection.milestone, held)
            XCTAssertEqual(input.selectionNotice, "Selected milestone unavailable.")
            XCTAssertTrue(input.panels.allSatisfy { !$0.selected })
            XCTAssertTrue(input.placements.allSatisfy { !$0.selected })
            XCTAssertNil(input.detailsAction(canOpenDetails: true))
            XCTAssertNil(input.timingPresentation(hasBinding: true))
            XCTAssertEqual(input.labels, plain.labels)
            XCTAssertEqual(input.plotModel(size: Self.plotSize, inset: Self.inset), plain.plotModel(size: Self.plotSize, inset: Self.inset))
            XCTAssertEqual(input.panelAction(index: 0, canSelect: true), .select(Self.retainedIDs[0]), "every original stays reachable")
        }
        XCTAssertEqual(Self.live(selected: "constructed:withdrawn").selection, .missing("constructed:withdrawn"))
        XCTAssertEqual(Self.live(selected: "").selection, .missing(""))
    }

    func testExtraOriginalsStayNamedReachableAndUncapped() {
        let extras = (0..<3).map { offset in
            Self.constructedRow(id: "constructed:extra:\(offset)", title: "Constructed extra \(offset)", quantity: 40 + Double(offset),
                                before: Self.obs(0.2 + Double(offset) / 10, "\(20 + 10 * offset)%", "12:54 AM", "constructed"))
        }
        let rows = [Self.retainedRow(0)] + extras + [Self.retainedRow(1)]
        let input = Self.live(rows: rows, domain: nil)
        XCTAssertEqual(input.panels.map(\.index), [0, 1, 2, 3, 4], "none capped")
        XCTAssertEqual(input.panels.map(\.milestone.title),
                       ["Under 22.5 games", "Constructed extra 0", "Constructed extra 1", "Constructed extra 2", "Under 23.5 games"])
        XCTAssertEqual(input.panels.map(\.isResolved), Array(repeating: true, count: 5))
        XCTAssertEqual(input.panels.map { $0.mark != nil }, [true, false, false, false, true])
        XCTAssertEqual(input.panels[2].channels.first, .chance(title: "Pre-match chance", observation: try! XCTUnwrap(extras[1].before)))
        XCTAssertEqual(input.placements.map(\.index), [0, 4])
        XCTAssertEqual(input.domain, TotalMilestoneDomain10868(lower: 18, upper: 23.5), "the extras' coordinates 40…42 are not thresholds")
        XCTAssertEqual((0..<5).map { input.panelAction(index: $0, canSelect: true) },
                       rows.map { TotalMilestoneAction10868?.some(.select($0.id)) })
    }

    // MARK: Actions

    func testActionsHandBackExactIDsAndCallbackFreeContentIsStatic() {
        let input = Self.live(selected: Self.retainedIDs[1])
        XCTAssertEqual((0..<2).map { input.panelAction(index: $0, canSelect: false) }, [nil, nil])
        XCTAssertNil(input.detailsAction(canOpenDetails: false))
        XCTAssertFalse(input.showsInvitation(canSelect: false, canOpenDetails: false))
        XCTAssertEqual((0..<2).map { input.panelAction(index: $0, canSelect: true) },
                       [.select(Self.retainedIDs[0]), .select(Self.retainedIDs[1])])
        XCTAssertNil(input.panelAction(index: 2, canSelect: true))
        XCTAssertNil(input.panelAction(index: -1, canSelect: true))
        XCTAssertEqual(input.detailsAction(canOpenDetails: true), .details(Self.retainedIDs[1]))
        XCTAssertTrue(input.showsInvitation(canSelect: true, canOpenDetails: false))
        XCTAssertTrue(input.showsInvitation(canSelect: false, canOpenDetails: true), "Details for the held original is a displayed control")
        XCTAssertFalse(Self.live().showsInvitation(canSelect: false, canOpenDetails: true), "nothing held, no Details control, no invitation")
        XCTAssertFalse(Self.live(words: Self.ownerWords(invitation: nil)).showsInvitation(canSelect: true, canOpenDetails: true))
        var selected: [String] = []
        var opened: [String] = []
        input.panelAction(index: 0, canSelect: true)?.perform(onSelect: { selected.append($0) }, onDetails: { opened.append($0) })
        input.detailsAction(canOpenDetails: true)?.perform(onSelect: { selected.append($0) }, onDetails: { opened.append($0) })
        XCTAssertEqual(selected, [Self.retainedIDs[0]])
        XCTAssertEqual(opened, [Self.retainedIDs[1]])
        let timed = Self.live(selected: Self.retainedIDs[1], timing: Self.timing(Self.retainedIDs[1]))
        XCTAssertEqual(timed.timingPresentation(hasBinding: true), .disclosure(Self.timing(Self.retainedIDs[1])))
        XCTAssertNil(Self.live(selected: Self.retainedIDs[0], timing: Self.timing(Self.retainedIDs[1])).timingPresentation(hasBinding: true))
    }

    // MARK: Label and panel planning

    func testNearbyThresholdLabelsStackIntoMeasuredRowsAndKeepTheirExactText() {
        let input = Self.live()
        XCTAssertEqual(input.labels.map(\.text), ["22.5", "23.5", "18 actual"], "each exact owner label, none merged")
        let sizes = [CGSize(width: 34, height: 16), CGSize(width: 34, height: 16), CGSize(width: 62, height: 16)]
        func plan(_ labels: [TotalMilestoneThresholdLabel10868], width: CGFloat, sizes: [CGSize],
                  domain: TotalMilestoneDomain10868?) -> TotalMilestoneChartPlan10868 {
            TotalMilestoneGeometry10868.chartPlan(width: width, plotHeight: 40, inset: Self.inset, domain: domain,
                                                  chanceFractions: [], chanceSizes: [],
                                                  annotationValues: labels.map(\.quantity), annotationSizes: sizes,
                                                  tickValues: [], tickSizes: [])
        }
        func assertApart(_ plan: TotalMilestoneChartPlan10868, width: CGFloat, _ message: String) {
            for a in plan.annotations.indices {
                for b in plan.annotations.indices where b > a {
                    XCTAssertFalse(plan.annotations[a].intersects(plan.annotations[b]), "\(message): \(a) and \(b)")
                }
            }
            XCTAssertTrue(plan.annotations.allSatisfy { $0.minX >= 0 && $0.maxX <= width + 0.001 && $0.maxY <= plan.plot.minY }, message)
        }
        let retainedPlan = plan(input.labels, width: 327, sizes: sizes, domain: input.domain)
        XCTAssertEqual(retainedPlan.annotations.count, 3)
        XCTAssertEqual(retainedPlan.plot.height, 40)
        XCTAssertNotEqual(retainedPlan.annotations[0].minY, retainedPlan.annotations[1].minY, "22.5 and 23.5 sit in separate measured rows")
        assertApart(retainedPlan, width: 327, "retained")

        let near = Self.live(thresholds: [Self.threshold(0), Self.threshold(1, quantity: 22.6, label: "22.6")])
        XCTAssertEqual(near.labels.map(\.text), ["22.5", "22.6", "18 actual"])
        assertApart(plan(near.labels, width: 327, sizes: sizes, domain: near.domain), width: 327, "near-coincident")

        let wrapped = [CGSize(width: 200, height: 44), CGSize(width: 96, height: 22), CGSize(width: 62, height: 22)]
        assertApart(plan(input.labels, width: 200, sizes: wrapped, domain: input.domain), width: 200, "enlarged and wrapped")

        let ends = Self.live(thresholds: [Self.threshold(0, quantity: 0, label: "0"), Self.threshold(1, quantity: 30, label: "30")])
        assertApart(plan(ends.labels, width: 327, sizes: sizes, domain: ends.domain), width: 327, "axis ends")
    }

    func testPanelColumnsComeFromWidthAndFigureScaleNotFromLongWords() {
        let longStatus = "Current probability unavailable — the capture does not establish reliable current trading"
        let longTitle = "Under 22.5 games in the whole match, both players combined, every set counted"
        let longClock = "Recorded 12:54 AM PT on Oct 12, before the verified 3:55 AM PT start of play"
        let rows = [Self.retainedRow(0, title: longTitle, before: Self.obs(0.55, "55%", longClock, Self.baselineDetail),
                                     current: .unavailable(longStatus)),
                    Self.retainedRow(1, current: .unavailable(longStatus))]
        let input = Self.live(rows: rows)
        XCTAssertEqual(input.panels[0].milestone.title, longTitle, "the owner's full words, never abbreviated")
        XCTAssertEqual(input.panels.map { $0.channels.last }, [.status(title: "Current chance", text: longStatus),
                                                              .status(title: "Current chance", text: longStatus)])
        guard case .chance(_, let observation)? = input.panels[0].channels.first else { return XCTFail("figure kept") }
        XCTAssertEqual(observation.timeText, longClock)
        XCTAssertTrue(input.accessibilityPlotValue.contains(longTitle))
        XCTAssertEqual(input.panelAction(index: 0, canSelect: true), .select(Self.retainedIDs[0]))
        func columns(_ width: CGFloat, minimum: CGFloat = 132, accessibility: Bool = false, count: Int = 2) -> Int {
            TotalMilestoneThresholdLiveInput10868.panelColumns(count: count, width: width, spacing: 8,
                                                               minimumCellWidth: minimum, accessibility: accessibility)
        }
        XCTAssertEqual(columns(327, count: input.panels.count), 2, "the long words wrap inside the pair at phone width")
        XCTAssertEqual(columns(288), 2, "a small phone keeps the pair")
        XCTAssertEqual(columns(260), 1, "narrower than two readable panels: stacked")
        XCTAssertEqual(columns(327, minimum: 178), 1, "enlarged figures need wider panels")
        XCTAssertEqual(columns(900, accessibility: true), 1, "accessibility sizes are one column")
        XCTAssertEqual(columns(900, count: 5), 5, "a wide view shows every extra original")
        XCTAssertEqual(columns(327, count: 5), 2)
        XCTAssertEqual(columns(.nan), 1)
        XCTAssertEqual(TotalMilestoneGeometry10868.stripCellWidth(columns: 2, width: 327, spacing: 8), 159.5, accuracy: 0.001)
        // Wrapped panels share a row as tall as the taller one; stacked ones keep every panel.
        let pair = TotalMilestoneGeometry10868.stripFrames(columns: 2, cellWidth: 159.5, heights: [340, 210], spacing: 8)
        XCTAssertEqual(pair.frames.map(\.minX), [0, 167.5])
        XCTAssertEqual(pair.frames.map(\.height), [340, 340])
        XCTAssertEqual(pair.size, CGSize(width: 327, height: 340))
        let stacked = TotalMilestoneGeometry10868.stripFrames(columns: 1, cellWidth: 260, heights: [420, 300], spacing: 8)
        XCTAssertEqual(stacked.frames.count, 2, "no original is hidden")
        XCTAssertEqual(stacked.frames[1].minY, 428)
        XCTAssertEqual(stacked.size, CGSize(width: 260, height: 728))
        XCTAssertTrue((pair.frames + stacked.frames).allSatisfy { $0.width >= 44 && $0.height >= 44 })
    }

    // MARK: Spoken text

    func testSpokenMeaningsNameChanceThresholdCountAndResultApart() {
        let input = Self.live()
        XCTAssertEqual(input.accessibilityHeader, "TOTAL GAMES · STILL IN PLAY. 18 games played so far. During play")
        XCTAssertEqual(input.accessibilityActualValue, "18 games, \(Self.actualDetail)")
        XCTAssertEqual(input.accessibilitySubtotals, "Games won: Fils 8, Zandschulp 10")
        XCTAssertEqual(input.accessibilityPlotLabel,
                       "Total games in the match Hollow marks are the original market thresholds: quantities on the count scale, "
                       + "not chances and not projected final scores. The solid rule is the count, not a chance.")
        XCTAssertEqual(input.accessibilityPlotValue,
                       "Count so far: 18 games; Under 22.5 games: Market threshold 22.5; Under 23.5 games: Market threshold 23.5")
        XCTAssertFalse(input.accessibilityPlotValue.contains("%"), "the axis speaks quantities, never chances")
        XCTAssertEqual(input.panels.map { input.accessibilityPanelValue($0) }, [
            "Pre-match chance: 55%, \(Self.baselineDetail); Current chance: No recent price; Original market result: Result pending; Market threshold: 22.5",
            "Pre-match chance: 60.5%, \(Self.baselineDetail); Current chance: No recent price; Original market result: Result pending; Market threshold: 23.5",
        ])
        XCTAssertEqual(TotalMilestoneThresholdLiveInput10868.resultTitle, "Original market result")
        XCTAssertEqual(TotalMilestoneThresholdLiveAccessibilityID10868.option(Self.retainedIDs[0]),
                       "totalMilestoneThreshold10868.option.constructed:15327807:polymarket:65197799:245152784")
        XCTAssertEqual(TotalMilestoneThresholdLiveAccessibilityID10868.details(Self.retainedIDs[1]),
                       "totalMilestoneThreshold10868.details.constructed:15327807:polymarket:65197800:245152786")
    }
}

// MARK: Pregame total-game threshold reuse — PREPARED, NOT_RUN
// Retained baselines/thresholds reuse the exact two original Under histories
// above. Copy, identity associations and contradictory later payloads are
// constructed owner inputs, not production bindings or native frame evidence.
extension TotalMilestoneThresholdLive10868Tests {
    private static let pregameCopy = TotalMilestoneThresholdBefore10868(
        eyebrow: "TOTAL GAMES · BEFORE PLAY", title: "Compare the original total-game chances",
        note: "The marks are original total-game conditions, not a forecast.")

    private static func beforeCard(
        rows: [TotalMilestoneRow10868] = retainedRows,
        selected: String? = nil,
        actual: TotalMilestoneActual10868? = retainedActual,
        domain: TotalMilestoneDomain10868? = retainedDomain,
        timing: TotalMilestoneTiming10868? = nil,
        thresholds: [TotalMilestoneThreshold10868] = retainedThresholds,
        shareUnit: Bool = true,
        copy: TotalMilestoneThresholdBefore10868? = pregameCopy
    ) -> TotalMilestoneThresholdLiveInput10868 {
        var input = live(.before, rows: rows, selected: selected, actual: actual, domain: domain,
                         timing: timing, thresholds: thresholds, shareUnit: shareUnit)
        input.beforePresentation = copy
        return input
    }

    func testPregameRequiresExplicitAdmissionAndKeepsTheTruePhase() {
        let legacy = Self.live(.before)
        XCTAssertNil(legacy.beforePresentation)
        XCTAssertFalse(legacy.isPresented)
        XCTAssertEqual(legacy.panels, [])
        XCTAssertEqual(legacy.placements, [])
        XCTAssertNil(legacy.panelAction(index: 0, canSelect: true))
        XCTAssertFalse(Self.beforeCard(copy: nil).isPresented)
        let input = Self.beforeCard()
        XCTAssertTrue(input.isPresented)
        XCTAssertEqual(input.profile.phase, .before)
        XCTAssertEqual(input.profile, legacy.profile, "the opt-in never rewrites phase or payload")
    }

    func testPregameRetainedOwnChancesAndClocksStayOnSeparateFixedRails() {
        let input = Self.beforeCard()
        XCTAssertEqual(input.panels.map(\.milestone.id), Self.retainedIDs)
        XCTAssertEqual(input.panels.map(\.milestone.title), ["Under 22.5 games", "Under 23.5 games"])
        XCTAssertEqual(input.panels.map(\.channels), [
            [.chance(title: "Pre-match chance", observation: Self.baseline(0))],
            [.chance(title: "Pre-match chance", observation: Self.baseline(1))],
        ])
        XCTAssertEqual(try! XCTUnwrap(Self.barWidth(0.55, track: 200)), 110, accuracy: 0.001)
        XCTAssertEqual(try! XCTUnwrap(Self.barWidth(0.605, track: 200)), 121, accuracy: 0.001)
        XCTAssertEqual(Self.barWidth(0, track: 200), 0)
        XCTAssertEqual(Self.barWidth(1, track: 200), 200)
        XCTAssertEqual(input.panels.map { input.accessibilityPanelValue($0) }, [
            "Pre-match chance: 55%, \(Self.baselineDetail); Market threshold: 22.5",
            "Pre-match chance: 60.5%, \(Self.baselineDetail); Market threshold: 23.5",
        ])
    }

    func testPregameUsesLiteralThresholdsNotDiscreteOverCountsOrActual() {
        let input = Self.beforeCard(domain: nil)
        XCTAssertEqual(input.profile.milestones.map(\.quantity), [23, 24])
        XCTAssertEqual(input.placements.map(\.quantity), [22.5, 23.5])
        XCTAssertEqual(input.labels.map(\.text), ["22.5", "23.5"])
        XCTAssertEqual(input.domain, TotalMilestoneDomain10868(lower: 22.5, upper: 23.5))
        XCTAssertNil(input.visibleActualQuantity)
        let plot = input.plotModel(size: Self.plotSize, inset: Self.inset)
        XCTAssertNil(plot?.actualX)
        XCTAssertEqual(plot?.marks.count, 2)
        XCTAssertEqual(input.accessibilityPlotValue,
                       "Under 22.5 games: Market threshold 22.5; Under 23.5 games: Market threshold 23.5")
        XCTAssertFalse(input.accessibilityPlotLabel.contains("solid rule"))
    }

    func testPregameSuppressesContradictoryLaterPayloadsAndTheirSpeech() {
        let current = TotalMilestoneCurrent10868.recorded(
            Self.obs(0.73, "73%", "Later quote clock", "Later quote evidence"), movement: "Later movement")
        let rows = [Self.retainedRow(0, current: current, result: .won("Later won result")),
                    Self.retainedRow(1, current: .unavailable("Later unavailable"), result: .lost("Later lost result"))]
        let timing = TotalMilestoneTiming10868(milestoneID: Self.retainedIDs[0], title: "Later timing",
                                               lines: ["Later live capture clock"])
        let input = Self.beforeCard(rows: rows, selected: Self.retainedIDs[0], timing: timing)
        XCTAssertNil(input.actualPresentation)
        XCTAssertNil(input.accessibilityActualValue)
        XCTAssertEqual(input.visibleSubtotals, [])
        XCTAssertEqual(input.accessibilitySubtotals, "")
        XCTAssertTrue(input.panels.allSatisfy { $0.channels.count == 1 && $0.movement == nil && $0.result == nil })
        XCTAssertNil(input.timingPresentation(hasBinding: false))
        XCTAssertNil(input.timingPresentation(hasBinding: true))
        let spoken = ([input.accessibilityHeader, input.accessibilityPlotLabel, input.accessibilityPlotValue,
                       input.accessibilitySubtotals, input.accessibilityActualValue ?? ""]
                      + input.panels.map { input.accessibilityPanelValue($0) }).joined(separator: " ")
        for forbidden in ["Later", "73%", "18", "Fils 8", "Zandschulp 10", "Current chance", "Original market result",
                          "Count so far", "Change since pregame", "STILL IN PLAY", "During play"] {
            XCTAssertFalse(spoken.contains(forbidden), forbidden)
        }
        XCTAssertTrue(spoken.contains(Self.baselineDetail), "only each baseline's own clock remains")
        XCTAssertEqual(input.profile.timing, timing, "retained payload is not mutated")
    }

    func testPregamePhaseSpecificCopyNeverFallsBackToLiveCopy() {
        let input = Self.beforeCard()
        XCTAssertEqual(input.displayedTitle, Self.pregameCopy.title)
        XCTAssertEqual(input.displayedEyebrow, Self.pregameCopy.eyebrow)
        XCTAssertEqual(input.displayedNote, Self.pregameCopy.note)
        XCTAssertEqual(input.accessibilityHeader,
                       "TOTAL GAMES · BEFORE PLAY. Compare the original total-game chances. Before play")
        let minimal = Self.beforeCard(copy: TotalMilestoneThresholdBefore10868(eyebrow: nil, title: "Original conditions", note: nil))
        XCTAssertNil(minimal.displayedEyebrow, "nil is not permission to reuse the live eyebrow")
        XCTAssertNil(minimal.displayedNote, "nil is not permission to reuse the unfinished-match note")
        XCTAssertEqual(minimal.accessibilityHeader, "Original conditions. Before play")
        XCTAssertEqual(minimal.profile.title, "18 games played so far", "negative live copy remains in the fixture only")
    }

    func testPregameMissingAndZeroStayDistinctWithoutBorrowingLaterOrNeighborReadings() {
        let rows = [Self.retainedRow(0, before: .some(nil),
                                    current: .recorded(Self.obs(0.73, "73%", "Later", "Later"), movement: nil)),
                    Self.retainedRow(1, before: Self.obs(0, "0%", nil, "Constructed zero before chance"))]
        let input = Self.beforeCard(rows: rows)
        XCTAssertEqual(input.panels[0].channels, [.status(title: "Pre-match chance", text: Self.missingWords)])
        XCTAssertEqual(input.panels[1].channels,
                       [.chance(title: "Pre-match chance", observation: try! XCTUnwrap(rows[1].before))])
        XCTAssertEqual(Self.barWidth(0), 0)
        XCTAssertFalse(input.accessibilityPanelValue(input.panels[0]).contains("0%"))
        XCTAssertFalse(input.accessibilityPanelValue(input.panels[0]).contains("73%"))
        XCTAssertEqual(input.panelAction(index: 0, canSelect: true), .select(Self.retainedIDs[0]))
    }

    func testPregameInvalidChanceGeometryDoesNotWithdrawAnExactOriginal() {
        for value in [Double.nan, .infinity, -.infinity, -0.1, 1.1] {
            let row = Self.retainedRow(0, before: Self.obs(value, "Owner figure", "Before clock", "Before detail"))
            let input = Self.beforeCard(rows: [row, Self.retainedRow(1)], selected: row.id)
            XCTAssertTrue(input.panels[0].isResolved)
            XCTAssertTrue(input.panels[0].selected)
            XCTAssertEqual(input.panels[0].channels.count, 1)
            XCTAssertNil(Self.barWidth(value))
            XCTAssertEqual(input.panelAction(index: 0, canSelect: true), .select(row.id))
            XCTAssertEqual(input.detailsAction(canOpenDetails: true), .details(row.id))
            XCTAssertEqual(input.placements.map(\.quantity), [22.5, 23.5])
        }
    }

    func testPregameDuplicateBlankAndWithdrawnIdentityNeverSelectsANeighbor() {
        let blank = Self.constructedRow(id: "  ", title: "Blank original", before: Self.baseline(0))
        let rows = [Self.retainedRow(0), Self.retainedRow(0), blank, Self.retainedRow(1)]
        let input = Self.beforeCard(rows: rows, selected: Self.retainedIDs[0])
        XCTAssertEqual(input.panels.map(\.isResolved), [false, false, false, true])
        XCTAssertEqual(input.panels.count, 4, "all originals remain named")
        XCTAssertEqual(input.selection, .duplicate(Self.retainedIDs[0]))
        XCTAssertEqual(input.placements.map(\.index), [3])
        for index in [0, 1, 2] {
            XCTAssertNil(input.panelAction(index: index, canSelect: true))
            XCTAssertEqual(input.panels[index].channels, [])
            XCTAssertEqual(input.accessibilityPanelValue(input.panels[index]), "Original contract unavailable")
        }
        for id in ["withdrawn", "", "  "] {
            let held = Self.beforeCard(selected: id)
            XCTAssertNil(held.selection.milestone)
            XCTAssertTrue(held.panels.allSatisfy { !$0.selected })
            XCTAssertNil(held.detailsAction(canOpenDetails: true))
            XCTAssertEqual(held.selectionNotice, "Selected milestone unavailable.")
            XCTAssertEqual(held.panelAction(index: 1, canSelect: true), .select(Self.retainedIDs[1]))
        }
    }

    func testPregameForeignDuplicateAndInvalidThresholdsNeverAcquireOtherOriginals() {
        let foreign = TotalMilestoneThreshold10868(originalID: "foreign", quantity: 40, label: "40", mark: Self.homeMark)
        let duplicate = Self.beforeCard(thresholds: [Self.threshold(0), Self.threshold(0), foreign])
        XCTAssertEqual(duplicate.placements, [])
        XCTAssertTrue(duplicate.panels.allSatisfy { $0.threshold == nil && $0.mark == nil })
        XCTAssertEqual(duplicate.panels.map(\.channels.count), [1, 1])
        for value in [Double.nan, .infinity, -1] {
            let invalid = Self.beforeCard(thresholds: [Self.threshold(0, quantity: value), Self.threshold(1)])
            XCTAssertEqual(invalid.placements.map(\.index), [1])
            XCTAssertNil(invalid.panels[0].mark)
            XCTAssertEqual(invalid.panelAction(index: 0, canSelect: true), .select(Self.retainedIDs[0]))
        }
    }

    func testPregameSameUnitGateAndSelectionCannotMoveTheQuantityAxis() {
        let baseline = Self.beforeCard()
        for id in Self.retainedIDs {
            let selected = Self.beforeCard(selected: id)
            XCTAssertEqual(selected.domain, baseline.domain)
            XCTAssertEqual(selected.labels, baseline.labels)
            XCTAssertEqual(selected.plotModel(size: Self.plotSize, inset: Self.inset)?.marks.map(\.x),
                           baseline.plotModel(size: Self.plotSize, inset: Self.inset)?.marks.map(\.x))
        }
        let mismatch = Self.beforeCard(shareUnit: false)
        XCTAssertNil(mismatch.domain)
        XCTAssertFalse(mismatch.showsPlot)
        XCTAssertEqual(mismatch.labels, [])
        XCTAssertEqual(mismatch.panels.map(\.channels), baseline.panels.map(\.channels))
        XCTAssertEqual(mismatch.panelAction(index: 1, canSelect: true), .select(Self.retainedIDs[1]))
    }

    func testPregameGenuineActionsStayOwnerDrivenAndCallbackFreeContentStaysStatic() {
        let input = Self.beforeCard(selected: Self.retainedIDs[1])
        XCTAssertNil(input.panelAction(index: 0, canSelect: false))
        XCTAssertNil(input.detailsAction(canOpenDetails: false))
        XCTAssertFalse(input.showsInvitation(canSelect: false, canOpenDetails: false))
        XCTAssertTrue(input.showsInvitation(canSelect: true, canOpenDetails: false))
        XCTAssertTrue(input.showsInvitation(canSelect: false, canOpenDetails: true))
        var selected: [String] = []
        var opened: [String] = []
        input.panelAction(index: 0, canSelect: true)?.perform(onSelect: { selected.append($0) }, onDetails: nil)
        input.detailsAction(canOpenDetails: true)?.perform(onSelect: nil, onDetails: { opened.append($0) })
        XCTAssertEqual(selected, [Self.retainedIDs[0]])
        XCTAssertEqual(opened, [Self.retainedIDs[1]])
        XCTAssertEqual(input.selection.index, 1, "callbacks do not mutate the owner's held selection")
    }

    func testPregameLongLabelsAndExtraOriginalsKeepTheBoundedPanelLayout() {
        let longTitle = "Under 22.5 games in the whole match, both players combined, every set counted"
        let longClock = "Recorded Oct 12 at 12:54 AM PT before the verified 3:55 AM PT start"
        let extra = Self.constructedRow(id: "extra", title: "Owner extra original", before: nil)
        let rows = [Self.retainedRow(0, title: longTitle, before: Self.obs(0.55, "55%", longClock, Self.baselineDetail)),
                    Self.retainedRow(1), extra]
        let input = Self.beforeCard(rows: rows)
        XCTAssertEqual(input.panels.count, 3)
        XCTAssertEqual(input.panels[0].milestone.title, longTitle)
        XCTAssertEqual(input.panels[0].channels,
                       [.chance(title: "Pre-match chance", observation: try! XCTUnwrap(rows[0].before))])
        XCTAssertEqual(input.panelAction(index: 2, canSelect: true), .select("extra"))
        for (width, minimum, accessibility, expected) in [
            (288.0, 132.0, false, 2), (327.0, 132.0, false, 2),
            (260.0, 132.0, false, 1), (327.0, 178.0, false, 1),
            (900.0, 132.0, true, 1), (900.0, 132.0, false, 3),
        ] {
            XCTAssertEqual(TotalMilestoneThresholdLiveInput10868.panelColumns(
                count: input.panels.count, width: CGFloat(width), spacing: 8,
                minimumCellWidth: CGFloat(minimum), accessibility: accessibility), expected)
        }
    }

    func testPregameOptionDoesNotChangeLiveOrEnableFinalComposition() {
        for phase in [TotalMilestonePhase10868.during, .final] {
            let legacy = Self.live(phase, selected: Self.retainedIDs[0], timing: Self.timing(Self.retainedIDs[0]))
            var opted = legacy
            opted.beforePresentation = Self.pregameCopy
            XCTAssertEqual(opted.isPresented, legacy.isPresented)
            XCTAssertEqual(opted.panels, legacy.panels)
            XCTAssertEqual(opted.actualPresentation, legacy.actualPresentation)
            XCTAssertEqual(opted.visibleSubtotals, legacy.visibleSubtotals)
            XCTAssertEqual(opted.domain, legacy.domain)
            XCTAssertEqual(opted.displayedTitle, legacy.profile.title)
            XCTAssertEqual(opted.displayedEyebrow, legacy.profile.eyebrow)
            XCTAssertEqual(opted.displayedNote, legacy.words.note)
            XCTAssertEqual(opted.accessibilityHeader, legacy.accessibilityHeader)
            XCTAssertEqual(opted.timingPresentation(hasBinding: true), legacy.timingPresentation(hasBinding: true))
        }
        XCTAssertFalse(Self.live(.final).isPresented)
    }
}

extension TotalMilestoneThresholdLive10868Tests {
    func testPregameReachedWithheldPerformanceAndProjectionCannotLeakIntoPanelsOrGeometry() {
        let projection = TotalMilestoneProjection10868(quantity: 100, title: "Later projection", text: "100 games",
                                                       clock: "Later forecast clock", ruleLabel: "Later forecast",
                                                       comparison: "Later comparison", accessibilityDetail: "Later forecast detail")
        for current in [TotalMilestoneCurrent10868.reached("Later reached condition"), .withheld("Later withheld quote")] {
            let row = TotalMilestoneRow10868(id: Self.retainedIDs[0], quantity: 23, quantityLabel: "constructed",
                                             title: "Under 22.5 games", before: Self.baseline(0), beforeMissing: "Unavailable",
                                             current: current, performance: "Later performance", result: .won("Later result"))
            var input = Self.live(.before, rows: [row, Self.retainedRow(1)],
                                  actual: Self.constructedCount(99, "99"), projection: projection, domain: nil)
            input.beforePresentation = Self.pregameCopy
            XCTAssertEqual(input.domain, TotalMilestoneDomain10868(lower: 22.5, upper: 23.5))
            XCTAssertNil(input.plotModel(size: Self.plotSize, inset: Self.inset)?.actualX)
            XCTAssertNil(input.actualPresentation)
            XCTAssertNil(input.panels[0].movement)
            XCTAssertNil(input.panels[0].result)
            XCTAssertEqual(input.panels[0].channels, [.chance(title: "Pre-match chance", observation: Self.baseline(0))])
            XCTAssertFalse(input.accessibilityPanelValue(input.panels[0]).contains("Later"))
            XCTAssertFalse(input.accessibilityPlotValue.contains("99"))
            XCTAssertFalse(input.accessibilityPlotValue.contains("100"))
        }
    }

    func testPregameZeroThresholdIsDrawableAndUnknownBaselineClockStaysUnknown() {
        let row = Self.retainedRow(0, before: Self.obs(0, "0%", nil, "Before observation time unavailable"))
        let input = Self.beforeCard(rows: [row, Self.retainedRow(1)],
                                    thresholds: [Self.threshold(0, quantity: 0, label: "0"), Self.threshold(1)])
        XCTAssertEqual(input.placements.map(\.quantity), [0, 23.5])
        XCTAssertEqual(input.labels.map(\.text), ["0", "23.5"])
        guard case .chance(_, let observation)? = input.panels[0].channels.first else {
            return XCTFail("zero remains a recorded before reading")
        }
        XCTAssertNil(observation.timeText)
        XCTAssertEqual(Self.barWidth(observation.probability), 0)
        XCTAssertTrue(input.accessibilityPanelValue(input.panels[0]).contains("time unavailable"))
        XCTAssertFalse(input.accessibilityPanelValue(input.panels[0]).contains(Self.baselineClock))
    }
}
