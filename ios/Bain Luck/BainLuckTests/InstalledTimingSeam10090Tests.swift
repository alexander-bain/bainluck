import OSLog
import XCTest
@testable import Bain_Luck

/// #10090 — the installed-phone timing seam. A trace is only evidence if an
/// adoption mark means the page took THAT value: a refused, stale, equal or
/// invalid frame must leave only its receipt, and every adopted value must
/// carry its own revision. Driven through the real controller and view model
/// with the same fake handle `FoldedQuoteStream10090Tests` uses.
@MainActor
final class InstalledTimingSeam10090Tests: XCTestCase {
    private static let sources = #""polymarket":{"value":0.6,"updated_at":"2026-09-25T17:00:00Z"}"#
    /// This page and the foreign game its frames are tested against.
    nonisolated private static let events: Set<Int> = [4242, 777]
    private static let oneRow = #"{"4242":20}"#
    private static let folded = #"{"4242":20,"999":5}"#

    private var marks: [LiveTimingSeam.Mark] = []

    override func setUp() async throws {
        marks = []
        // The host app runs its own live streams against production while the
        // tests run, and their marks reach this observer too (a live Dodgers
        // game's frame failed the foreign-frame test). Keep the fixtures' own.
        LiveTimingSeam.observer = { [weak self] in
            guard Self.events.contains($0.eventId) else { return }
            self?.marks.append($0)
        }
    }

    override func tearDown() async throws {
        LiveTimingSeam.observer = nil
    }

    private func page(p: Double = 0.6, revision: String = oneRow) throws -> EventDetail {
        let decoder = JSONDecoder()
        decoder.keyDecodingStrategy = .convertFromSnakeCase
        return try decoder.decode(EventDetail.self, from: Data("""
        {"id":4242,"sport":"basketball_nba","home_team":"Celtics","away_team":"Knicks","status":"live",
         "home_score":50,"away_score":48,
         "current_odds":{"home_probability":\(p),"away_probability":\(1 - p)},
         "hero_probability":\(p),"hero_probability_source":"blend",
         "hero_probability_observed_at":"2026-09-25T17:00:00Z",
         "blend_fold_revision":\(revision),"win_probability_sources":{\(Self.sources)}}
        """.utf8))
    }

    private static func raw(p: Double = 0.55, rev: Int = 21, at: String = "2026-09-25T17:10:00Z",
                            eventId: Int = 4242, pending: Bool = false) -> String {
        #"{"event_id":\#(eventId),"p":\#(p),"source":"polymarket","source_value":\#(p),"updated_at":"\#(at)","status":"live","rev":{"\#(eventId)":\#(rev)},"folded_quote_pending":\#(pending)}"#
    }

    private static func quote(p: Double = 0.52, revision: String = #"{"4242":21,"999":5}"#,
                              at: String = "2026-09-25T17:10:00Z") -> String {
        """
        {"event_id":4242,"hero_probability":\(p),"hero_probability_away":\(1 - p),
         "hero_probability_source":"blend","hero_probability_observed_at":"\(at)",
         "blend_fold_revision":\(revision),
         "win_probability_sources":{"polymarket":{"value":\(p),"display_name":"Polymarket","type":"market","color":"#000","updated_at":"\(at)"}},
         "hero_sportsbook_count":null,"status":"live","sport":"basketball_nba","hero_settled_result":null}
        """
    }

    private final class Handle: LiveStreamHandle, @unchecked Sendable {
        var isClosed = false
        var handlers: [String: [@MainActor (String) -> Void]] = [:]
        func on(_ event: String, _ handler: @escaping @MainActor (String) -> Void) { handlers[event, default: []].append(handler) }
        func close() { isClosed = true }
        func fire(_ event: String, _ raw: String = "") { for h in handlers[event] ?? [] { h(raw) } }
        func result(_ quote: String) {
            let raw = InstalledTimingSeam10090Tests.raw(p: 0.9).dropLast()
            fire("folded_probability", "\(raw),\"folded_quote\":\(quote)}")
        }
    }

