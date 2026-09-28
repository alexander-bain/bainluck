import XCTest
@testable import Bain_Luck

/// #9336 — the iPhone twin of web #6359 + #6853. The full-game margin card's
/// header printed `"\(abbr) \(Int((p * 100).rounded()))%"` in every lifecycle:
///
/// - Settled: Texans @ Colts (`/events/14782154`, FINAL 17–19) read `IND 93%`,
///   `current_odds.home_probability 0.9281` captured 50 s before the final
///   whistle, over the card's own `FINAL · IND by 2` tile.
/// - Live: an inline round, so a served 0.999 printed `100%` under a hero
///   reading `>99%`.
final class AFinishedGamesMarginMapPrintsNoLivePrice9336Tests: XCTestCase {

    private static func headline(isDone: Bool, away: Double?, home: Double?, sport: String) -> String {
        MarketMapView.marginHeadline(
            isDone: isDone,
            side: DrawPricedWinner.headlineSide(away: away, home: home, sport: sport),
            homeAbbr: "IND", awayAbbr: "HOU"
        )
    }

    /// The specimen: a decisive settled game prints no header.
    func testTheSettledSpecimenPrintsNoHeader() {
        XCTAssertEqual(Self.headline(isDone: true, away: 0.0719, home: 0.9281, sport: "americanfootball_nfl"), "")
    }

    /// #6359's case: a settled draw would name home at an in-play price.
    func testASettledDrawPrintsNoHeader() {
        XCTAssertEqual(Self.headline(isDone: true, away: 0.20, home: 0.62, sport: "soccer_epl"), "")
    }

    /// Control: the same numbers on an open game keep the header, so the
    /// settled rule is not simply "never print".
    func testAnOpenGameKeepsItsHeader() {
        XCTAssertEqual(Self.headline(isDone: false, away: 0.0719, home: 0.9281, sport: "americanfootball_nfl"), "IND 93%")
        XCTAssertEqual(Self.headline(isDone: false, away: 0.64, home: 0.36, sport: "americanfootball_nfl"), "HOU 64%")
    }

    /// #6853's case: a live game is never 100%, and never 0%.
    func testALiveHeaderKeepsTheBoundaryRule() {
        XCTAssertEqual(Self.headline(isDone: false, away: 0.001, home: 0.999, sport: "americanfootball_nfl"), "IND >99%")
        // A draw-priced sport names home even as a long shot.
        XCTAssertEqual(Self.headline(isDone: false, away: 0.95, home: 0.004, sport: "soccer_epl"), "IND <1%")
    }

    func testNoPriceMeansNoHeader() {
        XCTAssertEqual(Self.headline(isDone: false, away: nil, home: nil, sport: "americanfootball_nfl"), "")
    }

    /// The card must build its header through the helper. Reverting the call
    /// site to an inline round would leave every test above green.
    func testTheCardBuildsItsHeaderThroughTheHelper() throws {
        let root = URL(fileURLWithPath: #filePath).deletingLastPathComponent().deletingLastPathComponent()
        let file = root.appendingPathComponent("Bain Luck/Components/MarketMapView.swift")
        let source = try String(contentsOf: file, encoding: .utf8)
        // …and hand it the card's own settled test, not a constant.
        XCTAssertNotNil(source.range(of: #"let headline = Self\.marginHeadline\(\s*isDone: isDone,"#,
                                     options: .regularExpression),
                        "the full-game margin card's header must come from marginHeadline(isDone: isDone, …)")
        XCTAssertFalse(source.contains("Int((side.probability * 100).rounded())"),
                       "an inline round skips both the settled rule and the >99%/<1% rule")
    }
}
