import XCTest
@testable import Bain_Luck

/// #11666 (Step E4) — Unit tests for the native event-page Atlas shared state
/// vocabulary (`EventAtlasStates11666`), `AllMarketsCatalogView9483`,
/// `SpecialEventMarketsView`, and `EventDetailView` wiring behind
/// `ReleaseSurfaces.isEventPageAtlasEnabled()`.
final class EventAtlasStatesE4_11666Tests: XCTestCase {

    private let now = ISO8601DateFormatter().date(from: "2026-11-06T20:00:00Z")!
    private let pastKickoff = ISO8601DateFormatter().date(from: "2026-11-06T18:00:00Z")!
    private let futureKickoff = ISO8601DateFormatter().date(from: "2026-11-07T02:00:00Z")!

    func testSharedStateCopyAndConnectionStatusLabels11666() {
        XCTAssertEqual(EventAtlasStates11666.loading, "Loading")
        XCTAssertEqual(EventAtlasStates11666.updateInterrupted, "Update interrupted")
        XCTAssertEqual(EventAtlasStates11666.postponed, "Postponed")
        XCTAssertEqual(EventAtlasStates11666.voided, EventState.venueClosedNoWinnerLabel)
        XCTAssertEqual(EventAtlasStates11666.noRecentPrice, "No recent probability")
        XCTAssertEqual(EventAtlasStates11666.noPriceYet, "No probability yet")
        XCTAssertEqual(EventAtlasStates11666.wonWithCheck, "✓ Won")
        XCTAssertEqual(EventAtlasStates11666.lostWithCross, "✗ Lost")
        XCTAssertEqual(EventAtlasStates11666.pending, "Pending")

        XCTAssertEqual(
            EventAtlasStates11666.connectionStatusLabel(for: .awaitingUpdate, atlasEnabled: true),
            LiveUpdateStatus.awaitingUpdate.title
        )
        XCTAssertEqual(
            EventAtlasStates11666.connectionStatusLabel(for: .awaitingUpdate, atlasEnabled: false),
            LiveUpdateStatus.awaitingUpdate.title
        )
        XCTAssertEqual(
            EventAtlasStates11666.connectionStatusLabel(for: .interrupted, atlasEnabled: true),
            "Update interrupted"
        )
        XCTAssertEqual(
            EventAtlasStates11666.connectionStatusLabel(for: .interrupted, atlasEnabled: false),
            LiveUpdateStatus.interrupted.title
        )
        XCTAssertEqual(
            EventAtlasStates11666.connectionStatusLabel(for: .live, atlasEnabled: true),
            LiveUpdateStatus.live.title
        )
        XCTAssertNil(
            EventAtlasStates11666.connectionStatusLabel(for: .hidden, atlasEnabled: true)
        )
    }

    func testHeroStateLabelCoversPostponedVoidAndNoRecentProbability11666() {
        // 1. Suspended & started with authority stoppage "Postponed" -> nil (StatusBadge already prints "Postponed")
        XCTAssertNil(
            EventAtlasStates11666.heroStateLabel(
                status: "suspended",
                commenceTime: pastKickoff,
                authorityPeriod: "Postponed",
                venueSettled: false,
                venueClosedNoWinner: false,
                hasCurrentOdds: true,
                now: now
            )
        )

        // 2. Suspended & started without authority stoppage label -> nil (StatusBadge already prints "No result reported")
        XCTAssertNil(
            EventAtlasStates11666.heroStateLabel(
                status: "suspended",
                commenceTime: pastKickoff,
                authorityPeriod: nil,
                venueSettled: false,
                venueClosedNoWinner: false,
                hasCurrentOdds: true,
                now: now
            )
        )

        // 3. Venue closed with no winner -> nil (StatusBadge already prints EventState.venueClosedNoWinnerLabel)
        XCTAssertNil(
            EventAtlasStates11666.heroStateLabel(
                status: "suspended",
                commenceTime: pastKickoff,
                authorityPeriod: nil,
                venueSettled: false,
                venueClosedNoWinner: true,
                hasCurrentOdds: false,
                now: now
            )
        )

        // 4. Started game with no current odds -> "No recent probability"
        XCTAssertEqual(
            EventAtlasStates11666.heroStateLabel(
                status: "live",
                commenceTime: pastKickoff,
                authorityPeriod: nil,
                venueSettled: false,
                venueClosedNoWinner: false,
                hasCurrentOdds: false,
                now: now
            ),
            "No recent probability"
        )

        // 5. Pregame scheduled fixture with no current odds -> "No probability yet"
        XCTAssertEqual(
            EventAtlasStates11666.heroStateLabel(
                status: "scheduled",
                commenceTime: futureKickoff,
                authorityPeriod: nil,
                venueSettled: false,
                venueClosedNoWinner: false,
                hasCurrentOdds: false,
                now: now
            ),
            "No probability yet"
        )

        // 6. Settled or venue-settled event never claims "No recent probability"
        XCTAssertNil(
            EventAtlasStates11666.heroStateLabel(
                status: "completed",
                commenceTime: pastKickoff,
                authorityPeriod: nil,
                venueSettled: false,
                venueClosedNoWinner: false,
                hasCurrentOdds: false,
                now: now
            )
        )
        XCTAssertNil(
            EventAtlasStates11666.heroStateLabel(
                status: "suspended",
                commenceTime: pastKickoff,
                authorityPeriod: nil,
                venueSettled: true,
                venueClosedNoWinner: false,
                hasCurrentOdds: false,
                now: now
            )
        )
    }

