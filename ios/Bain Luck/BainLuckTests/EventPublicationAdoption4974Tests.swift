import Foundation
import XCTest
@testable import Bain_Luck

/// #4974 — **the event page's view model hands the finished-game chart a
/// current, validated checkpoint journey, or nothing — never a stale one, and
/// never at the price of the page itself.**
///
/// `EventDetailViewModel.adoptPublicationJourney()` is a finite call the page
/// makes; nothing in the view model calls it, polls it or observes for it. So
/// every case here drives that actual entry point through the
/// `EventDetailProviding` seam, and the race cases park the provider so the
/// test decides which read answers first. The provider IGNORES cancellation on
/// purpose: the view model's own checks are what a cancelled read has to pass.
///
/// The existing event-page fakes are each private to their own file, so this
/// file carries its own in the same shape (`EventRefreshLifecycleTests`,
/// `AGamePageReadsItsHistoryOncePerPayload8651Tests`). Nothing here touches a
/// server, a socket or the wall clock except as a timeout (gotcha #44).
///
/// Boundary: `4974-NATIVE-VM-ADOPTION-SOURCE-BOUNDARY.md`.
@MainActor
final class EventPublicationAdoption4974Tests: XCTestCase {

    private static let eventID = 4242

    // MARK: - Fixtures

    private static func decoder() -> JSONDecoder {
        let decoder = JSONDecoder()
        decoder.keyDecodingStrategy = .convertFromSnakeCase
        return decoder
    }

    /// A detail with a price and a source label, so "the price did not move"
    /// is a claim about a value and not about a nil.
    private func event(id: Int = 4242, status: String?) throws -> EventDetail {
        let statusField = status.map { "\"\($0)\"" } ?? "null"
        return try Self.decoder().decode(EventDetail.self, from: Data("""
        {"id": \(id), "home_team": "Red Sox", "away_team": "Yankees",
         "status": \(statusField), "commence_time": "2026-10-04T17:05:00Z",
         "home_score": 5, "away_score": 3,
         "current_odds": {"home_probability": 0.62, "away_probability": 0.38},
         "hero_probability_source": "blend"}
        """.utf8))
    }

    private func history() throws -> EventHistoryResponse {
        try Self.decoder().decode(EventHistoryResponse.self, from: Data("""
        {"event_id": \(Self.eventID), "home_team": "Red Sox", "away_team": "Yankees",
         "history": [{"timestamp": "2026-10-04T17:00:00Z", "home_probability": 0.55},
                     {"timestamp": "2026-10-04T20:00:00Z", "home_probability": 0.62}]}
        """.utf8))
    }

    private func vertex(_ rev: Int64, _ t: String, _ p: Double) -> PublicationCheckpointVertex {
        PublicationCheckpointVertex(rev: rev, t: t, p: p)
    }

    /// Two adoptable bodies that cannot be mistaken for each other, so a race
    /// case can say WHICH read the page is holding.
    private var olderVertices: [PublicationCheckpointVertex] {
        [vertex(3, "2026-10-04T18:00:00+00:00", 0.51), vertex(5, "2026-10-04T18:30:00+00:00", 0.49)]
    }
    private var newerVertices: [PublicationCheckpointVertex] {
        [vertex(7, "2026-10-04T20:15:10+00:00", 0.61), vertex(9, "2026-10-04T20:15:50+00:00", 0.58)]
    }

    private func body(
        eventId: Int = 4242,
        schemaVersion: Int = 1,
        timeBasis: String = "recorded_at_insert_before_commit",
        truncated: Bool = false,
        vertices: [PublicationCheckpointVertex]? = nil
    ) -> PublicationCheckpointsResponse {
        PublicationCheckpointsResponse(
            eventId: eventId, schemaVersion: schemaVersion, timeBasis: timeBasis,
            truncated: truncated, vertices: vertices ?? newerVertices
        )
    }

    /// What the strict contract itself makes of `response` — the expected
    /// value is computed by `adopt`, never re-derived here.
    private func journey(_ response: PublicationCheckpointsResponse) throws -> PublicationJourney4974.Journey {
        try PublicationJourney4974.adopt(response, expectedEventID: Self.eventID, finished: true).get()
    }

