import XCTest
@testable import Bain_Luck

/// #10090 — an already-open page keeps receiving folded previews when its
/// authoritative combined-event membership changes. The adopted detail is the
/// membership authority: a change retires the old fold's preview authority
/// (`BlendPreview.readerAfterMembership`), closes the connection whose
/// server-side composition was bound to the old membership, and the page's
/// re-plan opens a new one for the new fold. Old-session and old-membership
/// packets on the new connection are refused; the new fold is shown.
///
/// Written by Fable against 882fc964 without an Xcode build: Native runs it.
@MainActor
final class AMembershipChangeReopensTheFoldedPreview10090Tests: XCTestCase {
    private static let id = 4242

    private final class Handle: LiveStreamHandle, @unchecked Sendable {
        private var handlers: [String: [@MainActor (String) -> Void]] = [:]
        var isClosed = false
        func on(_ event: String, _ handler: @escaping @MainActor (String) -> Void) {
            handlers[event, default: []].append(handler)
        }
        func close() { isClosed = true }
        @MainActor func fire(_ event: String, _ data: String = "") {
            for h in handlers[event] ?? [] { h(data) }
        }
    }

    /// `load()` reads `page`; every other section declines, as in the other
    /// held-page tests (an optional read that fails leaves the page intact).
    @MainActor private final class Client: EventDetailProviding {
        struct Declined: Error {}
        var page: EventDetail
        init(page: EventDetail) { self.page = page }
        func fetchEvent(id: Int) async throws -> EventDetail { page }
        func fetchEventHistory(id: Int, hours: Int) async throws -> EventHistoryResponse { throw Declined() }
        func fetchRelatedFutures(eventId: Int) async throws -> RelatedFuturesResponse { throw Declined() }
        func fetchTeamProgression(eventId: Int) async throws -> TeamProgressionResponse { throw Declined() }
        func fetchGameMarkets(eventId: Int) async throws -> GameMarketsResponse { throw Declined() }
        func fetchLineMovement(eventId: Int) async throws -> LineMovementResponse { throw Declined() }
    }

    private static func detail(revision: String) throws -> EventDetail {
        let decoder = JSONDecoder()
        decoder.keyDecodingStrategy = .convertFromSnakeCase
        return try decoder.decode(EventDetail.self, from: Data("""
        {"id":\(id),"sport":"soccer_epl","home_team":"Home","away_team":"Away","status":"live",
         "home_score":1,"away_score":0,
         "current_odds":{"home_probability":0.5,"away_probability":0.25},
         "hero_probability":0.5,"hero_probability_away":0.25,"hero_probability_source":"blend",
         "hero_probability_observed_at":"2026-10-21T19:00:00Z","blend_fold_revision":\(revision),
         "win_probability_sources":{"kalshi":{"value":0.5,"updated_at":"2026-10-21T19:00:00Z"}}}
        """.utf8))
    }

    private static func open(_ session: String) -> String {
        #"{"event_id":4242,"fold_session":"\#(session)"}"#
    }

    private static func pending(_ epoch: Int, _ seq: Int) -> String {
        #"{"epoch":\#(epoch),"seq":\#(seq),"state":"pending","ttl_ms":60000}"#
    }

    private static func snapshot(session: String, seq: Int, base: String, authority: String,
                                 p: Double = 0.65) -> String {
        """
        {"event_id":\(id),"p":\(p),"p_away":0.2,"sport":"soccer_epl","status":"live","provisional":true,
         "display_observed_at":"2026-10-21T19:00:04Z",
         "preview":{"kind":"blend","folded_version":2,"fold_session":"\(session)","fold_seq":\(seq),
                    "ttl_ms":60000,"base_fold_revision":\(base),"origin_authority":\(authority)}}
        """
    }

    private static let oldBase = #"{"4242":10,"4243":20}"#
    private static let newBase = #"{"4242":11,"4244":30}"#
    private static let oldAuthority = #"{"4242":\#(AMembershipChangeReopensTheFoldedPreview10090Tests.pending(100, 2)),"4243":\#(AMembershipChangeReopensTheFoldedPreview10090Tests.pending(2, 1))}"#
    private static let newAuthority = #"{"4242":\#(AMembershipChangeReopensTheFoldedPreview10090Tests.pending(100, 2)),"4244":\#(AMembershipChangeReopensTheFoldedPreview10090Tests.pending(7, 1))}"#

    /// Every connection the page opens, in order.
    @MainActor private final class Handles {
        var all: [Handle] = []
    }

    private func headline(_ vm: EventDetailViewModel) throws -> Double? {
        vm.headline(try XCTUnwrap(vm.event)).currentOdds?.homeProbability
    }

    func testTheAdoptedMembershipChangeReopensTheStreamOnTheNewFoldAndRefusesTheOld() async throws {
        let client = Client(page: try Self.detail(revision: Self.oldBase))
        let handles = Handles()
        let vm = EventDetailViewModel(
            eventId: Self.id,
            client: client,
            makeStreamHandle: { _ in
                let handle = Handle()
                handles.all.append(handle)
                return handle
            },
            now: { 1_760_000_000 },
            sleep: { _ in try? await Task.sleep(nanoseconds: 60_000_000_000) }
        )
        defer { vm.stopRefresh() }
        await vm.load()
        XCTAssertEqual(handles.all.count, 1, "the held page opened one stream")
        let first = try XCTUnwrap(handles.all.first)
        first.fire("open", Self.open("s1"))
        first.fire("preview", Self.snapshot(session: "s1", seq: 1, base: Self.oldBase, authority: Self.oldAuthority))
        XCTAssertEqual(try headline(vm), 0.65, "the 4242/4243 fold shows its pending blend")

        // The authoritative detail now folds 4242 with 4244 instead of 4243.
        client.page = try Self.detail(revision: Self.newBase)
        await vm.load(fresh: false)
        XCTAssertEqual(vm.event?.blendFoldRevision?.revision?.rows, ["4242": 11, "4244": 30], "the changed fold is adopted")
        XCTAssertNil(vm.blendPreview, "the old fold's preview is withdrawn")
        XCTAssertEqual(try headline(vm), 0.5)
        XCTAssertTrue(first.isClosed, "the connection composed on the old membership is closed")
        XCTAssertEqual(handles.all.count, 2, "and the page opened a new one for the new fold")
        let second = try XCTUnwrap(handles.all.last)

        // On the new connection: the old session and the old membership are refused.
        second.fire("open", Self.open("s2"))
        second.fire("preview", Self.snapshot(session: "s1", seq: 2, base: Self.newBase, authority: Self.newAuthority))
        XCTAssertNil(vm.blendPreview, "a packet of the old session is refused")
        second.fire("preview", Self.snapshot(session: "s2", seq: 1, base: Self.oldBase, authority: Self.oldAuthority))
        XCTAssertNil(vm.blendPreview, "a packet naming the removed member is refused")
        XCTAssertEqual(try headline(vm), 0.5)

        // The new fold is admitted on the same connection.
        second.fire("preview", Self.snapshot(session: "s2", seq: 2, base: Self.newBase, authority: Self.newAuthority, p: 0.7))
        XCTAssertEqual(try headline(vm), 0.7, "the already-open page shows the new fold's pending blend")
        XCTAssertEqual(vm.event?.currentOdds?.homeProbability, 0.5, "the committed event is untouched")

        // The same membership read again is not a change: the stream stays.
        await vm.load(fresh: false)
        XCTAssertEqual(handles.all.count, 2, "an unchanged membership keeps the connection")
        XCTAssertFalse(second.isClosed)
        XCTAssertEqual(try headline(vm), 0.7, "and the shown preview")
    }
}
