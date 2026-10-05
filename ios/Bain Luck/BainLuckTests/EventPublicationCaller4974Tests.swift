import Foundation
import XCTest
@testable import Bain_Luck

/// #4974 — **the event page asks for a finished game's stored checkpoints once
/// per readiness, invalidates them when the game stops being eligible, and
/// hands the chart only its own finished game's journey.**
///
/// `EventDetailView` owns the caller half of the view model's contract
/// (`EventDetailViewModel.adoptPublicationJourney()`): call it when eligibility
/// changes, call it ineligible to invalidate, cancel it when the page goes.
/// The page does that with one `.task(id: publicationReadiness)` whose whole
/// body is `EventDetailView.adoptPublications(for:vm:)`, and one chart argument,
/// `EventDetailView.chartPublicationJourney(_:pageEventId:event:)`. Every case
/// here drives those exact functions, with the real view model behind them.
/// SwiftUI's own re-run and cancellation of `.task(id:)` is the framework's;
/// the cases that stand in for it say so.
///
/// The existing event-page fakes are each private to their own file, so this
/// file carries its own in the same shape (`EventPublicationAdoption4974Tests`).
/// Nothing here touches a server, a socket or the wall clock except as a
/// timeout (gotcha #44).
@MainActor
final class EventPublicationCaller4974Tests: XCTestCase {

    private typealias Readiness = EventDetailView.PublicationReadiness4974
    private static let eventID = 4242

    // MARK: - Fixtures

    private static func decoder() -> JSONDecoder {
        let decoder = JSONDecoder()
        decoder.keyDecodingStrategy = .convertFromSnakeCase
        return decoder
    }

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

    private func body(eventId: Int = 4242) -> PublicationCheckpointsResponse {
        PublicationCheckpointsResponse(
            eventId: eventId, schemaVersion: 1, timeBasis: "recorded_at_insert_before_commit",
            truncated: false,
            vertices: [PublicationCheckpointVertex(rev: 7, t: "2026-10-04T20:15:10+00:00", p: 0.61),
                       PublicationCheckpointVertex(rev: 9, t: "2026-10-04T20:15:50+00:00", p: 0.58)]
        )
    }

    /// What the strict contract itself makes of a body — computed by `adopt`,
    /// never re-derived here.
    private func journey(eventId: Int = 4242) throws -> PublicationJourney4974.Journey {
        try PublicationJourney4974.adopt(body(eventId: eventId), expectedEventID: eventId, finished: true).get()
    }

    // MARK: - Fakes

    private enum Reply {
        case serve(PublicationCheckpointsResponse)
        case fail(Error)
    }

    /// Serves one detail (replaceable) and answers checkpoint reads at once
    /// (`answerAll`) or parks each until the test answers it. Deaf to
    /// cancellation on purpose.
    private nonisolated final class Client: EventDetailProviding, @unchecked Sendable {
        struct Declined: Error {}
        private let lock = NSLock()
        private var detail: EventDetail
        private var immediate: Reply?
        private var parked: [CheckedContinuation<PublicationCheckpointsResponse, Error>?] = []
        private var asked: [Int] = []

        init(detail: EventDetail, answerAll: Reply? = nil) {
            self.detail = detail
            self.immediate = answerAll
        }

        func serveDetail(_ next: EventDetail) { lock.withLock { detail = next } }
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
            return try await withCheckedThrowingContinuation { continuation in
                lock.withLock { parked.append(continuation) }
            }
        }

