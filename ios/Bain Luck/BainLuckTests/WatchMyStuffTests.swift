import XCTest
@testable import Bain_Luck

final class WatchMyStuffTests: XCTestCase {
    private let instant = Date(timeIntervalSince1970: 1_800_000_000)
    private func packet(publisher: UUID = UUID(), generation: Int = 1, revision: Int = 1,
                        account: WatchMyStuffSnapshot.Account = .signedIn,
                        pins: WatchMyStuffSnapshot.Section = .init(state: .loaded)) -> WatchMyStuffSnapshot {
        .init(version: 1, publisher: publisher, generation: generation, revision: revision,
              sampledAt: instant, validUntil: instant.addingTimeInterval(3600), account: account,
              pins: pins, teams: .init(state: .loaded))
    }
    private func encoded(_ value: WatchMyStuffSnapshot) throws -> Data { try JSONEncoder().encode(value) }

    func testPublisherChangesRequireHandshakeAndOldGenerationCannotReturn() {
        let phone = UUID(), replacement = UUID()
        var cursor = WatchMyStuffCursor()
        XCTAssertFalse(cursor.accept(packet(publisher: phone), pairedHandshake: false))
        XCTAssertTrue(cursor.accept(packet(publisher: phone), pairedHandshake: true))
        XCTAssertFalse(cursor.accept(packet(publisher: phone), pairedHandshake: true), "Duplicate is not a new publication")
        XCTAssertTrue(cursor.accept(packet(publisher: phone, generation: 2, revision: 4, account: .signedOut), pairedHandshake: false))
        XCTAssertFalse(cursor.accept(packet(publisher: phone, generation: 1, revision: 5), pairedHandshake: true))
        XCTAssertFalse(cursor.accept(packet(publisher: replacement), pairedHandshake: false))
        XCTAssertTrue(cursor.accept(packet(publisher: replacement), pairedHandshake: true))
        XCTAssertFalse(cursor.accept(packet(publisher: phone, generation: 3, revision: 9), pairedHandshake: false))
    }

    func testBoundsAndExpiredSessionsAreRejectedInsteadOfPainted() throws {
        XCTAssertNil(WatchMyStuffSnapshot.decode(Data(repeating: 32, count: WatchMyStuffSnapshot.maxBytes + 1), now: instant))
        XCTAssertNil(WatchMyStuffSnapshot.decode(try encoded(packet()), now: instant.addingTimeInterval(3601)))
        let item = WatchMyStuffSnapshot.Item(kind: "future", targetID: 17, relation: nil, title: "Exact question")
        XCTAssertNil(WatchMyStuffSnapshot.decode(try encoded(packet(pins: .init(state: .loaded, items: [item, item]))), now: instant))
        XCTAssertNil(WatchMyStuffSnapshot.decode(try encoded(packet(account: .signedOut, pins: .init(items: [item]))), now: instant))
    }

    func testCanonicalRelationsRemainDistinctWithIdenticalNames() {
        let items = ["follow", "local", "alma_mater", "rival"].map {
            WatchMyStuffSnapshot.Item(kind: "team", targetID: 72, relation: $0, title: "Same name")
        }
        XCTAssertEqual(Set(items.map(\.id)).count, 4)
        XCTAssertEqual(items.map(\.relationLabel), ["Following", "Local team", "Alma mater", "Rival"])
    }

    @MainActor func testLateHandshakeAndLogoutCannotRepopulateCache() throws {
        let name = "watch-my-stuff-test-\(UUID())"
        let defaults = try XCTUnwrap(UserDefaults(suiteName: name))
        defer { defaults.removePersistentDomain(forName: name) }
        let store = WatchMyStuffStore(defaults: defaults, now: { self.instant })
        let oldNonce = store.beginHandshake()
        let nonce = store.beginHandshake()
        let phone = UUID()
        let value = packet(publisher: phone)
        store.receive(try encoded(value), handshake: oldNonce)
        XCTAssertNil(store.snapshot)
        store.receive(try encoded(value), handshake: nonce)
        XCTAssertTrue(store.connected)
        let oldNavigation = store.navigationGeneration
        store.receive(try encoded(packet(publisher: phone, generation: 2, revision: 2, account: .signedOut)))
        XCTAssertEqual(store.snapshot?.account, .signedOut)
        XCTAssertNotEqual(store.navigationGeneration, oldNavigation)
        store.receive(try encoded(packet(publisher: phone, revision: 3)))
        XCTAssertEqual(store.snapshot?.account, .signedOut)
        let restarted = WatchMyStuffStore(defaults: defaults, now: { self.instant })
        restarted.receive(try encoded(value))
        XCTAssertEqual(restarted.snapshot?.account, .signedOut)
    }

