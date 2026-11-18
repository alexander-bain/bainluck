import XCTest
@testable import Bain_Luck

/// #9470 pins the legacy opening-line resolver. #12824 keeps its historical
/// odds out of the current chance on the unified headline.
///
/// The specimen is production's 14780556 (Packers v Bears, Oct 11) as served
/// 2026-09-28 22:5xZ: hero 0.5996 from `opening`, `current_odds` the same
/// 0.5996 captured 2026-09-13T15:10Z, `win_probability_sources` holding only
/// `betting_book_count`. The phone drew it as **40% – 60% · Win Probability**
/// with confidence bars (artifacts/native-9470/before-14780556.png).
@MainActor
final class AnOpeningHeroIsNamedAnOpeningLine9470Tests: XCTestCase {
    private func event(
        status: String = "scheduled", source: String = "opening",
        hero: Double = 0.5996, heroAway: String = "0.4004",
        current: Double = 0.5996
    ) throws -> EventDetail {
        let decoder = JSONDecoder()
        decoder.keyDecodingStrategy = .convertFromSnakeCase
        return try decoder.decode(EventDetail.self, from: Data("""
        {"id":14780556,"sport":"americanfootball_nfl","home_team":"Green Bay Packers",
         "away_team":"Chicago Bears","status":"\(status)","commence_time":"2026-10-11T20:25:00+00:00",
         "current_odds":{"home_probability":\(current),"away_probability":\(1 - current),
           "home_rendered_percent":\(Int((current * 100).rounded())),
           "away_rendered_percent":\(Int(((1 - current) * 100).rounded())),
           "captured_at":"2026-09-13T15:10:39.053494+00:00","bookmaker_count":2},
         "hero_probability":\(hero),"hero_probability_away":\(heroAway),
         "hero_probability_source":"\(source)","hero_probability_observed_at":null,
         "win_probability_sources":{"betting_book_count":{"value":1.0,"display_name":"betting_book_count","type":"model"}}}
        """.utf8))
    }

    private func resolve(_ e: EventDetail) throws -> OpeningLineHero {
        OpeningLineHero.resolve(try XCTUnwrap(e.currentOdds), for: e)
    }

    func testTheSpecimenIsAnOpeningLineAndKeepsItsNumber() throws {
        let e = try event()
        XCTAssertEqual(e.heroProbabilityAway, 0.4004, "the away side decodes")
        let hero = try resolve(e)
        XCTAssertTrue(hero.isOpeningLine)
        XCTAssertEqual(hero.homeProbability, 0.5996)
        XCTAssertEqual(hero.awayProbability, 0.4004)
        // Rounded as one pair by the view's fallback, so the reader still sees 40 – 60.
        XCTAssertEqual(complementDisplayPercents(away: 0.4004, home: 0.5996), [40, 60])
    }

    /// Rule 2: a still-quoting sportsbook moves `current_odds` off the opening,
    /// and "Opening line" over that number would be a new false claim.
    func testTheOpeningArmPrintsTheServersPairNotCurrentOdds() throws {
        let hero = try resolve(event(hero: 0.64, heroAway: "0.36", current: 0.78))
        XCTAssertTrue(hero.isOpeningLine)
        XCTAssertEqual(hero.homeProbability, 0.64)
        XCTAssertEqual(hero.awayProbability, 0.36)
        XCTAssertNil(hero.homeRenderedPercent, "served percents round current_odds, not the hero")
    }

    /// Control: the change is conditioned on the source, so the opposite
    /// branch must stay byte-for-byte what the hero printed before.
    func testABlendHeroStillPrintsCurrentOddsWithItsServedPercents() throws {
        let hero = try resolve(event(source: "blend", hero: 0.64, heroAway: "0.36", current: 0.78))
        XCTAssertFalse(hero.isOpeningLine)
        XCTAssertEqual(hero.homeProbability, 0.78)
        XCTAssertEqual(hero.homeRenderedPercent, 78)
        XCTAssertEqual(hero.awayRenderedPercent, 22)
    }

    func testALivePageKeepsTheCurrentOddsItsFramesWrite() throws {
        let hero = try resolve(event(status: "live", hero: 0.64, heroAway: "0.36", current: 0.78))
        XCTAssertFalse(hero.isOpeningLine)
        XCTAssertEqual(hero.homeProbability, 0.78)
    }

    func testAnUnusableHeroFallsBackToCurrentOdds() throws {
        for bad in [0.0, 1.0] {
            let hero = try resolve(event(hero: bad, heroAway: "null", current: 0.55))
            XCTAssertFalse(hero.isOpeningLine, "\(bad)")
            XCTAssertEqual(hero.homeProbability, 0.55)
        }
    }

    func testTheHeadlineWithholdsTheCopiedOpeningOddsFromChance() throws {
        let now = try XCTUnwrap(ISO8601DateFormatter().date(from: "2026-10-11T19:25:00Z"))

        func headline(_ event: EventDetail) -> EventSportHeadlines12472.Model {
            EventSportHeadlines12472.resolve(
                event: event,
                awayFullName: event.awayTeam,
                homeFullName: event.homeTeam,
                liveStatusText: nil,
                hasScore: false,
                numberStreams: false,
                now: now
            )
        }

        let opening = try event()
        XCTAssertEqual(opening.heroProbabilitySource, "opening")
        XCTAssertEqual(opening.currentOdds?.homeProbability, 0.5996)
        let withheld = headline(opening)
        XCTAssertEqual(withheld.kind, .nflBeforeGame)
        XCTAssertEqual(withheld.away.winChanceText, "")
        XCTAssertEqual(withheld.home.winChanceText, "")
        XCTAssertEqual(withheld.rows.map(\.rawProbability), [nil, nil])
        XCTAssertNil(withheld.bottomBar)

        let current = headline(try event(source: "blend", hero: 0.64, heroAway: "0.36", current: 0.78))
        XCTAssertEqual(current.away.winChanceText, "22%")
        XCTAssertEqual(current.home.winChanceText, "78%")
        XCTAssertNotNil(current.bottomBar)
    }
}