        func fetchEvent(id: Int) async throws -> EventDetail { lock.withLock { detail } }
        func fetchEventHistory(id: Int, hours: Int) async throws -> EventHistoryResponse { throw Declined() }
        func fetchRelatedFutures(eventId: Int) async throws -> RelatedFuturesResponse { throw Declined() }
        func fetchTeamProgression(eventId: Int) async throws -> TeamProgressionResponse { throw Declined() }
        func fetchGameMarkets(eventId: Int) async throws -> GameMarketsResponse { throw Declined() }
        func fetchFreshGameMarkets(eventId: Int) async throws -> GameMarketsResponse { throw Declined() }
        func fetchLineMovement(eventId: Int) async throws -> LineMovementResponse { throw Declined() }
    }

    private final class QuietHandle: LiveStreamHandle, @unchecked Sendable {
        var isClosed = false
        func on(_ event: String, _ handler: @escaping @MainActor (String) -> Void) {}
        func close() { isClosed = true }
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

    /// The page's own readiness for what the view model holds now — the value
    /// its `.task(id:)` is keyed on.
    private func readiness(_ vm: EventDetailViewModel) -> Readiness {
        EventDetailView.publicationReadiness(pageEventId: Self.eventID, event: vm.event)
    }

    /// One run of the page's readiness task, exactly as the page runs it.
    private func runTask(_ vm: EventDetailViewModel) async {
        await EventDetailView.adoptPublications(for: readiness(vm), vm: vm)
    }

    /// What the page hands the chart right now.
    private func chartArgument(_ vm: EventDetailViewModel) -> PublicationJourney4974.Journey? {
        EventDetailView.chartPublicationJourney(vm.publicationJourney, pageEventId: Self.eventID, event: vm.event)
    }

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

    // MARK: - Readiness

    func testOnlyThePagesOwnFinishedGameIsEligible() throws {
        XCTAssertEqual(EventDetailView.publicationReadiness(pageEventId: Self.eventID, event: nil),
                       .ineligible, "no detail yet")
        for status in ["completed", "closed"] {
            XCTAssertEqual(
                EventDetailView.publicationReadiness(pageEventId: Self.eventID, event: try event(status: status)),
                .eligible(eventId: Self.eventID), status)
        }
        for status in ["scheduled", "live", "suspended", "postponed", "cancelled", nil] as [String?] {
            XCTAssertEqual(
                EventDetailView.publicationReadiness(pageEventId: Self.eventID, event: try event(status: status)),
                .ineligible, "\(status ?? "nil") is not finished")
        }
        XCTAssertEqual(
            EventDetailView.publicationReadiness(pageEventId: Self.eventID,
                                                 event: try event(id: 9999, status: "completed")),
            .ineligible, "another event's detail is never silently re-keyed")
    }

    /// The task key moves once per real transition and not at all within one
    /// state: `completed` → `closed` is the same finished game and is not read twice.
    func testReadinessMovesOncePerTransitionAndNotWithinAState() throws {
        let key = { (id: Int, status: String?) in
            EventDetailView.publicationReadiness(pageEventId: Self.eventID, event: try self.event(id: id, status: status))
        }
        XCTAssertEqual(try key(4242, "scheduled"), try key(4242, "live"), "not finished either way: no re-run")
        XCTAssertNotEqual(try key(4242, "live"), try key(4242, "completed"), "the game finishing re-runs")
        XCTAssertEqual(try key(4242, "completed"), try key(4242, "closed"), "finished either way: no second read")
        XCTAssertNotEqual(try key(4242, "completed"), try key(4242, "live"), "a correction back to live re-runs")
        XCTAssertNotEqual(try key(4242, "completed"), try key(9999, "completed"), "a re-keyed detail re-runs")
    }

    // MARK: - Whether a run calls the view model

    func testEveryIneligibleRunCallsAndAnEligibleRunSkipsOnlyOverItsOwnJourney() throws {
        let own = try journey()
        let other = try journey(eventId: 7777)
        XCTAssertTrue(EventDetailView.shouldAdoptPublications(.ineligible, held: nil),
                      "an ineligible run is the explicit invalidation")
        XCTAssertTrue(EventDetailView.shouldAdoptPublications(.ineligible, held: own),
                      "an ineligible run over a held journey clears it")
        XCTAssertTrue(EventDetailView.shouldAdoptPublications(.eligible(eventId: Self.eventID), held: nil),
                      "eligible with nothing held asks")
        XCTAssertFalse(EventDetailView.shouldAdoptPublications(.eligible(eventId: Self.eventID), held: own),
                       "eligible over its own journey does not read twice")
        XCTAssertTrue(EventDetailView.shouldAdoptPublications(.eligible(eventId: Self.eventID), held: other),
                      "a journey for another event is not this page's")
    }

    // MARK: - The chart argument

    func testTheChartGetsTheJourneyOnlyForThePagesOwnFinishedGame() throws {
        let own = try journey()
        XCTAssertEqual(EventDetailView.chartPublicationJourney(
            own, pageEventId: Self.eventID, event: try event(status: "completed")), own)
        XCTAssertEqual(EventDetailView.chartPublicationJourney(
            own, pageEventId: Self.eventID, event: try event(status: "closed")), own)
        XCTAssertNil(EventDetailView.chartPublicationJourney(
            nil, pageEventId: Self.eventID, event: try event(status: "completed")), "nothing held")
        XCTAssertNil(EventDetailView.chartPublicationJourney(
            own, pageEventId: Self.eventID, event: nil), "no detail")
        XCTAssertNil(EventDetailView.chartPublicationJourney(
            own, pageEventId: Self.eventID, event: try event(status: "live")),
            "a journey held from before the status changed is stale; the page withholds it")
        XCTAssertNil(EventDetailView.chartPublicationJourney(
            own, pageEventId: Self.eventID, event: try event(id: 9999, status: "completed")),
            "the page holds another event's detail")
        XCTAssertNil(EventDetailView.chartPublicationJourney(
            try journey(eventId: 7777), pageEventId: Self.eventID, event: try event(status: "completed")),
            "a journey for another event")
    }

    // MARK: - The page's lifecycle, on the real view model

    /// Appear before the detail arrives, the load finishing, the page leaving
    /// and coming back: one read in all of it.
    func testAFinishedPageReadsOnceAcrossAppearLoadAndReappear() async throws {
        let client = Client(detail: try event(status: "completed"), answerAll: .serve(body()))
        let vm = makeVM(client: client)

        // Appearance: the task's first run, before `load()` has a detail.
        XCTAssertEqual(readiness(vm), .ineligible)
        await runTask(vm)
        XCTAssertEqual(client.publicationRequests, [], "no detail yet: nothing asked")
        XCTAssertNil(chartArgument(vm))

        await vm.load()
        XCTAssertEqual(client.publicationRequests, [], "load() never asks; only the task does")
        XCTAssertEqual(readiness(vm), .eligible(eventId: Self.eventID), "the key changes, so the task re-runs")
        await runTask(vm)
        XCTAssertEqual(client.publicationRequests, [Self.eventID], "one read")
        XCTAssertEqual(chartArgument(vm), try journey(), "the chart gets the adopted journey")

        // Pull to refresh re-loads; the key does not move, so no run.
        await vm.load()
        XCTAssertEqual(readiness(vm), .eligible(eventId: Self.eventID))

        // Leaving and coming back re-runs `.task(id:)` with the same key.
        await runTask(vm)
        XCTAssertEqual(client.publicationRequests, [Self.eventID], "reappearing over its own journey: no second read")
        XCTAssertEqual(chartArgument(vm), try journey())
        vm.stopRefresh()
    }

    /// A finished game corrected back to live: the key moves, the ineligible run
    /// clears the journey without a request, and finishing again reads afresh.
    func testAGameThatStopsBeingFinishedLosesItsJourneyUntilItFinishesAgain() async throws {
        let client = Client(detail: try event(status: "completed"), answerAll: .serve(body()))
        let vm = makeVM(client: client)
        await vm.load()
        await runTask(vm)
        XCTAssertNotNil(vm.publicationJourney, "fixture: a finished page holding its journey")

        client.serveDetail(try event(status: "live"))
        await vm.load()
        XCTAssertNil(chartArgument(vm), "before the task re-runs, the page already withholds it")
        XCTAssertEqual(readiness(vm), .ineligible)
        await runTask(vm)
        XCTAssertNil(vm.publicationJourney, "the ineligible run invalidated it")
        XCTAssertEqual(client.publicationRequests, [Self.eventID], "and asked nothing")

        client.serveDetail(try event(status: "completed"))
        await vm.load()
        await runTask(vm)
        XCTAssertEqual(client.publicationRequests, [Self.eventID, Self.eventID], "finished again: read afresh")
        XCTAssertEqual(chartArgument(vm), try journey())
        vm.stopRefresh()
    }

    /// The page holding another event's detail: no read, nothing to the chart.
    func testAReKeyedDetailIsNeitherReadNorCharted() async throws {
        let client = Client(detail: try event(id: 9999, status: "completed"), answerAll: .serve(body(eventId: 9999)))
        let vm = makeVM(client: client)
        await vm.load()
        XCTAssertEqual(vm.event?.id, 9999, "fixture")

        await runTask(vm)

        XCTAssertEqual(client.publicationRequests, [])
        XCTAssertNil(chartArgument(vm))
    }

    /// A failed read leaves the chart on its normal path and the page error-free;
    /// the next readiness change, not a refresh, is what asks again.
    func testAFailedReadLeavesTheChartArgumentNilAndThePageClean() async throws {
        let client = Client(detail: try event(status: "completed"),
                            answerAll: .fail(URLError(.notConnectedToInternet)))
        let vm = makeVM(client: client)
        await vm.load()

        await runTask(vm)

        XCTAssertEqual(client.publicationRequests, [Self.eventID])
        XCTAssertNil(chartArgument(vm), "no journey: the chart draws as before")
        XCTAssertNil(vm.error, "a chart enhancement raises no page error")
        await vm.load()
        XCTAssertEqual(client.publicationRequests, [Self.eventID], "a refresh does not retry the read")
        vm.stopRefresh()
    }

    // MARK: - Cancellation (stands in for SwiftUI's `.task(id:)`)

    /// The page leaves (or its key moves) while a read is in flight: SwiftUI
    /// cancels the run. The provider answers anyway; nothing is published.
    func testACancelledRunPublishesNothingEvenIfTheProviderAnswers() async throws {
        let client = Client(detail: try event(status: "completed"))
        let vm = makeVM(client: client)
        await vm.load()

        let run = Task { @MainActor in await self.runTask(vm) }
        await waitUntil("read parked") { client.parkedCount == 1 }
        run.cancel()
        client.answer(0, with: .serve(body()))
        await run.value

        XCTAssertNil(vm.publicationJourney, "a cancelled run never publishes")
        XCTAssertNil(chartArgument(vm))
        XCTAssertNil(vm.error)
    }

    /// The key moves to ineligible mid-read: the old run is cancelled and the
    /// new ineligible run supersedes it, whichever way the provider answers.
    func testAnIneligibleRunSupersedesAnEligibleReadInFlight() async throws {
        let client = Client(detail: try event(status: "completed"))
        let vm = makeVM(client: client)
        await vm.load()

        let eligibleRun = Task { @MainActor in await self.runTask(vm) }
        await waitUntil("read parked") { client.parkedCount == 1 }

        client.serveDetail(try event(status: "live"))
        await vm.load()
        eligibleRun.cancel()
        await runTask(vm)
        client.answer(0, with: .serve(body()))
        await eligibleRun.value

        XCTAssertNil(vm.publicationJourney, "the superseded read does not land")
        XCTAssertNil(chartArgument(vm))
        XCTAssertEqual(client.publicationRequests, [Self.eventID], "the ineligible run asked nothing")
        vm.stopRefresh()
    }

    /// Reappearing while the first read was cancelled before it answered:
    /// nothing is held, so the same key reads again.
    func testReappearingAfterACancelledReadAsksAgain() async throws {
        let client = Client(detail: try event(status: "completed"))
        let vm = makeVM(client: client)
        await vm.load()

        let firstAppearance = Task { @MainActor in await self.runTask(vm) }
        await waitUntil("read parked") { client.parkedCount == 1 }
        firstAppearance.cancel()
        client.answer(0, with: .fail(CancellationError()))
        await firstAppearance.value
        XCTAssertNil(vm.publicationJourney, "fixture: the page left before its read answered")

        client.answerAll(.serve(body()))
        await runTask(vm)

        XCTAssertEqual(client.publicationRequests, [Self.eventID, Self.eventID])
        XCTAssertEqual(chartArgument(vm), try journey())
    }
}