    /// The read the chart draws: the blend served to `edge` (60% until then,
    /// `value` there), pinned at `edge` under `pinRevision` when one is given.
    /// The default ends before every frame and preview below, so those are
    /// drawn past it.
    private static func served(edge: String = "2026-09-25T16:59:00Z", value: Double = 0.6,
                               pinRevision: String? = nil, pinObserved: String? = nil) throws -> EventHistoryResponse {
        let pin = pinRevision.map { #","blend_edge_pinned":true,"blend_edge_fold_revision":\#($0)"# } ?? ""
        let observed = pinObserved.map { #","blend_edge_observed_at":"\#($0)""# } ?? ""
        let decoder = JSONDecoder()
        decoder.keyDecodingStrategy = .convertFromSnakeCase
        return try decoder.decode(EventHistoryResponse.self, from: Data("""
        {"event_id":4242,"home_team":"Celtics","away_team":"Knicks","status":"live","history":[],
         "aggregate_line":[{"timestamp":"2026-09-25T16:58:00Z","home_probability":0.6},
                           {"timestamp":"\(edge)","home_probability":\(value)}],
         "win_prob_history":{"polymarket":[{"timestamp":"\(edge)","home_probability":\(value)}]}\(pin)\(observed)}
        """.utf8))
    }

    @MainActor
    private final class Client: EventDetailProviding {
        struct Missing: Error {}
        var response: EventDetail
        var history: EventHistoryResponse?
        init(_ response: EventDetail, history: EventHistoryResponse?) {
            self.response = response
            self.history = history
        }
        func fetchEvent(id: Int) async throws -> EventDetail { response }
        func fetchEventHistory(id: Int, hours: Int) async throws -> EventHistoryResponse {
            guard let history else { throw Missing() }
            return history
        }
        func fetchRelatedFutures(eventId: Int) async throws -> RelatedFuturesResponse { throw Missing() }
        func fetchTeamProgression(eventId: Int) async throws -> TeamProgressionResponse { throw Missing() }
        func fetchGameMarkets(eventId: Int) async throws -> GameMarketsResponse { throw Missing() }
        func fetchLineMovement(eventId: Int) async throws -> LineMovementResponse { throw Missing() }
    }

    private func loaded(_ held: EventDetail) async throws -> (Client, Handle, EventDetailViewModel) {
        await loaded(held, history: try Self.served())
    }

    private func loaded(_ held: EventDetail, history: EventHistoryResponse?) async -> (Client, Handle, EventDetailViewModel) {
        let client = Client(held, history: history), handle = Handle()
        let vm = EventDetailViewModel(eventId: 4242, client: client, makeStreamHandle: { _ in handle },
            now: { 1_790_355_605 }, sleep: { _ in try? await Task.sleep(nanoseconds: 60_000_000_000) })
        await vm.load(); handle.fire("open")
        marks = []
        return (client, handle, vm)
    }

    private func drain() async { for _ in 0..<200 { await Task.yield() } }

    private func names(_ marks: [LiveTimingSeam.Mark]) -> [LiveTimingSeam.Name] { marks.map(\.name) }

    func testDistinctAdmittedChartDatesKeepDistinctModelToViewKeys() {
        // These distinct Foundation Dates collapse when converted to epoch seconds.
        let a = Date(timeIntervalSinceReferenceDate: Double(bitPattern: 4740106905103354771))
        let b = Date(timeIntervalSinceReferenceDate: Double(bitPattern: 4740106905103354772))
        XCTAssertLessThan(a, b)
        XCTAssertEqual(a.timeIntervalSince1970, b.timeIntervalSince1970)
        let first = LiveBlendBuffer.appending(LiveBlendPoint(date: a, homeProbability: 0.4), to: [])
        let both = LiveBlendBuffer.appending(LiveBlendPoint(date: b, homeProbability: 0.5), to: first)
        XCTAssertEqual(both.count, 2)

        LiveTimingSeam.modelChartAppended(eventId: 4242, path: "stream", basis: "rev:4242=21", at: a)
        LiveTimingSeam.modelChartAppended(eventId: 4242, path: "stream", basis: "rev:4242=22", at: b)
        LiveTimingSeam.viewUpdated(
            from: .init(eventId: 4242, headlineBasis: "none", probability: nil, observed: nil,
                        chartBasis: "-", chartEdge: nil, chartProbability: nil),
            to: .init(eventId: 4242, headlineBasis: "none", probability: nil, observed: nil,
                      chartBasis: "-", chartEdge: b, chartProbability: nil)
        )
        XCTAssertEqual(names(marks), [.modelChartAppended, .modelChartAppended, .viewChartUpdated])
        XCTAssertEqual(marks[0].stamp, "4740106905103354771")
        XCTAssertEqual(marks[1].stamp, "4740106905103354772")
        XCTAssertNotEqual(marks[0].stamp, marks[1].stamp)
        XCTAssertEqual(marks[2].stamp, marks[1].stamp, "the coalesced view joins only the point it carries")
    }

    /// A phone Logging recording keeps signposts for only its last ~50 s but
    /// Default rows for the whole hold, so every mark is also a `notice` line
    /// carrying exactly the signpost's message, behind the mark's name.
    func testEveryMarkIsAlsoAPersistedDefaultLineCarryingTheSignpostsMessage() throws {
        let basis = "rev:4242=\(UInt32.random(in: 1...UInt32.max))"
        let edge = Date(timeIntervalSinceReferenceDate: 1)
        let since = Date().addingTimeInterval(-1)
        LiveTimingSeam.modelChartAppended(eventId: 4242, path: "stream", basis: basis, at: edge)
        let line = LiveTimingSeam.logLine(try XCTUnwrap(marks.last))
        XCTAssertEqual(line, "model.chart.appended event=4242 path=stream basis=\(basis)"
                       + " stamp=\(LiveTimingSeam.stamp(edge)) p=- observed=-")

        let store = try OSLogStore(scope: .currentProcessIdentifier)
        let logged = try store.getEntries(at: store.position(date: since),
                                          matching: NSPredicate(format: "subsystem == %@ AND category == %@",
                                                                "com.bainluck", "liveTiming"))
            .compactMap { $0 as? OSLogEntryLog }
            .filter { $0.composedMessage == line }
        XCTAssertEqual(logged.map(\.level), [.notice], "one Default line, not Info or Debug, which a long hold loses")
    }

    // MARK: - Raw row

    func testAValidChangedFrameMarksReceiptThenModelHeadlineAndChartOnItsOwnRevision() async throws {
        let (_, handle, vm) = try await loaded(try page())
        defer { vm.stopRefresh() }
        let before = vm.timingPresented(try XCTUnwrap(vm.event))

        handle.fire("probability", Self.raw())
        await drain()

        XCTAssertEqual(vm.event?.currentOdds?.homeProbability, 0.55)
        let stamp = LiveTimingSeam.stamp(try XCTUnwrap("2026-09-25T17:10:00Z".asDate))
        XCTAssertEqual(marks, [
            .init(name: .frameReceived, eventId: 4242, path: "raw", basis: "rev:4242=21", stamp: "-"),
            .init(name: .modelChartAppended, eventId: 4242, path: "stream", basis: "rev:4242=21", stamp: stamp),
            .init(name: .modelHeadlineAdopted, eventId: 4242, path: "stream", basis: "rev:4242=21", stamp: "-"),
        ])
        // The chart point and the headline are the same value — agreement survives.
        XCTAssertEqual(vm.liveBlend.last?.homeProbability, vm.event?.currentOdds?.homeProbability)

        // The view mark names the same revision and the same chart point: the
        // chart's end under the basis it was appended with (#10090), not `-`.
        marks = []
        let after = vm.timingPresented(try XCTUnwrap(vm.event))
        LiveTimingSeam.viewUpdated(from: before, to: after)
        XCTAssertEqual(marks, [
            .init(name: .viewHeadlineUpdated, eventId: 4242, path: "view", basis: "rev:4242=21", stamp: "-",
                  probability: "0.55", observed: stamp),
            .init(name: .viewChartUpdated, eventId: 4242, path: "view", basis: "rev:4242=21", stamp: stamp,
                  probability: "0.55", observed: stamp),
        ])
        marks = []
        LiveTimingSeam.viewUpdated(from: after, to: after)
        XCTAssertEqual(marks, [], "an update that changes neither emits nothing")
    }

    func testAStaleEqualInvalidOrForeignFrameLeavesOnlyItsReceipt() async throws {
        let (_, handle, vm) = try await loaded(try page())
        defer { vm.stopRefresh() }
        handle.fire("probability", Self.raw())
        await drain()
        let points = vm.liveBlend.count
        marks = []

        for frame in [
            Self.raw(p: 0.7, rev: 21, at: "2026-09-25T17:11:00Z"),   // equal revision, later clock
            Self.raw(p: 0.7, rev: 19, at: "2026-09-25T17:12:00Z"),   // older revision
            Self.raw(p: 1.5, rev: 22, at: "2026-09-25T17:13:00Z"),   // not a probability
            Self.raw(p: 0.7, rev: 30, eventId: 777),                 // another game
        ] {
            handle.fire("probability", frame)
        }
        await drain()

        XCTAssertEqual(names(marks), Array(repeating: .frameReceived, count: 4))
        XCTAssertEqual(marks.map(\.basis), ["rev:4242=21", "rev:4242=19", "rev:4242=22", "rev:777=30"])
        XCTAssertEqual(vm.event?.currentOdds?.homeProbability, 0.55)
        XCTAssertEqual(vm.liveBlend.count, points)
    }

    /// The host app's own live page emits marks into the same process-wide
    /// observer. One landing mid-test (15329526, a live Dodgers game) failed the
    /// test above; such marks must never reach these assertions.
    func testAMarkFromTheHostAppsOwnLiveGameNeverReachesTheseAssertions() {
        LiveTimingSeam.modelChartAppended(eventId: 15329526, path: "stream", basis: "rev:15329526=5380", at: Date())
        XCTAssertEqual(marks, [])
        LiveTimingSeam.modelChartAppended(eventId: 4242, path: "stream", basis: "rev:4242=21", at: Date())
        XCTAssertEqual(marks.map(\.basis), ["rev:4242=21"], "the fixture's own mark is still recorded")
    }

    // MARK: - Folded

    func testAFoldedPageMarksTheQuotesFullVectorNeverTheRawRowsRevision() async throws {
        let (_, handle, vm) = try await loaded(try page(revision: Self.folded))
        defer { vm.stopRefresh() }

        handle.fire("probability", Self.raw(p: 0.9, pending: true))
        await drain()
        XCTAssertEqual(marks, [.init(name: .frameReceived, eventId: 4242, path: "raw", basis: "rev:4242=21", stamp: "-")],
                       "a promise is received, not adopted")

        marks = []
        handle.result(Self.quote())
        await drain()
        XCTAssertEqual(vm.event?.currentOdds?.homeProbability, 0.52)
        let stamp = LiveTimingSeam.stamp(try XCTUnwrap("2026-09-25T17:10:00Z".asDate))
        XCTAssertEqual(marks, [
            .init(name: .frameReceived, eventId: 4242, path: "folded", basis: "rev:4242=21;999=5", stamp: "-"),
            .init(name: .modelChartAppended, eventId: 4242, path: "folded", basis: "rev:4242=21;999=5", stamp: stamp),
            .init(name: .modelHeadlineAdopted, eventId: 4242, path: "folded", basis: "rev:4242=21;999=5", stamp: "-"),
        ])
        XCTAssertEqual(vm.liveBlend.last?.homeProbability, 0.52)
        let drawn = vm.timingPresented(try XCTUnwrap(vm.event))
        XCTAssertEqual(drawn.chartBasis, "rev:4242=21;999=5", "the chart's end names the quote's full vector too")
        XCTAssertEqual(drawn.chartEdge, "2026-09-25T17:10:00Z".asDate)

        // A replayed or older fold, and an explicit null: receipts only.
        marks = []
        handle.result(Self.quote(p: 0.7))
        handle.result(Self.quote(p: 0.7, revision: #"{"4242":20,"999":5}"#))
        handle.result("null")
        await drain()
        XCTAssertEqual(names(marks).filter { $0 != .frameReceived }, [], "only a read may follow a null")
        XCTAssertEqual(marks.filter { $0.name == .frameReceived }.map(\.basis),
                       ["rev:4242=21;999=5", "rev:4242=20;999=5", "null"])
        XCTAssertEqual(vm.event?.currentOdds?.homeProbability, 0.52)
    }

    // MARK: - Read

    func testAStalePollIsNoAdoptionAndANewerReadIsMarkedAsARead() async throws {
        let (client, handle, vm) = try await loaded(try page())
        defer { vm.stopRefresh() }
        handle.fire("probability", Self.raw())
        await drain()

        marks = []
        client.response = try page(p: 0.6, revision: Self.oneRow)   // older than the held 21
        await vm.load()
        XCTAssertEqual(vm.event?.currentOdds?.homeProbability, 0.55)
        XCTAssertEqual(names(marks), [], "the held headline did not move")

        client.response = try page(p: 0.48, revision: #"{"4242":22}"#)
        await vm.load()
        XCTAssertEqual(vm.event?.currentOdds?.homeProbability, 0.48)
        XCTAssertEqual(marks, [.init(name: .modelHeadlineAdopted, eventId: 4242, path: "read",
                                     basis: "rev:4242=22", stamp: "-")])

        // #10090 — a read moves the headline and draws no chart point, so the
        // chart still ends on the stream's frame: its mark names THAT frame's
        // revision, value and clock, never the newer headline's basis.
        let shown = vm.timingPresented(try XCTUnwrap(vm.event))
        XCTAssertEqual(shown.headlineBasis, "rev:4242=22")
        XCTAssertEqual(shown.chartBasis, "rev:4242=21", "the drawn point's own commit")
        XCTAssertEqual(shown.chartProbability, 0.55)
        XCTAssertEqual(shown.chartEdge, "2026-09-25T17:10:00Z".asDate)
        XCTAssertEqual(shown.chartObserved, "2026-09-25T17:10:00Z".asDate)
    }

    // MARK: - Buffer at or behind the read (#10090 served end)

    /// The chart's own end for `vm`'s page, as the plot draws it.
    private func chartsOwnEnd(_ vm: EventDetailViewModel, _ history: EventHistoryResponse) throws -> ChartDataPoint {
        try XCTUnwrap(OddsChartView.chartPoints(from: history, liveFrames: vm.chartFrames(try XCTUnwrap(vm.event)))
            .filter { $0.source == "aggregate" }.sorted { $0.date < $1.date }.last)
    }

    /// A frame at EXACTLY the read's edge is not drawn there (ties go to the
    /// served point): the line ends on the read's 58%, so the chart mark must
    /// name that point, never the buffer frame's revision or value.
    func testAFrameAtTheReadsEdgeIsNotTheEndSoTheMarkNamesTheServedPoint() async throws {
        let history = try Self.served(edge: "2026-09-25T17:10:00Z", value: 0.58)
        let (_, handle, vm) = await loaded(try page(), history: history)
        defer { vm.stopRefresh() }
        handle.fire("probability", Self.raw())
        await drain()
        XCTAssertEqual(names(marks), [.frameReceived, .modelChartAppended, .modelHeadlineAdopted],
                       "the buffer took the frame at the edge's own time")
        XCTAssertEqual(vm.liveBlend.last?.date, "2026-09-25T17:10:00Z".asDate)

        let end = try chartsOwnEnd(vm, history)
        XCTAssertEqual(end.probability, 0.58, "the chart draws the read's point at the shared time")
        let shown = vm.timingPresented(try XCTUnwrap(vm.event))
        XCTAssertEqual(shown.headlineBasis, "rev:4242=21")
        XCTAssertEqual(shown.chartBasis, "served:none", "an unpinned bucket carries no identity; never rev:4242=21")
        XCTAssertEqual(shown.chartEdge, end.date)
        XCTAssertEqual(shown.chartProbability, end.probability)
        XCTAssertNil(shown.chartObserved)
    }

    /// A read pinned PAST the buffer's frame: the line ends on the pin, named
    /// by the revision and observation the read gives it. The frame is drawn
    /// inside the line, not at its end, so its revision is not the end's.
    func testAFrameBehindAPinnedReadIsNotTheEndSoTheMarkNamesThePin() async throws {
        let history = try Self.served(edge: "2026-09-25T17:12:00Z", value: 0.57, pinRevision: #"{"4242":21}"#,
                                      pinObserved: "2026-09-25T17:11:00Z")
        let (_, handle, vm) = await loaded(try page(), history: history)
        defer { vm.stopRefresh() }
        handle.fire("probability", Self.raw())
        await drain()
        XCTAssertEqual(vm.liveBlend.last?.basis, "rev:4242=21")
        XCTAssertNil(vm.chartFrames(try XCTUnwrap(vm.event)).last?.headlineOverPin,
                     "a pin observed after the headline is not re-valued")

        let end = try chartsOwnEnd(vm, history)
        XCTAssertEqual(end.date, "2026-09-25T17:12:00Z".asDate)
        XCTAssertEqual(end.probability, 0.57)
        let shown = vm.timingPresented(try XCTUnwrap(vm.event))
        XCTAssertEqual(shown.chartBasis, "served:rev:4242=21", "the read's pin, never the buffer frame's own name")
        XCTAssertEqual(shown.chartEdge, end.date)
        XCTAssertEqual(shown.chartProbability, 0.57, "the drawn value, not the frame's 0.55")
        XCTAssertEqual(shown.chartObserved, "2026-09-25T17:11:00Z".asDate, "the pin's observation, not the frame's")

        // The view mark carries exactly that.
        marks = []
        LiveTimingSeam.viewUpdated(from: .idle, to: shown)
        XCTAssertEqual(marks.last, .init(name: .viewChartUpdated, eventId: 4242, path: "view",
                                         basis: "served:rev:4242=21", stamp: LiveTimingSeam.stamp(end.date),
                                         probability: "0.57",
                                         observed: LiveTimingSeam.stamp("2026-09-25T17:11:00Z".asDate)))
    }

    // MARK: - Preview v3 (#10090 preview seam)

    private static let namespace = V3PageWire.namespace

    /// A singleton v3 preview frame for this page: `p` observed at `at`, on
    /// committed base `base`.
    private static func previewFrame(seq: Int, p: Double, at: String, base: Int = 20, ttl: Int = 60_000) -> String {
        #"{"event_id":4242,"p":\#(p),"p_away":\#(1 - p),"sport":"basketball_nba","status":"live","display_observed_at":"\#(at)","preview":{"kind":"blend","epoch":2,"seq":\#(seq),"base_rev":\#(base),"ttl_ms":\#(ttl)}}"#
    }

    private func basis(_ session: String, seq: Int, base: Int = 20) -> String {
        "v3:1/\(Self.namespace)/\(session)/e2/s\(seq)/b\(base)"
    }

    /// A page holding a v3 domain on a fresh session.
    private func openV3(_ handle: Handle) -> String {
        let session = V3PageWire.nextSession()
        handle.fire("preview_open_v3", V3PageWire.open(4242, members: [4242], session: session))
        return session
    }

    /// Receipt, then adoption, each on the preview's own identity, value and
    /// observation clock; a repeated value under a new sequence is a new
    /// identity; a preview from another session and a replay are received and
    /// never adopted; the hero and chart print the preview with that identity,
    /// and give way to a newer committed revision under its own basis.
    func testAV3PreviewMarksReceiptThenAdoptionAndTheViewPrintsItsIdentityUntilACommitOutranksIt() async throws {
        let (_, handle, vm) = try await loaded(try page())
        defer { vm.stopRefresh() }
        let session = openV3(handle)
        var shown = vm.timingPresented(try XCTUnwrap(vm.event))
        XCTAssertEqual(marks, [], "an open shows nothing")
        let t1 = "2026-09-25T17:00:05Z", t1Stamp = LiveTimingSeam.stamp(try XCTUnwrap(t1.asDate))

        handle.fire("preview_v3", V3PageWire.preview(Self.previewFrame(seq: 1, p: 0.7, at: t1), eventId: 4242, session: session))
        XCTAssertEqual(marks, [
            .init(name: .previewReceived, eventId: 4242, path: "preview", basis: basis(session, seq: 1), stamp: "-",
                  probability: "0.7", observed: t1Stamp),
            .init(name: .modelPreviewAdopted, eventId: 4242, path: "preview", basis: basis(session, seq: 1), stamp: "-",
                  probability: "0.7", observed: t1Stamp),
        ], "offered, then adopted, on its own identity")
        marks = []
        var next = vm.timingPresented(try XCTUnwrap(vm.event))
        LiveTimingSeam.viewUpdated(from: shown, to: next)
        XCTAssertEqual(marks, [
            .init(name: .viewHeadlineUpdated, eventId: 4242, path: "view", basis: basis(session, seq: 1), stamp: "-",
                  probability: "0.7", observed: t1Stamp),
            .init(name: .viewChartUpdated, eventId: 4242, path: "view", basis: basis(session, seq: 1), stamp: t1Stamp,
                  probability: "0.7", observed: t1Stamp),
        ], "the hero and chart print the preview, named as the preview")

        // The same value under a new sequence: a new identity at every depth.
        marks = []
        shown = next
        handle.fire("preview_v3", V3PageWire.preview(Self.previewFrame(seq: 2, p: 0.7, at: t1), eventId: 4242, session: session))
        next = vm.timingPresented(try XCTUnwrap(vm.event))
        LiveTimingSeam.viewUpdated(from: shown, to: next)
        XCTAssertEqual(names(marks), [.previewReceived, .modelPreviewAdopted, .viewHeadlineUpdated, .viewChartUpdated])
        XCTAssertEqual(Set(marks.map(\.basis)), [basis(session, seq: 2)])
        XCTAssertEqual(Set(marks.map(\.probability)), ["0.7"], "the repeated value keeps its own identity")

        // Another session's preview and a replay: receipts only, nothing printed moves.
        marks = []
        shown = next
        let other = V3PageWire.nextSession()
        handle.fire("preview_v3", V3PageWire.preview(Self.previewFrame(seq: 3, p: 0.8, at: t1), eventId: 4242, session: other))
        handle.fire("preview_v3", V3PageWire.preview(Self.previewFrame(seq: 1, p: 0.9, at: t1), eventId: 4242, session: session))
        next = vm.timingPresented(try XCTUnwrap(vm.event))
        LiveTimingSeam.viewUpdated(from: shown, to: next)
        XCTAssertEqual(names(marks), [.previewReceived, .previewReceived])
        XCTAssertEqual(marks.map(\.basis), [basis(other, seq: 3), basis(session, seq: 1)])
        XCTAssertEqual(next, shown, "a refused preview changes nothing the page prints")

        // A newer committed revision outranks the held preview: the hero and
        // chart fall back to committed truth under its own basis.
        marks = []
        shown = next
        handle.fire("probability", Self.raw())
        await drain()
        next = vm.timingPresented(try XCTUnwrap(vm.event))
        LiveTimingSeam.viewUpdated(from: shown, to: next)
        let committed = LiveTimingSeam.stamp(try XCTUnwrap("2026-09-25T17:10:00Z".asDate))
        XCTAssertEqual(names(marks), [.frameReceived, .modelChartAppended, .modelHeadlineAdopted,
                                      .viewHeadlineUpdated, .viewChartUpdated])
        XCTAssertEqual(marks[3], .init(name: .viewHeadlineUpdated, eventId: 4242, path: "view", basis: "rev:4242=21",
                                       stamp: "-", probability: "0.55", observed: committed))
        XCTAssertEqual(marks[4], .init(name: .viewChartUpdated, eventId: 4242, path: "view", basis: "rev:4242=21",
                                       stamp: committed, probability: "0.55", observed: committed))
    }

    /// An expired preview gives way to the committed headline without a frame;
    /// the view names the committed basis again.
    func testAnExpiredPreviewHandsTheHeroBackToItsCommittedBasis() async throws {
        let (_, handle, vm) = try await loaded(try page())
        defer { vm.stopRefresh() }
        let session = openV3(handle)
        handle.fire("preview_v3", V3PageWire.preview(
            Self.previewFrame(seq: 1, p: 0.7, at: "2026-09-25T17:00:05Z", ttl: 150), eventId: 4242, session: session))
        let shown = vm.timingPresented(try XCTUnwrap(vm.event))
        XCTAssertEqual(shown.headlineBasis, basis(session, seq: 1))
        let deadline = Date().addingTimeInterval(3)
        while vm.blendPreview != nil, Date() < deadline { try await Task.sleep(nanoseconds: 20_000_000) }
        XCTAssertNil(vm.blendPreview, "the preview expired")
        marks = []
        let next = vm.timingPresented(try XCTUnwrap(vm.event))
        LiveTimingSeam.viewUpdated(from: shown, to: next)
        XCTAssertEqual(marks.first, .init(name: .viewHeadlineUpdated, eventId: 4242, path: "view", basis: "rev:4242=20",
                                          stamp: "-", probability: "0.6",
                                          observed: LiveTimingSeam.stamp(try XCTUnwrap("2026-09-25T17:00:00Z".asDate))))
        // No pushed point to fall back to: the line ends on the read's own
        // last point again, named as served (the read gives it no identity).
        XCTAssertEqual(Array(marks.dropFirst()), [
            .init(name: .viewChartUpdated, eventId: 4242, path: "view", basis: "served:none",
                  stamp: LiveTimingSeam.stamp(try XCTUnwrap("2026-09-25T16:59:00Z".asDate)), probability: "0.6"),
        ], "the chart falls back to the served line, never to the expired preview")
    }

    /// A folded v2 preview for this page on `session`: `p` observed at `at`,
    /// the page and its sibling at the fold's committed base.
    private static func foldedPreviewFrame(session: String, seq: Int, p: Double, at: String) -> String {
        #"{"event_id":4242,"p":\#(p),"p_away":\#(1 - p),"sport":"basketball_nba","status":"live","display_observed_at":"\#(at)","preview":{"kind":"blend","folded_version":2,"fold_session":"\#(session)","fold_seq":\#(seq),"ttl_ms":60000,"base_fold_revision":\#(folded),"origin_authority":{"4242":{"epoch":2,"seq":\#(seq),"state":"pending","ttl_ms":60000}}}}"#
    }

    /// The identity a folded v2 preview holds: no epoch of its own, its
    /// `fold_seq`, the page row's revision, its fold session and complete base.
    private func foldedBasis(_ session: String, seq: Int) -> String {
        "v3:1/\(Self.namespace)/\(session)/e0/s\(seq)/b20/f\(session)/m4242=20;999=5"
    }

    /// Folded v2 frames carry no epoch or sequence of their own: receipt,
    /// adoption and both view marks must still name each one by its
    /// `fold_seq` and complete base, so two sequences printing the SAME value
    /// stay two identities that join stage to stage — and a replay or another
    /// session's frame is a receipt that joins nothing.
    func testTwoFoldedV2PreviewsOfOneValueKeepTheirOwnIdentityFromReceiptToHeroAndChart() async throws {
        let (_, handle, vm) = try await loaded(try page(revision: Self.folded))
        defer { vm.stopRefresh() }
        let session = V3PageWire.nextSession()
        handle.fire("preview_open_v3", V3PageWire.open(4242, members: [4242, 999], session: session))
        var shown = vm.timingPresented(try XCTUnwrap(vm.event))
        XCTAssertEqual(marks, [], "an open shows nothing")
        let at = "2026-09-25T17:00:05Z", atStamp = LiveTimingSeam.stamp(try XCTUnwrap(at.asDate))

        for seq in [1, 2] {
            marks = []
            handle.fire("preview_v3", V3PageWire.preview(
                Self.foldedPreviewFrame(session: session, seq: seq, p: 0.7, at: at), eventId: 4242, session: session))
            let next = vm.timingPresented(try XCTUnwrap(vm.event))
            LiveTimingSeam.viewUpdated(from: shown, to: next)
            shown = next
            let id = foldedBasis(session, seq: seq)
            XCTAssertEqual(marks, [
                .init(name: .previewReceived, eventId: 4242, path: "preview", basis: id, stamp: "-",
                      probability: "0.7", observed: atStamp),
                .init(name: .modelPreviewAdopted, eventId: 4242, path: "preview", basis: id, stamp: "-",
                      probability: "0.7", observed: atStamp),
                .init(name: .viewHeadlineUpdated, eventId: 4242, path: "view", basis: id, stamp: "-",
                      probability: "0.7", observed: atStamp),
                .init(name: .viewChartUpdated, eventId: 4242, path: "view", basis: id, stamp: atStamp,
                      probability: "0.7", observed: atStamp),
            ], "fold_seq \(seq): one identity from receipt to the hero and the chart")
        }
        XCTAssertNotEqual(foldedBasis(session, seq: 1), foldedBasis(session, seq: 2))

        // A replay of fold_seq 1 and another session's frame: receipts under
        // their own names, nothing adopted, nothing printed moves.
        marks = []
        let other = V3PageWire.nextSession()
        handle.fire("preview_v3", V3PageWire.preview(
            Self.foldedPreviewFrame(session: session, seq: 1, p: 0.9, at: at), eventId: 4242, session: session))
        handle.fire("preview_v3", V3PageWire.preview(
            Self.foldedPreviewFrame(session: other, seq: 3, p: 0.8, at: at), eventId: 4242, session: other))
        let next = vm.timingPresented(try XCTUnwrap(vm.event))
        LiveTimingSeam.viewUpdated(from: shown, to: next)
        XCTAssertEqual(names(marks), [.previewReceived, .previewReceived])
        XCTAssertEqual(marks.map(\.basis), [foldedBasis(session, seq: 1), foldedBasis(other, seq: 3)])
        XCTAssertEqual(next, shown, "a refused preview changes nothing the page prints")
        XCTAssertEqual(next.headlineBasis, foldedBasis(session, seq: 2))
    }
}
