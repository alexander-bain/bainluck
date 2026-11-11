import XCTest
@testable import Bain_Luck

/// #12581 — the sheet against what Builder B's server change (PR #12597) actually
/// serves: Patriots at Lions' game-markets as the PR builds it from its saved
/// fixture, and blended, settled and capped marks made by the PR's own builder.
final class ServerSourceMarks12581Tests: XCTestCase {
    private let now = Date(timeIntervalSince1970: 1_794_426_300) // 2026-11-11T19:45:00Z

    private func fixture(_ name: String) throws -> Data {
        let url = URL(fileURLWithPath: #filePath).deletingLastPathComponent()
            .appendingPathComponent("Fixtures12581/\(name).json")
        return try Data(contentsOf: url)
    }

    private func decoder() -> JSONDecoder {
        let decoder = JSONDecoder()
        decoder.keyDecodingStrategy = .convertFromSnakeCase
        return decoder
    }

    private struct Wrapped: Decodable { let page: GameMarketsResponse }

    private func marks() throws -> [String: SourceMark] {
        let raw = try XCTUnwrap(JSONSerialization.jsonObject(with: try fixture("server_marks")) as? [String: Any])
        var out: [String: SourceMark] = [:]
        for key in ["blend", "settled", "none_capped"] {
            let data = try JSONSerialization.data(withJSONObject: try XCTUnwrap(raw[key]))
            out[key] = try decoder().decode(SourceMark.self, from: data)
        }
        return out
    }

    func testPatriotsLionsDecodesAndEveryPropCarriesOneVenue() throws {
        let page = try decoder().decode(Wrapped.self, from: try fixture("patriots_lions_game_markets")).page
        let props = try XCTUnwrap(page.playerProps)
        XCTAssertEqual(props.count, 270)
        for prop in props {
            let mark = try XCTUnwrap(prop.sourceMark, prop.id)
            XCTAssertEqual(mark.state, .blend, prop.id)
            XCTAssertEqual(mark.sources.count, 1, "145-A: props aren't blended; one venue per prop (\(prop.id))")
            XCTAssertTrue(mark.draws)
            XCTAssertEqual(SourceMarkSheet.method(mark), "\(mark.sources[0].name)'s price")
        }
        // The 18 Polymarket-only props now arrive named "Player: N+", so the card draws them.
        let polymarket = props.filter { $0.sourceMark?.sources.first?.key == "polymarket" }
        XCTAssertEqual(polymarket.count, 18)
        XCTAssertTrue(polymarket.allSatisfy { $0.outcomeName.contains(":") })
    }

    func testABlendedNumberListsEachVenueOnceAndSaysItIsABlend() throws {
        let blend = try XCTUnwrap(try marks()["blend"])
        XCTAssertEqual(SourceMarkSheet.lines(blend, now: now), [
            .init(name: "Kalshi", price: "57%", age: "1m ago"),
            .init(name: "Polymarket", price: "59%", age: nil),
            .init(name: "Sportsbooks (6)", price: "59%", age: "just now"),
        ], "server order; a source with no observation time shows no age")
        XCTAssertEqual(SourceMarkSheet.method(blend), "Bain Luck blend, weighted by freshness and depth")
    }

    func testASettledNumberNamesNoSources() throws {
        let settled = try XCTUnwrap(try marks()["settled"])
        XCTAssertTrue(SourceMarkSheet.lines(settled, now: now).isEmpty)
        XCTAssertEqual(SourceMarkSheet.settledLine(settled, now: now)?.name, "Official result")
        XCTAssertEqual(SourceMarkSheet.settledLine(settled, now: now)?.price, "Won")
        XCTAssertNil(SourceMarkSheet.method(settled))
        XCTAssertEqual(SourceMarkSheet.headline(1, mark: settled), "Won", "a result, never \"100%\"")
    }

    func testACappedRungKeepsTheMarkAndSaysWhyNoSourceStandsBehindIt() throws {
        let capped = try XCTUnwrap(try marks()["none_capped"])
        XCTAssertEqual(capped.state, .none)
        XCTAssertEqual(capped.reason, "monotonic_conflict")
        XCTAssertNotNil(SourceMarkButton(capped, number: 0.31, numberSize: 20), "the ⓘ is on every marked number")
        XCTAssertTrue(SourceMarkSheet.lines(capped, now: now).isEmpty)
        XCTAssertEqual(SourceMarkSheet.method(capped),
                       "This line is held to the price of the line below it, so no source's own price stands behind this number.")
    }
}
