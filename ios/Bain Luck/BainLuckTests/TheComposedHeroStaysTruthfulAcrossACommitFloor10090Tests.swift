import XCTest
@testable import Bain_Luck

/// #10090 — #11772 (tenths, decision J) composed with #11777 (the folded
/// hero's floor hand-over); lane1's 0750Z review, live's 0830Z contract.
///
/// C1: a commit floor the shown paired revision does not cover means that
/// commit's value is owed, whether or not its raw frame or result has come.
/// `confirmed_at` vouches for the server's newest commit, never an older one
/// once a floor names it, so the page claims no confirmation until a result or
/// load covers every floor. Its age clock stays on the shown value's own.
///
/// C2: the hero's slide follows what it printed. A displayed preview of 70%
/// replaced by a committed 66% slides down even when the committed prior was
/// 50%, and the "↑16 pts" committed caption is withheld rather than shown on
/// a visible fall. Folded and singleton pages alike.
@MainActor
final class TheComposedHeroStaysTruthfulAcrossACommitFloor10090Tests: XCTestCase {
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
        @MainActor func beat(_ confirmed: String) {
            fire("heartbeat", #"{"t":"2026-10-21T19:01:00.000+00:00","confirmed_at":"\#(confirmed)"}"#)
        }
    }

    @MainActor private final class Client: EventDetailProviding {
        struct Declined: Error {}
        var page: EventDetail
        /// When set, the stream pair's history half (a connect reconcile's proof).
        var freshHistory: EventHistoryResponse?
        init(page: EventDetail) { self.page = page }
        func fetchEvent(id: Int) async throws -> EventDetail { page }
        func fetchEventHistory(id: Int, hours: Int) async throws -> EventHistoryResponse { throw Declined() }
        func fetchFreshEventHistory(id: Int, hours: Int) async throws -> EventHistoryResponse {
            guard let freshHistory else { throw Declined() }
            return freshHistory
        }
        func fetchRelatedFutures(eventId: Int) async throws -> RelatedFuturesResponse { throw Declined() }
        func fetchTeamProgression(eventId: Int) async throws -> TeamProgressionResponse { throw Declined() }
        func fetchGameMarkets(eventId: Int) async throws -> GameMarketsResponse { throw Declined() }
        func fetchLineMovement(eventId: Int) async throws -> LineMovementResponse { throw Declined() }
    }

    private final class Clock { var t: TimeInterval = 1_760_000_000 }

    private static func detail(revision: String, p: Double = 0.5) throws -> EventDetail {
        let decoder = JSONDecoder()
        decoder.keyDecodingStrategy = .convertFromSnakeCase
        return try decoder.decode(EventDetail.self, from: Data("""
        {"id":\(id),"sport":"soccer_epl","home_team":"Home","away_team":"Away","status":"live",
         "home_score":1,"away_score":0,
         "current_odds":{"home_probability":\(p),"away_probability":0.25},
         "hero_probability":\(p),"hero_probability_away":0.25,"hero_probability_source":"blend",
         "hero_probability_observed_at":"2026-10-21T19:00:00Z","blend_fold_revision":\(revision),
         "win_probability_sources":{"kalshi":{"value":\(p),"updated_at":"2026-10-21T19:00:00Z"}}}
        """.utf8))
    }

    private static func foldedPreview(p: Double) -> String {
        V3PageWire.preview("""
        {"event_id":\(id),"p":\(p),"p_away":0.2,"sport":"soccer_epl","status":"live","provisional":true,
         "display_observed_at":"2026-10-21T19:00:04Z",
         "preview":{"kind":"blend","folded_version":2,"fold_session":"\(session)","fold_seq":1,
                    "ttl_ms":60000,"base_fold_revision":\(folded),
                    "origin_authority":{"4242":{"epoch":100,"seq":2,"state":"pending","ttl_ms":60000},
                                        "4243":{"epoch":2,"seq":1,"state":"pending","ttl_ms":60000}}}}
        """, eventId: id, session: session)
    }

    /// The commit of row 4243 at revision 21, as the stream sends it.
    private static let floor = #"{"event_id":4242,"floor":{"4243":21}}"#
    private static let raw = #""event_id":4242,"p":0.9,"source":"polymarket","source_value":0.9,"updated_at":"2026-10-21T19:00:05Z","status":"live","rev":{"4243":21}"#
    private static func result(_ quote: String) -> String {
        "{\(raw),\"folded_quote_pending\":false,\"folded_quote\":\(quote)}"
    }
    /// That commit's combined result: 0.66, below a 0.70 preview and above
    /// the older committed 0.5.
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