    // MARK: - Fakes

    private enum Reply {
        case serve(PublicationCheckpointsResponse)
        case fail(Error)
    }

    /// Serves one detail (replaceable) and one history, refuses the other
    /// secondary reads, and answers checkpoint reads either at once (`answerAll`)
    /// or by parking each until the test answers it — in any order.
    private nonisolated final class Client: EventDetailProviding, @unchecked Sendable {
        struct Declined: Error {}
        private let lock = NSLock()
        private var detail: EventDetail
        private let historyBody: EventHistoryResponse?
        private var immediate: Reply?
        private var parked: [CheckedContinuation<PublicationCheckpointsResponse, Error>?] = []
        private var asked: [Int] = []

        init(detail: EventDetail, history: EventHistoryResponse? = nil, answerAll: Reply? = nil) {
            self.detail = detail
            self.historyBody = history
            self.immediate = answerAll
        }

        func serveDetail(_ next: EventDetail) { lock.withLock { detail = next } }
        /// `nil` parks every later read until `answer(_:with:)`.
        func answerAll(_ reply: Reply?) { lock.withLock { immediate = reply } }
        var publicationRequests: [Int] { lock.withLock { asked } }
        var parkedCount: Int { lock.withLock { parked.count } }

        func answer(_ index: Int, with reply: Reply) {
            let continuation: CheckedContinuation<PublicationCheckpointsResponse, Error>? = lock.withLock {
                defer { parked[index] = nil }
                return parked[index]
            }
            switch reply {
            case .serve(let response): continuation?.resume(returning: response)
            case .fail(let error): continuation?.resume(throwing: error)
            }
        }

        func fetchEventPublications(id: Int) async throws -> PublicationCheckpointsResponse {
            let now: Reply? = lock.withLock {
                asked.append(id)
                return immediate
            }
            if let now {
                switch now {
                case .serve(let response): return response
                case .fail(let error): throw error
                }
            }
            // Deliberately deaf to cancellation: nothing here resumes early.
            return try await withCheckedThrowingContinuation { continuation in
                lock.withLock { parked.append(continuation) }
            }
        }

        func fetchEvent(id: Int) async throws -> EventDetail { lock.withLock { detail } }
        func fetchEventHistory(id: Int, hours: Int) async throws -> EventHistoryResponse {
            guard let historyBody else { throw Declined() }
            return historyBody
        }
        func fetchRelatedFutures(eventId: Int) async throws -> RelatedFuturesResponse { throw Declined() }
        func fetchTeamProgression(eventId: Int) async throws -> TeamProgressionResponse { throw Declined() }
        func fetchGameMarkets(eventId: Int) async throws -> GameMarketsResponse { throw Declined() }
        func fetchFreshGameMarkets(eventId: Int) async throws -> GameMarketsResponse { throw Declined() }
        func fetchLineMovement(eventId: Int) async throws -> LineMovementResponse { throw Declined() }
    }

    /// An existing provider written before #4974: it never mentions checkpoints,
    /// so it gets the protocol's default.
    private nonisolated final class PreCheckpointClient: EventDetailProviding, @unchecked Sendable {
        struct Declined: Error {}
        let detail: EventDetail
        init(detail: EventDetail) { self.detail = detail }
        func fetchEvent(id: Int) async throws -> EventDetail { detail }
        func fetchEventHistory(id: Int, hours: Int) async throws -> EventHistoryResponse { throw Declined() }
        func fetchRelatedFutures(eventId: Int) async throws -> RelatedFuturesResponse { throw Declined() }
        func fetchTeamProgression(eventId: Int) async throws -> TeamProgressionResponse { throw Declined() }
        func fetchGameMarkets(eventId: Int) async throws -> GameMarketsResponse { throw Declined() }
        func fetchLineMovement(eventId: Int) async throws -> LineMovementResponse { throw Declined() }
    }

