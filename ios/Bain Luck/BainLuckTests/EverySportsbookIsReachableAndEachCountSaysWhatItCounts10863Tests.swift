import XCTest
@testable import Bain_Luck

/// #10863 — "SPORTSBOOKS (6)" ABOVE TEN ROWS, AND NO WAY TO SEE AN ELEVENTH.
///
/// Alex's phone, Texas–Oklahoma (`14792837`), build 47: the Sources panel read
/// "Sportsbooks (6)" and listed ten sportsbooks underneath it, five of them
/// faded with ages of 45 minutes to 3 hours. The two numbers count different
/// things and nothing on screen said so:
///
/// - the 6 is `betting_book_count`, how many sportsbooks the odds poll that
///   wrote `betting` took its median from;
/// - the table is each sportsbook's LATEST price, older ones kept and marked
///   with their age (#7926).
///
/// And `namedBookmakerRows` ended in a silent `prefix(10)`, so an eleventh
/// named, priced sportsbook was unreachable from the page.
///
/// What these pin, and the mutation each kills:
/// - put a default cap back in `namedBookmakerRows` → `testEveryNamedPricedBookIsAReturnedRow`
/// - drop the "Show all" path or cap it short → `testShowAllRevealsEveryRowInPayloadOrder`
/// - filter old prices out instead of marking them → `testOlderPricesPastTheFirstTenKeepTheirAge`
/// - fold the count back into the label → `testTheConsensusCountAndTheTableCountReadAsDifferentThings`
final class EverySportsbookIsReachableAndEachCountSaysWhatItCounts10863Tests: XCTestCase {

    /// One fixed instant (gotcha #44). Every stamp is a fixed offset from it.
    private static let now = Date(timeIntervalSince1970: 1_791_590_400) // 2026-10-10T00:00:00Z

    private static func iso(minutesBefore minutes: Int) -> String {
        let f = ISO8601DateFormatter()
        f.formatOptions = [.withInternetDateTime]
        return f.string(from: now.addingTimeInterval(-Double(minutes) * 60))
    }

    private static func book(_ key: String, home: Double?, minutesAgo: Int) -> String {
        let price = home.map { "\"home_probability\": \($0), \"away_probability\": \(1 - $0)" }
            ?? "\"home_probability\": null, \"away_probability\": null"
        return """
        {"bookmaker": "\(key)", "captured_at": "\(iso(minutesBefore: minutesAgo))", \(price)}
        """
    }

    /// Thirteen named, priced sportsbooks, the last three hours old, with one
    /// unnamed key and one priceless book mixed in. Bigger than the old cap on
    /// purpose: a payload of ten or fewer cannot tell a cap from no cap.
    private static let payload: [(key: String, home: Double?, minutesAgo: Int)] = [
        ("fanduel", 0.69, 2), ("draftkings", 0.70, 2), ("betmgm", 0.68, 3),
        ("williamhill_us", 0.70, 3), ("fanatics", 0.71, 4),
        ("not_a_book_we_name", 0.70, 2),
        ("espnbet", 0.69, 5), ("betrivers", 0.70, 6), ("ballybet", 0.70, 8),
        ("mybookie", nil, 2),
        ("rebet", 0.66, 45), ("betus", 0.58, 180), ("lowvig", 0.57, 181),
        ("betonlineag", 0.57, 182),
    ]

    private static func rows() throws -> [EventDetailView.NamedBookmakerRow] {
        let json = "[" + payload.map { book($0.key, home: $0.home, minutesAgo: $0.minutesAgo) }
            .joined(separator: ",") + "]"
        let decoder = JSONDecoder()
        decoder.keyDecodingStrategy = .convertFromSnakeCase
        let books = try decoder.decode([BookmakerOdds].self, from: Data(json.utf8))
        return EventDetailView.namedBookmakerRows(books)
    }

    // MARK: - Every sportsbook is reachable

    func testEveryNamedPricedBookIsAReturnedRow() throws {
        let ids = try Self.rows().map(\.id)
        XCTAssertEqual(ids.count, 12, "every named, priced book; no default cap: \(ids)")
        XCTAssertFalse(ids.contains("not_a_book_we_name"), "#4284's naming rule still holds")
        XCTAssertFalse(ids.contains("mybookie"), "#4406's price rule still holds")
        XCTAssertEqual(Array(ids.suffix(2)), ["lowvig", "betonlineag"])
    }

