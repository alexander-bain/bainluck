#if os(iOS) && canImport(ActivityKit)
import Foundation
import XCTest
@testable import Bain_Luck

@MainActor private final class RegistrationTransportFake: GameActivityRegistrationTransport {
    struct Call {
        let token: String?
        let version: Int
        let bearer: String
        let mutationID: UUID
    }
    var calls: [Call] = []
    var pending: CheckedContinuation<GameActivityRegistrationMetadata, Error>?
    var reads = 0
    var readVersion = 1
    var readActive = true
    var readError: Error?
    var readBearers: [String] = []
    func read(id: String, bearer: String) async throws -> GameActivityRegistrationMetadata {
        reads += 1
        readBearers.append(bearer)
        if let readError { throw readError }
        return .init(activityID: id, eventID: 42, version: readVersion, isActive: readActive)
    }
    func mutate(id: String, eventID: Int, token: String?, version: Int,
                mutationID: UUID, bearer: String) async throws -> GameActivityRegistrationMetadata {
        calls.append(.init(token: token, version: version, bearer: bearer, mutationID: mutationID))
        return try await withCheckedThrowingContinuation { pending = $0 }
    }
    func complete(version: Int, active: Bool) {
        let continuation = pending
        pending = nil
        continuation?.resume(returning: .init(activityID: "activity", eventID: 42,
                                               version: version, isActive: active))
    }
    func fail(_ error: Error) {
        let continuation = pending
        pending = nil
        continuation?.resume(throwing: error)
    }
}

