import XCTest
@testable import Bain_Luck

/// native/092 — #4671: a map stops drawing a rail with nothing on it.
///
/// THE PHOTOGRAPH. Event 15307717 (Chiba Lotte Marines v Tohoku Rakuten Golden
/// Eagles, NPB, status `suspended`, both scores null), iPhone 17 simulator
/// against production, 2026-09-09 11:10pm PT —
/// `artifacts-native-091/after4018-master-npb-s1600.png`. A card headed
/// **"Runs map / Projected total runs"** drew a uniform pale-lavender capsule
/// over an axis reading **`0 · 10 · 21+`**, and nothing else. The four
/// `Over 5.5 / 7.5 / 9.5 / 11.5` rows below it are real quoted prices and are
/// untouched by this ship.
///
/// THE MECHANISM, in two halves.
///
/// 1. #4018 correctly stopped an abandoned game forecasting its own final, so
///    `drawsPregameMarker(canStillBeGraded: false)` withheld the `PROJECTION`
///    tile — and that marker was the ONLY thing ever drawn on this rail. The
///    tile was gated; the frame it sat in was not.
/// 2. The rail underneath was already a fiction. From the event's own
///    `/api/events/15307717/game-markets`, re-measured 2026-09-09: four totals
///    rows at thresholds `5.5 / 7.5 / 9.5 / 11.5`, **every one served at
///    `over_probability = 0.99`**. `MarketMapRail.densityFromThresholds` differences
///    adjacent pairs, so every `dp` is `0.99 - 0.99 = 0`, `rawPdf` is three
///    entries of density `0`, and the normalised return is **fourteen zeros** —
///    which `densityRail` renders at `alpha = 0.15 + 0` uniformly across its
///    whole width. Digit for digit the photographed capsule.
///
/// THE TRAP THIS ENCODES, and the reason `railDrawsNothing` reads the density
/// array rather than the card's `drawsDistribution` flag: that flag comes from
/// `totalRailHasDistribution`, which asks whether the THRESHOLDS are distinct.
/// These four are distinct, so the flag was **true** on the very card this issue
/// was filed for. A gate written against the flag would have compiled, passed,
/// merged, and changed nothing on screen.
///
/// #4692 has since put that flag on the drawn heights too, so it answers false
/// here and the trap is closed at its source rather than routed around;
/// `test_theFlagTheCardCarriesNowReadsTheDrawnHeightsToo` records both states.
/// What still keeps this rule its own function is the MARKER arm, which no
/// subtitle rule has.
final class EmptyRailWithheld4671Tests: XCTestCase {

    /// The fourteen heights the specimen's rail actually renders.
    private let npbSuspended = Array(repeating: 0.0, count: 14)

    /// A rail with a real shape on it — MLB 15298326, the two-bin card named as
    /// the admitted borderline in `marginRailHasDistribution`'s own census.
    private let varied: [Double] = [0, 0, 1.9, 96.0, 0, 0]

    // MARK: - The specimen

    func test_suspendedGameWithNoMarkerWithholdsItsRail() {
        XCTAssertTrue(
            MarketMapRail.railDrawsNothing(density: npbSuspended, markerCount: 0),
            "NPB 15307717: fourteen zero heights and no marker is a decorative capsule"
        )
    }

