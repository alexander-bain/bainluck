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
    private static let oneRow = #"{"4242":20}"#
    private static let folded = #"{"4242":20,"999":5}"#

    private var marks: [LiveTimingSeam.Mark] = []

    override func setUp() async throws {
        marks = []
        LiveTimingSeam.observer = { [weak self] in self?.marks.append($0) }
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

    @MainActor
    private final class Client: EventDetailProviding {
        struct Missing: Error {}
        var response: EventDetail
        init(_ response: EventDetail) { self.response = response }
        func fetchEvent(id: Int) async throws -> EventDetail { response }
        func fetchEventHistory(id: Int, hours: Int) async throws -> EventHistoryResponse { throw Missing() }
        func fetchRelatedFutures(eventId: Int) async throws -> RelatedFuturesResponse { throw Missing() }
        func fetchTeamProgression(eventId: Int) async throws -> TeamProgressionResponse { throw Missing() }
        func fetchGameMarkets(eventId: Int) async throws -> GameMarketsResponse { throw Missing() }
        func fetchLineMovement(eventId: Int) async throws -> LineMovementResponse { throw Missing() }
    }

    private func loaded(_ held: EventDetail) async -> (Client, Handle, EventDetailViewModel) {
        let client = Client(held), handle = Handle()
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
            from: .init(eventId: 4242, revision: nil, clock: nil, chartEdge: nil),
            to: .init(eventId: 4242, revision: nil, clock: nil, chartEdge: b)
        )
        XCTAssertEqual(names(marks), [.modelChartAppended, .modelChartAppended, .viewChartUpdated])
        XCTAssertEqual(marks[0].stamp, "4740106905103354771")
        XCTAssertEqual(marks[1].stamp, "4740106905103354772")
        XCTAssertNotEqual(marks[0].stamp, marks[1].stamp)
        XCTAssertEqual(marks[2].stamp, marks[1].stamp, "the coalesced view joins only the point it carries")
    }

    // MARK: - Raw row

    func testAValidChangedFrameMarksReceiptThenModelHeadlineAndChartOnItsOwnRevision() async throws {
        let (_, handle, vm) = await loaded(try page())
        defer { vm.stopRefresh() }
        let before = LiveTimingSeam.presented(try XCTUnwrap(vm.event), liveBlend: vm.liveBlend)

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

        // The view mark names the same revision and the same chart point.
        marks = []
        let after = LiveTimingSeam.presented(try XCTUnwrap(vm.event), liveBlend: vm.liveBlend)
        LiveTimingSeam.viewUpdated(from: before, to: after)
        XCTAssertEqual(marks, [
            .init(name: .viewHeadlineUpdated, eventId: 4242, path: "view", basis: "rev:4242=21", stamp: "-"),
            .init(name: .viewChartUpdated, eventId: 4242, path: "view", basis: "-", stamp: stamp),
        ])
        marks = []
        LiveTimingSeam.viewUpdated(from: after, to: after)
        XCTAssertEqual(marks, [], "an update that changes neither emits nothing")
    }

    func testAStaleEqualInvalidOrForeignFrameLeavesOnlyItsReceipt() async throws {
        let (_, handle, vm) = await loaded(try page())
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

    // MARK: - Folded

    func testAFoldedPageMarksTheQuotesFullVectorNeverTheRawRowsRevision() async throws {
        let (_, handle, vm) = await loaded(try page(revision: Self.folded))
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
        let (client, handle, vm) = await loaded(try page())
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
    }
}
