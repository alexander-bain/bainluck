import XCTest
@testable import Bain_Luck

/// native/081, #4284 — the event page printed database values where brands go.
///
/// Photographed at default Dynamic Type on a 375pt phone, from a build of master
/// `8d0abc64`, on the books-only specimen `bainluck://events/15305582`
/// (Northampton Town vs Shrewsbury Town):
///
///     INDIVIDUAL SPORTSBOOKS
///     betmgm        ▓▓▓▓▓  49%  51%
///     betonlineag   ▓▓▓▓▓  49%  51%
///     betus         ▓▓▓▓▓  49%  51%
///     lowvig        ▓▓▓▓▓  49%  51%
///
/// `SourceLabels`, two files away, already knew those four as BetMGM, BetOnline,
/// BetUS and LowVig. `bookmakerContent` never asked it: the row drew
/// `bm.bookmaker ?? "Unknown"`. This is #4135's defect on a fifth surface, and
/// `SourceLabels` exists because the PASSTHROUGH, not the key, is the bug.
///
/// These are pure-function tests and CI compiles no Swift, so the call site is
/// guarded by `frontend/__tests__/ios/appNamesEverySourceItPrints.test.ts`. This
/// file proves the rows; that file proves the view asks for them.
final class EventBookmakerNamesTests: XCTestCase {

    // MARK: - Fixtures

    /// Decoded rather than memberwise-initialised, so the fixture is the payload
    /// shape the app really receives — snake_case keys and all. A hand-built
    /// struct would still pass if the decoding contract moved underneath it.
    private static func bookmakers(_ json: String) throws -> [BookmakerOdds] {
        let decoder = JSONDecoder()
        decoder.keyDecodingStrategy = .convertFromSnakeCase
        return try decoder.decode([BookmakerOdds].self, from: Data(json.utf8))
    }

    private static func row(_ key: String, away: Double? = 0.49, home: Double? = 0.51) -> String {
        let awayText = away.map { "\($0)" } ?? "null"
        let homeText = home.map { "\($0)" } ?? "null"
        return """
            {"bookmaker": "\(key)", "away_probability": \(awayText), \
            "home_probability": \(homeText), "home_moneyline": null, \
            "away_moneyline": null, "captured_at": "2026-09-07T10:07:40Z", \
            "spread": null, "over_under": null, "projected_home_score": null, \
            "projected_away_score": null}
            """
    }

    private static func rows(
        _ keys: [String], limit: Int = 10
    ) throws -> [EventDetailView.NamedBookmakerRow] {
        EventDetailView.namedBookmakerRows(
            try bookmakers("[\(keys.map { row($0) }.joined(separator: ","))]"), limit: limit)
    }

    // MARK: - The frame in the issue

    /// The exact payload production served for 15305582 at 10:22Z on 2026-09-09,
    /// in its own order. Every one of the eight was drawing as its key.
    func testTheSpecimenEventDrawsEightBrandsAndNotOneKey() throws {
        let keys = [
            "betmgm", "betonlineag", "betrivers", "betus",
            "bovada", "draftkings", "fanatics", "lowvig",
        ]
        let rows = try Self.rows(keys)

        XCTAssertEqual(
            rows.map(\.label),
            [
                "BetMGM", "BetOnline", "BetRivers", "BetUS",
                "Bovada", "DraftKings", "Fanatics", "LowVig",
            ])

        // The defect as a property rather than a list: no row draws its own key.
        //
        // It does NOT also assert `label != id.capitalized`, though that is the
        // #4135 fallback and the tempting stronger claim. Two of these eight —
        // Bovada and Fanatics — really are their key capitalised, so that
        // assertion fails on correct output, and the only way to make it pass is
        // to spell a brand wrong. The title-casing claim belongs to the keys
        // where it is false (`betonlineag`, `betmgm`, `betparx`, …), and it is
        // made there: `SourceLabelsTests.testTheBrandsAreSpeltAsTheBrandsAndNotAsTheirKeys`.
        for row in rows {
            XCTAssertNotEqual(row.label, row.id, "\(row.id) reached the screen raw")
        }

        // The row is a NAME plus a PRICE, and renaming it must not cost it the
        // price. Without this, a `namedBookmakerRows` that returned every brand
        // with no pair would pass every other test in this file and draw eight
        // labelled rows with no bars and no numbers. Since #4406 the type says
        // so — `probabilities` is not optional — and this is what the type is
        // worth: eight rows, eight pairs, no arithmetic in between.
        XCTAssertEqual(rows.count, 8)
        XCTAssertEqual(rows.first?.probabilities.away ?? 0, 0.49, accuracy: 0.0001)
        XCTAssertEqual(rows.first?.probabilities.home ?? 0, 0.51, accuracy: 0.0001)
    }