@MainActor final class GameActivityRegistrationTests: XCTestCase {
    private func coordinator(_ transport: RegistrationTransportFake) -> GameActivityRegistrationCoordinator {
        let name = "GameActivityRegistrationTests.\(UUID().uuidString)"
        let defaults = UserDefaults(suiteName: name)!
        defaults.removePersistentDomain(forName: name)
        return GameActivityRegistrationCoordinator(transport: transport, defaults: defaults)
    }
    private func waitForCalls(_ count: Int, _ transport: RegistrationTransportFake) async {
        for _ in 0..<1000 {
            if transport.calls.count >= count { return }
            await Task.yield()
        }
        XCTFail("Expected bounded registration call")
    }
    func testAnonymousNeverRequestsRegistration() async {
        let transport = RegistrationTransportFake()
        let subject = coordinator(transport)
        XCTAssertFalse(subject.canRequestPushToken)
        subject.bind(id: "activity", eventID: 42)
        subject.receive(id: "activity", token: Data([0xab]))
        subject.stop(id: "activity")
        await Task.yield()
        XCTAssertTrue(transport.calls.isEmpty)
    }
    func testStopDuringInitialRegistrationRevokesReturnedVersionAndIgnoresLateToken() async {
        let transport = RegistrationTransportFake()
        let subject = coordinator(transport)
        subject.setSession(owner: 1, bearer: "test-old-session")
        subject.bind(id: "activity", eventID: 42)
        subject.receive(id: "activity", token: Data([0xab, 0x01]))
        await waitForCalls(1, transport)
        subject.stop(id: "activity")
        subject.receive(id: "activity", token: Data([0xff]))
        transport.complete(version: 1, active: true)
        await waitForCalls(2, transport)
        XCTAssertEqual(transport.calls[0].token, "ab01")
        XCTAssertNil(transport.calls[1].token)
        XCTAssertEqual(transport.calls[1].version, 1)
        transport.complete(version: 2, active: false)
        for _ in 0..<100 { await Task.yield() }
        XCTAssertTrue(subject.unconfirmedRevocations.isEmpty)
        XCTAssertEqual(transport.calls.count, 2)
    }
    func testRotationCoalescesToLatestToken() async {
        let transport = RegistrationTransportFake()
        let subject = coordinator(transport)
        subject.setSession(owner: 1, bearer: "test-session")
        subject.bind(id: "activity", eventID: 42)
        subject.receive(id: "activity", token: Data([1]))
        await waitForCalls(1, transport)
        subject.receive(id: "activity", token: Data([2]))
        subject.receive(id: "activity", token: Data([3]))
        transport.complete(version: 1, active: true)
        await waitForCalls(2, transport)
        XCTAssertEqual(transport.calls[1].token, "03")
        XCTAssertEqual(transport.calls[1].version, 1)
        transport.complete(version: 2, active: true)
    }
    func testAccountSwitchUsesOldCredentialForRevocation() async {
        let transport = RegistrationTransportFake()
        let subject = coordinator(transport)
        subject.setSession(owner: 1, bearer: "test-old-session")
        subject.bind(id: "activity", eventID: 42)
        subject.receive(id: "activity", token: Data([1]))
        await waitForCalls(1, transport)
        subject.setSession(owner: 2, bearer: "test-new-session")
        subject.receive(id: "activity", token: Data([2]))
        transport.complete(version: 1, active: true)
        await waitForCalls(2, transport)
        XCTAssertNil(transport.calls[1].token)
        XCTAssertEqual(transport.calls[1].bearer, "test-old-session")
        transport.fail(GameActivityRegistrationError.unavailable)
        for _ in 0..<100 { await Task.yield() }
        XCTAssertEqual(subject.unconfirmedRevocations, ["activity"])
    }
    func testConflictRequiresReadThenRevokeWithCurrentVersion() async {
        let transport = RegistrationTransportFake()
        let subject = coordinator(transport)
        subject.setSession(owner: 1, bearer: "test-session")
        subject.bind(id: "activity", eventID: 42)
        subject.stop(id: "activity")
        await waitForCalls(1, transport)
        transport.readVersion = 4
        transport.fail(GameActivityRegistrationError.conflict)
        await waitForCalls(2, transport)
        XCTAssertEqual(transport.reads, 1)
        XCTAssertEqual(transport.calls[1].version, 4)
        XCTAssertNil(transport.calls[1].token)
        XCTAssertEqual(subject.unconfirmedRevocations, ["activity"])
        transport.complete(version: 5, active: false)
    }
    func testOfflineRegistrationRetriesUnchangedTokenOnForegroundOnly() async {
        let transport = RegistrationTransportFake()
        let subject = coordinator(transport)
        subject.setSession(owner: 1, bearer: "test-session")
        subject.bind(id: "activity", eventID: 42)
        subject.receive(id: "activity", token: Data([0xab]))
        await waitForCalls(1, transport)
        transport.fail(GameActivityRegistrationError.unavailable)
        for _ in 0..<100 { await Task.yield() }
        XCTAssertEqual(transport.calls.count, 1, "No automatic retry timer")
        subject.foregroundActivated()
        await waitForCalls(2, transport)
        XCTAssertEqual(transport.calls[1].token, "ab")
        XCTAssertEqual(transport.calls[1].mutationID, transport.calls[0].mutationID,
                       "Retry an ambiguous result using the identical mutation")
        transport.complete(version: 1, active: true)
        for _ in 0..<100 { await Task.yield() }
        subject.foregroundActivated()
        await Task.yield()
        XCTAssertEqual(transport.calls.count, 2, "Acknowledged token needs no retry")
    }
    func testSameOwnerAuthRefreshRetriesWithRefreshedBearer() async {
        let transport = RegistrationTransportFake()
        let subject = coordinator(transport)
        subject.setSession(owner: 1, bearer: "test-expired-session")
        subject.bind(id: "activity", eventID: 42)
        subject.receive(id: "activity", token: Data([1]))
        await waitForCalls(1, transport)
        transport.fail(GameActivityRegistrationError.unavailable)
        for _ in 0..<100 { await Task.yield() }
        subject.setSession(owner: 1, bearer: "test-refreshed-session")
        await waitForCalls(2, transport)
        XCTAssertEqual(transport.calls[1].bearer, "test-refreshed-session")
        XCTAssertEqual(transport.calls[1].mutationID, transport.calls[0].mutationID)
        transport.complete(version: 1, active: true)
        for _ in 0..<100 { await Task.yield() }
        subject.stop(id: "activity")
        await waitForCalls(3, transport)
        XCTAssertNil(transport.calls[2].token)
        XCTAssertEqual(transport.calls[2].bearer, "test-refreshed-session")
        transport.complete(version: 2, active: false)
    }
    func testForegroundRecoveryCannotRegisterAfterStop() async {
        let transport = RegistrationTransportFake()
        let subject = coordinator(transport)
        subject.setSession(owner: 1, bearer: "test-session")
        subject.bind(id: "activity", eventID: 42)
        subject.receive(id: "activity", token: Data([1]))
        await waitForCalls(1, transport)
        transport.fail(GameActivityRegistrationError.unavailable)
        for _ in 0..<100 { await Task.yield() }
        subject.stop(id: "activity")
        subject.foregroundActivated()
        await waitForCalls(2, transport)
        XCTAssertNil(transport.calls[1].token)
        transport.fail(GameActivityRegistrationError.unavailable)
        for _ in 0..<100 { await Task.yield() }
        subject.foregroundActivated()
        subject.receive(id: "activity", token: Data([2]))
        await Task.yield()
        await waitForCalls(3, transport)
        XCTAssertNil(transport.calls[2].token)
        XCTAssertEqual(transport.calls[2].mutationID, transport.calls[1].mutationID)
        XCTAssertEqual(subject.unconfirmedRevocations, ["activity"])
        transport.complete(version: 1, active: false)
    }

