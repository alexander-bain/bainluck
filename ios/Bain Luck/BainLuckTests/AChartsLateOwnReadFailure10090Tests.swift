import XCTest
@testable import Bain_Luck

/// #10090 — a fresh event page mounts its chart before the page's own history
/// read lands, so the chart starts its own read. The page then hands the chart
/// its payload (`adopt`). If the chart's own read fails AFTER that, the chart
/// printed "couldn't load" over data it already had: the view reads `error`
/// before `history`. Seen on the hosted 390-wide page in
/// `SubsecondHeldDelivery10090Tests` (hero 56%, chart "We couldn't load that
/// just now.").
@MainActor
final class AChartsLateOwnReadFailure10090Tests: XCTestCase {

    struct Offline: Error {}

    /// Holds the chart's own read open until the test lets it fail.
    private final class Gate: @unchecked Sendable {
        private let lock = NSLock()
        private var waiter: CheckedContinuation<Void, Never>?
        private var opened = false
        private var entered = false

        /// Whether the chart's own read has actually started. `loading` can't
        /// say: it is already `true` before `load()` runs.
        var started: Bool { lock.lock(); defer { lock.unlock() }; return entered }

        func wait() async {
            await withCheckedContinuation { c in
                lock.lock()
                entered = true
                if opened { lock.unlock(); c.resume() } else { waiter = c; lock.unlock() }
            }
        }

        func open() {
            lock.lock(); opened = true; let c = waiter; waiter = nil; lock.unlock()
            c?.resume()
        }
    }

    private func history() throws -> EventHistoryResponse {
        let decoder = JSONDecoder()
        decoder.keyDecodingStrategy = .convertFromSnakeCase
        return try decoder.decode(EventHistoryResponse.self, from: Data("""
        {"event_id":4242,"home_team":"Celtics","away_team":"Knicks","status":"live",
         "history":[{"timestamp":"2026-09-25T17:00:00Z","home_probability":0.58},
                    {"timestamp":"2026-09-25T17:10:00Z","home_probability":0.60}],
         "aggregate_line":[{"timestamp":"2026-09-25T17:00:00Z","home_probability":0.58},
                           {"timestamp":"2026-09-25T17:10:00Z","home_probability":0.60}]}
        """.utf8))
    }

    private func failingModel(after gate: Gate) -> OddsChartViewModel {
        OddsChartViewModel(eventId: 4242, fetchHistory: { _ in
            await gate.wait()
            throw Offline()
        })
    }

    private func waitUntil(_ done: () -> Bool) async {
        let deadline = Date().addingTimeInterval(2)
        while !done(), Date() < deadline { try? await Task.sleep(nanoseconds: 5_000_000) }
    }

    func testTheChartsOwnReadFailingAfterThePageHandedItHistoryLeavesTheChartDrawn() async throws {
        let gate = Gate()
        let vm = failingModel(after: gate)
        let read = Task { await vm.load() }
        await waitUntil { gate.started }
        XCTAssertTrue(gate.started, "the chart's own read is in flight")

        let payload = try history()
        XCTAssertTrue(vm.adopt(payload), "the page hands the chart its history mid-read")
        gate.open()
        await read.value

        XCTAssertNil(vm.error, "a late failure of the chart's own read must not cover adopted data")
        XCTAssertEqual(vm.history, payload)
        XCTAssertFalse(vm.loading)
    }

    /// Control: with nothing adopted, a failed read still says so.
    func testTheChartsOwnReadFailingWithNothingAdoptedStillReportsTheFailure() async throws {
        let gate = Gate()
        gate.open()
        let vm = failingModel(after: gate)
        await vm.load()
        XCTAssertNotNil(vm.error)
        XCTAssertNil(vm.history)
        XCTAssertFalse(vm.loading)
    }

    /// The other order already worked: a failure first, then the page's payload.
    func testThePagesHistoryAfterAFailedReadClearsTheFailure() async throws {
        let gate = Gate()
        gate.open()
        let vm = failingModel(after: gate)
        await vm.load()
        XCTAssertNotNil(vm.error)
        XCTAssertTrue(vm.adopt(try history()))
        XCTAssertNil(vm.error)
    }
}
