import XCTest
@testable import Bain_Luck

@MainActor
final class DiscoverGroupsSelectedA9642Tests: XCTestCase {
    private func decoder() -> JSONDecoder {
        let decoder = JSONDecoder()
        decoder.keyDecodingStrategy = .convertFromSnakeCase
        return decoder
    }

    private func point(_ label: String, value: Double, probability: Double?, source: String = "outcome") -> [String: Any] {
        var result: [String: Any] = ["label": label, "value": value, "source": source]
        result["probability"] = probability.map { $0 as Any } ?? NSNull()
        return result
    }

    private func market(
        points: [[String: Any]],
        outcomes: [[String: Any]] = [],
        format: String = "threshold_heatmap",
        distribution: [[String: Any]] = []
    ) throws -> FeedFuturesData {
        let payload: [String: Any] = [
            "id": 30635376, "name": "Anthropic IPO?", "top_outcomes": outcomes,
            "discover_card": ["suggested_format": format, "threshold_points": points, "distribution_outcomes": distribution]
        ]
        return try decoder().decode(FeedFuturesData.self, from: JSONSerialization.data(withJSONObject: payload))
    }

    func testOldCachedBundleCanOmitTheSharedQuestion() throws {
        let old = Data(#"{"id":"ai","title":"AI","items":[],"kind":"theme"}"#.utf8)
        let bundle = try decoder().decode(FeedBundle.self, from: old)
        XCTAssertNil(bundle.sharedQuestion)
        XCTAssertEqual(bundle.title, "AI")
        XCTAssertEqual(bundle.id, "ai")
    }

    func testSuppliedQuestionSurvivesLifecycleFilteringWithoutInventedCopy() throws {
        let payload = Data(#"{"id":"ai","title":"AI","shared_question":"What happens next in AI?","items":[],"kind":"theme"}"#.utf8)
        let bundle = try decoder().decode(FeedBundle.self, from: payload)
        XCTAssertEqual(bundle.sharedQuestion, "What happens next in AI?")
        XCTAssertEqual(bundle.withItems([]).sharedQuestion, bundle.sharedQuestion)
        XCTAssertEqual(bundle.withItems([]).title, "AI")
        XCTAssertEqual(bundle.withItems([]).kind, "theme")
    }

    func testDateRowUsesTheCardsEarliestOverEvenRungNotMaximumPrice() throws {
        let data = try market(points: [
            point("December 31", value: 20261231, probability: 0.83, source: "date_bucket"),
            point("October 31", value: 20261031, probability: 0.08, source: "date_bucket"),
            point("November 30", value: 20261130, probability: 0.60, source: "date_bucket")
        ], outcomes: [["id": 1, "name": "December 31", "probability": 0.83, "movement": 0.12]])
        let summary = DiscoverGroupRows.compactSummary(for: data)
        XCTAssertEqual(summary.label, "November 30")
        XCTAssertEqual(summary.probability, 0.60)
        XCTAssertNil(summary.movement, "The December movement must not label a November probability.")
        XCTAssertEqual(summary.label, DiscoverGroupRows.markedRung(in: data.discoverCard?.thresholdPoints ?? [])?.label)
    }

    func testThresholdRowUsesTheMostSpecificOverEvenRungAndItsOwnMovement() throws {
        let data = try market(points: [
            point("40%+", value: 40, probability: 0.95),
            point("50%+", value: 50, probability: 0.65),
            point("60%+", value: 60, probability: 0.20)
        ], outcomes: [
            ["id": 1, "name": "40%+", "probability": 0.95, "movement": 0.20],
            ["id": 2, "name": "50%+", "probability": 0.65, "movement": 0.07]
        ])
        let summary = DiscoverGroupRows.compactSummary(for: data)
        XCTAssertEqual(summary.label, "50%+")
        XCTAssertEqual(summary.probability, 0.65)
        XCTAssertEqual(summary.movement, 0.07)
    }

    func testExactlyEvenIsAQualifiedRungAndUnpricedRowsCannotBecomeTheAnswer() throws {
        let data = try market(points: [
            point("Above 40", value: 40, probability: 0.90),
            point("Above 50", value: 50, probability: 0.50),
            point("Above 60", value: 60, probability: nil)
        ])
        XCTAssertEqual(DiscoverGroupRows.compactSummary(for: data).label, "Above 50")
        XCTAssertEqual(DiscoverGroupRows.compactSummary(for: data).probability, 0.50)
    }

    func testNoMarkedRungOrOrdinaryCardRetainsTheServedOutcome() throws {
        let points = [point("Low", value: 1, probability: 0.30), point("High", value: 2, probability: 0.40)]
        let outcomes: [[String: Any]] = [["id": 1, "name": "High", "probability": 0.40, "movement": -0.02]]
        for format in ["threshold_heatmap", "binary"] {
            let summary = DiscoverGroupRows.compactSummary(for: try market(points: points, outcomes: outcomes, format: format))
            XCTAssertEqual(summary.label, "High")
            XCTAssertEqual(summary.probability, 0.40)
            XCTAssertEqual(summary.movement, -0.02)
        }
        let unpriced = try market(points: [], outcomes: [["id": 1, "name": "Yes", "probability": NSNull()]], format: "binary")
        XCTAssertNil(DiscoverGroupRows.compactSummary(for: unpriced).probability, "Missing price must not become 0%.")
    }

    func testExpandedMembersSelectTheirExistingFullCardArchetypes() throws {
        let ladder = try market(points: [point("One", value: 1, probability: 0.7), point("Two", value: 2, probability: 0.4)])
        XCTAssertEqual(DiscoverGroupRows.fullCardStyle(for: ladder), .heatmap)
        let distribution = try market(points: [], format: "outcome_distribution", distribution: (1...4).map { ["label": "Option \($0)", "probability": 0.2] })
        XCTAssertEqual(DiscoverGroupRows.fullCardStyle(for: distribution), .distribution)
        XCTAssertEqual(DiscoverGroupRows.fullCardStyle(for: try market(points: [], format: "cross_source_comparison")), .comparison)
        XCTAssertEqual(DiscoverGroupRows.fullCardStyle(for: try market(points: [point("Only", value: 1, probability: 0.7)])), .futures)
    }
}