    func testRestartPreservesStopBeforeInFlightRegistrationAcknowledges() async {
        let name = "GameActivityRegistrationRestartTests.\(UUID().uuidString)"
        let defaults = UserDefaults(suiteName: name)!
        defer { defaults.removePersistentDomain(forName: name) }
        let transport = RegistrationTransportFake()
        let original = GameActivityRegistrationCoordinator(transport: transport, defaults: defaults)
        original.setSession(owner: 1, bearer: "test-session")
        original.bind(id: "activity", eventID: 42)
        original.receive(id: "activity", token: Data([1]))
        await waitForCalls(1, transport)
        original.stop(id: "activity")
        // Relaunch happens before PUT/DELETE or local ActivityKit end can finish.
        let restartedTransport = RegistrationTransportFake()
        let restarted = GameActivityRegistrationCoordinator(transport: restartedTransport, defaults: defaults)
        restarted.setSession(owner: 1, bearer: "test-session")
        restarted.bind(id: "activity", eventID: 42)
        restarted.receive(id: "activity", token: Data([1]))
        await waitForCalls(1, restartedTransport)
        XCTAssertNil(restartedTransport.calls[0].token, "Crash recovery is DELETE only")
        restartedTransport.fail(GameActivityRegistrationError.unavailable)
        for _ in 0..<100 { await Task.yield() }
        transport.complete(version: 1, active: true)
        await waitForCalls(2, transport)
        transport.fail(GameActivityRegistrationError.unavailable)
        for _ in 0..<100 { await Task.yield() }
        let recoveryTransport = RegistrationTransportFake()
        let offlineRestart = GameActivityRegistrationCoordinator(transport: recoveryTransport, defaults: defaults)
        offlineRestart.setSession(owner: 1, bearer: "test-refreshed-session")
        await waitForCalls(1, recoveryTransport)
        XCTAssertNil(recoveryTransport.calls[0].token)
        XCTAssertEqual(offlineRestart.unconfirmedRevocations, ["activity"])
        recoveryTransport.complete(version: 2, active: false)
    }

