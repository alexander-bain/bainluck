import XCTest
@testable import Bain_Luck

/// #5811 — the iPhone reader of `venue_closed_no_winner`.
///
/// THE SPECIMEN, photographed before the fix on 2026-09-30 (`artifacts/native-5811/`):
/// Erick Visconde v Ilias Bulaid, `15320964`, UFC, `status: suspended`, no score,
/// `venue_settled: false`, `venue_closed_no_winner: true` — Kalshi finalized both
/// fight markets as `scalar`. The MMA page filed it under **Live & Paused** and
/// the event hero's badge read **No result reported**. Web (#9828) reads
/// "Ended · no winner" and files it under Finished.
///
/// WHAT THIS FILE PROVES: the decode on all three doors, the predicate, and the
/// bucket every Sports/category/My Stuff section reads. The badge ORDER inside
/// SwiftUI bodies is `frontend/__tests__/ios/eventStatusSingleSource.test.ts`,
/// "#5811", which runs in CI.
@MainActor
final class VenueClosedNoWinner5811Tests: XCTestCase {

    /// Offset from a literal instant (gotcha #44).
    private static let now = Date(timeIntervalSince1970: 1_790_000_000)
    private static let started = "2026-09-20T23:15:00+00:00"   // before `now`
    private static let notYet = "2026-10-20T23:15:00+00:00"    // after `now`

    private static func decoder() -> JSONDecoder {
        let dec = JSONDecoder()
        dec.keyDecodingStrategy = .convertFromSnakeCase
        return dec
    }

    /// The feed item's wire shape, trimmed from the production payload.
    private func item(
        id: Int = 15320964, status: String = "suspended",
        commence: String = started, closedKey: String? = "true"
    ) throws -> FeedItem {
        let key = closedKey.map { #","venue_closed_no_winner":\#($0)"# } ?? ""
        return try Self.decoder().decode(FeedItem.self, from: Data("""
        {"type":"event","score":35,"data":{"id":\(id),"sport":"mma_mixed_martial_arts",
         "home_team":"Ilias Bulaid","away_team":"Erick Visconde",
         "commence_time":"\(commence)","status":"\(status)",
         "home_score":null,"away_score":null\(key)}}
        """.utf8))
    }

    private func section(_ item: FeedItem) -> EventState.Section {
        EventState.section(of: item.event, now: Self.now)
    }

    // MARK: - Decode, on every door that serves it

    func testTheFeedCardDecodesTheKeyAndAnAbsentKeyStaysNil() throws {
        XCTAssertEqual(try item().event?.venueClosedNoWinner, true)
        XCTAssertNil(try item(closedKey: nil).event?.venueClosedNoWinner,
                     "present only when true — absent is not a false")
    }

    func testTheEventPageDecodesTheKey() throws {
        let event = try Self.decoder().decode(EventDetail.self, from: Data("""
        {"id":15320964,"home_team":"Ilias Bulaid","away_team":"Erick Visconde",
         "status":"suspended","venue_settled":false,"venue_closed_no_winner":true}
        """.utf8))
        XCTAssertEqual(event.venueClosedNoWinner, true)
        XCTAssertEqual(event.venueSettled, false)
    }

    func testTheSearchRowDecodesTheKey() throws {
        let row = try Self.decoder().decode(SearchEvent.self, from: Data("""
        {"id":15320964,"home_team":"Ilias Bulaid","away_team":"Erick Visconde",
         "status":"suspended","venue_closed_no_winner":true}
        """.utf8))
        XCTAssertEqual(row.venueClosedNoWinner, true)
    }

    // MARK: - The predicate

    private func shows(
        _ status: String?, settled: Bool? = false, closed: Bool? = true,
        commence: String? = started
    ) -> Bool {
        EventState.showsVenueClosedNoWinner(
            status, venueSettled: settled, venueClosedNoWinner: closed,
            commenceTime: commence?.asDate, now: Self.now)
    }

    func testTheSpecimenSaysItEnded() {
        XCTAssertTrue(shows("suspended"))
    }

    func testAPlayedScheduledRowGetsItTooLikeTheSettledVerdict() {
        XCTAssertTrue(shows("scheduled"))
    }

    func testAGradedWinnerOutranksIt() {
        XCTAssertFalse(shows("suspended", settled: true),
                       "web's rule: `venueSettledSummary` checks the winner first")
    }

    func testAbsentOrFalseKeyChangesNothing() {
        XCTAssertFalse(shows("suspended", closed: nil))
        XCTAssertFalse(shows("suspended", closed: false))
    }

    func testFinalLiveAndFutureRowsKeepTheirOwnBadge() {
        XCTAssertFalse(shows("completed"), "FINAL says it better")
        XCTAssertFalse(shows("live"), "a live row keeps its live badge")
        XCTAssertFalse(shows("suspended", commence: Self.notYet), "#4021: still pregame")
    }

    func testTheLabelIsTheWebOne() {
        XCTAssertEqual(EventState.venueClosedNoWinnerLabel, "Ended · no winner")
    }

    // MARK: - The bucket

    func testTheSpecimenFilesUnderFinishedNotLive() throws {
        XCTAssertEqual(section(try item()), .finished)
    }

    func testWithoutTheKeyASuspendedRowStaysInLiveAndPaused() throws {
        XCTAssertEqual(section(try item(closedKey: nil)), .live)
    }

    func testTheKeyCannotMoveALiveOrAFutureRow() throws {
        XCTAssertEqual(section(try item(status: "live")), .live)
        // A future-dated `suspended` row files where it always did (the bare
        // ladder is clock-blind) — the key must not be what moves it.
        XCTAssertEqual(section(try item(commence: Self.notYet)),
                       section(try item(commence: Self.notYet, closedKey: nil)))
        XCTAssertEqual(section(try item(status: "completed")), .finished)
    }

    func testTheCategoryPageMovesTheCardAndItsNeighbourStays() throws {
        let vm = SportCategoryViewModel(categoryKey: "mma_mixed_martial_arts")
        let ended = try item()
        let paused = try item(id: 15320966, closedKey: nil)
        vm.setItemsForTesting([paused, ended])
        XCTAssertEqual(vm.liveNow.map(\.event?.id), [15320966])
        XCTAssertEqual(vm.justHappened.map(\.event?.id), [15320964])
    }

    func testTheSportsTabFinishedBucketKeepsIt() throws {
        let rows = FeedViewModel.finishedSection(
            [try item(), try item(id: 15320966, closedKey: nil)],
            now: Self.now, reprieved: false)
        XCTAssertEqual(rows.map(\.event?.id), [15320964],
                       "a suspended row never ages out, so the ended fight is kept")
    }
}
