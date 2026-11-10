import SwiftUI
import UIKit
import XCTest
@testable import Bain_Luck

final class FuturesAtlasPresentation11666Tests: XCTestCase {

    private let referenceNow = ISO8601DateFormatter().date(from: "2026-11-04T02:33:00Z")!

    private func makeDecoder() -> JSONDecoder {
        let decoder = JSONDecoder()
        decoder.keyDecodingStrategy = .convertFromSnakeCase
        return decoder
    }

    // MARK: - Canonical Fixtures (docs/designs/futures-page-2026-11)

    private func makeOutcomeDict(
        id: Int,
        name: String,
        probability: Double?,
        openingProbability: Double? = nil,
        change24h: Double? = nil,
        isWinner: Bool? = nil,
        resolutionSource: String? = nil,
        settlementVerdict: String? = nil,
        settlementBasis: String? = nil,
        observedAt: String? = "2026-11-04T02:30:00Z"
    ) -> [String: Any] {
        var dict: [String: Any] = [
            "id": id,
            "name": name,
        ]
        if let probability { dict["probability"] = probability }
        if let openingProbability { dict["opening_probability"] = openingProbability }
        if let change24h { dict["probability_change_24h"] = change24h }
        if let isWinner { dict["is_winner"] = isWinner }
        if let resolutionSource { dict["resolution_source"] = resolutionSource }
        if let settlementVerdict {
            dict["settlement_display"] = [
                "verdict": settlementVerdict,
                "basis": settlementBasis ?? "official_source",
            ]
        }
        if let observedAt {
            dict["observed_at"] = observedAt
            dict["last_updated"] = observedAt
        }
        return dict
    }

    private func makeMarket(
        id: Int,
        name: String,
        category: String = "politics",
        status: String = "active",
        source: String = "kalshi",
        mutuallyExclusive: Bool? = true,
        resolutionDate: String? = "2027-01-20T04:59:00Z",
        description: String? = nil,
        hookDescription: String? = nil,
        bookmakers: [String]? = ["kalshi"],
        outcomes: [[String: Any]]
    ) -> FuturesMarketDetail {
        var dict: [String: Any] = [
            "id": id,
            "name": name,
            "category": category,
            "llm_sport_category": category,
            "status": status,
            "source": source,
            "outcomes": outcomes,
        ]
        if let mutuallyExclusive { dict["mutually_exclusive"] = mutuallyExclusive }
        if let resolutionDate { dict["resolution_date"] = resolutionDate }
        if let description { dict["description"] = description }
        if let hookDescription { dict["hook_description"] = hookDescription }
        if let bookmakers { dict["bookmakers"] = bookmakers }
        let data = try! JSONSerialization.data(withJSONObject: dict)
        return try! makeDecoder().decode(FuturesMarketDetail.self, from: data)
    }

    // MARK: - 1. Multi-Outcome Mutually-Exclusive Field (108629 — Closest Governor Race)