    func testTheTableOpensOnTheFirstTenAndOffersTheRest() throws {
        let rows = try Self.rows()
        let collapsed = EventDetailView.visibleBookmakerRows(rows, showAll: false)
        XCTAssertEqual(EventDetailView.collapsedBookmakerRowLimit, 10)
        XCTAssertEqual(collapsed.map(\.id), Array(rows.prefix(10)).map(\.id))
        XCTAssertEqual(
            EventDetailView.showAllBookmakersLabel(rowCount: rows.count, showingAll: false),
            "Show all 12 sportsbooks")
        XCTAssertEqual(
            EventDetailView.showAllBookmakersLabel(rowCount: rows.count, showingAll: true),
            "Show fewer sportsbooks")
    }

    func testShowAllRevealsEveryRowInPayloadOrder() throws {
        let rows = try Self.rows()
        let all = EventDetailView.visibleBookmakerRows(rows, showAll: true)
        XCTAssertEqual(all.map(\.id), rows.map(\.id))
    }

    func testAShortTableIsUnchanged() throws {
        let rows = Array(try Self.rows().prefix(7))
        XCTAssertEqual(
            EventDetailView.visibleBookmakerRows(rows, showAll: false).map(\.id),
            rows.map(\.id))
    }

    /// #7926's rule past the old cap: an older price is marked, never dropped.
    func testOlderPricesPastTheFirstTenKeepTheirAge() throws {
        let tail = Array(try Self.rows().dropFirst(10))
        XCTAssertEqual(tail.map(\.id), ["lowvig", "betonlineag"])
        for row in tail {
            let mark = try XCTUnwrap(row.priceAgeMark(now: Self.now), row.id)
            XCTAssertEqual(mark.age, "3h ago", row.id)
        }
    }

    // MARK: - Each count says what it counts

    func testTheConsensusCountAndTheTableCountReadAsDifferentThings() throws {
        let decoder = JSONDecoder()
        decoder.keyDecodingStrategy = .convertFromSnakeCase
        let sources = try decoder.decode([String: WinProbSource].self, from: Data("""
        {
          "betting": {"value": 0.71, "display_name": "Betting Odds", "type": "market"},
          "kalshi": {"value": 0.70, "display_name": "Kalshi", "type": "market"},
          "betting_book_count": {"value": 6.0, "display_name": "betting_book_count", "type": "model"}
        }
        """.utf8))
        let betting = try XCTUnwrap(
            WinProbSourceCatalog.entries(from: sources).first { $0.key == "betting" })
        let heading = EventDetailView.bookmakerTableHeading(rowCount: 12)

        XCTAssertEqual(betting.label, "Sportsbooks", "no bare count in the label")
        XCTAssertEqual(betting.detail, "Based on 6 sportsbooks")
        XCTAssertEqual(heading, "Latest probabilities from each sportsbook (12)")
        XCTAssertFalse(heading.contains("Based on"))
        XCTAssertNotEqual(betting.label + (betting.detail ?? ""), heading)
    }

    func testOneSportsbookIsSingular() {
        XCTAssertEqual(WinProbSourceCatalog.consensusCountLine(1), "Based on 1 sportsbook")
        XCTAssertEqual(WinProbSourceCatalog.consensusCountLine(6), "Based on 6 sportsbooks")
    }

    /// Notice 33: the reader never sees "books" on its own.
    func testNoReaderStringSaysBooks() {
        let strings = [
            WinProbSourceCatalog.consensusCountLine(1),
            WinProbSourceCatalog.consensusCountLine(6),
            EventDetailView.bookmakerTableHeading(rowCount: 12),
            EventDetailView.showAllBookmakersLabel(rowCount: 12, showingAll: false),
            EventDetailView.showAllBookmakersLabel(rowCount: 12, showingAll: true),
        ]
        for s in strings {
            XCTAssertNil(
                s.range(of: #"\bbooks?\b|bookmaker"#, options: [.regularExpression, .caseInsensitive]),
                s)
        }
    }
}
