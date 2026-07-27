import XCTest
@testable import Bain_Luck

/// L2-196 / C43 — the event page's refresh chrome must be truthful: a countdown may
/// only appear when an actual auto-refresh request is scheduled, and it must count
/// down from the LAST ACTUAL load, not a self-resetting timer that fakes a cycle.
/// Only live events poll (the VM installs a request timer for `status == "live"`
/// only), so scheduled/completed pages previously cycled a 120s countdown that no
/// request performed. These pin the pure helpers on `EventDetailView`.
///
/// `now` is injected for determinism (gotcha #44).
final class EventRefreshTruthTests: XCTestCase {

    private let now = ISO8601DateFormatter().date(from: "2026-07-27T12:00:00Z")!

    // MARK: - showsRefreshCountdown: only live schedules a request

    func testLiveShowsCountdown() {
        XCTAssertTrue(EventDetailView.showsRefreshCountdown(status: "live"))
    }

    func testScheduledDoesNotShowCountdown() {
        // The C43 defect: scheduled pages have no reload request but cycled a ring.
        XCTAssertFalse(EventDetailView.showsRefreshCountdown(status: "scheduled"))
    }

    func testCompletedDoesNotShowCountdown() {
        XCTAssertFalse(EventDetailView.showsRefreshCountdown(status: "completed"))
    }

    func testClosedDoesNotShowCountdown() {
        XCTAssertFalse(EventDetailView.showsRefreshCountdown(status: "closed"))
    }

    func testNilStatusDoesNotShowCountdown() {
        XCTAssertFalse(EventDetailView.showsRefreshCountdown(status: nil))
    }

    // MARK: - refreshRemaining: driven by real last-load, clamped, ceil'd

    func testNeverLoadedShowsFullInterval() {
        XCTAssertEqual(EventDetailView.refreshRemaining(lastLoadedAt: nil, interval: 30, now: now), 30)
    }

    func testJustLoadedShowsFullInterval() {
        XCTAssertEqual(EventDetailView.refreshRemaining(lastLoadedAt: now, interval: 30, now: now), 30)
    }

    func testMidCycleCountsDownFromLastLoad() {
        let loaded = now.addingTimeInterval(-10) // 10s ago
        XCTAssertEqual(EventDetailView.refreshRemaining(lastLoadedAt: loaded, interval: 30, now: now), 20)
    }

    func testCycleElapsedClampsToZero() {
        let loaded = now.addingTimeInterval(-30)
        XCTAssertEqual(EventDetailView.refreshRemaining(lastLoadedAt: loaded, interval: 30, now: now), 0)
    }

    func testOverdueClampsToZeroNeverNegative() {
        let loaded = now.addingTimeInterval(-45)
        XCTAssertEqual(EventDetailView.refreshRemaining(lastLoadedAt: loaded, interval: 30, now: now), 0)
    }

    func testFractionalRemainingRoundsUp() {
        let loaded = now.addingTimeInterval(-5.5) // 24.5s remaining
        XCTAssertEqual(EventDetailView.refreshRemaining(lastLoadedAt: loaded, interval: 30, now: now), 25)
    }
}
