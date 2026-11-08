import SwiftUI
import XCTest
@testable import Bain_Luck

@MainActor
final class EventAtlasFootballCards11666Tests: XCTestCase {

    func testAppliesOnlyToNFLWhenAtlasEnabled() {
        XCTAssertFalse(EventAtlasFootballCards11666.applies(sportKey: "americanfootball_nfl", atlasEnabled: false))
        XCTAssertTrue(EventAtlasFootballCards11666.applies(sportKey: "americanfootball_nfl", atlasEnabled: true))
        XCTAssertFalse(EventAtlasFootballCards11666.applies(sportKey: "americanfootball_ncaaf", atlasEnabled: true))
        XCTAssertFalse(EventAtlasFootballCards11666.applies(sportKey: "basketball_nba", atlasEnabled: true))
        XCTAssertFalse(EventAtlasFootballCards11666.applies(sportKey: nil, atlasEnabled: true))
    }

    func testPeriodWinnersBuildsQ1ThroughQ4ExcludesOvertimeAndUsesStoredLineScore() throws {
        let now = ISO8601DateFormatter().date(from: "2026-11-08T21:30:00Z")!
        let commence = ISO8601DateFormatter().date(from: "2026-11-08T18:00:00Z")!
        let periodMarkets: [GameMarketOutcome] = [
            GameMarketOutcome(
                marketName: "1st Quarter Winner",
                outcomeName: "Philadelphia Eagles",
                probability: 1.0,
                source: "kalshi",
                threshold: nil,
                overProbability: nil,
                marketType: "moneyline",
                movement: nil,
                period: "Q1",
                isWinner: true,
                resolutionSource: "api_settlement",
                observedAt: "2026-11-08T18:45:00Z",
                pregameMark: 0.52
            ),
            GameMarketOutcome(
                marketName: "1st Quarter Winner",
                outcomeName: "Dallas Cowboys",
                probability: 0.0,
                source: "kalshi",
                threshold: nil,
                overProbability: nil,
                marketType: "moneyline",
                movement: nil,
                period: "Q1",
                isWinner: false,
                resolutionSource: "api_settlement",
                observedAt: "2026-11-08T18:45:00Z",
                pregameMark: 0.34
            ),
            GameMarketOutcome(
                marketName: "1st Quarter Winner",
                outcomeName: "Tie",
                probability: 0.0,
                source: "kalshi",
                threshold: nil,
                overProbability: nil,
                marketType: "moneyline",
                movement: nil,
                period: "Q1",
                isWinner: false,
                resolutionSource: "api_settlement",
                observedAt: "2026-11-08T18:45:00Z",
                pregameMark: 0.18
            ),
            GameMarketOutcome(
                marketName: "2nd Quarter Winner",
                outcomeName: "Dallas Cowboys",
                probability: 1.0,
                source: "kalshi",
                threshold: nil,
                overProbability: nil,
                marketType: "moneyline",
                movement: nil,
                period: "Q2",
                isWinner: nil,
                resolutionSource: nil,
                observedAt: "2026-11-08T19:30:00Z",
                pregameMark: 0.44
            ),
            // Overtime row must be excluded
            GameMarketOutcome(
                marketName: "Overtime Winner",
                outcomeName: "Philadelphia Eagles",
                probability: 1.0,
                source: "kalshi",
                threshold: nil,
                overProbability: nil,
                marketType: "moneyline",
                movement: nil,
                period: "OT",
                isWinner: true,
                resolutionSource: "api_settlement",
                observedAt: "2026-11-08T21:15:00Z",
                pregameMark: 0.55
            )
        ]

        let gm = GameMarketsResponse(
            eventId: 14780562,
            homeTeam: "Dallas Cowboys",
            awayTeam: "Philadelphia Eagles",
            status: "completed",
            homeScore: 20,
            awayScore: 28,
            playerProps: nil,
            spreads: nil,
            totals: nil,
            teamTotals: nil,
            periodMarkets: periodMarkets,
            other: nil,
            pace: nil
        )
        let boxScore = EventBoxScoreData(
            homePeriodScores: [3, 10, 0, 7],
            awayPeriodScores: [7, 7, 7, 7]
        )

        let card = try XCTUnwrap(
            EventAtlasFootballCards11666.buildPeriodWinnersCard(
                status: "completed",
                commenceTime: commence,
                homeTeam: "Dallas Cowboys",
                awayTeam: "Philadelphia Eagles",
                homeShort: "Cowboys",
                awayShort: "Eagles",
                homeScore: 20,
                awayScore: 28,
                boxScoreData: boxScore,
                gameMarkets: gm,
                now: now
            )
        )

        XCTAssertEqual(card.panels.map(\.quarter), [.q1, .q2])
        let q1 = card.panels[0]
        XCTAssertEqual(q1.awayScore, 7)
        XCTAssertEqual(q1.homeScore, 3)
        XCTAssertEqual(q1.legs.count, 3)
        // Independent pregame chances are preserved as traded (52% + 34% + 18% = 104%, never normalized)
        XCTAssertEqual(q1.legs[0].pregameChance ?? 0, 0.52, accuracy: 0.0001)
        XCTAssertEqual(q1.legs[0].verdict, .won)
        XCTAssertEqual(q1.legs[1].pregameChance ?? 0, 0.34, accuracy: 0.0001)
        XCTAssertEqual(q1.legs[1].verdict, .lost)
        XCTAssertEqual(q1.legs[2].pregameChance ?? 0, 0.18, accuracy: 0.0001)

        // Unconfirmed Q2 row shows .unconfirmed after final, never .lost
        let q2 = card.panels[1]
        XCTAssertEqual(q2.legs.first?.verdict, .unconfirmed)

        // Details sheet routing through EventAtlasStoryCards11666.readerDetailsModel
        let details = try XCTUnwrap(
            EventAtlasStoryCards11666.readerDetailsModel(
                rowID: q1.legs[0].id,
                cards: [.nflPeriodWinners(card)],
                rows: [:],
                awayName: "Eagles",
                homeName: "Cowboys"
            )
        )
        XCTAssertEqual(details.outcomeTitle, "First quarter · Eagles")
        XCTAssertEqual(details.primaryReadingLabel, "Result")
        XCTAssertEqual(details.primaryReadingValue, "✓ Won · Eagles 7 – 3 Cowboys")
        XCTAssertEqual(details.pregameBaseline, "52%")
        XCTAssertEqual(details.sourceLabel, "Kalshi")
    }

