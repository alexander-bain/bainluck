import XCTest
@testable import Bain_Luck

final class WatchPins12640Tests: XCTestCase {

    func testWireRoundTripPreservesOrderOutcomeIDAndRejectsInvalid() throws {
        let items: [WatchPinWireItem12640] = [
            WatchPinWireItem12640(kind: .event, id: 14780578),
            WatchPinWireItem12640(kind: .future, id: 69976810, outcomeId: 262830759),
            WatchPinWireItem12640(kind: .event, id: 14780578), // duplicate dropped
            WatchPinWireItem12640(kind: .event, id: 0), // invalid id dropped
            WatchPinWireItem12640(kind: .future, id: 500, outcomeId: -1) // invalid outcome_id dropped
        ]
        let data = WatchPinsWire12640.encode(items)
        let rawJSON = try XCTUnwrap(String(data: data, encoding: .utf8))
        XCTAssertTrue(rawJSON.contains("\"outcome_id\":262830759"))

        let decoded = try XCTUnwrap(WatchPinsWire12640.decode(data))
        XCTAssertEqual(decoded, [
            WatchPinWireItem12640(kind: .event, id: 14780578),
            WatchPinWireItem12640(kind: .future, id: 69976810, outcomeId: 262830759)
        ])
    }

    @MainActor
    func testPinManagerPreservesPinOrderAndClearsAccountPinsOnSignOut() async throws {
        let suiteName = "WatchPins12640Tests.\(UUID().uuidString)"
        let defaults = try XCTUnwrap(UserDefaults(suiteName: suiteName))
        defer { defaults.removePersistentDomain(forName: suiteName) }

        let manager = PinManager(
            defaults: defaults,
            allowLegacyGuestPins: false,
            initialBinding: PinAccountBinding(userID: "user-42", authenticated: true),
            serverLoad: {
                PinsResponse(events: [303, 101], futures: [888, 777])
            },
            serverSync: { _, _, _ in }
        )

        await manager.loadPins()
        XCTAssertEqual(manager.watchPinItems12640, [
            WatchPinWireItem12640(kind: .event, id: 303),
            WatchPinWireItem12640(kind: .event, id: 101),
            WatchPinWireItem12640(kind: .future, id: 888),
            WatchPinWireItem12640(kind: .future, id: 777)
        ])

        let addTask = manager.togglePin(type: "future", id: 999)
        await addTask?.value
        XCTAssertEqual(manager.orderedFuturesIDs, [888, 777, 999])

        // Signing out switches to guest scope (empty), so user-42's pins never outlive sign-out.
        manager.bindAccount(PinAccountBinding(userID: nil, authenticated: false))
        XCTAssertEqual(manager.watchPinItems12640, [])
    }

