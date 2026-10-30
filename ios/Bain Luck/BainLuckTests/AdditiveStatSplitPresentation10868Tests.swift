import SwiftUI
import XCTest
@testable import Bain_Luck

/// #10868 — the signed ground + air split beside the combined-yard card
/// (ADDITIVE-STAT-SPLIT-NEXT-SOURCE.md). The three players and their final
/// actuals are REAL, from ADDITIVE-STAT-SPLIT-RETAINED-CASES.json (Final
/// phase, Bears–Eagles): Swift 84 + 4 = 88, Barkley 82 + −2 = 80, Monangai
/// combined and split absent. The retained Before and During phases carry no
/// actual. The owner's figure text, endpoints, axis and ticks are CONSTRUCTED
/// presentation inputs an owner would supply; every live (actual-so-far),
/// zero, provenance, invalid or mismatched case is CONSTRUCTED and says so,
/// and none uses a real player's name.
@MainActor
final class AdditiveStatSplitPresentation10868Tests: XCTestCase {

    private typealias Leaf = AdditiveStatSplitPresentation10868
    private typealias Geometry = AdditiveStatSplitGeometry10868

    // MARK: Fixtures

    /// CONSTRUCTED: the owner's shared axis, 0–100 yards.
    private let yards = AdditiveStatSplitAxis10868(
        lower: 0, upper: 100,
        ticks: [.init(value: 0, text: "0"), .init(value: 50, text: "50"), .init(value: 100, text: "100")],
        unit: "yards")

    private func figure(_ text: String, unit: String = "yards", provenance: String? = nil) -> AdditiveStatSplitFigure10868 {
        AdditiveStatSplitFigure10868(text: text, unit: unit, provenance: provenance)
    }

    private func component(_ id: String, _ name: String, _ text: String, from start: Double, to end: Double,
                           emphasis: AdditiveStatSplitEmphasis10868 = .primary) -> AdditiveStatSplitComponent10868 {
        AdditiveStatSplitComponent10868(id: id, name: name, emphasis: emphasis,
                                        reading: .value(figure(text), span: .init(start: start, end: end)))
    }

    private func input(_ subject: String, phase: AdditiveStatSplitPhase10868, actual: AdditiveStatSplitActual10868,
                       axis: AdditiveStatSplitAxis10868? = nil, detailsID: String? = nil) -> AdditiveStatSplitInput10868 {
        AdditiveStatSplitInput10868(subject: subject, totalName: "Combined", phase: phase, actual: actual,
                                    axis: axis ?? yards, detailsID: detailsID)
    }

    /// REAL actuals (retained Final): D'Andre Swift, Bears — 84 rushing, 4
    /// receiving, 88 combined. Endpoints CONSTRUCTED from those values.
    private var swiftFinal: AdditiveStatSplitReading10868 {
        AdditiveStatSplitReading10868(
            total: .value(figure("88")),
            split: .qualified([component("rushing", "Ground", "84", from: 0, to: 84, emphasis: .primary),
                               component("receiving", "Air", "4", from: 84, to: 88, emphasis: .secondary)]))
    }

    /// REAL actuals (retained Final): Saquon Barkley, Eagles — 82 rushing, −2
    /// receiving, 80 combined.
    private var barkleyFinal: AdditiveStatSplitReading10868 {
        AdditiveStatSplitReading10868(
            total: .value(figure("80")),
            split: .qualified([component("rushing", "Ground", "82", from: 0, to: 82, emphasis: .primary),
                               component("receiving", "Air", "\u{2212}2", from: 82, to: 80, emphasis: .secondary)]))
    }

    /// REAL absence (retained Final): Kyle Monangai, Bears — combined actual
    /// null on all 3 combined rows, so the split is not qualified. His 31
    /// rushing yards are deliberately NOT supplied: receiving is null and no
    /// combined figure may be built from one component. Words CONSTRUCTED.
    private var monangaiFinal: AdditiveStatSplitReading10868 {
        AdditiveStatSplitReading10868(total: .unavailable("Unavailable"),
                                      split: .unavailable("Final yard split unavailable"))
    }

    /// REAL exact originals (retained Final `defaultOriginalKey`), opaque to the leaf.
    private let swiftOriginal = "player_props:159"
    private let barkleyOriginal = "player_props:161"
    private let monangaiOriginal = "player_props:164"

