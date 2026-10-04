import XCTest
@testable import Bain_Luck

/// #10374 — Alex, rage shake 170: the `Next Claude Haiku (4.6+) released on...?`
/// card read October 27 · October 12 · October 28 · October 13. The server now
/// names a date board (`distribution_order`) and each row's day (`date`); the card
/// draws the SAME four rows, listed earliest-first, leader styled by probability.
final class ADateBoardListsItsDrawnRowsByDate10374Tests: XCTestCase {
    private func card(_ json: String) throws -> FeedDiscoverCard {
        let decoder = JSONDecoder()
        decoder.keyDecodingStrategy = .convertFromSnakeCase
        return try decoder.decode(FeedDiscoverCard.self, from: Data(json.utf8))
    }

    /// The specimen as served 19:50Z (producer PR #10377's own example), in the
    /// served probability order, with its residual row.
    private let haikuBoard = """
    {
      "suggested_format": "outcome_distribution",
      "distribution_order": "chronological",
      "distribution_outcomes": [
        {"label": "October 27", "probability": 0.14, "movement": null, "date": "2026-10-27"},
        {"label": "October 12", "probability": 0.14, "movement": null, "date": "2026-10-12"},
        {"label": "October 14", "probability": 0.13, "movement": null, "date": "2026-10-14"},
        {"label": "October 28", "probability": 0.13, "movement": null, "date": "2026-10-28"},
        {"label": "October 13", "probability": 0.12, "movement": null, "date": "2026-10-13"},
        {"label": "No release by October 31", "probability": 0.05, "movement": null, "date": null}
      ],
      "remaining_outcome_count": 26
    }
    """

    func testTheSpecimenListsItsFourDrawnRowsEarliestFirst() throws {
        let c = try card(haikuBoard)
        let rows = DistributionBoardOrder.listedRows(c.distributionOutcomes ?? [], order: c.distributionOrder)
        XCTAssertEqual(rows.map(\.outcome.label), ["October 12", "October 14", "October 27", "October 28"])
        // Same percentages as served: only the order moved.
        XCTAssertEqual(rows.map(\.outcome.probability), [0.14, 0.13, 0.14, 0.13])
    }

    func testTheLeaderIsTheServedLeaderNotRowZero() throws {
        let c = try card(haikuBoard)
        let rows = DistributionBoardOrder.listedRows(c.distributionOutcomes ?? [], order: c.distributionOrder)
        // Oct 27 and Oct 12 tie at 14%; the served leader (Oct 27) keeps the bar,
        // and it is now the THIRD row drawn.
        XCTAssertEqual(rows.filter(\.isLeader).map(\.outcome.label), ["October 27"])
        XCTAssertFalse(rows[0].isLeader)
    }

    func testTheLeaderFollowsProbabilityWhenItIsNotServedFirst() {
        let rows = DistributionBoardOrder.listedRows([
            FeedDiscoverDistributionOutcome(label: "October 5", probability: 0.10, movement: nil, date: "2026-10-05"),
            FeedDiscoverDistributionOutcome(label: "October 9", probability: 0.30, movement: nil, date: "2026-10-09"),
            FeedDiscoverDistributionOutcome(label: "October 1", probability: 0.20, movement: nil, date: "2026-10-01"),
        ], order: "chronological")
        XCTAssertEqual(rows.map(\.outcome.label), ["October 1", "October 5", "October 9"])
        XCTAssertEqual(rows.filter(\.isLeader).map(\.outcome.label), ["October 9"])
    }

    func testTheResidualRowIsListedLastWhenItIsDrawn() {
        let rows = DistributionBoardOrder.listedRows([
            FeedDiscoverDistributionOutcome(label: "No release by October 31", probability: 0.40, movement: nil, date: nil),
            FeedDiscoverDistributionOutcome(label: "October 27", probability: 0.30, movement: nil, date: "2026-10-27"),
            FeedDiscoverDistributionOutcome(label: "October 12", probability: 0.20, movement: nil, date: "2026-10-12"),
        ], order: "chronological")
        XCTAssertEqual(rows.map(\.outcome.label), ["October 12", "October 27", "No release by October 31"])
        XCTAssertEqual(rows.filter(\.isLeader).map(\.outcome.label), ["No release by October 31"])
    }

