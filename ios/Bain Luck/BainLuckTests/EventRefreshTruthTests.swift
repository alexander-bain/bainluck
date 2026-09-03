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

    // MARK: - refreshIndicator: live push is the third state
    //
    // #2687 stands the 30-second poll DOWN while the stream delivers, so
    // `lastLoadedAt` stops advancing and `refreshRemaining` walks to 0 and stays
    // there. Measured on the simulator against a live US Open match: a full
    // green ring reading "0" for the whole match, on a page whose number was
    // being pushed every ~40 seconds. Same C43 defect — chrome describing work
    // that is not scheduled — arriving from the push side.

    private func indicator(
        status: String? = "live",
        streaming: Bool = false,
        lastLoadedAt: Date?
    ) -> EventDetailView.RefreshIndicator {
        EventDetailView.refreshIndicator(
            status: status, streamDelivering: streaming,
            lastLoadedAt: lastLoadedAt, interval: 30, now: now)
    }

    func testDeliveringStreamSaysSoInsteadOfCountingDown() {
        XCTAssertEqual(indicator(streaming: true, lastLoadedAt: now), .streaming)
    }

    func testTheFreezeItself() {
        // The exact state photographed: streaming, and the last load is long
        // enough ago that the countdown has bottomed out.
        let stale = now.addingTimeInterval(-600)
        XCTAssertEqual(
            indicator(streaming: false, lastLoadedAt: stale), .countdown(0),
            "control: with no stream this really is a poll that is overdue")
        XCTAssertEqual(
            indicator(streaming: true, lastLoadedAt: stale), .streaming,
            "with the stream delivering, `0` is not a countdown — it is the poll "
            + "having been stood down, and the page must not print a number that "
            + "will never change")
    }

    func testAStreamConnectingMidCycleStillWins() {
        // Ordering guard: checking "is the countdown zero" first would let a
        // stream that connected 10s into a cycle keep counting down to a poll
        // that has already been cancelled.
        let recent = now.addingTimeInterval(-10)
        XCTAssertEqual(indicator(streaming: false, lastLoadedAt: recent), .countdown(20))
        XCTAssertEqual(indicator(streaming: true, lastLoadedAt: recent), .streaming)
    }

    func testStreamOnANonLivePageStillShowsNothing() {
        // `streamDelivering` cannot resurrect chrome on a page that has no
        // refresh at all; the VM never opens a stream off `live`, and if that
        // ever changed the indicator must not be what discovers it.
        for status in ["scheduled", "completed", "closed"] {
            XCTAssertEqual(
                indicator(status: status, streaming: true, lastLoadedAt: now), .hidden,
                "status \(status)")
        }
        XCTAssertEqual(indicator(status: nil, streaming: true, lastLoadedAt: now), .hidden)
    }

    func testNotStreamingKeepsEveryPriorCountdownAnswer() {
        // The C43 behaviour is unchanged when no stream is delivering.
        XCTAssertEqual(indicator(lastLoadedAt: nil), .countdown(30))
        XCTAssertEqual(indicator(lastLoadedAt: now), .countdown(30))
        XCTAssertEqual(indicator(lastLoadedAt: now.addingTimeInterval(-5.5)), .countdown(25))
        XCTAssertEqual(indicator(lastLoadedAt: now.addingTimeInterval(-45)), .countdown(0))
    }
}