    func testAllMarketsCatalogPrintsNoRecentProbabilityOnlyOnStaleLiveOutcomes11666() {
        let stale = QuestionCatalog9483.Outcome(
            label: "Over 47.5",
            threshold: 47.5,
            probability: nil,
            observedAt: "2026-11-06T16:00:00Z",
            absence: .stale
        )
        let closedPeriod = QuestionCatalog9483.Outcome(
            label: "Over 10.5",
            threshold: 10.5,
            probability: nil,
            observedAt: nil,
            absence: .periodFinished
        )
        let unavailable = QuestionCatalog9483.Outcome(
            label: "Under 47.5",
            threshold: 47.5,
            probability: nil,
            observedAt: nil,
            absence: .unavailable
        )

        XCTAssertEqual(
            AllMarketsCatalogView9483.priceText(stale, status: "live", atlasEnabled: true),
            "No recent probability"
        )
        XCTAssertEqual(
            AllMarketsCatalogView9483.priceText(stale, status: "live", atlasEnabled: false),
            "No recent probability update"
        )
        XCTAssertEqual(
            AllMarketsCatalogView9483.priceText(closedPeriod, status: "live", atlasEnabled: true),
            "Period finished"
        )
        XCTAssertEqual(
            AllMarketsCatalogView9483.priceText(unavailable, status: "live", atlasEnabled: true),
            "Probability unavailable"
        )
        XCTAssertNil(
            AllMarketsCatalogView9483.priceText(stale, status: "final", atlasEnabled: true)
        )

        // Decide 80 (A): settled catalog rows ask OutcomeVerdict as for an open market
        // (marketResolved: false) and print "✓ Won" only on a provable authoritative win,
        // leaving unconfirmed or false-graded rows nil (never "✗ Lost").
        let settledWon = QuestionCatalog9483.Outcome(
            label: "Over 47.5",
            threshold: 47.5,
            probability: nil,
            observedAt: nil,
            absence: .settled,
            verdict: .won
        )
        let settledLost = QuestionCatalog9483.Outcome(
            label: "Under 47.5",
            threshold: 47.5,
            probability: nil,
            observedAt: nil,
            absence: .settled,
            verdict: .lost
        )
        XCTAssertEqual(
            AllMarketsCatalogView9483.priceText(settledWon, status: "final", atlasEnabled: true),
            "✓ Won"
        )
        XCTAssertNil(
            AllMarketsCatalogView9483.priceText(settledLost, status: "final", atlasEnabled: true)
        )
        XCTAssertNil(
            AllMarketsCatalogView9483.priceText(settledWon, status: "final", atlasEnabled: false)
        )

        let payload: [String: Any] = [
            "event_id": 11666,
            "home_team": "BOS",
            "away_team": "NYY",
            "status": "completed",
            "totals": [], "player_props": [], "team_totals": [], "spreads": [],
            "period_markets": [], "matchups": [],
            "other": [
                [
                    "is_winner": true,
                    "resolution_source": "api_settlement",
                    "market_name": "Will there be extra innings?",
                    "outcome_name": "Yes",
                    "probability": 0.12,
                    "source": "kalshi",
                ],
                [
                    "is_winner": false,
                    "resolution_source": "clob_never_graded",
                    "market_name": "Will there be extra innings?",
                    "outcome_name": "No",
                    "probability": 0.88,
                    "source": "kalshi",
                ],
                [
                    "is_winner": false,
                    "resolution_source": "api_settlement",
                    "market_name": "Will there be extra innings?",
                    "outcome_name": "Alt No",
                    "probability": 0.88,
                    "source": "kalshi",
                ],
            ],
        ]
        let decoder = JSONDecoder()
        decoder.keyDecodingStrategy = .convertFromSnakeCase
        guard let decodedMarkets = try? decoder.decode(
            GameMarketsResponse.self,
            from: JSONSerialization.data(withJSONObject: payload)
        ) else {
            XCTFail("Failed to decode GameMarketsResponse fixture")
            return
        }
        let catalogGroups = QuestionCatalog9483.build(
            decodedMarkets,
            status: "completed"
        )
        let builtOutcomes = catalogGroups.first?.outcomes ?? []
        XCTAssertEqual(builtOutcomes.count, 3)
        if builtOutcomes.count == 3 {
            XCTAssertEqual(builtOutcomes[0].verdict, OutcomeVerdict.won)
            XCTAssertEqual(
                AllMarketsCatalogView9483.priceText(builtOutcomes[0], status: "completed", atlasEnabled: true),
                "✓ Won"
            )
            XCTAssertNil(builtOutcomes[1].verdict)
            XCTAssertNil(
                AllMarketsCatalogView9483.priceText(builtOutcomes[1], status: "completed", atlasEnabled: true)
            )
            XCTAssertNil(builtOutcomes[2].verdict)
            XCTAssertNil(
                AllMarketsCatalogView9483.priceText(builtOutcomes[2], status: "completed", atlasEnabled: true)
            )
        }
    }

