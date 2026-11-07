import XCTest
@testable import Bain_Luck

/// #11666 Step E6b — Native Event-page Atlas NHL story cards (`icehockey_nhl`),
/// mirroring web `#11974` Step E6b (`frontend/lib/nhlEventCards.ts`), gated behind
/// `ReleaseSurfaces.isEventPageAtlasEnabled()`.
final class EventAtlasNhlCardsE6b_11666Tests: XCTestCase {

    func testGatesNhlAtlasCardsStrictlyOnAtlasEnabledAndIcehockeyNhl() {
        XCTAssertFalse(EventAtlasNhlCards11666.applies(sportKey: "icehockey_nhl", atlasEnabled: false))
        XCTAssertTrue(EventAtlasNhlCards11666.applies(sportKey: "icehockey_nhl", atlasEnabled: true))
        XCTAssertFalse(EventAtlasNhlCards11666.applies(sportKey: "basketball_nba", atlasEnabled: true))
        XCTAssertFalse(EventAtlasNhlCards11666.applies(sportKey: nil, atlasEnabled: true))
    }

    @MainActor
    func testBuildsWhoFoundTheNetAndWithholdsUnblendedMultiSourceProbabilities() throws {
        let now = try XCTUnwrap("2026-11-06T04:00:00Z".asDate)
        let decoder = JSONDecoder()
        decoder.keyDecodingStrategy = .convertFromSnakeCase

        let propsJSON = """
        [
            {
                "market_name": "TOR at BOS: Goals",
                "outcome_name": "Auston Matthews: 1+",
                "threshold": 1.0,
                "over_probability": 0.48,
                "pregame_mark": 0.44,
                "observed_at": "2026-11-05T23:55:00Z",
                "source": "kalshi",
                "player_team": "away",
                "actual": 2.0,
                "hit": true
            },
            {
                "market_name": "TOR at BOS: Goals",
                "outcome_name": "David Pastrnak: 1+",
                "threshold": 1.0,
                "over_probability": 0.50,
                "pregame_mark": 0.42,
                "observed_at": "2026-11-05T23:55:00Z",
                "source": "kalshi",
                "player_team": "home",
                "actual": 1.0,
                "hit": true
            },
            {
                "market_name": "TOR at BOS: Goals",
                "outcome_name": "David Pastrnak: 1+",
                "threshold": 1.0,
                "over_probability": 0.46,
                "pregame_mark": 0.36,
                "observed_at": "2026-11-05T23:56:00Z",
                "source": "polymarket",
                "player_team": "home",
                "actual": 1.0,
                "hit": true
            },
            {
                "market_name": "TOR at BOS: Goals",
                "outcome_name": "Brad Marchand: 1+",
                "threshold": 1.0,
                "over_probability": 0.29,
                "pregame_mark": 0.25,
                "observed_at": "2026-11-05T23:55:00Z",
                "source": "blended",
                "player_team": "home",
                "actual": 1.0,
                "hit": true
            }
        ]
        """
        let props = try decoder.decode([GameMarketPlayerProp].self, from: Data(propsJSON.utf8))
        let card = try XCTUnwrap(
            EventAtlasNhlCards11666.buildScoringCard(
                props: props,
                status: "completed",
                commenceTime: "2026-11-06T00:00:00Z".asDate,
                homeTeam: "Boston Bruins",
                awayTeam: "Toronto Maple Leafs",
                now: now
            )
        )
        XCTAssertEqual(card.story, .scored)
        XCTAssertEqual(card.title, "Who found the net?")
        XCTAssertEqual(card.entries.count, 3)

        // Matthews scored 2 goals (single source -> keeps 0.44 pregameChance)
        XCTAssertEqual(card.entries[0].player, "Auston Matthews")
        XCTAssertEqual(card.entries[0].actualGoals, 2)
        XCTAssertEqual(card.entries[0].pregameChance ?? 0, 0.44, accuracy: 1e-6)
        XCTAssertEqual(card.entries[0].hit, true)

        // Marchand scored 1 goal with blended pregameChance 0.25 (sorts ahead of Pastrnak whose pregameChance is nil)
        XCTAssertEqual(card.entries[1].player, "Brad Marchand")
        XCTAssertEqual(card.entries[1].actualGoals, 1)
        XCTAssertEqual(card.entries[1].pregameChance ?? 0, 0.25, accuracy: 1e-6)
        XCTAssertEqual(card.entries[1].source, "blended")

        // Pastrnak had two unblended sources (kalshi 0.42, polymarket 0.36) -> pregameChance withheld (nil), never averaged
        XCTAssertEqual(card.entries[2].player, "David Pastrnak")
        XCTAssertEqual(card.entries[2].actualGoals, 1)
        XCTAssertNil(card.entries[2].pregameChance)
        XCTAssertNil(card.entries[2].source)
        XCTAssertEqual(card.entries[2].sourceCount, 2)

        // Verify reader details sheet model for Matthews
        let details = try XCTUnwrap(
            EventAtlasStoryCards11666.readerDetailsModel(
                rowID: card.entries[0].id,
                cards: [.nhlScoring(card)],
                rows: [:],
                awayName: "Maple Leafs",
                homeName: "Bruins"
            )
        )
        XCTAssertEqual(details.outcomeTitle, "Auston Matthews: 1+ goals")
        XCTAssertEqual(details.primaryReadingLabel, "Result")
        XCTAssertEqual(details.primaryReadingValue, "✓ Won · 2 goals")
        XCTAssertEqual(details.pregameBaseline, "44%")
        XCTAssertEqual(details.sourceLabel, "Kalshi")
    }