    func testLogoutPersistsStopForOwnedActivityBeforeObservationRestores() async {
        let name = "GameActivityRegistrationColdLogoutTests.\(UUID().uuidString)"
        let defaults = UserDefaults(suiteName: name)!
        defer { defaults.removePersistentDomain(forName: name) }
        defaults.set(["activity": 1], forKey: "gameActivityRegistrationOwners")
        let transport = RegistrationTransportFake()
        let subject = GameActivityRegistrationCoordinator(transport: transport, defaults: defaults)
        subject.invalidateSession()
        let restarted = GameActivityRegistrationCoordinator(transport: transport, defaults: defaults)
        restarted.setSession(owner: 1, bearer: "test-session")
        restarted.bind(id: "activity", eventID: 42)
        restarted.receive(id: "activity", token: Data([1]))
        restarted.foregroundActivated()
        await Task.yield()
        await waitForCalls(1, transport)
        XCTAssertNil(transport.calls[0].token)
        XCTAssertEqual(restarted.unconfirmedRevocations, ["activity"])
        transport.complete(version: 2, active: false)
    }

    func testColdOfflineStopWithoutEntrySurvivesSameAccountRestore() async {
        let name = "GameActivityRegistrationColdStopTests.\(UUID().uuidString)"
        let defaults = UserDefaults(suiteName: name)!
        defer { defaults.removePersistentDomain(forName: name) }
        defaults.set(["activity": 1], forKey: "gameActivityRegistrationOwners")
        let transport = RegistrationTransportFake()
        let cold = GameActivityRegistrationCoordinator(transport: transport, defaults: defaults)
        XCTAssertFalse(cold.canRequestPushToken)
        cold.stop(id: "activity")
        // No credentials or in-memory entry were available for remote work.
        await Task.yield()
        XCTAssertTrue(transport.calls.isEmpty)
        let restarted = GameActivityRegistrationCoordinator(transport: transport, defaults: defaults)
        restarted.setSession(owner: 1, bearer: "test-restored-session")
        restarted.bind(id: "activity", eventID: 42)
        restarted.receive(id: "activity", token: Data([1]))
        restarted.foregroundActivated()
        await Task.yield()
        await waitForCalls(1, transport)
        XCTAssertNil(transport.calls[0].token, "Cold stop is DELETE-only after restore")
        XCTAssertEqual(restarted.unconfirmedRevocations, ["activity"])
        transport.complete(version: 2, active: false)
    }

    func testRejectedAuthAndFailedSilentRestorePersistActivityStop() async {
        for status in [401, 403] {
            let name = "GameActivityRejectedRestoreTests.\(UUID().uuidString)"
            let defaults = UserDefaults(suiteName: name)!
            defer { defaults.removePersistentDomain(forName: name) }
            defaults.set(["activity": 1], forKey: "gameActivityRegistrationOwners")
            let transport = RegistrationTransportFake()
            let subject = GameActivityRegistrationCoordinator(transport: transport, defaults: defaults)
            var credentialRetained = true
            var silentAttempts = 0
            await AuthManager.resolveSessionRestoreFailure(.httpError(statusCode: status, body: nil),
                attemptSilentRestore: { silentAttempts += 1; return false },
                clearCredentials: {
                    subject.invalidateSession()
                    XCTAssertEqual(subject.unconfirmedRevocations, ["activity"])
                    credentialRetained = false
                })
            XCTAssertEqual(silentAttempts, 1)
            XCTAssertFalse(credentialRetained)
            let restarted = GameActivityRegistrationCoordinator(transport: transport, defaults: defaults)
            restarted.setSession(owner: 1, bearer: "test-session")
            restarted.bind(id: "activity", eventID: 42)
            restarted.receive(id: "activity", token: Data([1]))
            await Task.yield()
            await waitForCalls(1, transport)
            XCTAssertNil(transport.calls[0].token)
            XCTAssertEqual(restarted.unconfirmedRevocations, ["activity"])
            transport.complete(version: 2, active: false)
        }
    }
    func testTransientRestoreRetainsCredentialsAndDoesNotStopActivity() async {
        for error in [APIError.networkError(underlying: URLError(.notConnectedToInternet)),
                      APIError.httpError(statusCode: 503, body: nil)] {
            let transport = RegistrationTransportFake()
            let subject = coordinator(transport)
            var credentialRetained = true
            var silentAttempts = 0
            await AuthManager.resolveSessionRestoreFailure(error,
                attemptSilentRestore: { silentAttempts += 1; return false },
                clearCredentials: { subject.invalidateSession(); credentialRetained = false })
            XCTAssertTrue(credentialRetained)
            XCTAssertEqual(silentAttempts, 0)
            XCTAssertTrue(subject.unconfirmedRevocations.isEmpty)
        }
    }
    func testSuccessfulSilentRestoreRetainsCredentialsAndActivity() async {
        let transport = RegistrationTransportFake()
        let subject = coordinator(transport)
        var credentialRetained = true
        await AuthManager.resolveSessionRestoreFailure(.httpError(statusCode: 401, body: nil),
            attemptSilentRestore: { true },
            clearCredentials: { subject.invalidateSession(); credentialRetained = false })
        XCTAssertTrue(credentialRetained)
        XCTAssertTrue(subject.unconfirmedRevocations.isEmpty)
    }