    private var realFinals: [(String, AdditiveStatSplitReading10868, [String])] {
        [("D'Andre Swift", swiftFinal, ["84", "88"]),
         ("Saquon Barkley", barkleyFinal, ["82", "\u{2212}2", "80"]),
         ("Kyle Monangai", monangaiFinal, [])]
    }

    // MARK: The three real players

    func test_realSwift_final_showsGroundAirAndCombinedVerbatimInOwnerOrder() {
        let readout = Leaf.readout(input("D'Andre Swift", phase: .final, actual: .final(swiftFinal), detailsID: swiftOriginal))
        XCTAssertEqual(readout.status, .shown)
        XCTAssertEqual(readout.caption, "Final actual")
        XCTAssertEqual(readout.total?.text, "88 yards")
        XCTAssertEqual(readout.total?.isFigure, true)
        XCTAssertEqual(readout.lanes.map(\.name), ["Ground", "Air"])
        XCTAssertEqual(readout.lanes.map(\.text), ["84 yards", "4 yards"], "no sign is added to a positive figure")
        XCTAssertEqual(readout.lanes.map(\.mark), [.bar(from: 0, to: 0.84), .bar(from: 0.84, to: 0.88)])
        XCTAssertEqual(readout.lanes.map(\.mark.direction), [.forward, .forward])
        XCTAssertEqual(readout.lanes.map(\.emphasis), [.primary, .secondary])
        XCTAssertNil(readout.splitWords)
    }

    func test_realBarkley_negativeAirKeepsItsSignAndRunsBackward() {
        let readout = Leaf.readout(input("Saquon Barkley", phase: .final, actual: .final(barkleyFinal)))
        let air = readout.lanes[1]
        XCTAssertEqual(air.text, "\u{2212}2 yards")
        XCTAssertEqual(air.mark, .bar(from: 0.82, to: 0.80))
        XCTAssertEqual(air.mark.direction, .backward, "a negative contribution is never drawn as positive yardage")
        XCTAssertEqual(readout.total?.text, "80 yards")
        XCTAssertEqual(readout.lanes[0].mark, .bar(from: 0, to: 0.82))
    }

    func test_realMonangai_final_combinedAndSplitUnavailable_neverZeroOrOneComponent() {
        let readout = Leaf.readout(input("Kyle Monangai", phase: .final, actual: .final(monangaiFinal), detailsID: monangaiOriginal))
        XCTAssertEqual(readout.status, .shown)
        XCTAssertEqual(readout.total?.text, "Unavailable")
        XCTAssertEqual(readout.total?.isFigure, false)
        XCTAssertEqual(readout.splitWords, "Final yard split unavailable")
        XCTAssertTrue(readout.lanes.isEmpty)
        XCTAssertNil(readout.axis, "nothing drawn, so no axis")
        XCTAssertFalse(readout.spoken.contains("0 yards"))
        XCTAssertFalse(readout.spoken.contains("31"))
    }

    func test_realPlayers_before_hidesEveryPhysicalCountEvenWhenFinalIsCarried() {
        for (name, reading, figures) in realFinals {
            let readout = Leaf.readout(input(name, phase: .before, actual: .final(reading)))
            XCTAssertEqual(readout.status, .hidden, name)
            XCTAssertNil(readout.total, name)
            XCTAssertTrue(readout.lanes.isEmpty, name)
            XCTAssertNil(readout.axis, name)
            XCTAssertEqual(readout.spoken, "\(name), actual split hidden before play")
            for figure in figures { XCTAssertFalse(readout.spoken.contains(figure), "\(name) leaks \(figure)") }
        }
    }

    func test_realPlayers_retainedDuringHasNoActual_soItReadsTheOwnersAbsence() {
        // The retained During phase carries no live count; the owner's words are CONSTRUCTED.
        for (name, _, _) in realFinals {
            let readout = Leaf.readout(input(name, phase: .during, actual: .absent("Actual so far unavailable in this capture")))
            XCTAssertEqual(readout.status, .words("Actual so far unavailable in this capture"), name)
            XCTAssertTrue(readout.lanes.isEmpty, name)
            XCTAssertNil(readout.total, name)
        }
    }

    // MARK: Phase gates (CONSTRUCTED)