    func testPeriodWinnersAgesOutLiveQuotesToNoRecentProbability() throws {
        let commence = ISO8601DateFormatter().date(from: "2026-11-08T18:00:00Z")!
        let freshNow = ISO8601DateFormatter().date(from: "2026-11-08T18:20:00Z")!
        let agedNow = ISO8601DateFormatter().date(from: "2026-11-08T19:05:00Z")!

        let gm = GameMarketsResponse(
            eventId: 14780562,
            homeTeam: "Dallas Cowboys",
            awayTeam: "Philadelphia Eagles",
            status: "live",
            homeScore: 3,
            awayScore: 7,
            playerProps: nil,
            spreads: nil,
            totals: nil,
            teamTotals: nil,
            periodMarkets: [
                GameMarketOutcome(
                    marketName: "1st Quarter Winner",
                    outcomeName: "Philadelphia Eagles",
                    probability: 0.78,
                    source: "kalshi",
                    threshold: nil,
                    overProbability: nil,
                    marketType: "moneyline",
                    movement: nil,
                    period: "Q1",
                    isWinner: nil,
                    resolutionSource: nil,
                    observedAt: "2026-11-08T18:15:00Z",
                    pregameMark: 0.52
                )
            ],
            other: nil,
            pace: nil
        )

        let freshCard = try XCTUnwrap(
            EventAtlasFootballCards11666.buildPeriodWinnersCard(
                status: "live",
                commenceTime: commence,
                homeTeam: "Dallas Cowboys",
                awayTeam: "Philadelphia Eagles",
                homeShort: "Cowboys",
                awayShort: "Eagles",
                homeScore: 3,
                awayScore: 7,
                boxScoreData: nil,
                gameMarkets: gm,
                now: freshNow
            )
        )
        let freshLeg = try XCTUnwrap(freshCard.panels.first?.legs.first)
        XCTAssertEqual(freshLeg.liveChance ?? 0, 0.78, accuracy: 0.0001)
        XCTAssertFalse(freshLeg.isStaleLive)

        let agedCard = freshCard.current(at: agedNow)
        let agedLeg = try XCTUnwrap(agedCard.panels.first?.legs.first)
        XCTAssertNil(agedLeg.liveChance)
        XCTAssertTrue(agedLeg.isStaleLive)
        let agedDetails = EventAtlasFootballCards11666.detailsModel(
            for: agedLeg,
            panel: agedCard.panels[0],
            card: agedCard
        )
        XCTAssertEqual(agedDetails.primaryReadingLabel, "Reading")
        XCTAssertEqual(agedDetails.primaryReadingValue, EventAtlasStates11666.noRecentPrice)
        XCTAssertEqual(agedDetails.pregameBaseline, "52%")
    }