    func testMutuallyExclusiveFieldBuildsTopThreeLeadersAndFullFieldSheet() {
        var outcomes: [[String: Any]] = [
            makeOutcomeDict(id: 1, name: "Florida", probability: 0.29, openingProbability: 0.24, change24h: 0.02),
            makeOutcomeDict(id: 2, name: "Georgia", probability: 0.21, openingProbability: 0.22, change24h: -0.01),
            makeOutcomeDict(id: 3, name: "Wisconsin", probability: 0.16, openingProbability: 0.15, change24h: 0.01),
        ]
        for idx in 4...24 {
            outcomes.append(
                makeOutcomeDict(
                    id: idx,
                    name: "State \(idx)",
                    probability: max(0.004, Double(25 - idx) * 0.005),
                    openingProbability: 0.02
                )
            )
        }

        let market = makeMarket(
            id: 108629,
            name: "Closest Governor race in 2026",
            category: "politics",
            mutuallyExclusive: true,
            outcomes: outcomes
        )

        let page = FuturesAtlasPresentation11666.build(market: market, now: referenceNow)
        XCTAssertEqual(page.body.shape, .mutuallyExclusiveField)
        XCTAssertEqual(page.header.eyebrow, "Politics · Open")
        XCTAssertEqual(page.header.selectedOutcomeName, "Florida")
        XCTAssertEqual(page.header.primaryDisplay.primaryLabel, "29%")
        XCTAssertEqual(page.header.openingChanceText, "Opening chance 24%")
        XCTAssertEqual(page.body.primaryRows.map(\.name), ["Florida", "Georgia", "Wisconsin"])
        XCTAssertEqual(page.body.sliceCaption, "Showing top 3 of 24")
        XCTAssertEqual(page.body.allRows.count, 24)
        XCTAssertEqual(page.body.remainingCount, 21)

        // Selecting a contender in the full-field sheet updates the header focus.
        let selected = FuturesAtlasPresentation11666.build(
            market: market,
            selectedOutcomeId: 2,
            now: referenceNow
        )
        XCTAssertEqual(selected.header.selectedOutcomeName, "Georgia")
        XCTAssertEqual(selected.header.primaryDisplay.primaryLabel, "21%")
    }

    // MARK: - 1b. Non-Sport & Special-Event Futures Categories (16d-3 Carried Into Item 17)

    func testSpecialEventFuturesCategoriesUseDomainContextAndDistinguishMacroFromEarnings() {
        let derby = makeMarket(
            id: 5001,
            name: "Kentucky Derby 2027 Winner",
            category: "horse_racing",
            outcomes: [
                makeOutcomeDict(id: 1, name: "Fierceness", probability: 0.24, openingProbability: 0.20),
                makeOutcomeDict(id: 2, name: "Sierra Leone", probability: 0.19, openingProbability: 0.18),
                makeOutcomeDict(id: 3, name: "Forever Young", probability: 0.14, openingProbability: 0.12),
                makeOutcomeDict(id: 4, name: "Catching Freedom", probability: 0.09, openingProbability: 0.08),
            ]
        )
        let derbyPage = FuturesAtlasPresentation11666.build(market: derby, now: referenceNow)
        XCTAssertEqual(derbyPage.body.domainContext, "Race Field")
        XCTAssertEqual(derbyPage.body.sliceCaption, "Showing top 3 of 4")

        let oscars = makeMarket(
            id: 5002,
            name: "Oscars 2027 Best Picture Winner",
            category: "entertainment",
            outcomes: [
                makeOutcomeDict(id: 1, name: "Anora", probability: 0.36, openingProbability: 0.28),
                makeOutcomeDict(id: 2, name: "The Brutalist", probability: 0.27, openingProbability: 0.25),
                makeOutcomeDict(id: 3, name: "Conclave", probability: 0.18, openingProbability: 0.16),
            ]
        )
        XCTAssertEqual(FuturesAtlasPresentation11666.domainContextLabel(for: oscars), "Ceremony & Release Outlook")

        let fedDecision = makeMarket(
            id: 5003,
            name: "Fed interest rate cut in December 2026?",
            category: "economics",
            outcomes: [
                makeOutcomeDict(id: 1, name: "25 bps cut", probability: 0.68, openingProbability: 0.60),
                makeOutcomeDict(id: 2, name: "No change", probability: 0.32, openingProbability: 0.40),
            ]
        )
        XCTAssertEqual(FuturesAtlasPresentation11666.domainContextLabel(for: fedDecision), "Macro & Policy Outlook")

        let nvidiaEarnings = makeMarket(
            id: 5004,
            name: "NVIDIA Revenue Beat Consensus?",
            category: "economics",
            outcomes: [
                makeOutcomeDict(id: 1, name: "Yes", probability: 0.78, openingProbability: 0.71),
                makeOutcomeDict(id: 2, name: "No", probability: 0.22, openingProbability: 0.29),
            ]
        )
        XCTAssertEqual(FuturesAtlasPresentation11666.domainContextLabel(for: nvidiaEarnings), "Earnings & Release Outlook")

        let olympics = makeMarket(
            id: 5005,
            name: "Winter Olympics 2026 Most Gold Medals",
            category: "olympics",
            outcomes: [
                makeOutcomeDict(id: 1, name: "Norway", probability: 0.44),
                makeOutcomeDict(id: 2, name: "Germany", probability: 0.24),
                makeOutcomeDict(id: 3, name: "United States", probability: 0.18),
            ]
        )
        XCTAssertEqual(FuturesAtlasPresentation11666.domainContextLabel(for: olympics), "Medal & Podium Outlook")

        let poker = makeMarket(
            id: 5006,
            name: "WSOP Main Event 2027 Winner",
            category: "poker",
            outcomes: [
                makeOutcomeDict(id: 1, name: "Daniel Negreanu", probability: 0.08),
                makeOutcomeDict(id: 2, name: "Phil Ivey", probability: 0.07),
                makeOutcomeDict(id: 3, name: "Bryn Kenney", probability: 0.05),
            ]
        )
        XCTAssertEqual(FuturesAtlasPresentation11666.domainContextLabel(for: poker), "Bracelet & Table Field")
    }

