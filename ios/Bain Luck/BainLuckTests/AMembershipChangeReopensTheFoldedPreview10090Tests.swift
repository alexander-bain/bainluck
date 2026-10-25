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

    /// The same live page before the detail carries a blend: no fold
    /// membership to adopt yet.
    private static func detailWithoutBlend() throws -> EventDetail {
        let decoder = JSONDecoder()
        decoder.keyDecodingStrategy = .convertFromSnakeCase
        return try decoder.decode(EventDetail.self, from: Data("""
        {"id":\(id),"sport":"soccer_epl","home_team":"Home","away_team":"Away","status":"live",
         "home_score":1,"away_score":0,
         "current_odds":{"home_probability":0.5,"away_probability":0.25},
         "hero_probability":0.5,"hero_probability_away":0.25,"hero_probability_source":"kalshi",
         "hero_probability_observed_at":"2026-10-21T19:00:00Z",
         "win_probability_sources":{"kalshi":{"value":0.5,"updated_at":"2026-10-21T19:00:00Z"}}}
        """.utf8))
    }

    /// #11564: the v3 stream sessions, each a lowercase UUID the inner
    /// `fold_session` repeats.
    private static let s1 = "00000001-0000-4000-8000-000000000001"
    private static let s2 = "00000002-0000-4000-8000-000000000002"
    private static let s3 = "00000003-0000-4000-8000-000000000003"
    private static let s4 = "00000004-0000-4000-8000-000000000004"

    @MainActor private static func open(_ handle: Handle, _ session: String, members: [Int]) {
        handle.fire("open")
        handle.fire("preview_open_v3", V3PageWire.open(id, members: members, session: session))
    }

    @MainActor private static func preview(_ handle: Handle, _ session: String, _ snapshot: String) {
        handle.fire("preview_v3", V3PageWire.preview(snapshot, eventId: id, session: session))
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

    /// The page's clock, moved by the test.
    private final class Clock { var t: TimeInterval = 1_760_000_000 }

    private static func authority(_ rows: [Int: (epoch: Int, seq: Int)]) -> String {
        "{" + rows.sorted { $0.key < $1.key }
            .map { "\"\($0.key)\":\(pending($0.value.epoch, $0.value.seq))" }
            .joined(separator: ",") + "}"
    }

    private static func base(_ rows: [Int: Int]) -> String {
        "{" + rows.sorted { $0.key < $1.key }.map { "\"\($0.key)\":\($0.value)" }.joined(separator: ",") + "}"
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
        Self.open(first, Self.s1, members: [4242, 4243])
        Self.preview(first, Self.s1, Self.snapshot(session: Self.s1, seq: 1, base: Self.oldBase, authority: Self.oldAuthority))
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
        Self.open(second, Self.s2, members: [4242, 4244])
        Self.preview(second, Self.s1, Self.snapshot(session: Self.s1, seq: 2, base: Self.newBase, authority: Self.newAuthority))
        XCTAssertNil(vm.blendPreview, "a packet of the old session is refused")
        Self.preview(second, Self.s2, Self.snapshot(session: Self.s2, seq: 1, base: Self.oldBase, authority: Self.oldAuthority))
        XCTAssertNil(vm.blendPreview, "a packet naming the removed member is refused")
        XCTAssertEqual(try headline(vm), 0.5)

        // The new fold is admitted on the same connection.
        Self.preview(second, Self.s2, Self.snapshot(session: Self.s2, seq: 2, base: Self.newBase, authority: Self.newAuthority, p: 0.7))
        XCTAssertEqual(try headline(vm), 0.7, "the already-open page shows the new fold's pending blend")
        XCTAssertEqual(vm.event?.currentOdds?.homeProbability, 0.5, "the committed event is untouched")

        // The same membership read again is not a change: the stream stays.
        await vm.load(fresh: false)
        XCTAssertEqual(handles.all.count, 2, "an unchanged membership keeps the connection")
        XCTAssertFalse(second.isClosed)
        XCTAssertEqual(try headline(vm), 0.7, "and the shown preview")
    }

    /// lane1b R1 on cb9a5e47d1: the stream opens on a live page whatever its
    /// hero, so its one `preview_open_v3` can arrive before the detail names
    /// any membership. That open is refused and never replayed; the first
    /// membership the page adopts is not a change, so the refusal itself
    /// closes the connection and the re-plan opens one whose open is admitted.
    /// Without it the page shows no preview until the connection ends.
    func testAnOpenRefusedBeforeTheFirstMembershipReopensTheStreamWhenOneIsAdopted() async throws {
        let client = Client(page: try Self.detailWithoutBlend())
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
        XCTAssertEqual(handles.all.count, 1, "the live page opened a stream before any blend")
        let first = try XCTUnwrap(handles.all.first)
        Self.open(first, Self.s1, members: [4242, 4243])
        Self.preview(first, Self.s1, Self.snapshot(session: Self.s1, seq: 1, base: Self.oldBase, authority: Self.oldAuthority))
        XCTAssertNil(vm.blendPreview, "an open before any membership activates no session")
        XCTAssertEqual(try headline(vm), 0.5)

        // A poll adopts the first blend: the refused connection is closed and a new one opened.
        client.page = try Self.detail(revision: Self.oldBase)
        await vm.load(fresh: false)
        XCTAssertEqual(vm.event?.blendFoldRevision?.revision?.rows, ["4242": 10, "4243": 20])
        XCTAssertTrue(first.isClosed, "the connection whose open was refused is closed")
        XCTAssertEqual(handles.all.count, 2, "and the page opened a new one")
        let second = try XCTUnwrap(handles.all.last)
        Self.preview(second, Self.s1, Self.snapshot(session: Self.s1, seq: 2, base: Self.oldBase, authority: Self.oldAuthority))
        XCTAssertNil(vm.blendPreview, "the refused open is never replayed")

        Self.open(second, Self.s2, members: [4242, 4243])
        Self.preview(second, Self.s2, Self.snapshot(session: Self.s2, seq: 1, base: Self.oldBase, authority: Self.oldAuthority))
        XCTAssertEqual(try headline(vm), 0.65, "the new connection's open is admitted and its preview shows")

        // It reopens once: the same membership read again keeps the connection.
        await vm.load(fresh: false)
        XCTAssertEqual(handles.all.count, 2)
        XCTAssertFalse(second.isClosed)
        XCTAssertEqual(try headline(vm), 0.65)
    }

    /// lane1b R2 on cb9a5e47d1: the v1 page file's flap leg, in v3 envelopes
    /// with folded v2. A cached detail flaps the membership back and the fresh
    /// one returns; every reopen is the SAME v3 domain under a new session, so
    /// each row's fence, first-seen deadline and commit floor cross the flap
    /// (`readerAfterMembership`'s retired evidence, kept by the same-domain
    /// open): a returning row's tuple gets no new lease, its kept floor
    /// withholds an uncovered base, and its older identity stays fenced.
    func testAMembershipFlapAcrossSameDomainReopensKeepsEveryRowsEvidence() async throws {
        let ab = [4242: 10, 4243: 20]
        let ac = [4242: 10, 4244: 30]
        let client = Client(page: try Self.detail(revision: Self.base(ab)))
        let handles = Handles()
        let clock = Clock()
        let t0 = clock.t
        let vm = EventDetailViewModel(
            eventId: Self.id,
            client: client,
            makeStreamHandle: { _ in
                let handle = Handle()
                handles.all.append(handle)
                return handle
            },
            now: { clock.t },
            sleep: { _ in try? await Task.sleep(nanoseconds: 60_000_000_000) }
        )
        defer { vm.stopRefresh() }
        func show(_ handle: Handle, _ session: String, seq: Int, base: [Int: Int],
                  _ authority: [Int: (epoch: Int, seq: Int)], p: Double = 0.65) {
            Self.preview(handle, session, Self.snapshot(session: session, seq: seq, base: Self.base(base),
                                                        authority: Self.authority(authority), p: p))
        }
        await vm.load()
        let first = try XCTUnwrap(handles.all.last)
        Self.open(first, Self.s1, members: [4242, 4243])
        show(first, Self.s1, seq: 1, base: ab, [4242: (100, 2), 4243: (2, 1)])
        XCTAssertEqual(try headline(vm), 0.65, "the 4242/4243 fold shows its pending blend")
        XCTAssertEqual(vm.blendPreview?.expiresAt, t0 + 60)
        // A commit of the row about to leave: the parent withheld every later fold on it.
        first.fire("fold_preview_floor", #"{"event_id":4242,"floor":{"4243":21}}"#)
        XCTAssertNil(vm.blendPreview)
        XCTAssertEqual(try headline(vm), 0.5)

        // The authoritative detail now folds 4242 with 4244 instead of 4243.
        clock.t = t0 + 10
        client.page = try Self.detail(revision: Self.base(ac))
        await vm.load(fresh: false)
        XCTAssertEqual(handles.all.count, 2)
        let second = try XCTUnwrap(handles.all.last)
        Self.open(second, Self.s2, members: [4242, 4244])
        show(second, Self.s2, seq: 1, base: ac, [4242: (100, 2), 4244: (7, 1)], p: 0.7)
        XCTAssertEqual(try headline(vm), 0.7, "the already-open page shows the new fold's pending blend")

        // A cached detail flips back to the old fold: the same domain reopens under a new session.
        clock.t = t0 + 20
        client.page = try Self.detail(revision: Self.base(ab))
        await vm.load(fresh: false)
        XCTAssertEqual(vm.event?.blendFoldRevision?.revision?.rows, ["4242": 10, "4243": 20])
        XCTAssertTrue(second.isClosed)
        XCTAssertEqual(handles.all.count, 3)
        let third = try XCTUnwrap(handles.all.last)
        Self.open(third, Self.s3, members: [4242, 4243])
        show(third, Self.s3, seq: 1, base: ab, [4242: (100, 2), 4243: (2, 1)])
        XCTAssertNil(vm.blendPreview, "the returned row's kept commit floor withholds an uncovered base")
        show(third, Self.s3, seq: 2, base: [4242: 10, 4243: 21], [4242: (100, 2), 4243: (2, 0)])
        XCTAssertNil(vm.blendPreview, "the returned row's older identity stays fenced")
        show(third, Self.s3, seq: 3, base: [4242: 10, 4243: 21], [4242: (100, 2), 4243: (2, 1)], p: 0.66)
        XCTAssertEqual(try headline(vm), 0.66, "its same tuple over a covered base continues")
        XCTAssertEqual(vm.blendPreview?.expiresAt, t0 + 60, "under the deadline it was first seen with: no new lease")
        clock.t = t0 + 61
        XCTAssertEqual(try headline(vm), 0.5, "and it ends there, not renewed by the flap")

        // The fresh detail returns: 4244 gets its evidence back the same way.
        clock.t = t0 + 62
        client.page = try Self.detail(revision: Self.base(ac))
        await vm.load(fresh: false)
        XCTAssertTrue(third.isClosed)
        XCTAssertEqual(handles.all.count, 4)
        let fourth = try XCTUnwrap(handles.all.last)
        Self.open(fourth, Self.s4, members: [4242, 4244])
        show(fourth, Self.s4, seq: 1, base: ac, [4242: (100, 3), 4244: (7, 0)], p: 0.7)
        XCTAssertNil(vm.blendPreview, "the replayed older identity stays fenced across the flap")
        show(fourth, Self.s4, seq: 2, base: ac, [4242: (100, 3), 4244: (7, 1)], p: 0.7)
        XCTAssertEqual(try headline(vm), 0.7)
        XCTAssertEqual(vm.blendPreview?.expiresAt, t0 + 70, "4244's same tuple keeps its first-seen deadline across two flaps")
        show(fourth, Self.s4, seq: 3, base: ac, [4242: (100, 3), 4244: (7, 2)], p: 0.72)
        XCTAssertEqual(try headline(vm), 0.72, "a newer tuple of the row still leads")
        XCTAssertEqual(vm.blendPreview?.expiresAt, t0 + 122)
        XCTAssertEqual(vm.event?.currentOdds?.homeProbability, 0.5, "the committed event is untouched")
    }
}
