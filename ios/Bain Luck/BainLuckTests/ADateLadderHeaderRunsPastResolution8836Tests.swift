import SwiftUI
import XCTest
@testable import Bain_Luck

/// #8836 — **a date ladder's header does not print one rung's close as the card's.**
///
/// THE SPECIMEN: Discover card "Will the U.S. confirm that aliens exist?"
/// (futures 109435, Kalshi KXALIENS, group kalshi:KXALIENS-27), served
/// 2026-09-26 15:1xZ (the same payload the web guard
/// `dateLadderResolvesPastHeader8836.test.tsx` pins). Header: "Resolves Jan 1,
/// 2027". Rungs:
///
///     Before October        1%
///     Before November       2%
///     Before December       3%
///     Before 2027           4%
///     Before 2028          13%
///     Before Jan 20, 2029  19%
///
/// Kalshi closes each rung on its own date (KXALIENS-27-29 closes
/// 2029-01-20T15:00Z); the served `resolution_date` is the Before-2027 rung's
/// close. The payload carries no per-rung close, so the header says nothing.
final class ADateLadderHeaderRunsPastResolution8836Tests: XCTestCase {

    private static let servedResolution = "2027-01-01T15:00:00+00:00"

    private func point(_ source: String, _ label: String, _ value: Double, _ probability: Double) -> String {
        """
        {"source": "\(source)", "label": "\(label)", "value": \(value), "unit": "date",
         "direction": "before", "probability": \(probability)}
        """
    }

    /// The served `threshold_points`, verbatim off `/api/feed`.
    private var aliensPoints: [String] {
        [
            point("date_bucket", "Before October", 20261000, 0.01),
            point("date_bucket", "Before November", 20261100, 0.015),
            point("date_bucket", "Before December", 20261200, 0.025),
            point("date_bucket", "Before 2027", 20270100, 0.044),
            point("date_bucket", "Before 2028", 20280100, 0.125),
            point("date_bucket", "Before Jan 20, 2029", 20290120, 0.185),
        ]
    }

    /// Decoded through the real feed decoder, the way the app reads the card.
    private func card(_ points: [String], resolution: String?) throws -> FeedFuturesData {
        let resolutionJSON = resolution.map { "\"\($0)\"" } ?? "null"
        let json = """
        {
          "id": 109435, "name": "Will the U.S. confirm that aliens exist?",
          "sport": null, "sport_name": null, "llm_sport_category": "tech",
          "source": "kalshi", "source_count": 1, "status": "open",
          "resolution_date": \(resolutionJSON), "confidence_tier": "low",
          "discover_card": {
            "suggested_format": "threshold_heatmap",
            "threshold_points": [\(points.joined(separator: ","))]
          }
        }
        """
        let dec = JSONDecoder()
        dec.keyDecodingStrategy = .convertFromSnakeCase
        return try dec.decode(FeedFuturesData.self, from: Data(json.utf8))
    }

    private func header(_ data: FeedFuturesData) -> String? {
        HeatMapCardView(data: data, navigationPath: .constant(NavigationPath())).resolvesText
    }

    // MARK: - The defect

    func testTheProductionCardPrintsNoResolvesLineOverRungsTo2029() throws {
        let data = try card(aliensPoints, resolution: Self.servedResolution)
        XCTAssertEqual(data.discoverCard?.thresholdPoints?.count, 6, "the fixture decodes whole")
        XCTAssertNil(header(data), "the header named the Before-2027 rung's close as the card's")
    }

    /// The card draws five cells; the sixth ("Before Jan 20, 2029") sits behind
    /// "+1 more". Dropping it must not bring the wrong date back — "Before 2028"
    /// alone already runs a year past the served date, and the hidden rung is
    /// still the card's.
    func testTheDrawnFiveCellsAloneAlsoRunPastTheServedDate() throws {
        let data = try card(Array(aliensPoints.prefix(5)), resolution: Self.servedResolution)
        XCTAssertNil(header(data))
    }

    // MARK: - Controls

    func testControlTheSameLadderWhoseServedDateIsItsLatestRungKeepsItsLine() throws {
        let data = try card(aliensPoints, resolution: "2029-01-20T15:00:00+00:00")
        XCTAssertEqual(header(data), "Resolves Jan 20")
    }

    /// "Before 2028" (20280100 → Jan 1, 2028) against a venue close the evening
    /// before its label's date: inside the two-day slack, the line stays.
    func testControlARungClosedTheEveningBeforeItsLabelKeepsTheLine() throws {
        let data = try card(Array(aliensPoints.prefix(5)), resolution: "2027-12-31T23:00:00Z")
        XCTAssertNotNil(header(data))
    }

    /// A bare calendar-date `resolution_date` is read as its day, not dropped.
    func testABareCalendarDateResolutionIsReadAsItsDay() throws {
        XCTAssertNil(header(try card(aliensPoints, resolution: "2027-01-01")))
        XCTAssertNotNil(header(try card(aliensPoints, resolution: "2029-01-20")))
    }

    /// A comparator ladder's `value` is a magnitude, not a date: 20290120 there
    /// is a number, and the card keeps its line whatever it is.
    func testControlAComparatorLadderIsNeverReadAsADate() throws {
        let points = [
            point("outcome", "Above 20261000", 20261000, 0.6),
            point("outcome", "Above 20290120", 20290120, 0.2),
        ]
        XCTAssertEqual(header(try card(points, resolution: Self.servedResolution)), "Resolves Jan 1")
    }

    /// A mixture is not a date ladder we recognise (web's `ladderKind`: every, not some).
    func testControlAMixedLadderKeepsItsLine() throws {
        var points = aliensPoints
        points[0] = point("outcome", "Before October", 20261000, 0.01)
        XCTAssertNotNil(header(try card(points, resolution: Self.servedResolution)))
    }

    func testControlAValueOutsideTheYYYYMMDDShapeKeepsItsLine() throws {
        let points = [
            point("date_bucket", "Before 2027", 20270100, 0.044),
            point("date_bucket", "Month 13", 20291300, 0.185),
        ]
        XCTAssertNotNil(header(try card(points, resolution: Self.servedResolution)))
    }

    func testControlNoResolutionDatePrintsNothingAsBefore() throws {
        XCTAssertNil(header(try card(aliensPoints, resolution: nil)))
    }
}