    // MARK: - 2. Quantity / Threshold Ladder (65536371 — Snow in Denver)

    func testQuantityLadderOrdersThresholdsWithoutNormalizationOrMonotonicRepair() {
        let outcomes = [
            makeOutcomeDict(id: 10, name: "Above 6 inches", probability: 0.64, openingProbability: 0.58),
            makeOutcomeDict(id: 11, name: "Above 0 inches", probability: 0.96, openingProbability: 0.94),
            makeOutcomeDict(id: 12, name: "Above 2 inches", probability: 0.88, openingProbability: 0.85),
            makeOutcomeDict(id: 13, name: "Above 10 inches", probability: 0.34, openingProbability: 0.31),
            makeOutcomeDict(id: 14, name: "Above 15 inches", probability: 0.14, openingProbability: 0.12),
            makeOutcomeDict(id: 15, name: "Above 20 inches", probability: 0.05, openingProbability: 0.04),
        ]
        let market = makeMarket(
            id: 65536371,
            name: "Snow in Denver in Dec 2026",
            category: "weather",
            mutuallyExclusive: false,
            outcomes: outcomes
        )

        let page = FuturesAtlasPresentation11666.build(
            market: market,
            selectedOutcomeId: 10,
            now: referenceNow
        )
        XCTAssertEqual(page.body.shape, .quantityLadder)
        XCTAssertEqual(page.header.selectedOutcomeName, "Above 6 inches")
        XCTAssertEqual(page.header.primaryDisplay.primaryLabel, "64%")
        XCTAssertEqual(
            page.body.primaryRows.map(\.name),
            [
                "Above 0 inches",
                "Above 2 inches",
                "Above 6 inches",
                "Above 10 inches",
                "Above 15 inches",
                "Above 20 inches",
            ]
        )
        XCTAssertEqual(
            page.body.primaryRows.map { $0.displayValue.primaryLabel },
            ["96%", "88%", "64%", "34%", "14%", "5%"]
        )
    }

    // MARK: - 3. Independent Participation / Qualification Field (227 — CFP Qualifiers)

