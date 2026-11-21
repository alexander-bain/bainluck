#if os(iOS) && canImport(ActivityKit)
import Foundation
import XCTest
@testable import Bain_Luck

@MainActor
final class LiveActivityPushStart254ATests: XCTestCase {
    private final class MemoryIdentityStore: DeviceIdentityStoring254A, @unchecked Sendable {
        let fixed: DeviceIdentity254A
        init(fixed: DeviceIdentity254A = DeviceIdentity254A(
            deviceID: UUID(uuidString: "11111111-2222-3333-4444-555555555555")!,
            secret: String(repeating: "a", count: 64)
        )) {
            self.fixed = fixed
        }
        func loadOrCreate() -> DeviceIdentity254A { fixed }
    }

    @MainActor
    private final class MockPushDeviceTransport: PushDeviceTransport254A {
        struct PutCall: Equatable {
            let identity: DeviceIdentity254A
            let state: PushDeviceState254A
        }
        struct ClaimCall: Equatable {
            let identity: DeviceIdentity254A
            let bearer: String
        }
        struct MutateCall: Equatable {
            let id: String
            let eventID: Int
            let token: String?
            let version: Int
            let identity: DeviceIdentity254A
        }

        var putCalls: [PutCall] = []
        var claimCalls: [ClaimCall] = []
        var mutateCalls: [MutateCall] = []
        var failNextPut = false
        var failNextMutateWithConflict = false
        var serverVersionByActivity: [String: Int] = [:]

        func putDevice(identity: DeviceIdentity254A, state: PushDeviceState254A) async throws {
            if failNextPut {
                failNextPut = false
                throw PushDeviceClientError254A.unavailable
            }
            putCalls.append(PutCall(identity: identity, state: state))
        }

        func claimDevice(identity: DeviceIdentity254A, bearer: String) async throws {
            claimCalls.append(ClaimCall(identity: identity, bearer: bearer))
        }

        func readActivityRegistration(
            id: String,
            identity: DeviceIdentity254A
        ) async throws -> GameActivityRegistrationMetadata {
            let v = serverVersionByActivity[id] ?? 1
            return GameActivityRegistrationMetadata(activityID: id, eventID: 4201, version: v, isActive: true)
        }

        func mutateActivityRegistration(
            id: String,
            eventID: Int,
            token: String?,
            version: Int,
            mutationID: UUID,
            identity: DeviceIdentity254A
        ) async throws -> GameActivityRegistrationMetadata {
            if failNextMutateWithConflict {
                failNextMutateWithConflict = false
                serverVersionByActivity[id] = 3
                throw PushDeviceClientError254A.conflict
            }
            mutateCalls.append(MutateCall(id: id, eventID: eventID, token: token, version: version, identity: identity))
            let nextVersion = version + 1
            serverVersionByActivity[id] = nextVersion
            return GameActivityRegistrationMetadata(
                activityID: id,
                eventID: eventID,
                version: nextVersion,
                isActive: token != nil
            )
        }
    }

    func testGeneratedSecretMatchesBackendDeviceAuthContract() {
        let secret = DeviceIdentity254A.generateSecret()
        XCTAssertEqual(secret.count, 64)
        XCTAssertTrue(secret.allSatisfy { "0123456789abcdef".contains($0) })
        let second = DeviceIdentity254A.generateSecret()
        XCTAssertNotEqual(secret, second)
    }

    func testDeviceStateWireJSONMatchesBackendExtraForbidSchema() throws {
        let state = PushDeviceState254A(
            platform: "ios",
            apnsEnv: "production",
            laStartToken: "AABBCCDD",
            osMajor: 18,
            appVersion: "1.0.8",
            pinnedEventIDs: [42, -1, 0, 7, 42],
            pinnedMarketIDs: [99, 12]
        )
        let data = try JSONEncoder().encode(state)
        let json = try XCTUnwrap(JSONSerialization.jsonObject(with: data) as? [String: Any])

        XCTAssertEqual(Set(json.keys), [
            "platform", "apns_env", "la_start_token", "os_major", "app_version",
            "pinned_event_ids", "pinned_market_ids",
        ])
        XCTAssertEqual(json["platform"] as? String, "ios")
        XCTAssertEqual(json["apns_env"] as? String, "production")
        XCTAssertEqual(json["la_start_token"] as? String, "aabbccdd")
        XCTAssertEqual(json["os_major"] as? Int, 18)
        XCTAssertEqual(json["app_version"] as? String, "1.0.8")
        XCTAssertEqual(json["pinned_event_ids"] as? [Int], [7, 42])
        XCTAssertEqual(json["pinned_market_ids"] as? [Int], [12, 99])
    }

