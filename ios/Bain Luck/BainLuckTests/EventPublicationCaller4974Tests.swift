import Foundation
import SwiftUI
import XCTest
@testable import Bain_Luck

/// #4974 — **opening or refreshing a finished game supplies its validated
/// stored checkpoints to the chart once; leaving the page or changing
/// eligibility can never publish an obsolete journey.**
///
/// `EventDetailView` is the caller of `EventDetailViewModel.adoptPublicationJourney()`.
/// It owns one `@State PublicationCaller4974` (readiness + generation +
/// revision), one `.task(id: PublicationTaskKey4974)` whose whole body is
/// `EventDetailView.runPublicationTask(for:vm:)`, one page-load helper
/// `EventDetailView.loadPage(pageEventId:vm:caller:)` used by appearance, pull
/// to refresh and Refresh now, and one chart argument
/// `EventDetailView.chartPublicationJourney(_:key:)`.
///
/// The unit cases drive those exact functions on the real view model. `Page`
/// below stands in for SwiftUI only where SwiftUI is the actor: a body pass
/// whose key moved cancels the run in flight and starts one for the new key,
/// and a disappearance cancels the page's tasks and suspends readiness. The
/// hosted cases at the end mount the actual page and count requests.
///
/// AUTHORED, NOT EXECUTED: lane1b has no Swift compiler, Xcode or simulator in
/// this slice. Native compiles, runs and composes (boundary:
/// `4974-NATIVE-CALLER-WIRING-SOURCE-BOUNDARY.md`). The chart initializer
/// argument `publicationJourney:` arrives with latency's #10495 chart commit;
/// the page source here compiles only once composed with it.
///
/// The existing event-page fakes are each private to their own file, so this
/// file carries its own in the same shape (`EventPublicationAdoption4974Tests`).
/// Nothing here touches a server, a socket or the wall clock except as a
/// timeout (gotcha #44).
@MainActor
final class EventPublicationCaller4974Tests: XCTestCase {

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

    /// What the strict contract makes of `body()` — computed by `adopt`, never
    /// re-derived here.
    private func journey() throws -> PublicationJourney4974.Journey {
        try PublicationJourney4974.adopt(body(), expectedEventID: Self.eventID, finished: true).get()
    }

    // MARK: - Fakes

    private enum Reply<T> {
        case serve(T)
        case fail(Error)
    }

