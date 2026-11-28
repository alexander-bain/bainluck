#if os(iOS) && canImport(ActivityKit)
import Foundation
import XCTest
@testable import Bain_Luck

@MainActor
final class GameAlertsDeviceSync13082Tests: XCTestCase {
    private final class MemoryIdentityStore: DeviceIdentityStoring254A, @unchecked Sendable {
        let fixed = DeviceIdentity254A(
            deviceID: UUID(uuidString: "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee")!,
            secret: String(repeating: "b", count: 64)
        )
        func loadOrCreate() -> DeviceIdentity254A { fixed }
    }

    @MainActor
    private final class MockPushDeviceTransport: PushDeviceTransport254A {
        struct PutCall: Equatable {
            let identity: DeviceIdentity254A
            let state: PushDeviceState254A
        }

        var putCalls: [PutCall] = []
        var claimCalls: [(DeviceIdentity254A, String)] = []

        func putDevice(identity: DeviceIdentity254A, state: PushDeviceState254A) async throws {
            putCalls.append(PutCall(identity: identity, state: state))
        }

        func claimDevice(identity: DeviceIdentity254A, bearer: String) async throws {
            claimCalls.append((identity, bearer))
        }

        func readActivityRegistration(
            id: String,
            identity: DeviceIdentity254A
        ) async throws -> GameActivityRegistrationMetadata {
            GameActivityRegistrationMetadata(activityID: id, eventID: 1, version: 1, isActive: true)
        }

        func mutateActivityRegistration(
            id: String,
            eventID: Int,
            token: String?,
            version: Int,
            mutationID: UUID,
            identity: DeviceIdentity254A
        ) async throws -> GameActivityRegistrationMetadata {
            GameActivityRegistrationMetadata(activityID: id, eventID: eventID, version: version + 1, isActive: token != nil)
        }
    }

    private func makePreference() -> (GameAlertsPreference13083, NotificationCenter, UserDefaults, String) {
        let suiteName = "test.gameAlerts13082.\(UUID().uuidString)"
        let defaults = UserDefaults(suiteName: suiteName)!
        let center = NotificationCenter()
        let pref = GameAlertsPreference13083(defaults: defaults, center: center)
        return (pref, center, defaults, suiteName)
    }

    func testWireJSONCarriesLowercaseNotificationTokenAndExplicitNullOnClear() throws {
        let withToken = PushDeviceState254A(
            platform: "ios",
            apnsEnv: "production",
            notificationToken: String(repeating: "AB", count: 6),
            laStartToken: nil,
            osMajor: 26,
            appVersion: "1.0.8",
            pinnedEventIDs: [15345678],
            pinnedMarketIDs: [70709343]
        )
        let dataWith = try JSONEncoder().encode(withToken)
        let jsonWith = try XCTUnwrap(JSONSerialization.jsonObject(with: dataWith) as? [String: Any])
        XCTAssertEqual(Set(jsonWith.keys), [
            "platform", "apns_env", "notification_token", "la_start_token",
            "os_major", "app_version", "pinned_event_ids", "pinned_market_ids",
        ])
        XCTAssertEqual(jsonWith["notification_token"] as? String, String(repeating: "ab", count: 6))
        XCTAssertTrue(jsonWith["la_start_token"] is NSNull)

        let cleared = PushDeviceState254A(
            platform: "ios",
            apnsEnv: "production",
            notificationToken: nil,
            laStartToken: "fedcba",
            osMajor: 26,
            appVersion: "1.0.8",
            pinnedEventIDs: [15345678],
            pinnedMarketIDs: []
        )
        let dataCleared = try JSONEncoder().encode(cleared)
        let jsonCleared = try XCTUnwrap(JSONSerialization.jsonObject(with: dataCleared) as? [String: Any])
        XCTAssertTrue(jsonCleared["notification_token"] is NSNull)
        XCTAssertEqual(jsonCleared["la_start_token"] as? String, "fedcba")
    }

