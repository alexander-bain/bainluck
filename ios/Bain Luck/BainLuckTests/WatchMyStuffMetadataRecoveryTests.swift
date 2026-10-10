#if os(iOS)
import XCTest
@testable import Bain_Luck

final class WatchMyStuffMetadataRecoveryTests: XCTestCase {
    @MainActor func testExplicitSyncRetriesMetadataAfterOfflineFailureWithUnchangedPinIDs() async throws {
        try await verifyRecovery(from: .failed)
    }

    @MainActor func testExplicitSyncClearsNoLongerListedAfterExactIDRecovers() async throws {
        try await verifyRecovery(from: .unavailable)
    }

    @MainActor private func verifyRecovery(from initial: PinMetadata) async throws {
        let name = "watch-metadata-recovery-\(UUID())"
        let defaults = try XCTUnwrap(UserDefaults(suiteName: name))
        defer { defaults.removePersistentDomain(forName: name) }
        let identity = PinAccountBinding(userID: "same-account", authenticated: true)
        let pins = PinManager(defaults: defaults, initialBinding: identity,
            serverLoad: { PinsResponse(events: [101], futures: []) })
        await pins.loadPins()
        var calls = 0
        let publisher = WatchMyStuffPublisher(fetchPreferences: {
            throw URLError(.notConnectedToInternet)
        }, lookupPin: { pin in
            XCTAssertEqual(pin, SavedPin(type: "event", value: 101))
            calls += 1
            return calls == 1 ? initial : .available(title: "Recovered away at home")
        })
        let first = expectation(description: "Initial metadata result published")
        let recovered = expectation(description: "Explicit sync retries the same saved identity")
        var observedFirst = false
        var observedRecovery = false
        publisher.publish = { bytes in
            guard let snapshot = WatchMyStuffSnapshot.decode(bytes, now: Date()),
                  let row = snapshot.pins.items.first, calls > 0 else { return }
            if !observedFirst, initial != .unavailable || row.unavailable {
                observedFirst = true
                first.fulfill()
            }
            if row.title == "Recovered away at home", !row.unavailable, !observedRecovery {
                observedRecovery = true
                recovered.fulfill()
            }
        }
        publisher.bind(identity, pins: pins)
        await fulfillment(of: [first], timeout: 2)
        XCTAssertEqual(calls, 1)
        XCTAssertEqual(publisher.snapshot?.pins.items.first?.unavailable, initial == .unavailable)
        publisher.refresh() // The real phone-side handler for Watch's Sync action.
        await fulfillment(of: [recovered], timeout: 2)
        XCTAssertEqual(calls, 2, "Ordinary pin notifications must not duplicate an explicit metadata retry")
        XCTAssertEqual(publisher.snapshot?.pins.items.map(\.targetID), [101])
        XCTAssertEqual(publisher.snapshot?.pins.items.first?.title, "Recovered away at home")
        XCTAssertEqual(publisher.snapshot?.pins.items.first?.unavailable, false)
    }
}
#endif