    func testColdAccountSwitchEndsOldIdentityWithoutNewOwnerRevocation() async {
        let name = "GameActivityColdAccountSwitchTests.\(UUID().uuidString)"
        let defaults = UserDefaults(suiteName: name)!
        defer { defaults.removePersistentDomain(forName: name) }
        defaults.set(["activity": 1], forKey: "gameActivityRegistrationOwners")
        let transport = RegistrationTransportFake()
        let cold = GameActivityRegistrationCoordinator(transport: transport, defaults: defaults)
        cold.setSession(owner: 2, bearer: "test-new-owner-session")
        XCTAssertEqual(cold.restoreOwnership(id: "activity", eventID: 42), .end)
        XCTAssertEqual(defaults.stringArray(forKey: "gameActivityRegistrationStoppedIDs"), ["activity"])
        cold.bind(id: "activity", eventID: 42)
        cold.receive(id: "activity", token: Data([1]))
        cold.foregroundActivated()
        await Task.yield()
        XCTAssertTrue(transport.calls.isEmpty, "New owner may neither register nor revoke old ownership")
        XCTAssertEqual(cold.unconfirmedRevocations, ["activity"])
    }
    func testColdSameOwnerCanRestoreObservationAndRegister() async {
        let name = "GameActivityColdSameOwnerTests.\(UUID().uuidString)"
        let defaults = UserDefaults(suiteName: name)!
        defer { defaults.removePersistentDomain(forName: name) }
        defaults.set(["activity": 1], forKey: "gameActivityRegistrationOwners")
        let transport = RegistrationTransportFake()
        let cold = GameActivityRegistrationCoordinator(transport: transport, defaults: defaults)
        cold.setSession(owner: 1, bearer: "test-restored-owner-session")
        XCTAssertEqual(cold.restoreOwnership(id: "activity", eventID: 42), .observe)
        XCTAssertEqual(defaults.stringArray(forKey: "gameActivityRegistrationStoppedIDs") ?? [], [])
        cold.bind(id: "activity", eventID: 42)
        cold.receive(id: "activity", token: Data([0xab]))
        await waitForCalls(1, transport)
        XCTAssertEqual(transport.calls[0].bearer, "test-restored-owner-session")
        XCTAssertEqual(transport.calls[0].token, "ab")
        XCTAssertTrue(cold.unconfirmedRevocations.isEmpty)
        transport.complete(version: 1, active: true)
    }

