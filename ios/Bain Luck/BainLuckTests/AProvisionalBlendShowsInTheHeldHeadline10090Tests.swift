import XCTest
@testable import Bain_Luck

/// #10090 — the iPhone reader half of display-before-persist, ported from web's
/// `frontend/__tests__/blendPreview.test.ts` (accepted e8259f0). A provisional
/// blend overlays the hero only while no newer committed revision exists, is
/// fenced by a monotonic epoch floor, orders by seq within an epoch, is
/// withdrawn by revoke, expires, is cleared on reconnect and at the end of the
/// match, and never reaches `onFrame`, the committed `event`, the stored chart
/// history or the delivery clock.
@MainActor
final class AProvisionalBlendShowsInTheHeldHeadline10090Tests: XCTestCase {
    private static let id = 4242

    // MARK: - Frames

    private static func blendJSON(_ seq: Int, _ p: Double, epoch: Int = 1, base: Int = 10,
                                  ttl: Int = 60_000, status: String = "live", event: Int = id) -> String {
        """
        {"event_id":\(event),"p":\(p),"status":"\(status)","source":"kalshi","source_value":\(p),
         "observed_at":"2026-10-20T19:00:00+00:00","provisional":true,
         "preview":{"kind":"blend","epoch":\(epoch),"seq":\(seq),"base_rev":\(base),"ttl_ms":\(ttl),
                    "pending":{"kalshi":\(p)}}}
        """
    }

    private static func revokeJSON(_ seq: Int, through: Int, epoch: Int = 1) -> String {
        """
        {"event_id":\(id),"p":null,"status":"live","provisional":true,
         "preview":{"kind":"revoke","epoch":\(epoch),"seq":\(seq),"through_seq":\(through),"reason":"stale"}}
        """
    }

    private static func blend(_ seq: Int, _ p: Double, epoch: Int = 1, base: Int = 10,
                              ttl: Int = 60_000, status: String = "live", event: Int = id) -> BlendPreviewFrame {
        BlendPreviewFrame(eventId: event, p: p, status: status, kind: .blend, epoch: epoch, seq: seq,
                          baseRev: base, ttlMs: ttl)
    }

    private static func revoke(_ seq: Int, through: Int, epoch: Int = 1) -> BlendPreviewFrame {
        BlendPreviewFrame(eventId: id, p: nil, status: "live", kind: .revoke, epoch: epoch, seq: seq,
                          throughSeq: through)
    }

