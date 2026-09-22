import XCTest
@testable import Bain_Luck

/// #5899 — the futures page stops printing `0%` for an outcome the venue prices.
///
/// THE SPECIMEN, on production and in `artifacts-native-144/`: market 60755512,
/// "Lowest temperature in Buenos Aires on September 13?", status **open**,
/// Polymarket, five outcomes all served `0.0005` (payload read at 11:19:48Z and
/// again at 11:20:12Z, identical). The phone printed that one number three ways on
/// one page — `0%` on the 52pt hero, `0.1%` in the chart's participant table, and
/// `0%` on `#1` of All Outcomes directly above `<1%` on `#2`, `#3` and `#4`.
///
/// The rounding was never wrong. `0%` reads as "cannot happen", and the four rows
/// below it, drawn from the identical number, said "barely".
///
/// These tests pin the fix AND the two things that must NOT move with it: the
/// `>99%` end, and a stored exact zero. Both are deliberate and both are measured
/// — see `percentNumber`'s own doc comment for the 749,007-row reason.
final class FuturesZeroPercentLabel5899Tests: XCTestCase {

    // MARK: - The specimen

    func testAPricedOutcomeIsBarelyAliveNotImpossible() {
        // 0.0005 as the view holds it: percentage POINTS.
        XCTAssertEqual(percentNumber(0.05), "<1")
    }

    /// The whole All Outcomes list of the shot, as the page draws it: `#1` through
    /// `ProbabilityNumber`/`percentNumber`, every row below it through
    /// `formatProbability`. The defect was that those two disagreed about one
    /// number; the fix is that they agree.
    func testTheShotsOwnListNoLongerContradictsItself() {
        let served = [0.0005, 0.0005, 0.0005, 0.0005, 0.0005]   // 4°C 5°C 6°C 7°C 8°C

        let leader = percentNumber(served[0] * 100) + "%"
        let rest = served.dropFirst().map { formatProbability($0) }

        XCTAssertEqual(leader, "<1%")
        XCTAssertEqual(rest, ["<1%", "<1%", "<1%", "<1%"])
        XCTAssertFalse(([leader] + rest).contains("0%"),
                       "the defect was a flat 0% on a leader the venue still prices")
        XCTAssertEqual(Set([leader] + rest).count, 1,
                       "one number may not be printed two ways in one list")
    }

    /// The page's THIRD spelling of the same number is the one that was already
    /// right, and it stays. The chart's participant table drew `0.1%` for these
    /// outcomes throughout — more precise than the marker, not in conflict with it
    /// — and it arrives at that through its own rule, whose boundary happens to be
    /// the same open interval this fix adopts. Pinned so a later tidy-up does not
    /// "unify" the precise one away.
    func testTheChartTablesOwnSubPercentRuleIsUntouched() {
        XCTAssertEqual(EvolutionLeaderboardGeometry.probLabel(0.05), "0.1%")
        XCTAssertEqual(EvolutionLeaderboardGeometry.probLabel(0), "0%")
        XCTAssertEqual(EvolutionLeaderboardGeometry.probLabel(57), "57%")
    }

    /// The second surface, same cause, different payload and a different scale.
    /// `/api/entertainment` serves percentage POINTS, and `/trending[0]` —
    /// "Which movie has biggest opening weekend in 2026?" — carried
    /// `Dune: Messiah` at `0.1` while the card printed `0%`.
    func testTheEntertainmentCardsThirdRowIsSmallNotDead() {
        let topOutcomes = [55.0, 41.0, 0.1]      // Avengers, Spider-Man, Dune: Messiah
        // Called through a closure rather than passed as a bare function value:
        // #8097 gave `percentNumber` a defaulted `renderedPercent:`, which changes
        // its TYPE to `(Double, Int?) -> String` even though every existing call
        // still compiles. The assertion is unchanged.
        XCTAssertEqual(topOutcomes.map { percentNumber($0) }, ["55", "41", "<1"])
    }

    // MARK: - The half that must NOT move: the top end