    /// For a page that goes live: the stream needs a handle and the poll a
    /// sleep. Neither is exercised; both are torn down by `stopRefresh()`.
    private final class QuietHandle: LiveStreamHandle, @unchecked Sendable {
        var isClosed = false
        func on(_ event: String, _ handler: @escaping @MainActor (String) -> Void) {}
        func close() { isClosed = true }
    }

    /// Stubs the server for the real `APIClient`, test-local (no global
    /// registration, no network).
    private nonisolated final class PublicationsOrigin: URLProtocol, @unchecked Sendable {
        private static let lock = NSLock()
        nonisolated(unsafe) private static var paths: [String] = []
        static func reset() { lock.withLock { paths = [] } }
        static var requested: [String] { lock.withLock { paths } }

        override class func canInit(with request: URLRequest) -> Bool { true }
        override class func canonicalRequest(for request: URLRequest) -> URLRequest { request }
        override func startLoading() {
            Self.lock.withLock { Self.paths.append(request.url?.path ?? "") }
            let body = Data("""
            {"event_id":4242,"schema_version":1,"time_basis":"recorded_at_insert_before_commit",\
            "truncated":false,"vertices":[{"rev":7,"t":"2026-10-04T20:15:10+00:00","p":0.61},\
            {"rev":9,"t":"2026-10-04T20:15:50+00:00","p":0.58}]}
            """.utf8)
            let response = HTTPURLResponse(url: request.url!, statusCode: 200, httpVersion: "HTTP/1.1",
                                           headerFields: ["Content-Type": "application/json"])!
            client?.urlProtocol(self, didReceive: response, cacheStoragePolicy: .notAllowed)
            client?.urlProtocol(self, didLoad: body)
            client?.urlProtocolDidFinishLoading(self)
        }
        override func stopLoading() {}
    }

    private func makeVM(client: EventDetailProviding) -> EventDetailViewModel {
        EventDetailViewModel(
            eventId: Self.eventID,
            client: client,
            makeStreamHandle: { _ in QuietHandle() },
            now: { 1_791_150_000 },
            sleep: { seconds in try? await Task.sleep(nanoseconds: UInt64(seconds * 1_000_000_000)) }
        )
    }

    /// A finished page that has loaded once, its main state settled.
    private func loadedFinishedPage(
        _ client: Client, status: String = "completed"
    ) async throws -> EventDetailViewModel {
        let vm = makeVM(client: client)
        await vm.load()
        XCTAssertEqual(vm.event?.status, status, "fixture: the page holds a finished game")
        XCTAssertEqual(client.publicationRequests, [], "fixture: load() never asks for checkpoints")
        return vm
    }

    /// Bounded spin. The wall clock is a TIMEOUT here, never an assertion anchor.
    private func waitUntil(
        _ description: String, timeout: TimeInterval = 3, _ condition: @MainActor () -> Bool
    ) async {
        let deadline = Date().addingTimeInterval(timeout)
        while Date() < deadline {
            if condition() { return }
            await Task.yield()
            try? await Task.sleep(nanoseconds: 200_000)
        }
        XCTFail("timed out waiting for: \(description)")
    }

    /// Every main-page field the checkpoint call must leave alone.
    private nonisolated struct PageState: Equatable {
        let loading: Bool
        let error: String?
        let lastLoadedAt: Date?
        let priceActivity: LivePriceActivity?
        let homeProbability: Double?
        let heroSource: String?
        let status: String?
        let eventID: Int?
        let historyPoints: Int?
        let historyArrivedAt: Date?
        let pricePairRefreshFailed: Bool
        let isAutoRefreshing: Bool
        let plan: EventRefreshPlan?
        let streamDelivering: Bool
        let streamHasPushedPrice: Bool
        let liveBlendCount: Int

        @MainActor init(_ vm: EventDetailViewModel) {
            loading = vm.loading
            error = vm.error
            lastLoadedAt = vm.lastLoadedAt
            priceActivity = vm.priceActivity
            homeProbability = vm.event?.currentOdds?.homeProbability
            heroSource = vm.event?.heroProbabilitySource
            status = vm.event?.status
            eventID = vm.event?.id
            historyPoints = vm.history?.history.count
            historyArrivedAt = vm.historyArrivedAt
            pricePairRefreshFailed = vm.pricePairRefreshFailed
            isAutoRefreshing = vm.isAutoRefreshing
            plan = vm.currentRefreshPlan
            streamDelivering = vm.streamDelivering
            streamHasPushedPrice = vm.streamHasPushedPrice
            liveBlendCount = vm.liveBlend.count
        }
    }

