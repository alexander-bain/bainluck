#if os(iOS) && canImport(ActivityKit)
import XCTest
import UserNotifications
@testable import Bain_Luck

/// `#13261` Item 4 (Rows 11, 12 & 13) — notification choice & opens, Live Activity
/// start/stop/fail actions, and widget opens; strict `181-C` zero-emission gating
/// without `"Allow"`, and zero names, person IDs, or search text.
@MainActor
final class WidgetAndAlertTelemetry13261Tests: XCTestCase {
    private final class SpySink: TelemetrySink {
        var analyticsEnabled: [Bool] = []
        var crashlyticsEnabled: [Bool] = []
        var resets = 0

        func setAnalyticsCollectionEnabled(_ enabled: Bool) { analyticsEnabled.append(enabled) }
        func setCrashlyticsCollectionEnabled(_ enabled: Bool) { crashlyticsEnabled.append(enabled) }
        func resetAnalyticsData() { resets += 1 }
    }

    private final class FakeGameActivityService: GameActivityServing {
        var isEnabled = true
        var records: [GameActivityRecord] = []
        var requestFails = false

        func request(_ snapshot: GameActivitySnapshot, staleDate: Date) throws {
            if requestFails { throw NSError(domain: "TestActivity", code: 1) }
            records.append(GameActivityRecord(id: "la-\(snapshot.eventID)", eventID: snapshot.eventID, snapshot: snapshot))
        }

        func update(id: String, snapshot: GameActivitySnapshot, staleDate: Date) async {}

        func end(id: String, final: GameActivitySnapshot?) async {
            records.removeAll { $0.id == id }
        }
    }

    private var sink: SpySink!
    private var captured: [(name: String, params: [String: Any])] = []

    override func setUp() {
        super.setUp()
        sink = SpySink()
        captured = []
        TelemetryConsent.shared.resetForTests(sink: sink)
        TelemetryConsent.shared.initialize()
        AnalyticsService.eventEmitterForTests = { [weak self] name, params in
            self?.captured.append((name, params ?? [:]))
        }
    }

    override func tearDown() {
        AnalyticsService.eventEmitterForTests = nil
        TelemetryConsent.shared.resetForTests(sink: FirebaseTelemetrySink())
        sink = nil
        super.tearDown()
    }

    private func sampleSnapshot(eventID: Int = 15300999) -> GameActivitySnapshot {
        GameActivitySnapshot(
            eventID: eventID,
            homeTeam: "Miami Heat",
            awayTeam: "Boston Celtics",
            status: "live",
            homeScore: 88,
            awayScore: 84,
            homeProbability: 0.61,
            awayProbability: 0.39,
            sport: "basketball_nba",
            scoreObservedAt: Date(),
            probabilityObservedAt: Date()
        )!
    }

    // MARK: - 181-C: nothing is sent without "Allow"

    func testNothingSentWithoutAllowAcrossAllStatesAndRevocation() async throws {
        // 1. No choice yet (`nil`) is a denial.
        XCTAssertFalse(TelemetryConsent.shared.isGranted)
        await fireEveryRow11To13Path()
        XCTAssertTrue(captured.isEmpty, "must emit zero events before Allow")
        XCTAssertFalse(sink.analyticsEnabled.contains(true))

        // 2. Explicit decline (`.none`) must still emit zero events.
        TelemetryConsent.shared.set(.none)
        await fireEveryRow11To13Path()
        XCTAssertTrue(captured.isEmpty, "must emit zero events after Decline")

        // 3. Grant then revoke (`analytics` -> `none`): zero events post-revocation.
        TelemetryConsent.shared.set(.analytics)
        captured.removeAll()
        TelemetryConsent.shared.set(.none)
        await fireEveryRow11To13Path()
        XCTAssertTrue(captured.isEmpty, "must emit zero events after revocation")
    }

    private func fireEveryRow11To13Path() async {
        AnalyticsService.trackPushPermissionResult(granted: true, surface: "system_prompt")
        AnalyticsService.trackPushOpened(payloadId: "digest-20261120", surface: "digest", destinationType: "event")

        let service = FakeGameActivityService()
        let controller = GameActivityController(service: service, isForeground: { true })
        controller.start(snapshot: sampleSnapshot())
        await controller.stop(eventID: 15300999)

        let nav = NavigationCoordinator()
        if let url = URL(string: "bainluck://events/15300999?source=widget&widget_kind=live_games_small") {
            _ = nav.handleURL(url)
        }
    }

    // MARK: - Row 11: push_permission_result & push_opened

