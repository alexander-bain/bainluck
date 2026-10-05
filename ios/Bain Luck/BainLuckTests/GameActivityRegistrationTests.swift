#if os(iOS) && canImport(ActivityKit)
import Foundation
import XCTest
@testable import Bain_Luck

@MainActor private final class RegistrationTransportFake: GameActivityRegistrationTransport {
    struct Call {
        let token: String?
        let version: Int
        let bearer: String
    }
    var calls: [Call] = []
    var pending: CheckedContinuation<GameActivityRegistrationMetadata, Error>?
    var reads = 0
    var readVersion = 1
    func read(id: String, bearer: String) async throws -> GameActivityRegistrationMetadata {
        reads += 1
        return .init(activityID: id, eventID: 42, version: readVersion, isActive: true)
    }
    func mutate(id: String, eventID: Int, token: String?, version: Int,
                mutationID: UUID, bearer: String) async throws -> GameActivityRegistrationMetadata {
        calls.append(.init(token: token, version: version, bearer: bearer))
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
}
#endif