    // MARK: - Who asks at all

    func testAPageWithNoEventYetMakesNoRequestAndHoldsNothing() async throws {
        let client = Client(detail: try event(status: "completed"), answerAll: .serve(body()))
        let vm = makeVM(client: client)
        XCTAssertNil(vm.event)

        await vm.adoptPublicationJourney()

        XCTAssertEqual(client.publicationRequests, [], "no event, no request")
        XCTAssertNil(vm.publicationJourney)
    }

    func testUpcomingLiveAndUnknownPagesMakeNoRequest() async throws {
        for status in ["scheduled", "live", "suspended", "postponed", nil] as [String?] {
            let client = Client(detail: try event(status: status), answerAll: .serve(body()))
            let vm = makeVM(client: client)
            await vm.load()
            XCTAssertEqual(vm.event?.status, status, "fixture")

            await vm.adoptPublicationJourney()

            XCTAssertEqual(client.publicationRequests, [], "\(status ?? "nil") is not finished; nothing asked")
            XCTAssertNil(vm.publicationJourney, "\(status ?? "nil") holds no checkpoint journey")
            vm.stopRefresh()
        }
    }

    /// The page holds a different game's detail than the id it was opened for
    /// (a canonical re-key): an honest refusal, never a silent re-key.
    func testADetailForAnotherEventIdRefusesWithoutARequest() async throws {
        let client = Client(detail: try event(id: 9999, status: "completed"), answerAll: .serve(body()))
        let vm = makeVM(client: client)
        await vm.load()
        XCTAssertEqual(vm.event?.id, 9999, "fixture: the served detail is another id")

        await vm.adoptPublicationJourney()

        XCTAssertEqual(client.publicationRequests, [])
        XCTAssertNil(vm.publicationJourney)
    }

    /// The call is the ONLY path: loads, re-loads and a resume never ask.
    func testLoadingTheFinishedPageNeverAsksForCheckpoints() async throws {
        let client = Client(detail: try event(status: "completed"), history: try history(),
                            answerAll: .serve(body()))
        let vm = makeVM(client: client)
        await vm.load()
        await vm.load()
        XCTAssertNil(vm.scenePhaseChanged(to: .background, pageVisible: true))
        let resumed = try XCTUnwrap(vm.scenePhaseChanged(to: .active, pageVisible: true))
        await resumed.value

        XCTAssertEqual(client.publicationRequests, [], "no existing method was hooked")
        XCTAssertNil(vm.publicationJourney)
    }

    // MARK: - Adoption

    func testAFinishedPageAdoptsItsOwnJourney() async throws {
        for status in ["completed", "closed"] {
            let served = body()
            let client = Client(detail: try event(status: status), answerAll: .serve(served))
            let vm = try await loadedFinishedPage(client, status: status)

            await vm.adoptPublicationJourney()

            XCTAssertEqual(client.publicationRequests, [Self.eventID], "\(status): one read, for this event")
            XCTAssertEqual(vm.publicationJourney, try journey(served), "\(status): adopted whole")
            XCTAssertEqual(vm.publicationJourney?.checkpoints.map(\.vertex), served.vertices)
        }
    }

