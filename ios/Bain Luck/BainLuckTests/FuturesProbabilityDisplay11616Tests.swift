import XCTest
@testable import Bain_Luck

// Web's test executes probabilityDisplay on this same table; Native executes
// the actual helper here. This is label parity, not a new normalization rule.
// FUTURES LABEL CASES BEGIN
private let labelCases: [(Double, Int?, String)] = [
    (0.0, nil, "0%"),
    (0.0005, nil, "<1%"),
    (0.0049, nil, "<1%"),
    (0.005, nil, "1%"),
    (0.006, nil, "1%"),
    (0.145, nil, "15%"),
    (0.285, nil, "29%"),
    (0.565, nil, "57%"),
    (0.575, nil, "58%"),
    (0.5, nil, "50%"),
    (0.994, nil, "99%"),
    (0.995, nil, ">99%"),
    (0.999, nil, ">99%"),
    (1.0, nil, "100%"),
    (0.405, 40, "40%"),
    (0.0005, 0, "<1%"),
    (0.999, 100, ">99%"),
    (0.995, 99, "99%"),
    (0.006, 0, "<1%"),
    (0.925, 93, "93%"),
    (0.075, 7, "7%"),
]
// FUTURES LABEL CASES END

final class FuturesProbabilityDisplay11616Tests: XCTestCase {
    func testEveryWebBoundaryAndFieldOverride() {
        for (probability, integer, expected) in labelCases {
            XCTAssertEqual(futuresProbabilityLabel(probability, renderedPercent: integer), expected)
            XCTAssertEqual(futuresProbabilityNumber(probability, renderedPercent: integer) + "%", expected)
        }
    }

    func testNonfiniteValuesRemainAbsentEvenWithAnOverride() {
        for value in [Double.nan, .infinity, -.infinity] {
            XCTAssertEqual(futuresProbabilityLabel(value, renderedPercent: 50), "—")
            XCTAssertEqual(futuresProbabilityNumber(value), "—")
        }
    }

    func testUnrelatedFormatterPoliciesArePreserved() {
        XCTAssertEqual(formatProbability(0), "<1%")
        XCTAssertEqual(formatProbability(0.994), ">99%")
        XCTAssertEqual(percentNumber(99.9), "100")
        XCTAssertEqual(percentNumber(0.6), "<1")
    }

    func testDecodedFullFieldIntegersSurvivePartialSelectionAndOrder() throws {
        let wire = Data("""
        [{"id":1,"name":"Victor","probability":0.605,"rendered_percent":61},
         {"id":2,"name":"Shai","probability":0.395,"rendered_percent":40},
         {"id":3,"name":"Nikola","probability":0.2,"rendered_percent":20}]
        """.utf8)
        let decoder = JSONDecoder()
        decoder.keyDecodingStrategy = .convertFromSnakeCase
        let detail = try decoder.decode([FuturesOutcome].self, from: wire)
        let search = try decoder.decode([SearchFuturesOutcome].self, from: wire)
        XCTAssertEqual(futuresDetailRenderedPercents(Array(detail.prefix(2))), [1: 61, 2: 40])
        XCTAssertEqual(futuresDetailRenderedPercents(Array(detail.reversed())), [1: 61, 2: 40, 3: 20])
        XCTAssertEqual(search.map(\.renderedPercent), [61, 40, 20])
        XCTAssertEqual(futuresProbabilityLabel(search[1].probability!, renderedPercent: search[1].renderedPercent), "40%")
    }

    func testLegacyAndMalformedOptionalIntegersKeepTheOutcome() throws {
        let decoder = JSONDecoder()
        decoder.keyDecodingStrategy = .convertFromSnakeCase
        for metadata in ["", ",\"rendered_percent\":null", ",\"rendered_percent\":\"bad\""] {
            let wire = Data("{\"id\":1,\"name\":\"Victor\",\"probability\":0.605\(metadata)}".utf8)
            let detail = try decoder.decode(FuturesOutcome.self, from: wire)
            let search = try decoder.decode(SearchFuturesOutcome.self, from: wire)
            XCTAssertNil(detail.renderedPercent)
            XCTAssertNil(search.renderedPercent)
            XCTAssertEqual(detail.probability, 0.605)
            XCTAssertEqual(search.probability, 0.605)
        }
    }

    func testActualFuturesConsumersUseTheFormatterAndKeepFieldOverrides() throws {
        let app = URL(fileURLWithPath: #filePath).deletingLastPathComponent()
            .deletingLastPathComponent().appendingPathComponent("Bain Luck")
        let detail = try String(contentsOf: app.appendingPathComponent("Views/FuturesDetailView.swift"), encoding: .utf8)
        let search = try String(contentsOf: app.appendingPathComponent("Views/SearchView.swift"), encoding: .utf8)
        let component = try String(contentsOf: app.appendingPathComponent("Components/DesignSystem.swift"), encoding: .utf8)
        XCTAssertTrue(detail.contains("futuresProbabilityLabel(prob, renderedPercent: heroPercent)"))
        XCTAssertTrue(detail.contains("formattedNumber: futuresProbabilityNumber(prob, renderedPercent: percent)"))
        XCTAssertTrue(detail.contains("futuresProbabilityLabel(prob, renderedPercent: percent)"))
        XCTAssertTrue(detail.contains("futuresProbabilityLabel(lastRecorded, renderedPercent: percent)"))
        XCTAssertTrue(detail.contains("let label = futuresProbabilityLabel(prob, renderedPercent: percent)"))
        XCTAssertTrue(search.contains("Text(futuresProbabilityLabel(probability, renderedPercent: renderedPercent))"))
        XCTAssertTrue(component.contains("formattedNumber ?? percentNumber(value, renderedPercent: renderedPercent)"))
        XCTAssertTrue(component.contains("if formattedNumber != \"—\""))
    }
}
