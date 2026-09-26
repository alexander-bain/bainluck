import SwiftUI
import XCTest
@testable import Bain_Luck

/// #8713 — **a heat-map card's cells show the rung its caption names.**
///
/// THE SPECIMEN: Discover card "When will Anthropic officially announce an IPO?"
/// (futures 8430022, Kalshi), the same ten served rungs
/// `ADateLadderNamesTheEarliestRungOverEven8647Tests` pins. The card draws five
/// cells. It drew the first five:
///
///     Before Oct 1   1%   Oct 10  1%   Oct 17  1%   Oct 24  2%   Nov 1  6%
///
/// under the caption "More likely than not: Before Dec 1, 2026", with the 56% …
/// 90% rungs behind "+5 more" (artifacts/native-8647/after-anthropic-ipo-card.png).
final class AHeatMapCardDrawsTheRungItsCaptionNames8713Tests: XCTestCase {

    private func point(_ source: String, _ label: String, _ value: Double, _ probability: Double) -> String {
        """
        {"source": "\(source)", "label": "\(label)", "value": \(value), "unit": "date",
         "direction": "before", "probability": \(probability)}
        """
    }

    /// The served `threshold_points`, verbatim (#8647's fixture).
    private var anthropicIpo: [String] {
        [
            point("date_bucket", "Before Oct 1, 2026", 20261001, 0.01),
            point("date_bucket", "Before Oct 10, 2026", 20261010, 0.01),
            point("date_bucket", "Before Oct 17, 2026", 20261017, 0.01),
            point("date_bucket", "Before Oct 24, 2026", 20261024, 0.015),
            point("date_bucket", "Before Nov 1, 2026", 20261101, 0.055),
            point("date_bucket", "Before Dec 1, 2026", 20261201, 0.565),
            point("date_bucket", "Before Jan 1, 2027", 20270101, 0.725),
            point("date_bucket", "Before Feb 1, 2027", 20270201, 0.845),
            point("date_bucket", "Before Mar 1, 2027", 20270301, 0.88),
            point("date_bucket", "Before Apr 1, 2027", 20270401, 0.895),
        ]
    }

    /// Decoded through the real feed decoder, the way the app reads the card.
    private func card(_ points: [String]) throws -> FeedFuturesData {
        let json = """
        {
          "id": 8430022, "name": "When will Anthropic officially announce an IPO?",
          "sport": null, "sport_name": null, "llm_sport_category": "tech",
          "source": "kalshi", "source_count": 1, "status": "open",
          "resolution_date": null, "confidence_tier": "low",
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

    private func drawn(_ data: FeedFuturesData) -> [String] {
        HeatMapCardView(data: data, navigationPath: .constant(NavigationPath())).drawnLabels
    }

    private func rung(_ source: String, _ value: Double, _ probability: Double) -> FeedDiscoverThresholdPoint {
        FeedDiscoverThresholdPoint(
            source: source, label: "r\(Int(value))", value: value, unit: nil,
            direction: nil, probability: probability, needsSiblingMarkets: nil
        )
    }

    // MARK: - The defect

    func testTheProductionCardDrawsTheCrossoverWithARungEitherSide() throws {
        let data = try card(anthropicIpo)
        XCTAssertEqual(data.discoverCard?.thresholdPoints?.count, 10, "the fixture decodes whole")
        XCTAssertEqual(
            drawn(data),
            ["Before Oct 24, 2026", "Before Nov 1, 2026", "Before Dec 1, 2026",
             "Before Jan 1, 2027", "Before Feb 1, 2027"],
            "the card drew the five near-zero rungs before the one its caption names"
        )
    }

    /// The caption reads every rung; the cells must contain whatever it names,
    /// however many rungs are served.
    func testTheCellsHoldTheCaptionRungAtEveryServedLength() throws {
        for count in 6...anthropicIpo.count {
            let labels = drawn(try card(Array(anthropicIpo.prefix(count))))
            XCTAssertEqual(labels.count, 5, "with the first \(count) rungs")
            XCTAssertTrue(labels.contains("Before Dec 1, 2026"), "with the first \(count) rungs: \(labels)")
        }
    }

    /// Every ladder length and every crossover position, both axes: the window is
    /// `maxCells` contiguous rungs in ladder order and holds the caption's rung.
    func testTheWindowIsContiguousAndHoldsTheAnchorEverywhere() {
        for source in ["date_bucket", "outcome"] {
            for n in 1...12 {
                for anchor in 0..<n {
                    // Date ladder: chances rise, first over-even is the anchor.
                    // Comparator ladder: chances fall, last over-even is the anchor.
                    let ladder = (0..<n).map { i -> FeedDiscoverThresholdPoint in
                        let over = source == "date_bucket" ? i >= anchor : i <= anchor
                        return rung(source, Double(i), over ? 0.7 : 0.2)
                    }
                    let window = heatMapDrawnRungs(ladder, maxCells: 5)
                    let values = window.compactMap(\.value)
                    let where_ = "\(source) n=\(n) anchor=\(anchor)"
                    XCTAssertEqual(window.count, min(5, n), where_)
                    XCTAssertTrue(values.contains(Double(anchor)), where_)
                    XCTAssertEqual(values, (0..<values.count).map { values[0] + Double($0) }, where_)
                }
            }
        }
    }

    // MARK: - Controls

    func testALadderThatFitsDrawsEveryRung() throws {
        let data = try card(Array(anthropicIpo.suffix(5)))
        XCTAssertEqual(drawn(data).count, 5)
        XCTAssertEqual(drawn(data).first, "Before Dec 1, 2026")
    }

    /// "All below 50%" names no rung, so there is nothing to centre on: the first
    /// rungs, as before.
    func testALadderWithNoRungOverEvenKeepsItsFirstRungs() {
        let ladder = (0..<8).map { rung("date_bucket", Double($0), 0.1) }
        XCTAssertEqual(heatMapDrawnRungs(ladder, maxCells: 5).compactMap(\.value), [0, 1, 2, 3, 4])
    }

    /// A comparator ladder whose crossover is near its start draws the same first
    /// five it always did.
    func testAnEarlyCrossoverDrawsTheFirstRungs() {
        let ladder = (0..<8).map { rung("outcome", Double($0), $0 <= 1 ? 0.8 : 0.2) }
        XCTAssertEqual(heatMapDrawnRungs(ladder, maxCells: 5).compactMap(\.value), [0, 1, 2, 3, 4])
    }

    /// A crossover at the top of the ladder clamps to its last five.
    func testALateCrossoverClampsToTheLastRungs() {
        let ladder = (0..<8).map { rung("date_bucket", Double($0), $0 >= 7 ? 0.8 : 0.2) }
        XCTAssertEqual(heatMapDrawnRungs(ladder, maxCells: 5).compactMap(\.value), [3, 4, 5, 6, 7])
    }
}
