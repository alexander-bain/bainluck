import XCTest
@testable import Bain_Luck

/// #9483 tennis — **each player's pre-match chance is prominent under their
/// own name, beside an explicit final result in sets.**
///
/// Design's adoption finding (2026-10-20, `tennis-headline-probability-
/// adoption-20261020`): the completed tennis hero led with "Zverev Win" and
/// small set counts, and both chances sat in one caption between the crests
/// ("Pre-match 41% – 59%"). The specimen below is that page's own values:
/// Ben Shelton (away) v Alexander Zverev (home), Zverev in 3–1... served as
/// `away 1, home 3`.
@MainActor
final class TennisFinalHeadlineProbabilityFirst9483Tests: XCTestCase {

    private let sport = "tennis_atp_us_open"

    private func served(away: Double, home: Double, awayPct: Int?, homePct: Int?) -> PrematchReading? {
        PrematchReading.resolve(
            prematch: PrematchOdds(homeProbability: home, awayProbability: away,
                                   homeRenderedPercent: homePct, awayRenderedPercent: awayPct,
                                   source: "kalshi"),
            opening: nil)
    }

    private func opening(away: Double?, home: Double?) -> PrematchReading? {
        PrematchReading.resolve(
            prematch: nil,
            opening: OpeningOdds(homeProbability: home, awayProbability: away, favorite: nil, overUnder: nil))
    }

    private func headline(
        outcome: EventOutcome, score: (away: Int, home: Int)?, pregame: PrematchReading?,
        away: String = "Ben Shelton", home: String = "Alexander Zverev"
    ) -> TennisFinalHeadline9483 {
        TennisFinalHeadline9483.resolve(
            awayName: away, homeName: home, sportKey: sport,
            outcome: outcome, score: score, pregame: pregame)
    }

    // MARK: - The served pre-match arm

    func testEachPlayerCarriesTheirOwnServedPreMatchChance() {
        let h = headline(outcome: .home, score: (1, 3),
                         pregame: served(away: 0.41, home: 0.59, awayPct: 41, homePct: 59))
        XCTAssertEqual(h.away, .init(name: "Ben Shelton", chance: "41%", won: false))
        XCTAssertEqual(h.home, .init(name: "Alexander Zverev", chance: "59%", won: true))
        XCTAssertEqual(h.chanceLabel, "Pre-match win chance")
        XCTAssertEqual(h.result?.figure, "1\u{2013}3")
        XCTAssertEqual(h.result?.caption, "Final · sets")
    }

    /// The reading's own rounded pair, never re-rounded here: the served
    /// integers are printed even where local rounding would say otherwise.
    func testTheServedWholePercentsArePrintedAsServed() {
        let h = headline(outcome: .home, score: (1, 3),
                         pregame: served(away: 0.414, home: 0.586, awayPct: 42, homePct: 58))
        XCTAssertEqual(h.away.chance, "42%")
        XCTAssertEqual(h.home.chance, "58%")
        // Control: the same pair with no served integers rounds locally.
        let local = headline(outcome: .home, score: (1, 3),
                             pregame: served(away: 0.414, home: 0.586, awayPct: nil, homePct: nil))
        XCTAssertEqual(local.away.chance, "41%")
        XCTAssertEqual(local.home.chance, "59%")
    }

    // MARK: - The opening-only fallback

    func testTheOpeningFallbackIsNamedAsTheOpeningLine() {
        let h = headline(outcome: .home, score: (0, 2), pregame: opening(away: 0.31, home: 0.69),
                         away: "Stefanos Tsitsipas", home: "Daniil Medvedev")
        XCTAssertEqual(h.chanceLabel, "Opening win chance")
        XCTAssertEqual(h.away.chance, "31%")
        XCTAssertEqual(h.home.chance, "69%")
        XCTAssertEqual(h.result?.caption, "Final · sets")
        // Control: the served arm on the same numbers says pre-match.
        let s = headline(outcome: .home, score: (0, 2),
                         pregame: served(away: 0.31, home: 0.69, awayPct: 31, homePct: 69))
        XCTAssertEqual(s.chanceLabel, "Pre-match win chance")
    }