    func testFourBucketOrderingAndProbabilityAdmission() {
        let base = Date(timeIntervalSince1970: 1_794_500_000)
        let wire: [WatchPinWireItem12640] = [
            WatchPinWireItem12640(kind: .event, id: 10),   // final (older)
            WatchPinWireItem12640(kind: .future, id: 201), // market #1 in pin order
            WatchPinWireItem12640(kind: .event, id: 20),   // upcoming (later: +3d)
            WatchPinWireItem12640(kind: .event, id: 30),   // upcoming NO probability -> dropped!
            WatchPinWireItem12640(kind: .future, id: 202), // market NO priced outcomes -> dropped!
            WatchPinWireItem12640(kind: .future, id: 203), // market #2 in pin order
            WatchPinWireItem12640(kind: .event, id: 40),   // live game
            WatchPinWireItem12640(kind: .event, id: 50),   // upcoming (sooner: +4h)
            WatchPinWireItem12640(kind: .event, id: 60),   // final (newer)
            WatchPinWireItem12640(kind: .event, id: 70)    // final missing score -> dropped!
        ]

        let events: [Int: WatchPinEventSummary12640] = [
            10: WatchPinEventSummary12640(id: 10, isLive: false, isFinal: true, showsForecast: false, homeRenderedPercent: nil, homeScore: 98, awayScore: 95, commenceTime: base.addingTimeInterval(-10_000), scoreObservedAt: base.addingTimeInterval(-3_000)),
            20: WatchPinEventSummary12640(id: 20, isLive: false, isFinal: false, showsForecast: true, homeRenderedPercent: 58, homeScore: nil, awayScore: nil, commenceTime: base.addingTimeInterval(3 * 86_400), scoreObservedAt: nil),
            30: WatchPinEventSummary12640(id: 30, isLive: false, isFinal: false, showsForecast: true, homeRenderedPercent: nil, homeScore: nil, awayScore: nil, commenceTime: base.addingTimeInterval(1_800), scoreObservedAt: nil),
            40: WatchPinEventSummary12640(id: 40, isLive: true, isFinal: false, showsForecast: true, homeRenderedPercent: 64, homeScore: 4, awayScore: 2, commenceTime: base.addingTimeInterval(-3_600), scoreObservedAt: base),
            50: WatchPinEventSummary12640(id: 50, isLive: false, isFinal: false, showsForecast: true, homeRenderedPercent: 52, homeScore: nil, awayScore: nil, commenceTime: base.addingTimeInterval(4 * 3_600), scoreObservedAt: nil),
            60: WatchPinEventSummary12640(id: 60, isLive: false, isFinal: true, showsForecast: false, homeRenderedPercent: nil, homeScore: 4, awayScore: 2, commenceTime: base.addingTimeInterval(-5_000), scoreObservedAt: base.addingTimeInterval(-600)),
            70: WatchPinEventSummary12640(id: 70, isLive: false, isFinal: true, showsForecast: false, homeRenderedPercent: nil, homeScore: nil, awayScore: 2, commenceTime: base.addingTimeInterval(-2_000), scoreObservedAt: nil)
        ]

        let futures: [Int: WatchFutureDetail12640] = [
            201: WatchFutureDetail12640(
                id: 201,
                name: "2028 Democratic Nominee",
                status: "open",
                outcomes: [WatchFutureOutcome12640(id: 1, name: "Newsom", probability: 0.23)]
            ),
            202: WatchFutureDetail12640(
                id: 202,
                name: "Withheld Market",
                status: "open",
                pricesWithheld: 2,
                outcomes: [WatchFutureOutcome12640(id: 2, name: "Option A", probability: 0.50)]
            ),
            203: WatchFutureDetail12640(
                id: 203,
                name: "NBA Champion",
                status: "open",
                outcomes: [WatchFutureOutcome12640(id: 3, name: "Celtics", probability: 0.27)]
            )
        ]

        let ranked = WatchPinsOrdering12640.rank(
            wireItems: wire,
            events: events,
            futures: futures,
            chosenOutcomes: [:]
        )

        // Expected: live (40) -> upcoming soonest (50, 20) -> markets in pin order (201, 203) -> finals most recent (60, 10)
        XCTAssertEqual(ranked.map { $0.wireItem.id }, [40, 50, 20, 201, 203, 60, 10])
    }

    func testFutureDetailDecodingSkipsMalformedLegAndHonorsChosenOutcome() throws {
        let json = """
        {
          "id": 9303,
          "name": "2028 Democratic Nominee",
          "status": "open",
          "prices_withheld": 0,
          "lead_outcome_id": 301,
          "outcomes": [
            {"id": 301, "name": "Newsom", "probability": 0.23, "last_updated": "2026-11-12T20:29:00Z"},
            {"id": 0, "name": "Broken Leg", "probability": 0.50},
            {"id": 302, "name": "Shapiro", "probability": 0.19, "last_updated": "2026-11-12T20:29:00Z"},
            {"id": 303, "name": "Longshot", "probability": 0.002}
          ]
        }
        """
        let market = try JSONDecoder().decode(WatchFutureDetail12640.self, from: Data(json.utf8))
        XCTAssertEqual(market.pricedOutcomes.map(\.id), [301, 302, 303])
        XCTAssertEqual(market.resolvedOutcome(chosenOutcomeID: nil)?.name, "Newsom")
        XCTAssertEqual(market.resolvedOutcome(chosenOutcomeID: 302)?.name, "Shapiro")
        XCTAssertEqual(market.resolvedOutcome(chosenOutcomeID: 303)?.formattedProbability?.display, "<1%")
    }

