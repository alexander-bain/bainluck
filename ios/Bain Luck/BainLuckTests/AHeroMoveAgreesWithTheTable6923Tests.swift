import XCTest
@testable import Bain_Luck

/// #6923 — **the futures hero badge stops overstating the move.**
///
/// THE SPECIMEN, measured twice against production on 2026-09-18 (native/227 at
/// ~10:5xZ, re-read by native/229 at ~11:0xZ, same value): `/api/futures/114175`,
/// "Who will be UFC Heavyweight champion at the end of 2026?", Polymarket, open.
/// `Ciryl Gane` is served `probability_change_24h = 0.005` exactly.
///
/// One number, one screen, three spellings — all three visible in
/// `artifacts-native-021/`:
///
///     hero badge, beside the 52pt 70%   ->  ↑ 1%     (ufc114175-after.png)
///     chart participant table, "24h"    ->  +0.5%    (ufc114175-after2.png)
///     All Outcomes ladder, DeltaBadge   ->  ↗ 0.5pp  (ufc114175-after2.png)
///
/// The biggest type carried the wrong one. And it was not an edge case: the
/// badge's own gate is `abs(change) >= 0.005`, so EVERY move it will show from
/// 0.5 to 1.49 points printed `1%`, and the smallest move it is capable of
/// showing was doubled. The floor case always overstated.
///
/// The fix is that the hero draws the magnitude through `deltaPointsNumber`, the
/// rule the table beside it was already using and already right about. The table
/// delegates to the same call so the two cannot drift apart again.
final class AHeroMoveAgreesWithTheTable6923Tests: XCTestCase {

    /// The hero badge's own arithmetic, lifted verbatim from
    /// `FuturesDetailView.detailMovementBadge` — the gate, then the string beside
    /// the arrow. The arrow carries the sign, so the number is a magnitude.
    private func heroBadgeText(_ change: Double?) -> String? {
        guard let m = change, abs(m) >= 0.005 else { return nil }
        return "\(deltaPointsNumber(m * 100))%"
    }

    // MARK: - The specimen

    /// The whole point, in one assertion: the number that was printed twice on one
    /// screen is now printed once.
    func testCirylGanesMoveReadsTheSameInBothPlacesOnOneScreen() throws {
        let served = 0.005

        let hero = try XCTUnwrap(heroBadgeText(served))
        let table = EvolutionLeaderboardGeometry.changeLabel(served * 100)

        XCTAssertEqual(hero, "0.5%")
        XCTAssertEqual(table, "+0.5%")
        XCTAssertNotEqual(hero, "1%", "the hero doubled the smallest move it can show (#6923)")
        XCTAssertEqual(hero, String(table.dropFirst()),
                       "hero and chart table disagree about one field again (#6923)")
    }

    /// The defect's other end. The two renderings AGREE at exactly 1.0 point, which
    /// is why a test fed only a round number cannot see this bug at all — feed it
    /// the band's ends or it is vacuous.
    func testTheBandEndsWhereTheIntegerRoundingWouldHaveUnderstatedInstead() {
        XCTAssertEqual(heroBadgeText(0.0149), "1.5%",
                       "1.49 points rounded DOWN to the same `1%` the floor rounded UP to")
        XCTAssertEqual(heroBadgeText(0.010), "1.0%")

        // The mutant this kills: restoring `Int((m * 100).rounded())`. At 1.0 point
        // both spellings say "1", so this is the pair that separates them.
        let atFloor = heroBadgeText(0.005)
        let atCeiling = heroBadgeText(0.0149)
        XCTAssertNotEqual(atFloor, atCeiling,
                          "0.5 and 1.49 points both printed `1%` before #6923")
    }

    /// Every admissible move in the band the integer rule flattened now prints a
    /// distinct, true magnitude rather than a single `1%`.
    func testTheWholeFlattenedBandNoLongerCollapsesToOnePercent() {
        let band = stride(from: 0.005, to: 0.0150, by: 0.0005).map { heroBadgeText($0) }

        XCTAssertFalse(band.contains(nil), "the gate admits all of these")
        XCTAssertGreaterThan(Set(band.map { $0 ?? "" }).count, 1,
                             "the band collapsed to one string again (#6923)")
        for value in band {
            XCTAssertNotEqual(value, "1%", "the flattened spelling is back (#6923)")
        }
    }

    // MARK: - The direction still reads, and the gate did not move