    func testAYearBoundaryIsTheServersYearNotTheMonthName() {
        // A board resolving in January: the server placed December in the prior
        // year, so December lists first even though "January" < "December" never
        // enters into it — the client sorts the served day, not the label.
        let rows = DistributionBoardOrder.listedRows([
            FeedDiscoverDistributionOutcome(label: "January 5", probability: 0.30, movement: nil, date: "2027-01-05"),
            FeedDiscoverDistributionOutcome(label: "December 28", probability: 0.20, movement: nil, date: "2026-12-28"),
        ], order: "chronological")
        XCTAssertEqual(rows.map(\.outcome.label), ["December 28", "January 5"])
    }

    func testAProbabilityBoardIsDrawnExactlyAsServed() throws {
        let c = try card("""
        {
          "distribution_order": "probability",
          "distribution_outcomes": [
            {"label": "Google", "probability": 0.65, "movement": null},
            {"label": "Anthropic", "probability": 0.36, "movement": null},
            {"label": "OpenAI", "probability": 0.01, "movement": null},
            {"label": "SpaceXAI", "probability": 0.0, "movement": null}
          ]
        }
        """)
        let rows = DistributionBoardOrder.listedRows(c.distributionOutcomes ?? [], order: c.distributionOrder)
        XCTAssertEqual(rows.map(\.outcome.label), ["Google", "Anthropic", "OpenAI", "SpaceXAI"])
        XCTAssertEqual(rows.map(\.isLeader), [true, false, false, false])
        XCTAssertFalse(DistributionBoardOrder.isChronological(c.distributionOrder))
    }

    func testABodyThatPredatesTheFieldDecodesAsTodaysBoard() throws {
        // A cached feed body from before #10377: no `distribution_order`, no `date`.
        let c = try card("""
        {
          "distribution_outcomes": [
            {"label": "October 27", "probability": 0.14, "movement": null},
            {"label": "October 12", "probability": 0.14, "movement": null}
          ]
        }
        """)
        XCTAssertNil(c.distributionOrder)
        XCTAssertNil(c.distributionOutcomes?.first?.date)
        let rows = DistributionBoardOrder.listedRows(c.distributionOutcomes ?? [], order: c.distributionOrder)
        XCTAssertEqual(rows.map(\.outcome.label), ["October 27", "October 12"])
        XCTAssertEqual(rows.map(\.isLeader), [true, false])
    }

    func testOnlyTheServedFourAreDrawnSoTheLeaderCannotFallOff() throws {
        // October 13 is earlier than two drawn dates but is the fifth served row:
        // a chronological board lists the four it draws; it does not re-pick them.
        let c = try card(haikuBoard)
        let rows = DistributionBoardOrder.listedRows(c.distributionOutcomes ?? [], order: c.distributionOrder)
        XCTAssertEqual(rows.count, DistributionBoardOrder.drawnRowLimit)
        XCTAssertFalse(rows.map(\.outcome.label).contains("October 13"))
        XCTAssertTrue(rows.map(\.outcome.label).contains("October 27"))
    }

    /// The card reads the helper, not a private copy of the rule: a correct helper
    /// the card does not call is invisible from the outside.
    func testTheCardIsWiredToTheHelperAndDropsRanksOnADateBoard() throws {
        let path = URL(fileURLWithPath: #filePath)
            .deletingLastPathComponent().deletingLastPathComponent()
            .appendingPathComponent("Bain Luck/Components/DistributionCardView.swift")
        let source = try String(contentsOf: path, encoding: .utf8)
        XCTAssertTrue(source.contains("DistributionBoardOrder.listedRows(outcomes, order: data.discoverCard?.distributionOrder)"))
        XCTAssertTrue(source.contains("isLeader: row.isLeader"))
        XCTAssertFalse(source.contains("isLeader: index == 0"))
        XCTAssertTrue(source.contains("if showsRanks {"))
        XCTAssertTrue(source.contains("!DistributionBoardOrder.isChronological(data.discoverCard?.distributionOrder)"))
    }
}