    func testParticipationFieldShowsIndependentBadgeAndRespectsDecide80ASettlement() {
        let openMarket = makeMarket(
            id: 227,
            name: "College Football Playoff Qualifiers",
            category: "football",
            mutuallyExclusive: false,
            outcomes: [
                makeOutcomeDict(id: 101, name: "Miami (FL)", probability: 0.94, openingProbability: 0.72),
                makeOutcomeDict(id: 102, name: "Oregon", probability: 0.92, openingProbability: 0.81),
                makeOutcomeDict(id: 103, name: "Ohio State", probability: 0.89, openingProbability: 0.86),
                makeOutcomeDict(id: 104, name: "Texas", probability: 0.84, openingProbability: 0.79),
                makeOutcomeDict(id: 105, name: "Georgia", probability: 0.78, openingProbability: 0.83),
                makeOutcomeDict(id: 106, name: "Penn State", probability: 0.74, openingProbability: 0.68),
                makeOutcomeDict(id: 107, name: "Indiana", probability: 0.61, openingProbability: 0.18),
            ]
        )

        let openPage = FuturesAtlasPresentation11666.build(market: openMarket, now: referenceNow)
        XCTAssertEqual(openPage.body.shape, .participationField)
        XCTAssertEqual(openPage.body.subtitleBadge, "Independent chances · do not add to 100%")
        XCTAssertEqual(openPage.body.sliceCaption, "Showing top 6 of 7")
        XCTAssertEqual(openPage.header.selectedOutcomeName, "Miami (FL)")
        XCTAssertEqual(openPage.header.primaryDisplay.primaryLabel, "94%")
        XCTAssertEqual(openPage.body.primaryRows.count, 6)
        XCTAssertEqual(openPage.body.remainingCount, 1)

        // Decide 80-A: on a resolved participation field, `ungradeable_result` or a missing
        // authoritative loss never grades a team as `✗ Lost`.
        let settledMarket = makeMarket(
            id: 227,
            name: "College Football Playoff Qualifiers",
            category: "football",
            status: "resolved",
            mutuallyExclusive: false,
            outcomes: [
                makeOutcomeDict(
                    id: 101,
                    name: "Miami (FL)",
                    probability: 1.0,
                    openingProbability: 0.72,
                    isWinner: true,
                    resolutionSource: "api_settlement"
                ),
                makeOutcomeDict(
                    id: 102,
                    name: "Oregon",
                    probability: 0.92,
                    openingProbability: 0.81,
                    isWinner: false,
                    resolutionSource: "ungradeable_result"
                ),
                makeOutcomeDict(
                    id: 103,
                    name: "Alabama",
                    probability: 0.0,
                    openingProbability: 0.65,
                    isWinner: false,
                    resolutionSource: "api_settlement"
                ),
            ]
        )
        let settledPage = FuturesAtlasPresentation11666.build(market: settledMarket, now: referenceNow)
        XCTAssertEqual(settledPage.body.primaryRows[0].displayValue, .won)
        XCTAssertEqual(
            settledPage.body.primaryRows[1].displayValue,
            .resultUnconfirmed(lastRecordedText: "92%")
        )
        XCTAssertEqual(settledPage.body.primaryRows[2].displayValue, .lost)
    }

    // MARK: - 4. Two-Way Duel Open & Settled (109085 Kansas Senate & 108645 Georgia Governor)

    func testTwoWayDuelPreservesUnnormalizedServerNumbersAndSettledVerdicts() {
        let kansasDuel = makeMarket(
            id: 109085,
            name: "Kansas Senate winner",
            category: "politics",
            status: "active",
            mutuallyExclusive: true,
            outcomes: [
                makeOutcomeDict(id: 201, name: "Adam Hamilton", probability: 0.97, openingProbability: 0.91),
                makeOutcomeDict(id: 202, name: "Democratic Challenger", probability: 0.02, openingProbability: 0.08),
            ]
        )
        let kansasPage = FuturesAtlasPresentation11666.build(market: kansasDuel, now: referenceNow)
        XCTAssertEqual(kansasPage.body.shape, .twoWayDuel)
        XCTAssertEqual(kansasPage.body.primaryRows.map { $0.displayValue.primaryLabel }, ["97%", "2%"])

        let georgiaSettled = makeMarket(
            id: 108645,
            name: "Georgia Governor winner",
            category: "politics",
            status: "resolved",
            mutuallyExclusive: true,
            outcomes: [
                makeOutcomeDict(
                    id: 301,
                    name: "Keisha Lance Bottoms",
                    probability: 1.0,
                    openingProbability: 0.56,
                    isWinner: true,
                    resolutionSource: "kalshi"
                ),
                makeOutcomeDict(
                    id: 302,
                    name: "Burt Jones",
                    probability: 0.0,
                    openingProbability: 0.45,
                    isWinner: false,
                    resolutionSource: "kalshi"
                ),
            ]
        )
        let georgiaPage = FuturesAtlasPresentation11666.build(market: georgiaSettled, now: referenceNow)
        XCTAssertEqual(georgiaPage.header.eyebrow, "Politics · Settled")
        XCTAssertEqual(georgiaPage.header.selectedOutcomeName, "Keisha Lance Bottoms")
        XCTAssertEqual(georgiaPage.header.primaryDisplay, .won)
        XCTAssertEqual(georgiaPage.header.openingChanceText, "Opening chance 56%")
        XCTAssertEqual(georgiaPage.body.primaryRows.map(\.displayValue), [.won, .lost])
    }