    func testRectangularFaceDaysAwayStartAndFutureOutcomeNeverSayStaleOrChecked() throws {
        var tz = try XCTUnwrap(TimeZone(identifier: "America/Los_Angeles"))
        var cal = Calendar(identifier: .gregorian)
        cal.timeZone = tz

        // Thu Nov 12, 2026 2:30 PM PT; Sunday game Sun Nov 15, 2026 1:25 PM PT
        let now = try XCTUnwrap(cal.date(from: DateComponents(year: 2026, month: 11, day: 12, hour: 14, minute: 30)))
        let sunday = try XCTUnwrap(cal.date(from: DateComponents(year: 2026, month: 11, day: 15, hour: 13, minute: 25)))
        let oneHourAgo = try XCTUnwrap(cal.date(from: DateComponents(year: 2026, month: 11, day: 12, hour: 13, minute: 29)))

        let gameReading = WatchRectangularReading(
            version: 1,
            eventID: 9202,
            kind: .scheduledForecast,
            homeName: "Kansas City Chiefs",
            awayName: "Buffalo Bills",
            home: Self.makeCompactTeam(teamID: 11, abbreviation: "KC"),
            away: Self.makeCompactTeam(teamID: 12, abbreviation: "BUF"),
            homePercent: 58,
            homeScore: nil,
            awayScore: nil,
            commenceTime: sunday,
            stateLabel: "Scheduled",
            observedAt: now.addingTimeInterval(-300),
            scoreObservedAt: nil
        )
        XCTAssertEqual(gameReading.primaryLine(at: now), "KC 58%")
        XCTAssertEqual(gameReading.metadataLine(at: now, timeZone: tz), "Sun 1:25 PM")

        // Past start with no live reading -> "Open to update"
        XCTAssertEqual(gameReading.metadataLine(at: sunday.addingTimeInterval(60), timeZone: tz), "Open to update")

        // Future market on Watch face -> "2028 Democratic Nominee" / "Newsom 23%" / "As of 1:29 PM"
        let futureReading = WatchRectangularReading(
            version: 1,
            eventID: 9303,
            kind: .futureForecast,
            homeName: "2028 Democratic Nominee",
            awayName: "Newsom",
            home: nil,
            away: nil,
            homePercent: 23,
            homeScore: nil,
            awayScore: nil,
            commenceTime: nil,
            stateLabel: "Market",
            observedAt: oneHourAgo,
            scoreObservedAt: nil
        )
        let parent = WatchComplicationSnapshot(
            version: 1,
            eventID: 9303,
            title: "2028 Democratic Nominee",
            detail: "Newsom 23%",
            observedAt: oneHourAgo,
            savedAt: now,
            circularReading: nil,
            rectangularReading: futureReading
        )
        XCTAssertEqual(parent.validatedRectangularReading(now: now), futureReading)
        XCTAssertEqual(futureReading.headerLine(), "2028 Democratic Nominee")
        XCTAssertEqual(futureReading.primaryLine(at: now), "Newsom 23%")
        XCTAssertEqual(futureReading.metadataLine(at: now, timeZone: tz), "As of 1:29 PM")

        let spoken = futureReading.accessibilityDescription(at: now, timeZone: tz)
        for forbidden in ["stale", "saved", "checked"] {
            XCTAssertFalse(spoken.localizedCaseInsensitiveContains(forbidden), spoken)
            XCTAssertFalse(futureReading.metadataLine(at: now, timeZone: tz).localizedCaseInsensitiveContains(forbidden))
        }
        _ = tz
    }

    private static func makeCompactTeam(teamID: Int, abbreviation: String) -> WatchCompactTeamIdentity {
        let payload: [String: Any] = ["team_id": teamID, "abbreviation": abbreviation]
        let data = try! JSONSerialization.data(withJSONObject: payload)
        return try! JSONDecoder().decode(WatchCompactTeamIdentity.self, from: data)
    }
}