    func testSyncWaitsForStartTokenDeduplicatesUnchangedStateAndClaimsOnce() async {
        let store = MemoryIdentityStore()
        let transport = MockPushDeviceTransport()
        let coordinator = LiveActivityPushStartCoordinator254A(
            identityStore: store,
            transport: transport,
            apnsEnv: "production",
            osMajor: 18,
            appVersion: "1.0.8"
        )

        // Pin update before any push-to-start token does not create an empty device row.
        await coordinator.updatePins(eventIDs: [101], marketIDs: [202])
        XCTAssertEqual(transport.putCalls.count, 0)

        // Receiving push-to-start token syncs token + current pins immediately.
        await coordinator.receiveStartToken(Data([0xDE, 0xAD, 0xBE, 0xEF]))
        XCTAssertEqual(transport.putCalls.count, 1)
        XCTAssertEqual(transport.putCalls[0].state.laStartToken, "deadbeef")
        XCTAssertEqual(transport.putCalls[0].state.pinnedEventIDs, [101])
        XCTAssertEqual(transport.putCalls[0].state.pinnedMarketIDs, [202])

        // Re-sending identical pins is a no-op (no duplicate PUT).
        await coordinator.updatePins(eventIDs: [101], marketIDs: [202])
        XCTAssertEqual(transport.putCalls.count, 1)

        // Adding a new pin triggers a PUT with updated sorted pins.
        await coordinator.updatePins(eventIDs: [101, 55], marketIDs: [202])
        XCTAssertEqual(transport.putCalls.count, 2)
        XCTAssertEqual(transport.putCalls[1].state.pinnedEventIDs, [55, 101])

        // Signing in claims the device once for that bearer.
        await coordinator.updateSession(bearer: "session-token-1")
        XCTAssertEqual(transport.claimCalls.count, 1)
        XCTAssertEqual(transport.claimCalls[0].bearer, "session-token-1")

        await coordinator.foregroundActivated()
        XCTAssertEqual(transport.claimCalls.count, 1)

        // Signing out clears claimed state; signing in again claims with the new bearer.
        await coordinator.updateSession(bearer: nil)
        await coordinator.updateSession(bearer: "session-token-2")
        XCTAssertEqual(transport.claimCalls.count, 2)
        XCTAssertEqual(transport.claimCalls[1].bearer, "session-token-2")
    }

    func testFailedPutRetriesOnForegroundActivation() async {
        let store = MemoryIdentityStore()
        let transport = MockPushDeviceTransport()
        transport.failNextPut = true
        let coordinator = LiveActivityPushStartCoordinator254A(
            identityStore: store,
            transport: transport,
            apnsEnv: "sandbox",
            osMajor: 18,
            appVersion: "1.0.8"
        )

        await coordinator.receiveStartToken(Data([0x01, 0x02]))
        XCTAssertEqual(transport.putCalls.count, 0)

        await coordinator.foregroundActivated()
        XCTAssertEqual(transport.putCalls.count, 1)
        XCTAssertEqual(transport.putCalls[0].state.laStartToken, "0102")
    }

    func testPushStartedActivityRegistersRotatesReconcilesConflictAndRevokesWithoutAccount() async {
        let store = MemoryIdentityStore()
        let transport = MockPushDeviceTransport()
        let coordinator = LiveActivityPushStartCoordinator254A(
            identityStore: store,
            transport: transport,
            apnsEnv: "production",
            osMajor: 18,
            appVersion: "1.0.8"
        )

        // Signed out: push-started activity ensures parent device row exists and registers update token.
        await coordinator.registerPushStartedActivityToken(
            id: "act-push-1",
            eventID: 4201,
            tokenData: Data([0xAA, 0xBB])
        )
        XCTAssertEqual(transport.putCalls.count, 1)
        XCTAssertEqual(transport.mutateCalls.count, 1)
        XCTAssertEqual(transport.mutateCalls[0].id, "act-push-1")
        XCTAssertEqual(transport.mutateCalls[0].token, "aabb")
        XCTAssertEqual(transport.mutateCalls[0].version, 0)
        XCTAssertTrue(coordinator.hasDeviceRegisteredActivity(eventID: 4201))

        // Token rotation hits a 409 conflict -> reads server version (3) and retries PUT with expected_version 3.
        transport.failNextMutateWithConflict = true
        await coordinator.registerPushStartedActivityToken(
            id: "act-push-1",
            eventID: 4201,
            tokenData: Data([0xCC, 0xDD])
        )
        XCTAssertEqual(transport.mutateCalls.count, 2)
        XCTAssertEqual(transport.mutateCalls[1].token, "ccdd")
        XCTAssertEqual(transport.mutateCalls[1].version, 3)

        // Ending the activity sends DELETE (token == nil) with version 4 and marks inactive.
        await coordinator.revokePushStartedActivity(id: "act-push-1", eventID: 4201)
        XCTAssertEqual(transport.mutateCalls.count, 3)
        XCTAssertNil(transport.mutateCalls[2].token)
        XCTAssertEqual(transport.mutateCalls[2].version, 4)
        XCTAssertFalse(coordinator.hasDeviceRegisteredActivity(eventID: 4201))
    }
}
#endif