    /// Every key production served in the 24h to 2026-09-09 10:30Z draws a brand.
    /// Seven of these eighteen were nameless before this ship.
    ///
    /// 🔴 THE LIMIT IS LIFTED DELIBERATELY. Eighteen keys through the default cap
    /// of ten returns ten rows, and the first version of this test read that as
    /// "eight production keys have no name" — it accused the map of what the cap
    /// had done, with a message naming eight innocent books. A census fixture
    /// larger than the cap must say so, or the cap answers the question.
    func testEveryProductionKeyDrawsARow() throws {
        let measured = [
            "bovada", "betonlineag", "lowvig", "draftkings", "fanduel", "betus",
            "betrivers", "betmgm", "fanatics", "williamhill_us", "mybookieag",
            "fliff", "ballybet", "betparx", "espnbet", "rebet", "hardrockbet",
            "betanysports",
        ]
        let rows = try Self.rows(measured, limit: measured.count)
        XCTAssertEqual(
            rows.count, measured.count,
            "a key production serves drew no row: "
                + measured.filter { key in !rows.contains { $0.id == key } }.joined(separator: ", "))
    }

    // MARK: - The unnameable key

    /// The rule this surface inherits from `sportsbookChips(for:)`: a key the app
    /// cannot name is a key the app does not print. It costs a row of detail; the
    /// alternative costs the reader a brand that does not exist.
    func testAnUnnameableKeyDrawsNoRowRatherThanItsRawSelf() throws {
        let rows = try Self.rows(["draftkings", "a_new_venue", "betmgm"])
        XCTAssertEqual(rows.map(\.label), ["DraftKings", "BetMGM"])
        XCTAssertFalse(rows.contains { $0.id == "a_new_venue" })
    }

    /// …including when it is the only thing in the payload, which is what makes
    /// `sourcesToggle` ask this function rather than `bookmakerOdds`: otherwise
    /// the disclosure opens onto an "INDIVIDUAL SPORTSBOOKS" heading with an
    /// empty table under it.
    func testAPayloadOfOnlyUnnameableKeysYieldsNoTable() throws {
        XCTAssertTrue(try Self.rows(["a_new_venue", "another_one"]).isEmpty)
    }

    // MARK: - The cap

    /// 🔴 THE ORDERING DECISION, BOTH WAYS ROUND. Cap-then-name and
    /// name-then-cap agree on every payload of ten or fewer, so a fixture that
    /// small cannot see the difference. With eleven books where one is
    /// unnameable, cap-first draws nine named rows and name-first draws ten —
    /// the reader loses a row they could have read, to a row we never draw.
    ///
    /// Run at both ends and in the middle, because a defect that only shows when
    /// the odd row out sits in position zero is a test of the position (the
    /// `.max()` → `.first` survivor of #4208).
    func testTheCapIsAppliedAfterNamingSoAnUnnameableKeyCostsNobodyASlot() throws {
        let named = [
            "draftkings", "fanduel", "betmgm", "caesars", "betrivers",
            "bovada", "espnbet", "betonlineag", "lowvig", "fliff",
        ]
        let expected = [
            "DraftKings", "FanDuel", "BetMGM", "Caesars", "BetRivers",
            "Bovada", "ESPN BET", "BetOnline", "LowVig", "Fliff",
        ]
        for position in [0, 5, named.count] {
            var keys = named
            keys.insert("a_new_venue", at: position)

            let rows = try Self.rows(keys)
            XCTAssertEqual(
                rows.count, 10,
                "unnameable key at \(position) cost a named book its slot")
            XCTAssertEqual(
                rows.map(\.label), expected,
                "unnameable key at \(position) changed which books the table draws")
        }
    }

    /// The cap is still a cap.
    func testMoreNamedBooksThanTheCapAreTruncatedInPayloadOrder() throws {
        let keys = [
            "draftkings", "fanduel", "betmgm", "caesars", "betrivers", "bovada",
            "espnbet", "betonlineag", "lowvig", "fliff", "hardrockbet", "betus",
        ]
        let rows = try Self.rows(keys)
        XCTAssertEqual(rows.count, 10)
        XCTAssertEqual(rows.first?.label, "DraftKings")
        XCTAssertEqual(rows.last?.label, "Fliff")
        XCTAssertFalse(rows.contains { $0.label == "BetUS" })
    }

    // MARK: - What the row carries

    /// Payload order is the API's ranking; the list does not re-sort it.
    func testRowsKeepPayloadOrder() throws {
        XCTAssertEqual(
            try Self.rows(["lowvig", "draftkings", "betmgm"]).map(\.label),
            ["LowVig", "DraftKings", "BetMGM"])
    }

