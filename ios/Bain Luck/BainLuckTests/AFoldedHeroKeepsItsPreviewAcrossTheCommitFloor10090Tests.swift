import XCTest
@testable import Bain_Luck

/// #10090 — on a page that folds two rows, a commit arrives as a floor, then
/// the row's raw frame (a promise), then the combined result. The floor used
/// to withdraw the shown preview at once, so for the ~30 ms until the result
/// the hero printed the OLDER committed value (hold C, build 92: 44 jumps back
/// in 3 minutes, up to 255 ms). The reader still takes the floor at once; the
/// hero keeps the shown value until the page decides the result, never past
/// its own lifetime nor `BlendPreview.commitFloorHandover`. Every other
/// withdrawal, a malformed floor and a singleton page are exactly as before.
@MainActor
final class AFoldedHeroKeepsItsPreviewAcrossTheCommitFloor10090Tests: XCTestCase {
    private static let id = 4242
    private static let session = "00000001-0000-4000-8000-000000000001"
    private static let folded = #"{"4242":10,"4243":20}"#

    private final class Handle: LiveStreamHandle, @unchecked Sendable {
        private var handlers: [String: [@MainActor (String) -> Void]] = [:]
        var isClosed = false
        func on(_ event: String, _ handler: @escaping @MainActor (String) -> Void) {
            handlers[event, default: []].append(handler)
        }
        func close() {}
        @MainActor func fire(_ event: String, _ data: String = "") {
            for h in handlers[event] ?? [] { h(data) }
        }
    }

    @MainActor private final class Client: EventDetailProviding {
        struct Declined: Error {}
        let page: EventDetail
        private(set) var eventFetches = 0
        init(page: EventDetail) { self.page = page }
        func fetchEvent(id: Int) async throws -> EventDetail { eventFetches += 1; return page }
        func fetchEventHistory(id: Int, hours: Int) async throws -> EventHistoryResponse { throw Declined() }
        func fetchRelatedFutures(eventId: Int) async throws -> RelatedFuturesResponse { throw Declined() }
        func fetchTeamProgression(eventId: Int) async throws -> TeamProgressionResponse { throw Declined() }
        func fetchGameMarkets(eventId: Int) async throws -> GameMarketsResponse { throw Declined() }
        func fetchLineMovement(eventId: Int) async throws -> LineMovementResponse { throw Declined() }
    }

    private final class Clock { var t: TimeInterval = 1_760_000_000 }

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

    private static func foldedPreview(seq: Int = 1, p: Double = 0.65) -> String {
        V3PageWire.preview("""
        {"event_id":\(id),"p":\(p),"p_away":0.2,"sport":"soccer_epl","status":"live","provisional":true,
         "display_observed_at":"2026-10-21T19:00:04Z",
         "preview":{"kind":"blend","folded_version":2,"fold_session":"\(session)","fold_seq":\(seq),
                    "ttl_ms":60000,"base_fold_revision":\(folded),
                    "origin_authority":{"4242":{"epoch":100,"seq":2,"state":"pending","ttl_ms":60000},
                                        "4243":{"epoch":2,"seq":1,"state":"pending","ttl_ms":60000}}}}
        """, eventId: id, session: session)
    }

    private static let foldedRevoke = V3PageWire.preview("""
        {"event_id":\(id),"p":null,
         "preview":{"kind":"revoke","folded_version":2,"fold_session":"\(session)","fold_seq":2,
                    "ttl_ms":0,"base_fold_revision":\(folded),
                    "origin_authority":{"4242":{"epoch":100,"seq":2,"state":"revoked"},
                                        "4243":{"epoch":2,"seq":1,"state":"revoked"}}}}
        """, eventId: id, session: session)

    /// The commit of row 4243 at revision 21, as the stream sends it.
    private static let floor = #"{"event_id":4242,"floor":{"4243":21}}"#
    private static let raw = #""event_id":4242,"p":0.9,"source":"polymarket","source_value":0.9,"updated_at":"2026-10-21T19:00:05Z","status":"live","rev":{"4243":21}"#
    private static let pending = "{\(raw),\"folded_quote_pending\":true}"
    private static func result(_ quote: String) -> String {
        "{\(raw),\"folded_quote_pending\":false,\"folded_quote\":\(quote)}"
    }
    /// The combined result of that commit: a value that differs from both the
    /// preview (0.65) and the older committed one (0.5).
    private static let quote = """
        {"event_id":4242,"hero_probability":0.66,"hero_probability_away":0.2,
         "hero_probability_source":"blend","hero_probability_observed_at":"2026-10-21T19:00:05Z",
         "blend_fold_revision":{"4242":10,"4243":21},
         "win_probability_sources":{"polymarket":{"value":0.66,"display_name":"Polymarket","type":"market","color":"#000","updated_at":"2026-10-21T19:00:05Z"}},
         "hero_sportsbook_count":null,"status":"live","sport":"soccer_epl","hero_settled_result":null}
        """