    func testNotificationTokenSyncsOnlyWhenEnabledWithoutAccountOrStartTokenAndClearsImmediatelyOnDisable() async {
        let (pref, center, defaults, suiteName) = makePreference()
        defer { defaults.removePersistentDomain(forName: suiteName) }

        let store = MemoryIdentityStore()
        let transport = MockPushDeviceTransport()
        let coordinator = LiveActivityPushStartCoordinator254A(
            identityStore: store,
            transport: transport,
            gameAlertsPreference: pref,
            preferenceCenter: center,
            apnsEnv: "production",
            osMajor: 26,
            appVersion: "1.0.8"
        )
        coordinator.start()

        // Signed out, no la_start_token, Game alerts OFF: receiving raw APNs token does not PUT.
        await coordinator.updatePins(eventIDs: [15345678], marketIDs: [])
        await coordinator.receiveNotificationToken(Data([0xAA, 0xBB, 0xCC, 0xDD]))
        XCTAssertEqual(transport.putCalls.count, 0)

        // Enabling Game alerts posts notification and immediately PUTs `notification_token` without account or la_start_token.
        pref.setEnabled(true)
        await coordinator.refreshGameAlertsPreference()
        XCTAssertGreaterThanOrEqual(transport.putCalls.count, 1)
        let lastEnabled = transport.putCalls.last!.state
        XCTAssertEqual(lastEnabled.notificationToken, "aabbccdd")
        XCTAssertNil(lastEnabled.laStartToken)
        XCTAssertEqual(lastEnabled.pinnedEventIDs, [15345678])
        XCTAssertEqual(transport.claimCalls.count, 0)

        // Turning Game alerts OFF immediately clears `notification_token` to nil via PUT while keeping pins intact.
        let countBeforeDisable = transport.putCalls.count
        pref.setEnabled(false)
        await coordinator.refreshGameAlertsPreference()
        XCTAssertGreaterThanOrEqual(transport.putCalls.count, countBeforeDisable + 1)
        let lastDisabled = transport.putCalls.last!.state
        XCTAssertNil(lastDisabled.notificationToken)
        XCTAssertEqual(lastDisabled.pinnedEventIDs, [15345678])

        // Re-enabling restores the raw token cleanly without re-registering APNs.
        let countBeforeReenable = transport.putCalls.count
        pref.setEnabled(true)
        await coordinator.refreshGameAlertsPreference()
        XCTAssertGreaterThanOrEqual(transport.putCalls.count, countBeforeReenable + 1)
        XCTAssertEqual(transport.putCalls.last?.state.notificationToken, "aabbccdd")
    }

    func testGameAlertPushTapRoutesEventAndDismissesModalsBeforeNavigate() async {
        // Speed #13088 GameAlertPush integer `event_id` payload
        let payload: [AnyHashable: Any] = [
            "event_id": 15345678,
            "trigger_kind": "final",
        ]
        let destination = NotificationManager.notificationDestination(
            actionIdentifier: "com.apple.UNNotificationDefaultActionIdentifier",
            userInfo: payload
        )
        XCTAssertEqual(destination, .event(id: 15345678))

        // 1. Primary path: canonical link handed off through IntentRouteHandoff10873 (closes sheets via IntentRouteCloser10873).
        var handedOffURL: URL?
        NotificationManager.routeDestinationOnIOS(
            destination,
            navCoordinator: nil,
            closePresentations: { _ in XCTFail("Should use handoff path first for event URLs") },
            handoff: { url in
                handedOffURL = url
                return true
            }
        )
        XCTAssertEqual(handedOffURL?.absoluteString, "bainluck://events/15345678")

        // 2. Direct coordinator fallback path: closes open presentations first, then navigates to event detail on feed tab.
        let nav = NavigationCoordinator()
        var dismissedModals = false
        NotificationManager.routeDestinationOnIOS(
            destination,
            navCoordinator: nav,
            closePresentations: { route in
                dismissedModals = true
                route()
            },
            handoff: { _ in false }
        )
        XCTAssertTrue(dismissedModals)
        XCTAssertEqual(nav.selectedTab, .feed)
        try? await Task.sleep(for: .milliseconds(160))
        XCTAssertEqual(nav.pendingRoute, .eventDetail(id: 15345678))
    }

    func testMainAppUsesStandardNotificationsOnlyAndNoTimeSensitiveEntitlement() throws {
        let entitlementsURL = URL(fileURLWithPath: #filePath)
            .deletingLastPathComponent()
            .deletingLastPathComponent()
            .appendingPathComponent("Bain Luck/Bain Luck.entitlements")
        let xml = try String(contentsOf: entitlementsURL, encoding: .utf8)
        XCTAssertTrue(xml.contains("aps-environment"), "Main iOS target must keep standard aps-environment")
        XCTAssertFalse(
            xml.contains("com.apple.developer.usernotifications.time-sensitive"),
            "Ruling 261: A forbids Time Sensitive entitlement"
        )
    }
}
#endif