    // MARK: - 5. One-Leg Predicate Fallback & Decide 10-C Stale Quote Aging (109918)

    func testSingleLegPredicateNeverInventsSecondRowAndAgesStaleQuotes() {
        let settledOneLeg = makeMarket(
            id: 109918,
            name: "Will Democrats sweep all swing state Governor races",
            category: "politics",
            status: "resolved",
            description: "If Democrats win Pennsylvania, Michigan, Wisconsin, Georgia, Arizona, AND Nevada in 2026, resolves to Yes.",
            outcomes: [
                makeOutcomeDict(
                    id: 401,
                    name: "Yes",
                    probability: 1.0,
                    openingProbability: 0.38,
                    isWinner: true,
                    resolutionSource: "kalshi"
                ),
            ]
        )
        let settledPage = FuturesAtlasPresentation11666.build(market: settledOneLeg, now: referenceNow)
        XCTAssertEqual(settledPage.body.shape, .singleLegPredicate)
        XCTAssertEqual(settledPage.body.primaryRows.count, 1)
        XCTAssertEqual(settledPage.body.primaryRows.first?.name, "Yes")
        XCTAssertEqual(settledPage.header.primaryDisplay, .won)
        XCTAssertEqual(settledPage.header.openingChanceText, "Opening chance 38%")
        XCTAssertEqual(settledPage.detailsSheet.openingChanceValue, "38%")
        XCTAssertEqual(settledPage.detailsSheet.currentOrSettlementValue, "✓ Won")

        // Decide 10-C: an open outcome whose `observed_at` is older than 30 minutes ages to
        // `"No recent probability"` rather than printing an old quote as live.
        let staleOneLeg = makeMarket(
            id: 109918,
            name: "Will Democrats sweep all swing state Governor races",
            category: "politics",
            status: "active",
            outcomes: [
                makeOutcomeDict(
                    id: 401,
                    name: "Yes",
                    probability: 0.58,
                    openingProbability: 0.38,
                    observedAt: "2026-11-04T01:00:00Z" // 93 minutes before referenceNow
                ),
            ]
        )
        let stalePage = FuturesAtlasPresentation11666.build(market: staleOneLeg, now: referenceNow)
        XCTAssertEqual(stalePage.header.primaryDisplay.primaryLabel, "No recent probability")
    }

    // MARK: - 6. Chart Agreement Expectation Follows Selected Outcome & Withholds Stale Headline (#9387 + Decide 10-C)