    func testPushPermissionResultAndNotificationOpenDescriptors() throws {
        TelemetryConsent.shared.set(.analytics)

        AnalyticsService.trackPushPermissionResult(granted: true, surface: "system_prompt")
        AnalyticsService.trackPushPermissionResult(granted: false, surface: "system_prompt")

        let permEvents = captured.filter { $0.name == "push_permission_result" }
        XCTAssertEqual(permEvents.count, 2)
        XCTAssertEqual(permEvents[0].params["outcome"] as? String, "granted")
        XCTAssertEqual(permEvents[0].params["surface"] as? String, "system_prompt")
        XCTAssertEqual(permEvents[1].params["outcome"] as? String, "denied")

        let digestOpen = try XCTUnwrap(
            NotificationManager.notificationOpenDescriptor(
                actionIdentifier: UNNotificationDefaultActionIdentifier,
                userInfo: ["payload_id": "digest-20261120", "url": "https://bainluck.com/futures/9001"]
            )
        )
        XCTAssertEqual(digestOpen.payloadId, "digest-20261120")
        XCTAssertEqual(digestOpen.surface, "digest")
        XCTAssertEqual(digestOpen.destinationType, "futures")

        let alertOpen = try XCTUnwrap(
            NotificationManager.notificationOpenDescriptor(
                actionIdentifier: UNNotificationDefaultActionIdentifier,
                userInfo: ["event_id": "15300999"]
            )
        )
        XCTAssertNil(alertOpen.payloadId)
        XCTAssertEqual(alertOpen.surface, "game_alert")
        XCTAssertEqual(alertOpen.destinationType, "event")

        let universalUrlOpen = try XCTUnwrap(
            NotificationManager.notificationOpenDescriptor(
                actionIdentifier: UNNotificationDefaultActionIdentifier,
                userInfo: ["url": "https://bainluck.com/events/42"]
            )
        )
        XCTAssertNil(universalUrlOpen.payloadId)
        XCTAssertEqual(universalUrlOpen.surface, "game_alert")
        XCTAssertEqual(universalUrlOpen.destinationType, "event")

        let customSchemeUrlOpen = try XCTUnwrap(
            NotificationManager.notificationOpenDescriptor(
                actionIdentifier: UNNotificationDefaultActionIdentifier,
                userInfo: ["url": "bainluck://events/42"]
            )
        )
        XCTAssertNil(customSchemeUrlOpen.payloadId)
        XCTAssertEqual(customSchemeUrlOpen.surface, "game_alert")
        XCTAssertEqual(customSchemeUrlOpen.destinationType, "event")

        AnalyticsService.trackPushOpened(
            payloadId: alertOpen.payloadId,
            surface: alertOpen.surface,
            destinationType: alertOpen.destinationType
        )
        let opens = captured.filter { $0.name == "push_opened" }
        XCTAssertEqual(opens.count, 1)
        XCTAssertNil(opens[0].params["payload_id"])
        XCTAssertEqual(opens[0].params["surface"] as? String, "game_alert")
        XCTAssertEqual(opens[0].params["destination_type"] as? String, "event")
    }

    // MARK: - Row 12: live_activity_action

    func testGameActivityControllerEmitsStartStopAndFailureWithZeroTeamOrPersonNames() async {
        TelemetryConsent.shared.set(.analytics)

        let service = FakeGameActivityService()
        let controller = GameActivityController(service: service, isForeground: { true })

        controller.start(snapshot: sampleSnapshot(eventID: 4411))
        await controller.stop(eventID: 4411)

        service.requestFails = true
        controller.start(snapshot: sampleSnapshot(eventID: 4412))

        let laEvents = captured.filter { $0.name == "live_activity_action" }
        XCTAssertEqual(laEvents.count, 3)

        XCTAssertEqual(laEvents[0].params["action"] as? String, "start")
        XCTAssertEqual(laEvents[0].params["event_id"] as? Int, 4411)
        XCTAssertEqual(laEvents[0].params["outcome"] as? String, "started")
        XCTAssertEqual(laEvents[0].params["surface"] as? String, "event_detail")
        XCTAssertNil(laEvents[0].params["home_team"])
        XCTAssertNil(laEvents[0].params["user_id"])

        XCTAssertEqual(laEvents[1].params["action"] as? String, "stop")
        XCTAssertEqual(laEvents[1].params["event_id"] as? Int, 4411)
        XCTAssertEqual(laEvents[1].params["outcome"] as? String, "stopped")

        XCTAssertEqual(laEvents[2].params["action"] as? String, "start")
        XCTAssertEqual(laEvents[2].params["event_id"] as? Int, 4412)
        XCTAssertEqual(laEvents[2].params["outcome"] as? String, "failed")
    }

    // MARK: - Row 13: widget_open

    func testNavigationCoordinatorEmitsWidgetOpenAndCollapsesUnknownWidgetKinds() throws {
        TelemetryConsent.shared.set(.analytics)
        let nav = NavigationCoordinator()

        let smallWidget = try XCTUnwrap(
            URL(string: "bainluck://events/15300999?source=widget&widget_kind=live_games_small")
        )
        XCTAssertTrue(nav.handleURL(smallWidget))

        let badKindWidget = try XCTUnwrap(
            URL(string: "bainluck://my-stuff?source=widget&widget_kind=JaneDoeSecretToken")
        )
        XCTAssertTrue(nav.handleURL(badKindWidget))

        let nonWidget = try XCTUnwrap(URL(string: "https://bainluck.com/events/15300999"))
        XCTAssertTrue(nav.handleURL(nonWidget))

        let widgetEvents = captured.filter { $0.name == "widget_open" }
        XCTAssertEqual(widgetEvents.count, 2, "only ?source=widget URLs emit widget_open")

        XCTAssertEqual(widgetEvents[0].params["widget_kind"] as? String, "live_games_small")
        XCTAssertEqual(widgetEvents[0].params["destination_type"] as? String, "event")
        XCTAssertEqual(widgetEvents[0].params["surface"] as? String, "widget")
        XCTAssertNil(widgetEvents[0].params["url"])

        XCTAssertEqual(widgetEvents[1].params["widget_kind"] as? String, "unknown")
        XCTAssertEqual(widgetEvents[1].params["destination_type"] as? String, "my_stuff")
    }
}
#endif