    func test_constructedDuring_showsOnlyAnIndependentActualSoFar() {
        let soFar = AdditiveStatSplitReading10868(
            total: .value(figure("37")),
            split: .qualified([component("rushing", "Ground", "31", from: 0, to: 31),
                               component("receiving", "Air", "6", from: 31, to: 37)]))
        let readout = Leaf.readout(input("Constructed Runner", phase: .during, actual: .soFar(soFar)))
        XCTAssertEqual(readout.status, .shown)
        XCTAssertEqual(readout.caption, "Actual so far")
        XCTAssertEqual(readout.total?.text, "37 yards")
        XCTAssertTrue(readout.spoken.hasPrefix("Constructed Runner, actual so far. "))
    }

    func test_constructedDuring_aFinalCarriedEarlyIsNotRelabelledSoFar() {
        let readout = Leaf.readout(input("Constructed Runner", phase: .during, actual: .final(swiftFinal)))
        XCTAssertEqual(readout.status, .words("Actual so far unavailable"))
        XCTAssertTrue(readout.lanes.isEmpty)
        XCTAssertFalse(readout.spoken.contains("88"))
    }

    func test_constructedFinal_anActualSoFarIsNotAFinal() {
        let readout = Leaf.readout(input("Constructed Runner", phase: .final, actual: .soFar(swiftFinal)))
        XCTAssertEqual(readout.status, .words("Final actual unavailable"))
        XCTAssertNil(readout.total)
    }

    func test_constructedBefore_absentAndSoFarAreHiddenToo() {
        XCTAssertEqual(Leaf.readout(input("Constructed Runner", phase: .before, actual: .absent("No actual"))).status, .hidden)
        XCTAssertEqual(Leaf.readout(input("Constructed Runner", phase: .before, actual: .soFar(swiftFinal))).status, .hidden)
    }

    // MARK: Signed, zero and missing (CONSTRUCTED)

    func test_constructedZero_drawsAZeroMark_whileMissingDrawsNothing() {
        let reading = AdditiveStatSplitReading10868(
            total: .value(figure("40")),
            split: .qualified([component("rushing", "Ground", "40", from: 0, to: 40),
                               component("receiving", "Air", "0", from: 40, to: 40),
                               AdditiveStatSplitComponent10868(id: "returns", name: "Returns", emphasis: .secondary,
                                                               reading: .unavailable("Return yards unavailable"))]))
        let lanes = Leaf.readout(input("Constructed Runner", phase: .final, actual: .final(reading))).lanes
        XCTAssertEqual(lanes[1].mark, .zero(at: 0.4))
        XCTAssertEqual(lanes[1].text, "0 yards")
        XCTAssertTrue(lanes[1].isFigure)
        XCTAssertEqual(lanes[2].mark, .none)
        XCTAssertEqual(lanes[2].text, "Return yards unavailable")
        XCTAssertFalse(lanes[2].isFigure)
        XCTAssertEqual(lanes[2].spoken, "Returns, Return yards unavailable")
    }

    func test_constructedSigns_areShownExactlyAsTheOwnerWroteThem() {
        let reading = AdditiveStatSplitReading10868(
            total: .value(figure("88")),
            split: .qualified([component("rushing", "Ground", "84", from: 0, to: 84),
                               component("receiving", "Air", "+4", from: 84, to: 88)]))
        let lanes = Leaf.readout(input("Constructed Runner", phase: .final, actual: .final(reading))).lanes
        XCTAssertEqual(lanes.map(\.text), ["84 yards", "+4 yards"])
    }

    func test_constructedProvenanceAndUnits_stayWithTheirOwnFigure() {
        let reading = AdditiveStatSplitReading10868(
            total: .value(figure("88", unit: "yds", provenance: "Constructed combined source")),
            split: .qualified([
                AdditiveStatSplitComponent10868(id: "rushing", name: "Ground", emphasis: .primary,
                                                reading: .value(figure("84", unit: "rush yds", provenance: "Constructed rushing source"),
                                                                span: .init(start: 0, end: 84))),
                AdditiveStatSplitComponent10868(id: "receiving", name: "Air", emphasis: .secondary,
                                                reading: .value(figure("4", unit: "rec yds", provenance: nil),
                                                                span: .init(start: 84, end: 88)))]))
        let readout = Leaf.readout(input("Constructed Runner", phase: .final, actual: .final(reading)))
        XCTAssertEqual(readout.total?.text, "88 yds")
        XCTAssertEqual(readout.total?.provenance, "Constructed combined source")
        XCTAssertEqual(readout.lanes.map(\.text), ["84 rush yds", "4 rec yds"])
        XCTAssertEqual(readout.lanes.map(\.provenance), ["Constructed rushing source", nil])
        XCTAssertEqual(readout.lanes[0].spoken, "Ground, 84 rush yds, Constructed rushing source")
        XCTAssertEqual(readout.lanes[1].spoken, "Air, 4 rec yds")
        XCTAssertEqual(readout.axisWords, "Lengths show yards, not chances", "the axis keeps its own unit")
    }