    /// Each refusal starts from a page already HOLDING an adopted journey, so
    /// "nil afterwards" proves the old one was cleared, not merely never set.
    func testARefusedBodyLeavesNoJourney() async throws {
        let refused: [(String, PublicationCheckpointsResponse)] = [
            ("empty (recording off)", body(vertices: [])),
            ("one vertex", body(vertices: [vertex(7, "2026-10-04T20:15:10+00:00", 0.61)])),
            ("wrong event", body(eventId: 9999)),
            ("truncated", body(truncated: true, vertices: [])),
            ("truncated with rows", body(truncated: true)),
            ("unknown schema", body(schemaVersion: 2)),
            ("unknown time basis", body(timeBasis: "published_at")),
            ("malformed stamp", body(vertices: [vertex(7, "2026-10-04 20:15:10", 0.61),
                                               vertex(9, "2026-10-04T20:15:50+00:00", 0.58)])),
            ("probability out of range", body(vertices: [vertex(7, "2026-10-04T20:15:10+00:00", 1.2),
                                                        vertex(9, "2026-10-04T20:15:50+00:00", 0.58)])),
            ("revisions out of order", body(vertices: [vertex(9, "2026-10-04T20:15:10+00:00", 0.61),
                                                      vertex(7, "2026-10-04T20:15:50+00:00", 0.58)]))
        ]
        for (name, response) in refused {
            if case .success = PublicationJourney4974.adopt(response, expectedEventID: Self.eventID, finished: true) {
                XCTFail("fixture \(name) must be one the strict contract refuses")
            }
            let client = Client(detail: try event(status: "completed"), answerAll: .serve(body()))
            let vm = try await loadedFinishedPage(client)
            await vm.adoptPublicationJourney()
            XCTAssertNotNil(vm.publicationJourney, "\(name): fixture holds a journey first")

            client.answerAll(.serve(response))
            await vm.adoptPublicationJourney()

            XCTAssertNil(vm.publicationJourney, "\(name): refused whole, old journey gone")
            XCTAssertNil(vm.error, "\(name): a refusal is not a page error")
        }
    }

