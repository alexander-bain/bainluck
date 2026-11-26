import XCTest
@testable import Bain_Luck

/// `#13261` Rows 9, 10 & 14 — Set hub interactions, iPhone Game page + My Stuff pin
/// presence, and Watch Pin/Matchup dual-opt-in telemetry strictly behind `"Allow"` (`181-C`).
@MainActor
final class FirstWeekSurfaceAndWatchEvents13261Tests: XCTestCase {
    private final class SpySink: TelemetrySink {
        var analyticsEnabled: [Bool] = []
        var crashlyticsEnabled: [Bool] = []
        var resets = 0

        func setAnalyticsCollectionEnabled(_ enabled: Bool) { analyticsEnabled.append(enabled) }
        func setCrashlyticsCollectionEnabled(_ enabled: Bool) { crashlyticsEnabled.append(enabled) }
        func resetAnalyticsData() { resets += 1 }
    }

    private nonisolated final class MockEmptyMyStuffClient: MyStuffFeedProviding, @unchecked Sendable {
        private static func decoder() -> JSONDecoder {
            let d = JSONDecoder()
            d.keyDecodingStrategy = .convertFromSnakeCase
            return d
        }

        nonisolated func fetchMyTeamsFeed() async throws -> FeedResponse {
            try Self.decoder().decode(
                FeedResponse.self,
                from: Data(#"{"items":[],"total":0,"limit":20,"offset":0,"has_more":false}"#.utf8)
            )
        }

        nonisolated func fetchMyTeamFuturesSection(limit: Int) async throws -> TeamFuturesResponse {
            try Self.decoder().decode(
                TeamFuturesResponse.self,
                from: Data(#"{"items":[],"team_ids":[],"total_count":0}"#.utf8)
            )
        }

        nonisolated func currentMyStuffPrincipal() async -> String {
            "user:test"
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

    // MARK: - 181-C: Nothing emitted without "Allow"

    func testNothingSentWithoutAllowForRows9_10_14() throws {
        XCTAssertFalse(TelemetryConsent.shared.isGranted)
        fireRows9And10()
        XCTAssertTrue(captured.isEmpty, "must emit zero events before Allow")

        TelemetryConsent.shared.set(.none)
        fireRows9And10()
        XCTAssertTrue(captured.isEmpty, "must emit zero events after explicit refusal")
        XCTAssertFalse(sink.analyticsEnabled.contains(true))

        // Watch dual-opt-in also refuses when phone grant is missing or revoked.
        let now = Date(timeIntervalSince1970: 1_800_000_000)
        var buffer = WatchTelemetryBuffer(watchEpoch: nil, phoneGrant: nil, records: [])
        buffer.append(
            WatchTelemetryRecord(recordedAt: now, kind: .action, surface: .pinsHome, action: .openPinnedGame),
            now: now
        )
        XCTAssertTrue(buffer.records.isEmpty, "Watch buffer must drop events when Watch toggle is off")

        let fakeEpoch = UUID()
        let packet = try JSONEncoder().encode(
            WatchTelemetryBatch(
                schema: 1,
                phoneEpoch: fakeEpoch,
                watchEpoch: UUID(),
                records: [
                    WatchTelemetryRecord(recordedAt: now, kind: .action, surface: .pinsHome, action: .openPinnedGame)
                ]
            )
        )
        XCTAssertTrue(
            WatchTelemetryIngress.accept(packet, phoneEpoch: nil, now: now, seen: []).records.isEmpty,
            "Phone ingress must refuse Watch events when phone Allow is off"
        )
    }

    // MARK: - Row 9: Set hubs (collection_hub_action)

    func testCollectionHubActionEmitsSanitizedSlugAndClosedKindWhenAllowed() throws {
        TelemetryConsent.shared.set(.analytics)

        AnalyticsService.trackCollectionHubAction(
            slug: "Machinery-Oscars_2027?user=Alex&email=a@b.com",
            actionKind: "open_market",
            itemType: "market"
        )
        AnalyticsService.trackCollectionHubAction(
            slug: "academy-awards-best-picture",
            actionKind: "open_child_collection",
            itemType: "collection"
        )

        XCTAssertEqual(captured.count, 2)
        XCTAssertEqual(captured[0].name, "collection_hub_action")
        XCTAssertEqual(captured[0].params["slug"] as? String, "machinery-oscars_2027")
        XCTAssertEqual(captured[0].params["action_kind"] as? String, "open_market")
        XCTAssertEqual(captured[0].params["item_type"] as? String, "market")
        XCTAssertEqual(captured[0].params["surface"] as? String, "collection_hub")

        XCTAssertEqual(captured[1].name, "collection_hub_action")
        XCTAssertEqual(captured[1].params["slug"] as? String, "academy-awards-best-picture")
        XCTAssertEqual(captured[1].params["action_kind"] as? String, "open_child_collection")
        XCTAssertEqual(captured[1].params["item_type"] as? String, "collection")
    }

    // MARK: - Row 10: Game page interactions & My Stuff has_pins / state

    func testGamePageActionAndMyStuffLoadStateEmitWhenAllowed() async throws {
        TelemetryConsent.shared.set(.analytics)

        AnalyticsService.trackGamePageAction(actionKind: "expand", section: "sources", sport: "americanfootball_nfl")
        AnalyticsService.trackGamePageAction(actionKind: "open", section: "models", sport: "basketball_nba")
        AnalyticsService.trackGamePageAction(actionKind: "filter", section: "props", sport: "basketball_nba")

        let vm = MyStuffViewModel(
            client: MockEmptyMyStuffClient(),
            autoRefreshEnabled: false,
            requiredAttempts: 1
        )
        vm.setHasPins(true)
        await vm.load()

        let vmEmpty = MyStuffViewModel(
            client: MockEmptyMyStuffClient(),
            autoRefreshEnabled: false,
            requiredAttempts: 1
        )
        vmEmpty.setHasPins(false)
        await vmEmpty.load()

        let gameActions = captured.filter { $0.name == "game_page_action" }
        XCTAssertEqual(gameActions.count, 3)
        XCTAssertEqual(gameActions[0].params["section"] as? String, "sources")
        XCTAssertEqual(gameActions[0].params["action_kind"] as? String, "expand")
        XCTAssertEqual(gameActions[1].params["section"] as? String, "models")
        XCTAssertEqual(gameActions[2].params["section"] as? String, "props")
        XCTAssertEqual(gameActions[2].params["action_kind"] as? String, "filter")

        let myStuffLoads = captured.filter {
            $0.name == "my_stuff_load" && ($0.params["stage"] as? String) == "required_data_ready"
        }
        XCTAssertEqual(myStuffLoads.count, 2)
        XCTAssertEqual(myStuffLoads[0].params["has_pins"] as? Bool, true)
        XCTAssertEqual(myStuffLoads[0].params["state"] as? String, "populated")
        XCTAssertEqual(myStuffLoads[1].params["has_pins"] as? Bool, false)
        XCTAssertEqual(myStuffLoads[1].params["state"] as? String, "empty")
    }

    // MARK: - Row 14: Watch Pin & Matchup telemetry behind dual opt-in

    func testWatchPinAndMatchupTelemetryRequiresDualConsentAndSanitizes() throws {
        let now = Date(timeIntervalSince1970: 1_800_000_000)
        TelemetryConsent.shared.set(.analytics)
        let phoneEpoch = try XCTUnwrap(TelemetryConsent.shared.analyticsAuthorizationEpoch)

        var buffer = WatchTelemetryBuffer(
            watchEpoch: nil,
            phoneGrant: WatchTelemetryGrant(epoch: phoneEpoch, validUntil: now.addingTimeInterval(3600)),
            records: []
        )
        buffer.append(
            WatchTelemetryRecord(recordedAt: now, kind: .action, surface: .pinsHome, action: .openPinnedGame),
            now: now
        )
        XCTAssertTrue(buffer.records.isEmpty, "Phone grant alone must not collect Watch diagnostics")

        buffer.setWatchConsent(true)
        buffer.setPhoneGrant(WatchTelemetryGrant(epoch: phoneEpoch, validUntil: now.addingTimeInterval(3600)), now: now)
        let actions: [(WatchTelemetrySurface, WatchTelemetryAction)] = [
            (.pinsHome, .openPinnedGame),
            (.pinsHome, .openPinnedMarket),
            (.pinsHome, .refreshPins),
            (.pinnedMarket, .chooseOutcome),
            (.matchupGame, .clearSelection),
        ]
        for (surface, action) in actions {
            buffer.append(WatchTelemetryRecord(recordedAt: now, kind: .action, surface: surface, action: action), now: now)
        }
        XCTAssertEqual(buffer.records.count, 5)

        let batch = try XCTUnwrap(buffer.batch(now: now))
        let wire = try JSONEncoder().encode(batch)
        let accepted = WatchTelemetryIngress.accept(wire, phoneEpoch: phoneEpoch, now: now, seen: [])
        XCTAssertEqual(accepted.records.count, 5)

        for record in accepted.records {
            let params = try XCTUnwrap(AnalyticsPrivacy.sanitize(event: record.kind.rawValue, parameters: record.analyticsParameters))
            XCTAssertEqual(params["device_class"] as? String, "watch")
            XCTAssertNil(params["id"])
        }
    }

    func testForbiddenKeysStrippedFromRows9_10_14() throws {
        let params = try XCTUnwrap(
            AnalyticsPrivacy.sanitize(
                event: "collection_hub_action",
                parameters: [
                    "slug": "oscars-2027",
                    "action_kind": "open_market",
                    "name": "Secret User Name",
                    "url": "https://bainluck.com/collections/oscars",
                    "query": "raw query leak",
                ]
            )
        )
        XCTAssertEqual(params["slug"] as? String, "oscars-2027")
        XCTAssertNil(params["name"])
        XCTAssertNil(params["url"])
        XCTAssertNil(params["query"])

        let unsafeTokenSlug = try XCTUnwrap(
            AnalyticsPrivacy.sanitize(
                event: "collection_hub_action",
                parameters: [
                    "slug": "abcdefghijklmnopqrstuvwxyz123456",
                    "action_kind": "open_market",
                ]
            )
        )
        XCTAssertNil(unsafeTokenSlug["slug"])
    }

    private func fireRows9And10() {
        AnalyticsService.trackCollectionHubAction(slug: "oscars-2027", actionKind: "open_market", itemType: "market")
        AnalyticsService.trackGamePageAction(actionKind: "expand", section: "sources", sport: "basketball_nba")
        AnalyticsService.trackMyStuffStage(
            MyStuffLoadStage(
                kind: .requiredDataReady,
                authReadyMs: 1,
                networkMs: 10,
                requiredDataReadyMs: 12,
                itemCount: 0,
                cacheOutcome: "miss",
                cacheAgeSeconds: -1,
                outcomeClass: .emptySuccess,
                hasPins: true
            )
        )
    }
}