    func testPairedMilestonesBuildsTeamSacksAndFieldGoalsRefusesFlatLaddersAndRoutesDetails() throws {
        let commence = ISO8601DateFormatter().date(from: "2026-11-08T18:00:00Z")!
        let now = ISO8601DateFormatter().date(from: "2026-11-08T21:40:00Z")!

        let props: [GameMarketPlayerProp] = [
            // Away (Eagles) descending pregame chances
            GameMarketPlayerProp(
                marketName: "Team Sacks",
                outcomeName: "Philadelphia Eagles: 2+",
                threshold: 2,
                overProbability: 1.0,
                source: "kalshi",
                movement: nil,
                playerHeadshot: nil,
                playerTeam: "PHI",
                actual: 4,
                hit: true,
                pregameMark: 0.72,
                observedAt: "2026-11-08T21:00:00Z"
            ),
            GameMarketPlayerProp(
                marketName: "Team Sacks",
                outcomeName: "Philadelphia Eagles: 3+",
                threshold: 3,
                overProbability: 1.0,
                source: "kalshi",
                movement: nil,
                playerHeadshot: nil,
                playerTeam: "PHI",
                actual: 4,
                hit: true,
                pregameMark: 0.48,
                observedAt: "2026-11-08T21:00:00Z"
            ),
            GameMarketPlayerProp(
                marketName: "Team Sacks",
                outcomeName: "Philadelphia Eagles: 4+",
                threshold: 4,
                overProbability: 1.0,
                source: "kalshi",
                movement: nil,
                playerHeadshot: nil,
                playerTeam: "PHI",
                actual: 4,
                hit: true,
                pregameMark: 0.26,
                observedAt: "2026-11-08T21:00:00Z"
            ),
            // Home (Cowboys) flat ladder across 3 rungs -> pregame chances refused (#5137)
            GameMarketPlayerProp(
                marketName: "Team Sacks",
                outcomeName: "Dallas Cowboys: 2+",
                threshold: 2,
                overProbability: 0.0,
                source: "kalshi",
                movement: nil,
                playerHeadshot: nil,
                playerTeam: "DAL",
                actual: 1,
                hit: false,
                pregameMark: 0.50,
                observedAt: "2026-11-08T21:00:00Z"
            ),
            GameMarketPlayerProp(
                marketName: "Team Sacks",
                outcomeName: "Dallas Cowboys: 3+",
                threshold: 3,
                overProbability: 0.0,
                source: "kalshi",
                movement: nil,
                playerHeadshot: nil,
                playerTeam: "DAL",
                actual: 1,
                hit: false,
                pregameMark: 0.50,
                observedAt: "2026-11-08T21:00:00Z"
            ),
            GameMarketPlayerProp(
                marketName: "Team Sacks",
                outcomeName: "Dallas Cowboys: 4+",
                threshold: 4,
                overProbability: 0.0,
                source: "kalshi",
                movement: nil,
                playerHeadshot: nil,
                playerTeam: "DAL",
                actual: 1,
                hit: false,
                pregameMark: 0.50,
                observedAt: "2026-11-08T21:00:00Z"
            )
        ]

        let gm = GameMarketsResponse(
            eventId: 14780562,
            homeTeam: "Dallas Cowboys",
            awayTeam: "Philadelphia Eagles",
            status: "completed",
            homeScore: 20,
            awayScore: 28,
            playerProps: props,
            spreads: nil,
            totals: nil,
            teamTotals: nil,
            periodMarkets: nil,
            other: nil,
            pace: nil
        )

        let sacksCard = try XCTUnwrap(
            EventAtlasFootballCards11666.buildPairedMilestonesCard(
                family: .sacks,
                status: "completed",
                commenceTime: commence,
                homeTeam: "Dallas Cowboys",
                awayTeam: "Philadelphia Eagles",
                homeShort: "Cowboys",
                awayShort: "Eagles",
                gameMarkets: gm,
                now: now
            )
        )

        XCTAssertEqual(sacksCard.title, "Pressure on the passer")
        XCTAssertEqual(sacksCard.groups.map(\.threshold), [2, 3, 4])
        // Away keeps valid descending pregame chances
        XCTAssertEqual(sacksCard.groups[0].away?.pregameChance ?? 0, 0.72, accuracy: 0.0001)
        XCTAssertEqual(sacksCard.groups[0].away?.verdict, .won)
        // Home flat ladder is refused (#5137) -> pregameChance is nil while verdict remains .lost
        XCTAssertNil(sacksCard.groups[0].home?.pregameChance)
        XCTAssertEqual(sacksCard.groups[0].home?.verdict, .lost)

        let awaySlot = try XCTUnwrap(sacksCard.groups[1].away)
        let details = try XCTUnwrap(
            EventAtlasStoryCards11666.readerDetailsModel(
                rowID: awaySlot.id,
                cards: [.nflPairedMilestones(sacksCard)],
                rows: [:],
                awayName: "Eagles",
                homeName: "Cowboys"
            )
        )
        XCTAssertEqual(details.outcomeTitle, "Eagles: 3+ sacks")
        XCTAssertEqual(details.primaryReadingLabel, "Result")
        XCTAssertEqual(details.primaryReadingValue, "✓ HIT · Final 4 sacks")
        XCTAssertEqual(details.pregameBaseline, "48%")
    }

