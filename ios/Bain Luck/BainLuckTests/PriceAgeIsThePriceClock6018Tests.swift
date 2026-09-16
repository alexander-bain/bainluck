import XCTest
@testable import Bain_Luck

/// #6018 (native half) — THE "UPDATED" STAMP WAS READING THE WRONG CLOCK.
///
/// `FuturesDetailView`'s metadata card printed `market.updated_at` under the
/// word "Updated", directly above a hero probability, a price chart and a
/// ladder of prices. That column is when the market ROW was touched; the prices
/// live in `futures_outcomes.last_updated` and are written by different passes.
/// The web twin found this first and shipped `lib/futuresCardPriceAge.ts`
/// (#6018); the native half was never built, so the two tiers answered "how
/// fresh is this number?" with two different clocks.
///
/// Measured on production 2026-09-16 (see `Utilities/FuturesPriceAge` for the
/// full rows): market 55686530 printed "Updated Sep 12 at 5:53 PM" over seven
/// prices rewritten Sep 16 05:51Z — three days of understatement — while market
/// 109435's row, touched two hours before the shot, vouched for a rung frozen
/// since Sep 7. Wrong in both directions, on one screen each.
///
/// ## What is pinned, and why in this shape
///
/// 🔴 The defect is not "the date is off". It is that ONE stamp is read as
/// covering every row beneath it, so the rule has a direction: the FLOOR. A
/// guard that only asserted "the stamp moved off `updatedAt`" would pass on the
/// newest-price version, which is the flattering half of the same lie and is
/// what market 109435 already does. So `oldest_wins` is asserted with a set
/// whose newest member is the trap.
///
/// The view assertion is a SOURCE SCAN for the same reason #6501's was: the
/// metadata card is inside a 700-line `ScrollView` body that no test can
/// instantiate headlessly, and CI compiles no Swift (#4302). Comments are
/// stripped first, so the prose this fix just wrote — which names both field
/// names — cannot satisfy a claim about code.
final class PriceAgeIsThePriceClock6018Tests: XCTestCase {

    // MARK: - The rule

    private let iso = ISO8601DateFormatter()

    /// THE TRAP: the newest stamp is last in the list and the shortest to
    /// reach. A `max`, a `first`, or a `.sorted().last` all pass a test that
    /// only checks "not updatedAt"; none of them passes this one.
    func test_oldest_wins_over_a_fresher_sibling() throws {
        let asOf = try XCTUnwrap(FuturesPriceAge.oldestStamp([
            "2026-09-16T05:51:43.449574+00:00",
            "2026-09-07T08:50:00+00:00",          // the frozen rung — the answer
            "2026-09-16T07:50:00+00:00",
        ]))
        XCTAssertEqual(iso.string(from: asOf), "2026-09-07T08:50:00Z")
    }

    /// Both stamp shapes the API serves reach the same clock. `last_updated`
    /// carries fractional seconds and `commence_time` does not; a parser that
    /// handled only one would silently drop half the rows and age the page to
    /// whichever half survived.
    func test_both_iso_shapes_parse() throws {
        let withFrac = try XCTUnwrap(FuturesPriceAge.oldestStamp(["2026-09-16T05:51:43.449574+00:00"]))
        let without = try XCTUnwrap(FuturesPriceAge.oldestStamp(["2026-09-16T05:51:43+00:00"]))
        XCTAssertEqual(iso.string(from: withFrac), "2026-09-16T05:51:43Z")
        XCTAssertEqual(iso.string(from: without), "2026-09-16T05:51:43Z")
    }

    /// An unparseable row is skipped, not treated as time zero. Treating it as
    /// the oldest would print 1970 over a live ladder.
    func test_an_unreadable_row_is_skipped_not_floored() throws {
        let asOf = try XCTUnwrap(FuturesPriceAge.oldestStamp([
            nil, "", "not a date", "2026-09-16T05:51:43+00:00",
        ]))
        XCTAssertEqual(iso.string(from: asOf), "2026-09-16T05:51:43Z")
    }

    /// "This payload cannot say" is nil, so the caller can render nothing.
    /// Notice 34: if a number cannot be shown honestly, leave the space empty.
    func test_nothing_to_say_is_nil() {
        XCTAssertNil(FuturesPriceAge.oldestStamp([]))
        XCTAssertNil(FuturesPriceAge.oldestStamp([nil, nil]))
        XCTAssertNil(FuturesPriceAge.oldestStamp(["yesterday"]))
    }