    /// Serves a replaceable detail, at once or parked (`holdDetails`), and
    /// answers checkpoint reads at once (`answerPublications`) or parked. Deaf
    /// to cancellation on purpose: the caller's and view model's own checks are
    /// what a cancelled read has to pass. Every other secondary read refuses.
    private nonisolated final class Client: EventDetailProviding, @unchecked Sendable {
        struct Declined: Error {}
        private let lock = NSLock()
        private var detail: Reply<EventDetail>
        private var holding = false
        private var parkedDetails: [CheckedContinuation<EventDetail, Error>?] = []
        private var publications: Reply<PublicationCheckpointsResponse>?
        private var parkedPublications: [CheckedContinuation<PublicationCheckpointsResponse, Error>?] = []
        private var asked: [Int] = []

        init(detail: EventDetail, publications: PublicationCheckpointsResponse? = nil) {
            self.detail = .serve(detail)
            self.publications = publications.map { .serve($0) }
        }

        func serveDetail(_ next: EventDetail) { lock.withLock { detail = .serve(next) } }
        func failDetail(_ error: Error) { lock.withLock { detail = .fail(error) } }
        /// `true` parks every later detail read until `answerDetail(_:with:)`.
        func holdDetails(_ hold: Bool) { lock.withLock { holding = hold } }
        /// `nil` parks every later checkpoint read until `answerPublication(_:with:)`.
        func answerPublications(_ response: PublicationCheckpointsResponse?) {
            lock.withLock { publications = response.map { .serve($0) } }
        }
        var publicationRequests: [Int] { lock.withLock { asked } }
        var parkedDetailCount: Int { lock.withLock { parkedDetails.count } }
        var parkedPublicationCount: Int { lock.withLock { parkedPublications.count } }

        func answerDetail(_ index: Int, with reply: Reply<EventDetail>) {
            let continuation: CheckedContinuation<EventDetail, Error>? = lock.withLock {
                defer { parkedDetails[index] = nil }
                return parkedDetails[index]
            }
            switch reply {
            case .serve(let value): continuation?.resume(returning: value)
            case .fail(let error): continuation?.resume(throwing: error)
            }
        }

        func answerPublication(_ index: Int, with reply: Reply<PublicationCheckpointsResponse>) {
            let continuation: CheckedContinuation<PublicationCheckpointsResponse, Error>? = lock.withLock {
                defer { parkedPublications[index] = nil }
                return parkedPublications[index]
            }
            switch reply {
            case .serve(let value): continuation?.resume(returning: value)
            case .fail(let error): continuation?.resume(throwing: error)
            }
        }

        func fetchEvent(id: Int) async throws -> EventDetail {
            let now: Reply<EventDetail>? = lock.withLock { holding ? nil : detail }
            if let now {
                switch now {
                case .serve(let value): return value
                case .fail(let error): throw error
                }
            }
            return try await withCheckedThrowingContinuation { continuation in
                lock.withLock { parkedDetails.append(continuation) }
            }
        }

        func fetchEventPublications(id: Int) async throws -> PublicationCheckpointsResponse {
            let now: Reply<PublicationCheckpointsResponse>? = lock.withLock {
                asked.append(id)
                return publications
            }
            if let now {
                switch now {
                case .serve(let value): return value
                case .fail(let error): throw error
                }
            }
            return try await withCheckedThrowingContinuation { continuation in
                lock.withLock { parkedPublications.append(continuation) }
            }
        }

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

    private func makeVM(client: EventDetailProviding, eventId: Int = 4242) -> EventDetailViewModel {
        EventDetailViewModel(
            eventId: eventId,
            client: client,
            makeStreamHandle: { _ in QuietHandle() },
            now: { 1_791_150_000 },
            sleep: { seconds in try? await Task.sleep(nanoseconds: UInt64(seconds * 1_000_000_000)) }
        )
    }

    /// The page's caller state and keyed task, with SwiftUI's part played by
    /// the test: `render()` is a body pass (a moved key cancels the run in
    /// flight and starts one), `disappear()` is the page leaving.
    @MainActor
    private final class Page {
        let pageEventId: Int
        let vm: EventDetailViewModel
        private(set) var caller = PublicationCaller4974()
        private var shownKey: PublicationTaskKey4974?
        private(set) var run: Task<Void, Never>?
        private(set) var runsStarted = 0

        init(pageEventId: Int = 4242, vm: EventDetailViewModel) {
            self.pageEventId = pageEventId
            self.vm = vm
        }

        var callerBinding: Binding<PublicationCaller4974> {
            Binding(get: { self.caller }, set: { self.caller = $0 })
        }

        var key: PublicationTaskKey4974 {
            PublicationTaskKey4974(pageEventId: pageEventId, vmEventId: vm.eventId,
                                   event: vm.event, caller: caller)
        }

        /// What the page hands the chart right now.
        var chart: PublicationJourney4974.Journey? {
            EventDetailView.chartPublicationJourney(vm.publicationJourney, key: key)
        }

        func render() {
            let now = key
            guard now != shownKey else { return }
            shownKey = now
            run?.cancel()
            runsStarted += 1
            let vm = self.vm
            run = Task { @MainActor in await EventDetailView.runPublicationTask(for: now, vm: vm) }
        }

        func settle() async { await run?.value }

        /// A page load exactly as appearance, pull to refresh and Refresh now start it.
        func startLoad() -> Task<Void, Never> {
            let vm = self.vm, id = pageEventId, binding = callerBinding
            return Task { @MainActor in
                await EventDetailView.loadPage(pageEventId: id, vm: vm, caller: binding)
            }
        }

        /// Load, then the body pass its completion causes, then that run.
        func loadAndSettle() async {
            await startLoad().value
            render()
            await settle()
        }

        /// The page leaving: SwiftUI cancels its keyed task and the page
        /// suspends readiness. The next appearance's `.task(id:)` starts afresh.
        func disappear() {
            run?.cancel()
            caller.suspend()
            shownKey = nil
        }
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

    // MARK: - The caller state and key, alone

    func testReadinessOpensOnlyForTheLatestLoadAndEachOpeningIsANewRevision() {
        var caller = PublicationCaller4974()
        XCTAssertFalse(caller.ready)
        let first = caller.suspend()
        let second = caller.suspend()
        XCTAssertFalse(caller.open(ifCurrent: first), "an older load cannot reopen readiness")
        XCTAssertFalse(caller.ready)
        XCTAssertTrue(caller.open(ifCurrent: second))
        XCTAssertTrue(caller.ready)
        let opened = caller.revision
        caller.suspend()
        XCTAssertFalse(caller.ready, "a new load or a disappearance closes it")
        XCTAssertFalse(caller.open(ifCurrent: second), "nor can the load that opened it last time")
        let third = caller.suspend()
        XCTAssertTrue(caller.open(ifCurrent: third))
        XCTAssertNotEqual(caller.revision, opened, "a fresh opening is a fresh key")
    }

    func testTheKeyIgnoresTheRawFinishedStatusAndActsOnlyWhenReadyForItsOwnViewModel() throws {
        var ready = PublicationCaller4974()
        let generation = ready.suspend()
        ready.open(ifCurrent: generation)
        let completed = PublicationTaskKey4974(pageEventId: 4242, vmEventId: 4242,
                                               event: try event(status: "completed"), caller: ready)
        let closed = PublicationTaskKey4974(pageEventId: 4242, vmEventId: 4242,
                                            event: try event(status: "closed"), caller: ready)
        XCTAssertEqual(completed, closed, "completed and closed are one finished key")
        XCTAssertEqual(completed.action, .adopt)

        let notReady = PublicationTaskKey4974(pageEventId: 4242, vmEventId: 4242,
                                              event: try event(status: "completed"),
                                              caller: PublicationCaller4974())
        XCTAssertEqual(notReady.action, .withhold, "a false-ready key never calls: the call itself would fetch")

        let mismatched = PublicationTaskKey4974(pageEventId: 5151, vmEventId: 4242,
                                                event: try event(status: "completed"), caller: ready)
        XCTAssertEqual(mismatched.action, .withhold,
                       "page and view model disagree: never call, it would fetch the view model's old game")

        let readyLive = PublicationTaskKey4974(pageEventId: 4242, vmEventId: 4242,
                                               event: try event(status: "live"), caller: ready)
        XCTAssertEqual(readyLive.action, .adopt, "a ready ineligible key calls once to clear")
        let readyNoEvent = PublicationTaskKey4974(pageEventId: 4242, vmEventId: 4242, event: nil, caller: ready)
        XCTAssertEqual(readyNoEvent.action, .adopt)
    }

    // MARK: - Opening the page

    func testANoEventPageWithholdsAndItsFirstSuccessfulLoadReadsOnce() async throws {
        let client = Client(detail: try event(status: "completed"), publications: body())
        let page = Page(vm: makeVM(client: client))

        page.render()   // appearance: `.task(id:)` starts with no detail and nothing ready
        await page.settle()
        XCTAssertEqual(page.key.action, .withhold)
        XCTAssertEqual(client.publicationRequests, [], "nothing asked before the load finishes")

        await page.loadAndSettle()

        XCTAssertEqual(client.publicationRequests, [Self.eventID], "one read")
        XCTAssertEqual(page.vm.publicationJourney, try journey())
        XCTAssertEqual(page.chart, try journey(), "positive control: the chart receives the accepted journey")
        page.vm.stopRefresh()
    }

    /// The detail arrives finished while the page's own load is still running:
    /// not ready yet, so the finished key calls nothing until the load completes.
    func testAFinishedDetailBeforeTheLoadCompletesIsAFalseReadyKeyThatCallsNothing() async throws {
        let client = Client(detail: try event(status: "completed"), publications: body())
        let page = Page(vm: makeVM(client: client))
        await page.vm.load()   // the detail is held; the caller's own load has not opened readiness
        page.render()
        await page.settle()

        XCTAssertTrue(page.key.finished)
        XCTAssertEqual(page.key.action, .withhold)
        XCTAssertEqual(client.publicationRequests, [], "calling here would itself fetch")
        XCTAssertNil(page.chart)
        page.vm.stopRefresh()
    }

    func testAFailedLoadOpensNothingAndStartsNoRead() async throws {
        let client = Client(detail: try event(status: "completed"), publications: body())
        client.failDetail(URLError(.notConnectedToInternet))
        let page = Page(vm: makeVM(client: client))

        await page.loadAndSettle()

        XCTAssertNotNil(page.vm.error, "control: the page's own error behavior is unchanged")
        XCTAssertFalse(page.caller.ready, "completion alone is not success")
        XCTAssertEqual(client.publicationRequests, [])
        XCTAssertNil(page.chart)
        page.vm.stopRefresh()
    }

    /// The page was opened for one id and handed a view model for another:
    /// zero requests for the view model's game, ever.
    func testAPageWhoseViewModelIsAnotherGameNeverCallsIt() async throws {
        let client = Client(detail: try event(status: "completed"), publications: body())
        let page = Page(pageEventId: 5151, vm: makeVM(client: client))

        page.render()
        await page.loadAndSettle()
        await page.vm.load()
        page.render()
        await page.settle()

        XCTAssertEqual(client.publicationRequests, [], "no request for the view model's old game")
        XCTAssertNil(page.chart)
        page.vm.stopRefresh()
    }

    // MARK: - Eligibility changing while shown

    /// A regular background refresh (not the page's own load) finishes the game.
    func testALiveGameThatFinishesWhileShownReadsOnce() async throws {
        let client = Client(detail: try event(status: "live"), publications: body())
        let page = Page(vm: makeVM(client: client))
        await page.loadAndSettle()
        XCTAssertEqual(client.publicationRequests, [], "a ready live page calls only to clear: no request")

        client.serveDetail(try event(status: "completed"))
        await page.vm.load()
        page.render()
        await page.settle()

        XCTAssertEqual(client.publicationRequests, [Self.eventID])
        XCTAssertEqual(page.chart, try journey())
        page.vm.stopRefresh()
    }

    func testAFinishedGameCorrectedToLiveIsWithheldAtOnceAndClearedWithoutARequest() async throws {
        let client = Client(detail: try event(status: "completed"), publications: body())
        let page = Page(vm: makeVM(client: client))
        await page.loadAndSettle()
        XCTAssertEqual(page.chart, try journey(), "fixture: a finished page holding its journey")

        client.serveDetail(try event(status: "live"))
        await page.vm.load()
        XCTAssertNotNil(page.vm.publicationJourney, "the view model still holds the old journey here")
        XCTAssertNil(page.chart, "and the chart refuses that old stored output before the task re-runs")

        page.render()
        await page.settle()
        XCTAssertNil(page.vm.publicationJourney, "the fresh ineligible run cleared it")
        XCTAssertEqual(client.publicationRequests, [Self.eventID], "without a request")
        page.vm.stopRefresh()
    }

    func testCompletedToClosedIsNotASecondRead() async throws {
        let client = Client(detail: try event(status: "completed"), publications: body())
        let page = Page(vm: makeVM(client: client))
        await page.loadAndSettle()
        let runs = page.runsStarted

        client.serveDetail(try event(status: "closed"))
        await page.vm.load()
        page.render()
        await page.settle()

        XCTAssertEqual(page.runsStarted, runs, "the key did not move")
        XCTAssertEqual(client.publicationRequests, [Self.eventID])
        XCTAssertEqual(page.chart, try journey())
        page.vm.stopRefresh()
    }

    func testAnUnchangedRerenderOrRefreshReceiptIsNotASecondRead() async throws {
        let client = Client(detail: try event(status: "completed"), publications: body())
        let page = Page(vm: makeVM(client: client))
        await page.loadAndSettle()
        let runs = page.runsStarted

        page.render()
        page.render()
        await page.vm.load()   // a background refresh: new receipt, same game, same state
        page.render()
        await page.settle()

        XCTAssertEqual(page.runsStarted, runs)
        XCTAssertEqual(client.publicationRequests, [Self.eventID])
        page.vm.stopRefresh()
    }

    // MARK: - Leaving and coming back

    func testAResponseArrivingAfterThePageLeftPublishesNothing() async throws {
        let client = Client(detail: try event(status: "completed"))
        let page = Page(vm: makeVM(client: client))
        await page.startLoad().value
        page.render()
        await waitUntil("read parked") { client.parkedPublicationCount == 1 }

        page.disappear()
        client.answerPublication(0, with: .serve(body()))
        await page.settle()

        XCTAssertNil(page.vm.publicationJourney, "a provider ignoring cancellation still cannot publish")
        XCTAssertNil(page.chart)
        page.vm.stopRefresh()
    }

    func testReappearingLoadsAfreshAndReadsOnceMore() async throws {
        let client = Client(detail: try event(status: "completed"), publications: body())
        let page = Page(vm: makeVM(client: client))
        await page.loadAndSettle()
        XCTAssertEqual(client.publicationRequests, [Self.eventID])

        page.disappear()
        XCTAssertNil(page.chart, "a page that left is not ready")

        page.render()   // reappearance: `.task(id:)` starts with readiness still closed
        await page.settle()
        XCTAssertEqual(client.publicationRequests, [Self.eventID], "nothing before the fresh load")
        await page.loadAndSettle()

        XCTAssertEqual(client.publicationRequests, [Self.eventID, Self.eventID], "one fresh read")
        XCTAssertEqual(page.chart, try journey())
        page.vm.stopRefresh()
    }

    /// Leaving while the page's own load is in flight: neither the cancelled
    /// appearance load nor an uncancelled Refresh-now load reopens readiness.
    func testALoadInFlightWhenThePageLeavesNeverOpensReadiness() async throws {
        for cancelled in [true, false] {
            let client = Client(detail: try event(status: "completed"), publications: body())
            client.holdDetails(true)
            let page = Page(vm: makeVM(client: client))
            let load = page.startLoad()
            await waitUntil("detail parked") { client.parkedDetailCount == 1 }

            if cancelled { load.cancel() }
            page.disappear()
            client.answerDetail(0, with: .serve(try event(status: "completed")))
            await load.value

            XCTAssertFalse(page.caller.ready, "cancelled=\(cancelled): a load from before leaving reopens nothing")
            XCTAssertEqual(page.key.action, .withhold)
            XCTAssertEqual(client.publicationRequests, [])
            page.vm.stopRefresh()
        }
    }

    // MARK: - The reader's own reloads

    /// Pull to refresh and Refresh now both run `loadPage`.
    func testARefreshOfAFinishedPageReadsExactlyOnceMore() async throws {
        let client = Client(detail: try event(status: "completed"), publications: body())
        let page = Page(vm: makeVM(client: client))
        await page.loadAndSettle()

        client.holdDetails(true)
        let reload = page.startLoad()
        await waitUntil("detail parked") { client.parkedDetailCount == 1 }
        page.render()   // the suspension is a body pass: old run cancelled, nothing called
        await page.settle()
        XCTAssertNil(page.chart, "suspended for the reload")
        XCTAssertEqual(client.publicationRequests, [Self.eventID])

        client.answerDetail(0, with: .serve(try event(status: "completed")))
        await reload.value
        page.render()
        await page.settle()

        XCTAssertEqual(client.publicationRequests, [Self.eventID, Self.eventID], "exactly one more")
        XCTAssertEqual(page.chart, try journey())
        page.vm.stopRefresh()
    }

    func testARefreshThatFinishesTheGameReadsOnceNotTwice() async throws {
        let client = Client(detail: try event(status: "live"), publications: body())
        let page = Page(vm: makeVM(client: client))
        await page.loadAndSettle()

        client.holdDetails(true)
        let reload = page.startLoad()
        await waitUntil("detail parked") { client.parkedDetailCount == 1 }
        page.render()   // suspended for the reload: nothing called
        await page.settle()
        XCTAssertEqual(page.key.action, .withhold)

        // Finished arrives inside the reload; the reload's completion opens
        // readiness and moves the revision in the same write, so the key moves
        // once. (A finished-but-not-ready key withholds: see the key test.)
        client.answerDetail(0, with: .serve(try event(status: "completed")))
        await reload.value
        page.render()
        await page.settle()

        XCTAssertEqual(client.publicationRequests, [Self.eventID], "one, not two")
        XCTAssertEqual(page.chart, try journey())
        page.vm.stopRefresh()
    }

    func testAnOlderReloadFinishingOutOfOrderCannotReopenReadiness() async throws {
        // Newer first, then the older one lands.
        do {
            let client = Client(detail: try event(status: "completed"), publications: body())
            client.holdDetails(true)
            let page = Page(vm: makeVM(client: client))
            let older = page.startLoad()
            await waitUntil("older parked") { client.parkedDetailCount == 1 }
            let newer = page.startLoad()
            await waitUntil("newer parked") { client.parkedDetailCount == 2 }

            client.answerDetail(1, with: .serve(try event(status: "completed")))
            await newer.value
            page.render()
            await page.settle()
            let opened = page.caller
            XCTAssertEqual(client.publicationRequests, [Self.eventID])

            client.answerDetail(0, with: .serve(try event(status: "completed")))
            await older.value
            page.render()
            await page.settle()
            XCTAssertEqual(page.caller, opened, "the older completion moved nothing")
            XCTAssertEqual(client.publicationRequests, [Self.eventID], "and caused no second read")
            page.vm.stopRefresh()
        }
        // Older first, while the newer is still pending.
        do {
            let client = Client(detail: try event(status: "completed"), publications: body())
            client.holdDetails(true)
            let page = Page(vm: makeVM(client: client))
            let older = page.startLoad()
            await waitUntil("older parked") { client.parkedDetailCount == 1 }
            let newer = page.startLoad()
            await waitUntil("newer parked") { client.parkedDetailCount == 2 }

            client.answerDetail(0, with: .serve(try event(status: "completed")))
            await older.value
            page.render()
            await page.settle()
            XCTAssertFalse(page.caller.ready, "the older completion does not open over a pending newer load")
            XCTAssertEqual(client.publicationRequests, [])

            client.answerDetail(1, with: .serve(try event(status: "completed")))
            await newer.value
            page.render()
            await page.settle()
            XCTAssertEqual(client.publicationRequests, [Self.eventID])
            page.vm.stopRefresh()
        }
    }

    func testAFailedRefreshKeepsThePageErrorAndStartsNoReplacementRead() async throws {
        let client = Client(detail: try event(status: "completed"), publications: body())
        let page = Page(vm: makeVM(client: client))
        await page.loadAndSettle()
        XCTAssertEqual(page.chart, try journey())

        client.failDetail(URLError(.timedOut))
        await page.loadAndSettle()

        XCTAssertNotNil(page.vm.error, "the existing page error behavior")
        XCTAssertFalse(page.caller.ready)
        XCTAssertNil(page.chart, "not ready: the chart is handed nothing")
        XCTAssertEqual(client.publicationRequests, [Self.eventID], "no replacement read, no retry")
        page.vm.stopRefresh()
    }

    // MARK: - The mounted page

    private func settle(_ host: UIViewController, _ seconds: TimeInterval) {
        let until = Date().addingTimeInterval(seconds)
        repeat {
            host.view.setNeedsLayout(); host.view.layoutIfNeeded()
            RunLoop.current.run(until: min(until, Date().addingTimeInterval(0.01)))
        } while Date() < until
    }

    private func mount(_ vm: EventDetailViewModel) -> (UIWindow, UIViewController) {
        let page = NavigationStack { EventDetailView(eventId: Self.eventID, viewModel: vm) }
            .environmentObject(PinManager())
            .environment(\.scenePhase, .active).environment(\.colorScheme, .light)
        let host = hostForMeasurement(page)
        host.view.frame = CGRect(x: 0, y: 0, width: 390, height: 844)
        let window = UIWindow(frame: host.view.frame)
        window.rootViewController = host
        window.isHidden = false
        return (window, host)
    }

    func testTheMountedPageReadsOnceAfterItsOwnLoadAndNotOnReRender() async throws {
        let client = Client(detail: try event(status: "completed"), publications: body())
        let vm = makeVM(client: client)
        let (window, host) = mount(vm)
        defer { vm.stopRefresh(); window.isHidden = true }

        settle(host, 1.0)
        XCTAssertEqual(client.publicationRequests, [Self.eventID], "the page's own load, then one read")
        XCTAssertEqual(vm.publicationJourney, try journey())

        settle(host, 0.5)
        XCTAssertEqual(client.publicationRequests, [Self.eventID], "re-renders are not reads")
    }

    func testTheMountedPageReadsAgainOnReappearanceAndPublishesNothingAfterLeaving() async throws {
        let client = Client(detail: try event(status: "completed"), publications: body())
        let vm = makeVM(client: client)
        let (window, host) = mount(vm)
        defer { vm.stopRefresh(); window.isHidden = true }
        settle(host, 1.0)
        XCTAssertEqual(client.publicationRequests, [Self.eventID], "fixture: first appearance read once")

        let elsewhere = UIViewController()
        window.rootViewController = elsewhere
        settle(elsewhere, 0.3)
        client.answerPublications(nil)   // the next read parks
        window.rootViewController = host
        settle(host, 1.0)
        XCTAssertEqual(client.publicationRequests, [Self.eventID, Self.eventID], "reappearance: one fresh read")
        XCTAssertEqual(client.parkedPublicationCount, 1)

        window.rootViewController = elsewhere   // leave before it answers
        settle(elsewhere, 0.3)
        client.answerPublication(0, with: .serve(body()))
        settle(elsewhere, 0.3)
        XCTAssertNil(vm.publicationJourney, "the read answered after the page left publishes nothing")
    }
}