    private func loaded(revision: String = folded, members: [Int] = [4242, 4243])
        async throws -> (Client, Handle, Clock, EventDetailViewModel)
    {
        let client = Client(page: try Self.detail(revision: revision))
        let handle = Handle(), clock = Clock()
        let vm = EventDetailViewModel(eventId: Self.id, client: client, makeStreamHandle: { _ in handle },
                                      now: { clock.t },
                                      sleep: { _ in try? await Task.sleep(nanoseconds: 60_000_000_000) })
        await vm.load()
        handle.fire("open")
        handle.fire("preview_open_v3", V3PageWire.open(Self.id, members: members, session: Self.session))
        return (client, handle, clock, vm)
    }

    private func headline(_ vm: EventDetailViewModel) throws -> Double? {
        vm.headline(try XCTUnwrap(vm.event)).currentOdds?.homeProbability
    }

    private func drain() async { for _ in 0..<200 { await Task.yield() } }

    // MARK: - The hand-over

    func testFloorThenRawThenResultNeverPrintsThePreFloorValue() async throws {
        let (client, handle, clock, vm) = try await loaded()
        defer { vm.stopRefresh() }
        handle.fire("preview_v3", Self.foldedPreview())
        XCTAssertEqual(try headline(vm), 0.65, "the fold shows its pending blend")
        let fetches = client.eventFetches
        var printed: [Double?] = []

        handle.fire("fold_preview_floor", Self.floor)
        printed.append(try headline(vm))
        XCTAssertEqual(vm.blendPreview?.expiresAt, clock.t + BlendPreview.commitFloorHandover,
                       "kept no longer than the hand-over")
        handle.fire("probability", Self.pending)
        await drain()
        printed.append(try headline(vm))
        XCTAssertEqual(vm.event?.currentOdds?.homeProbability, 0.5, "the raw row is not the folded hero")
        handle.fire("folded_probability", Self.result(Self.quote))
        await drain()
        printed.append(try headline(vm))

        XCTAssertEqual(printed, [0.65, 0.65, 0.66], "preview → committed result, never the older 0.5 between")
        XCTAssertEqual(vm.event?.currentOdds?.homeProbability, 0.66)
        XCTAssertEqual(vm.event?.blendFoldRevision?.revision?.rows, ["4242": 10, "4243": 21])
        XCTAssertNil(vm.blendPreview, "the hand-over ends with the result")
        XCTAssertEqual(client.eventFetches, fetches, "and asks no read")
    }

    /// Control: the result never arrives. The hero still gives the preview up
    /// at the hand-over bound, and at its own lifetime when that is sooner.
    func testWithNoResultThePreviewEndsAtTheHandoverOrItsOwnLifetime() async throws {
        let (_, handle, clock, vm) = try await loaded()
        defer { vm.stopRefresh() }
        let t0 = clock.t
        handle.fire("preview_v3", Self.foldedPreview())
        XCTAssertEqual(vm.blendPreview?.expiresAt, t0 + 60)
        handle.fire("fold_preview_floor", Self.floor)
        clock.t = t0 + BlendPreview.commitFloorHandover - 0.001
        XCTAssertEqual(try headline(vm), 0.65)
        clock.t = t0 + BlendPreview.commitFloorHandover
        XCTAssertEqual(try headline(vm), 0.5, "the bound ends it with no result")

        let (_, late, lateClock, lateVM) = try await loaded()
        defer { lateVM.stopRefresh() }
        let t1 = lateClock.t
        late.fire("preview_v3", Self.foldedPreview())
        lateClock.t = t1 + 59.5
        late.fire("fold_preview_floor", Self.floor)
        XCTAssertEqual(lateVM.blendPreview?.expiresAt, t1 + 60, "never past the preview's own lifetime")
        XCTAssertEqual(try headline(lateVM), 0.65)
        lateClock.t = t1 + 60
        XCTAssertEqual(try headline(lateVM), 0.5)
    }

    /// Control: a result the page refuses (here an explicit null) ends the
    /// hand-over the moment it is decided; the existing read then runs.
    func testARefusedResultEndsTheHandoverAtOnce() async throws {
        let (client, handle, _, vm) = try await loaded()
        defer { vm.stopRefresh() }
        handle.fire("preview_v3", Self.foldedPreview())
        let fetches = client.eventFetches
        handle.fire("fold_preview_floor", Self.floor)
        handle.fire("probability", Self.pending)
        await drain()
        XCTAssertEqual(try headline(vm), 0.65)
        handle.fire("folded_probability", Self.result("null"))
        XCTAssertNil(vm.blendPreview)
        XCTAssertEqual(try headline(vm), 0.5)
        for _ in 0..<200 where client.eventFetches == fetches { await Task.yield() }
        XCTAssertEqual(client.eventFetches, fetches + 1, "the null result runs the read the raw frame skipped")
    }