    func testBeforeKickoffUsesRecentCurrentPriceIgnoresOpeningMarkAndAgesOut() throws {
        // Buccaneers @ Bears (kick-off 5:20 PM PT = 2026-11-09T01:20:00Z, read at 1:44 PM PT = 2026-11-08T21:44:00Z)
        let now = ISO8601DateFormatter().date(from: "2026-11-08T21:44:00Z")!
        let commence = ISO8601DateFormatter().date(from: "2026-11-09T01:20:00Z")!
        let heldLater = ISO8601DateFormatter().date(from: "2026-11-08T22:20:00Z")!

        // 12b: Bucs @ Bears Team Field Goals rows where pregame_mark (opening) differs from current price
        let fgProps: [GameMarketPlayerProp] = [
            GameMarketPlayerProp(
                marketName: "Tampa Bay vs Chicago: Team Field Goals",
                outcomeName: "Chicago: 1+",
                threshold: 1,
                overProbability: 0.885,
                source: "kalshi",
                movement: nil,
                playerHeadshot: nil,
                playerTeam: "CHI",
                actual: nil,
                hit: nil,
                pregameMark: 0.755,
                observedAt: "2026-11-08T21:35:00Z"
            ),
            GameMarketPlayerProp(
                marketName: "Tampa Bay vs Chicago: Team Field Goals",
                outcomeName: "Chicago: 3+",
                threshold: 3,
                overProbability: 0.265,
                source: "kalshi",
                movement: nil,
                playerHeadshot: nil,
                playerTeam: "CHI",
                actual: nil,
                hit: nil,
                pregameMark: 0.22,
                observedAt: "2026-11-08T21:35:00Z"
            ),
            GameMarketPlayerProp(
                marketName: "Tampa Bay vs Chicago: Team Field Goals",
                outcomeName: "Chicago: 4+",
                threshold: 4,
                overProbability: 0.10,
                source: "kalshi",
                movement: nil,
                playerHeadshot: nil,
                playerTeam: "CHI",
                actual: nil,
                hit: nil,
                pregameMark: 0.265,
                observedAt: "2026-11-08T21:35:00Z"
            ),
            GameMarketPlayerProp(
                marketName: "Tampa Bay vs Chicago: Team Field Goals",
                outcomeName: "Tampa Bay: 3+",
                threshold: 3,
                overProbability: 0.215,
                source: "kalshi",
                movement: nil,
                playerHeadshot: nil,
                playerTeam: "TB",
                actual: nil,
                hit: nil,
                pregameMark: nil,
                observedAt: "2026-11-08T21:35:00Z"
            ),
            GameMarketPlayerProp(
                marketName: "Tampa Bay vs Chicago: Team Field Goals",
                outcomeName: "Tampa Bay: 4+",
                threshold: 4,
                overProbability: 0.085,
                source: "kalshi",
                movement: nil,
                playerHeadshot: nil,
                playerTeam: "TB",
                actual: nil,
                hit: nil,
                pregameMark: 0.26,
                observedAt: "2026-11-08T21:35:00Z"
            ),
            // Stale pre-kickoff row (45m old) -> pregameChance must be nil ("No recent probability")
            GameMarketPlayerProp(
                marketName: "Tampa Bay vs Chicago: Team Field Goals",
                outcomeName: "Tampa Bay: 1+",
                threshold: 1,
                overProbability: 0.85,
                source: "kalshi",
                movement: nil,
                playerHeadshot: nil,
                playerTeam: "TB",
                actual: nil,
                hit: nil,
                pregameMark: 0.80,
                observedAt: "2026-11-08T20:55:00Z"
            )
        ]

        // 12a: Q1 fresh (9m old) vs Q2 stale (40m old) before kickoff
        let periodMarkets: [GameMarketOutcome] = [
            GameMarketOutcome(
                marketName: "1st Quarter Winner",
                outcomeName: "Chicago Bears",
                probability: 0.49,
                source: "polymarket",
                threshold: nil,
                overProbability: nil,
                marketType: "moneyline",
                movement: nil,
                period: "Q1",
                isWinner: nil,
                resolutionSource: nil,
                observedAt: "2026-11-08T21:35:00Z",
                pregameMark: 0.42
            ),
            GameMarketOutcome(
                marketName: "2nd Quarter Winner",
                outcomeName: "Chicago Bears",
                probability: 0.51,
                source: "polymarket",
                threshold: nil,
                overProbability: nil,
                marketType: "moneyline",
                movement: nil,
                period: "Q2",
                isWinner: nil,
                resolutionSource: nil,
                observedAt: "2026-11-08T21:00:00Z",
                pregameMark: nil
            )
        ]

        let gm = GameMarketsResponse(
            eventId: 14780575,
            homeTeam: "Chicago Bears",
            awayTeam: "Tampa Bay Buccaneers",
            status: "scheduled",
            homeScore: nil,
            awayScore: nil,
            playerProps: fgProps,
            spreads: nil,
            totals: nil,
            teamTotals: nil,
            periodMarkets: periodMarkets,
            other: nil,
            pace: nil
        )

        let fgCard = try XCTUnwrap(
            EventAtlasFootballCards11666.buildPairedMilestonesCard(
                family: .fieldGoals,
                status: "scheduled",
                commenceTime: commence,
                homeTeam: "Chicago Bears",
                awayTeam: "Tampa Bay Buccaneers",
                homeShort: "Bears",
                awayShort: "Buccaneers",
                gameMarkets: gm,
                now: now
            )
        )
        XCTAssertEqual(fgCard.phase, .before)
        XCTAssertEqual(fgCard.groups.map(\.threshold), [1, 3, 4])

        // 1. Pre-kickoff rows whose mark differs from current price show the current price (never opening mark)
        let chi1 = try XCTUnwrap(fgCard.groups[0].home?.pregameChance)
        let chi3 = try XCTUnwrap(fgCard.groups[1].home?.pregameChance)
        let chi4 = try XCTUnwrap(fgCard.groups[2].home?.pregameChance)
        XCTAssertEqual(chi1, 0.885, accuracy: 0.0001)
        XCTAssertEqual(chi3, 0.265, accuracy: 0.0001)
        XCTAssertEqual(chi4, 0.10, accuracy: 0.0001)

        let tb3 = try XCTUnwrap(fgCard.groups[1].away?.pregameChance)
        let tb4 = try XCTUnwrap(fgCard.groups[2].away?.pregameChance)
        XCTAssertEqual(tb3, 0.215, accuracy: 0.0001)
        XCTAssertEqual(tb4, 0.085, accuracy: 0.0001)

        // 2. Ladder monotonicity: higher rung never prints a higher probability than a lower rung
        XCTAssertLessThan(chi3, chi1)
        XCTAssertLessThan(chi4, chi3)
        XCTAssertLessThan(tb4, tb3)

        // 3. Stale pre-kickoff row (Tampa Bay 1+ at 20:55Z, 49m old) has nil pregameChance and reads "No recent probability"
        let tb1Slot = try XCTUnwrap(fgCard.groups[0].away)
        XCTAssertNil(tb1Slot.pregameChance)
        let staleSlotDetails = EventAtlasFootballCards11666.detailsModel(for: tb1Slot, card: fgCard)
        XCTAssertEqual(staleSlotDetails.primaryReadingValue, EventAtlasStates11666.noRecentPrice)
        XCTAssertNil(staleSlotDetails.pregameBaseline)

        // 4. Card held open past 30 minutes before kick-off ages out its pre-kickoff values
        let agedFgCard = fgCard.current(at: heldLater)
        XCTAssertNil(agedFgCard.groups[0].home?.pregameChance)
        XCTAssertNil(agedFgCard.groups[1].home?.pregameChance)
        XCTAssertNil(agedFgCard.groups[2].home?.pregameChance)

        // Verify 12a PeriodWinnersCard pre-kickoff recency and aging as well
        let periodCard = try XCTUnwrap(
            EventAtlasFootballCards11666.buildPeriodWinnersCard(
                status: "scheduled",
                commenceTime: commence,
                homeTeam: "Chicago Bears",
                awayTeam: "Tampa Bay Buccaneers",
                homeShort: "Bears",
                awayShort: "Buccaneers",
                homeScore: nil,
                awayScore: nil,
                boxScoreData: nil,
                gameMarkets: gm,
                now: now
            )
        )
        XCTAssertEqual(periodCard.phase, .before)
        // Q1 (9m old) uses current price 0.49 (not pregameMark 0.42)
        XCTAssertEqual(periodCard.panels[0].legs.first?.pregameChance ?? 0, 0.49, accuracy: 0.0001)
        // Q2 (44m old) is nil ("No recent probability")
        let q2Leg = try XCTUnwrap(periodCard.panels[1].legs.first)
        XCTAssertNil(q2Leg.pregameChance)
        let q2Details = EventAtlasFootballCards11666.detailsModel(
            for: q2Leg,
            panel: periodCard.panels[1],
            card: periodCard
        )
        XCTAssertEqual(q2Details.primaryReadingValue, EventAtlasStates11666.noRecentPrice)

        // Held open past 30m before kick-off ages Q1 as well
        let agedPeriodCard = periodCard.current(at: heldLater)
        XCTAssertNil(agedPeriodCard.panels[0].legs.first?.pregameChance)
    }