    /// An unusable served reading (a settled endpoint leaking backwards)
    /// falls to the opening line, as `PrematchReading` decides — not to a
    /// number this file chose.
    func testAnUnusableServedReadingFallsToTheOpeningLine() {
        let reading = PrematchReading.resolve(
            prematch: PrematchOdds(homeProbability: 1, awayProbability: 0,
                                   homeRenderedPercent: 100, awayRenderedPercent: 0, source: "kalshi"),
            opening: OpeningOdds(homeProbability: 0.81, awayProbability: 0.19, favorite: nil, overUnder: nil))
        let h = headline(outcome: .home, score: (0, 2), pregame: reading,
                         away: "Pablo Carreno Busta", home: "Daniil Medvedev")
        XCTAssertEqual(h.chanceLabel, "Opening win chance")
        XCTAssertEqual(h.away.chance, "19%")
        XCTAssertEqual(h.home.chance, "81%")
    }

    // MARK: - Missing chance

    /// No usable reading: each side is Unavailable. The result never becomes
    /// a chance — the winner is not 100% and the loser is not 0%.
    func testAMissingChanceIsUnavailableNeverInferredFromTheResult() {
        let h = headline(outcome: .home, score: (1, 3), pregame: nil)
        XCTAssertNil(h.away.chance)
        XCTAssertNil(h.home.chance)
        XCTAssertEqual(h.home.won, true, "the result still says who won")
        XCTAssertEqual(h.away.won, false)
        XCTAssertEqual(h.result?.figure, "1\u{2013}3", "and the sets still print")
        let spoken = h.accessibilityLabel
        XCTAssertTrue(spoken.contains("unavailable"))
        XCTAssertFalse(spoken.contains("100%"))
        XCTAssertFalse(spoken.contains("0%"))
        // Endpoints only, with no opening line, are no reading at all.
        let endpoints = PrematchReading.resolve(
            prematch: PrematchOdds(homeProbability: 1, awayProbability: 0,
                                   homeRenderedPercent: 100, awayRenderedPercent: 0, source: "kalshi"),
            opening: nil)
        XCTAssertNil(headline(outcome: .home, score: (1, 3), pregame: endpoints).home.chance)
    }

    // MARK: - Undecided, level and retirement-shaped results

    /// Over, and nothing names a result: no Won/Lost, no invented score.
    func testAnUndecidedFinalNamesNoWinnerAndNoScore() {
        let h = headline(outcome: .undecided, score: nil,
                         pregame: served(away: 0.41, home: 0.59, awayPct: 41, homePct: 59))
        XCTAssertNil(h.away.won)
        XCTAssertNil(h.home.won)
        XCTAssertNil(h.result)
        XCTAssertEqual(h.home.chance, "59%", "the chances still lead")
        XCTAssertFalse(h.accessibilityLabel.contains("won"))
        XCTAssertFalse(h.accessibilityLabel.contains("Final"))
    }

    /// A tennis match cannot end level, so a level scoreboard with no served
    /// verdict (`EventOutcome.draw`) names no winner — and is not called a draw.
    func testALevelTennisScoreboardNamesNoWinner() {
        let outcome = EventOutcome.resolve(status: "completed", homeScore: 1, awayScore: 1)
        XCTAssertEqual(outcome, .draw, "control: the shared resolver calls it level")
        let h = headline(outcome: outcome, score: (1, 1),
                         pregame: served(away: 0.41, home: 0.59, awayPct: 41, homePct: 59))
        XCTAssertNil(h.away.won)
        XCTAssertNil(h.home.won)
        XCTAssertEqual(h.result?.figure, "1\u{2013}1")
        XCTAssertFalse(h.accessibilityLabel.lowercased().contains("draw"))
    }

    /// A retirement can leave the winner behind on sets. The served verdict
    /// decides Won/Lost (`EventOutcome`'s authority) and the scoreboard prints
    /// exactly as served — neither is rewritten to agree with the other.
    func testAServedVerdictAndTheScoreboardArePrintedAsServed() {
        let outcome = EventOutcome.resolve(status: "completed", homeScore: 1, awayScore: 0,
                                           servedResult: "away")
        XCTAssertEqual(outcome, .away)
        let h = headline(outcome: outcome, score: (0, 1),
                         pregame: served(away: 0.41, home: 0.59, awayPct: 41, homePct: 59))
        XCTAssertEqual(h.away.won, true)
        XCTAssertEqual(h.home.won, false)
        XCTAssertEqual(h.result?.figure, "0\u{2013}1")
    }

