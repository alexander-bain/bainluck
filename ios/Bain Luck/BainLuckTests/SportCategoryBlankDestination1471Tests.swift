import XCTest
@testable import Bain_Luck

/// #1471 / #6444 — a Discover card's destination must never be a blank page.
///
/// Alex's 2026-09-15 phone walkthrough: "Tapping into a UFC card brought up a
/// blank white screen, with no loading indicator of any kind. The screen
/// remained blank-white for +15 seconds… Tapping the golf card did the same."
///
/// Reproduced unattended on the iPhone 17 simulator at 19:33 PT the same day:
/// `bainluck://category/ufc` and `bainluck://category/golf` both render a large
/// title over white — no content, no spinner, no error, and NOT the view's own
/// "No UFC Right Now" empty state either.
///
/// That last part is the whole diagnosis. `SportCategoryView` has three honest
/// terminals (skeleton, error, empty) and picks the empty one on
/// `items.isEmpty`. Reaching none of them means `items` was NOT empty — the app
/// logged `Category ufc loaded: 9 items` — and every SECTION of `categoryList`
/// was. The sections are `liveNow` / `justHappened` / `upcoming` (all keyed on
/// `event`) and `topMarkets` (keyed on `futures`), so a payload of concepts and
/// tournaments falls through all four into an empty `List`, which draws as
/// white. The blank screen is a page that believes it has content.
///
/// Two independent contracts are pinned here, because either alone leaves the
/// reader on a white page:
///
///   1. Every supported sibling in a real mixed payload survives decode.
///   2. The view's section partition COVERS what decode admits — an item that
///      is neither event nor futures must still be placed, or the page must
///      fall to a terminal that says something.
final class SportCategoryBlankDestination1471Tests: XCTestCase {

    private func decoded() throws -> FeedResponse {
        let dec = JSONDecoder()
        dec.keyDecodingStrategy = .convertFromSnakeCase
        return try dec.decode(
            FeedResponse.self,
            data: Data(SportCategoryUFCFixture.json.utf8))
    }

    // MARK: - 1. Decode keeps every supported sibling

    /// `FeedResponse`'s item loop skips a throwing item SILENTLY. That
    /// tolerance is right — one malformed card must not blank the feed — but it
    /// means a shape regression costs cards with no error anywhere. This is the
    /// witness.
    func testEverySupportedSiblingSurvivesDecode() throws {
        let response = try decoded()
        let futures = response.items.filter { $0.futures != nil }
        let concepts = response.items.filter { $0.concept != nil }

        XCTAssertEqual(
            response.items.count, 7,
            "the captured payload holds 7 items; \(response.items.count) "
            + "decoded, so the skip loop ate "
            + "\(7 - response.items.count) of them")
        XCTAssertEqual(futures.count, 4, "all four futures must decode")
        XCTAssertEqual(concepts.count, 3, "all three concepts must decode")
    }

    /// A futures card is only useful if the fields the row draws survived with
    /// it. A decode that produces the right COUNT of husks passes the test
    /// above and still renders a blank row.
    func testDecodedFuturesCarryTheirRenderableFields() throws {
        let futures = try decoded().items.compactMap(\.futures)
        for f in futures {
            XCTAssertFalse(f.name.isEmpty, "market \(f.id) decoded a blank name")
            XCTAssertFalse(
                (f.topOutcomes ?? []).isEmpty,
                "market \(f.id) (\(f.name)) decoded with no outcomes — the row "
                + "would draw a title over empty space")
        }
    }

    // MARK: - 2. The section partition covers what decode admits

    /// Drives the REAL view model so the partition under test is the one the
    /// app runs, not a restatement of it in the test. `load()` is never called,
    /// so this touches no network.
    @MainActor
    private func model(_ items: [FeedItem]) -> SportCategoryViewModel {
        let vm = SportCategoryViewModel(categoryKey: "ufc")
        vm.setItemsForTesting(items)
        return vm
    }

    /// Every item the page holds must land in a section. A concept card landed
    /// in none of the four, which is how nine decoded items drew zero rows.
    @MainActor
    func testEveryDecodedItemIsPlacedBySomeSection() throws {
        let items = try decoded().items
        let vm = model(items)
        let placed = vm.liveNow.count + vm.justHappened.count
            + vm.upcoming.count + vm.topMarkets.count + vm.otherEvents.count
        XCTAssertEqual(
            placed, items.count,
            "\(items.count - placed) of \(items.count) items are in no section, "
            + "so the page renders an empty List over a title — Alex's blank "
            + "white screen")
    }

    /// The concepts specifically, since they are what the UFC page was left
    /// holding once the server's seen-filter had taken the futures.
    @MainActor
    func testConceptsLandInTheEventsSection() throws {
        let items = try decoded().items
        let vm = model(items)
        XCTAssertEqual(
            vm.otherEvents.filter { $0.concept != nil }.count, 3,
            "all three concepts must be placed by the Events section")
    }

    /// The futures must not have MOVED into the new section — a partition that
    /// places everything by putting it all in one bucket passes the test above
    /// and throws away the page's structure.
    @MainActor
    func testMarketsStayInTheMarketsSection() throws {
        let vm = model(try decoded().items)
        XCTAssertEqual(vm.topMarkets.count, 4)
        XCTAssertTrue(
            vm.otherEvents.allSatisfy { $0.futures == nil },
            "the Events section must not swallow markets")
    }

    /// The all-orphan case is the reader's worst one and the one he hit: a page
    /// whose entire payload the old sections could not place. It must now draw
    /// rows — and `drawsNoRows` must say so, since that is what stands between
    /// a future unplaceable type and another white page.
    @MainActor
    func testAnAllConceptPayloadStillDrawsRows() throws {
        let concepts = try decoded().items.filter { $0.concept != nil }
        XCTAssertFalse(concepts.isEmpty, "fixture must contain concepts")
        let vm = model(concepts)
        XCTAssertEqual(vm.otherEvents.count, concepts.count)
        XCTAssertFalse(
            vm.drawsNoRows,
            "a payload of \(concepts.count) concepts must draw \(concepts.count) "
            + "rows, not a blank page")
    }

    /// The honest terminal. An EMPTY payload must report that it draws nothing,
    /// so the view picks "No UFC Right Now" instead of an empty `List`.
    @MainActor
    func testAnEmptyPayloadReportsThatItDrawsNothing() {
        XCTAssertTrue(model([]).drawsNoRows)
    }
}

private extension JSONDecoder {
    /// Spelled out so the call site above reads as one statement.
    func decode<T: Decodable>(_ type: T.Type, data: Data) throws -> T {
        try decode(type, from: data)
    }
}
