import XCTest
@testable import Bain_Luck

/// #10876 — the pin tip's read of the REAL `PinManager`. The pure rule is in
/// `ContextualTips10876Tests`; this proves the adapter feeds it the store's
/// own answers, the limit included, so `PinButton` never has to read it.
@MainActor
final class ContextualTipsPinStore10876Tests: XCTestCase {

    private var suiteName = ""
    private var defaults: UserDefaults!

    override func setUp() {
        super.setUp()
        suiteName = "ContextualTipsPinStore10876Tests.\(UUID().uuidString)"
        defaults = UserDefaults(suiteName: suiteName)
    }

    override func tearDown() {
        defaults.removePersistentDomain(forName: suiteName)
        defaults = nil
        super.tearDown()
    }

    private func tip(_ manager: PinManager, id: Int) -> PinTipState10876 {
        ContextualTipEligibility10876.pinTip(isDetailAnchor: true, localPinUIShowing: false) {
            manager.pinTipReading10876(type: "event", id: id)
        }
    }

    func testAFreshStoreIsTaughtAndNothingIsLearned() {
        let manager = PinManager(defaults: defaults) { _, _, _ in }
        XCTAssertEqual(tip(manager, id: 99), PinTipState10876(usable: true, learned: false))
    }

    func testAtTheLimitTheTipIsNotTaughtBecauseTheTapWouldRefuse() {
        let manager = PinManager(defaults: defaults) { _, _, _ in }
        for id in 1...PinManager.maxPinsPerType {
            manager.togglePin(type: "event", id: id)
        }
        manager.feedback = nil
        let reading = manager.pinTipReading10876(type: "event", id: 99)
        XCTAssertFalse(reading.canPin, "the reading lost the store's limit")
        XCTAssertEqual(reading.savedPinCount, PinManager.maxPinsPerType)
        XCTAssertEqual(tip(manager, id: 99), PinTipState10876(usable: false, learned: true))
    }

    func testAPinnedSubjectAndAPinMessageAreRead() {
        let manager = PinManager(defaults: defaults) { _, _, _ in }
        manager.togglePin(type: "event", id: 7)
        let reading = manager.pinTipReading10876(type: "event", id: 7)
        XCTAssertTrue(reading.isPinned)
        XCTAssertTrue(reading.hasPinMessage, "the \"Pinned\" toast is a pin message on screen")
        XCTAssertEqual(reading.loadState, manager.loadState)
        XCTAssertFalse(tip(manager, id: 7).usable)
    }
}
