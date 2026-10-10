import XCTest
@testable import Bain_Luck

@MainActor final class WatchForegroundUpdatesTests: XCTestCase {
    private final class Handle: LiveStreamHandle {
        var isClosed = false
        var closes = 0
        var handlers: [String: [@MainActor (String) -> Void]] = [:]
        func on(_ event: String, _ handler: @escaping @MainActor (String) -> Void) {
            handlers[event, default: []].append(handler)
        }
        func close() { isClosed = true; closes += 1 }
        func fire(_ event: String, _ raw: String) { handlers[event]?.forEach { $0(raw) } }
    }
    private actor Detail: WatchSelectedGameTransport {
        var calls = 0
        func fetch(eventID: Int) async throws -> WatchSelectedGame {
            calls += 1
            return try WatchForegroundUpdatesTests.game(revision: calls, home: calls == 1 ? 0.50 : 0.61)
        }
    }
    nonisolated private static func game(revision: Int, home: Double = 0.6, status: String = "live",
                                         scoreClock: String = "2026-10-10T09:00:00Z",
                                         priceClock: String = "2026-10-10T09:00:00Z") throws -> WatchSelectedGame {
        let object: [String: Any] = ["id": 101, "home_team": "Home", "away_team": "Away", "status": status,
            "hero_probability": home, "hero_probability_away": 0.29,
            "hero_probability_source": "blend", "hero_probability_observed_at": priceClock,
            "score_observed_at": scoreClock, "sport": "soccer_epl",
            "current_odds": ["draw_probability": 0.10], "blend_fold_revision": ["101": revision]]
        return try JSONDecoder().decode(WatchSelectedGame.self, from: JSONSerialization.data(withJSONObject: object))
    }