    @MainActor
    func testBuildsGoalTotalsAndPuckLineMarginCardsFromTypedQuestionMatrix() throws {
        let now = try XCTUnwrap("2026-11-06T04:00:00Z".asDate)
        let decoder = JSONDecoder()
        decoder.keyDecodingStrategy = .convertFromSnakeCase

        let matrixJSON = """
        {
            "contract": "10238.v1",
            "display_scope": "game",
            "questions": [
                {
                    "question_key": "q:total:5.5",
                    "label": "Total Goals O/U 5.5",
                    "market_name": "Total Goals",
                    "typing": { "state": "typed" },
                    "kind": "count_threshold",
                    "quantity": { "key": "goals" },
                    "subject": { "side": "game" },
                    "period": { "key": "full_game" },
                    "predicate": { "relation": "ge", "line": 5.5 },
                    "options": [
                        {
                            "option_key": "o:101",
                            "label": "Over 5.5 goals",
                            "side": "over",
                            "contributor_outcome_ids": [101],
                            "published": { "value_state": "not_quoted", "source": "kalshi" },
                            "pregame_reading": {
                                "state": "available",
                                "basis": "pregame_pin",
                                "outcome_id": 101,
                                "probability": 0.62,
                                "observed_at": "2026-11-05T23:50:00Z"
                            },
                            "result": { "state": "won" }
                        }
                    ]
                },
                {
                    "question_key": "q:total:6.5",
                    "label": "Total Goals O/U 6.5",
                    "market_name": "Total Goals",
                    "typing": { "state": "typed" },
                    "kind": "count_threshold",
                    "quantity": { "key": "goals" },
                    "subject": { "side": "game" },
                    "period": { "key": "full_game" },
                    "predicate": { "relation": "ge", "line": 6.5 },
                    "options": [
                        {
                            "option_key": "o:102",
                            "label": "Over 6.5 goals",
                            "side": "over",
                            "contributor_outcome_ids": [102],
                            "published": { "value_state": "not_quoted", "source": "kalshi" },
                            "pregame_reading": {
                                "state": "available",
                                "basis": "pregame_pin",
                                "outcome_id": 102,
                                "probability": 0.44,
                                "observed_at": "2026-11-05T23:50:00Z"
                            },
                            "result": { "state": "lost" }
                        }
                    ]
                },
                {
                    "question_key": "q:total:7.5",
                    "label": "Total Goals O/U 7.5",
                    "market_name": "Total Goals",
                    "typing": { "state": "typed" },
                    "kind": "count_threshold",
                    "quantity": { "key": "goals" },
                    "subject": { "side": "game" },
                    "period": { "key": "full_game" },
                    "predicate": { "relation": "ge", "line": 7.5 },
                    "options": [
                        {
                            "option_key": "o:103",
                            "label": "Over 7.5 goals",
                            "side": "over",
                            "contributor_outcome_ids": [103],
                            "published": { "value_state": "not_quoted", "source": "kalshi" },
                            "pregame_reading": {
                                "state": "available",
                                "basis": "pregame_pin",
                                "outcome_id": 103,
                                "probability": 0.24,
                                "observed_at": "2026-11-05T23:50:00Z"
                            },
                            "result": { "state": "lost" }
                        }
                    ]
                }
            ]
        }
        """
        let matrix = try decoder.decode(EventQuestionMatrix.self, from: Data(matrixJSON.utf8))
        let input = NBALadderCard9483.Input(
            matrix: matrix,
            status: "completed",
            commenceTime: "2026-11-06T00:00:00Z".asDate,
            homeScore: 4,
            awayScore: 2,
            pregameProjection: nil,
            homeShort: "BOS",
            awayShort: "TOR",
            now: now
        )
        let totals = try XCTUnwrap(EventAtlasNhlCards11666.buildGoalTotalsCard(input))
        XCTAssertEqual(totals.family, .total)
        XCTAssertEqual(totals.points.map(\.label), ["Over 5.5 goals", "Over 6.5 goals", "Over 7.5 goals"])
        XCTAssertEqual(totals.points[0].chance ?? 0, 0.62, accuracy: 1e-6)
        XCTAssertEqual(totals.points[0].result, true)
        XCTAssertEqual(totals.actual, 6.0)
    }
}
