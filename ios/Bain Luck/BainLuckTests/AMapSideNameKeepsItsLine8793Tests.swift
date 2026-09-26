import XCTest
import SwiftUI
@testable import Bain_Luck

/// #8793 — a margin map for two clubs with no served abbreviation printed the
/// whole club name into the ladder's label column, and truncation took the
/// `by N+` — the only part of a row that tells one rung from the next.
///
/// THE PHOTOGRAPH: `artifacts/native-8739/after-sdwave-s650.png`, event
/// 15310972, San Diego Wave FC @ Racing Louisville FC: `San Diego Wave F…` ×3,
/// `Racing Louisville F…` ×3, and the axis running `…FC by 8.5+` into `Tie`.
final class AMapSideNameKeepsItsLine8793Tests: XCTestCase {

    private let away = "San Diego Wave FC"
    private let home = "Racing Louisville FC"

    /// 🔴 The premise. If the whole-name label fit the column, the truncation
    /// in the photograph had some other cause and this fix is aimed wrong.
    @MainActor
    func testTheWholeClubNameLabelOverflowsTheColumn() {
        let wanted = naturalWidth(of: MarketMapLadderLabel(
            text: MarketMapRail.marginThresholdLabel(teamAbbr: away, threshold: 1.5),
            color: .blue))
        XCTAssertGreaterThan(wanted, MarketMapLadderLayout.labelColumnWidth)
    }

    /// 🟢 The fix: the specimen's map calls its sides by the badges the page
    /// title already reads (`SDW vs RAC`), and every rung keeps its line —
    /// including a two-digit one, the widest a soccer margin reaches.
    @MainActor
    func testTheSpecimenMapUsesTheBadgesAndEveryRungKeepsItsLine() {
        let sides = MarketMapRail.mapSideLabels(away: away, home: home)
        XCTAssertEqual(sides.away, "SDW")
        XCTAssertEqual(sides.home, "RAC")

        for name in [sides.away, sides.home] {
            for line in [1.5, 8.5, 10.5] {
                let label = MarketMapRail.marginThresholdLabel(teamAbbr: name, threshold: line)
                XCTAssertTrue(label.hasSuffix("by \(line)+"), label)
                let wanted = naturalWidth(of: MarketMapLadderLabel(text: label, color: .blue))
                XCTAssertLessThanOrEqual(
                    wanted, MarketMapLadderLayout.labelColumnWidth,
                    "'\(label)' wants \(wanted) pt — the column would truncate its line")
            }
        }
    }

    /// One side the pair rule cannot shorten is enough: both sides move to
    /// badges together, so a map never reads `SDW` above `Thorns`.
    func testOneUnshortenedSideMovesBothSides() {
        let sides = MarketMapRail.mapSideLabels(away: "San Diego Wave FC", home: "Portland Thorns")
        XCTAssertEqual(sides.away.count, 3, sides.away)
        XCTAssertEqual(sides.home.count, 3, sides.home)
    }

    /// 🔴 THE CONTROL — every label that already shortened is exactly what the
    /// pair rule gave before: served codes, tennis surnames, nicknames. Without
    /// this, "badges everywhere" would pass every assertion above.
    func testEverythingThatAlreadyShortenedIsUnchanged() {
        let cases: [(String, String, String?, String?)] = [
            ("Los Angeles Rams", "San Francisco 49ers", "LAR", "SF"),
            ("Aryna Sabalenka", "Jessica Pegula", nil, nil),
            ("Botic van de Zandschulp", "Tomas Martin Etcheverry", nil, nil),
            ("Boston Red Sox", "New York Yankees", nil, nil),
            // Served codes win even for the specimen's own teams.
            ("San Diego Wave FC", "Racing Louisville FC", "SDW", "LOU"),
        ]
        for (a, h, aServed, hServed) in cases {
            let before = TeamShortName.shortPair(
                away: a, home: h, awayServed: aServed, homeServed: hServed)
            let after = MarketMapRail.mapSideLabels(
                away: a, home: h, awayServed: aServed, homeServed: hServed)
            XCTAssertEqual(after.away, before.away, "\(a) @ \(h)")
            XCTAssertEqual(after.home, before.home, "\(a) @ \(h)")
        }
    }

    /// The map must actually take its names from the rule above — the rule
    /// being right does nothing if `MarketMapView.sides` still calls the pair
    /// rule directly (it is private, so it is read from source).
    func testTheMapViewTakesItsSideNamesFromTheMapRule() throws {
        let url = URL(fileURLWithPath: #filePath)
            .deletingLastPathComponent()
            .deletingLastPathComponent()
            .appendingPathComponent("Bain Luck/Components/MarketMapView.swift")
        let source = try String(contentsOf: url, encoding: .utf8)
            .split(separator: "\n", omittingEmptySubsequences: false)
            .filter { !$0.trimmingCharacters(in: .whitespaces).hasPrefix("//") }
            .joined(separator: "\n")
        XCTAssertEqual(source.components(separatedBy: "MarketMapRail.mapSideLabels(").count - 1, 1)
        XCTAssertFalse(source.contains("TeamShortName.shortPair("),
                       "a second side-name path would bring the truncation back")
    }

    @MainActor
    private func naturalWidth<V: View>(of view: V) -> CGFloat {
        let host = hostForMeasurement(view)
        host.view.setNeedsLayout()
        host.view.layoutIfNeeded()
        return host.sizeThatFits(
            in: CGSize(width: CGFloat.greatestFiniteMagnitude,
                       height: CGFloat.greatestFiniteMagnitude)).width
    }
}