    func testCombinedYardsPreservesSignedNegativeYardageAndHandlesUnavailableSplit() throws {
        let milestone = NFLMilestoneCard9483(
            id: "barkley-rush-rec",
            player: "Saquon Barkley",
            stat: "Rushing + Receiving Yards",
            side: .away,
            basis: .pregameMark,
            rungs: [
                .init(threshold: 25, chance: 0.88, observedAt: nil, rowID: "b-25", hit: true),
                .init(threshold: 50, chance: 0.62, observedAt: nil, rowID: "b-50", hit: false),
                .init(threshold: 75, chance: 0.34, observedAt: nil, rowID: "b-75", hit: false)
            ],
            actual: 44
        )

        // Signed negative rushing (-2 yards) + receiving (46 yards) = 44 yards combined
        let signedCard = EventAtlasFootballCards11666.makeCombinedYardsCard(
            milestone: milestone,
            phase: .after,
            rushingActual: -2,
            receivingActual: 46
        )
        XCTAssertLessThan(signedCard.axisDomain.lowerBound, 0, "Axis domain must include negative rushing yardage")
        if case .decomposed(let totalYards, let formattedTotal, let ground, let air) = signedCard.splitState {
            XCTAssertEqual(totalYards, 44, accuracy: 0.001)
            XCTAssertEqual(formattedTotal, "44 yards")
            XCTAssertEqual(ground.formattedYards, "−2 yards")
            XCTAssertEqual(ground.span, .init(start: 0, end: -2))
            XCTAssertEqual(air.formattedYards, "46 yards")
            XCTAssertEqual(air.span, .init(start: -2, end: 44))
        } else {
            XCTFail("Expected decomposed signed ground + air split")
        }

        // When component actuals are not served, shows "Ground and air split unavailable" and never invents 0
        let totalOnlyCard = EventAtlasFootballCards11666.makeCombinedYardsCard(
            milestone: milestone,
            phase: .after,
            rushingActual: nil,
            receivingActual: nil
        )
        XCTAssertEqual(
            totalOnlyCard.splitState,
            .totalOnly(
                totalYards: 44,
                formattedTotal: "44 yards",
                splitUnavailableMessage: "Ground and air split unavailable"
            )
        )

        // During play with no combined actual served -> "Actual so far unavailable"
        let liveMilestoneNoActual = NFLMilestoneCard9483(
            id: "barkley-live",
            player: "Saquon Barkley",
            stat: "Rushing + Receiving Yards",
            side: .away,
            basis: .pregameMark,
            rungs: milestone.rungs,
            actual: nil
        )
        let liveCard = EventAtlasFootballCards11666.makeCombinedYardsCard(
            milestone: liveMilestoneNoActual,
            phase: .during
        )
        XCTAssertEqual(liveCard.splitState, .absent("Actual so far unavailable"))

        // Deck deduplication: a milestone dealt as .nflCombinedYards is not duplicated as .milestone
        let otherMilestone = NFLMilestoneCard9483(
            id: "hurts-pass",
            player: "Jalen Hurts",
            stat: "Passing Yards",
            side: .away,
            basis: .pregameMark,
            rungs: [.init(threshold: 200, chance: 0.65, observedAt: nil, rowID: "h-200", hit: true)],
            actual: 245
        )
        let deck = NFLEventCardDeck9483.cards(
            sportKey: "americanfootball_nfl",
            finish: nil,
            milestones: [milestone, otherMilestone],
            combinedYards: [signedCard]
        )
        XCTAssertEqual(deck.map(\.id), ["nfl:combined-yards:barkley-rush-rec", "milestone:hurts-pass"])
    }

