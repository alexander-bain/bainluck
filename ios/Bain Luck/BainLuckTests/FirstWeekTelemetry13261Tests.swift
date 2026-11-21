import XCTest
@testable import Bain_Luck

/// `#13261` Item 3 (Rows 6, 7 & 8) — iPhone first-week measurement events,
/// strict `181-C` zero-emission gating without `"Allow"`, and PII/name/query redaction.
@MainActor
final class FirstWeekTelemetry13261Tests: XCTestCase {
    private final class SpySink: TelemetrySink {
        var analyticsEnabled: [Bool] = []
        var crashlyticsEnabled: [Bool] = []
        var resets = 0

        func setAnalyticsCollectionEnabled(_ enabled: Bool) { analyticsEnabled.append(enabled) }
        func setCrashlyticsCollectionEnabled(_ enabled: Bool) { crashlyticsEnabled.append(enabled) }
        func resetAnalyticsData() { resets += 1 }
    }

    private var sink: SpySink!
    private var captured: [(name: String, params: [String: Any])] = []
    private var defaults: UserDefaults!
    private var suiteName: String!

    override func setUp() {
        super.setUp()
        sink = SpySink()
        captured = []
        suiteName = "FirstWeekTelemetry13261Tests.\(UUID().uuidString)"
        defaults = UserDefaults(suiteName: suiteName)

        TelemetryConsent.shared.resetForTests(sink: sink)
        TelemetryConsent.shared.initialize()
        SessionOpenTracker13261.shared.resetForTests()
        AnalyticsService.eventEmitterForTests = { [weak self] name, params in
            self?.captured.append((name, params ?? [:]))
        }
    }

    override func tearDown() {
        AnalyticsService.eventEmitterForTests = nil
        SessionOpenTracker13261.shared.resetForTests()
        TelemetryConsent.shared.resetForTests(sink: FirebaseTelemetrySink())
        defaults.removePersistentDomain(forName: suiteName)
        defaults = nil
        sink = nil
        super.tearDown()
    }

    // MARK: - 181-C: nothing is sent without "Allow"

    func testNothingSentWithoutAllowAcrossAllStatesAndRevocation() throws {
        // 1. No choice yet (`nil`) is a denial.
        XCTAssertFalse(TelemetryConsent.shared.isGranted)
        fireEveryRow6To8Path()
        XCTAssertTrue(captured.isEmpty, "must emit zero events before Allow")
        XCTAssertFalse(sink.analyticsEnabled.contains(true))

        // 2. Explicit decline (`.none`) must still emit zero events.
        TelemetryConsent.shared.set(.none)
        XCTAssertFalse(TelemetryConsent.shared.isGranted)
        fireEveryRow6To8Path()
        XCTAssertTrue(captured.isEmpty, "must emit zero events after Decline")
        XCTAssertFalse(sink.analyticsEnabled.contains(true))

        // 3. Grant then revoke (`analytics` -> `none`): nothing sent post-revocation.
        TelemetryConsent.shared.set(.analytics)
        XCTAssertTrue(TelemetryConsent.shared.isGranted)
        captured.removeAll()
        TelemetryConsent.shared.set(.none)
        fireEveryRow6To8Path()
        XCTAssertTrue(captured.isEmpty, "must emit zero events after revocation")
    }

    private func fireEveryRow6To8Path() {
        AnalyticsService.trackPinItem(action: "pin", itemType: "event", itemId: 15300001, surface: "iphone")
        AnalyticsService.trackFollowTeam(action: "follow", sport: "basketball_nba", relationType: "follow", surface: "onboarding")
        AnalyticsService.trackSearchResultClick(query: "Boston Celtics", resultType: "team", resultId: "42", position: 0)

        let manager = PinManager(defaults: defaults)
        manager.togglePin(type: "event", id: 15300001)

        SessionOpenTracker13261.shared.recordLaunch(sessionNumber: 1)
        let nav = NavigationCoordinator()
        if let url = URL(string: "https://bainluck.com/events/15300001?source=share&medium=share_sheet") {
            _ = nav.handleURL(url)
        }
    }

