import XCTest
@testable import Bain_Luck

/// #10090 — an already-open page keeps receiving folded previews when its
/// authoritative fold membership changes. The server composes a connection's
/// folded previews for the rows it opened with (`_fold_stream_ids`: membership
/// changes are picked up on reconnect), so the adopted detail is the authority:
/// a change withdraws the old fold's preview, closes that connection, and the
/// page's re-plan opens one on the new fold. Every origin fence and commit
/// floor the visit holds is kept (`BlendPreview.readerAfterMembership`).
@MainActor
final class AMembershipChangeReopensTheV1FoldedPreview10090Tests: XCTestCase {
    private static let id = 4242
    private static let oldFold = #"{"4242":10,"4243":20}"#
    private static let newFold = #"{"4242":10,"4244":30}"#

    private final class Handle: LiveStreamHandle, @unchecked Sendable {
        var isClosed = false
        var handlers: [String: [@MainActor (String) -> Void]] = [:]
        func on(_ event: String, _ handler: @escaping @MainActor (String) -> Void) {
            handlers[event, default: []].append(handler)
        }
        func close() { isClosed = true }
        func fire(_ event: String, _ data: String = "") {
            for handler in handlers[event] ?? [] { handler(data) }
        }
    }

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

    @MainActor private final class Handles { var all: [Handle] = [] }

    private static func detail(_ fold: String) throws -> EventDetail {
        let decoder = JSONDecoder()
        decoder.keyDecodingStrategy = .convertFromSnakeCase
        return try decoder.decode(EventDetail.self, from: Data("""
        {"id":\(id),"sport":"soccer_epl","home_team":"Home","away_team":"Away","status":"live",
         "home_score":1,"away_score":0,
         "current_odds":{"home_probability":0.5,"away_probability":0.25},
         "hero_probability":0.5,"hero_probability_away":0.25,"hero_probability_source":"blend",
         "hero_probability_observed_at":"2026-10-21T19:00:00Z","blend_fold_revision":\(fold),
         "win_probability_sources":{"kalshi":{"value":0.5,"updated_at":"2026-10-21T19:00:00Z"}}}
        """.utf8))
    }

    /// The backend's folded projection of one origin row's ledger frame: the
    /// removed row 4243 composes on `oldFold`, the joining row 4244 on `newFold`.
    private static func preview(origin: Int, epoch: Int, seq: Int, p: Double = 0.65) -> String {
        let (fold, rev) = origin == 4243 ? (oldFold, 20) : (newFold, 30)
        return """
        {"event_id":\(id),"p":\(p),"p_away":0.2,"sport":"soccer_epl","status":"live","source":"kalshi",
         "source_value":\(p),"display_observed_at":"2026-10-21T19:00:04+00:00","provisional":true,
         "preview":{"kind":"blend","epoch":\(epoch),"seq":\(seq),"base_rev":\(rev),"ttl_ms":60000,
                    "origin_event_id":\(origin),"folded_version":1,"base_fold_revision":\(fold)}}
        """
    }

    private func headline(_ vm: EventDetailViewModel) throws -> Double? {
        vm.headline(try XCTUnwrap(vm.event)).currentOdds?.homeProbability
    }

    /// #11564 (contract R2): a page reads v3 only, and a fold of two or more
    /// rows admits only folded v2. The v1 folded projection this file once
    /// drove through a membership change can no longer reach the page — neither
    /// as a legacy `preview` event nor wrapped in a v3 envelope — so the page
    /// shows committed truth throughout. The v1 reader rules themselves stay
    /// pinned at reader level (`FoldedBlendPreview10090Tests`).
    func testAV1FoldedProjectionNeverReachesAV3Page() async throws {
        let client = Client(page: try Self.detail(Self.oldFold))
        let handles = Handles()
        let vm = EventDetailViewModel(
            eventId: Self.id, client: client,
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
        let first = try XCTUnwrap(handles.all.last)
        let session = V3PageWire.nextSession()
        first.fire("open")
        first.fire("preview", Self.preview(origin: 4243, epoch: 900, seq: 1))
        XCTAssertEqual(try headline(vm), 0.5, "a legacy preview event is never read")
        first.fire("preview_open_v3", V3PageWire.open(Self.id, members: [4242, 4243], session: session))
        first.fire("preview_v3", V3PageWire.preview(Self.preview(origin: 4243, epoch: 900, seq: 2),
                                                    eventId: Self.id, session: session))
        XCTAssertEqual(try headline(vm), 0.5, "a v1 folded payload is refused on a v3 fold")
        XCTAssertNil(vm.blendPreview)

        // The membership change still reopens the stream, and the new fold
        // still refuses the v1 shape.
        client.page = try Self.detail(Self.newFold)
        await vm.load(fresh: false)
        XCTAssertTrue(first.isClosed)
        XCTAssertEqual(handles.all.count, 2)
        let second = try XCTUnwrap(handles.all.last)
        let next = V3PageWire.nextSession()
        second.fire("open")
        second.fire("preview_open_v3", V3PageWire.open(Self.id, members: [4242, 4244], session: next))
        second.fire("preview_v3", V3PageWire.preview(Self.preview(origin: 4244, epoch: 12, seq: 1, p: 0.7),
                                                     eventId: Self.id, session: next))
        XCTAssertEqual(try headline(vm), 0.5)
        XCTAssertEqual(vm.event?.currentOdds?.homeProbability, 0.5, "the committed event is untouched")
    }
}