    // MARK: Geometry (CONSTRUCTED)

    func test_invalidEndpoints_keepTheFigureAndDrawNoBar() {
        let spans: [AdditiveStatSplitSpan10868?] = [
            nil, .init(start: .nan, end: 4), .init(start: 0, end: .infinity),
            .init(start: -5, end: 4), .init(start: 90, end: 101)]
        for span in spans {
            XCTAssertEqual(Geometry.mark(span, on: yards), .none, "\(String(describing: span))")
            let reading = AdditiveStatSplitReading10868(
                total: .value(figure("4")),
                split: .qualified([AdditiveStatSplitComponent10868(id: "receiving", name: "Air", emphasis: .secondary,
                                                                   reading: .value(figure("4"), span: span))]))
            let readout = Leaf.readout(input("Constructed Runner", phase: .final, actual: .final(reading)))
            XCTAssertEqual(readout.lanes.first?.text, "4 yards")
            XCTAssertNil(readout.axis, "nothing placeable, so no axis")
            XCTAssertNil(readout.axisWords)
        }
    }

    func test_invalidDomain_drawsNoMarksButKeepsStaticNumbersAndSummary() {
        for (lower, upper) in [(0.0, 0.0), (100.0, 0.0), (Double.nan, 100.0), (0.0, Double.infinity)] {
            let axis = AdditiveStatSplitAxis10868(lower: lower, upper: upper, ticks: yards.ticks, unit: "yards")
            XCTAssertFalse(Geometry.isValid(axis))
            XCTAssertTrue(Geometry.ticks(axis).isEmpty)
            let readout = Leaf.readout(input("Saquon Barkley", phase: .final, actual: .final(barkleyFinal), axis: axis))
            XCTAssertEqual(readout.lanes.map(\.mark), [.none, .none])
            XCTAssertEqual(readout.lanes.map(\.text), ["82 yards", "\u{2212}2 yards"])
            XCTAssertNil(readout.axis)
            XCTAssertEqual(readout.spoken, "Saquon Barkley, final actual. Combined, 80 yards. Ground, 82 yards. Air, \u{2212}2 yards")
        }
    }

    func test_finiteBoundsWithInfiniteExtent_drawNoMarkAndNoSyntheticZero() {
        // CONSTRUCTED: both bounds are finite but upper − lower overflows to infinity,
        // which put 0 and 1 both at fraction 0 and drew a zero mark for a 1-yard span.
        let huge = AdditiveStatSplitAxis10868(lower: -1e308, upper: 1e308, ticks: yards.ticks, unit: "yards")
        XCTAssertFalse((huge.upper - huge.lower).isFinite)
        XCTAssertFalse(Geometry.isValid(huge))
        XCTAssertNil(Geometry.fraction(0, on: huge))
        XCTAssertNil(Geometry.fraction(1, on: huge))
        XCTAssertEqual(Geometry.mark(.init(start: 0, end: 1), on: huge), .none)
        XCTAssertTrue(Geometry.ticks(huge).isEmpty)
        let reading = AdditiveStatSplitReading10868(
            total: .value(figure("1", provenance: "Constructed combined source")),
            split: .qualified([component("receiving", "Air", "1", from: 0, to: 1)]))
        let readout = Leaf.readout(input("Constructed Runner", phase: .final, actual: .final(reading), axis: huge))
        XCTAssertEqual(readout.lanes.map(\.mark), [.none])
        XCTAssertEqual(readout.lanes.map(\.text), ["1 yards"], "the owner's figure stays")
        XCTAssertEqual(readout.total?.provenance, "Constructed combined source")
        XCTAssertNil(readout.axis)
        XCTAssertNil(readout.axisWords)
        // CONSTRUCTED: a finite extent so wide that 0 and 1 land on the same fraction is a
        // span the arithmetic cannot draw — no mark — while equal endpoints still mark zero.
        let wide = AdditiveStatSplitAxis10868(lower: -1e20, upper: 1e20, ticks: [], unit: "yards")
        XCTAssertTrue(Geometry.isValid(wide))
        XCTAssertEqual(Geometry.mark(.init(start: 0, end: 1), on: wide), .none)
        XCTAssertEqual(Geometry.mark(.init(start: 0, end: 0), on: wide), .zero(at: 0.5))
    }