    /// The flag the card carries on this specimen was TRUE when #4671 shipped,
    /// and is FALSE now. Both facts are the same lesson and this case keeps
    /// recording it.
    ///
    /// #4671 could not gate on `drawsDistribution` because that flag asked the
    /// served THRESHOLDS whether they were distinct, and 5.5 / 7.5 / 9.5 / 11.5
    /// are distinct — a gate written against it would have compiled, passed,
    /// merged, and changed nothing on the card it was filed for. #4692 has since
    /// moved the flag onto the drawn heights, so it now answers false here and
    /// the two rules agree on this array.
    ///
    /// That agreement is NOT permission to derive one from the other. What keeps
    /// `railDrawsNothing` separate is its marker arm, pinned in
    /// `test_theMarkerArmIsWhatThisRuleAddsToTheSubtitles` — on this very array
    /// the two rules give opposite answers as soon as a marker is on the rail.
    func test_theFlagTheCardCarriesNowReadsTheDrawnHeightsToo() {
        XCTAssertFalse(
            MarketMapRail.totalRailHasDistribution(density: npbSuspended),
            "#4692 — the flag asks the heights now, and this rail draws fourteen zeros"
        )
        XCTAssertEqual(
            MarketMapRail.totalRailHasDistribution(density: npbSuspended),
            MarketMapRail.marginRailHasDistribution(density: npbSuspended),
            "the two cards' subtitle rules must answer the same array identically"
        )
    }

    // MARK: - What must keep its rail

    /// #2086 — declare, don't delete. A marker is content, so any marker keeps
    /// the rail even over a flat track: the FINAL tile on a settled game and the
    /// PROJECTION tile on a scheduled one both still draw.
    func test_anyMarkerKeepsTheRail() {
        XCTAssertFalse(
            MarketMapRail.railDrawsNothing(density: npbSuspended, markerCount: 1),
            "a FINAL or PROJECTION tile is the rail's content"
        )
        XCTAssertFalse(MarketMapRail.railDrawsNothing(density: npbSuspended, markerCount: 2))
    }

    func test_aRealDistributionKeepsTheRailWithNoMarkerAtAll() {
        XCTAssertFalse(
            MarketMapRail.railDrawsNothing(density: varied, markerCount: 0),
            "the shape IS the content; it does not need a marker to earn its axis"
        )
    }

    // MARK: - The class, not the specimen

    /// `MarketMapRail.densityFromThresholds` has two early exits — fewer than two lines,
    /// and no pair separated by a positive gap — and both return
    /// `Array(repeating: 8, count: 14)`. A uniform NON-zero array is the same
    /// empty chrome as a uniform zero one, and reading heights refuses both with
    /// one expression. A rule that only tested `allSatisfy { $0 == 0 }` would
    /// pass the specimen and miss every card that arrives by those exits.
    func test_theBuildersFlatExitsAreAlsoNothing() {
        XCTAssertTrue(
            MarketMapRail.railDrawsNothing(density: Array(repeating: 8.0, count: 14), markerCount: 0),
            "the flat-exit placeholder is a uniform 8, not a zero"
        )
    }

    /// A single populated bin at full height is the case #3763 was filed on: one
    /// block, no shape.
    func test_aSinglePopulatedBinIsNothing() {
        XCTAssertTrue(MarketMapRail.railDrawsNothing(density: [96], markerCount: 0))
        XCTAssertTrue(
            MarketMapRail.railDrawsNothing(density: [0, 0, 96, 0, 0], markerCount: 0)
        )
        XCTAssertTrue(
            MarketMapRail.railDrawsNothing(density: [96, 0, 96, 0, 96], markerCount: 0),
            "five bins at one height is a plateau, not a distribution"
        )
    }

    func test_anEmptyDensityIsNothing() {
        XCTAssertTrue(MarketMapRail.railDrawsNothing(density: [], markerCount: 0))
    }

    /// THE CLASS RULE. Whether a rail is worth drawing and whether its subtitle
    /// may say "distribution" are the same question about the same array, and
    /// #3554's lesson is that two copies of one rule drift apart. With no marker
    /// on it, `railDrawsNothing` must be exactly the negation of the rule the
    /// margin subtitle already uses — on every array, not on a chosen one.
    ///
    /// This is the assertion that fails a special case: a gate that hard-codes
    /// the specimen, or tests zeros only, breaks the identity here.
    func test_withNoMarkerTheRuleIsExactlyTheSubtitlesOwn() {
        let arrays: [[Double]] = [
            [],
            [96],
            [0, 0, 0],
            Array(repeating: 0.0, count: 14),
            Array(repeating: 8.0, count: 14),
            Array(repeating: 96.0, count: 5),
            [0, 96, 0],
            [96, 0, 96, 0, 96],
            [1.9, 96.0],
            [96, 0, 95.9],
            [0, 0, 1.9, 96.0, 0, 0],
        ]
        for density in arrays {
            XCTAssertEqual(
                MarketMapRail.railDrawsNothing(density: density, markerCount: 0),
                !MarketMapRail.marginRailHasDistribution(density: density),
                "the rail's existence rule disagreed with the subtitle's on \(density)"
            )
        }
    }

