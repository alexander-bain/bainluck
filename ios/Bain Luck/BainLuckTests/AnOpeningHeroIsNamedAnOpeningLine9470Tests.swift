import XCTest
@testable import Bain_Luck

/// #9470 — an event whose server hero is `hero_probability_source: "opening"`
/// is printed as an opening line, not as a current "Win Probability".
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
        OpeningLineHero.resolve(
            currentOdds: try XCTUnwrap(e.currentOdds),
            heroSource: e.heroProbabilitySource,
            heroHome: e.heroProbability,
            heroAway: e.heroProbabilityAway,
            status: e.status)
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

    /// The view reads the resolved pair, drops the bars and the since-open
    /// caption on the opening arm, and prints the caption constant.
    func testTheHeroIsWiredThroughTheResolver() throws {
        let root = URL(fileURLWithPath: #filePath).deletingLastPathComponent().deletingLastPathComponent()
        let page = try String(contentsOf: root.appendingPathComponent("Bain Luck/Views/EventDetailView.swift"),
                              encoding: .utf8)
        let start = try XCTUnwrap(page.range(of: "} else if let currentOdds = event.currentOdds,"))
        let end = try XCTUnwrap(page.range(of: "// Projected final score.", range: start.upperBound..<page.endIndex))
        let hero = String(page[start.upperBound..<end.lowerBound])
        XCTAssertTrue(hero.contains("OpeningLineHero.resolve("))
        XCTAssertFalse(hero.contains("currentOdds.homeProbability"), "the pair comes from the resolver")
        let sinceOpen = try XCTUnwrap(hero.range(of: "if carriesContext, let caption = SinceOpenCaption.caption("))
        let sinceOpenBody = hero[sinceOpen.upperBound...].prefix(1200)
        XCTAssertTrue(sinceOpenBody.contains("!odds.isOpeningLine {"), "the since-open caption is gated off an opening line")
        XCTAssertTrue(hero.contains("if odds.isOpeningLine {"))
        XCTAssertTrue(hero.contains("Text(OpeningLineHero.caption)"))
        XCTAssertEqual(OpeningLineHero.caption, "Opening line")
    }
}