    // MARK: - Immediate withdrawals, unchanged

    func testEveryOtherWithdrawalStillEndsThePreviewAtOnce() async throws {
        // A malformed floor for this page, with no hand-over to cover.
        do {
            let (_, handle, _, vm) = try await loaded()
            handle.fire("preview_v3", Self.foldedPreview())
            handle.fire("fold_preview_floor", "broken")
            XCTAssertNil(vm.blendPreview, "malformed floor")
            XCTAssertEqual(try headline(vm), 0.5)
            vm.stopRefresh()
        }
        // Inside a hand-over: a revoke, a malformed floor, the session ending.
        let during: [(String, (Handle) -> Void)] = [
            ("revoke", { $0.fire("preview_v3", Self.foldedRevoke) }),
            ("malformed floor", { $0.fire("fold_preview_floor", "broken") }),
            ("reconnect", { $0.fire("reconnect") }),
            ("new domain", { $0.fire("preview_open_v3", V3PageWire.open(Self.id, members: [4242, 4243],
                                                                       session: Self.session, incarnation: "2")) }),
        ]
        for (name, withdraw) in during {
            let (_, handle, _, vm) = try await loaded()
            handle.fire("preview_v3", Self.foldedPreview())
            handle.fire("fold_preview_floor", Self.floor)
            XCTAssertEqual(try headline(vm), 0.65, name)
            withdraw(handle)
            XCTAssertNil(vm.blendPreview, name)
            XCTAssertEqual(try headline(vm), 0.5, name)
            vm.stopRefresh()
        }
        // Another page's floor is ignored and keeps the hand-over.
        let (_, handle, _, vm) = try await loaded()
        defer { vm.stopRefresh() }
        handle.fire("preview_v3", Self.foldedPreview())
        handle.fire("fold_preview_floor", Self.floor)
        handle.fire("fold_preview_floor", #"{"event_id":9,"floor":{"9":99}}"#)
        XCTAssertEqual(try headline(vm), 0.65)
    }

    /// A newer preview during the hand-over replaces it as before.
    func testANewerPreviewDuringTheHandoverShowsAndEndsIt() async throws {
        let (_, handle, clock, vm) = try await loaded()
        defer { vm.stopRefresh() }
        handle.fire("preview_v3", Self.foldedPreview())
        handle.fire("fold_preview_floor", Self.floor)
        handle.fire("preview_v3", V3PageWire.preview("""
            {"event_id":\(Self.id),"p":0.7,"p_away":0.2,"sport":"soccer_epl","status":"live","provisional":true,
             "display_observed_at":"2026-10-21T19:00:06Z",
             "preview":{"kind":"blend","folded_version":2,"fold_session":"\(Self.session)","fold_seq":2,
                        "ttl_ms":60000,"base_fold_revision":{"4242":10,"4243":21},
                        "origin_authority":{"4242":{"epoch":100,"seq":2,"state":"pending","ttl_ms":60000},
                                            "4243":{"epoch":2,"seq":2,"state":"pending","ttl_ms":60000}}}}
            """, eventId: Self.id, session: Self.session))
        XCTAssertEqual(try headline(vm), 0.7)
        clock.t += BlendPreview.commitFloorHandover
        XCTAssertEqual(try headline(vm), 0.7, "on its own lifetime, not the hand-over's")
    }

    /// A page that folds one row is exactly as before: a floor orders its
    /// singleton preview through the display gate's `base_rev`, never through
    /// the reader, so no hand-over begins and its lifetime is untouched.
    func testASingletonPageTakesTheFloorAsBefore() async throws {
        let (_, handle, clock, vm) = try await loaded(revision: #"{"4242":10}"#, members: [4242])
        defer { vm.stopRefresh() }
        let t0 = clock.t
        handle.fire("preview_v3", V3PageWire.preview("""
            {"event_id":\(Self.id),"p":0.6,"p_away":0.4,"sport":"soccer_epl","status":"live",
             "display_observed_at":"2026-10-21T19:00:04Z",
             "preview":{"kind":"blend","epoch":2,"seq":1,"base_rev":10,"ttl_ms":60000}}
            """, eventId: Self.id, session: Self.session))
        XCTAssertEqual(try headline(vm), 0.6, "the singleton page shows its preview")
        handle.fire("fold_preview_floor", #"{"event_id":4242,"floor":{"4242":11}}"#)
        XCTAssertEqual(vm.blendPreview?.expiresAt, t0 + 60, "no hand-over cap on a singleton page")
        handle.fire("fold_preview_floor", "broken")
        XCTAssertNil(vm.blendPreview, "a malformed floor still withdraws at once")
        XCTAssertEqual(try headline(vm), 0.5)
    }
}
