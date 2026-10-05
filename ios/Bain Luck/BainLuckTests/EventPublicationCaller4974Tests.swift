import Foundation
import SwiftUI
import Vision
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
/// The last section pins the page's ONE chart window
/// (`EventDetailView.pageSharedChartDomain`), which both charts take as
/// `forcedDomain`: a finished game's stored checkpoints can be inserted after
/// the legacy window's end, and the window must reach them or the chart's own
/// admission hides every dot (Root's correction,
/// `4974-root-shared-window-correction/ROOT-FINDING-AND-SCOPE.md`). Also
/// authored, not executed.
///
/// The wider window is the AXIS, never the legacy INK: the page also hands
/// both charts the original window as `legacyDataDomain`
/// (`EventDetailView.pageLegacyChartDataDomain`), so post-final market drift
/// and score rows inside each chart's own finish clip stay off the page and
/// the score carry stops at the original end (Root's B,
/// `4974-ROOT-AXIS-INK-CORRECTION-BOUNDARY.md`). The chart argument
/// `legacyDataDomain:` arrives with latency's sibling chart commit; like the
/// rest, authored here and executed only by Native once composed.
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
        /// Served at once when set; refused (the history-less page) when nil.
        private let history: EventHistoryResponse?
        private var historyAsks = 0

        init(detail: EventDetail, publications: PublicationCheckpointsResponse? = nil,
             history: EventHistoryResponse? = nil) {
            self.detail = .serve(detail)
            self.publications = publications.map { .serve($0) }
            self.history = history
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

        var historyRequestCount: Int { lock.withLock { historyAsks } }

        func fetchEventHistory(id: Int, hours: Int) async throws -> EventHistoryResponse {
            let served: EventHistoryResponse? = lock.withLock {
                historyAsks += 1
                return history
            }
            guard let served else { throw Declined() }
            return served
        }
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

    // MARK: - The page's one chart window

    private typealias Journey = PublicationJourney4974.Journey

    /// 2026-10-04T20:15:00Z (`PublicationCheckpointChart4974Tests.t0`).
    private static let t0 = Date(timeIntervalSince1970: 1_791_144_900)
    private func at(_ seconds: TimeInterval) -> Date { Self.t0.addingTimeInterval(seconds) }
    /// First pitch, `event()`'s `commence_time`: 17:05:00Z.
    private var kickoff: Date { at(-11_400) }

    /// A finished page's legacy history. ESPN in-game rows from first pitch to
    /// 20:16:30 (final 5–3), sportsbook rows to 20:16:00, and the blend
    /// (`aggregate_line`) from 16:05 pre-game to 20:16:00 at 88%. So the legacy
    /// window ends at 20:17:00 (last ESPN/odds row + 30 s) and the probability
    /// chart's own finish clip at 20:18:30 (last ESPN row + 120 s).
    /// `extraBlend` appends blend rows; `blend: false` serves no blend at all.
    private func legacyHistory(extraBlend: [(TimeInterval, Double)] = [],
                               blend: Bool = true) throws -> EventHistoryResponse {
        func stamp(_ seconds: TimeInterval) -> String { at(seconds).ISO8601Format() }
        let espn: [[String: Any]] = [
            ["timestamp": stamp(-11_400), "home_probability": 0.55, "period": "1",
             "home_score": 0, "away_score": 0],
            ["timestamp": stamp(-5_700), "home_probability": 0.62, "period": "5",
             "home_score": 2, "away_score": 1],
            ["timestamp": stamp(90), "home_probability": 0.99, "period": "9",
             "home_score": 5, "away_score": 3],
        ]
        let odds: [[String: Any]] = [
            ["timestamp": stamp(-14_400), "home_probability": 0.52],
            ["timestamp": stamp(60), "home_probability": 0.88],
        ]
        let blendRows: [(TimeInterval, Double)] = blend
            ? [(-14_400, 0.52), (-11_400, 0.55), (-5_700, 0.62), (60, 0.88)] + extraBlend
            : []
        let aggregate: [[String: Any]] = blendRows.map { row -> [String: Any] in
            ["timestamp": stamp(row.0), "home_probability": row.1]
        }
        let object: [String: Any] = [
            "event_id": Self.eventID, "home_team": "Red Sox", "away_team": "Yankees",
            "status": "completed", "history": odds, "espn_history": espn, "aggregate_line": aggregate,
        ]
        let data = try JSONSerialization.data(withJSONObject: object)
        return try Self.decoder().decode(EventHistoryResponse.self, from: data)
    }

    /// Stored at 20:20:00 (rev 7, 93%) and 20:21:00 (rev 9, 96%): both after
    /// the legacy window's 20:17:00 end.
    private func lateBody(eventId: Int = 4242) -> PublicationCheckpointsResponse {
        PublicationCheckpointsResponse(
            eventId: eventId, schemaVersion: 1, timeBasis: "recorded_at_insert_before_commit",
            truncated: false,
            vertices: [PublicationCheckpointVertex(rev: 7, t: at(300).ISO8601Format(), p: 0.93),
                       PublicationCheckpointVertex(rev: 9, t: at(360).ISO8601Format(), p: 0.96)])
    }

    /// `lateBody()` through the strict contract — never a hand-built journey.
    private func lateJourney(eventId: Int = 4242) throws -> Journey {
        try PublicationJourney4974.adopt(lateBody(eventId: eventId), expectedEventID: eventId,
                                         finished: true).get()
    }

    private func readyCaller() -> PublicationCaller4974 {
        var caller = PublicationCaller4974()
        let generation = caller.suspend()
        caller.open(ifCurrent: generation)
        return caller
    }

    private func key(page: Int = 4242, vm: Int = 4242, detail: EventDetail?,
                     ready: Bool = true) -> PublicationTaskKey4974 {
        PublicationTaskKey4974(pageEventId: page, vmEventId: vm, event: detail,
                               caller: ready ? readyCaller() : PublicationCaller4974())
    }

    /// What the page handed both charts before this correction.
    private func legacyWindow(_ detail: EventDetail, _ history: EventHistoryResponse?,
                              _ range: OddsTimeRange) -> ClosedRange<Date>? {
        SharedChartWindow.domain(status: detail.status, commenceTime: detail.commenceTime,
                                 history: history, range: range, sportKey: detail.sport, now: at(0))
    }

    /// The ink window the page hands both charts: its own helper, on its own inputs.
    private func inkWindow(_ detail: EventDetail?, _ history: EventHistoryResponse?,
                           _ range: OddsTimeRange, journey: Journey?,
                           key: PublicationTaskKey4974) -> ClosedRange<Date>? {
        EventDetailView.pageLegacyChartDataDomain(event: detail, history: history, range: range,
                                                  journey: journey, key: key, now: at(0))
    }

    /// What the page hands both charts now: its own helper, on its own inputs.
    private func pageWindow(_ detail: EventDetail?, _ history: EventHistoryResponse?,
                            _ range: OddsTimeRange, journey: Journey?,
                            key: PublicationTaskKey4974) -> ClosedRange<Date>? {
        EventDetailView.pageSharedChartDomain(event: detail, history: history, range: range,
                                              journey: journey, key: key, now: at(0))
    }

    /// The probability chart's points under `domain`, composed as
    /// `OddsChartView.filterPoints` composes them for a finished game (its
    /// legacy finish clip, then the forced window, then Since Start) — the
    /// composition `PublicationCheckpointChart4974Tests` uses. That the private
    /// function still runs those clips is pinned by source below.
    private func drawnPoints(_ history: EventHistoryResponse, domain: ClosedRange<Date>?,
                             range: OddsTimeRange) throws -> [ChartDataPoint] {
        let end = try XCTUnwrap(OddsChartView.gameEndDate(status: "completed", history: history))
        let clipped = OddsChartView.chartPoints(from: history)
            .filter { $0.date <= end }
            .filter { SharedChartWindow.contains($0.date, in: domain) }
        return OddsChartView.sinceStartWindow(clipped, range: range, kickoff: kickoff)
    }

    /// The chart's checkpoint mount under `domain`, with the Since Start cut the
    /// chart applies for that range.
    private func checkpointMount(_ journey: Journey?, _ history: EventHistoryResponse,
                                 domain: ClosedRange<Date>?,
                                 range: OddsTimeRange) throws -> PublicationCheckpointMount4974? {
        OddsChartView.publicationCheckpointMount(
            journey: journey, eventId: Self.eventID, status: "completed",
            points: try drawnPoints(history, domain: domain, range: range), gameStart: nil,
            forcedDomain: domain, sinceStart: range == .sinceStart ? kickoff : nil)
    }

    private func signature(_ points: [ChartDataPoint]) -> [String] {
        points.map { "\($0.source)@\($0.date.timeIntervalSince1970)=\($0.probability)" }
    }

    /// Legacy window 20:17:00; checkpoints 20:20 and 20:21. Both ranges keep the
    /// start the reader chose and end 30 s after the latest stored checkpoint.
    func testThePageWindowReachesTheStoredCheckpointsAndKeepsEachRangesStart() throws {
        let detail = try event(status: "completed")
        let history = try legacyHistory()
        let journey = try lateJourney()
        var starts: [OddsTimeRange: Date] = [:]
        for range in [OddsTimeRange.sinceStart, .all] {
            let legacy = try XCTUnwrap(legacyWindow(detail, history, range), "fixture: \(range)")
            XCTAssertEqual(legacy.upperBound, at(120), "fixture: the legacy window ends at 20:17:00 (\(range))")
            XCTAssertTrue(journey.checkpoints.allSatisfy { $0.date > legacy.upperBound },
                          "control: every checkpoint was stored after the legacy end")
            let page = try XCTUnwrap(pageWindow(detail, history, range, journey: journey,
                                                key: key(detail: detail)))
            XCTAssertEqual(page.lowerBound, legacy.lowerBound, "\(range) keeps the start it selected")
            XCTAssertEqual(page.upperBound, at(390), "the 20:21:00 checkpoint plus the window's 30 s (\(range))")
            starts[range] = page.lowerBound
        }
        XCTAssertLessThan(try XCTUnwrap(starts[.all]), try XCTUnwrap(starts[.sinceStart]),
                          "control: All and Since Start are two different starts on this page")
    }

    /// Under the page's window the chart draws both stored dots and rests on
    /// the latest; the window the page handed it before this correction hides
    /// the same dots and rests on the legacy 88%. The legacy line is the same
    /// line under both.
    func testThePageWindowDrawsTheStoredDotsTheOldWindowHid() throws {
        let detail = try event(status: "completed")
        let history = try legacyHistory()
        let journey = try lateJourney()
        for range in [OddsTimeRange.sinceStart, .all] {
            let page = pageWindow(detail, history, range, journey: journey, key: key(detail: detail))
            let legacy = legacyWindow(detail, history, range)

            let mount = try XCTUnwrap(try checkpointMount(journey, history, domain: page, range: range))
            XCTAssertEqual(mount.drawn.map(\.vertex.rev), [7, 9], "\(range)")
            guard case .checkpoint(let rest)? = mount.resting else {
                return XCTFail("\(range): expected to rest on a checkpoint, got \(String(describing: mount.resting))")
            }
            XCTAssertEqual(rest.vertex.rev, 9, "\(range): rests on the latest stored checkpoint")

            // POSITIVE CONTROL — the old page window.
            let old = try XCTUnwrap(try checkpointMount(journey, history, domain: legacy, range: range))
            XCTAssertTrue(old.drawn.isEmpty, "\(range): the old window must hide both dots for this test to mean anything")
            guard case .legacy(let oldRest)? = old.resting else {
                return XCTFail("\(range): expected the old window to rest on the legacy line, got \(String(describing: old.resting))")
            }
            XCTAssertEqual(oldRest.probability, 0.88, "\(range)")

            XCTAssertEqual(signature(try drawnPoints(history, domain: page, range: range)),
                           signature(try drawnPoints(history, domain: legacy, range: range)),
                           "\(range): the wider window drew a legacy point the old one did not")
        }
    }

    /// A finger on the stored 20:21 dot under the page's window lands on THAT
    /// checkpoint and reads its own 96%. Under the old window the same far-right
    /// finger could only read the legacy 88%.
    func testAScrubOnTheStoredDotNamesItWhereTheOldWindowNamedTheOldValue() throws {
        let detail = try event(status: "completed")
        let history = try legacyHistory()
        let journey = try lateJourney()
        let plot = CGRect(x: 0, y: 0, width: 400, height: 200)
        func x(_ date: Date, in domain: ClosedRange<Date>) -> CGFloat {
            let span = domain.upperBound.timeIntervalSince(domain.lowerBound)
            return CGFloat(date.timeIntervalSince(domain.lowerBound) / span) * plot.width
        }
        func date(_ x: CGFloat, in domain: ClosedRange<Date>) -> Date {
            let span = domain.upperBound.timeIntervalSince(domain.lowerBound)
            return domain.lowerBound.addingTimeInterval(Double(x / plot.width) * span)
        }

        let page = try XCTUnwrap(pageWindow(detail, history, .sinceStart, journey: journey,
                                            key: key(detail: detail)))
        let mount = try XCTUnwrap(try checkpointMount(journey, history, domain: page, range: .sinceStart))
        let latest = try XCTUnwrap(mount.drawn.last)
        let picked = mount.selection(atChartX: x(latest.date, in: page), plotFrame: plot,
                                     dateAt: { date($0, in: page) },
                                     position: { x($0.date, in: page) })
        guard case .checkpoint(let hit)? = picked.scrub else {
            return XCTFail("expected the stored dot, got \(String(describing: picked.scrub))")
        }
        XCTAssertEqual(hit.vertex.rev, 9)
        XCTAssertEqual(picked.date, latest.date, "the crosshair stands on the dot's own time")
        guard case .checkpoint(let shown) = mount.readout(date: picked.date, scrub: picked.scrub) else {
            return XCTFail("the hit did not read as its checkpoint")
        }
        XCTAssertEqual(shown.vertex.p, 0.96)

        // POSITIVE CONTROL — the old window: the rightmost finger is on the line.
        let legacy = try XCTUnwrap(legacyWindow(detail, history, .sinceStart))
        let old = try XCTUnwrap(try checkpointMount(journey, history, domain: legacy, range: .sinceStart))
        let oldPick = old.selection(atChartX: plot.width, plotFrame: plot,
                                    dateAt: { date($0, in: legacy) },
                                    position: { x($0.date, in: legacy) })
        XCTAssertNil(oldPick.scrub, "no stored dot is reachable under the old window")
        guard case .legacy(let point) = old.readout(date: oldPick.date, scrub: oldPick.scrub) else {
            return XCTFail("expected the old window's finger to read the legacy line")
        }
        XCTAssertEqual(point.probability, 0.88)
        // A stored hit carried into the old window names nothing.
        if case .checkpoint = old.readout(date: latest.date, scrub: .checkpoint(latest)) {
            XCTFail("a checkpoint the old window does not draw was named")
        }
    }

    /// Every input the chart's journey guard refuses leaves the window exactly
    /// the legacy one: no journey, an unready appearance, another page, a view
    /// model or detail of another game, another game's journey, a live game,
    /// no history, no detail.
    func testEveryIneligibleInputKeepsTheLegacyWindowExactly() throws {
        let finished = try event(status: "completed")
        let history = try legacyHistory()
        let journey = try lateJourney()
        let otherDetail = try event(id: 5151, status: "completed")
        let otherJourney = try lateJourney(eventId: 5151)
        let expected = legacyWindow(finished, history, .sinceStart)
        XCTAssertNotNil(expected, "fixture")
        XCTAssertNotEqual(pageWindow(finished, history, .sinceStart, journey: journey, key: key(detail: finished)),
                          expected, "control: the eligible page does widen")

        let cases: [(String, Journey?, PublicationTaskKey4974)] = [
            ("no journey", nil, key(detail: finished)),
            ("unready appearance", journey, key(detail: finished, ready: false)),
            ("another page", journey, key(page: 5151, detail: finished)),
            ("view model of another game", journey, key(vm: 5151, detail: finished)),
            ("detail of another game", journey, key(detail: otherDetail)),
            ("another game's journey", otherJourney, key(detail: finished)),
        ]
        for (name, held, pageKey) in cases {
            XCTAssertEqual(pageWindow(finished, history, .sinceStart, journey: held, key: pageKey), expected, name)
            XCTAssertEqual(pageWindow(finished, history, .all, journey: held, key: pageKey),
                           legacyWindow(finished, history, .all), "\(name) (All)")
        }

        let live = try event(status: "live")
        XCTAssertNotNil(legacyWindow(live, history, .sinceStart), "fixture: a live page has a window")
        XCTAssertEqual(pageWindow(live, history, .sinceStart, journey: journey, key: key(detail: live)),
                       legacyWindow(live, history, .sinceStart), "live")

        XCTAssertNil(legacyWindow(finished, nil, .sinceStart), "fixture: no history, no legacy window")
        XCTAssertNil(pageWindow(finished, nil, .sinceStart, journey: journey, key: key(detail: finished)),
                     "the checkpoints do not invent a window the legacy rule declined")
        XCTAssertNil(pageWindow(nil, history, .sinceStart, journey: journey, key: key(detail: nil)))
    }

    /// Only the end can move, only later, and only for a checkpoint at or after
    /// the selected start.
    func testCheckpointsBeforeTheStartDoNotWidenItAndALaterEndIsNeverShortened() throws {
        let ready = key(detail: try event(status: "completed"))
        let journey = try lateJourney()   // 20:20:00 and 20:21:00

        let wide = at(-600)...at(1_800)
        XCTAssertEqual(EventDetailView.publicationSharedChartDomain(wide, journey: journey, key: ready), wide,
                       "an end already past both checkpoints is not shortened")
        let late = at(600)...at(1_200)
        XCTAssertEqual(EventDetailView.publicationSharedChartDomain(late, journey: journey, key: ready), late,
                       "checkpoints before the start widen nothing")
        let straddle = at(330)...at(340)
        XCTAssertEqual(EventDetailView.publicationSharedChartDomain(straddle, journey: journey, key: ready),
                       at(330)...at(390),
                       "the 20:20 checkpoint before the start neither moves the start nor counts; 20:21 sets the end")
        XCTAssertNil(EventDetailView.publicationSharedChartDomain(nil, journey: journey, key: ready))
    }

    /// A post-final blend row at 20:19:30 sits inside the wider window. Only the
    /// chart's own finish clip (20:18:30) keeps it off the page, and that clip
    /// still runs before the window (pinned by source in the next test).
    func testTheChartsOwnFinishClipStillBindsInsideTheWiderWindow() throws {
        let detail = try event(status: "completed")
        let drift = try legacyHistory(extraBlend: [(270, 0.99)])
        let journey = try lateJourney()
        let legacy = try XCTUnwrap(legacyWindow(detail, drift, .sinceStart))
        XCTAssertEqual(legacy.upperBound, at(120), "fixture: blend rows do not move the legacy end")
        let page = try XCTUnwrap(pageWindow(detail, drift, .sinceStart, journey: journey, key: key(detail: detail)))
        XCTAssertTrue(page.contains(at(270)), "control: the drift row is inside the wider window")
        XCTAssertEqual(OddsChartView.gameEndDate(status: "completed", history: drift), at(210),
                       "fixture: the chart's legacy finish clip")
        XCTAssertTrue(OddsChartView.chartPoints(from: drift).contains {
            $0.date == at(270) && $0.source == PublicationCheckpointMount4974.blendSource
        }, "control: the drift row is a blend point the chart would draw unclipped")

        let drawn = try drawnPoints(drift, domain: page, range: .sinceStart)
        XCTAssertFalse(drawn.contains { $0.date == at(270) })
        XCTAssertEqual(signature(drawn), signature(try drawnPoints(drift, domain: legacy, range: .sinceStart)))
    }

    /// The window is the only thing that changed: both charts take it, the
    /// probability chart is handed the same guarded journey that widened it,
    /// both axes are the forced window, and both charts' own finish clips still
    /// run. Inline and fullscreen share one mount (`PublicationCheckpointChart4974Tests`).
    func testBothChartsTakeTheOneWindowAndKeepTheirFinishClips() throws {
        let page = try code("Bain Luck/Views/EventDetailView.swift")
        XCTAssertEqual(page.components(separatedBy: "forcedDomain:sharedChartDomain,").count - 1, 2,
                       "the probability chart and the score chart")
        XCTAssertEqual(page.components(
            separatedBy: "forcedDomain:sharedChartDomain,legacyDataDomain:legacyChartDataDomain,").count - 1, 2,
                       "both charts take the one axis AND the one legacy ink window")
        XCTAssertTrue(page.contains(
            "privatevarlegacyChartDataDomain:ClosedRange<Date>?{Self.pageLegacyChartDataDomain(event:vm.event,history:vm.history,range:chartRange,journey:vm.publicationJourney,key:publicationTaskKey)}"))
        XCTAssertTrue(page.contains(
            "guardchartPublicationJourney(journey,key:key)!=nilelse{returnnil}returnpageLegacyChartDomain(event:event,history:history,range:range,now:now)"),
                      "the ink window is handed only for the journey the chart is handed")
        XCTAssertTrue(page.contains(
            "letlegacyDomain=pageLegacyChartDomain(event:event,history:history,range:range,now:now)returnpublicationSharedChartDomain(legacyDomain,journey:journey,key:key)"),
                      "the axis widens the same one legacy window the ink keeps")
        XCTAssertTrue(page.contains(
            "privatevarsharedChartDomain:ClosedRange<Date>?{Self.pageSharedChartDomain(event:vm.event,history:vm.history,range:chartRange,journey:vm.publicationJourney,key:publicationTaskKey)}"))
        XCTAssertTrue(page.contains("returnpublicationSharedChartDomain(legacyDomain,journey:journey,key:key)"))
        XCTAssertTrue(page.contains("letcurrent=chartPublicationJourney(journey,key:key)"),
                      "the window widens only for the journey the chart is handed")
        XCTAssertTrue(page.contains("publicationJourney:Self.chartPublicationJourney(vm.publicationJourney,key:publicationTaskKey))"))

        let chart = try code("Bain Luck/Components/OddsChartView.swift")
        XCTAssertTrue(chart.contains("ifletforced=forcedDomain{returnforced}"))
        XCTAssertTrue(chart.contains("ifEventState.isFinished(status),letendDate=gameEndDate{filtered=filtered.filter{$0.date<=endDate}}"),
                      "the legacy finish clip")
        let score = try code("Bain Luck/Components/ScoreDifferentialChartView.swift")
        XCTAssertTrue(score.contains("ifletforced=forcedDomain{returnforced}"))
        XCTAssertTrue(score.contains("ifletendDate{returncontained.filter{$0.date<=endDate}}"),
                      "the score chart's finish clip")
    }

    /// The score line gains no reading and no new margin, and the #9175 carry
    /// does NOT follow the wider axis: the chart carries to
    /// `min(axis end, legacyDataDomain end)` and the page hands the original
    /// window as `legacyDataDomain`, so the final margin still ends at 20:17:00,
    /// not 20:21:30 (Root's B). The real chart's carry: the hosted score render
    /// in the ink section below.
    func testTheScoreLineGainsNoReadingAndItsFinalCarryStopsAtTheOriginalWindow() throws {
        let detail = try event(status: "completed")
        let history = try legacyHistory()
        let journey = try lateJourney()
        let legacy = try XCTUnwrap(legacyWindow(detail, history, .sinceStart))
        let page = try XCTUnwrap(pageWindow(detail, history, .sinceStart, journey: journey,
                                            key: key(detail: detail)))
        let ink = try XCTUnwrap(inkWindow(detail, history, .sinceStart, journey: journey,
                                          key: key(detail: detail)))
        XCTAssertEqual(ink, legacy, "the page's ink window is the original window")
        let edge = min(page.upperBound, ink.upperBound)
        XCTAssertLessThan(edge, page.upperBound, "control: the axis did widen past the original end")
        let readings: [(date: Date, diff: Double)] = [(at(-11_400), 0), (at(-5_700), 1), (at(90), 2)]
        let before = ScoreDifferentialChartView.actualSteps(readings, carriedTo: legacy.upperBound)
        let after = ScoreDifferentialChartView.actualSteps(readings, carriedTo: edge)
        XCTAssertEqual(after.dropLast().map { $0.date }, readings.map { $0.date })
        XCTAssertEqual(after.dropLast().map { $0.diff }, readings.map { $0.diff })
        XCTAssertEqual(after.count, before.count, "one carry before, one after")
        XCTAssertEqual(after.last?.diff, 2, "the carry repeats the final margin")
        XCTAssertEqual(after.last?.date, legacy.upperBound, "the carry ends where the original window ends")
        XCTAssertEqual(before.last?.date, legacy.upperBound)
    }

    /// No blend line: the chart's own admission refuses the journey under the
    /// wider window, so no dot or checkpoint readout can appear.
    func testWithoutABlendLineTheWiderWindowMountsNothing() throws {
        let detail = try event(status: "completed")
        let history = try legacyHistory(blend: false)
        let journey = try lateJourney()
        let page = try XCTUnwrap(pageWindow(detail, history, .sinceStart, journey: journey, key: key(detail: detail)))
        XCTAssertFalse(try drawnPoints(history, domain: page, range: .sinceStart).isEmpty,
                       "control: the chart still has points to draw")
        XCTAssertNil(try checkpointMount(journey, history, domain: page, range: .sinceStart))
        XCTAssertNotNil(try checkpointMount(journey, try legacyHistory(), domain: page, range: .sinceStart),
                        "control: with the blend line the same window mounts")
    }

    // MARK: Hosted, on the page's window

    private func code(_ path: String) throws -> String {
        let url = URL(fileURLWithPath: #filePath)
            .deletingLastPathComponent()   // BainLuckTests
            .deletingLastPathComponent()   // Bain Luck (project dir)
            .appendingPathComponent(path)
        return try String(contentsOf: url, encoding: .utf8)
            .split(separator: "\n", omittingEmptySubsequences: false)
            .map { line -> String in
                guard let slashes = line.range(of: "//") else { return String(line) }
                return String(line[line.startIndex..<slashes.lowerBound])
            }
            .joined(separator: "\n")
            .filter { !$0.isWhitespace }
    }

    private func pumpShown(_ host: UIViewController, times: Int = 5) {
        for _ in 0..<times {
            host.view.setNeedsLayout()
            host.view.layoutIfNeeded()
            RunLoop.current.run(until: Date().addingTimeInterval(0.02))
        }
    }

    private func readText(_ host: UIViewController, name: String) throws -> String {
        let image = UIGraphicsImageRenderer(bounds: host.view.bounds).image { _ in
            host.view.drawHierarchy(in: host.view.bounds, afterScreenUpdates: true)
        }
        let url = FileManager.default.temporaryDirectory.appendingPathComponent("4974-window-\(name).png")
        try XCTUnwrap(image.pngData()).write(to: url)
        print("#4974 rendered evidence: \(url.path)")
        let request = VNRecognizeTextRequest()
        request.recognitionLevel = .accurate
        try VNImageRequestHandler(cgImage: XCTUnwrap(image.cgImage)).perform([request])
        return (request.results ?? []).compactMap { $0.topCandidates(1).first?.string }.joined(separator: " ")
    }

    /// The real chart as the page builds it, on `domain`, with `legacy` as its
    /// ink window (`nil`, the default, is every chart's prior behaviour).
    private func pageChart(_ history: EventHistoryResponse, journey: Journey?, domain: ClosedRange<Date>?,
                           legacy: ClosedRange<Date>? = nil, range: OddsTimeRange = .sinceStart,
                           model: OddsChartViewModel? = nil,
                           selection: OddsChartSelection? = nil) -> OddsChartView {
        OddsChartView(eventId: Self.eventID, commenceTime: "2026-10-04T17:05:00Z", status: "completed",
                      homeTeamName: "Red Sox", awayTeamName: "Yankees",
                      forcedDomain: domain, legacyDataDomain: legacy,
                      selectedRange: .constant(range), preloadedHistory: history,
                      readout: GamePlayCardView(homeTeam: "Red Sox", awayTeam: "Yankees", lastPoint: nil),
                      publicationJourney: journey, model: model, selection: selection)
    }

    /// `view` in a key window on the active scene with the LOOK rig's
    /// fullscreen flag (#9185) set, so the probability chart opens its cover.
    /// `whileMounted` runs once the window shows; the cover is read when it is
    /// open and `ready` holds.
    private func fullscreenText<V: View>(_ view: V, name: String,
                                         whileMounted: () -> Void = {},
                                         ready: () -> Bool = { true }) throws -> String {
        let defaults = UserDefaults.standard
        defaults.set(true, forKey: LaunchRig.chartFullscreenKey)
        defer { defaults.removeObject(forKey: LaunchRig.chartFullscreenKey) }
        let scenes = UIApplication.shared.connectedScenes.compactMap { $0 as? UIWindowScene }
        let scene = scenes.first { $0.activationState == .foregroundActive } ?? scenes.first
        let previousKey = scene?.windows.first { $0.isKeyWindow }
        let host = hostForMeasurement(view.frame(width: 390), at: .large)
        let window = scene.map { UIWindow(windowScene: $0) } ?? UIWindow()
        window.frame = CGRect(x: 0, y: 0, width: 390, height: 844)
        window.rootViewController = host
        window.makeKeyAndVisible()
        defer {
            host.dismiss(animated: false)
            window.isHidden = true
            previousKey?.makeKey()
        }
        whileMounted()
        let deadline = Date().addingTimeInterval(10)
        while host.presentedViewController == nil || !ready(), Date() < deadline {
            RunLoop.current.run(until: Date().addingTimeInterval(0.05))
        }
        XCTAssertTrue(ready(), "\(name): never ready")
        let cover = try XCTUnwrap(host.presentedViewController, "\(name): the fullscreen cover never opened")
        pumpShown(cover, times: 12)
        return try readText(cover, name: name)
    }

    /// The real inline chart on the page's window, scrubbed onto the stored
    /// 20:21 dot, prints its 96%. POSITIVE CONTROL: on the old window the
    /// rightmost finger prints the legacy 88%, and the same stored hit carried
    /// into it prints nothing of the checkpoint.
    func testHostedChartOnThePageWindowScrubsTheStoredDot() throws {
        let detail = try event(status: "completed")
        let history = try legacyHistory()
        let journey = try lateJourney()
        let page = try XCTUnwrap(pageWindow(detail, history, .sinceStart, journey: journey,
                                            key: key(detail: detail)))
        let legacy = try XCTUnwrap(legacyWindow(detail, history, .sinceStart))
        let latest = try XCTUnwrap(try checkpointMount(journey, history, domain: page, range: .sinceStart)?.drawn.last)

        func scrubbed(on domain: ClosedRange<Date>, date: Date, scrub: PublicationCheckpointScrub4974?,
                      name: String) throws -> (builds: Int, text: String) {
            let model = OddsChartViewModel(eventId: Self.eventID, preloaded: history)
            var builds = 0
            model.onPlotBuild = { builds += 1 }
            defer { model.onPlotBuild = nil }
            let selection = OddsChartSelection()
            let host = hostForMeasurement(
                pageChart(history, journey: journey, domain: domain, model: model, selection: selection)
                    .frame(width: 390), at: .large)
            host.view.frame = CGRect(x: 0, y: 0, width: 390, height: 844)
            let window = UIWindow(frame: host.view.frame)
            window.rootViewController = host
            window.isHidden = false
            defer { window.isHidden = true }
            pumpShown(host, times: 12)
            selection.hold(date: date, checkpoint: scrub)
            pumpShown(host)
            return (builds, try readText(host, name: name))
        }

        let hit = try scrubbed(on: page, date: latest.date, scrub: .checkpoint(latest), name: "page-window-hit")
        XCTAssertGreaterThan(hit.builds, 0, "the real plot must render for this test to mean anything")
        XCTAssertTrue(hit.text.contains("96%"), hit.text)
        XCTAssertFalse(hit.text.contains("88%"), "the legacy value stood in for the stored dot: \(hit.text)")

        let old = try scrubbed(on: legacy, date: legacy.upperBound, scrub: nil, name: "old-window-edge")
        XCTAssertTrue(old.text.contains("88%"), "control: the old window's finger reads the legacy line: \(old.text)")
        XCTAssertFalse(old.text.contains("96%"), old.text)
        let stale = try scrubbed(on: legacy, date: latest.date, scrub: .checkpoint(latest), name: "old-window-stale-hit")
        XCTAssertFalse(stale.text.contains("96%"), "a dot the old window clips was printed: \(stale.text)")
    }

    /// The fullscreen chart on the page's window rests on the stored 96%; on
    /// the old window (POSITIVE CONTROL) it rests on the legacy 88%.
    func testHostedFullscreenOnThePageWindowRestsOnTheStoredCheckpoint() throws {
        let detail = try event(status: "completed")
        let history = try legacyHistory()
        let journey = try lateJourney()
        let page = try XCTUnwrap(pageWindow(detail, history, .sinceStart, journey: journey,
                                            key: key(detail: detail)))
        let legacy = try XCTUnwrap(legacyWindow(detail, history, .sinceStart))

        let corrected = try fullscreenText(pageChart(history, journey: journey, domain: page),
                                           name: "fullscreen-page-window")
        XCTAssertTrue(corrected.contains("96%"), corrected)
        XCTAssertFalse(corrected.contains("88%"), "rested on the legacy end: \(corrected)")

        let old = try fullscreenText(pageChart(history, journey: journey, domain: legacy),
                                     name: "fullscreen-old-window")
        XCTAssertTrue(old.contains("88%"), "control: the old window rests on the legacy end: \(old)")
        XCTAssertFalse(old.contains("96%"), old)
    }

    /// The mounted page itself: its own load, its own one checkpoint read, its
    /// own window, its own probability chart's fullscreen cover resting on the
    /// stored 96%. The detail is held until the history read has been asked
    /// and answered, so the chart mounts with the page's history (it would
    /// otherwise fetch its own).
    func testTheMountedPageHandsItsChartTheWindowThatReachesTheStoredCheckpoints() throws {
        let detail = try event(status: "completed")
        let client = Client(detail: detail, publications: lateBody(), history: try legacyHistory())
        client.holdDetails(true)
        let vm = makeVM(client: client)
        defer { vm.stopRefresh() }
        let page = NavigationStack { EventDetailView(eventId: Self.eventID, viewModel: vm) }
            .environmentObject(PinManager())
            .environment(\.scenePhase, .active).environment(\.colorScheme, .light)

        let text = try fullscreenText(page, name: "mounted-page-fullscreen", whileMounted: {
            let deadline = Date().addingTimeInterval(5)
            while client.parkedDetailCount == 0 || client.historyRequestCount == 0, Date() < deadline {
                RunLoop.current.run(until: Date().addingTimeInterval(0.02))
            }
            RunLoop.current.run(until: Date().addingTimeInterval(0.2))
            client.holdDetails(false)
            client.answerDetail(0, with: .serve(detail))
        }, ready: { vm.history != nil && vm.publicationJourney != nil })

        XCTAssertEqual(client.publicationRequests, [Self.eventID], "the page's own load, then one read")
        XCTAssertEqual(vm.publicationJourney, try lateJourney())
        XCTAssertTrue(text.contains("96%"), text)
        XCTAssertFalse(text.contains("88%"),
                       "the page's chart rested on the legacy end: its window still clips the stored dots: \(text)")
    }

    // MARK: - The legacy ink window inside the wider axis

    /// The ink specimen (Root's B). The last ESPN row is 20:17:00 (final 5–3)
    /// and the last sportsbook row 20:16:30, so the ORIGINAL page window ends
    /// 20:17:30; with no `completed_at`, both charts' own finish clips end
    /// 20:19:00 (last ESPN row + 120 s). Inside those clips and outside the
    /// original window: post-final blend drift at 20:18:00 (71%) and 20:19:00
    /// (73%), and post-final score rows at 20:18:00 (5–5) and 20:19:00 (5–9).
    /// None of them moves either page window. `lateDrift` adds a `stat_model`
    /// row at 20:21:15 — it moves only the probability chart's finish clip, to
    /// 20:23:15 — and a blend row at 20:21:20 (77%; 75% would collide with a
    /// y-axis label): after the latest stored checkpoint, inside the wider
    /// axis, so with no ink bound it would outrank the stored 96% as the
    /// resting reading.
    private func inkHistory(blendDrift: Bool = true, scoreDrift: Bool = true,
                            lateDrift: Bool = false) throws -> EventHistoryResponse {
        func stamp(_ seconds: TimeInterval) -> String { at(seconds).ISO8601Format() }
        let espn: [[String: Any]] = [
            ["timestamp": stamp(-11_400), "home_probability": 0.55, "period": "1",
             "home_score": 0, "away_score": 0],
            ["timestamp": stamp(-5_700), "home_probability": 0.62, "period": "5",
             "home_score": 2, "away_score": 1],
            ["timestamp": stamp(120), "home_probability": 0.99, "period": "9",
             "home_score": 5, "away_score": 3],
        ]
        let odds: [[String: Any]] = [
            ["timestamp": stamp(-14_400), "home_probability": 0.52],
            ["timestamp": stamp(90), "home_probability": 0.88],
        ]
        var blend: [(TimeInterval, Double)] = [(-14_400, 0.52), (-11_400, 0.55), (-5_700, 0.62), (90, 0.88)]
        if blendDrift { blend += [(180, 0.71), (240, 0.73)] }
        if lateDrift { blend += [(380, 0.77)] }
        var scores: [(TimeInterval, Int, Int)] = [(-5_700, 2, 1), (120, 5, 3)]
        if scoreDrift { scores += [(180, 5, 5), (240, 5, 9)] }
        var object: [String: Any] = [
            "event_id": Self.eventID, "home_team": "Red Sox", "away_team": "Yankees",
            "status": "completed", "history": odds, "espn_history": espn,
            "aggregate_line": blend.map { row -> [String: Any] in
                ["timestamp": stamp(row.0), "home_probability": row.1]
            },
            "score_history": scores.map { row -> [String: Any] in
                ["timestamp": stamp(row.0), "home_score": row.1, "away_score": row.2]
            },
        ]
        if lateDrift {
            object["win_prob_history"] = ["stat_model": [["timestamp": stamp(375), "home_probability": 0.97]]]
        }
        let data = try JSONSerialization.data(withJSONObject: object)
        return try Self.decoder().decode(EventHistoryResponse.self, from: data)
    }

    /// The specimen is what it claims: the drift rows sit inside each chart's
    /// own finish clip and the wider axis, outside the original window; the
    /// page's ink window IS the original window, inside the axis on the same
    /// start; and the stored dots are admitted by the axis, never by the ink.
    func testTheInkSpecimenSitsInsideTheChartsOwnClipsAndOutsideTheOriginalWindow() throws {
        let detail = try event(status: "completed")
        let history = try inkHistory()
        let journey = try lateJourney()
        XCTAssertEqual(OddsChartView.gameEndDate(status: "completed", history: history), at(240),
                       "fixture: the probability chart's own finish clip is 20:19:00")
        XCTAssertNil(history.completedAt, "fixture: so the score chart's own clip is also last ESPN + 120 s")
        XCTAssertTrue(OddsChartView.chartPoints(from: history).contains {
            $0.date == at(240) && $0.source == PublicationCheckpointMount4974.blendSource && $0.probability == 0.73
        }, "control: the 20:19 drift is a blend point the chart would draw unbounded")
        for range in [OddsTimeRange.sinceStart, .all] {
            let legacy = try XCTUnwrap(legacyWindow(detail, history, range), "fixture: \(range)")
            XCTAssertEqual(legacy.upperBound, at(150), "the original window ends 20:17:30 (\(range))")
            let page = try XCTUnwrap(pageWindow(detail, history, range, journey: journey, key: key(detail: detail)))
            XCTAssertEqual(page.lowerBound, legacy.lowerBound, "\(range) keeps its start")
            XCTAssertEqual(page.upperBound, at(390), "the axis ends 20:21:30 (\(range))")
            let ink = try XCTUnwrap(inkWindow(detail, history, range, journey: journey, key: key(detail: detail)))
            XCTAssertEqual(ink, legacy, "the ink window is the original window, unchanged (\(range))")
            XCTAssertEqual(ink, EventDetailView.pageLegacyChartDomain(event: detail, history: history,
                                                                       range: range, now: at(0)))
            XCTAssertEqual(ink.lowerBound, page.lowerBound, "one start in both domains (\(range))")
            XCTAssertLessThanOrEqual(ink.upperBound, page.upperBound, "the ink lies inside the axis (\(range))")
            for drift in [at(180), at(240)] {
                XCTAssertTrue(page.contains(drift), "control: the drift is inside the axis (\(range))")
                XCTAssertFalse(ink.contains(drift), "the drift is outside the ink (\(range))")
            }
            XCTAssertTrue(journey.checkpoints.allSatisfy { page.contains($0.date) && !ink.contains($0.date) },
                          "the stored dots are admitted by the axis, never by the ink window (\(range))")
        }
        let late = try inkHistory(lateDrift: true)
        XCTAssertEqual(OddsChartView.gameEndDate(status: "completed", history: late), at(495),
                       "fixture: the stat_model row moves the probability clip to 20:23:15")
        XCTAssertEqual(legacyWindow(detail, late, .sinceStart), legacyWindow(detail, history, .sinceStart),
                       "fixture: and moves neither page window")
        XCTAssertEqual(pageWindow(detail, late, .sinceStart, journey: journey, key: key(detail: detail)),
                       pageWindow(detail, history, .sinceStart, journey: journey, key: key(detail: detail)))
    }

    /// The ink window is handed only where the chart's own journey guard admits
    /// a journey. Every refused input hands `nil` — each chart's exact prior
    /// behaviour — beside the axis that stays the original window; where the
    /// axis is `nil` the ink is too; and where stored dots did not widen the
    /// axis, the ink window equals it, so every cut is the old cut.
    func testTheInkWindowIsHandedOnlyWhereTheChartsJourneyGuardAdmits() throws {
        let finished = try event(status: "completed")
        let history = try inkHistory()
        let journey = try lateJourney()
        let otherDetail = try event(id: 5151, status: "completed")
        let otherJourney = try lateJourney(eventId: 5151)
        for range in [OddsTimeRange.sinceStart, .all] {
            XCTAssertEqual(inkWindow(finished, history, range, journey: journey, key: key(detail: finished)),
                           legacyWindow(finished, history, range),
                           "control: the eligible page hands the original window (\(range))")
            let cases: [(String, Journey?, PublicationTaskKey4974)] = [
                ("no journey", nil, key(detail: finished)),
                ("unready appearance", journey, key(detail: finished, ready: false)),
                ("another page", journey, key(page: 5151, detail: finished)),
                ("view model of another game", journey, key(vm: 5151, detail: finished)),
                ("detail of another game", journey, key(detail: otherDetail)),
                ("another game's journey", otherJourney, key(detail: finished)),
            ]
            for (name, held, pageKey) in cases {
                XCTAssertNil(inkWindow(finished, history, range, journey: held, key: pageKey), "\(name) (\(range))")
                XCTAssertEqual(pageWindow(finished, history, range, journey: held, key: pageKey),
                               legacyWindow(finished, history, range), "\(name): the axis stays the original (\(range))")
            }
            let unwidened = try self.journey()   // 20:15:10 and 20:15:50, inside the original window
            XCTAssertEqual(pageWindow(finished, history, range, journey: unwidened, key: key(detail: finished)),
                           legacyWindow(finished, history, range), "fixture: these dots do not widen the axis (\(range))")
            XCTAssertEqual(inkWindow(finished, history, range, journey: unwidened, key: key(detail: finished)),
                           pageWindow(finished, history, range, journey: unwidened, key: key(detail: finished)),
                           "an axis the dots did not widen IS the ink window: every cut is the old cut (\(range))")
        }
        let live = try event(status: "live")
        XCTAssertNil(inkWindow(live, history, .sinceStart, journey: journey, key: key(detail: live)), "live")
        XCTAssertNil(pageWindow(finished, nil, .sinceStart, journey: journey, key: key(detail: finished)),
                     "fixture: no history, no axis")
        XCTAssertNil(inkWindow(finished, nil, .sinceStart, journey: journey, key: key(detail: finished)),
                     "no axis, no ink window: the charts' own nil-domain paths are untouched")
        XCTAssertNil(inkWindow(nil, history, .sinceStart, journey: journey, key: key(detail: nil)))
    }

    /// The real inline chart on `domain` with `legacy` ink, its selection held
    /// at `date` (on `scrub`), read back as text.
    private func heldText(_ history: EventHistoryResponse, journey: Journey, domain: ClosedRange<Date>,
                          legacy: ClosedRange<Date>?, range: OddsTimeRange, date: Date,
                          scrub: PublicationCheckpointScrub4974?, name: String) throws -> (builds: Int, text: String) {
        let model = OddsChartViewModel(eventId: Self.eventID, preloaded: history)
        var builds = 0
        model.onPlotBuild = { builds += 1 }
        defer { model.onPlotBuild = nil }
        let selection = OddsChartSelection()
        let host = hostForMeasurement(
            pageChart(history, journey: journey, domain: domain, legacy: legacy, range: range,
                      model: model, selection: selection)
                .frame(width: 390), at: .large)
        host.view.frame = CGRect(x: 0, y: 0, width: 390, height: 844)
        let window = UIWindow(frame: host.view.frame)
        window.rootViewController = host
        window.isHidden = false
        defer { window.isHidden = true }
        pumpShown(host, times: 12)
        selection.hold(date: date, checkpoint: scrub)
        pumpShown(host)
        return (builds, try readText(host, name: name))
    }

    /// The real inline chart, in both ranges, on the page's axis with the
    /// page's ink window: the stored 20:21 dot still scrubs to its own 96%,
    /// and a finger at 20:19 reads the last real reading inside the original
    /// window (88%), never the post-final 73%. POSITIVE CONTROL — the same
    /// chart, axis, journey and finger with the ink bound removed reads 73%.
    func testHostedChartKeepsThePostFinalDriftOffTheWiderAxisAndStillScrubsTheDots() throws {
        let detail = try event(status: "completed")
        let history = try inkHistory()
        let journey = try lateJourney()
        let latest = try XCTUnwrap(journey.checkpoints.last, "fixture: rev 9 at 20:21")
        for range in [OddsTimeRange.sinceStart, .all] {
            let page = try XCTUnwrap(pageWindow(detail, history, range, journey: journey, key: key(detail: detail)))
            let ink = try XCTUnwrap(inkWindow(detail, history, range, journey: journey, key: key(detail: detail)))

            let hit = try heldText(history, journey: journey, domain: page, legacy: ink, range: range,
                                   date: latest.date, scrub: .checkpoint(latest), name: "ink-hit-\(range)")
            XCTAssertGreaterThan(hit.builds, 0, "the real plot must render for this test to mean anything")
            XCTAssertTrue(hit.text.contains("96%"), "\(range): the stored dot stopped scrubbing: \(hit.text)")

            let drift = try heldText(history, journey: journey, domain: page, legacy: ink, range: range,
                                     date: at(240), scrub: nil, name: "ink-drift-\(range)")
            XCTAssertTrue(drift.text.contains("88%"), "\(range): \(drift.text)")
            XCTAssertFalse(drift.text.contains("73%") || drift.text.contains("71%"),
                           "\(range): post-final drift outside the original window was read: \(drift.text)")

            let unbound = try heldText(history, journey: journey, domain: page, legacy: nil, range: range,
                                       date: at(240), scrub: nil, name: "no-ink-drift-\(range)")
            XCTAssertTrue(unbound.text.contains("73%"),
                          "\(range): control: without the ink bound the drift is read, so the bound is what holds it off: \(unbound.text)")
        }
    }

    /// The fullscreen cover shares the inline chart's state and cuts. In both
    /// ranges, with the page's ink window, it rests on the stored 96% and a
    /// held 20:19 finger reads 88%. POSITIVE CONTROL — without the ink bound
    /// the post-final 20:21:20 blend row (77%) outranks the stored dot as the
    /// resting reading, and the held finger reads the 73% drift.
    func testHostedFullscreenRestsOnTheStoredDotAndReadsNoDriftUnderTheInkWindow() throws {
        let detail = try event(status: "completed")
        let late = try inkHistory(lateDrift: true)
        let journey = try lateJourney()
        let driftTime = at(240)
        for range in [OddsTimeRange.sinceStart, .all] {
            let page = try XCTUnwrap(pageWindow(detail, late, range, journey: journey, key: key(detail: detail)))
            let ink = try XCTUnwrap(inkWindow(detail, late, range, journey: journey, key: key(detail: detail)))
            XCTAssertTrue(page.contains(at(380)) && !ink.contains(at(380)), "fixture: the late drift is axis-only (\(range))")

            let rest = try fullscreenText(pageChart(late, journey: journey, domain: page, legacy: ink, range: range),
                                          name: "ink-fullscreen-rest-\(range)")
            XCTAssertTrue(rest.contains("96%"), "\(range): \(rest)")
            XCTAssertFalse(rest.contains("77%"), "\(range): rested on post-final drift: \(rest)")

            let unboundRest = try fullscreenText(pageChart(late, journey: journey, domain: page, legacy: nil, range: range),
                                                 name: "no-ink-fullscreen-rest-\(range)")
            XCTAssertTrue(unboundRest.contains("77%"),
                          "\(range): control: without the ink bound the late drift is the resting reading: \(unboundRest)")

            let selection = OddsChartSelection()
            let held = try fullscreenText(
                pageChart(late, journey: journey, domain: page, legacy: ink, range: range, selection: selection),
                name: "ink-fullscreen-held-\(range)", whileMounted: { selection.hold(date: driftTime, checkpoint: nil) })
            XCTAssertTrue(held.contains("88%"), "\(range): \(held)")
            XCTAssertFalse(held.contains("73%"), "\(range): the held finger read post-final drift: \(held)")

            let unboundSelection = OddsChartSelection()
            let unboundHeld = try fullscreenText(
                pageChart(late, journey: journey, domain: page, legacy: nil, range: range, selection: unboundSelection),
                name: "no-ink-fullscreen-held-\(range)",
                whileMounted: { unboundSelection.hold(date: driftTime, checkpoint: nil) })
            XCTAssertTrue(unboundHeld.contains("73%"), "\(range): control: \(unboundHeld)")
        }
    }

    /// The real score chart on `domain` with `legacy` ink, rendered at 3x on
    /// white as the page lays it out: its RGBA bytes, its teal (#0d9488, the
    /// actual series) pixel count above the legend band, and the rightmost
    /// teal column there (`ALoneFinalScoreIsDrawnNotJustNamed8997Tests`' rule).
    private func scoreRender(_ history: EventHistoryResponse, domain: ClosedRange<Date>?,
                             legacy: ClosedRange<Date>?, range: OddsTimeRange,
                             name: String) throws -> (bytes: [UInt8], teal: Int, rightmostTeal: Int?) {
        let view = ScoreDifferentialChartView(
            history: history, homeTeam: "Red Sox", awayTeam: "Yankees",
            commenceTime: "2026-10-04T17:05:00Z", eventStatus: "completed",
            homeTeamColor: .red, awayTeamColor: .blue,
            forcedDomain: domain, legacyDataDomain: legacy, range: range)
            .padding(16)
            .frame(width: 390)
            .background(Color.white)
        let renderer = rendererForMeasurement(view)
        renderer.scale = 3
        let image = try XCTUnwrap(renderer.cgImage)
        let url = FileManager.default.temporaryDirectory.appendingPathComponent("4974-ink-\(name).png")
        try? UIImage(cgImage: image).pngData()?.write(to: url)
        print("#4974 rendered evidence: \(url.path)")

        let w = image.width, h = image.height
        var bytes = [UInt8](repeating: 0, count: w * h * 4)
        let ctx = try XCTUnwrap(CGContext(
            data: &bytes, width: w, height: h, bitsPerComponent: 8, bytesPerRow: w * 4,
            space: CGColorSpaceCreateDeviceRGB(),
            bitmapInfo: CGImageAlphaInfo.premultipliedLast.rawValue))
        ctx.draw(image, in: CGRect(x: 0, y: 0, width: w, height: h))
        let legendBand = 50 * 3
        var teal = 0
        var rightmost: Int?
        for y in 0..<max(0, h - legendBand) {
            for x in 0..<w {
                let i = (y * w + x) * 4
                let r = Int(bytes[i]), g = Int(bytes[i + 1]), b = Int(bytes[i + 2])
                if r < 70, g > 110, b > 100, g - r > 60, abs(g - b) < 40 {
                    teal += 1
                    rightmost = max(rightmost ?? x, x)
                }
            }
        }
        return (bytes, teal, rightmost)
    }

    /// The real score chart, in both ranges, on the page's axis with the page's
    /// ink window: the post-final 20:18 and 20:19 score rows draw nothing (the
    /// render is byte-identical to the same game without them), and the final
    /// margin's carry stops short of the wider axis edge. POSITIVE CONTROLS —
    /// with the ink bound removed the post-final rows change the render, and
    /// the carry runs on toward 20:21:30. Where exactly the carry stops
    /// (20:17:30) is the chart rule's own test (latency's
    /// `PublicationAxisInk4974Tests`) and the static case above.
    func testTheRealScoreChartDrawsNoPostFinalRowAndItsCarryStopsShortOfTheWiderAxis() throws {
        let detail = try event(status: "completed")
        let journey = try lateJourney()
        let drift = try inkHistory()
        let clean = try inkHistory(scoreDrift: false)
        for range in [OddsTimeRange.sinceStart, .all] {
            let page = try XCTUnwrap(pageWindow(detail, drift, range, journey: journey, key: key(detail: detail)))
            let ink = try XCTUnwrap(inkWindow(detail, drift, range, journey: journey, key: key(detail: detail)))
            XCTAssertEqual(pageWindow(detail, clean, range, journey: journey, key: key(detail: detail)), page,
                           "fixture: the score rows move no window (\(range))")
            XCTAssertEqual(inkWindow(detail, clean, range, journey: journey, key: key(detail: detail)), ink)

            let bounded = try scoreRender(drift, domain: page, legacy: ink, range: range, name: "score-drift-\(range)")
            let bare = try scoreRender(clean, domain: page, legacy: ink, range: range, name: "score-clean-\(range)")
            XCTAssertGreaterThan(bounded.teal, 150, "\(range): the actual series must draw for this to mean anything")
            XCTAssertTrue(bounded.bytes == bare.bytes, "\(range): a post-final score row outside the original window drew ink")

            let unbound = try scoreRender(drift, domain: page, legacy: nil, range: range, name: "no-ink-score-drift-\(range)")
            XCTAssertFalse(unbound.bytes == bounded.bytes,
                           "\(range): control: without the ink bound the post-final rows draw, so the bound is what holds them off")

            let axisCarry = try scoreRender(clean, domain: page, legacy: nil, range: range, name: "no-ink-score-carry-\(range)")
            let inkEnd = try XCTUnwrap(bare.rightmostTeal)
            let axisEnd = try XCTUnwrap(axisCarry.rightmostTeal)
            XCTAssertGreaterThanOrEqual(axisEnd - inkEnd, 2 * 3,
                                        "\(range): the final margin was carried past the original window toward the axis edge")
        }
    }

    /// The mounted page itself (Since Start, its default — the page's range
    /// control has no hosted driver; All is the same two helpers, pinned
    /// above): its own load, its own read, its own windows. On the late-drift
    /// specimen its probability chart's fullscreen cover rests on the stored
    /// 96%. Had the page handed its charts no ink window it would rest on the
    /// post-final 77% — the positive control is the same chart, axis and
    /// payload unbound in `testHostedFullscreenRestsOnTheStoredDotAndReadsNoDriftUnderTheInkWindow`.
    func testTheMountedPageKeepsItsLegacyInkInsideTheOriginalWindow() throws {
        let detail = try event(status: "completed")
        let late = try inkHistory(lateDrift: true)
        let client = Client(detail: detail, publications: lateBody(), history: late)
        client.holdDetails(true)
        let vm = makeVM(client: client)
        defer { vm.stopRefresh() }
        let page = NavigationStack { EventDetailView(eventId: Self.eventID, viewModel: vm) }
            .environmentObject(PinManager())
            .environment(\.scenePhase, .active).environment(\.colorScheme, .light)

        let text = try fullscreenText(page, name: "mounted-page-ink-fullscreen", whileMounted: {
            let deadline = Date().addingTimeInterval(5)
            while client.parkedDetailCount == 0 || client.historyRequestCount == 0, Date() < deadline {
                RunLoop.current.run(until: Date().addingTimeInterval(0.02))
            }
            RunLoop.current.run(until: Date().addingTimeInterval(0.2))
            client.holdDetails(false)
            client.answerDetail(0, with: .serve(detail))
        }, ready: { vm.history != nil && vm.publicationJourney != nil })

        XCTAssertEqual(client.publicationRequests, [Self.eventID], "the page's own load, then one read")
        XCTAssertEqual(vm.publicationJourney, try lateJourney())
        XCTAssertTrue(text.contains("96%"), text)
        XCTAssertFalse(text.contains("77%"),
                       "the page's chart rested on post-final drift: it was handed no ink window: \(text)")
        XCTAssertEqual(inkWindow(vm.event, vm.history, .sinceStart, journey: vm.publicationJourney,
                                 key: key(detail: vm.event)),
                       legacyWindow(detail, late, .sinceStart), "the page's own inputs give the original window")
    }
}