    /// #4406 REVERSES #4208's disposal of this row, and the reversal is the ship.
    ///
    /// #4208 left a priceless book its brand on the reasoning that "the reader
    /// learns the book is in the market". Photographed, that reasoning does not
    /// survive: on 15307197 it put twelve bare names under a heading promising
    /// sportsbooks, three of them consecutive, and a reader cannot tell that
    /// screen from a broken one. The width claim #4208 actually needed — that a
    /// numberless row contributes no string to the column — is preserved in the
    /// strongest possible form, because there is no such row to contribute one.
    ///
    /// Both halves of the pair are tested. `bookmakerProbabilities` needs BOTH
    /// sides, so a row with one is as priceless as a row with none, and a filter
    /// written as `away == nil` would keep the half-priced row and draw `43%`
    /// with nothing opposite it.
    func testARowMissingEitherSideIsNotDrawnAtAll() throws {
        for missing in ["home", "away"] {
            let json = missing == "home"
                ? Self.row("betmgm", home: nil)
                : Self.row("betmgm", away: nil)
            let rows = EventDetailView.namedBookmakerRows(try Self.bookmakers("[\(json)]"))
            XCTAssertTrue(
                rows.isEmpty,
                "a book quoting only the \(missing == "home" ? "away" : "home") side drew a row")
        }
    }

    /// A book that quoted nothing is not a row, and a payload of nothing but
    /// those is not a table — so `sourcesToggle` draws no heading over it, the
    /// same way it already refuses a payload of only unnameable keys.
    func testAPayloadOfOnlyPricelessBooksYieldsNoTable() throws {
        let json = ["draftkings", "fanduel", "betmgm"]
            .map { Self.row($0, away: nil, home: nil) }
            .joined(separator: ",")
        XCTAssertTrue(EventDetailView.namedBookmakerRows(try Self.bookmakers("[\(json)]")).isEmpty)
    }

    /// 🔴 THE SPECIMEN IN #4406, IN ITS OWN PAYLOAD ORDER, AT THE REAL CAP.
    ///
    /// `GET /api/events/15307197` (Angels 6 – Sox 1), read from production at
    /// 21:10Z on 2026-09-09: eighteen books, alphabetical, eleven of them `null`
    /// on both sides. This is the frame in the issue and it is the whole ship in
    /// one assertion — but note WHICH failure it is pinning.
    ///
    /// Six of the first ten quoted nothing. So the shipped order (name, cap at
    /// ten, then let the view skip the priceless) drew FOUR numbers, and LowVig,
    /// MyBookie and Rebet — positions 14, 15 and 16, all three carrying real
    /// prices — never reached the reader at all. Removing the empty rows without
    /// moving the filter above the cap would draw those same four and call it
    /// fixed. Seven is the number that proves the ordering.
    func testTheSpecimenDrawsSevenPricedBooksIncludingThreeThatWereBelowTheCap() throws {
        let payload = [
            ("ballybet", false), ("betanysports", true), ("betmgm", true),
            ("betonlineag", true), ("betparx", false), ("betrivers", false),
            ("betus", true), ("bovada", false), ("draftkings", false),
            ("espnbet", false), ("fanatics", false), ("fanduel", false),
            ("fliff", false), ("hardrockbet", false), ("lowvig", true),
            ("mybookieag", true), ("rebet", true), ("williamhill_us", false),
        ]
        let json = payload
            .map { key, priced in
                priced ? Self.row(key) : Self.row(key, away: nil, home: nil)
            }
            .joined(separator: ",")
        let rows = EventDetailView.namedBookmakerRows(try Self.bookmakers("[\(json)]"))

        XCTAssertEqual(
            rows.map(\.label),
            ["BetAnySports", "BetMGM", "BetOnline", "BetUS", "LowVig", "MyBookie", "Rebet"])
        // Said as the reader's own count, so a future change that drops the three
        // below the cap fails with the sentence rather than with an index.
        XCTAssertEqual(rows.count, 7, "the reader sees fewer numbers than the payload carries")
    }

    /// Two keys can share one brand — Caesars bought William Hill US, and the
    /// payload can carry both. The row's identity is the KEY, so `ForEach` does
    /// not collapse them into one row or animate them as the same row.
    func testTwoKeysSharingABrandStayTwoRows() throws {
        let rows = try Self.rows(["caesars", "williamhill_us"])
        XCTAssertEqual(rows.map(\.label), ["Caesars", "Caesars"])
        XCTAssertEqual(Set(rows.map(\.id)).count, 2)
    }

    /// A row with no `bookmaker` at all used to draw the word "Unknown".
    func testAMissingKeyDrawsNothingRatherThanTheWordUnknown() throws {
        let json = """
            [{"bookmaker": null, "away_probability": 0.49, "home_probability": 0.51, \
            "home_moneyline": null, "away_moneyline": null, "captured_at": null, \
            "spread": null, "over_under": null, "projected_home_score": null, \
            "projected_away_score": null}]
            """
        let rows = EventDetailView.namedBookmakerRows(try Self.bookmakers(json))
        XCTAssertTrue(rows.isEmpty)
        XCTAssertFalse(rows.contains { $0.label == "Unknown" })
    }
}
