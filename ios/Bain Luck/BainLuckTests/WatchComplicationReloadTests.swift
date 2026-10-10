import Foundation
import XCTest
@testable import Bain_Luck

@MainActor final class WatchComplicationReloadTests: XCTestCase {
    func testBurstKeepsOneTrailingReloadAtOriginalDeadline() async {
        var clock = 1_000.0
        var reloads = 0
        var timer: CheckedContinuation<Void, Never>?
        let scheduled = expectation(description: "One trailing reload scheduled")
        let completed = expectation(description: "Latest snapshot reload requested")
        let gate = WatchComplicationReloads(now: { clock }, sleep: { delay in
            XCTAssertEqual(delay, 28, accuracy: 0.001)
            await withCheckedContinuation { continuation in
                timer = continuation; scheduled.fulfill()
            }
        }, reload: {
            reloads += 1
            if reloads == 2 { completed.fulfill() }
        })
        gate.changed(key: "101:forecast", live: true)
        XCTAssertEqual(reloads, 1)
        clock = 1_002
        gate.changed(key: "101:forecast", live: true)
        await fulfillment(of: [scheduled], timeout: 2)
        clock = 1_015
        gate.changed(key: "101:forecast", live: true)
        gate.changed(key: "101:forecast", live: true)
        XCTAssertEqual(reloads, 1)
        clock = 1_030
        timer?.resume(); timer = nil
        await fulfillment(of: [completed], timeout: 2)
        XCTAssertEqual(reloads, 2, "No new data is needed to flush the final burst")
        clock = 1_060
        gate.changed(key: "101:forecast", live: true)
        XCTAssertEqual(reloads, 3, "An elapsed interval does not add another wait")
    }

    func testClearAndSelectionChangeCancelOldTrailingReload() async {
        var clock = 1_000.0
        var reloads = 0
        var timer: CheckedContinuation<Void, Never>?
        let scheduled = expectation(description: "Trailing reload suspended")
        let returned = expectation(description: "Old timer returns despite cancellation")
        let gate = WatchComplicationReloads(now: { clock }, sleep: { _ in
            await withCheckedContinuation { continuation in
                timer = continuation; scheduled.fulfill()
            }
            returned.fulfill()
        }, reload: { reloads += 1 })
        gate.changed(key: "101:forecast", live: true)
        clock += 2
        gate.changed(key: "101:forecast", live: true)
        await fulfillment(of: [scheduled], timeout: 2)
        gate.changed(key: nil, live: false)
        XCTAssertEqual(reloads, 2, "Clearing must immediately invalidate the old reading")
        gate.changed(key: "202:forecast", live: true)
        XCTAssertEqual(reloads, 3, "A new selection must not wait for the old event")
        timer?.resume(); timer = nil
        await fulfillment(of: [returned], timeout: 2)
        XCTAssertEqual(reloads, 3, "Canceled timer cannot request an extra old-event reload")
    }

    func testFinalScoreFallbackAndNonLiveChangesReloadImmediately() {
        var reloads = 0
        let gate = WatchComplicationReloads(now: { 1_000 }, sleep: { _ in
            XCTFail("Urgent identity/lifecycle changes do not wait")
        }, reload: { reloads += 1 })
        gate.changed(key: "101:forecast", live: true)
        gate.changed(key: "101:score", live: true)
        gate.changed(key: "101:final", live: false)
        gate.changed(key: "101:final", live: false)
        gate.changed(key: nil, live: false)
        XCTAssertEqual(reloads, 5)
    }
}
