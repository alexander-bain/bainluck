//
//  APinTapAlwaysSaysWhatHappened9495Tests.swift
//  BainLuckTests
//
//  #9495 — on installed build 31 a reader pressed the pin on a game page
//  several times and saw nothing, and could not tell whether it saved.
//  Two silent paths were proven from source:
//
//  1. At 6 pinned games `PinButton` was `.disabled`, so the tap never reached
//     `togglePin` and its "limit reached" toast could not fire.
//  2. Signed in, "Pinned to My Stuff" was shown before the server save ran;
//     a failed save only logged, so the reader saw success for a pin their
//     account did not hold.
//
//  These tests drive the real `PinManager` with an injected server save.
//

import XCTest
@testable import Bain_Luck

@MainActor
final class APinTapAlwaysSaysWhatHappened9495Tests: XCTestCase {

    private struct SaveFailed: Error {}

    private var suiteName = ""
    private var defaults: UserDefaults!

    override func setUp() {
        super.setUp()
        suiteName = "APinTapAlwaysSaysWhatHappened9495Tests.\(UUID().uuidString)"
        defaults = UserDefaults(suiteName: suiteName)
    }

    override func tearDown() {
        defaults.removePersistentDomain(forName: suiteName)
        defaults = nil
        super.tearDown()
    }

    private func storedEventPins() -> Set<Int> {
        guard let data = defaults.data(forKey: "bainluck_pinnedEvents"),
              let ids = try? JSONDecoder().decode([Int].self, from: data) else { return [] }
        return Set(ids)
    }

    // MARK: - 1. The limit explains itself

    func testASeventhGameAtTheLimitIsRefusedOutLoud() {
        var serverCalls = 0
        let manager = PinManager(defaults: defaults) { _, _, _ in serverCalls += 1 }
        for id in 1...PinManager.maxPinsPerType {
            manager.togglePin(type: "event", id: id)
        }
        XCTAssertFalse(manager.canPin(type: "event"))

        let task = manager.togglePin(type: "event", id: 99)

        XCTAssertNil(task, "no server save starts for a refused pin")
        XCTAssertFalse(manager.isPinned(type: "event", id: 99))
        XCTAssertEqual(manager.pinnedEventIDs.count, PinManager.maxPinsPerType)
        XCTAssertEqual(serverCalls, 0)
        let feedback = manager.feedback
        XCTAssertEqual(feedback?.message, "You already have 6 pinned games. Unpin one in My Stuff.")
        XCTAssertEqual(feedback?.isWarning, true)
    }

