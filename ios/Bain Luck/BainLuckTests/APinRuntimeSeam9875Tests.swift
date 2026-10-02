#if DEBUG
import XCTest
@testable import Bain_Luck

@MainActor
final class APinRuntimeSeam9875Tests: XCTestCase {
    private var suite = ""
    private var settingsSuite = ""
    private var settings: UserDefaults!
    override func setUp() {
        super.setUp()
        suite = "bainluck.debug.9875.\(UUID())"
        settingsSuite = "Pin9875LaunchReaders.\(UUID())"
        settings = UserDefaults(suiteName: settingsSuite)!
    }
    override func tearDown() {
        UserDefaults(suiteName: suite)!.removePersistentDomain(forName: suite)
        settings.removePersistentDomain(forName: settingsSuite)
        settings = nil
        super.tearDown()
    }
    private func runtime(seed: Bool = true, offline: Bool = false) -> PinManagementRuntime9875 {
        PinManagementRuntime9875(configuration: .success(.init(suite: suite, seed: seed, offline: offline)))
    }
    private func standardPinState() -> NSDictionary {
        NSDictionary(dictionary: UserDefaults.standard.dictionaryRepresentation().filter { $0.key.hasPrefix("bainluck_pin") })
    }

    func testAbsentFlagDoesNotArmAndInvalidInputsAreNamedFailures() {
        XCTAssertNil(LaunchRig.pinRuntime9875(defaults: settings))
        for bad in ["standard", "bainluck.debug.9875.user.364", "../pins", ""] {
            settings.set(bad, forKey: LaunchRig.pinRuntime9875Key)
            guard case .failure(_)? = LaunchRig.pinRuntime9875(defaults: settings) else {
                return XCTFail("invalid isolated suite must fail without live fallback")
            }
        }
        settings.set(suite, forKey: LaunchRig.pinRuntime9875Key)
        settings.set("reset_every_launch", forKey: LaunchRig.pinPhase9875Key)
        guard case .failure(_)? = LaunchRig.pinRuntime9875(defaults: settings) else { return XCTFail("bad phase accepted") }
        settings.set("warm", forKey: LaunchRig.pinPhase9875Key)
        settings.set("maybe", forKey: LaunchRig.pinSeed9875Key)
        guard case .failure(_)? = LaunchRig.pinRuntime9875(defaults: settings) else { return XCTFail("bad seed accepted") }
    }

    func testOneTimeSeedAndColdLaunchDoNotRewriteFakeServerOrStandardPins() async {
        let before = standardPinState()
        let warm = runtime()
        let manager = warm.makeManager()
        warm.bindRealIdentity(.init(userID: "unit-real-A", authenticated: true), to: manager)
        await manager.loadPins()
        await manager.togglePin(type: "event", id: 1)?.value
        let cold = runtime(seed: false, offline: true)
        let restored = cold.makeManager()
        cold.bindRealIdentity(.init(userID: "unit-real-A", authenticated: true), to: restored)
        await restored.loadPins()
        XCTAssertEqual(cold.seedState, "retained")
        XCTAssertEqual(restored.loadState, .failed)
        XCTAssertFalse(restored.savedPins.contains(.init(type: "event", value: 1)))
        let repeatedSeed = runtime(seed: true)
        let again = repeatedSeed.makeManager()
        repeatedSeed.bindRealIdentity(.init(userID: "unit-real-A", authenticated: true), to: again)
        await again.loadPins()
        XCTAssertFalse(again.savedPins.contains(.init(type: "event", value: 1)), "seed flag cannot reset an already seeded run")
        XCTAssertEqual(standardPinState(), before)
    }

    func testArmedOfflineTransportNeverFallsBackToLivePins() async {
        let fake = runtime(offline: true)
        let manager = fake.makeManager()
        fake.bindRealIdentity(.init(userID: "unit-real-A", authenticated: true), to: manager)
        await manager.loadPins()
        XCTAssertEqual(manager.loadState, .failed)
        XCTAssertTrue(manager.savedPins.isEmpty)
        XCTAssertTrue(fake.calls.isEmpty)
        XCTAssertTrue(fake.receipt(manager).contains("CONTROLLED PIN BINDING"))
    }

    func testUnseededAndMalformedArmsFailInsteadOfServingEmptyOrNetwork() async {
        let unseeded = runtime(seed: false)
        XCTAssertEqual(unseeded.failure, .harness("unseeded isolated pin store"))
        let malformed = PinManagementRuntime9875(configuration: .failure(.harness("bad input")))
        defer { malformed.defaults.removePersistentDomain(forName: malformed.configuration.suite) }
        let manager = malformed.makeManager()
        malformed.bindRealIdentity(.init(userID: "unit-real-A", authenticated: true), to: manager)
        await manager.loadPins()
        XCTAssertEqual(manager.loadState, .failed)
        XCTAssertTrue(manager.savedPins.isEmpty)
        XCTAssertTrue(malformed.calls.isEmpty)
    }

    func testFixtureBindingNeverUpgradesUnresolvedOrGuestRealAuthentication() async {
        let fake = runtime()
        let manager = fake.makeManager()
        fake.bindRealIdentity(.init(userID: "unit-real-A", authenticated: false), to: manager)
        fake.select(.b, manager: manager)
        XCTAssertFalse(fake.ready)
        XCTAssertFalse(manager.isAuthenticated)
        XCTAssertEqual(fake.slot, .a)
        fake.bindRealIdentity(.init(userID: nil, authenticated: false), to: manager)
        XCTAssertFalse(manager.isAuthenticated)
        XCTAssertTrue(fake.calls.isEmpty)
    }

    func testHeldReplyIsBoundToDispatchAccountAndLateFailureCannotWriteB() async {
        let fake = runtime()
        let manager = fake.makeManager()
        fake.bindRealIdentity(.init(userID: "unit-real-A", authenticated: true), to: manager)
        await manager.loadPins()
        fake.nextReply = .hold
        let removal = manager.togglePin(type: "event", id: 1)
        for _ in 0..<100 where fake.heldSyncCount == 0 { await Task.yield() }
        XCTAssertEqual(fake.heldSyncCount, 1)
        fake.select(.b, manager: manager)
        await manager.loadPins()
        fake.releaseSync(confirm: false)
        await removal?.value
        XCTAssertEqual(Set(manager.pinnedEventIDs), Set([1, 201, 202, 203, 204, 205]))
        XCTAssertNil(manager.feedback)
        XCTAssertEqual(fake.calls.map(\.slot), [.a])
    }

    func testRetainedMalformedServerAndChangedRealPrincipalFailClosed() {
        let first = runtime()
        first.defaults.removeObject(forKey: "fixture.server.A.event")
        let damaged = runtime(seed: false)
        XCTAssertEqual(damaged.failure, .harness("missing or malformed retained fake server IDs"))
        first.defaults.set(Array(1...6), forKey: "fixture.server.A.event")
        let clean = runtime(seed: false)
        let manager = clean.makeManager()
        clean.bindRealIdentity(.init(userID: "unit-real-A", authenticated: true), to: manager)
        clean.bindRealIdentity(.init(userID: "unit-real-B", authenticated: true), to: manager)
        XCTAssertFalse(clean.ready)
        XCTAssertEqual(clean.failure, .harness("actual restored principal changed; fixture cannot adopt another real account"))
    }

}
#endif