    /// `formatProbability` guards the top with `>99%`. `percentNumber` deliberately
    /// does not, because on this page the leader of a resolved market is the
    /// WINNER — 749,007 outcomes of resolved futures markets sit above 0.99
    /// (db-query, 2026-09-13 11:2xZ) — and `>99%` would hedge a decided question
    /// across that whole population. Settled means settled.
    func testANearCertaintyStillPrintsItsInteger() {
        XCTAssertEqual(percentNumber(99.6), "100")
        XCTAssertEqual(percentNumber(100), "100")
        XCTAssertEqual(percentNumber(99), "99")
    }

    /// And the rule it declines to copy is still in force where it belongs, so the
    /// asymmetry is a choice about this surface and not a quiet edit of the app's
    /// marker rule.
    func testFormatProbabilityKeepsBothOfItsOwnGuards() {
        XCTAssertEqual(formatProbability(0.996), ">99%")
        XCTAssertEqual(formatProbability(0.0005), "<1%")
    }

    // MARK: - The half that must NOT move: a measured zero

    /// #5837 ruled a served `0.0` reads `<1%` because the golf feed quotes on a
    /// three-decimal grid, so its zero was a rounding floor. Here it is not:
    /// `futures_outcomes.current_probability` is `numeric` and holds `0.0005`, so a
    /// zero that arrives is a zero that was measured. Absence is a dash and is not
    /// this function's business.
    func testAMeasuredZeroIsStillZero() {
        XCTAssertEqual(percentNumber(0), "0")
        XCTAssertEqual(formatProbabilityOrDash(nil), absentProbabilityMarker)
    }

    // MARK: - The band, and where it stops

    /// The marker is a claim about the VALUE, so it covers the whole open interval
    /// and not just the part that rounds to zero. `0.7` rounds to the integer `1`
    /// and is still under one percent.
    func testTheMarkerBandIsTheWholeOpenIntervalBelowOne() {
        XCTAssertEqual(percentNumber(0.0001), "<1")
        XCTAssertEqual(percentNumber(0.7), "<1")
        XCTAssertEqual(percentNumber(0.999), "<1")
        XCTAssertEqual(percentNumber(1), "1", "exactly one percent is not below one percent")
    }

    /// Everything the marker does not touch prints exactly the integer it printed
    /// before — the fix moves one band, not the arithmetic.
    func testEveryOtherValuePrintsTheSameIntegerItAlwaysDid() {
        for points in stride(from: 1.0, through: 100.0, by: 0.5) {
            XCTAssertEqual(percentNumber(points), "\(Int(points.rounded()))",
                           "percentNumber re-rounded at \(points)")
        }
    }

    // MARK: - The two call sites that had the defect

    /// A source scan, so it is worth exactly what its population is worth: it reads
    /// the two files that HAD the defect and asserts each now delegates. Positive
    /// AND negative, because "the old string is gone" goes stale the day someone
    /// writes it a third way, and because a scan that finds nothing must fail.
    func testTheTwoCallSitesDelegateToTheSharedRule() throws {
        let project = URL(fileURLWithPath: #filePath)
            .deletingLastPathComponent()      // BainLuckTests
            .deletingLastPathComponent()      // Bain Luck (project dir)
            .appendingPathComponent("Bain Luck")

        let sites: [(file: String, anchor: String, banned: String)] = [
            ("Components/DesignSystem.swift",
             "struct ProbabilityNumber",
             "Text(\"\\(Int(value.rounded()))\")"),
            ("Views/FuturesDetailView.swift",
             "size: 52, weight: .black",
             "Text(\"\\(Int((prob * 100).rounded()))%\")"),
        ]

        for site in sites {
            let source = try String(contentsOf: project.appendingPathComponent(site.file),
                                    encoding: .utf8)
            XCTAssertTrue(source.contains(site.anchor),
                          "\(site.file) no longer holds the thing this scan aims at — re-aim it")
            XCTAssertTrue(source.contains("percentNumber("),
                          "\(site.file) stopped delegating to the shared rule (#5899)")
            XCTAssertFalse(source.contains(site.banned),
                           "\(site.file) interpolates the bare integer again (#5899)")
        }
    }
}