    // MARK: - Orientation

    /// Away first everywhere: names, chances, Won/Lost and the scoreboard.
    /// Swapping the sides swaps every one of them.
    func testAwayHomeOrientationHoldsAcrossNamesChancesAndSets() {
        let h = headline(outcome: .home, score: (1, 3),
                         pregame: served(away: 0.41, home: 0.59, awayPct: 41, homePct: 59))
        let swapped = headline(outcome: .away, score: (3, 1),
                               pregame: served(away: 0.59, home: 0.41, awayPct: 59, homePct: 41),
                               away: "Alexander Zverev", home: "Ben Shelton")
        XCTAssertEqual(h.away, swapped.home)
        XCTAssertEqual(h.home, swapped.away)
        XCTAssertEqual(h.result?.figure, "1\u{2013}3")
        XCTAssertEqual(swapped.result?.figure, "3\u{2013}1")
        XCTAssertEqual(h.accessibilityLabel,
                       "Ben Shelton, lost, pre-match win chance 41%. "
                       + "Alexander Zverev, won, pre-match win chance 59%. "
                       + "Final sets, Ben Shelton 1, Alexander Zverev 3")
    }

    // MARK: - Admission

    func testOnlyACompletedTennisMatchAdoptsTheHeadline() {
        XCTAssertTrue(TennisFinalHeadline9483.applies(sportKey: sport, status: "completed"))
        XCTAssertTrue(TennisFinalHeadline9483.applies(sportKey: "tennis_wta_china_open", status: "closed"))
        XCTAssertFalse(TennisFinalHeadline9483.applies(sportKey: sport, status: "live"))
        XCTAssertFalse(TennisFinalHeadline9483.applies(sportKey: sport, status: "scheduled"))
        XCTAssertFalse(TennisFinalHeadline9483.applies(sportKey: sport, status: "suspended"))
        XCTAssertFalse(TennisFinalHeadline9483.applies(sportKey: sport, status: nil))
        XCTAssertFalse(TennisFinalHeadline9483.applies(sportKey: "americanfootball_nfl", status: "completed"))
        XCTAssertFalse(TennisFinalHeadline9483.applies(sportKey: nil, status: "completed"))
        // The point-sport page is not broadened to tennis: it keeps its own gate.
        XCTAssertFalse(MLBFinalPage11284.adoptsPairedPage(sportKey: sport, status: "completed"))
    }

    /// No projection on a finished match: today's served projection is not a
    /// pre-match one, and the shared gate already withholds it.
    func testAFinishedTennisMatchPrintsNoProjection() {
        XCTAssertNil(EventDetailView.projectionText(
            sport: sport, status: "completed", commenceTime: Date(timeIntervalSince1970: 1_789_322_400),
            projectedHome: 22.2, projectedAway: 20.8, ladderHome: 22.2, ladderAway: 20.8, hasScore: true))
        // Control: the same pair before the match prints, in games.
        XCTAssertEqual(EventDetailView.projectionText(
            sport: sport, status: "scheduled", commenceTime: Date(timeIntervalSince1970: 1_789_322_400),
            projectedHome: 22.2, projectedAway: 20.8, hasScore: false,
            now: Date(timeIntervalSince1970: 1_789_322_400 - 3_600)), "Proj. 21-22 games")
    }

    // MARK: - The page mounts it (source guards)

