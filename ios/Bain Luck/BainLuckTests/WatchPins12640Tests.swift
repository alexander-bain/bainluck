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

    func testEightRowCapPreservesBucketOrderBoundsRefreshAndFormatsOverflowFooter() {
        let base = Date(timeIntervalSince1970: 1_794_500_000)
        // 11 phone pins: 1 live (40), 4 upcoming (50, 51, 52, 53), 3 markets (201, 202, 203), 3 finals (60, 61, 62)
        let wire: [WatchPinWireItem12640] = [
            WatchPinWireItem12640(kind: .event, id: 62),    // final oldest
            WatchPinWireItem12640(kind: .future, id: 201),  // market #1
            WatchPinWireItem12640(kind: .event, id: 53),    // upcoming +9h
            WatchPinWireItem12640(kind: .event, id: 61),    // final middle
            WatchPinWireItem12640(kind: .future, id: 202),  // market #2
            WatchPinWireItem12640(kind: .event, id: 51),    // upcoming +5h
            WatchPinWireItem12640(kind: .event, id: 40),    // live
            WatchPinWireItem12640(kind: .future, id: 203),  // market #3
            WatchPinWireItem12640(kind: .event, id: 50),    // upcoming +2h
            WatchPinWireItem12640(kind: .event, id: 60),    // final newest
            WatchPinWireItem12640(kind: .event, id: 52)     // upcoming +7h
        ]

        // Cold start: refresh fetches at most 8 pins rather than all 11.
        let coldRefresh = WatchPinsOrdering12640.itemsToRefresh(
            wireItems: wire,
            events: [:],
            futures: [:],
            chosenOutcomes: [:]
        )
        XCTAssertEqual(coldRefresh.count, 8)

        let events: [Int: WatchPinEventSummary12640] = [
            40: WatchPinEventSummary12640(id: 40, isLive: true, isFinal: false, showsForecast: true, homeRenderedPercent: 64, homeScore: 4, awayScore: 2, commenceTime: base.addingTimeInterval(-3_600), scoreObservedAt: base),
            50: WatchPinEventSummary12640(id: 50, isLive: false, isFinal: false, showsForecast: true, homeRenderedPercent: 58, homeScore: nil, awayScore: nil, commenceTime: base.addingTimeInterval(2 * 3_600), scoreObservedAt: nil),
            51: WatchPinEventSummary12640(id: 51, isLive: false, isFinal: false, showsForecast: true, homeRenderedPercent: 55, homeScore: nil, awayScore: nil, commenceTime: base.addingTimeInterval(5 * 3_600), scoreObservedAt: nil),
            52: WatchPinEventSummary12640(id: 52, isLive: false, isFinal: false, showsForecast: true, homeRenderedPercent: 61, homeScore: nil, awayScore: nil, commenceTime: base.addingTimeInterval(7 * 3_600), scoreObservedAt: nil),
            53: WatchPinEventSummary12640(id: 53, isLive: false, isFinal: false, showsForecast: true, homeRenderedPercent: 52, homeScore: nil, awayScore: nil, commenceTime: base.addingTimeInterval(9 * 3_600), scoreObservedAt: nil),
            60: WatchPinEventSummary12640(id: 60, isLive: false, isFinal: true, showsForecast: false, homeRenderedPercent: nil, homeScore: 114, awayScore: 108, commenceTime: base.addingTimeInterval(-3_600), scoreObservedAt: base.addingTimeInterval(-600)),
            61: WatchPinEventSummary12640(id: 61, isLive: false, isFinal: true, showsForecast: false, homeRenderedPercent: nil, homeScore: 102, awayScore: 99, commenceTime: base.addingTimeInterval(-7_200), scoreObservedAt: base.addingTimeInterval(-3_600)),
            62: WatchPinEventSummary12640(id: 62, isLive: false, isFinal: true, showsForecast: false, homeRenderedPercent: nil, homeScore: 95, awayScore: 90, commenceTime: base.addingTimeInterval(-10_800), scoreObservedAt: base.addingTimeInterval(-7_200))
        ]
        let futures: [Int: WatchFutureDetail12640] = [
            201: WatchFutureDetail12640(id: 201, name: "2028 Democratic Nominee", status: "open", outcomes: [WatchFutureOutcome12640(id: 1, name: "Newsom", probability: 0.23)]),
            202: WatchFutureDetail12640(id: 202, name: "NBA Champion", status: "open", outcomes: [WatchFutureOutcome12640(id: 2, name: "Celtics", probability: 0.27)]),
            203: WatchFutureDetail12640(id: 203, name: "Super Bowl Champion", status: "open", outcomes: [WatchFutureOutcome12640(id: 3, name: "Chiefs", probability: 0.18)])
        ]

        let displayed = WatchPinsOrdering12640.displayed(
            wireItems: wire,
            events: events,
            futures: futures,
            chosenOutcomes: [:]
        )
        // First 8 in bucket order: live (40), upcoming soonest (50, 51, 52, 53), markets in pin order (201, 202, 203).
        XCTAssertEqual(displayed.map { $0.wireItem.id }, [40, 50, 51, 52, 53, 201, 202, 203])

        let warmRefresh = WatchPinsOrdering12640.itemsToRefresh(
            wireItems: wire,
            events: events,
            futures: futures,
            chosenOutcomes: [:]
        )
        XCTAssertEqual(warmRefresh.map(\.id), [40, 50, 51, 52, 53, 201, 202, 203])

        let overflow = WatchPinsOrdering12640.overflowLine(
            wireItems: wire,
            events: events,
            futures: futures,
            chosenOutcomes: [:]
        )
        XCTAssertEqual(overflow, "8 of 11 · the rest are on your iPhone")

        // Cold-start 8-fetched-of-11 also reports "8 of 11 · the rest are on your iPhone".
        let coldFetchedEvents = events.filter { [40, 50, 51, 53, 61, 62].contains($0.key) }
        let coldFetchedFutures = futures.filter { [201, 202].contains($0.key) }
        let coldOverflow = WatchPinsOrdering12640.overflowLine(
            wireItems: wire,
            events: coldFetchedEvents,
            futures: coldFetchedFutures,
            chosenOutcomes: [:]
        )
        XCTAssertEqual(coldOverflow, "8 of 11 · the rest are on your iPhone")
    }

    func testFailedPinNeverVanishesSilentlyAndSavedReadingSuppressesFalseError() {
        let base = Date(timeIntervalSince1970: 1_794_500_000)
        let wire: [WatchPinWireItem12640] = [
            WatchPinWireItem12640(kind: .event, id: 40),
            WatchPinWireItem12640(kind: .future, id: 201),
            WatchPinWireItem12640(kind: .event, id: 99)
        ]
        let events: [Int: WatchPinEventSummary12640] = [
            40: WatchPinEventSummary12640(id: 40, isLive: true, isFinal: false, showsForecast: true, homeRenderedPercent: 64, homeScore: 4, awayScore: 2, commenceTime: base.addingTimeInterval(-1_800), scoreObservedAt: base)
        ]
        let futures: [Int: WatchFutureDetail12640] = [
            201: WatchFutureDetail12640(id: 201, name: "2028 Democratic Nominee", status: "open", outcomes: [WatchFutureOutcome12640(id: 1, name: "Newsom", probability: 0.23)])
        ]

        // 2 load and 1 fails with no saved reading -> 2 rows + "1 pin didn't load", no overflow footer, no full-failure replacement.
        let partial = WatchPinsOrdering12640.reconcileRefresh(
            wireItems: wire,
            events: events,
            futures: futures,
            chosenOutcomes: [:],
            attemptedKeys: ["event:40", "future:201", "event:99"],
            attemptedFailedKeys: ["event:99"]
        )
        XCTAssertEqual(partial.displayedEntries.map { $0.wireItem.id }, [40, 201])
        XCTAssertEqual(partial.partialFailureLine, "1 pin didn't load")
        XCTAssertNil(partial.overflowFooterLine)
        XCTAssertNil(partial.fullFailureMessage)

        // Plural when 2 pins fail with no saved reading.
        let twoFailed = WatchPinsOrdering12640.reconcileRefresh(
            wireItems: wire,
            events: events,
            futures: [:],
            chosenOutcomes: [:],
            attemptedKeys: ["event:40", "future:201", "event:99"],
            attemptedFailedKeys: ["future:201", "event:99"]
        )
        XCTAssertEqual(twoFailed.displayedEntries.map { $0.wireItem.id }, [40])
        XCTAssertEqual(twoFailed.partialFailureLine, "2 pins didn't load")
        XCTAssertNil(twoFailed.fullFailureMessage)

        // When a failed pin already has a saved reading, its row stays visible and no "didn't load" line prints.
        let savedFallback = WatchPinsOrdering12640.reconcileRefresh(
            wireItems: [WatchPinWireItem12640(kind: .event, id: 40), WatchPinWireItem12640(kind: .future, id: 201)],
            events: events,
            futures: futures,
            chosenOutcomes: [:],
            attemptedKeys: ["event:40", "future:201"],
            attemptedFailedKeys: ["future:201"]
        )
        XCTAssertEqual(savedFallback.displayedEntries.map { $0.wireItem.id }, [40, 201])
        XCTAssertNil(savedFallback.partialFailureLine)
        XCTAssertNil(savedFallback.fullFailureMessage)

        // When all pins fail and nothing is saved, full-failure copy prints instead.
        let totalFailure = WatchPinsOrdering12640.reconcileRefresh(
            wireItems: wire,
            events: [:],
            futures: [:],
            chosenOutcomes: [:],
            attemptedKeys: ["event:40", "future:201", "event:99"],
            attemptedFailedKeys: ["event:40", "future:201", "event:99"]
        )
        XCTAssertTrue(totalFailure.displayedEntries.isEmpty)
        XCTAssertEqual(totalFailure.fullFailureMessage, "Unable to load pins. Try Refresh.")
        XCTAssertNil(totalFailure.partialFailureLine)

        for copy in [partial.partialFailureLine, twoFailed.partialFailureLine, totalFailure.fullFailureMessage].compactMap({ $0 }) {
            for forbidden in ["stale", "checked", "question"] {
                XCTAssertFalse(copy.localizedCaseInsensitiveContains(forbidden), copy)
            }
        }
    }

    private static func makeCompactTeam(teamID: Int, abbreviation: String) -> WatchCompactTeamIdentity {
        let payload: [String: Any] = ["team_id": teamID, "abbreviation": abbreviation]
        let data = try! JSONSerialization.data(withJSONObject: payload)
        return try! JSONDecoder().decode(WatchCompactTeamIdentity.self, from: data)
    }
}
