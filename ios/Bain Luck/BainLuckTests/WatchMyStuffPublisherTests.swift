#if os(iOS)
import XCTest
@testable import Bain_Luck

final class WatchMyStuffPublisherTests: XCTestCase {
    @MainActor func testPinsAndRelationsPublishWithoutTelemetryOrTokenTransfer() async throws {
        let name = "watch-publisher-\(UUID())"
        let defaults = try XCTUnwrap(UserDefaults(suiteName: name))
        defer { defaults.removePersistentDomain(forName: name) }
        let identity = PinAccountBinding(userID: "private-account", authenticated: true)
        let pins = PinManager(defaults: defaults, initialBinding: identity,
            serverLoad: { PinsResponse(events: [101], futures: [202]) })
        await pins.loadPins()
        let prefs = PreferencesResponse(homeLocation: nil, sportAffinities: [:], onboardingCompleted: true,
            favorites: [FavoriteItem(teamId: 7, teamName: "Same name", relationType: "rival",
                sportKey: nil, logoUrl: nil, source: nil)])
        let publisher = WatchMyStuffPublisher(fetchPreferences: { prefs }, lookupPin: { pin in
            .available(title: pin.type == "event" ? "Away at Home" : "A full saved question?")
        })
        let ready = expectation(description: "Independent pin and team publication")
        ready.assertForOverFulfill = false
        var bytes = Data()
        publisher.publish = { data in
            bytes = data
            if let snapshot = WatchMyStuffSnapshot.decode(data, now: Date()),
               snapshot.pins.items.count == 2, snapshot.teams.state == .loaded { ready.fulfill() }
        }
        publisher.bind(identity, pins: pins)
        await fulfillment(of: [ready], timeout: 2)
        let value = try XCTUnwrap(WatchMyStuffSnapshot.decode(bytes, now: Date()))
        XCTAssertEqual(Set(value.pins.items.map(\.targetID)), [101, 202])
        XCTAssertEqual(value.teams.items.first?.relation, "rival")
        XCTAssertFalse(String(decoding: bytes, as: UTF8.self).contains("private-account"))
        let previousGeneration = value.generation
        publisher.bind(.init(userID: nil, authenticated: false), pins: pins)
        XCTAssertEqual(publisher.snapshot?.account, .signedOut)
        XCTAssertTrue(publisher.snapshot?.pins.items.isEmpty == true)
        XCTAssertTrue(publisher.snapshot?.teams.items.isEmpty == true)
        XCTAssertGreaterThan(publisher.snapshot?.generation ?? 0, previousGeneration)
    }

    @MainActor func testPendingFailedAndConfirmedRemovalAfterFailedListRead() async throws {
        let name = "watch-publisher-removal-\(UUID())"
        let defaults = try XCTUnwrap(UserDefaults(suiteName: name))
        defer { defaults.removePersistentDomain(forName: name) }
        var listFails = false
        var writeFails = true
        let identity = PinAccountBinding(userID: "account", authenticated: true)
        let pins = PinManager(defaults: defaults, initialBinding: identity, serverLoad: {
            if listFails { throw URLError(.notConnectedToInternet) }
            return PinsResponse(events: [101], futures: [])
        }, serverSync: { _, _, _ in
            if writeFails { throw URLError(.notConnectedToInternet) }
        })
        await pins.loadPins()
        let publisher = WatchMyStuffPublisher(fetchPreferences: { throw URLError(.notConnectedToInternet) },
                                               lookupPin: { _ in .failed })
        publisher.bind(identity, pins: pins)
        listFails = true
        await pins.loadPins()
        let failed = pins.togglePin(type: "event", id: 101)
        publisher.refreshPins()
        XCTAssertEqual(publisher.snapshot?.pins.state, .pending)
        XCTAssertEqual(publisher.snapshot?.pins.items.map(\.targetID), [101])
        await failed?.value
        publisher.refreshPins()
        XCTAssertEqual(publisher.snapshot?.pins.items.map(\.targetID), [101])
        XCTAssertEqual(publisher.snapshot?.pins.state, .failed)
        writeFails = false
        let success = pins.togglePin(type: "event", id: 101)
        await success?.value
        publisher.refreshPins()
        XCTAssertEqual(publisher.snapshot?.pins.items.count, 0, "Acknowledged unpin survives an earlier failed list read")
        XCTAssertEqual(publisher.snapshot?.pins.state, .failed, "The failed list read is not silently relabeled as loaded empty")
    }

    @MainActor func testPinFailureCannotEraseConfirmedRowsOrClaimLoadedEmpty() async throws {
        let name = "watch-publisher-failure-\(UUID())"
        let defaults = try XCTUnwrap(UserDefaults(suiteName: name))
        defer { defaults.removePersistentDomain(forName: name) }
        var fail = false
        let identity = PinAccountBinding(userID: "account", authenticated: true)
        let pins = PinManager(defaults: defaults, initialBinding: identity, serverLoad: {
            if fail { throw URLError(.notConnectedToInternet) }
            return PinsResponse(events: [101], futures: [])
        })
        await pins.loadPins()
        let publisher = WatchMyStuffPublisher(fetchPreferences: { throw URLError(.notConnectedToInternet) },
                                               lookupPin: { _ in .failed })
        publisher.bind(identity, pins: pins)
        XCTAssertEqual(publisher.snapshot?.pins.items.map(\.targetID), [101])
        let originalSync = publisher.snapshot?.pins.syncedAt
        fail = true
        await pins.loadPins()
        publisher.refreshPins()
        XCTAssertEqual(publisher.snapshot?.pins.state, .failed)
        XCTAssertEqual(publisher.snapshot?.pins.items.map(\.targetID), [101])
        XCTAssertEqual(publisher.snapshot?.pins.syncedAt, originalSync)
    }
}
#endif