    func testChartExpectationFollowsSelectedOutcomeAndWithholdsStaleHeadlineProbability() throws {
        let market = makeMarket(
            id: 108629,
            name: "Closest Governor race in 2026",
            category: "politics",
            status: "active",
            outcomes: [
                makeOutcomeDict(
                    id: 1,
                    name: "Florida",
                    probability: 0.29,
                    openingProbability: 0.24,
                    observedAt: "2026-11-04T02:25:00Z"
                ),
                makeOutcomeDict(
                    id: 2,
                    name: "Georgia",
                    probability: 0.21,
                    openingProbability: 0.22,
                    observedAt: "2026-11-04T02:25:00Z"
                ),
                makeOutcomeDict(
                    id: 3,
                    name: "Wisconsin",
                    probability: 0.16,
                    openingProbability: 0.15,
                    observedAt: "2026-11-04T01:00:00Z" // > 30m before referenceNow (stale)
                ),
            ]
        )

        // Default headline follows leading outcome (id: 1, probability: 0.29)
        let defaultPresentation = FuturesAtlasPresentation11666.build(market: market, now: referenceNow)
        let defaultExpectation = try XCTUnwrap(
            FuturesAtlasPresentation11666.chartExpectation(
                market: market,
                presentation: defaultPresentation,
                representation: .verifiedTitle
            )
        )
        XCTAssertEqual(defaultExpectation.heroOutcomeId, 1)
        XCTAssertEqual(defaultExpectation.heroProbability, 0.29)

        // Picking another fresh outcome updates the chart expectation to follow the pick (id: 2, probability: 0.21)
        let pickedPresentation = FuturesAtlasPresentation11666.build(
            market: market,
            selectedOutcomeId: 2,
            now: referenceNow
        )
        let pickedExpectation = try XCTUnwrap(
            FuturesAtlasPresentation11666.chartExpectation(
                market: market,
                presentation: pickedPresentation,
                representation: .verifiedTitle
            )
        )
        XCTAssertEqual(pickedExpectation.heroOutcomeId, 2)
        XCTAssertEqual(pickedExpectation.heroProbability, 0.21)

        // Picking a stale outcome whose headline reads "No recent probability" withholds heroProbability (nil)
        let stalePickedPresentation = FuturesAtlasPresentation11666.build(
            market: market,
            selectedOutcomeId: 3,
            now: referenceNow
        )
        XCTAssertEqual(stalePickedPresentation.header.primaryDisplay.primaryLabel, "No recent probability")
        let staleExpectation = try XCTUnwrap(
            FuturesAtlasPresentation11666.chartExpectation(
                market: market,
                presentation: stalePickedPresentation,
                representation: .verifiedTitle
            )
        )
        XCTAssertEqual(staleExpectation.heroOutcomeId, 3)
        XCTAssertNil(staleExpectation.heroProbability)

        // Source representation continues to pass nil expectation
        XCTAssertNil(
            FuturesAtlasPresentation11666.chartExpectation(
                market: market,
                presentation: defaultPresentation,
                representation: .source
            )
        )
    }