    @MainActor func testFailureIsNotEmptyAndExpiredCacheCannotAuthorizeRows() throws {
        let name = "watch-my-stuff-expiry-\(UUID())"
        let defaults = try XCTUnwrap(UserDefaults(suiteName: name))
        defer { defaults.removePersistentDomain(forName: name) }
        var clock = instant
        let store = WatchMyStuffStore(defaults: defaults, now: { clock })
        let item = WatchMyStuffSnapshot.Item(kind: "event", targetID: 101, relation: nil, title: "Away at Home")
        let phone = UUID()
        store.receive(try encoded(packet(publisher: phone, pins: .init(state: .loaded, items: [item], syncedAt: instant))),
                      handshake: store.beginHandshake())
        store.receive(try encoded(packet(publisher: phone, revision: 2,
            pins: .init(state: .failed, items: [item], syncedAt: instant))))
        XCTAssertTrue(store.contains(item))
        XCTAssertEqual(store.snapshot?.pins.state, .failed)
        XCTAssertEqual(store.snapshot?.pins.syncedAt, instant)
        clock = instant.addingTimeInterval(3601)
        store.expireIfNeeded()
        XCTAssertNil(store.snapshot)
        XCTAssertFalse(store.contains(item))
        clock = instant
        store.receive(try encoded(packet(publisher: phone)))
        XCTAssertNil(store.snapshot, "Expiry retains the revision fence")
    }

    @MainActor func testConfirmedUnpinRevokesPersonalSelection() throws {
        let name = "watch-my-stuff-selection-\(UUID())"
        let defaults = try XCTUnwrap(UserDefaults(suiteName: name))
        defer { defaults.removePersistentDomain(forName: name) }
        let selected = WatchSelectedGameStore(defaults: defaults)
        let store = WatchMyStuffStore(defaults: defaults, now: { self.instant })
        let item = WatchMyStuffSnapshot.Item(kind: "event", targetID: 101, relation: nil, title: "Pinned game")
        let phone = UUID()
        store.receive(try encoded(packet(publisher: phone, pins: .init(state: .loaded, items: [item]))),
                      handshake: store.beginHandshake())
        store.select(eventID: 101, from: item, in: selected)
        XCTAssertEqual(selected.selectedEventID, 101)
        store.receive(try encoded(packet(publisher: phone, revision: 2)))
        store.reconcileSelection(in: selected)
        XCTAssertNil(selected.selectedEventID)
    }

    @MainActor func testConcurrentSyncTriggersPreserveFirstReplyAndPermitNextSync() throws {
        let name = "watch-my-stuff-coalescing-\(UUID())"
        let defaults = try XCTUnwrap(UserDefaults(suiteName: name))
        defer { defaults.removePersistentDomain(forName: name) }
        let store = WatchMyStuffStore(defaults: defaults, now: { self.instant })
        let value = packet()
        let data = try encoded(value)
        let first = try XCTUnwrap(store.beginHandshakeIfNeeded())
        XCTAssertNil(store.beginHandshakeIfNeeded(), "Screen entry must share the foreground request")
        XCTAssertNil(store.beginHandshakeIfNeeded(), "Reachability must not replace its nonce or restart its timeout")
        store.receive(data, handshake: first)
        XCTAssertEqual(store.snapshot, value)
        XCTAssertTrue(store.connected, "The original valid phone reply still completes sync")
        XCTAssertFalse(store.connecting)

        let next = try XCTUnwrap(store.beginHandshakeIfNeeded())
        XCTAssertNotEqual(next, first)
        store.receive(data, handshake: first)
        XCTAssertTrue(store.connecting, "A stale callback cannot finish the new request")
        XCTAssertFalse(store.connected)
        store.receive(data, handshake: next)
        XCTAssertTrue(store.connected, "An unchanged current reply can verify a later sync")
        XCTAssertFalse(store.connecting)
    }

    @MainActor func testFailedOrDisconnectedCoalescedHandshakeCanRetry() throws {
        let name = "watch-my-stuff-coalesced-retry-\(UUID())"
        let defaults = try XCTUnwrap(UserDefaults(suiteName: name))
        defer { defaults.removePersistentDomain(forName: name) }
        let store = WatchMyStuffStore(defaults: defaults, now: { self.instant })
        let data = try encoded(packet())
        let first = try XCTUnwrap(store.beginHandshakeIfNeeded())
        XCTAssertNil(store.beginHandshakeIfNeeded())
        store.failedHandshake(first) // Existing timeout and transport-error path.
        XCTAssertFalse(store.connecting)
        let retry = try XCTUnwrap(store.beginHandshakeIfNeeded())
        store.receive(data, handshake: first)
        XCTAssertNil(store.snapshot)
        store.failedHandshake(first)
        XCTAssertTrue(store.connecting, "The old timeout cannot end the retry")
        store.disconnect() // Existing unreachable/background path.
        XCTAssertFalse(store.connecting)
        let resumed = try XCTUnwrap(store.beginHandshakeIfNeeded())
        store.receive(data, handshake: retry)
        XCTAssertNil(store.snapshot)
        XCTAssertTrue(store.connecting)
        store.receive(data, handshake: resumed)
        XCTAssertTrue(store.connected)
        XCTAssertFalse(store.connecting)
    }
}