    /// And the marker arm is not part of that identity — it is the one thing
    /// `railDrawsNothing` adds. Pinned so a refactor cannot quietly collapse the
    /// two functions into one and drop the markers.
    func test_theMarkerArmIsWhatThisRuleAddsToTheSubtitles() {
        XCTAssertFalse(MarketMapRail.marginRailHasDistribution(density: npbSuspended))
        XCTAssertFalse(
            MarketMapRail.railDrawsNothing(density: npbSuspended, markerCount: 1),
            "identical array, opposite answer, because a marker is on it"
        )
    }

    // MARK: - The rule the view can no longer break

    /// 🔴 EVERY assertion above passes with the gate deleted from `mapCard`.
    /// They pin the rule; this pins its USE, which is the half the reader sees.
    /// A rule nobody calls is the#4018 residue all over again — a correct gate
    /// one layer away from the thing that draws.
    ///
    /// Asserted structurally, not by line number and not by a substring: the
    /// rail call and the axis block must BOTH fall inside the guard's braces.
    /// That kills the three mutants a substring check would survive — deleting
    /// the `if`, gating only the rail and leaving the axis floating, and moving
    /// either call out past the closing brace.
    func test_mapCardDrawsTheRailAndItsAxisOnlyInsideTheGuard() throws {
        let url = URL(fileURLWithPath: #filePath)
            .deletingLastPathComponent()      // BainLuckTests
            .deletingLastPathComponent()      // Bain Luck
            .appendingPathComponent("Bain Luck/Components/MarketMapView.swift")
        // Comments are stripped first — this file's own prose quotes the call it
        // guards, and a scanner that reads prose is measuring the write-up.
        // `MarketMapMidAxisLabelTests` learned that on the same file.
        let source = try String(contentsOf: url, encoding: .utf8)
            .split(separator: "\n", omittingEmptySubsequences: false)
            .filter { !$0.trimmingCharacters(in: .whitespaces).hasPrefix("//") }
            .joined(separator: "\n")

        let guardCall = "MarketMapRail.railDrawsNothing(density: density, markerCount: markers.count)"
        guard let guardStart = source.range(of: guardCall) else {
            return XCTFail("`mapCard` no longer gates its rail through `railDrawsNothing`")
        }

        // Walk from the guard's opening brace to its matching close, so the span
        // is the block itself rather than a fixed number of lines after it.
        guard let braceOpen = source.range(of: "{", range: guardStart.upperBound ..< source.endIndex) else {
            return XCTFail("no block opens after the `railDrawsNothing` guard")
        }
        var depth = 0
        var blockEnd: String.Index?
        var i = braceOpen.lowerBound
        while i < source.endIndex {
            let character = source[i]
            if character == "{" { depth += 1 }
            if character == "}" {
                depth -= 1
                if depth == 0 { blockEnd = i; break }
            }
            i = source.index(after: i)
        }
        guard let end = blockEnd else {
            return XCTFail("the `railDrawsNothing` guard's block never closes")
        }
        let guarded = source[braceOpen.upperBound ..< end]

        XCTAssertTrue(
            guarded.contains("densityRail("),
            "the rail must be drawn INSIDE the guard, or #4671's empty capsule comes back"
        )
        XCTAssertTrue(
            guarded.contains("MarketMapRail.midAxisLabel(zeroPercent: zeroPosition)"),
            "the axis must be withheld WITH the rail — `0 · 10 · 21+` under nothing is the same chrome"
        )
    }
}