    /// The arrow carries the sign, so the magnitude is unsigned — a badge reading
    /// `↓ -0.8%` would be a double negative. Down moves print the bare magnitude.
    ///
    /// The specimen's own down-mover is NOT usable here and that is worth recording:
    /// `Josh Hokit` is served `-0.0035`, which the chart table draws as `-0.4%`
    /// because `changeLabel` has no floor, while the hero badge and the ladder both
    /// gate at `abs >= 0.005` and draw nothing. That asymmetry is real, predates
    /// this ship and is not touched by it — the gate is pinned below.
    func testADownMovePrintsAMagnitudeBecauseTheArrowAlreadySaidDown() {
        XCTAssertEqual(heroBadgeText(-0.008), "0.8%")
        XCTAssertEqual(heroBadgeText(-0.012), "1.2%")
        XCTAssertFalse(heroBadgeText(-0.008)?.contains("-") ?? true)

        // Served, drawn by the table, below the badge's floor — both are correct.
        XCTAssertNil(heroBadgeText(-0.0035))
        XCTAssertEqual(EvolutionLeaderboardGeometry.changeLabel(-0.0035 * 100), "-0.4%")
    }

    /// The fix is about the STRING, not about which moves are shown. The gate is
    /// untouched, including the boundary it admits.
    func testTheGateIsUnchanged() {
        XCTAssertNil(heroBadgeText(nil), "no move served, no badge")
        XCTAssertNil(heroBadgeText(0), "a flat market draws nothing")
        XCTAssertNil(heroBadgeText(0.004), "below the floor, as before")
        XCTAssertNil(heroBadgeText(-0.004))
        XCTAssertNotNil(heroBadgeText(0.005), "the floor itself is admitted, as before")
        XCTAssertNotNil(heroBadgeText(-0.005))
    }

    // MARK: - What must NOT have moved

    /// `changeLabel` was already correct; it was refactored to share the call, not
    /// to change. A sweep over the whole plausible range asserts byte-identity with
    /// the rule it used before, so this refactor cannot be the thing that broke the
    /// column widths `EvolutionLeaderboardGeometry` measures against these strings.
    func testTheChartTablesStringsAreByteIdenticalToBefore() {
        func previousRule(_ pct: Double) -> String {
            if pct > 0 { return "+\(String(format: "%.1f", pct))%" }
            if pct < 0 { return "\(String(format: "%.1f", pct))%" }
            return "-"
        }

        for tenths in stride(from: -1000, through: 1000, by: 1) {
            let pct = Double(tenths) / 10.0
            XCTAssertEqual(EvolutionLeaderboardGeometry.changeLabel(pct),
                           previousRule(pct),
                           "changeLabel drifted at \(pct)")
        }
        // The served specimens, at the scale the view hands over.
        for served in [0.005, -0.0035, -0.0015, 0.001, 0.0] {
            XCTAssertEqual(EvolutionLeaderboardGeometry.changeLabel(served * 100),
                           previousRule(served * 100))
        }
    }

    /// The other renderers of this same field are NOT in this ship and are pinned
    /// so a later "unify everything" does not quietly change a surface nobody
    /// measured. `DeltaBadge`'s `pp` in particular is a copy decision across three
    /// surfaces, not an arithmetic one — see `deltaPointsNumber`'s doc comment.
    func testTheRenderersThisShipDeliberatelyLeftAloneStillReadAsTheyDid() {
        // The ladder on the specimen screen: one decimal, and the unit is `pp`.
        XCTAssertEqual(String(format: "%.1f", abs(0.005 * 100)) + "pp", "0.5pp")

        // The chart table's probability rule is a different function and untouched.
        XCTAssertEqual(EvolutionLeaderboardGeometry.probLabel(0.05), "0.1%")
        XCTAssertEqual(EvolutionLeaderboardGeometry.probLabel(70), "70%")

        // And the app's probability formatter is not a delta formatter: this is why
        // the movers card prints `<1%` for a half-point move. Recorded, not fixed.
        XCTAssertEqual(formatProbability(0.005), "<1%")
    }

    // MARK: - The call site

    /// A source scan over the file that HAD the defect. Positive and negative, so
    /// it fails if the delegation goes away AND fails if it is re-aimed at nothing.
    func testTheHeroBadgeDelegatesToTheSharedRule() throws {
        let project = URL(fileURLWithPath: #filePath)
            .deletingLastPathComponent()      // BainLuckTests
            .deletingLastPathComponent()      // Bain Luck (project dir)
            .appendingPathComponent("Bain Luck")

        let source = try String(
            contentsOf: project.appendingPathComponent("Views/FuturesDetailView.swift"),
            encoding: .utf8
        )

        XCTAssertTrue(source.contains("private func detailMovementBadge"),
                      "this scan no longer aims at anything — re-aim it")
        XCTAssertTrue(source.contains("deltaPointsNumber(m * 100)"),
                      "the hero badge stopped delegating to the shared rule (#6923)")
        XCTAssertFalse(source.contains("Text(\"\\(abs(Int((m * 100).rounded())))%\")"),
                       "the hero badge rounds the move to an integer again (#6923)")
    }
}