    func testRenders390pxFootballCardsDefaultAndAccessibilitySizes() throws {
        let now = ISO8601DateFormatter().date(from: "2026-11-08T21:30:00Z")!
        let commence = ISO8601DateFormatter().date(from: "2026-11-08T18:00:00Z")!

        let periodCard = try XCTUnwrap(
            EventAtlasFootballCards11666.buildPeriodWinnersCard(
                status: "completed",
                commenceTime: commence,
                homeTeam: "Dallas Cowboys",
                awayTeam: "Philadelphia Eagles",
                homeShort: "Cowboys",
                awayShort: "Eagles",
                homeScore: 20,
                awayScore: 28,
                boxScoreData: EventBoxScoreData(homePeriodScores: [3, 10, 0, 7], awayPeriodScores: [7, 7, 7, 7]),
                gameMarkets: GameMarketsResponse(
                    eventId: 14780562,
                    homeTeam: "Dallas Cowboys",
                    awayTeam: "Philadelphia Eagles",
                    status: "completed",
                    homeScore: 20,
                    awayScore: 28,
                    playerProps: nil,
                    spreads: nil,
                    totals: nil,
                    teamTotals: nil,
                    periodMarkets: [
                        .init(marketName: "1st Quarter Winner", outcomeName: "Philadelphia Eagles", probability: 1, source: "kalshi", threshold: nil, overProbability: nil, marketType: "moneyline", movement: nil, period: "Q1", isWinner: true, resolutionSource: "api_settlement", observedAt: "2026-11-08T18:45:00Z", pregameMark: 0.52),
                        .init(marketName: "1st Quarter Winner", outcomeName: "Dallas Cowboys", probability: 0, source: "kalshi", threshold: nil, overProbability: nil, marketType: "moneyline", movement: nil, period: "Q1", isWinner: false, resolutionSource: "api_settlement", observedAt: "2026-11-08T18:45:00Z", pregameMark: 0.34),
                        .init(marketName: "2nd Quarter Winner", outcomeName: "Philadelphia Eagles", probability: 0, source: "kalshi", threshold: nil, overProbability: nil, marketType: "moneyline", movement: nil, period: "Q2", isWinner: false, resolutionSource: "api_settlement", observedAt: "2026-11-08T19:30:00Z", pregameMark: 0.48),
                        .init(marketName: "2nd Quarter Winner", outcomeName: "Dallas Cowboys", probability: 1, source: "kalshi", threshold: nil, overProbability: nil, marketType: "moneyline", movement: nil, period: "Q2", isWinner: true, resolutionSource: "api_settlement", observedAt: "2026-11-08T19:30:00Z", pregameMark: 0.41)
                    ],
                    other: nil,
                    pace: nil
                ),
                now: now
            )
        )

        let sacksCard = EventAtlasFootballCards11666.PairedMilestonesCard(
            family: .sacks,
            phase: .after,
            awayShort: "Eagles",
            homeShort: "Cowboys",
            awayActual: 4,
            homeActual: 2,
            groups: [
                .init(
                    threshold: 2,
                    targetLabel: "2+",
                    away: .init(id: "s-a-2", side: .away, teamLabel: "Eagles", threshold: 2, targetLabel: "2+", pregameChance: 0.72, liveChance: nil, observedAt: now, isStaleLive: false, verdict: .won, rawSource: "kalshi", sourceCount: 1),
                    home: .init(id: "s-h-2", side: .home, teamLabel: "Cowboys", threshold: 2, targetLabel: "2+", pregameChance: 0.64, liveChance: nil, observedAt: now, isStaleLive: false, verdict: .won, rawSource: "kalshi", sourceCount: 1)
                ),
                .init(
                    threshold: 3,
                    targetLabel: "3+",
                    away: .init(id: "s-a-3", side: .away, teamLabel: "Eagles", threshold: 3, targetLabel: "3+", pregameChance: 0.48, liveChance: nil, observedAt: now, isStaleLive: false, verdict: .won, rawSource: "kalshi", sourceCount: 1),
                    home: .init(id: "s-h-3", side: .home, teamLabel: "Cowboys", threshold: 3, targetLabel: "3+", pregameChance: 0.39, liveChance: nil, observedAt: now, isStaleLive: false, verdict: .lost, rawSource: "kalshi", sourceCount: 1)
                )
            ]
        )

        let combinedCard = EventAtlasFootballCards11666.makeCombinedYardsCard(
            milestone: NFLMilestoneCard9483(
                id: "barkley-rush-rec",
                player: "Saquon Barkley",
                stat: "Rushing + Receiving Yards",
                side: .away,
                basis: .pregameMark,
                rungs: [
                    .init(threshold: 25, chance: 0.88, observedAt: nil, rowID: "b-25", hit: true),
                    .init(threshold: 50, chance: 0.62, observedAt: nil, rowID: "b-50", hit: false),
                    .init(threshold: 75, chance: 0.34, observedAt: nil, rowID: "b-75", hit: false),
                    .init(threshold: 100, chance: 0.14, observedAt: nil, rowID: "b-100", hit: false)
                ],
                actual: 44
            ),
            phase: .after,
            rushingActual: -2,
            receivingActual: 46
        )

        let state = NFLCardDeckState9483()
        let defaultStack = VStack(alignment: .leading, spacing: 18) {
            EventAtlasFootballPeriodWinnersCardView11666(
                card: periodCard,
                awayColor: .green,
                homeColor: .blue,
                state: state,
                expanded: true
            )
            Divider()
            EventAtlasFootballPairedMilestonesCardView11666(
                card: sacksCard,
                awayColor: .green,
                homeColor: .blue,
                state: state,
                expanded: true
            )
            Divider()
            EventAtlasFootballCombinedYardsCardView11666(
                card: combinedCard,
                color: .green,
                state: state,
                expanded: true
            )
        }
        .padding(16)
        .frame(width: 390, alignment: .leading)
        .background(Color(.systemBackground))
        .environment(\.colorScheme, .light)

        let defaultRenderer = rendererForMeasurement(defaultStack)
        defaultRenderer.scale = 2.0
        let defaultImage = try XCTUnwrap(defaultRenderer.uiImage)
        XCTAssertEqual(defaultImage.size.width, 390, accuracy: 1.0)
        XCTAssertGreaterThan(defaultImage.size.height, 600)

        let a11yStack = VStack(alignment: .leading, spacing: 18) {
            EventAtlasFootballPeriodWinnersCardView11666(
                card: periodCard,
                awayColor: .green,
                homeColor: .blue,
                state: state,
                expanded: true
            )
            Divider()
            EventAtlasFootballPairedMilestonesCardView11666(
                card: sacksCard,
                awayColor: .green,
                homeColor: .blue,
                state: state,
                expanded: true
            )
        }
        .padding(16)
        .frame(width: 390, alignment: .leading)
        .background(Color(.systemBackground))
        .environment(\.colorScheme, .light)
        .environment(\.dynamicTypeSize, .accessibility3)

        let a11yRenderer = rendererForMeasurement(a11yStack)
        a11yRenderer.scale = 2.0
        let a11yImage = try XCTUnwrap(a11yRenderer.uiImage)
        XCTAssertEqual(a11yImage.size.width, 390, accuracy: 1.0)
        XCTAssertGreaterThan(a11yImage.size.height, 500)

        let outDir = URL(fileURLWithPath: "/tmp/nfl-cards-11666")
        if FileManager.default.fileExists(atPath: outDir.path) {
            try defaultImage.pngData()?.write(to: outDir.appendingPathComponent("nfl-story-cards-default-390px.png"))
            try a11yImage.pngData()?.write(to: outDir.appendingPathComponent("nfl-story-cards-a11y-390px.png"))
        }
    }
}