    /// Production's connect: a `reconcile` naming the committed revision, paid
    /// by one covering pair. Then past the pair coalescer's window.
    private func reconcile(_ handle: Handle, _ client: Client, _ clock: Clock, _ vm: EventDetailViewModel,
                           floor: String = folded) async throws {
        let decoder = JSONDecoder()
        decoder.keyDecodingStrategy = .convertFromSnakeCase
        client.freshHistory = try decoder.decode(EventHistoryResponse.self, from: Data("""
        {"event_id":4242,"home_team":"Home","away_team":"Away","status":"live","history":[],
         "blend_edge_pinned":true,"blend_edge_fold_revision":\(floor),
         "blend_edge_observed_at":"2026-10-21T19:00:00Z",
         "aggregate_line":[{"timestamp":"2026-10-21T19:00:00Z","home_probability":0.5}]}
        """.utf8))
        handle.fire("reconcile", #"{"event_id":4242,"custody_id":"connect","removal_rev":\#(floor)}"#)
        await settle { vm.reconcileOwedSince == nil }
        XCTAssertNil(vm.reconcileOwedSince, "the connect reconcile is paid")
        client.freshHistory = nil
        clock.t += 2
    }

    private func settle(until condition: () -> Bool) async {
        for _ in 0..<400 where !condition() { await Task.yield() }
    }

    private func drain() async { for _ in 0..<200 { await Task.yield() } }

    private func shown(_ vm: EventDetailViewModel) throws -> EventDetail { try XCTUnwrap(vm.event) }

    private let committedClock = "2026-10-21T19:00:00Z".asDate!
    private let previewClock = "2026-10-21T19:00:04Z".asDate!
    private let t = "2026-10-21T19:00:10Z".asDate!
    private let tLater = "2026-10-21T19:00:20Z".asDate!

    // MARK: - C1

    /// Live's catching sequence (0830Z §4): a floor with no raw frame, the
    /// same confirmation repeated, a newer one, a null result — none dates the
    /// older value; the covering result does.
    func testAnUncoveredCommitFloorWithholdsEveryConfirmationUntilACoveringResult() async throws {
        let (client, handle, clock, vm) = try await loaded()
        defer { vm.stopRefresh() }
        try await reconcile(handle, client, clock, vm)
        handle.beat("2026-10-21T19:00:10.000+00:00")
        XCTAssertEqual(vm.confirmedAtCoveringShown(try shown(vm)), t, "control: the held {10, 20} is confirmed")
        XCTAssertEqual(vm.displayedProbabilityAgeClock(try shown(vm)), t)

        handle.fire("fold_preview_floor", Self.floor)
        XCTAssertNil(vm.confirmedAtCoveringShown(try shown(vm)), "a floor {4243: 21} the held 20 does not cover")
        XCTAssertNil(vm.displayedConfirmation(try shown(vm)))
        XCTAssertEqual(vm.displayedProbabilityAgeClock(try shown(vm)), committedClock, "its own observation")
        XCTAssertEqual(vm.liveUpdateStatus, .awaitingUpdate)

        handle.beat("2026-10-21T19:00:10.000+00:00")
        XCTAssertNil(vm.confirmedAtCoveringShown(try shown(vm)), "a repeat is not a re-confirmation")
        // #11772 R4: a quiet 100 s lapses delivery on the open socket, which
        // keeps its reconcile; the floor's debt survives the lapse too.
        for _ in 1...5 {
            clock.t += 20
            handle.beat("2026-10-21T19:00:10.000+00:00")
            vm.tickStream()
        }
        XCTAssertFalse(vm.streamDelivering, "the lapse")
        handle.beat("2026-10-21T19:00:10.000+00:00")
        XCTAssertNil(vm.confirmedAtCoveringShown(try shown(vm)), "the lapse does not pay the floor")
        XCTAssertEqual(vm.displayedProbabilityAgeClock(try shown(vm)), committedClock)
        handle.beat("2026-10-21T19:00:20.000+00:00")
        XCTAssertEqual(vm.streamConfirmedAt, tLater, "stored")
        XCTAssertNil(vm.confirmedAtCoveringShown(try shown(vm)), "a newer one dates the newer commit, not this value")

        handle.fire("folded_probability", Self.result("null"))
        await drain()
        XCTAssertEqual(vm.event?.blendFoldRevision?.revision?.rows, ["4242": 10, "4243": 20])
        XCTAssertNil(vm.confirmedAtCoveringShown(try shown(vm)), "a null result is not coverage")
        XCTAssertEqual(vm.displayedProbabilityAgeClock(try shown(vm)), committedClock)

        handle.fire("folded_probability", Self.result(Self.quote))
        await settle { vm.event?.blendFoldRevision?.revision?.rows == ["4242": 10, "4243": 21] }
        await drain()
        XCTAssertEqual(vm.event?.blendFoldRevision?.revision?.rows, ["4242": 10, "4243": 21])
        XCTAssertEqual(vm.confirmedAtCoveringShown(try shown(vm)), tLater, "the covering result resumes it")
        XCTAssertEqual(vm.displayedProbabilityAgeClock(try shown(vm)), tLater)
        XCTAssertEqual(vm.liveUpdateStatus, .live)
    }

    /// Strawman: a floor the shown revision already covers keeps the
    /// confirmation, so the gate does not suppress everything.
    func testACoveredFloorKeepsTheConfirmation() async throws {
        let (client, handle, clock, vm) = try await loaded()
        defer { vm.stopRefresh() }
        try await reconcile(handle, client, clock, vm)
        handle.beat("2026-10-21T19:00:10.000+00:00")
        handle.fire("fold_preview_floor", #"{"event_id":4242,"floor":{"4243":20}}"#)
        XCTAssertEqual(vm.confirmedAtCoveringShown(try shown(vm)), t)
        XCTAssertEqual(vm.liveUpdateStatus, .live)
    }

    /// The composed invariant (lane1 0750Z): while the hand-over keeps the
    /// published preview, no confirmation and the preview's own clock; at the
    /// cap nothing of the preview survives, and the still-uncovered floor
    /// keeps the confirmation off the older committed value (C1).
    func testTheHandoverPreviewIsNeverConfirmedAndTheCapLeavesTheFloorOwed() async throws {
        let (client, handle, clock, vm) = try await loaded()
        defer { vm.stopRefresh() }
        try await reconcile(handle, client, clock, vm)
        handle.fire("preview_v3", Self.foldedPreview(p: 0.7))
        handle.fire("fold_preview_floor", Self.floor)
        handle.beat("2026-10-21T19:00:10.000+00:00")
        XCTAssertTrue(vm.displaysPreview(try shown(vm)), "kept across the floor")
        XCTAssertEqual(vm.headline(try shown(vm)).currentOdds?.homeProbability, 0.7)
        XCTAssertNil(vm.confirmedAtCoveringShown(try shown(vm)))
        XCTAssertEqual(vm.displayedProbabilityAgeClock(try shown(vm)), previewClock, "the preview's own clock")

        clock.t += BlendPreview.commitFloorHandover
        XCTAssertFalse(vm.displaysPreview(try shown(vm)), "the cap ends it")
        XCTAssertEqual(vm.headline(try shown(vm)).currentOdds?.homeProbability, 0.5)
        XCTAssertNil(vm.confirmedAtCoveringShown(try shown(vm)), "the floor is still owed")
        XCTAssertEqual(vm.displayedProbabilityAgeClock(try shown(vm)), committedClock)
    }

    // MARK: - C2

    /// Folded: committed 50, preview 70 shown, floor (kept), result 66. The
    /// hero visibly goes 70 → 66: it slides down, and "↑16 pts" is withheld.
    func testAPreviewReplacedByALowerCommitSlidesDownAndWithholdsTheRisingCaption() async throws {
        let (_, handle, _, vm) = try await loaded()
        defer { vm.stopRefresh() }
        handle.fire("preview_v3", Self.foldedPreview(p: 0.7))
        handle.fire("fold_preview_floor", Self.floor)
        handle.fire("folded_probability", Self.result(Self.quote))
        await drain()
        XCTAssertEqual(vm.event?.currentOdds?.homeProbability, 0.66)
        XCTAssertFalse(vm.displaysPreview(try shown(vm)))
        let activity = try XCTUnwrap(vm.priceActivity)
        XCTAssertEqual(activity.previousHomePrinted, "70.0%", "what the hero printed before the commit")
        XCTAssertEqual(activity.homePrinted, "66.0%")
        XCTAssertEqual(activity.homeDelta, 16, "the committed whole points did move up")
        XCTAssertEqual(activity.homeRising, false, "70 → 66 slides down")
        XCTAssertNil(activity.homeCaptionDelta, "never \"↑16 pts\" on a visible fall")
    }

    /// Control: a preview below the commit (65 → 66) agrees with the
    /// committed move, so the slide rises and the caption stays.
    func testAPreviewReplacedByAHigherCommitKeepsTheCaption() async throws {
        let (_, handle, _, vm) = try await loaded()
        defer { vm.stopRefresh() }
        handle.fire("preview_v3", Self.foldedPreview(p: 0.65))
        handle.fire("fold_preview_floor", Self.floor)
        handle.fire("folded_probability", Self.result(Self.quote))
        await drain()
        let activity = try XCTUnwrap(vm.priceActivity)
        XCTAssertEqual(activity.previousHomePrinted, "65.0%")
        XCTAssertEqual(activity.homeRising, true)
        XCTAssertEqual(activity.homeCaptionDelta, 16)
    }

    /// Singleton: the committed revision passes the preview's base, so the
    /// display gate drops it while `blendPreview` stays set until its expiry
    /// task. The commit's slide must not read that leftover as "a preview is
    /// showing" (nil, which slides up).
    func testASingletonPreviewReplacedByALowerCommitSlidesDown() async throws {
        let (_, handle, _, vm) = try await loaded(revision: #"{"4242":10}"#, members: [4242])
        defer { vm.stopRefresh() }
        handle.fire("preview_v3", V3PageWire.preview("""
            {"event_id":\(Self.id),"p":0.7,"p_away":0.2,"sport":"soccer_epl","status":"live",
             "display_observed_at":"2026-10-21T19:00:04Z",
             "preview":{"kind":"blend","epoch":2,"seq":1,"base_rev":10,"ttl_ms":60000}}
            """, eventId: Self.id, session: Self.session))
        XCTAssertEqual(vm.headline(try shown(vm)).currentOdds?.homeProbability, 0.7)
        handle.fire("probability", #"{"event_id":4242,"p":0.66,"source":"kalshi","source_value":0.66,"updated_at":"2026-10-21T19:00:05Z","status":"live","rev":{"4242":11}}"#)
        await drain()
        XCTAssertEqual(vm.event?.currentOdds?.homeProbability, 0.66)
        XCTAssertNotNil(vm.blendPreview, "still set until its expiry task")
        XCTAssertFalse(vm.displaysPreview(try shown(vm)), "but no longer printed")
        let activity = try XCTUnwrap(vm.priceActivity)
        XCTAssertEqual(activity.previousHomePrinted, "70.0%")
        XCTAssertEqual(activity.homeRising, false)
        XCTAssertNil(activity.homeCaptionDelta)
    }

    /// The chart tip slides like the hero: nil while a preview prints, the
    /// printed committed direction otherwise.
    func testTheTipSlidesLikeTheHero() throws {
        let fall = LivePriceActivity(sequence: 1, receivedAt: Date(), homeProbability: 0.66,
                                     previousHomePercent: 70, previousAwayPercent: nil,
                                     homePercent: 66, awayPercent: nil,
                                     previousHomeLabel: "70%", previousAwayLabel: nil,
                                     homeLabel: "66%", awayLabel: nil,
                                     previousHomePrinted: "70.0%", homePrinted: "66.0%")
        XCTAssertEqual(OddsChartView.liveEdgeRising(fall, showsPreview: false), false)
        XCTAssertNil(OddsChartView.liveEdgeRising(fall, showsPreview: true), "a preview prints: no committed direction")
        let path = URL(fileURLWithPath: #filePath).deletingLastPathComponent().deletingLastPathComponent()
            .appendingPathComponent("Bain Luck/Views/EventDetailView.swift")
        let view = try String(contentsOf: path, encoding: .utf8)
        XCTAssertTrue(view.contains("liveEdgeShowsPreview: vm.displaysPreview(event),"))
    }

    /// The page reads them: the caption the withheld delta, the hero's slide
    /// the published display state (not merely a held `blendPreview`).
    func testThePageReadsTheCaptionDeltaAndTheDisplayedPreview() throws {
        let path = URL(fileURLWithPath: #filePath).deletingLastPathComponent().deletingLastPathComponent()
            .appendingPathComponent("Bain Luck/Views/EventDetailView.swift")
        let view = try String(contentsOf: path, encoding: .utf8)
        XCTAssertTrue(view.contains("guard let delta = vm.priceActivity?.homeCaptionDelta, delta != 0 else { return nil }"))
        XCTAssertFalse(view.contains("vm.priceActivity?.homeDelta"))
        XCTAssertTrue(view.contains("guard let event = vm.event, !vm.displaysPreview(event) else { return nil }"))
        XCTAssertFalse(view.contains("vm.blendPreview == nil"))
    }
}