    /// A transport failure or an undecodable body: no journey, no page error,
    /// and the normal chart path (history) untouched.
    func testAFailedReadRaisesNoPageErrorAndLeavesTheChartPathAlone() async throws {
        let undecodable: Error
        do {
            _ = try Self.decoder().decode(PublicationCheckpointsResponse.self,
                                          from: Data(#"{"event_id":"4242"}"#.utf8))
            XCTFail("fixture: that body must not decode")
            return
        } catch { undecodable = error }

        for (name, failure) in [("offline", URLError(.notConnectedToInternet) as Error),
                                ("server error", URLError(.badServerResponse) as Error),
                                ("undecodable", undecodable)] {
            let client = Client(detail: try event(status: "completed"), history: try history(),
                                answerAll: .serve(body()))
            let vm = try await loadedFinishedPage(client)
            await vm.adoptPublicationJourney()
            XCTAssertNotNil(vm.publicationJourney, "\(name): fixture holds a journey first")
            let before = PageState(vm)

            client.answerAll(.fail(failure))
            await vm.adoptPublicationJourney()

            XCTAssertNil(vm.publicationJourney, "\(name): no checkpoint journey")
            XCTAssertNil(vm.error, "\(name): the page shows no error for a chart enhancement")
            XCTAssertEqual(PageState(vm), before, "\(name): main page untouched")
            XCTAssertEqual(vm.history?.history.count, 2, "\(name): the normal chart path still has its history")
        }
    }

    /// Success, refusal and failure each leave every main-page field as it was.
    func testTheMainPageIsUnchangedByEveryOutcome() async throws {
        let client = Client(detail: try event(status: "completed"), history: try history(),
                            answerAll: .serve(body()))
        let vm = try await loadedFinishedPage(client)
        let before = PageState(vm)
        XCTAssertEqual(before.homeProbability, 0.62, "fixture: a real price on the page")
        XCTAssertEqual(before.heroSource, "blend")
        XCTAssertEqual(before.historyPoints, 2)
        XCTAssertNotNil(before.lastLoadedAt)

        await vm.adoptPublicationJourney()
        XCTAssertNotNil(vm.publicationJourney)
        XCTAssertEqual(PageState(vm), before, "success")

        client.answerAll(.serve(body(truncated: true, vertices: [])))
        await vm.adoptPublicationJourney()
        XCTAssertNil(vm.publicationJourney)
        XCTAssertEqual(PageState(vm), before, "refusal")

        client.answerAll(.fail(URLError(.timedOut)))
        await vm.adoptPublicationJourney()
        XCTAssertNil(vm.publicationJourney)
        XCTAssertEqual(PageState(vm), before, "failure")
    }

    // MARK: - Last request wins

    /// The newer read answers first and is adopted; the older one answers
    /// later with a different, perfectly adoptable body and must not replace it.
    func testADelayedOlderResponseNeverReplacesTheNewerAcceptedOne() async throws {
        let client = Client(detail: try event(status: "completed"))
        let vm = try await loadedFinishedPage(client)

        let older = Task { @MainActor in await vm.adoptPublicationJourney() }
        await waitUntil("older read parked") { client.parkedCount == 1 }
        let newer = Task { @MainActor in await vm.adoptPublicationJourney() }
        await waitUntil("newer read parked") { client.parkedCount == 2 }

        client.answer(1, with: .serve(body(vertices: newerVertices)))
        await newer.value
        XCTAssertEqual(vm.publicationJourney, try journey(body(vertices: newerVertices)))

        client.answer(0, with: .serve(body(vertices: olderVertices)))
        await older.value
        XCTAssertEqual(vm.publicationJourney, try journey(body(vertices: newerVertices)),
                       "the superseded read published nothing")
        XCTAssertEqual(client.publicationRequests, [Self.eventID, Self.eventID])
    }

    /// The older read answers FIRST, while the newer is still out: it is
    /// already superseded, so the page shows nothing until the newer answers.
    func testAnOlderResponseArrivingFirstIsNotShownInTheMeantime() async throws {
        let client = Client(detail: try event(status: "completed"))
        let vm = try await loadedFinishedPage(client)

        let older = Task { @MainActor in await vm.adoptPublicationJourney() }
        await waitUntil("older read parked") { client.parkedCount == 1 }
        let newer = Task { @MainActor in await vm.adoptPublicationJourney() }
        await waitUntil("newer read parked") { client.parkedCount == 2 }

        client.answer(0, with: .serve(body(vertices: olderVertices)))
        await older.value
        XCTAssertNil(vm.publicationJourney, "a superseded success is never shown, not even briefly")

        client.answer(1, with: .serve(body(vertices: newerVertices)))
        await newer.value
        XCTAssertEqual(vm.publicationJourney, try journey(body(vertices: newerVertices)))
    }

    /// A stale FAILURE cannot clear a newer success either.
    func testASupersededFailureDoesNotClearTheNewerJourney() async throws {
        let client = Client(detail: try event(status: "completed"))
        let vm = try await loadedFinishedPage(client)

        let older = Task { @MainActor in await vm.adoptPublicationJourney() }
        await waitUntil("older read parked") { client.parkedCount == 1 }
        let newer = Task { @MainActor in await vm.adoptPublicationJourney() }
        await waitUntil("newer read parked") { client.parkedCount == 2 }

        client.answer(1, with: .serve(body()))
        await newer.value
        let accepted = try journey(body())
        XCTAssertEqual(vm.publicationJourney, accepted)

        client.answer(0, with: .fail(URLError(.timedOut)))
        await older.value
        XCTAssertEqual(vm.publicationJourney, accepted, "the stale failure returned before any clear")
        XCTAssertNil(vm.error)
    }

    /// A new attempt clears the old journey BEFORE its network wait: the page
    /// never shows the previous answer while the next is in flight.
    func testANewAttemptClearsTheOldJourneyBeforeItsReadReturns() async throws {
        let client = Client(detail: try event(status: "completed"), answerAll: .serve(body()))
        let vm = try await loadedFinishedPage(client)
        await vm.adoptPublicationJourney()
        XCTAssertNotNil(vm.publicationJourney)

        client.answerAll(nil)
        let next = Task { @MainActor in await vm.adoptPublicationJourney() }
        await waitUntil("next read parked") { client.parkedCount == 1 }
        XCTAssertNil(vm.publicationJourney, "cleared while the read is still out")

        client.answer(0, with: .serve(body(vertices: olderVertices)))
        await next.value
        XCTAssertEqual(vm.publicationJourney, try journey(body(vertices: olderVertices)))
    }

    // MARK: - Cancellation

    /// The provider ignores cancellation and answers with a valid body anyway.
    /// The view model's own check after the await is what refuses it.
    func testACancelledReadPublishesNothingEvenIfTheProviderAnswers() async throws {
        let client = Client(detail: try event(status: "completed"))
        let vm = try await loadedFinishedPage(client)

        let read = Task { @MainActor in await vm.adoptPublicationJourney() }
        await waitUntil("read parked") { client.parkedCount == 1 }
        read.cancel()
        client.answer(0, with: .serve(body()))
        await read.value

        XCTAssertNil(vm.publicationJourney, "a cancelled read never publishes")
        XCTAssertNil(vm.error)
    }

    /// A call that is already cancelled when it starts returns at once: no
    /// request, and the newer result already on the page stays.
    func testAnAlreadyCancelledCallKeepsTheJourneyAlreadyAccepted() async throws {
        let client = Client(detail: try event(status: "completed"), answerAll: .serve(body()))
        let vm = try await loadedFinishedPage(client)
        await vm.adoptPublicationJourney()
        let accepted = try journey(body())
        XCTAssertEqual(vm.publicationJourney, accepted)

        let cancelled = Task { @MainActor in
            withUnsafeCurrentTask { $0?.cancel() }
            await vm.adoptPublicationJourney()
        }
        await cancelled.value

        XCTAssertEqual(client.publicationRequests, [Self.eventID], "the cancelled call asked nothing")
        XCTAssertEqual(vm.publicationJourney, accepted, "and replaced nothing")
    }

    /// An already-cancelled call takes no generation, so a read still out from
    /// a live call is not superseded by it.
    func testAnAlreadyCancelledCallDoesNotSupersedeALiveRead() async throws {
        let client = Client(detail: try event(status: "completed"))
        let vm = try await loadedFinishedPage(client)

        let live = Task { @MainActor in await vm.adoptPublicationJourney() }
        await waitUntil("live read parked") { client.parkedCount == 1 }
        let cancelled = Task { @MainActor in
            withUnsafeCurrentTask { $0?.cancel() }
            await vm.adoptPublicationJourney()
        }
        await cancelled.value
        XCTAssertEqual(client.parkedCount, 1, "the cancelled call made no request")

        client.answer(0, with: .serve(body()))
        await live.value
        XCTAssertEqual(vm.publicationJourney, try journey(body()))
    }

    // MARK: - Eligibility changes

    /// The page stops being finished while a read is out, and the caller has
    /// not re-invoked yet: the recheck before adoption refuses the answer.
    func testAPageThatStopsBeingFinishedMidReadAdoptsNothing() async throws {
        let client = Client(detail: try event(status: "completed"))
        let vm = try await loadedFinishedPage(client)
        defer { vm.stopRefresh() }

        let read = Task { @MainActor in await vm.adoptPublicationJourney() }
        await waitUntil("read parked") { client.parkedCount == 1 }
        client.serveDetail(try event(status: "live"))
        await vm.load()
        XCTAssertEqual(vm.event?.status, "live", "fixture: the page left finished")

        client.answer(0, with: .serve(body()))
        await read.value
        XCTAssertNil(vm.publicationJourney, "never reintroduced on a page that is no longer finished")
    }

    /// The caller's ineligible invocation while a read is out supersedes it.
    func testAnIneligibleInvocationSupersedesARead() async throws {
        let client = Client(detail: try event(status: "completed"))
        let vm = try await loadedFinishedPage(client)
        defer { vm.stopRefresh() }

        let read = Task { @MainActor in await vm.adoptPublicationJourney() }
        await waitUntil("read parked") { client.parkedCount == 1 }
        client.serveDetail(try event(status: "live"))
        await vm.load()
        await vm.adoptPublicationJourney()
        XCTAssertEqual(client.publicationRequests, [Self.eventID], "the ineligible call asked nothing")

        // Flip back to finished before the stale read lands: only the
        // generation can refuse it now, not the eligibility recheck.
        client.serveDetail(try event(status: "completed"))
        await vm.load()
        client.answer(0, with: .serve(body()))
        await read.value
        XCTAssertNil(vm.publicationJourney, "the superseded read published nothing")
    }

    /// The page's detail turns into another event's while a read is out.
    func testADetailRekeyedMidReadAdoptsNothing() async throws {
        let client = Client(detail: try event(status: "completed"))
        let vm = try await loadedFinishedPage(client)

        let read = Task { @MainActor in await vm.adoptPublicationJourney() }
        await waitUntil("read parked") { client.parkedCount == 1 }
        client.serveDetail(try event(id: 9999, status: "completed"))
        await vm.load()
        XCTAssertEqual(vm.event?.id, 9999, "fixture")

        client.answer(0, with: .serve(body()))
        await read.value
        XCTAssertNil(vm.publicationJourney, "requested and canonical ids are not treated as one game")
    }

    /// THE CALLER CONTRACT, pinned. The view model hooks nothing, so a status
    /// change through `load()` alone does NOT clear the optional — the page's
    /// ineligible invocation does, without a request. (Downstream, the chart
    /// checks finished and identity itself before using it.)
    func testOnlyTheCallersInvocationClearsAJourneyAfterTheStatusChanges() async throws {
        let client = Client(detail: try event(status: "completed"), answerAll: .serve(body()))
        let vm = try await loadedFinishedPage(client)
        defer { vm.stopRefresh() }
        await vm.adoptPublicationJourney()
        let accepted = try journey(body())
        XCTAssertEqual(vm.publicationJourney, accepted)

        client.serveDetail(try event(status: "live"))
        await vm.load()
        XCTAssertEqual(vm.event?.status, "live", "fixture")
        XCTAssertEqual(vm.publicationJourney, accepted,
                       "load() is not hooked: the stored optional is stale until the caller invokes")
        XCTAssertEqual(client.publicationRequests, [Self.eventID])

        await vm.adoptPublicationJourney()
        XCTAssertNil(vm.publicationJourney, "the ineligible invocation clears it")
        XCTAssertEqual(client.publicationRequests, [Self.eventID], "and asks nothing")
    }

    // MARK: - The seam

    /// A provider written before #4974 refuses by throwing — it never answers
    /// with an empty success body the page could mistake for a server's word.
    func testTheProtocolDefaultRefusesByThrowing() async throws {
        let provider: EventDetailProviding = PreCheckpointClient(detail: try event(status: "completed"))
        do {
            let response = try await provider.fetchEventPublications(id: Self.eventID)
            XCTFail("the default must throw, not synthesize \(response)")
        } catch {
            XCTAssertEqual(error as? EventPublicationsUnsupported, EventPublicationsUnsupported())
        }

        let vm = makeVM(client: provider)
        await vm.load()
        XCTAssertEqual(vm.event?.status, "completed", "fixture")
        await vm.adoptPublicationJourney()
        XCTAssertNil(vm.publicationJourney)
        XCTAssertNil(vm.error, "an unsupported provider is not a page error")
    }

    /// APIClient's own method — not the refusing default — answers through the
    /// seam. A drifted signature would silently fall to the default and every
    /// production page would refuse; this is what catches that.
    func testAPIClientIsTheProductionWitness() async throws {
        PublicationsOrigin.reset()
        let configuration = URLSessionConfiguration.ephemeral
        configuration.protocolClasses = [PublicationsOrigin.self]
        let provider: EventDetailProviding = APIClient(session: URLSession(configuration: configuration))

        let response = try await provider.fetchEventPublications(id: Self.eventID)

        XCTAssertEqual(response, body(vertices: newerVertices))
        XCTAssertEqual(PublicationsOrigin.requested, ["/api/events/4242/publications"])
    }
}