    func testVerdictLabelsAndVenueDisagreementPending11666() {
        XCTAssertEqual(EventAtlasStates11666.verdictLabel(.won, atlasEnabled: true), "✓ Won")
        XCTAssertEqual(EventAtlasStates11666.verdictLabel(.lost, atlasEnabled: true), "✗ Lost")
        XCTAssertEqual(EventAtlasStates11666.verdictLabel(.won, atlasEnabled: false), "Won")
        XCTAssertEqual(EventAtlasStates11666.verdictLabel(.lost, atlasEnabled: false), "Lost")

        XCTAssertEqual(
            EventAtlasStates11666.verdictDisplay(verdicts: [.won, .won], atlasEnabled: true),
            "✓ Won"
        )
        XCTAssertEqual(
            EventAtlasStates11666.verdictDisplay(verdicts: [.lost, .lost], atlasEnabled: true),
            "✗ Lost"
        )
        XCTAssertEqual(
            EventAtlasStates11666.verdictDisplay(verdicts: [.won, .lost], atlasEnabled: true),
            "Pending"
        )
        XCTAssertNil(
            EventAtlasStates11666.verdictDisplay(verdicts: [], atlasEnabled: true)
        )

        // SpecialEventMarketsView merges multiple venues sharing an outcome label and
        // routes their grades through EventAtlasStates11666.verdictDisplay (#11666 Step E4).
        let disagreeingMarkets: [GameMarketOther] = [
            GameMarketOther(
                isWinner: true,
                resolutionSource: "api_settlement",
                marketName: "Will there be overtime?",
                outcomeName: "Yes",
                probability: 0.12,
                source: "kalshi",
                observedAt: "2026-11-06T17:50:00Z"
            ),
            GameMarketOther(
                isWinner: false,
                resolutionSource: "api_settlement",
                marketName: "Will there be overtime?",
                outcomeName: "Yes",
                probability: 0.14,
                source: "polymarket",
                observedAt: "2026-11-06T17:51:00Z"
            ),
        ]
        let view = SpecialEventMarketsView(
            markets: disagreeingMarkets,
            eventStatus: "completed",
            commenceTime: pastKickoff
        )
        let mergedEntry = try? XCTUnwrap(view.categories.first?.items.first?.outcomes.first)
        XCTAssertNotNil(mergedEntry)
        if let entry = mergedEntry, case .verdict(let v) = view.treatment(for: entry) {
            XCTAssertEqual(view.resolvedVerdictText(for: entry, verdict: v, atlasEnabled: true), "Pending")
            XCTAssertFalse(
                view.verdictIsWonHighlight(for: entry, verdict: v, atlasEnabled: true),
                "Disagreeing venue verdicts ('Pending') must never inherit the first venue's bold emerald styling"
            )
            XCTAssertEqual(view.resolvedVerdictText(for: entry, verdict: v, atlasEnabled: false), "Won")
            XCTAssertTrue(view.verdictIsWonHighlight(for: entry, verdict: v, atlasEnabled: false))
        } else {
            XCTFail("Expected merged settled outcome to resolve to .verdict")
        }
    }

    func testEventDetailViewCatalogAndSpecialMarketsWireStepE4BehindFlag11666() throws {
        let testFile = URL(fileURLWithPath: #filePath)
        let root = testFile
            .deletingLastPathComponent()
            .deletingLastPathComponent()
            .appendingPathComponent("Bain Luck")

        let detailSrc = try String(
            contentsOf: root.appendingPathComponent("Views/EventDetailView.swift"),
            encoding: .utf8
        )
        let catalogSrc = try String(
            contentsOf: root.appendingPathComponent("Components/AllMarketsCatalogView9483.swift"),
            encoding: .utf8
        )
        let specialSrc = try String(
            contentsOf: root.appendingPathComponent("Components/SpecialEventMarketsView.swift"),
            encoding: .utf8
        )

        XCTAssertTrue(detailSrc.contains("ProgressView(EventAtlasStates11666.loading)"))
        XCTAssertTrue(detailSrc.contains("EventAtlasStates11666.heroStateLabel("))
        XCTAssertTrue(detailSrc.contains("EventAtlasHeroStateLabelView11666(label: stateLabel)"))
        XCTAssertTrue(catalogSrc.contains("case .stale: return atlasEnabled ? EventAtlasStates11666.noRecentPrice : noRecentPrice"))
        XCTAssertTrue(specialSrc.contains("EventAtlasStates11666.verdictDisplay(verdicts: allVerdicts, atlasEnabled: true)"))
        XCTAssertTrue(specialSrc.contains("resolvedVerdictText(for: o, verdict: v"))
        XCTAssertTrue(specialSrc.contains("verdictIsWonHighlight(for: o, verdict: v"))
    }
}