    func test_negativeDomain_placesASignedEndpointWithoutClamping() {
        let axis = AdditiveStatSplitAxis10868(lower: -10, upper: 90, ticks: [], unit: "yards")
        XCTAssertEqual(Geometry.mark(.init(start: 0, end: -2), on: axis), .bar(from: 0.1, to: 0.08))
        XCTAssertEqual(Geometry.fraction(-10, on: axis), 0)
        XCTAssertNil(Geometry.fraction(-10.5, on: axis))
    }

    func test_emptyComponents_readSplitUnavailable() {
        let reading = AdditiveStatSplitReading10868(total: .value(figure("88")), split: .qualified([]))
        let readout = Leaf.readout(input("Constructed Runner", phase: .final, actual: .final(reading)))
        XCTAssertEqual(readout.splitWords, "Split unavailable")
        XCTAssertTrue(readout.lanes.isEmpty)
        XCTAssertNil(readout.axis)
    }

    func test_ownerOrder_isNeverResorted() {
        let reading = AdditiveStatSplitReading10868(
            total: .value(figure("88")),
            split: .qualified([component("receiving", "Air", "4", from: 84, to: 88),
                               component("rushing", "Ground", "84", from: 0, to: 84)]))
        let readout = Leaf.readout(input("Constructed Runner", phase: .final, actual: .final(reading)))
        XCTAssertEqual(readout.lanes.map(\.id), ["receiving", "rushing"])
    }

    func test_ticks_keepOnlyPlaceableOnesInOwnerOrder() {
        let axis = AdditiveStatSplitAxis10868(
            lower: 0, upper: 100,
            ticks: [.init(value: 100, text: "100"), .init(value: .nan, text: "x"), .init(value: 0, text: "0"),
                    .init(value: 120, text: "120")],
            unit: "yards")
        XCTAssertEqual(Geometry.ticks(axis), [.init(fraction: 1, text: "100"), .init(fraction: 0, text: "0")])
    }

    func test_x_staysInsideTheInsetsAndRefusesBadInput() {
        XCTAssertEqual(Geometry.x(0, width: 112), Geometry.inset)
        XCTAssertEqual(Geometry.x(1, width: 112), 112 - Geometry.inset)
        XCTAssertEqual(Geometry.x(0.5, width: 112), 56)
        XCTAssertNil(Geometry.x(0.5, width: 2 * Geometry.inset))
        XCTAssertNil(Geometry.x(1.01, width: 112))
        XCTAssertNil(Geometry.x(.nan, width: 112))
    }

    func test_axisLabelRows_moveACollidingLabelToTheNextRowWithoutShrinking() {
        // Two labels 20pt wide centred 10pt apart collide; the third is clear.
        XCTAssertEqual(Geometry.labelRows(centers: [20, 30, 90], widths: [20, 20, 20], extent: 120), [0, 1, 0])
        // A label wider than the axis starts at 0 and takes its own row.
        XCTAssertEqual(Geometry.labelStart(center: 50, width: 200, extent: 100), 0)
        XCTAssertEqual(Geometry.labelRows(centers: [50, 50], widths: [200, 10], extent: 100), [0, 1])
        // Labels at the edges stay inside the axis.
        XCTAssertEqual(Geometry.labelStart(center: 2, width: 20, extent: 100), 0)
        XCTAssertEqual(Geometry.labelStart(center: 99, width: 20, extent: 100), 80)
        XCTAssertEqual(Geometry.labelRows(centers: [1], widths: [1, 2], extent: 100), [])
    }

    // MARK: Details, layout and spoken words