    // MARK: - Row 6: pin_item & follow_team

    func testPinManagerEmitsPinItemOnConfirmedLocalAndAuthenticatedSaveButNotOnRollback() async throws {
        TelemetryConsent.shared.set(.analytics)

        // Local guest pin + unpin
        let guestManager = PinManager(defaults: defaults)
        guestManager.togglePin(type: "event", id: 901)
        guestManager.togglePin(type: "event", id: 901)

        let pinEvents = captured.filter { $0.name == "pin_item" }
        XCTAssertEqual(pinEvents.count, 2)
        XCTAssertEqual(pinEvents[0].params["action"] as? String, "pin")
        XCTAssertEqual(pinEvents[0].params["item_type"] as? String, "event")
        XCTAssertEqual(pinEvents[0].params["item_id"] as? String, "901")
        XCTAssertNotNil(pinEvents[0].params["surface"])
        XCTAssertEqual(pinEvents[1].params["action"] as? String, "unpin")

        // Authenticated failure must roll back AND emit zero `pin_item`
        captured.removeAll()
        let failingManager = PinManager(
            defaults: defaults,
            initialBinding: PinAccountBinding(userID: "77", authenticated: true),
            serverLoad: { PinsResponse(events: [], futures: []) }
        ) { _, _, _ in
            throw URLError(.notConnectedToInternet)
        }
        await failingManager.loadPins()
        let failTask = try XCTUnwrap(failingManager.togglePin(type: "future", id: 505))
        await failTask.value
        XCTAssertTrue(captured.filter { $0.name == "pin_item" }.isEmpty)

        // Authenticated success emits `"pin"`
        let okManager = PinManager(
            defaults: defaults,
            initialBinding: PinAccountBinding(userID: "78", authenticated: true),
            serverLoad: { PinsResponse(events: [], futures: []) }
        ) { _, _, _ in }
        await okManager.loadPins()
        let okTask = try XCTUnwrap(okManager.togglePin(type: "future", id: 506))
        await okTask.value
        let okEvents = captured.filter { $0.name == "pin_item" }
        XCTAssertEqual(okEvents.count, 1)
        if let ok = okEvents.first {
            XCTAssertEqual(ok.params["item_type"] as? String, "future")
            XCTAssertEqual(ok.params["item_id"] as? String, "506")
        }
    }

    func testFollowTeamEmitsCategoryOnlyWithZeroNamesOrPersonIds() {
        TelemetryConsent.shared.set(.analytics)

        AnalyticsService.trackFollowTeam(
            action: "follow",
            sport: "americanfootball_nfl",
            relationType: "alma_mater",
            surface: "onboarding"
        )
        AnalyticsService.trackFollowTeam(
            action: "unfollow",
            sport: nil,
            relationType: "Alice Smith Secret",
            surface: "preferences"
        )

        let events = captured.filter { $0.name == "follow_team" }
        XCTAssertEqual(events.count, 2)
        XCTAssertEqual(events[0].params["action"] as? String, "follow")
        XCTAssertEqual(events[0].params["sport"] as? String, "americanfootball_nfl")
        XCTAssertEqual(events[0].params["relation_type"] as? String, "alma_mater")
        XCTAssertEqual(events[0].params["surface"] as? String, "onboarding")
        XCTAssertNil(events[0].params["team_name"])
        XCTAssertNil(events[0].params["user_id"])

        XCTAssertEqual(events[1].params["action"] as? String, "unfollow")
        XCTAssertEqual(events[1].params["sport"] as? String, "unknown")
        XCTAssertEqual(events[1].params["relation_type"] as? String, "unknown")
    }

    // MARK: - Row 7: session_open & shared_link_open