    private func pageCode() throws -> String {
        let here = URL(fileURLWithPath: #filePath)
        let url = here.deletingLastPathComponent().deletingLastPathComponent()
            .appendingPathComponent("Bain Luck/Views/EventDetailView.swift")
        return try String(contentsOf: url, encoding: .utf8)
    }

    private func span(_ text: String, from start: String, to end: String) throws -> String {
        let lo = try XCTUnwrap(text.range(of: start), "moved: \(start)")
        let hi = try XCTUnwrap(text.range(of: end, range: lo.upperBound..<text.endIndex), "moved: \(end)")
        return String(text[lo.upperBound..<hi.lowerBound])
    }

    /// The hero tries the point-sport pair first, then the tennis final, then
    /// today's hero — whose finished caption (#8622) stays for every other sport.
    func testTheHeroMountsTheTennisFinalBetweenThePairAndTheLegacyHero() throws {
        let hero = try span(pageCode(), from: "private func heroSection(", to: "static func heroBackdrop(")
        let paired = try XCTUnwrap(hero.range(of: "if let paired = nflPairedHeadline(event, hasScore: hasScore) {"))
        let tennis = try XCTUnwrap(hero.range(of: "} else if let tennis = tennisFinalHeadline(event, hasScore: hasScore) {"))
        let view = try XCTUnwrap(hero.range(of: "tennisFinalHeadlineView(tennis, colors: colors)"))
        let legacy = try XCTUnwrap(hero.range(of: "heroLayout {"))
        XCTAssertLessThan(paired.lowerBound, tennis.lowerBound)
        XCTAssertLessThan(tennis.lowerBound, view.lowerBound)
        XCTAssertLessThan(view.lowerBound, legacy.lowerBound)
        XCTAssertTrue(hero.contains("// Pre-game odds as secondary context"), "control: the legacy caption remains")
    }

    /// The headline reads the hero's own inputs — the canonical reading, the
    /// shared verdict and the shown scoreboard — never the chart or a fixture.
    func testTheHeadlineReadsTheHerosOwnInputs() throws {
        let resolve = try span(pageCode(), from: "private func tennisFinalHeadline(_ event: EventDetail, hasScore: Bool)",
                               to: "private func tennisFinalHeadlineView(")
        XCTAssertTrue(resolve.contains("PrematchReading.resolve(prematch: event.prematchOdds, opening: event.openingOdds)"))
        XCTAssertTrue(resolve.contains("outcome: heroOutcome(event)"))
        XCTAssertTrue(resolve.contains("score: hasScore ?"))
        XCTAssertTrue(resolve.contains("TennisFinalHeadline9483.applies(sportKey: event.sport, status: event.status)"))
        XCTAssertFalse(resolve.contains("history"), "no chart-selected observation")
        XCTAssertFalse(resolve.contains("commenceTime"), "no baseline derived from the start")
    }

    /// Accessibility sizes stack the players (the adopted pair's rule); names
    /// wrap between words and are never shrunk or cut; the chances use the
    /// adopted headline's scaled size; no projection is drawn.
    func testTheLayoutStacksAtAccessibilitySizesAndNeverShrinksNames() throws {
        let page = try pageCode()
        let view = try span(page, from: "private func tennisFinalHeadlineView(",
                            to: "private func tennisFinalSide(")
        XCTAssertTrue(view.contains("dynamicTypeSize.isAccessibilitySize\n            ? AnyLayout(VStackLayout(alignment: .leading, spacing: 16))"))
        XCTAssertTrue(view.contains(": AnyLayout(HStackLayout(alignment: .nflPairedFigure9483, spacing: 12))"))
        XCTAssertTrue(view.contains("tennisFinalSide(headline.away,"))
        XCTAssertLessThan(try XCTUnwrap(view.range(of: "tennisFinalSide(headline.away,")).lowerBound,
                          try XCTUnwrap(view.range(of: "tennisFinalSide(headline.home,")).lowerBound,
                          "away first")
        XCTAssertFalse(view.lowercased().contains("projection"))
        let side = try span(page, from: "private func tennisFinalSide(",
                            to: "/// The pregame meta row's broadcast and start")
        let name = try span(side, from: "Text(side.name)", to: "if let won = side.won {")
        XCTAssertFalse(name.contains("lineLimit"))
        XCTAssertFalse(name.contains("minimumScaleFactor"))
        XCTAssertTrue(name.contains(".fixedSize(horizontal: false, vertical: true)"))
        XCTAssertTrue(side.contains("size: eventHeadlineChanceSize9483"))
        XCTAssertTrue(side.contains("Text(label)"), "the chance carries its meaning")
    }
}
