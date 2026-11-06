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
        XCTAssertEqual(EventAtlasStates11666.voided, "Void")
        XCTAssertEqual(EventAtlasStates11666.noRecentPrice, "No recent probability")
        XCTAssertEqual(EventAtlasStates11666.noPriceYet, "No price yet")
        XCTAssertEqual(EventAtlasStates11666.wonWithCheck, "✓ Won")
        XCTAssertEqual(EventAtlasStates11666.lostWithCross, "✗ Lost")
        XCTAssertEqual(EventAtlasStates11666.pending, "Pending")

        XCTAssertEqual(
            EventAtlasStates11666.connectionStatusLabel(for: .awaitingUpdate, atlasEnabled: true),
            "Loading"
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
        // 1. Suspended & started with authority stoppage "Postponed" -> "Postponed"
        XCTAssertEqual(
            EventAtlasStates11666.heroStateLabel(
                status: "suspended",
                commenceTime: pastKickoff,
                authorityPeriod: "Postponed",
                venueSettled: false,
                venueClosedNoWinner: false,
                hasCurrentOdds: true,
                now: now
            ),
            "Postponed"
        )

        // 2. Suspended & started without authority stoppage label -> nil (never claims Postponed)
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

        // 3. Venue closed with no winner -> "Void"
        XCTAssertEqual(
            EventAtlasStates11666.heroStateLabel(
                status: "suspended",
                commenceTime: pastKickoff,
                authorityPeriod: nil,
                venueSettled: false,
                venueClosedNoWinner: true,
                hasCurrentOdds: false,
                now: now
            ),
            "Void"
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

        // 5. Pregame scheduled fixture with no current odds -> "No price yet"
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
            "No price yet"
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
        XCTAssertTrue(specialSrc.contains("EventAtlasStates11666.verdictLabel(v)"))
    }
}