    func testDayOneSessionOpenAndArrivalHoldUntilAllowThenFlushOnce() throws {
        // Launch + universal link arrive BEFORE consent is granted.
        SessionOpenTracker13261.shared.recordLaunch(sessionNumber: 1)
        let nav = NavigationCoordinator()
        XCTAssertTrue(
            nav.handleURL(
                try XCTUnwrap(URL(string: "https://bainluck.com/events/15300001?utm_source=share&utm_medium=share_sheet"))
            )
        )
        // Must wait quietly while prompt is open.
        XCTAssertTrue(captured.isEmpty)

        // User taps Allow -> flushes shared_link_open + Day-1 session_open exactly once.
        TelemetryConsent.shared.set(.analytics)
        SessionOpenTracker13261.shared.handleConsentChange()

        XCTAssertEqual(captured.map(\.name), ["shared_link_open", "session_open"])
        let link = captured[0].params
        XCTAssertEqual(link["entry_type"] as? String, "universal_link")
        XCTAssertEqual(link["destination_type"] as? String, "event")
        XCTAssertEqual(link["source"] as? String, "share")
        XCTAssertEqual(link["medium"] as? String, "share_sheet")
        XCTAssertNil(link["url"])

        let session = captured[1].params
        XCTAssertEqual(session["is_first_session"] as? Bool, true)
        XCTAssertEqual(session["session_number"] as? Int, 1)
        XCTAssertEqual(session["entry_type"] as? String, "universal_link")
        XCTAssertEqual(session["first_screen"] as? String, "event_detail")

        let colDescriptor = NavigationCoordinator.linkDestinationDescriptor(for: ["collections", "nfl-2026"])
        XCTAssertEqual(colDescriptor.destinationType, "collection")
        XCTAssertEqual(colDescriptor.firstScreen, "collection_hub")

        // Repeated flush does not duplicate session_open.
        SessionOpenTracker13261.shared.flushIfConsented()
        XCTAssertEqual(captured.filter { $0.name == "session_open" }.count, 1)
    }

    func testSharedLinkClassifierCollapsesUnknownParamsAndExcludesWidgets() throws {
        let custom = try XCTUnwrap(URL(string: "bainluck://events/42?utm_source=alice@example.com&utm_medium=custom_text"))
        let classified = try XCTUnwrap(
            FirstWeekTelemetry13261.classifyArrival(
                url: custom,
                destinationType: "event",
                firstScreen: "event_detail"
            )
        )
        XCTAssertEqual(classified.entryType, "custom_scheme")
        XCTAssertEqual(classified.source, "unknown")
        XCTAssertEqual(classified.medium, "unknown")

        // Widget deep links stay separate for row 13 (`widget_open`), never `shared_link_open`.
        let widgetURL = try XCTUnwrap(URL(string: "bainluck://events/42?source=widget&widget_kind=live_games_single"))
        XCTAssertNil(
            FirstWeekTelemetry13261.classifyArrival(
                url: widgetURL,
                destinationType: "event",
                firstScreen: "event_detail"
            )
        )
    }

    // MARK: - Row 8: search_result_click

    func testSearchResultClickDropsRawQueryTextAndUsesHashedOrOpaqueIds() {
        TelemetryConsent.shared.set(.analytics)

        let rawQuery = "Jane Doe Lakers user@example.com"
        let hashedTournamentId = FirstWeekTelemetry13261.hashedResultId("us-open-2026")
        AnalyticsService.trackSearchResultClick(
            query: rawQuery,
            resultType: "tournament",
            resultId: hashedTournamentId,
            position: 0
        )

        let clicks = captured.filter { $0.name == "search_result_click" }
        XCTAssertEqual(clicks.count, 1)
        let params = clicks[0].params
        XCTAssertNil(params["query"])
        XCTAssertNil(params["search_term"])
        XCTAssertEqual(params["query_hash"] as? String, AnalyticsPrivacy.hashQuery(rawQuery))
        XCTAssertEqual(params["query_length"] as? Int, rawQuery.utf16.count)
        XCTAssertEqual(params["query_word_count"] as? Int, 4)
        XCTAssertEqual(params["result_type"] as? String, "tournament")
        XCTAssertEqual(params["result_id"] as? String, hashedTournamentId)
        XCTAssertFalse((params["result_id"] as? String ?? "").contains("us-open"))
        XCTAssertEqual(params["position"] as? Int, 0)
    }
}
