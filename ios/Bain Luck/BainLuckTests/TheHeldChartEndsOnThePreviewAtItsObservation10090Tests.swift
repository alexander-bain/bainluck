import XCTest
@testable import Bain_Luck

/// #10090 — the iPhone twin of web's preview chart edge and its observation
/// clock (PR #11348 `overlayBlendPreviewLine`, PR #11352
/// `displayedProbabilityObservedAt`). The displayed provisional blend ends the
/// chart at `display_observed_at` — the contributing readings' observation
/// time, never the producer's `observed_at` attempt time — and dates the
/// displayed reading with it. Unknown stays unknown. Anything that retires the
/// headline's preview (expiry, revoke, reconnect, a newer commit, the end of
/// the match) returns the chart and the clock to committed truth, and the
/// stored history is never written.
@MainActor
final class TheHeldChartEndsOnThePreviewAtItsObservation10090Tests: XCTestCase {
    private static let id = 4242

    private static func date(_ stamp: String) -> Date { stamp.asDate! }

    private static func blendJSON(_ seq: Int, _ p: Double, observed: String?, epoch: Int = 1, base: Int = 10,
                                  ttl: Int = 60_000, attempt: String = "2026-10-20T19:00:59+00:00") -> String {
        let clock = observed.map { #""display_observed_at":\#($0),"# } ?? ""
        return """
        {"event_id":\(id),"p":\(p),"status":"live","source":"polymarket","source_value":\(p),
         "observed_at":"\(attempt)",\(clock)"provisional":true,
         "preview":{"kind":"blend","epoch":\(epoch),"seq":\(seq),"base_rev":\(base),"ttl_ms":\(ttl),
                    "pending":{"polymarket":\(p)}}}
        """
    }

    private static func quoted(_ stamp: String) -> String { "\"\(stamp)\"" }

    private static func revokeJSON(_ seq: Int, through: Int) -> String {
        """
        {"event_id":\(id),"p":null,"status":"live","provisional":true,
         "preview":{"kind":"revoke","epoch":1,"seq":\(seq),"through_seq":\(through),"reason":"stale"}}
        """
    }

    private static func commit(_ rev: Int, _ p: Double, at: String) -> String {
        """
        {"event_id":\(id),"p":\(p),"source":"polymarket","source_value":\(p),"updated_at":"\(at)",
         "status":"live","rev":{"\(id)":\(rev)}}
        """
    }

    private static let decoder: JSONDecoder = {
        let d = JSONDecoder()
        d.keyDecodingStrategy = .convertFromSnakeCase
        return d
    }()

    /// Committed 60% at 19:00:00 on a singleton fold revision of this row.
    private static func detail(rev: String = #"{"4242":10}"#, status: String = "live") throws -> EventDetail {
        try decoder.decode(EventDetail.self, from: Data("""
        {"id":\(id),"sport":"basketball_nba","home_team":"Home","away_team":"Away","status":"\(status)",
         "home_score":50,"away_score":48,
         "current_odds":{"home_probability":0.6,"away_probability":0.4},
         "hero_probability":0.6,"hero_probability_source":"blend",
         "hero_probability_observed_at":"2026-10-20T19:00:00Z","blend_fold_revision":\(rev),
         "win_probability_sources":{"polymarket":{"value":0.6,"updated_at":"2026-10-20T19:00:00Z"}}}
        """.utf8))
    }

    /// A served blend line whose edge is 19:00:00.
    private static func history(edge: String = "2026-10-20T19:00:00Z") throws -> EventHistoryResponse {
        let rows = [("2026-10-20T18:20:00Z", 0.5), ("2026-10-20T18:40:00Z", 0.55), (edge, 0.6)]
        let points = rows.map { #"{"timestamp":"\#($0.0)","home_probability":\#($0.1)}"# }.joined(separator: ",")
        return try decoder.decode(EventHistoryResponse.self, from: Data("""
        {"event_id":\(id),"home_team":"Home","away_team":"Away","status":"live",
         "history":[\(points)],"aggregate_line":[\(points)],"win_prob_history":{"polymarket":[\(points)]}}
        """.utf8))
    }

    private static func state(_ p: Double, observed: String?, base: Int = 10, expiresAt: TimeInterval = 100)
        -> BlendPreviewState {
        BlendPreviewState(eventId: id, epoch: 1, seq: 1, baseRev: base, p: p, status: "live",
                          expiresAt: expiresAt, observedAt: observed.map(date))
    }

    // MARK: - The frame's observation clock

    func testDisplayObservedAtDecodesAndTheAttemptClockNeverStandsInForIt() throws {
        let micro = try XCTUnwrap(BlendPreviewFrame.decode(
            Self.blendJSON(1, 0.7, observed: Self.quoted("2026-10-20T19:00:04.250000+00:00"))))
        XCTAssertEqual(micro.displayObservedAt, Self.date("2026-10-20T19:00:04.250Z"))
        // Absent, null, unreadable or not a string: unknown — and the frame
        // still decodes, so the headline is unchanged by the additive field.
        for clock in [nil, "null", #""not a time""#, "1792540799", #""""#] {
            let frame = try XCTUnwrap(BlendPreviewFrame.decode(Self.blendJSON(1, 0.7, observed: clock)),
                                      clock ?? "absent")
            XCTAssertNil(frame.displayObservedAt, clock ?? "absent")
            XCTAssertEqual(frame.p, 0.7)
        }
        let held = BlendPreview.readerAfter(.empty, micro, eventId: Self.id, now: 0).held
        XCTAssertEqual(held?.observedAt, Self.date("2026-10-20T19:00:04.250Z"))
    }

    // MARK: - The displayed probability's clock

    func testTheDisplayedClockIsThePreviewsOwnAndUnknownIsNeverTheCommittedOne() throws {
        let event = try Self.detail()
        let committed = Self.date("2026-10-20T19:00:00Z")
        XCTAssertEqual(BlendPreview.displayedObservedAt(nil, held: event, now: 0, committed: committed), committed)
        XCTAssertEqual(BlendPreview.displayedObservedAt(Self.state(0.75, observed: "2026-10-20T18:59:58Z"),
                                                        held: event, now: 0, committed: committed),
                       Self.date("2026-10-20T18:59:58Z"),
                       "an older genuine observation dates the number it produced")
        XCTAssertNil(BlendPreview.displayedObservedAt(Self.state(0.75, observed: nil),
                                                      held: event, now: 0, committed: committed),
                     "a shown preview with no observation clock is undated, not the committed time")
        // Whatever retires the headline's preview restores the committed clock.
        let dated = Self.state(0.75, observed: "2026-10-20T19:00:04Z")
        XCTAssertEqual(BlendPreview.displayedObservedAt(dated, held: event, now: 100, committed: committed),
                       committed, "expired")
        XCTAssertEqual(BlendPreview.displayedObservedAt(dated, held: try Self.detail(rev: #"{"4242":11}"#),
                                                        now: 0, committed: committed), committed, "newer commit")
        XCTAssertEqual(BlendPreview.displayedObservedAt(dated, held: try Self.detail(status: "final"),
                                                        now: 0, committed: committed), committed, "terminal")
        XCTAssertEqual(BlendPreview.displayedObservedAt(dated, held: try Self.detail(rev: #"{"4242":10,"4243":5}"#),
                                                        now: 0, committed: committed), committed, "folded")
    }

    // MARK: - The chart projection

    func testTheChartEndsOnTheShownPreviewAtItsObservationOnlyWhenItIsNewer() throws {
        let event = try Self.detail()
        let history = try Self.history()
        let pushed = [LiveBlendPoint(date: Self.date("2026-10-20T19:00:02Z"), homeProbability: 0.62)]
        func frames(_ observed: String?, _ held: [LiveBlendPoint] = pushed,
                    history: EventHistoryResponse? = history) -> [LiveBlendPoint] {
            BlendPreview.chartFrames(held, history: history, state: Self.state(0.75, observed: observed),
                                     held: event, now: 0)
        }
        XCTAssertEqual(frames("2026-10-20T19:00:04Z"),
                       pushed + [LiveBlendPoint(date: Self.date("2026-10-20T19:00:04Z"), homeProbability: 0.75)])
        XCTAssertEqual(frames("2026-10-20T19:00:04Z", []),
                       [LiveBlendPoint(date: Self.date("2026-10-20T19:00:04Z"), homeProbability: 0.75)])
        XCTAssertEqual(frames(nil), pushed, "no observation clock: the line stays committed")
        XCTAssertEqual(frames("2026-10-20T19:00:02Z"), pushed, "not after the last pushed point")
        XCTAssertEqual(frames("2026-10-20T19:00:01Z", []).count, 1)
        XCTAssertEqual(frames("2026-10-20T19:00:00Z", []), [], "not after the served edge")
        XCTAssertEqual(frames("2026-10-20T18:59:00Z", []), [], "behind the served edge")
        let unreadable = try Self.decoder.decode(EventHistoryResponse.self, from: Data("""
        {"event_id":\(Self.id),"home_team":"Home","away_team":"Away","status":"live","history":[],
         "aggregate_line":[{"timestamp":"garbage","home_probability":0.6}]}
        """.utf8))
        XCTAssertEqual(frames("2026-10-20T19:00:04Z", [], history: unreadable), [],
                       "an undatable served point cannot be proved older")
        // Not displayed: the line is the input, untouched.
        let dated = Self.state(0.75, observed: "2026-10-20T19:00:04Z")
        for (held, now) in [(try Self.detail(rev: #"{"4242":11}"#), 0.0), (try Self.detail(status: "final"), 0),
                            (event, 100)] {
            XCTAssertEqual(BlendPreview.chartFrames(pushed, history: history, state: dated, held: held, now: now),
                           pushed)
        }
        XCTAssertEqual(BlendPreview.chartFrames(pushed, history: history, state: nil, held: event, now: 0), pushed)
    }

    /// The projection is a vertex on the served blend line, and it never mints
    /// a series on a page whose line is one venue's (`extendingServedSourceSeries`).
    func testTheProjectedPointExtendsTheBlendLineAndNeverAVenueSeries() throws {
        let at = Self.date("2026-10-20T19:00:04Z")
        let projected = [LiveBlendPoint(date: at, homeProbability: 0.75)]
        let blend = OddsChartView.chartPoints(from: try Self.history(), liveFrames: projected)
        let tip = try XCTUnwrap(blend.filter { $0.source == "aggregate" }.max { $0.date < $1.date })
        XCTAssertEqual(tip.date, at)
        XCTAssertEqual(tip.probability, 0.75)

        let venueOnly = try Self.decoder.decode(EventHistoryResponse.self, from: Data("""
        {"event_id":\(Self.id),"home_team":"Home","away_team":"Away","status":"live","history":[],
         "win_prob_history":{"polymarket":[{"timestamp":"2026-10-20T19:00:00Z","home_probability":0.6}]}}
        """.utf8))
        XCTAssertFalse(OddsChartView.chartPoints(from: venueOnly, liveFrames: projected).contains { $0.date == at })
    }

    // MARK: - The held page

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
        /// #11564: a transport open, then the v3 domain on a fresh session.
        var session = ""
        @MainActor func openV3() {
            fire("open")
            session = V3PageWire.nextSession()
            fire("preview_open_v3", V3PageWire.open(4242, members: [4242], session: session))
        }
        @MainActor func previewV3(_ frame: String) {
            fire("preview_v3", V3PageWire.preview(frame, eventId: 4242, session: session))
        }
    }

    private struct Client: EventDetailProviding {
        struct Declined: Error {}
        let event: EventDetail
        let history: EventHistoryResponse
        func fetchEvent(id: Int) async throws -> EventDetail { event }
        func fetchEventHistory(id: Int, hours: Int) async throws -> EventHistoryResponse { history }
        func fetchRelatedFutures(eventId: Int) async throws -> RelatedFuturesResponse { throw Declined() }
        func fetchTeamProgression(eventId: Int) async throws -> TeamProgressionResponse { throw Declined() }
        func fetchGameMarkets(eventId: Int) async throws -> GameMarketsResponse { throw Declined() }
        func fetchLineMovement(eventId: Int) async throws -> LineMovementResponse { throw Declined() }
    }

    private final class Clock { var t: TimeInterval = 1_760_000_000 }

    private func heldPage() async throws -> (EventDetailViewModel, FakeHandle, Clock) {
        let handle = FakeHandle()
        let clock = Clock()
        let vm = EventDetailViewModel(
            eventId: Self.id,
            client: Client(event: try Self.detail(), history: try Self.history()),
            makeStreamHandle: { _ in handle },
            now: { clock.t },
            sleep: { _ in try? await Task.sleep(nanoseconds: 60_000_000_000) }
        )
        await vm.load()
        let deadline = Date().addingTimeInterval(5)
        while vm.history == nil, Date() < deadline { try? await Task.sleep(nanoseconds: 10_000_000) }
        XCTAssertNotNil(vm.history)
        return (vm, handle, clock)
    }

    /// What the page hands its hero, chart and clock, read the way the page reads them.
    private struct Shown: Equatable {
        let headline: String?
        let chartEnd: LiveBlendPoint?
        let clock: Date?
    }

    private func shown(_ vm: EventDetailViewModel) throws -> Shown {
        let event = try XCTUnwrap(vm.event)
        return Shown(headline: LivePriceActivity.displayedLabels(in: vm.headline(event)).home,
                     chartEnd: vm.chartFrames(event).last,
                     clock: vm.displayedProbabilityObservedAt(event))
    }

    private static let committedClock = date("2026-10-20T19:00:00Z")

    /// THE SHIP, on the held page: during the event-stamp hold the chart ends
    /// on the headline's number at its observation time; a newer observation
    /// that rounds the same moves the time, not the digits; a replay cannot
    /// move the time; and nothing committed is written.
    func testTheHeldPageChartAndClockFollowTheAdmittedPreview() async throws {
        let (vm, handle, _) = try await heldPage()
        defer { vm.stopRefresh() }
        handle.openV3()
        XCTAssertEqual(try shown(vm), Shown(headline: "60%", chartEnd: nil, clock: Self.committedClock))

        handle.previewV3(Self.blendJSON(1, 0.751, observed: Self.quoted("2026-10-20T19:00:04Z")))
        let first = LiveBlendPoint(date: Self.date("2026-10-20T19:00:04Z"), homeProbability: 0.751)
        XCTAssertEqual(try shown(vm), Shown(headline: "75%", chartEnd: first, clock: first.date))

        // Same rounded digits, newer genuine observation: only the time moves.
        handle.previewV3(Self.blendJSON(2, 0.754, observed: Self.quoted("2026-10-20T19:00:09Z")))
        let second = LiveBlendPoint(date: Self.date("2026-10-20T19:00:09Z"), homeProbability: 0.754)
        XCTAssertEqual(try shown(vm), Shown(headline: "75%", chartEnd: second, clock: second.date))

        // A replay of seq 2 and a delayed seq 1 move nothing, whatever the
        // producer's attempt clock says.
        handle.previewV3(Self.blendJSON(2, 0.754, observed: Self.quoted("2026-10-20T19:00:30Z"),
                                              attempt: "2026-10-20T19:01:30+00:00"))
        handle.previewV3(Self.blendJSON(1, 0.751, observed: Self.quoted("2026-10-20T19:00:40Z")))
        XCTAssertEqual(try shown(vm), Shown(headline: "75%", chartEnd: second, clock: second.date))

        XCTAssertTrue(vm.liveBlend.isEmpty, "the projection is never stored")
        XCTAssertEqual(vm.event?.currentOdds?.homeProbability, 0.6)
        XCTAssertEqual(vm.event?.heroProbabilityObservedAt, "2026-10-20T19:00:00Z")
        XCTAssertEqual(vm.history?.aggregateLine?.count, 3)
    }

    func testAPreviewWithNoObservationClockLeavesTheChartCommittedAndTheTimeUnknown() async throws {
        let (vm, handle, _) = try await heldPage()
        defer { vm.stopRefresh() }
        handle.openV3()
        handle.previewV3(Self.blendJSON(1, 0.8, observed: nil))
        XCTAssertEqual(try shown(vm), Shown(headline: "80%", chartEnd: nil, clock: nil))
        handle.previewV3(Self.blendJSON(2, 0.81, observed: "null"))
        XCTAssertEqual(try shown(vm), Shown(headline: "81%", chartEnd: nil, clock: nil))
        // A clock behind the served edge dates the number but cannot extend the line.
        handle.previewV3(Self.blendJSON(3, 0.82, observed: Self.quoted("2026-10-20T18:59:50Z")))
        XCTAssertEqual(try shown(vm), Shown(headline: "82%", chartEnd: nil,
                                            clock: Self.date("2026-10-20T18:59:50Z")))
    }

    func testRevokeExpiryReconnectNewerCommitAndTheEndRestoreCommittedTruth() async throws {
        let (vm, handle, clock) = try await heldPage()
        defer { vm.stopRefresh() }
        handle.openV3()
        let committed = Shown(headline: "60%", chartEnd: nil, clock: Self.committedClock)
        let observed = Self.quoted("2026-10-20T19:00:04Z")

        handle.previewV3(Self.blendJSON(1, 0.8, observed: observed))
        XCTAssertEqual(try shown(vm).headline, "80%")
        handle.previewV3(Self.revokeJSON(2, through: 1))
        XCTAssertEqual(try shown(vm), committed, "revoked")

        let arrival = clock.t
        handle.previewV3(Self.blendJSON(3, 0.8, observed: observed, ttl: 2_000))
        clock.t = arrival + 1.5
        XCTAssertEqual(try shown(vm).headline, "80%")
        clock.t = arrival + 2
        XCTAssertEqual(try shown(vm), committed, "expired")

        handle.previewV3(Self.blendJSON(4, 0.8, observed: observed))
        XCTAssertEqual(try shown(vm).headline, "80%")
        handle.openV3()
        XCTAssertEqual(try shown(vm), committed, "reopened transport")

        handle.previewV3(Self.blendJSON(5, 0.8, observed: observed))
        handle.fire("probability", Self.commit(11, 0.72, at: "2026-10-20T19:00:06Z"))
        let newer = try shown(vm)
        XCTAssertEqual(newer.headline, "72%", "the newer commit wins")
        XCTAssertEqual(newer.clock, Self.date("2026-10-20T19:00:06Z"), "on its own committed clock")
        XCTAssertEqual(newer.chartEnd, vm.liveBlend.last, "the chart ends on the committed push")
        XCTAssertEqual(newer.chartEnd?.homeProbability, 0.72)

        handle.previewV3(Self.blendJSON(6, 0.9, observed: Self.quoted("2026-10-20T19:00:08Z"), base: 11))
        XCTAssertEqual(try shown(vm).headline, "90%")
        handle.fire("closed")
        XCTAssertEqual(try shown(vm), newer, "the end of the match")
    }

    // MARK: - The page's wiring

    private static func source(_ relative: String) throws -> String {
        let root = URL(fileURLWithPath: #filePath).deletingLastPathComponent().deletingLastPathComponent()
        return try String(contentsOf: root.appendingPathComponent(relative), encoding: .utf8)
    }

    /// The page tests above read the view model's helpers, so only the page's
    /// source shows the chart and both clock readers use them.
    func testTheChartItsEdgeAndThePhaseClockReadTheDisplayedPreview() throws {
        let page = try Self.source("Bain Luck/Views/EventDetailView.swift")
        let head = try XCTUnwrap(page.range(of: "OddsChartView(eventId:"))
        let tail = try XCTUnwrap(page.range(of: "vm.publicationJourney, key: publicationTaskKey))",
                                            range: head.upperBound..<page.endIndex))
        let chart = String(page[head.lowerBound..<tail.upperBound])
        XCTAssertTrue(chart.contains("liveFrames: vm.chartFrames(event)"))
        XCTAssertTrue(chart.contains("liveEdge: LiveEdgeReading.current(in: vm.headline(event))"))
        XCTAssertTrue(chart.contains("pairedAwayLabel9483: LivePriceActivity.displayedLabels(in: vm.headline(event)).away"))
        XCTAssertTrue(chart.contains("observedAt: vm.displayedProbabilityObservedAt(event)"))
        XCTAssertFalse(chart.contains("heroProbabilityObservedAt"))
        // The phase label ("Current" / "Last recorded win chance") reads the
        // same clock; it is the only other reader of the hero's clock here.
        XCTAssertEqual(page.components(separatedBy: "observedAt: vm.displayedProbabilityObservedAt(event)").count - 1, 2)
        XCTAssertFalse(page.contains("observedAt: event.heroProbabilityObservedAt"))
    }
}