    func testAbsentActivityReconcilesOnlyWhenOriginalOwnerReturnsAndRetainsStopAfterAck() async {
        let name = "GameActivityDurableRevokeTests.\(UUID().uuidString)"
        let defaults = UserDefaults(suiteName: name)!
        defer { defaults.removePersistentDomain(forName: name) }
        let firstTransport = RegistrationTransportFake()
        let first = GameActivityRegistrationCoordinator(transport: firstTransport, defaults: defaults)
        first.setSession(owner: 1, bearer: "owner-a")
        first.bind(id: "activity", eventID: 42)
        first.stop(id: "activity")
        await waitForCalls(1, firstTransport)
        firstTransport.fail(GameActivityRegistrationError.unavailable)
        for _ in 0..<100 { await Task.yield() }
        let transport = RegistrationTransportFake()
        let restarted = GameActivityRegistrationCoordinator(transport: transport, defaults: defaults)
        restarted.setSession(owner: 2, bearer: "owner-b")
        for _ in 0..<100 { await Task.yield() }
        XCTAssertTrue(transport.calls.isEmpty)
        XCTAssertTrue(transport.readBearers.isEmpty)
        restarted.setSession(owner: 1, bearer: "owner-a-refreshed")
        await waitForCalls(1, transport)
        XCTAssertNil(transport.calls[0].token)
        XCTAssertEqual(transport.calls[0].bearer, "owner-a-refreshed")
        XCTAssertEqual(transport.calls[0].mutationID, firstTransport.calls[0].mutationID)
        transport.complete(version: 1, active: false)
        for _ in 0..<100 { await Task.yield() }
        XCTAssertTrue(restarted.unconfirmedRevocations.isEmpty)
        restarted.bind(id: "activity", eventID: 42)
        restarted.receive(id: "activity", token: Data([1]))
        restarted.foregroundActivated()
        for _ in 0..<100 { await Task.yield() }
        XCTAssertEqual(transport.calls.count, 1, "Acknowledged identity can never register again")
        XCTAssertEqual(defaults.stringArray(forKey: "gameActivityRegistrationStoppedIDs"), ["activity"])
        let final = GameActivityRegistrationCoordinator(transport: transport, defaults: defaults)
        final.setSession(owner: 1, bearer: "owner-a")
        XCTAssertTrue(final.unconfirmedRevocations.isEmpty)
    }
    func testActiveDeleteResponseDoesNotAcknowledgeAndConflictReadInactiveDoes() async {
        let transport = RegistrationTransportFake()
        let subject = coordinator(transport)
        subject.setSession(owner: 1, bearer: "owner-a")
        subject.bind(id: "activity", eventID: 42)
        subject.stop(id: "activity")
        await waitForCalls(1, transport)
        transport.complete(version: 1, active: true)
        for _ in 0..<100 { await Task.yield() }
        XCTAssertEqual(subject.unconfirmedRevocations, ["activity"])
        subject.foregroundActivated()
        await waitForCalls(2, transport)
        transport.readActive = false
        transport.readVersion = 3
        transport.fail(GameActivityRegistrationError.conflict)
        for _ in 0..<100 { await Task.yield() }
        XCTAssertTrue(subject.unconfirmedRevocations.isEmpty)
        XCTAssertEqual(transport.calls.count, 2)
    }
    func testLegacyStoppedOwnershipReadsInactiveWithoutInventingEventOrSendingDelete() async {
        let name = "GameActivityLegacyRevokeTests.\(UUID().uuidString)"
        let defaults = UserDefaults(suiteName: name)!
        defer { defaults.removePersistentDomain(forName: name) }
        defaults.set(["activity": 1], forKey: "gameActivityRegistrationOwners")
        defaults.set(["activity"], forKey: "gameActivityRegistrationStoppedIDs")
        let transport = RegistrationTransportFake()
        transport.readActive = false
        let subject = GameActivityRegistrationCoordinator(transport: transport, defaults: defaults)
        subject.setSession(owner: 2, bearer: "owner-b")
        for _ in 0..<100 { await Task.yield() }
        XCTAssertEqual(transport.reads, 0)
        subject.setSession(owner: 1, bearer: "owner-a")
        for _ in 0..<100 { await Task.yield() }
        XCTAssertEqual(transport.readBearers, ["owner-a"])
        XCTAssertTrue(transport.calls.isEmpty)
        XCTAssertTrue(subject.unconfirmedRevocations.isEmpty)
        XCTAssertEqual(defaults.stringArray(forKey: "gameActivityRegistrationStoppedIDs"), ["activity"])
    }

