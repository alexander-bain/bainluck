import XCTest
@testable import Bain_Luck

/// L2-198 — `SearchViewModel.search()` full-search stale-response race.
///
/// The full-search path had no cancellation, no stored Task, and no
/// request-generation guard, so two overlapping `search()` calls (rapid
/// sport-filter toggles, submit-then-tap-a-suggestion, deep links) resolved in
/// completion order and a slower OLDER response could overwrite a newer query's
/// results. These tests drive the view model through a manually-released fake
/// transport (the injectable `searchFetch` seam) so out-of-order completion,
/// field clearing, and surface-disappear are all exercised deterministically —
/// none of which a pure predicate test can reach.
final class SearchViewModelRaceTests: XCTestCase {

    // MARK: - Manually-released fake transport

    /// Off-MainActor, lock-guarded fake so `searchFetch` genuinely suspends when
    /// awaited from the @MainActor view model, and the test controls exactly
    /// when (and in which order) each query's response is released.
    private nonisolated final class ManualSearchTransport: @unchecked Sendable {
        private let lock = NSLock()
        private var pending: [String: CheckedContinuation<SearchResponse, Error>] = [:]
        private var starts: [String: XCTestExpectation] = [:]
        private var stopped = false

        func fetch(query: String, sport: String?) async throws -> SearchResponse {
            try await withCheckedThrowingContinuation { cont in
                lock.lock()
                guard !stopped else {
                    lock.unlock()
                    cont.resume(throwing: CancellationError())
                    return
                }
                pending[query] = cont
                let started = starts.removeValue(forKey: query)
                lock.unlock()
                started?.fulfill()
            }
        }

        // Register before or after fetch enters: neither scheduling order
        // can lose the signal that the continuation is ready to be released.
        func startedExpectation(_ query: String) -> XCTestExpectation {
            let expectation = XCTestExpectation(description: "search started: \(query)")
            lock.lock()
            let alreadyPending = pending[query] != nil
            if !alreadyPending { starts[query] = expectation }
            lock.unlock()
            if alreadyPending { expectation.fulfill() }
            return expectation
        }

        // Timeout cleanup must also reject a fetch that starts after cleanup.
        func stop() {
            lock.lock()
            stopped = true
            let waiting = Array(pending.values)
            pending.removeAll()
            starts.removeAll()
            lock.unlock()
            for continuation in waiting {
                continuation.resume(throwing: CancellationError())
            }
        }

        func hasPending(_ query: String) -> Bool {
            lock.lock(); defer { lock.unlock() }
            return pending[query] != nil
        }

        func complete(_ query: String, with response: SearchResponse) {
            lock.lock()
            let cont = pending.removeValue(forKey: query)
            lock.unlock()
            cont?.resume(returning: response)
        }
    }

    private func makeResponse(query: String) -> SearchResponse {
        let json = "{\"query\":\"\(query)\",\"results\":[],\"futures\":[]}"
        return try! JSONDecoder().decode(SearchResponse.self, from: Data(json.utf8))
    }

    /// Await the fake transport's actual start signal; a count of Task.yield
    /// calls is not a bound on elapsed time or proof that search was scheduled.
    private func waitForPending(_ transport: ManualSearchTransport, _ query: String) async -> Bool {
        let started = transport.startedExpectation(query)
        await fulfillment(of: [started], timeout: 10)
        guard transport.hasPending(query) else {
            // XCTest records the timeout; stop before exercising a nonexistent
            // in-flight response and drain any other pending fake requests.
            transport.stop()
            return false
        }
        return true
    }

    // MARK: - Tests

    @MainActor
    func testOlderQueryCannotOverwriteNewer() async {
        let transport = ManualSearchTransport()
        let vm = SearchViewModel(searchFetch: { q, s in try await transport.fetch(query: q, sport: s) })

        vm.query = "raider"
        let older = Task { await vm.search() }
        guard await waitForPending(transport, "raider") else {
            older.cancel()
            await older.value
            return
        }

        vm.query = "raiders"
        let newer = Task { await vm.search() }
        guard await waitForPending(transport, "raiders") else {
            older.cancel()
            newer.cancel()
            await older.value
            await newer.value
            return
        }

        // Newer resolves FIRST (correct result lands)...
        transport.complete("raiders", with: makeResponse(query: "raiders"))
        // ...then the older, slower request resolves LAST — the classic race.
        transport.complete("raider", with: makeResponse(query: "raider"))

        await older.value
        await newer.value

        // Only the newest query's result survived; the stale one was dropped.
        XCTAssertEqual(vm.results?.query, "raiders")
        XCTAssertFalse(vm.loading)
    }

    @MainActor
    func testClearedFieldDropsInFlightResponse() async {
        let transport = ManualSearchTransport()
        let vm = SearchViewModel(searchFetch: { q, s in try await transport.fetch(query: q, sport: s) })

        vm.query = "wizards"
        let task = Task { await vm.search() }
        guard await waitForPending(transport, "wizards") else {
            task.cancel()
            await task.value
            return
        }

        // User clears the field before the response arrives.
        vm.cancelInFlightWork()
        vm.query = ""
        vm.results = nil

        transport.complete("wizards", with: makeResponse(query: "wizards"))
        await task.value

        // The cleared field must stay empty — no repopulation from the late reply.
        XCTAssertNil(vm.results)
        XCTAssertFalse(vm.loading)
    }

    @MainActor
    func testDisappearDropsLateResponse() async {
        let transport = ManualSearchTransport()
        let vm = SearchViewModel(searchFetch: { q, s in try await transport.fetch(query: q, sport: s) })

        vm.query = "celtics"
        let task = Task { await vm.search() }
        guard await waitForPending(transport, "celtics") else {
            task.cancel()
            await task.value
            return
        }

        // Surface disappears (navigation away) → onDisappear calls this.
        vm.cancelInFlightWork()

        transport.complete("celtics", with: makeResponse(query: "celtics"))
        await task.value

        // No setState published onto the absent surface.
        XCTAssertNil(vm.results)
        XCTAssertFalse(vm.loading)
    }

    @MainActor
    func testLatestQueryStillPublishesNormally() async {
        let transport = ManualSearchTransport()
        let vm = SearchViewModel(searchFetch: { q, s in try await transport.fetch(query: q, sport: s) })

        vm.query = "lakers"
        let task = Task { await vm.search() }
        guard await waitForPending(transport, "lakers") else {
            task.cancel()
            await task.value
            return
        }

        transport.complete("lakers", with: makeResponse(query: "lakers"))
        await task.value

        // A clean, uncontested search publishes as before.
        XCTAssertEqual(vm.results?.query, "lakers")
        XCTAssertFalse(vm.loading)
        XCTAssertNil(vm.error)
    }
}