    /// The limit toast only exists if the tap reaches `togglePin`. The build-31
    /// defect was the modifier itself, so the guard is on the modifier.
    func testThePinButtonNeverSwallowsTheTap() throws {
        let source = try String(
            contentsOf: URL(fileURLWithPath: #filePath)
                .deletingLastPathComponent()
                .deletingLastPathComponent()
                .appendingPathComponent("Bain Luck/Components/PinButton.swift"),
            encoding: .utf8
        )
        XCTAssertTrue(source.contains("pinManager.togglePin(type: type, id: id)"))
        XCTAssertFalse(source.contains(".disabled("), "a disabled pin button ignores taps silently")
        XCTAssertFalse(source.contains("canPin("), "the button must not pre-judge the limit; togglePin explains it")
    }

    // MARK: - 2. Signed in, success waits for the server

    func testSignedInSuccessIsShownOnlyAfterTheServerConfirms() async {
        var release: CheckedContinuation<Void, Never>?
        var calls: [(String, Int, Bool)] = []
        let manager = PinManager(defaults: defaults) { type, id, pinned in
            calls.append((type, id, pinned))
            await withCheckedContinuation { release = $0 }
        }
        manager.setAuthenticated(true)

        let task = manager.togglePin(type: "event", id: 15319563)
        XCTAssertNotNil(task)
        await Task.yield()

        XCTAssertTrue(manager.isSaving(type: "event", id: 15319563))
        XCTAssertEqual(manager.feedback?.isPending, true)
        XCTAssertNotEqual(manager.feedback?.message, "Pinned to My Stuff")

        // A second tap while the save is in flight is answered, not queued.
        XCTAssertNil(manager.togglePin(type: "event", id: 15319563))
        XCTAssertEqual(manager.feedback?.message, "Still saving…")
        XCTAssertTrue(manager.isPinned(type: "event", id: 15319563))

        while release == nil { await Task.yield() }
        release?.resume()
        await task?.value

        XCTAssertEqual(calls.count, 1)
        XCTAssertEqual(calls.first?.2, true)
        XCTAssertFalse(manager.isSaving(type: "event", id: 15319563))
        XCTAssertEqual(manager.feedback?.message, "Pinned to My Stuff")
        XCTAssertEqual(manager.feedback?.isPending, false)
        XCTAssertTrue(manager.isPinned(type: "event", id: 15319563))
    }

    func testAFailedServerSaveIsShownAndTheLocalPinIsUndone() async {
        let manager = PinManager(defaults: defaults) { _, _, _ in throw SaveFailed() }
        manager.setAuthenticated(true)

        await manager.togglePin(type: "event", id: 42)?.value

        XCTAssertNotEqual(manager.feedback?.message, "Pinned to My Stuff")
        XCTAssertEqual(manager.feedback?.message, "Couldn't save pin. Try again.")
        XCTAssertEqual(manager.feedback?.isWarning, true)
        XCTAssertFalse(manager.isPinned(type: "event", id: 42), "local state must match the account")
        XCTAssertFalse(storedEventPins().contains(42), "the undone pin must not survive a relaunch")
        XCTAssertFalse(manager.isSaving(type: "event", id: 42))
    }

    func testAFailedServerRemoveIsShownAndThePinIsRestored() async {
        var failNext = false
        let manager = PinManager(defaults: defaults) { _, _, _ in
            if failNext { throw SaveFailed() }
        }
        manager.setAuthenticated(true)
        await manager.togglePin(type: "event", id: 7)?.value
        XCTAssertTrue(manager.isPinned(type: "event", id: 7))

        failNext = true
        await manager.togglePin(type: "event", id: 7)?.value

        XCTAssertEqual(manager.feedback?.message, "Couldn't remove pin. Try again.")
        XCTAssertTrue(manager.isPinned(type: "event", id: 7))
        XCTAssertTrue(storedEventPins().contains(7))
    }

    // MARK: - 3. Signed out, the device is the store

    func testSignedOutPinConfirmsFromTheLocalSaveWithoutTheServer() {
        var serverCalls = 0
        let manager = PinManager(defaults: defaults) { _, _, _ in serverCalls += 1 }

        XCTAssertNil(manager.togglePin(type: "event", id: 5))
        XCTAssertEqual(manager.feedback?.message, "Pinned to My Stuff")
        XCTAssertTrue(storedEventPins().contains(5))

        XCTAssertNil(manager.togglePin(type: "event", id: 5))
        XCTAssertEqual(manager.feedback?.message, "Removed from My Stuff")
        XCTAssertFalse(storedEventPins().contains(5))
        XCTAssertEqual(serverCalls, 0)
    }

    // MARK: - 4. The answer is readable where it lands

    /// The simulator LOOK on the game page found the toast drawn over the
    /// iPhone tab bar's labels at 22pt from the bottom safe area.
    func testTheToastClearsTheIPhoneTabBar() {
        XCTAssertGreaterThanOrEqual(PinFeedbackToast.bottomClearance(horizontalSizeClass: .compact), 70)
        XCTAssertGreaterThanOrEqual(PinFeedbackToast.bottomClearance(horizontalSizeClass: nil), 70)
    }

    func testAWarningStaysUpLongerThanAConfirmationAndAPendingSaveWaitsForItsOutcome() {
        let pending = PinActionFeedback(message: "Saving…", systemImage: "bookmark", isWarning: false, isPending: true)
        let done = PinActionFeedback(message: "Pinned to My Stuff", systemImage: "bookmark.fill", isWarning: false)
        let warning = PinActionFeedback(message: PinManager.limitMessage(type: "event"), systemImage: "exclamationmark.triangle.fill", isWarning: true)
        XCTAssertNil(PinFeedbackToast.displaySeconds(for: pending))
        XCTAssertGreaterThanOrEqual(PinFeedbackToast.displaySeconds(for: done) ?? 0, 2.5)
        XCTAssertGreaterThan(PinFeedbackToast.displaySeconds(for: warning) ?? 0, PinFeedbackToast.displaySeconds(for: done) ?? 0)
    }
}