    func test_details_passesTheOwnersExactIDAndIsAbsentWithoutBoth() {
        var opened: [String] = []
        let action = Leaf.detailsAction(id: barkleyOriginal) { opened.append($0) }
        action?()
        XCTAssertEqual(opened, [barkleyOriginal])
        XCTAssertNil(Leaf.detailsAction(id: nil) { opened.append($0) }, "never synthesizes an id")
        XCTAssertNil(Leaf.detailsAction(id: swiftOriginal, onDetails: nil), "static leaf asks for no tap")
        XCTAssertNil(Leaf.detailsAction(id: "") { opened.append($0) }, "an empty id names no original: absent, exactly as nil")
        XCTAssertEqual(opened, [barkleyOriginal])
        // CONSTRUCTED opaque token: a nonempty id is handed back byte for byte, never trimmed or reinterpreted.
        let opaque = " player_props:161 "
        let opaqueAction = Leaf.detailsAction(id: opaque) { opened.append($0) }
        opaqueAction?()
        XCTAssertEqual(opened, [barkleyOriginal, opaque])
        XCTAssertEqual(Leaf.readout(input("Saquon Barkley", phase: .final, actual: .final(barkleyFinal))).detailsSpoken,
                       "Details, Saquon Barkley")
    }

    /// Replaces test_layout_stacksOnlyAtAccessibilitySizes, whose ordinary-size
    /// assertion (always aligned) is no longer true: stacking is width-driven at
    /// every size, and accessibility sizes still always stack.
    func test_layout_stacksWheneverTheAlignedRowDoesNotFit_andAlwaysAtAccessibilitySizes() {
        XCTAssertEqual(Leaf.layoutCandidates(isAccessibilitySize: false), [.aligned, .stacked],
                       "aligned only while it fits the width; stacked otherwise, at any ordinary size")
        XCTAssertEqual(Leaf.layoutCandidates(isAccessibilitySize: true), [.stacked])
        XCTAssertFalse(DynamicTypeSize.xxxLarge.isAccessibilitySize)
        XCTAssertTrue(DynamicTypeSize.accessibility1.isAccessibilitySize)
        // The width the fit counts for an aligned track leaves real room between the insets.
        let minimum = Geometry.minimumTrackWidth
        XCTAssertGreaterThan(Geometry.minimumUsableTrackWidth, 0)
        XCTAssertEqual(minimum, Geometry.minimumUsableTrackWidth + 2 * Geometry.inset)
        XCTAssertEqual(Geometry.x(0, width: minimum), Geometry.inset)
        XCTAssertEqual(Geometry.x(1, width: minimum), minimum - Geometry.inset)
        XCTAssertNil(Geometry.x(1, width: 0), "a collapsed track places nothing")
    }

    func test_axisLabels_widerThanThePlotWrapInsideItAndStayUnderTheirTick() {
        // Labels are measured at the axis width, so none is wider than the plot.
        XCTAssertEqual(Geometry.labelWrapWidth(extent: 80), 80)
        XCTAssertNil(Geometry.labelWrapWidth(extent: 0))
        XCTAssertNil(Geometry.labelWrapWidth(extent: -4))
        XCTAssertNil(Geometry.labelWrapWidth(extent: .nan))
        XCTAssertNil(Geometry.labelWrapWidth(extent: .infinity))
        // CONSTRUCTED: a label wrapped to the full 80pt plot fills it from 0 to 80; a
        // narrower one at the end tick ends at the edge, never past it.
        let end = Geometry.x(1, width: 80) ?? -1
        XCTAssertEqual(Geometry.labelStart(center: end, width: 80, extent: 80), 0)
        XCTAssertEqual(Geometry.labelStart(center: end, width: 30, extent: 80), 50)
    }

    func test_spokenSummary_realBarkley_wordsNotColour() {
        let readout = Leaf.readout(input("Saquon Barkley", phase: .final, actual: .final(barkleyFinal)))
        XCTAssertEqual(readout.spoken,
                       "Saquon Barkley, final actual. Combined, 80 yards. Ground, 82 yards. Air, \u{2212}2 yards. Lengths show yards, not chances")
        XCTAssertFalse(readout.spoken.contains("%"), "no chance is spoken")
    }

    func test_spokenSummary_realMonangai_namesBothAbsences() {
        let readout = Leaf.readout(input("Kyle Monangai", phase: .final, actual: .final(monangaiFinal)))
        XCTAssertEqual(readout.spoken,
                       "Kyle Monangai, final actual. Combined, Unavailable. Final yard split unavailable")
    }
}