    func testWithheldCurrentOutcomeIdsWithholdsStaleSourceModeChartProbabilities108629() throws {
        // Production 108629 ("Closest Governor race"): representation is "source", and Kansas
        // (1594085) + Nebraska (235955688) are older than 30 minutes while Alaska (235955685) is fresh.
        let market = makeMarket(
            id: 108629,
            name: "Closest Governor race",
            category: "politics",
            status: "open",
            outcomes: [
                makeOutcomeDict(
                    id: 1594085,
                    name: "Kansas",
                    probability: 0.92125984,
                    openingProbability: 0.85,
                    observedAt: "2026-11-04T00:35:00Z" // 1h50m before referenceNow (stale)
                ),
                makeOutcomeDict(
                    id: 235955685,
                    name: "Alaska",
                    probability: 0.0246063,
                    openingProbability: 0.03,
                    observedAt: "2026-11-04T02:20:00Z" // 13m before referenceNow (fresh)
                ),
                makeOutcomeDict(
                    id: 235955688,
                    name: "Nebraska",
                    probability: 0.01968504,
                    openingProbability: 0.02,
                    observedAt: "2026-11-03T20:30:00Z" // 6h before referenceNow (stale)
                ),
            ]
        )

        let presentation = FuturesAtlasPresentation11666.build(market: market, now: referenceNow)
        XCTAssertEqual(presentation.header.selectedOutcomeId, 1594085)
        XCTAssertEqual(presentation.header.primaryDisplay.primaryLabel, "No recent probability")

        let withheldIds = FuturesAtlasPresentation11666.withheldCurrentOutcomeIds(presentation: presentation)
        XCTAssertEqual(withheldIds, Set([1594085, 235955688]))

        let timelineOutcomesJSON: [[String: Any]] = [
            [
                "id": 1594085,
                "name": "Kansas",
                "current_probability": 0.92125984,
                "probability_change_24h": 0.01,
            ],
            [
                "id": 235955685,
                "name": "Alaska",
                "current_probability": 0.0246063,
                "probability_change_24h": -0.005,
            ],
            [
                "id": 235955688,
                "name": "Nebraska",
                "current_probability": 0.01968504,
                "probability_change_24h": 0.0,
            ],
        ]
        let data = try JSONSerialization.data(withJSONObject: timelineOutcomesJSON)
        let rawOutcomes = try makeDecoder().decode([TimelineOutcomeMeta].self, from: data)

        let resolved = EvolutionChartView.resolveServedOutcomes(
            rawOutcomes,
            withholdsCurrent: false,
            withheldCurrentOutcomeIds: withheldIds
        )
        XCTAssertEqual(resolved.count, 3)
        // Stale Kansas and Nebraska have their currentProbability withheld (nil -> "—")
        XCTAssertNil(resolved[0].currentProbability)
        XCTAssertNil(resolved[0].probabilityChange24h)
        // Fresh Alaska keeps its currentProbability (2%)
        XCTAssertEqual(resolved[1].currentProbability ?? 0, 0.0246063, accuracy: 0.0001)
        // Stale Nebraska has its currentProbability withheld (nil -> "—")
        XCTAssertNil(resolved[2].currentProbability)

        let percents = EvolutionLeaderboardGeometry.renderedPercents(forServedField: resolved)
        XCTAssertEqual(percents, [nil, 2, nil])
        XCTAssertEqual(
            EvolutionLeaderboardGeometry.probLabel(resolved[0].currentProbability.map { $0 * 100 }, renderedPercent: percents[0]),
            "—"
        )
        XCTAssertEqual(
            EvolutionLeaderboardGeometry.probLabel(resolved[1].currentProbability.map { $0 * 100 }, renderedPercent: percents[1]),
            "2%"
        )
    }

    // MARK: - 7. 390px Default & Accessibility3 Snapshot Verification