    /// 🔴 THE RULE IS ONLY WORTH ANYTHING IF IT REACHES THE PRICES.
    ///
    /// Every assertion above calls `oldestStamp` directly, so a `pricesAsOf`
    /// that read the wrong field — or returned `nil` unconditionally, which
    /// merely deletes the row and looks tidy — passes all of them AND both
    /// source scans. This decodes the real payload shape (`/api/futures/{id}`
    /// outcomes, `.convertFromSnakeCase`) so the `last_updated` key, the
    /// mapping and the floor are one chain.
    func test_pricesAsOf_reads_last_updated_off_the_real_payload_shape() throws {
        let json = """
        [
          {"id": 1, "name": "Guyana Amazon Warriors", "probability": 0.403,
           "last_updated": "2026-09-16T05:51:43.449574+00:00"},
          {"id": 2, "name": "Barbados Royals", "probability": 0.167,
           "last_updated": "2026-09-07T08:50:00+00:00"},
          {"id": 3, "name": "Trinbago Knight Riders", "probability": 0.1,
           "last_updated": null}
        ]
        """
        let decoder = JSONDecoder()
        decoder.keyDecodingStrategy = .convertFromSnakeCase
        let outcomes = try decoder.decode([FuturesOutcome].self, from: Data(json.utf8))

        let asOf = try XCTUnwrap(FuturesPriceAge.pricesAsOf(outcomes))
        XCTAssertEqual(iso.string(from: asOf), "2026-09-07T08:50:00Z")
    }

    /// A market whose rows carry no stamp at all says nothing, so the caller
    /// renders nothing. This is the branch that must NOT quietly become
    /// `market.updatedAt` again.
    func test_pricesAsOf_is_nil_when_no_row_can_say() throws {
        let json = """
        [{"id": 1, "name": "Only Outcome", "probability": 0.5}]
        """
        let decoder = JSONDecoder()
        decoder.keyDecodingStrategy = .convertFromSnakeCase
        let outcomes = try decoder.decode([FuturesOutcome].self, from: Data(json.utf8))
        XCTAssertNil(FuturesPriceAge.pricesAsOf(outcomes))
    }

    // MARK: - The view

    private func detailSource() throws -> String {
        let url = URL(fileURLWithPath: #filePath)
            .deletingLastPathComponent()   // BainLuckTests
            .deletingLastPathComponent()   // Bain Luck (project dir)
            .appendingPathComponent("Bain Luck")
            .appendingPathComponent("Views")
            .appendingPathComponent("FuturesDetailView.swift")
        return try Self.stripped(String(contentsOf: url, encoding: .utf8))
    }

    /// Line comments removed, then ALL whitespace, so an expectation never
    /// encodes where the author happened to wrap a line.
    static func stripped(_ text: String) -> String {
        text
            .split(separator: "\n", omittingEmptySubsequences: false)
            .map { line -> String in
                guard let slashes = line.range(of: "//") else { return String(line) }
                return String(line[line.startIndex..<slashes.lowerBound])
            }
            .joined(separator: "\n")
            .filter { !$0.isWhitespace }
    }

    /// The stamp is computed from the prices.
    func test_the_updated_row_reads_the_price_clock() throws {
        let code = try detailSource()
        XCTAssertTrue(
            code.contains("FuturesPriceAge.pricesAsOf(market.outcomes)"),
            "The Updated row must age itself from the outcomes it draws."
        )
    }

    /// 🔴 THE GENERAL CLAIM, and the one that survives the next edit: the row
    /// clock is not reachable from this view AT ALL. Pinning only the positive
    /// call above passes the moment someone re-adds `market.updatedAt` beside
    /// it — which is exactly how a wrong stamp comes back, since the field is
    /// still on the model and still decodes. #6501's lesson: a guard that names
    /// the sites it knows about cannot see the site added after it.
    func test_the_row_clock_is_not_rendered_anywhere_in_this_view() throws {
        let code = try detailSource()
        XCTAssertFalse(
            code.contains("market.updatedAt"),
            """
            FuturesDetailView reads `market.updatedAt` again. That column is \
            when the market ROW was touched, not when its prices moved, and it \
            was measured wrong in both directions on production (#6018). If a \
            row-level timestamp is genuinely wanted here, it needs a label that \
            is not a freshness claim about the numbers on the page.
            """
        )
    }

    /// The empty case is a real branch, not prose: the stamp is inside an
    /// `if let`, so a payload with no readable price stamp renders no row. A
    /// version that fell back to `updatedAt` would satisfy the two assertions
    /// above and still print the wrong clock on exactly the markets where the
    /// right one is unavailable.
    func test_no_fallback_to_the_row_clock() throws {
        let code = try detailSource()
        XCTAssertTrue(
            code.contains("ifletdate=FuturesPriceAge.pricesAsOf(market.outcomes){"),
            "The price stamp must be optional-bound, with no else-branch clock."
        )
        XCTAssertFalse(code.contains("??market.updatedAt"))
    }
}