    private static func detail(rev: String? = #"{"4242":10}"#, p: Double = 0.6, status: String = "live",
                               heroSource: String = "blend", away: Bool = true) throws -> EventDetail {
        let revision = rev.map { #","blend_fold_revision":\#($0)"# } ?? ""
        let awaySide = away ? #","away_probability":\#(1 - p)"# : ""
        let decoder = JSONDecoder()
        decoder.keyDecodingStrategy = .convertFromSnakeCase
        return try decoder.decode(EventDetail.self, from: Data("""
        {"id":\(id),"sport":"americanfootball_nfl","home_team":"Home","away_team":"Away","status":"\(status)",
         "home_score":7,"away_score":3,
         "current_odds":{"home_probability":\(p)\(awaySide),"home_rendered_percent":60,"away_rendered_percent":40},
         "hero_probability":\(p),"hero_probability_source":"\(heroSource)",
         "hero_probability_observed_at":"2026-10-20T19:00:00Z"\(revision),
         "win_probability_sources":{"kalshi":{"value":0.6,"updated_at":"2026-10-20T19:00:00Z"},
                                    "polymarket":{"value":0.6,"updated_at":"2026-10-20T19:00:00Z"}}}
        """.utf8))
    }

    private func apply(_ state: BlendPreviewState?, _ frame: BlendPreviewFrame, now: TimeInterval = 0) -> BlendPreviewState? {
        BlendPreview.previewAfter(state, frame, eventId: Self.id, now: now)
    }

    private func read(_ reader: BlendPreviewReader, _ frame: BlendPreviewFrame, now: TimeInterval = 0) -> BlendPreviewReader {
        BlendPreview.readerAfter(reader, frame, eventId: Self.id, now: now)
    }

    // MARK: - Decode refuses what is not a provisional frame

    func testAFrameCarryingACommittedRevisionIsRefused() {
        let withRev = Self.blendJSON(1, 0.7).replacingOccurrences(of: #""provisional":true"#,
                                                                    with: #""provisional":true,"rev":{"4242":11}"#)
        XCTAssertNil(BlendPreviewFrame.decode(withRev))
        XCTAssertNotNil(BlendPreviewFrame.decode(Self.blendJSON(1, 0.7)), "control: the same frame without rev decodes")
    }

    func testMalformedPreviewsAreRefusedAndWellFormedOnesDecode() {
        let good = Self.blendJSON(1, 0.7)
        XCTAssertEqual(BlendPreviewFrame.decode(good), Self.blend(1, 0.7))
        XCTAssertNil(BlendPreviewFrame.decode(good.replacingOccurrences(of: #""epoch":1"#, with: #""epoch":"e1""#)))
        XCTAssertNil(BlendPreviewFrame.decode(good.replacingOccurrences(of: #""epoch":1"#, with: #""epoch":1.5"#)))
        XCTAssertNil(BlendPreviewFrame.decode(good.replacingOccurrences(of: #""base_rev":10,"#, with: "")))
        XCTAssertNil(BlendPreviewFrame.decode(good.replacingOccurrences(of: #""ttl_ms":60000,"#, with: "")))
        XCTAssertNil(BlendPreviewFrame.decode(Self.blendJSON(1, 1.2)))
        XCTAssertNil(BlendPreviewFrame.decode(Self.blendJSON(-1, 0.7)))
        XCTAssertNil(BlendPreviewFrame.decode(good.replacingOccurrences(of: #""kind":"blend""#, with: #""kind":"commit""#)))
        XCTAssertNil(BlendPreviewFrame.decode(Self.revokeJSON(2, through: 1).replacingOccurrences(of: #""through_seq":1,"#, with: "")))
        XCTAssertEqual(BlendPreviewFrame.decode(Self.revokeJSON(2, through: 1)), Self.revoke(2, through: 1))
        let padded = good.replacingOccurrences(of: #""pending":{"kalshi":0.7}"#,
                                  with: #""pending":{"kalshi":0.7},"pad":""# + String(repeating: "x", count: 17_000) + "\"")
        XCTAssertNil(BlendPreviewFrame.decode(padded), "past the client's frame bound")
    }

    // MARK: - Ordering and correction

    func testAPreviewShowsOverTheCommittedValueWhileItsBaseIsCurrent() throws {
        let state = apply(nil, Self.blend(1, 0.7))
        let held = try Self.detail()
        XCTAssertEqual(BlendPreview.displayed(state, held: held, now: 0), 0.7)
        let shown = BlendPreview.overlay(held, state, now: 0)
        XCTAssertEqual(shown.currentOdds?.homeProbability, 0.7)
        XCTAssertEqual(try XCTUnwrap(shown.currentOdds?.awayProbability), 0.3, accuracy: 1e-9)
        XCTAssertNil(shown.currentOdds?.homeRenderedPercent, "the served whole percents describe the committed pair")
        XCTAssertNil(shown.currentOdds?.awayRenderedPercent)
        XCTAssertEqual(shown.heroProbability, 0.7)
        XCTAssertEqual(shown.blendFoldRevision, held.blendFoldRevision, "a preview has no revision of its own")
        XCTAssertEqual(shown.heroProbabilityObservedAt, held.heroProbabilityObservedAt, "nor a clock")
    }

    func testANewerCommittedRevisionWinsAnOlderOrEqualOneDoesNot() throws {
        let state = apply(nil, Self.blend(1, 0.7, base: 10))
        XCTAssertNil(BlendPreview.displayed(state, held: try Self.detail(rev: #"{"4242":11}"#), now: 0))
        XCTAssertEqual(BlendPreview.displayed(state, held: try Self.detail(rev: #"{"4242":9}"#), now: 0), 0.7)
        XCTAssertEqual(BlendPreview.displayed(state, held: try Self.detail(rev: #"{"4242":10}"#), now: 0), 0.7)
    }

    func testADelayedLowerSeqNeverReplacesAHigherOneInTheSameEpoch() throws {
        var state = apply(nil, Self.blend(5, 0.72))
        state = apply(state, Self.blend(4, 0.65))
        state = apply(state, Self.blend(5, 0.61))
        XCTAssertEqual(BlendPreview.displayed(state, held: try Self.detail(), now: 0), 0.72)
    }

    func testARecomposedPreviewOnTheNewBaseSurvivesTheCommitThatRetiredTheOldOne() throws {
        var state = apply(nil, Self.blend(1, 0.7, base: 10))
        XCTAssertNil(BlendPreview.displayed(state, held: try Self.detail(rev: #"{"4242":11}"#), now: 0))
        state = apply(state, Self.blend(2, 0.71, base: 11))
        XCTAssertEqual(BlendPreview.displayed(state, held: try Self.detail(rev: #"{"4242":11}"#), now: 0), 0.71)
    }

    func testRevokeWithdrawsPreviewsUpToThroughSeqOnly() throws {
        var state = apply(nil, Self.blend(3, 0.7))
        XCTAssertEqual(apply(state, Self.revoke(4, through: 2)), state)
        state = apply(state, Self.revoke(4, through: 3))
        XCTAssertNil(state)
        XCTAssertEqual(BlendPreview.overlay(try Self.detail(), state, now: 0).currentOdds?.homeProbability, 0.6)
    }

    // MARK: - Epoch fence: an earlier worker never regains the display

    func testAReplacementEpochVoidsTheOldPreviewWhateverItsSeq() throws {
        var reader = read(.empty, Self.blend(90, 0.7, epoch: 4))
        reader = read(reader, Self.blend(1, 0.66, epoch: 5))
        XCTAssertEqual(reader.epoch, 5)
        XCTAssertEqual(BlendPreview.displayed(reader.held, held: try Self.detail(), now: 0), 0.66)
        let old = read(.empty, Self.blend(90, 0.7, epoch: 4))
        let voided = read(old, Self.revoke(1, through: 0, epoch: 5))
        XCTAssertNil(voided.held)
        XCTAssertEqual(voided.epoch, 5)
    }

    func testAnOldEpochBlendArrivingAfterTheReplacementSpokeIsRefused() throws {
        var reader = read(.empty, Self.blend(1, 0.66, epoch: 5))
        let after = read(reader, Self.blend(91, 0.7, epoch: 4))
        XCTAssertEqual(after, reader)
        XCTAssertEqual(BlendPreview.displayed(after.held, held: try Self.detail(), now: 0), 0.66)
        // Even with nothing held (the replacement revoked its own), the floor stays.
        reader = read(reader, Self.revoke(2, through: 1, epoch: 5))
        XCTAssertNil(reader.held)
        XCTAssertEqual(reader.epoch, 5)
        XCTAssertEqual(read(reader, Self.blend(92, 0.71, epoch: 4)), reader)
    }

    func testAnOldEpochsRevokeCannotTakeDownTheReplacementsPreview() {
        let reader = read(.empty, Self.blend(1, 0.66, epoch: 5))
        XCTAssertEqual(read(reader, Self.revoke(99, through: 98, epoch: 4)), reader)
    }

    func testAnotherEventsFrameChangesNothing() {
        let reader = read(.empty, Self.blend(1, 0.66, epoch: 5))
        XCTAssertEqual(read(reader, Self.blend(2, 0.1, epoch: 9, event: 7)), reader)
    }

    // MARK: - Committed truth

    func testExpiryStatusFoldedUnversionedAndNonBlendHeroesShowCommittedTruth() throws {
        let state = apply(nil, Self.blend(1, 0.7, ttl: 1000), now: 5000)
        XCTAssertEqual(BlendPreview.displayed(state, held: try Self.detail(), now: 5000.999), 0.7)
        XCTAssertNil(BlendPreview.displayed(state, held: try Self.detail(), now: 5001))
        XCTAssertNil(BlendPreview.displayed(state, held: try Self.detail(status: "final"), now: 5000))
        XCTAssertNil(BlendPreview.displayed(state, held: try Self.detail(status: "scheduled"), now: 5000),
                     "a different quote status than the preview's")
        XCTAssertNil(BlendPreview.displayed(state, held: try Self.detail(rev: #"{"4242":10,"4243":4}"#), now: 5000))
        XCTAssertNil(BlendPreview.displayed(state, held: try Self.detail(rev: #"{"4243":4}"#), now: 5000),
                     "a singleton revision of some other row")
        XCTAssertNil(BlendPreview.displayed(state, held: try Self.detail(rev: nil), now: 5000))
        XCTAssertNil(BlendPreview.displayed(state, held: try Self.detail(heroSource: "opening"), now: 5000))
        let terminal = apply(nil, Self.blend(1, 0.7, status: "final"))
        XCTAssertNil(BlendPreview.displayed(terminal, held: try Self.detail(status: "final"), now: 0))
    }

    func testWithoutAPreviewTheEventIsUntouchedAndAWithheldAwayStaysWithheld() throws {
        let event = try Self.detail()
        let untouched = BlendPreview.overlay(event, nil, now: 0)
        XCTAssertEqual(untouched.currentOdds?.homeProbability, 0.6)
        XCTAssertEqual(untouched.currentOdds?.homeRenderedPercent, 60)
        let drawPriced = try Self.detail(away: false)
        let shown = BlendPreview.overlay(drawPriced, apply(nil, Self.blend(1, 0.7)), now: 0)
        XCTAssertEqual(shown.currentOdds?.homeProbability, 0.7)
        XCTAssertNil(shown.currentOdds?.awayProbability)
    }

    // MARK: - Stream controller seam

    private final class FakeHandle: LiveStreamHandle, @unchecked Sendable {
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

    func testAPreviewReachesOnPreviewNeverOnFrameAndRenewsNoClockOpenAndClosedResetIt() {
        var clock: TimeInterval = 1_000
        let handle = FakeHandle()
        var frames = 0
        var previews: [String] = []
        var delivering: [Bool] = []
        var resets = 0
        let controller = LiveStreamController(
            open: { handle }, now: { clock },
            onFrame: { _ in frames += 1 },
            onDeliveringChange: { delivering.append($0) },
            onPreview: { previews.append($0) },
            onPreviewReset: { resets += 1 },
            schedule: { _, _ in {} }
        )
        controller.start()
        handle.fire("open")
        XCTAssertEqual(resets, 1)
        XCTAssertEqual(delivering, [true])
        // Previews every 10 s past the 90 s data-silence budget: none renews it.
        for step in 1...10 {
            clock = 1_000 + Double(step) * 10
            handle.fire("preview", Self.blendJSON(step, 0.7))
            handle.fire("heartbeat")
        }
        XCTAssertEqual(previews.count, 10)
        XCTAssertEqual(frames, 0, "a preview is never a committed frame")
        XCTAssertEqual(delivering, [true], "a preview turns nothing on")
        controller.tick()
        XCTAssertEqual(delivering, [true, false], "the data-silence fallback still fires behind previews")
        handle.fire("closed")
        XCTAssertEqual(resets, 2)
        handle.fire("preview", Self.blendJSON(11, 0.7))
        XCTAssertEqual(previews.count, 10, "nothing after the stream ends")
    }

    // MARK: - The held page

    private struct LiveOnlyClient: EventDetailProviding {
        struct Declined: Error {}
        let event: EventDetail
        func fetchEvent(id: Int) async throws -> EventDetail { event }
        func fetchEventHistory(id: Int, hours: Int) async throws -> EventHistoryResponse { throw Declined() }
        func fetchRelatedFutures(eventId: Int) async throws -> RelatedFuturesResponse { throw Declined() }
        func fetchTeamProgression(eventId: Int) async throws -> TeamProgressionResponse { throw Declined() }
        func fetchGameMarkets(eventId: Int) async throws -> GameMarketsResponse { throw Declined() }
        func fetchLineMovement(eventId: Int) async throws -> LineMovementResponse { throw Declined() }
    }

    private final class Clock { var t: TimeInterval = 1_760_000_000 }

    private func heldPage(_ event: EventDetail? = nil) async throws -> (EventDetailViewModel, FakeHandle, Clock) {
        let handle = FakeHandle()
        let clock = Clock()
        let vm = EventDetailViewModel(
            eventId: Self.id,
            client: LiveOnlyClient(event: try event ?? Self.detail()),
            makeStreamHandle: { _ in handle },
            now: { clock.t },
            sleep: { _ in try? await Task.sleep(nanoseconds: 60_000_000_000) }
        )
        await vm.load()
        return (vm, handle, clock)
    }

    private func headline(_ vm: EventDetailViewModel) throws -> Double? {
        vm.headline(try XCTUnwrap(vm.event)).currentOdds?.homeProbability
    }

    private static func commit(_ rev: Int, _ p: Double, at: String = "2026-10-20T19:00:05Z") -> String {
        """
        {"event_id":\(id),"p":\(p),"source":"kalshi","source_value":\(p),"updated_at":"\(at)",
         "status":"live","rev":{"\(id)":\(rev)}}
        """
    }

    /// THE SHIP. The held page shows the accepted preview in its headline while
    /// the commit is still delayed — and nothing committed moves with it.
    func testAnAcceptedPreviewAppearsInTheHeldHeadlineBeforeTheDelayedCommit() async throws {
        let (vm, handle, _) = try await heldPage()
        defer { vm.stopRefresh() }
        handle.fire("open")
        XCTAssertEqual(try headline(vm), 0.6)

        handle.fire("preview", Self.blendJSON(1, 0.88))
        XCTAssertEqual(try headline(vm), 0.88, "the held headline shows the provisional blend")
        XCTAssertEqual(vm.event?.currentOdds?.homeProbability, 0.6, "the committed event is untouched")
        XCTAssertEqual(vm.event?.blendFoldRevision?.revision, FoldRevision(["4242": 10]))
        XCTAssertTrue(vm.liveBlend.isEmpty, "no provisional value enters the chart's history")
        XCTAssertFalse(vm.streamHasPushedPrice, "a preview is not a pushed price")

        // The delayed commit lands on a newer revision with its own value: the
        // committed value wins, whatever the preview said.
        handle.fire("probability", Self.commit(11, 0.87))
        XCTAssertEqual(vm.event?.currentOdds?.homeProbability, 0.87)
        XCTAssertEqual(try headline(vm), 0.87, "the commit retires the preview")
        XCTAssertTrue(vm.streamHasPushedPrice)

        // A delayed preview still on the old base never takes the headline back.
        handle.fire("preview", Self.blendJSON(2, 0.9, base: 10))
        XCTAssertEqual(try headline(vm), 0.87)
        // One recomposed on the new base does.
        handle.fire("preview", Self.blendJSON(3, 0.89, base: 11))
        XCTAssertEqual(try headline(vm), 0.89)
    }

    func testOldOutOfOrderAndRevokedPreviewsOnTheHeldPage() async throws {
        let (vm, handle, _) = try await heldPage()
        defer { vm.stopRefresh() }
        handle.fire("open")
        handle.fire("preview", Self.blendJSON(5, 0.8))
        handle.fire("preview", Self.blendJSON(4, 0.7))
        XCTAssertEqual(try headline(vm), 0.8, "out of order")
        handle.fire("preview", Self.revokeJSON(6, through: 5))
        XCTAssertEqual(try headline(vm), 0.6, "revoked")
        XCTAssertNil(vm.blendPreview)
        handle.fire("preview", "{not json")
        handle.fire("preview", Self.blendJSON(7, 0.8).replacingOccurrences(of: #""provisional":true"#,
                                                                           with: #""provisional":true,"rev":{"4242":12}"#))
        XCTAssertEqual(try headline(vm), 0.6, "malformed and rev-carrying previews are dropped")
    }

    func testAnExpiredPreviewGivesWayToCommittedTruth() async throws {
        let (vm, handle, clock) = try await heldPage()
        defer { vm.stopRefresh() }
        handle.fire("open")
        let arrival = clock.t
        handle.fire("preview", Self.blendJSON(1, 0.8, ttl: 2_000))
        clock.t = arrival + 1.5
        XCTAssertEqual(try headline(vm), 0.8)
        clock.t = arrival + 2
        XCTAssertEqual(try headline(vm), 0.6)
    }

    func testAnEpochTakeoverAndAReconnectOnTheHeldPage() async throws {
        let (vm, handle, _) = try await heldPage()
        defer { vm.stopRefresh() }
        handle.fire("open")
        handle.fire("preview", Self.blendJSON(90, 0.8, epoch: 4))
        handle.fire("preview", Self.blendJSON(1, 0.75, epoch: 5))
        XCTAssertEqual(try headline(vm), 0.75, "the replacement takes the display")
        handle.fire("preview", Self.blendJSON(91, 0.81, epoch: 4))
        XCTAssertEqual(try headline(vm), 0.75, "the superseded worker never regains it")

        // A reconnect: previews are never replayed, so the held one is cleared;
        // the epoch floor is kept.
        handle.fire("open")
        XCTAssertNil(vm.blendPreview)
        XCTAssertEqual(try headline(vm), 0.6)
        handle.fire("preview", Self.blendJSON(92, 0.82, epoch: 4))
        XCTAssertEqual(try headline(vm), 0.6, "an older epoch stays fenced across the reconnect")
        // The cleared preview orders nothing: the reader no longer holds it, so
        // even a seq it had used shows (web's reset is `held: null`, floor kept).
        handle.fire("preview", Self.blendJSON(1, 0.76, epoch: 5))
        XCTAssertEqual(try headline(vm), 0.76, "the reconnect cleared the reader, not only the page")
        handle.fire("preview", Self.blendJSON(2, 0.77, epoch: 5))
        XCTAssertEqual(try headline(vm), 0.77)
    }

    func testTheEndOfTheMatchAndLeavingThePageClearThePreview() async throws {
        let (vm, handle, _) = try await heldPage()
        handle.fire("open")
        handle.fire("preview", Self.blendJSON(1, 0.8))
        XCTAssertEqual(try headline(vm), 0.8)
        handle.fire("closed")
        XCTAssertNil(vm.blendPreview)
        XCTAssertEqual(try headline(vm), 0.6)

        let (left, leftHandle, _) = try await heldPage()
        leftHandle.fire("open")
        leftHandle.fire("preview", Self.blendJSON(1, 0.8))
        left.stopRefresh()
        XCTAssertNil(left.blendPreview)
        XCTAssertEqual(try headline(left), 0.6)
    }

    func testAFoldedHeldPageNeverShowsAPreview() async throws {
        let (vm, handle, _) = try await heldPage(Self.detail(rev: #"{"4242":10,"4243":5}"#))
        defer { vm.stopRefresh() }
        handle.fire("open")
        handle.fire("preview", Self.blendJSON(1, 0.8))
        XCTAssertEqual(try headline(vm), 0.6)
    }

    /// The decoder admits any safe `ttl_ms`; the expiry re-render must not trap on it.
    func testTheLargestAdmittedTtlShowsWithoutTrapping() async throws {
        let (vm, handle, _) = try await heldPage()
        defer { vm.stopRefresh() }
        handle.fire("open")
        handle.fire("preview", Self.blendJSON(1, 0.8, ttl: FoldRevision.maxSafeInteger))
        XCTAssertEqual(try headline(vm), 0.8)
    }

    // MARK: - The page's wiring

    private static func source(_ relative: String) throws -> String {
        let root = URL(fileURLWithPath: #filePath)
            .deletingLastPathComponent()      // BainLuckTests
            .deletingLastPathComponent()      // Bain Luck (project dir)
        return try String(contentsOf: root.appendingPathComponent(relative), encoding: .utf8)
    }

    /// From `start` through the first `end` after it.
    private static func slice(_ text: String, from start: String, to end: String) throws -> String {
        let head = try XCTUnwrap(text.range(of: start), start)
        let tail = try XCTUnwrap(text.range(of: end, range: head.upperBound..<text.endIndex), end)
        return String(text[head.lowerBound..<tail.upperBound])
    }

    /// Every page test reads `vm.headline(...)` directly, so only the page's
    /// source shows the hero is fed the headline. The chart's projection of the
    /// same preview is pinned in `TheHeldChartEndsOnThePreviewAtItsObservation10090Tests`.
    func testTheHeroAndItsSlideReadTheHeadlineAndTheChartReadsOnlyItsProjection() throws {
        let page = try Self.source("Bain Luck/Views/EventDetailView.swift")
        XCTAssertEqual(page.components(separatedBy: "heroSection(vm.headline(event))").count - 1, 1,
                       "the hero is drawn from the headline")
        XCTAssertFalse(page.contains("heroSection(event)"))
        let value = try Self.slice(page, from: "private func heroValue(away: Bool) -> String {", to: "\n    }\n")
        XCTAssertTrue(value.contains("displayedLabels(in: vm.headline(event))"),
                      "the slide reads the string the hero prints")
        let rising = try Self.slice(page, from: "private func heroRising(away: Bool) -> Bool? {", to: "\n    }\n")
        XCTAssertTrue(rising.contains("guard vm.blendPreview == nil else { return nil }"))
        let chart = try Self.slice(page, from: "OddsChartView(eventId:",
                                  to: "vm.publicationJourney, key: publicationTaskKey))")
        // No raw preview state: only the admitted projections reach the chart.
        XCTAssertFalse(chart.contains("blendPreview"))
        XCTAssertFalse(chart.contains("liveFrames: vm.liveBlend"))
        // Only the edge reading and the paired away label read the headline;
        // the balance ink's admission stays on the committed pair (#10456).
        XCTAssertEqual(chart.components(separatedBy: "vm.headline(").count - 1, 2,
                       "only the edge reading and the paired away label read the headline")
        XCTAssertTrue(chart.contains("servedHomeProbability: event.currentOdds?.homeProbability"),
                      "the balance ink is admitted on the committed pair")
    }
}