    @MainActor
    func testRenderFuturesAtlas390pxDefaultAndAccessibility3Snapshots() throws {
        let governorField = makeMarket(
            id: 108629,
            name: "Closest Governor race in 2026",
            category: "politics",
            hookDescription: "Florida leads the 24-state field at 29%, ahead of Georgia and Wisconsin.",
            outcomes: [
                makeOutcomeDict(id: 1, name: "Florida", probability: 0.29, openingProbability: 0.24, change24h: 0.02),
                makeOutcomeDict(id: 2, name: "Georgia", probability: 0.21, openingProbability: 0.22, change24h: -0.01),
                makeOutcomeDict(id: 3, name: "Wisconsin", probability: 0.16, openingProbability: 0.15, change24h: 0.01),
                makeOutcomeDict(id: 4, name: "Arizona", probability: 0.12, openingProbability: 0.13),
                makeOutcomeDict(id: 5, name: "Michigan", probability: 0.09, openingProbability: 0.10),
            ]
        )
        let denverSnow = makeMarket(
            id: 65536371,
            name: "Snow in Denver in Dec 2026",
            category: "weather",
            mutuallyExclusive: false,
            outcomes: [
                makeOutcomeDict(id: 11, name: "Above 0 inches", probability: 0.96, openingProbability: 0.94),
                makeOutcomeDict(id: 12, name: "Above 2 inches", probability: 0.88, openingProbability: 0.85),
                makeOutcomeDict(id: 10, name: "Above 6 inches", probability: 0.64, openingProbability: 0.58),
                makeOutcomeDict(id: 13, name: "Above 10 inches", probability: 0.34, openingProbability: 0.31),
            ]
        )
        let cfpQualifiers = makeMarket(
            id: 227,
            name: "College Football Playoff Qualifiers",
            category: "football",
            mutuallyExclusive: false,
            outcomes: [
                makeOutcomeDict(id: 101, name: "Miami (FL)", probability: 0.94, openingProbability: 0.72),
                makeOutcomeDict(id: 102, name: "Oregon", probability: 0.92, openingProbability: 0.81),
                makeOutcomeDict(id: 103, name: "Ohio State", probability: 0.89, openingProbability: 0.86),
                makeOutcomeDict(id: 104, name: "Texas", probability: 0.84, openingProbability: 0.79),
            ]
        )
        let georgiaSettled = makeMarket(
            id: 108645,
            name: "Georgia Governor winner",
            category: "politics",
            status: "resolved",
            mutuallyExclusive: true,
            outcomes: [
                makeOutcomeDict(
                    id: 301,
                    name: "Keisha Lance Bottoms",
                    probability: 1.0,
                    openingProbability: 0.56,
                    isWinner: true,
                    resolutionSource: "kalshi"
                ),
                makeOutcomeDict(
                    id: 302,
                    name: "Burt Jones",
                    probability: 0.0,
                    openingProbability: 0.45,
                    isWinner: false,
                    resolutionSource: "kalshi"
                ),
            ]
        )

        let markets = [governorField, denverSnow, cfpQualifiers, georgiaSettled]
        let presentations = markets.map { FuturesAtlasPresentation11666.build(market: $0, now: referenceNow) }

        let stack = VStack(alignment: .leading, spacing: 20) {
            ForEach(Array(presentations.enumerated()), id: \.offset) { idx, p in
                VStack(alignment: .leading, spacing: 12) {
                    FuturesAtlasHeaderCardView11666(
                        header: p.header,
                        marketId: markets[idx].id,
                        marketName: markets[idx].name,
                        shareMessage: "\(markets[idx].name) on Bain Luck",
                        onShare: {},
                        onOpenDetails: {}
                    )
                    FuturesAtlasBodyCardView11666(
                        bodyModel: p.body,
                        selectedOutcomeId: p.header.selectedOutcomeId,
                        onSelectOutcome: { _ in },
                        onOpenFullField: {}
                    )
                    if let attr = p.attribution {
                        FuturesAtlasAttributionFooterView11666(attribution: attr)
                    }
                }
            }
        }
        .padding(16)
        .frame(width: 390)
        .background(DS.trackBg)
        .environment(\.colorScheme, .light)

        let defaultView = stack.environment(\.dynamicTypeSize, .large)
        let a11yView = stack.environment(\.dynamicTypeSize, .accessibility3)

        let defaultRenderer = rendererForMeasurement(defaultView)
        let a11yRenderer = rendererForMeasurement(a11yView)

        let defaultImage = try XCTUnwrap(defaultRenderer.uiImage)
        let a11yImage = try XCTUnwrap(a11yRenderer.uiImage)

        XCTAssertEqual(Int(defaultImage.size.width), 390)
        XCTAssertEqual(Int(a11yImage.size.width), 390)
        XCTAssertGreaterThan(defaultImage.size.height, 900)
        XCTAssertGreaterThan(a11yImage.size.height, defaultImage.size.height)

        let outDir = URL(fileURLWithPath: "/tmp/futures-atlas-11666", isDirectory: true)
        try FileManager.default.createDirectory(at: outDir, withIntermediateDirectories: true)
        try XCTUnwrap(defaultImage.pngData()).write(
            to: outDir.appendingPathComponent("futures-atlas-default-390px.png")
        )
        try XCTUnwrap(a11yImage.pngData()).write(
            to: outDir.appendingPathComponent("futures-atlas-a11y-390px.png")
        )
    }
}