    func testDurableTupleWithoutSeparateLatchStillPreventsRegistrationAfterCrash() async throws {
        let name = "GameActivityTupleCrashTests.\(UUID().uuidString)"
        let defaults = UserDefaults(suiteName: name)!
        defer { defaults.removePersistentDomain(forName: name) }
        let mutation = UUID()
        let data = try JSONSerialization.data(withJSONObject: ["activity": [
            "owner": 1, "eventID": 42, "version": 0, "mutationID": mutation.uuidString
        ]])
        defaults.set(data, forKey: "gameActivityRegistrationRevocations")
        let transport = RegistrationTransportFake()
        let subject = GameActivityRegistrationCoordinator(transport: transport, defaults: defaults)
        subject.setSession(owner: 1, bearer: "owner-a")
        subject.bind(id: "activity", eventID: 42)
        subject.receive(id: "activity", token: Data([1]))
        await waitForCalls(1, transport)
        XCTAssertNil(transport.calls[0].token)
        XCTAssertEqual(transport.calls[0].mutationID, mutation)
        XCTAssertEqual(defaults.stringArray(forKey: "gameActivityRegistrationStoppedIDs"), ["activity"])
        transport.complete(version: 1, active: false)
        for _ in 0..<100 { await Task.yield() }
        subject.bind(id: "activity", eventID: 42)
        subject.receive(id: "activity", token: Data([2]))
        for _ in 0..<100 { await Task.yield() }
        XCTAssertEqual(transport.calls.count, 1)
    }

    func testLegacyReadFailureRetainsOwnershipAndStopsWithoutGuessingEvent() async {
        let name = "GameActivityLegacyReadFailureTests.\(UUID().uuidString)"
        let defaults = UserDefaults(suiteName: name)!
        defer { defaults.removePersistentDomain(forName: name) }
        defaults.set(["activity": 1], forKey: "gameActivityRegistrationOwners")
        defaults.set(["activity"], forKey: "gameActivityRegistrationStoppedIDs")
        let transport = RegistrationTransportFake()
        transport.readError = GameActivityRegistrationError.unavailable
        let subject = GameActivityRegistrationCoordinator(transport: transport, defaults: defaults)
        subject.setSession(owner: 1, bearer: "owner-a")
        for _ in 0..<100 { await Task.yield() }
        XCTAssertTrue(transport.calls.isEmpty)
        XCTAssertEqual(subject.unconfirmedRevocations, ["activity"])
        transport.readError = nil
        subject.foregroundActivated()
        await waitForCalls(1, transport)
        XCTAssertNil(transport.calls[0].token)
        XCTAssertEqual(transport.calls[0].version, transport.readVersion)
        transport.complete(version: 2, active: false)
    }
    func testColdAccountSwitchStopsSavedIdentityEvenWithoutActivityKitObject() async {
        let name = "GameActivityAbsentOwnerSwitchTests.\(UUID().uuidString)"
        let defaults = UserDefaults(suiteName: name)!
        defer { defaults.removePersistentDomain(forName: name) }
        defaults.set(["activity": 1], forKey: "gameActivityRegistrationOwners")
        defaults.set(["activity": 42], forKey: "gameActivityRegistrationEventIDs")
        let transport = RegistrationTransportFake()
        let subject = GameActivityRegistrationCoordinator(transport: transport, defaults: defaults)
        subject.setSession(owner: 2, bearer: "owner-b")
        for _ in 0..<100 { await Task.yield() }
        XCTAssertTrue(transport.calls.isEmpty)
        XCTAssertEqual(subject.unconfirmedRevocations, ["activity"])
        subject.setSession(owner: 1, bearer: "owner-a")
        await waitForCalls(1, transport)
        XCTAssertNil(transport.calls[0].token)
        XCTAssertEqual(transport.calls[0].bearer, "owner-a")
        transport.complete(version: 1, active: false)
    }

}
#endif