    func testOneVisibleStreamRefreshesAuthoritativeDetailWithoutPaintingRawFrame() async throws {
        let name = "watch-stream-\(UUID())"
        let defaults = try XCTUnwrap(UserDefaults(suiteName: name))
        defer { defaults.removePersistentDomain(forName: name) }
        var clock = 1_000.0
        let transport = Detail()
        let selected = WatchSelectedGameStore(transport: transport, defaults: defaults, retryClock: { clock })
        selected.select(eventID: 101)
        let handle = Handle()
        var opens = 0, sleeps = 0
        await selected.runLiveForegroundRefresh(open: { id in
            XCTAssertEqual(id, 101); opens += 1; return handle
        }, clock: { clock }, sleep: { seconds in
            sleeps += 1
            if selected.successfulRefreshSequence == 2 || sleeps > 10 { throw CancellationError() }
            clock += seconds
            if sleeps == 1 {
                handle.fire("probability", #"{"event_id":101,"p":0.99,"rev":{"101":2}}"#)
            }
        })
        XCTAssertEqual(selected.successfulRefreshSequence, 2)
        XCTAssertEqual(selected.game?.homeProbability, 0.61)
        XCTAssertEqual(selected.game?.awayProbability, 0.29)
        XCTAssertEqual(selected.game?.drawProbability, 0.10)
        XCTAssertEqual(selected.game?.probabilitySource, "blend")
        XCTAssertLessThan(clock - 1_000, 30)
        XCTAssertEqual(opens, 1)
        XCTAssertEqual(handle.closes, 1)
    }

    func testInvalidationDuringFetchEarnsOneFollowupAndDuplicatesDoNot() {
        let signal = WatchForegroundInvalidation()
        var wakeups = 0
        signal.onPending = { wakeups += 1 }
        let first = LiveStreamFrame(eventId: 101, p: 0.5, source: nil, sourceValue: nil,
            updatedAt: nil, status: nil, rev: .init(FoldRevision(["101": 1])))
        let newer = LiveStreamFrame(eventId: 101, p: 0.6, source: nil, sourceValue: nil,
            updatedAt: nil, status: nil, rev: .init(FoldRevision(["101": 2])))
        signal.receive(first, eventID: 101)
        signal.take(at: 100)
        signal.receive(newer, eventID: 101)
        signal.receive(newer, eventID: 101)
        signal.receive(first, eventID: 101)
        XCTAssertTrue(signal.pending)
        XCTAssertEqual(wakeups, 2, "One initial wake and one in-flight follow-up, no duplicate wakes")
        XCTAssertEqual(signal.delay(at: 101), 1)
        signal.take(at: 102)
        signal.receive(newer, eventID: 101)
        XCTAssertFalse(signal.pending)
        signal.receive(newer, eventID: 202)
        XCTAssertFalse(signal.pending)
        XCTAssertEqual(wakeups, 2)
    }

    func testResyncIsDedupedPerConnectionAndNeverPaintsAPrice() {
        let handle = Handle()
        var resyncs = 0
        let controller = LiveStreamController(open: { handle }, now: { 100 },
            onFrame: { _ in XCTFail("Recovery is not a price") }, onDeliveringChange: { _ in },
            onResync: { resyncs += 1 })
        controller.start()
        handle.fire("resync", #"{"generation":1}"#)
        handle.fire("resync", #"{"generation":1}"#)
        handle.fire("resync", #"{"generation":2}"#)
        XCTAssertEqual(resyncs, 2)
        handle.fire("open", "")
        handle.fire("resync", #"{"generation":1}"#)
        XCTAssertEqual(resyncs, 3)
        controller.stop()
    }

    func testRevisionAndObservationClocksCannotRegressTogether() throws {
        let held = try Self.game(revision: 8)
        XCTAssertFalse(WatchSelectedGameStore.canAdopt(try Self.game(revision: 7), replacing: held))
        XCTAssertFalse(WatchSelectedGameStore.canAdopt(try Self.game(revision: 9,
            scoreClock: "2026-10-10T08:00:00Z"), replacing: held))
        // Removing a source can produce a newer fold with an older price observation.
        XCTAssertTrue(WatchSelectedGameStore.canAdopt(try Self.game(revision: 9,
            priceClock: "2026-10-10T08:00:00Z"), replacing: held))
        let final = try Self.game(revision: 8, status: "final")
        XCTAssertFalse(WatchSelectedGameStore.canAdopt(try Self.game(revision: 9), replacing: final))
    }

    func testLiveSignalInterruptsQuietTickWaitAndReadsAuthoritativeDetail() async throws {
        let name = "watch-event-wakeup-\(UUID())"
        let defaults = try XCTUnwrap(UserDefaults(suiteName: name))
        defer { defaults.removePersistentDomain(forName: name) }
        var clock = 1_000.0
        let selected = WatchSelectedGameStore(transport: Detail(), defaults: defaults, retryClock: { clock })
        selected.select(eventID: 101)
        let handle = Handle()
        let quiet = expectation(description: "Quiet live wait uses controller tick")
        let refreshed = expectation(description: "Signal fetched detail before tick")
        var waits = 0
        let worker = Task {
            await selected.runLiveForegroundRefresh(open: { _ in handle }, clock: { clock }, sleep: { seconds in
                waits += 1
                if waits == 1 {
                    XCTAssertEqual(seconds, 5, accuracy: 0.001)
                    quiet.fulfill()
                } else if waits == 2 {
                    XCTAssertEqual(selected.successfulRefreshSequence, 2)
                    XCTAssertEqual(selected.game?.homeProbability, 0.61)
                    XCTAssertEqual(selected.game?.awayProbability, 0.29)
                    XCTAssertEqual(selected.game?.drawProbability, 0.10)
                    XCTAssertEqual(selected.game?.probabilitySource, "blend")
                    XCTAssertEqual(clock, 1_002, "No timer advance was needed for the frame")
                    refreshed.fulfill()
                } else { XCTFail("Unexpected extra wake") }
                try await Task.sleep(for: .seconds(60))
            })
        }
        defer { worker.cancel() }
        await fulfillment(of: [quiet], timeout: 2)
        clock = 1_002 // The existing two-second coalescing deadline has passed.
        handle.fire("probability", #"{"event_id":101,"p":0.99,"rev":{"101":2}}"#)
        await fulfillment(of: [refreshed], timeout: 2)
        worker.cancel()
        await worker.value
        XCTAssertEqual(waits, 2)
        XCTAssertEqual(handle.closes, 1)
    }

    func testRolloverBeforeDeliveringWakesForOneSecondReopenDeadline() async throws {
        let name = "watch-rollover-wakeup-\(UUID())"
        let defaults = try XCTUnwrap(UserDefaults(suiteName: name))
        defer { defaults.removePersistentDomain(forName: name) }
        var clock = 1_000.0
        let selected = WatchSelectedGameStore(transport: Detail(), defaults: defaults, retryClock: { clock })
        selected.select(eventID: 101)
        var handles: [Handle] = []
        let quiet = expectation(description: "Waiting before any open frame")
        let reopened = expectation(description: "Reopened at controller deadline")
        var waits = 0
        let worker = Task {
            await selected.runLiveForegroundRefresh(open: { _ in
                let handle = Handle(); handles.append(handle); return handle
            }, clock: { clock }, sleep: { seconds in
                waits += 1
                if waits == 1 {
                    XCTAssertEqual(seconds, 5, accuracy: 0.001)
                    quiet.fulfill()
                } else if waits == 2 {
                    XCTAssertEqual(seconds, 1, accuracy: 0.001)
                    clock += seconds
                    return
                } else if waits == 3 {
                    XCTAssertEqual(handles.count, 2)
                    XCTAssertEqual(clock, 1_001)
                    XCTAssertEqual(selected.successfulRefreshSequence, 1,
                                   "A control wake is not a detail invalidation")
                    reopened.fulfill()
                } else { XCTFail("Unexpected extra wake") }
                try await Task.sleep(for: .seconds(60))
            })
        }
        defer { worker.cancel() }
        await fulfillment(of: [quiet], timeout: 2)
        handles.first?.fire("reconnect", "") // delivering is already false.
        await fulfillment(of: [reopened], timeout: 2)
        worker.cancel()
        await worker.value
        XCTAssertTrue(handles.allSatisfy(\.isClosed))
    }

    func testSignalDuringCoalescingDoesNotEarnExtraWakeOrEarlyRead() async throws {
        let name = "watch-coalesce-wakeup-\(UUID())"
        let defaults = try XCTUnwrap(UserDefaults(suiteName: name))
        defer { defaults.removePersistentDomain(forName: name) }
        var clock = 1_000.0
        let selected = WatchSelectedGameStore(transport: Detail(), defaults: defaults, retryClock: { clock })
        selected.select(eventID: 101)
        let handle = Handle()
        var waits = 0
        await selected.runLiveForegroundRefresh(open: { _ in handle }, clock: { clock }, sleep: { seconds in
            waits += 1
            if waits == 1 {
                XCTAssertEqual(seconds, 5, accuracy: 0.001)
                handle.fire("probability", #"{"event_id":101,"p":0.99,"rev":{"101":2}}"#)
            } else if waits == 2 {
                XCTAssertEqual(seconds, 2, accuracy: 0.001)
                XCTAssertEqual(selected.successfulRefreshSequence, 1)
                // These arrive while the two-second wait is pending. Neither
                // duplicates nor newer frames bypass its single deadline.
                handle.fire("probability", #"{"event_id":101,"p":0.99,"rev":{"101":2}}"#)
                handle.fire("probability", #"{"event_id":101,"p":0.98,"rev":{"101":3}}"#)
                clock += seconds
            } else {
                XCTAssertEqual(waits, 3)
                XCTAssertEqual(selected.successfulRefreshSequence, 2)
                XCTAssertEqual(clock, 1_002)
                throw CancellationError()
            }
        })
        XCTAssertEqual(waits, 3)
    }

    func testWakeupFencesLateTimerAndCancelsRegisteredWait() async throws {
        let wakeup = WatchForegroundWakeup()
        let firstStarted = expectation(description: "First timer suspended")
        let secondStarted = expectation(description: "Second timer suspended")
        let oldTimerReturned = expectation(description: "Canceled old timer returned late")
        var oldTimer: CheckedContinuation<Void, Never>?
        let first = Task {
            try await wakeup.wait(seconds: 300) { _ in
                await withCheckedContinuation { continuation in
                    oldTimer = continuation
                    firstStarted.fulfill()
                }
                oldTimerReturned.fulfill()
            }
        }
        await fulfillment(of: [firstStarted], timeout: 2)
        wakeup.signal()
        try await first.value
        var secondFinished = false
        let second = Task {
            defer { secondFinished = true }
            try await wakeup.wait(seconds: 300) { _ in
                secondStarted.fulfill()
                try await Task.sleep(for: .seconds(300))
            }
        }
        defer { second.cancel() }
        await fulfillment(of: [secondStarted], timeout: 2)
        oldTimer?.resume(); oldTimer = nil
        await fulfillment(of: [oldTimerReturned], timeout: 2)
        XCTAssertFalse(secondFinished, "A stale timer must not complete the next wait")
        second.cancel()
        do { try await second.value; XCTFail("Cancellation must leave the wait") }
        catch is CancellationError { }
        catch { XCTFail("Unexpected error: \(error)") }
        XCTAssertTrue(secondFinished)
        // A canceled wait leaves no registered continuation behind.
        try await wakeup.wait(seconds: 1) { _ in }
    }

    func testAlreadyCancelledWaitDoesNotRegisterTimer() async {
        let wakeup = WatchForegroundWakeup()
        let worker = Task { @MainActor in
            // Test cancellation before entry without depending on scheduling.
            withUnsafeCurrentTask { $0?.cancel() }
            do {
                try await wakeup.wait(seconds: 300) { _ in XCTFail("Canceled owner cannot start a timer") }
                XCTFail("Canceled owner cannot complete normally")
            } catch is CancellationError { }
            catch { XCTFail("Unexpected error: \(error)") }
        }
        await worker.value
    }

    private actor BusyAfterFirstDetail: WatchSelectedGameTransport {
        var calls = 0
        func fetch(eventID: Int) async throws -> WatchSelectedGame {
            calls += 1
            if calls == 2 { throw WatchSelectedGameRequestError.retryAfter(120) }
            return try WatchForegroundUpdatesTests.game(revision: calls)
        }
    }

    func testStoppedStreamSleepsToServerDeadlineAndCannotBypassBackoff() async throws {
        let name = "watch-stream-busy-wakeup-\(UUID())"
        let defaults = try XCTUnwrap(UserDefaults(suiteName: name))
        defer { defaults.removePersistentDomain(forName: name) }
        var clock = 1_000.0
        let transport = BusyAfterFirstDetail()
        let selected = WatchSelectedGameStore(transport: transport, defaults: defaults, retryClock: { clock })
        selected.select(eventID: 101)
        let handle = Handle()
        var waits = 0
        await selected.runLiveForegroundRefresh(open: { _ in handle }, clock: { clock }, sleep: { seconds in
            waits += 1
            switch waits {
            case 1:
                XCTAssertEqual(seconds, 5, accuracy: 0.001)
                clock = 1_002
                handle.fire("probability", #"{"event_id":101,"p":0.99,"rev":{"101":2}}"#)
            case 2:
                XCTAssertEqual(seconds, 3, accuracy: 0.001)
                XCTAssertEqual(selected.successfulRefreshSequence, 1)
                XCTAssertEqual(selected.foregroundInvalidationDelay, 120, accuracy: 0.001)
                handle.fire("closed", "")
            case 3:
                XCTAssertEqual(seconds, 120, accuracy: 0.001,
                               "A stopped stream has no five-second maintenance ticks")
                XCTAssertEqual(selected.successfulRefreshSequence, 1)
                handle.fire("probability", #"{"event_id":101,"p":0.99,"rev":{"101":3}}"#)
                clock += seconds
            default:
                XCTAssertEqual(waits, 4)
                XCTAssertEqual(selected.successfulRefreshSequence, 2)
                XCTAssertEqual(clock, 1_122)
                throw CancellationError()
            }
        })
        let calls = await transport.calls
        XCTAssertEqual(calls, 3)
        XCTAssertTrue(handle.isClosed)
    }

    /// Deliberately ignores task cancellation until released. This models a
    /// response racing visibility loss and makes the store's fence observable.
    private actor HeldDetail: WatchSelectedGameTransport {
        private var waiter: CheckedContinuation<WatchSelectedGame, Error>?
        private let onHeld: @MainActor @Sendable () -> Void
        var calls = 0
        var active = 0
        var maxActive = 0
        init(onHeld: @escaping @MainActor @Sendable () -> Void) { self.onHeld = onHeld }
        func fetch(eventID: Int) async throws -> WatchSelectedGame {
            calls += 1
            active += 1
            maxActive = max(maxActive, active)
            defer { active -= 1 }
            if calls == 2 {
                let notify = onHeld
                return try await withCheckedThrowingContinuation { continuation in
                    waiter = continuation
                    Task { @MainActor in notify() }
                }
            }
            return try WatchForegroundUpdatesTests.game(revision: calls, home: calls == 1 ? 0.50 : 0.70)
        }
        func release() throws {
            let result = try WatchForegroundUpdatesTests.game(revision: 2, home: 0.61)
            waiter?.resume(returning: result)
            waiter = nil
        }
    }

    func testActualLoopRetainsOneSerialFollowupForFramesDuringDetailFetch() async throws {
        let name = "watch-inflight-followup-\(UUID())"
        let defaults = try XCTUnwrap(UserDefaults(suiteName: name))
        defer { defaults.removePersistentDomain(forName: name) }
        let held = expectation(description: "Second detail held in flight")
        let transport = HeldDetail(onHeld: { held.fulfill() })
        var clock = 1_000.0
        let selected = WatchSelectedGameStore(transport: transport, defaults: defaults, retryClock: { clock })
        selected.select(eventID: 101)
        let handle = Handle()
        let quiet = expectation(description: "Initial detail adopted and stream waiting")
        let followed = expectation(description: "Exactly one follow-up adopted")
        var waits = 0
        let worker = Task {
            await selected.runLiveForegroundRefresh(open: { _ in handle }, clock: { clock }, sleep: { _ in
                waits += 1
                if waits == 1 { quiet.fulfill() }
                else if waits == 2 {
                    XCTAssertEqual(selected.successfulRefreshSequence, 3)
                    XCTAssertEqual(selected.game?.homeProbability, 0.70)
                    XCTAssertEqual(selected.game?.probabilitySource, "blend")
                    followed.fulfill()
                } else { XCTFail("Unexpected extra read or wait") }
                try await Task.sleep(for: .seconds(60))
            })
        }
        defer { worker.cancel() }
        await fulfillment(of: [quiet], timeout: 2)
        clock = 1_002
        handle.fire("probability", #"{"event_id":101,"p":0.99,"rev":{"101":2}}"#)
        await fulfillment(of: [held], timeout: 2)
        XCTAssertTrue(selected.isRefreshing)
        XCTAssertEqual(selected.game?.homeProbability, 0.50)
        clock = 1_004
        handle.fire("probability", #"{"event_id":101,"p":0.98,"rev":{"101":3}}"#)
        handle.fire("probability", #"{"event_id":101,"p":0.98,"rev":{"101":3}}"#)
        handle.fire("probability", #"{"event_id":101,"p":0.97,"rev":{"101":4}}"#)
        try await transport.release()
        await fulfillment(of: [followed], timeout: 2)
        worker.cancel()
        await worker.value
        let calls = await transport.calls
        let maxActive = await transport.maxActive
        XCTAssertEqual(calls, 3, "Burst during a fetch earns one authoritative follow-up")
        XCTAssertEqual(maxActive, 1, "Detail requests never overlap")
        XCTAssertEqual(handle.closes, 1)
    }

    func testCancellingVisibleOwnerDiscardsLateDetailAndPendingFollowup() async throws {
        let name = "watch-inflight-cancel-\(UUID())"
        let defaults = try XCTUnwrap(UserDefaults(suiteName: name))
        defer { defaults.removePersistentDomain(forName: name) }
        let held = expectation(description: "Detail held across owner cancellation")
        let transport = HeldDetail(onHeld: { held.fulfill() })
        var clock = 1_000.0
        var publications = 0
        let selected = WatchSelectedGameStore(transport: transport, defaults: defaults,
            retryClock: { clock }, publish: { _, _ in publications += 1 })
        selected.select(eventID: 101)
        let handle = Handle()
        let quiet = expectation(description: "Waiting after initial reading")
        let worker = Task {
            await selected.runLiveForegroundRefresh(open: { _ in handle }, clock: { clock }, sleep: { _ in
                quiet.fulfill()
                try await Task.sleep(for: .seconds(60))
            })
        }
        defer { worker.cancel() }
        await fulfillment(of: [quiet], timeout: 2)
        let initialPublications = publications
        let initialReceived = selected.fetchedAt
        let initialObserved = selected.game?.probabilityObservedAt
        clock = 1_002
        handle.fire("probability", #"{"event_id":101,"p":0.99,"rev":{"101":2}}"#)
        await fulfillment(of: [held], timeout: 2)
        clock = 1_004
        handle.fire("probability", #"{"event_id":101,"p":0.98,"rev":{"101":3}}"#)
        // Same stop + structured-task cancellation performed on view departure.
        selected.stopLiveForegroundUpdates()
        worker.cancel()
        XCTAssertTrue(handle.isClosed)
        try await transport.release()
        await worker.value
        let calls = await transport.calls
        XCTAssertEqual(calls, 2, "Cancellation discards the queued follow-up")
        XCTAssertEqual(selected.successfulRefreshSequence, 1)
        XCTAssertEqual(selected.game?.homeProbability, 0.50)
        XCTAssertEqual(selected.fetchedAt, initialReceived)
        XCTAssertEqual(selected.game?.probabilityObservedAt, initialObserved)
        XCTAssertEqual(publications, initialPublications, "Late response cannot publish a complication update")
        XCTAssertFalse(selected.isRefreshing)
        XCTAssertNil(selected.activeForegroundStream)
    }
}
