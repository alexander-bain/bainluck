import XCTest
@testable import Bain_Luck

/// #4967 — an unfinished search row drew no percentage unless `current_odds` was
/// present, discarding a blend the server had already computed and served.
///
/// Two separate failures had to line up to produce the blank, and this file pins
/// both, because fixing either alone leaves the row blank:
///
/// 1. `SearchEvent` did not name `hero_probability` / `hero_probability_away`, so
///    `Decodable` dropped them in silence — the same class of defect as
///    `SearchProdFixture` (a wire shape the model does not name).
/// 2. `searchEventRow` gated the whole number on `current_odds`.
///
/// Measured on production 2026-09-10 across eight queries: of 84 unfinished rows,
/// 29 drew no number; 20 of those 29 carried a complete hero pair. The other 9
/// carry neither and must keep drawing nothing (#4794).
final class SearchHeroPercentTests: XCTestCase {

    // MARK: - The decode half

    /// `GET /api/events/search?q=real madrid` on production 2026-09-10, the
    /// `results` entry for event 15307707, VERBATIM and untrimmed.
    ///
    /// Real Madrid @ Atletico, scheduled, La Liga. It is the specimen because it
    /// carries **no `current_odds` key at all** while serving a complete hero pair
    /// — the exact shape that rendered blank. Nothing is stripped, for the reason
    /// `SearchProdFixture` states: the defect was keys the decoder did not expect,
    /// so trimming is a guess made by the judgement that already missed them.
    private static let realMadridRowJSON = #"""
    {
      "query": "real madrid",
      "teams": [],
      "futures": [],
      "results": [
        {
          "id": 15307707,
          "external_id": null,
          "sport": "soccer_spain_la_liga",
          "sport_name": "La Liga - Spain",
          "home_team": "Atletico",
          "away_team": "Real Madrid",
          "commence_time": "2026-09-20T17:15:00+00:00",
          "completed_at": null,
          "status": "scheduled",
          "home_score": null,
          "away_score": null,
          "metadata": {
            "gender": "men",
            "level": "professional",
            "league": "La_Liga",
            "importance": "regular_season"
          },
          "espn": {
            "probability_sources": {
              "kalshi": 0.375
            }
          },
          "win_probability_sources": {
            "kalshi": {
              "value": 0.375,
              "display_name": "Kalshi",
              "type": "market",
              "color": "#22c55e",
              "updated_at": "2026-09-10T04:50:06.462338+00:00"
            }
          },
          "hero_probability": 0.375,
          "hero_probability_away": 0.625,
          "hero_probability_source": "blend",
          "highlight": {
            "score": 20,
            "reasons": ["tier_1"],
            "label": null,
            "should_feature": false,
            "flags": {
              "is_live": false,
              "is_close_matchup": false,
              "is_blowout": false,
              "favorite_switched": false,
              "probability_swing": "stable",
              "score_swing": "stable",
              "is_starting_soon": false,
              "is_recently_finished": false,
              "is_upset": false,
              "league_tier": 1,
              "is_volatile": false,
              "has_lead_changes": false,
              "has_recent_momentum": false
            }
          }
        }
      ]
    }
    """#

    private func decodeRealMadridRow() throws -> SearchEvent {
        let decoder = JSONDecoder()
        decoder.keyDecodingStrategy = .convertFromSnakeCase
        let response = try decoder.decode(SearchResponse.self,
                                          from: Data(Self.realMadridRowJSON.utf8))
        return try XCTUnwrap(response.results.first)
    }

    /// The half that was silent. Before naming the keys these two were `nil` and
    /// nothing threw — which is why the row went blank rather than red.
    func testTheServedHeroPairSurvivesDecoding() throws {
        let event = try decodeRealMadridRow()
        XCTAssertEqual(event.heroProbability, 0.375)
        XCTAssertEqual(event.heroProbabilityAway, 0.625)
    }

    /// Stated so the fixture cannot quietly stop being the specimen: if a future
    /// capture carries `current_odds`, it exercises the preferred arm instead and
    /// proves nothing about the fallback.
    func testTheSpecimenReallyHasNoCurrentOdds() throws {
        let event = try decodeRealMadridRow()
        XCTAssertNil(event.currentOdds)
    }

    /// End to end on the real payload: the row that drew nothing draws the
    /// FIRST-NAMED side, Real Madrid, at 63% (`0.625` → `Int((62.5).rounded())`).
    func testTheProductionRowThatDrewNothingNowDrawsSixtyThree() throws {
        let event = try decodeRealMadridRow()
        let number = firstNamedSideNumber(
            oddsAway: event.currentOdds?.awayProbability,
            oddsHome: event.currentOdds?.homeProbability,
            servedAway: event.currentOdds?.awayRenderedPercent,
            servedHome: event.currentOdds?.homeRenderedPercent,
            heroAway: event.heroProbabilityAway,
            heroHome: event.heroProbability
        )
        XCTAssertEqual(number?.percent, 63)
        XCTAssertEqual(number?.probability, 0.625)
    }

    // MARK: - The preference order

    /// `current_odds` stays authoritative, so no row that renders correctly today
    /// moves by one point. The hero pair here would say 63 and must not be heard.
    func testCurrentOddsWinsWheneverItCanAnswer() {
        let number = firstNamedSideNumber(
            oddsAway: 0.20, oddsHome: 0.80,
            servedAway: nil, servedHome: nil,
            heroAway: 0.625, heroHome: 0.375
        )
        XCTAssertEqual(number?.percent, 20)
    }

    /// The fallback is strictly for rows drawing nothing.
    func testTheHeroPairAnswersOnlyWhenCurrentOddsCannot() {
        let number = firstNamedSideNumber(
            oddsAway: nil, oddsHome: nil,
            servedAway: nil, servedHome: nil,
            heroAway: 0.625, heroHome: 0.375
        )
        XCTAssertEqual(number?.percent, 63)
    }

    /// #4794 — a row with no reading states no reading. The 9 of 29 that carry
    /// neither source must stay blank rather than acquire a number from somewhere.
    func testARowWithNeitherSourceStillDrawsNothing() {
        XCTAssertNil(firstNamedSideNumber(
            oddsAway: nil, oddsHome: nil,
            servedAway: nil, servedHome: nil,
            heroAway: nil, heroHome: nil
        ))
    }

    /// Half a hero pair is still an answer: the complement is derived, exactly as
    /// the single-sided readers already do.
    func testTheHomeSideAloneStillYieldsTheFirstNamedNumber() {
        let number = firstNamedSideNumber(
            oddsAway: nil, oddsHome: nil,
            servedAway: nil, servedHome: nil,
            heroAway: nil, heroHome: 0.375
        )
        XCTAssertEqual(number?.percent, 63)
    }

    // MARK: - The contract that has no other guard

    /// `duelPercents` is explicit that `servedAway`/`servedHome` describe
    /// `current_odds` AND NOTHING ELSE. A payload can carry the served ROUNDING
    /// with no probabilities beside it, and the tempting call-site spelling —
    /// pass the served pair through and coalesce the probabilities — would then
    /// print `current_odds`' percent against the hero source's number.
    ///
    /// The pair still sums to 100, so no sum guard anywhere could catch it. This
    /// asserts the served percents are dropped with the arm they belong to: 63
    /// from the hero pair, never the 99 sitting in the served fields.
    func testTheServedPercentsCannotLeakOntoTheHeroNumber() {
        let number = firstNamedSideNumber(
            oddsAway: nil, oddsHome: nil,
            servedAway: 99, servedHome: 1,
            heroAway: 0.625, heroHome: 0.375
        )
        XCTAssertEqual(number?.percent, 63)
        XCTAssertNotEqual(number?.percent, 99)
    }
}
