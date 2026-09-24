import XCTest
@testable import Bain_Luck

/// L2-196 / C43 — the event page's refresh chrome must be truthful: it may only
/// appear when the page actually refreshes. Only live events poll (the VM
/// installs a request timer for `status == "live"` only), so scheduled/completed
/// pages previously cycled a countdown that no request performed.
///
/// #2687 added the stream state (a delivering stream stands the poll down, and a
/// countdown to it froze at 0). #8320 then took the countdown out of the
/// reader's view entirely: what remains is hidden / polling / streaming. These
/// pin the pure helpers on `EventDetailView`; the one-status-per-page layout is
/// pinned by `ALiveEventPageSaysItsFreshnessOnce8320Tests`.
final class EventRefreshTruthTests: XCTestCase {

    // MARK: - showsRefreshStatus: only live refreshes

    func testLiveShowsStatus() {
        XCTAssertTrue(EventDetailView.showsRefreshStatus(status: "live"))
    }

    func testScheduledDoesNotShowStatus() {
        // The C43 defect: scheduled pages have no reload request but cycled a ring.
        XCTAssertFalse(EventDetailView.showsRefreshStatus(status: "scheduled"))
    }

    func testCompletedDoesNotShowStatus() {
        XCTAssertFalse(EventDetailView.showsRefreshStatus(status: "completed"))
    }

    func testClosedDoesNotShowStatus() {
        XCTAssertFalse(EventDetailView.showsRefreshStatus(status: "closed"))
    }

    func testNilStatusDoesNotShowStatus() {
        XCTAssertFalse(EventDetailView.showsRefreshStatus(status: nil))
    }

    // MARK: - refreshIndicator: three states, none of them a number

    /// `pushed` defaults to true so the cases below keep asking about the
    /// stream state alone; the #8320 cases set it explicitly.
    private func indicator(
        status: String? = "live",
        streaming: Bool,
        pushed: Bool = true
    ) -> EventDetailView.RefreshIndicator {
        EventDetailView.refreshIndicator(
            status: status, streamDelivering: streaming, pushedPrice: pushed)
    }

    func testDeliveringStreamSaysSo() {
        XCTAssertEqual(indicator(streaming: true), .streaming)
    }

    /// The fallback arm: reconnecting, or a stream that never delivered. The
    /// page is being polled, and the control says only that it can refresh —
    /// never a green dot, which would claim a push that is not arriving.
    func testNoStreamIsPollingNotStreaming() {
        XCTAssertEqual(indicator(streaming: false), .polling)
        XCTAssertNotEqual(indicator(streaming: false), .streaming)
    }

    /// #8320 — the stream reports delivering on `open`, before any price. A
    /// socket is not a price: until one has been pushed onto the page, the dot
    /// would be claiming a delivery that has not happened.
    func testAnOpenedStreamThatHasPushedNoPriceIsPolling() {
        XCTAssertEqual(indicator(streaming: true, pushed: false), .polling)
        XCTAssertEqual(indicator(streaming: false, pushed: false), .polling)
    }

    func testStreamOnANonLivePageStillShowsNothing() {
        // `streamDelivering` cannot resurrect chrome on a page that has no
        // refresh at all; the VM never opens a stream off `live`, and if that
        // ever changed the indicator must not be what discovers it.
        for status in ["scheduled", "completed", "closed"] {
            XCTAssertEqual(indicator(status: status, streaming: true), .hidden, "status \(status)")
            XCTAssertEqual(indicator(status: status, streaming: false), .hidden, "status \(status)")
        }
        XCTAssertEqual(indicator(status: nil, streaming: true), .hidden)
        XCTAssertEqual(indicator(status: "completed", streaming: true, pushed: false), .hidden)
    }
}
