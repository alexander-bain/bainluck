import XCTest
@testable import Bain_Luck

/// #9483 — the recognizable NFL page's decisions (design ref #10868 v105/v107):
/// the paired headline and the paired chart's away line.
///
/// What these pin, and the mutation each kills:
/// - adopt another sport, or drop the NBA slice → `testOnlyTheNFLAndTheNBAAdoptThePage`
/// - draw the away line where the balance ink is refused → `testTheAwayLineNeedsTheBinaryAdmission`
/// - draw the away line from anything but the blend's own run → `testTheAwayRunIsTheSameRunReadFromTheOtherSide`
/// - drop or invent a live-tail vertex → `testTheAwayTailEndsWhereTheHomeTailEnds`
/// - print the pregame number before kickoff (it IS the price) → `testBeforeKickoffNoSideRepeatsItsPregameNumber`
/// - drop the pregame number live → `testLiveEachSideCarriesItsPregameNumber`
/// - call a draw or an unresolved final Won/Lost → `testALevelOrUnresolvedFinalDeclines`
/// - swap the winner's side → `testAFinalNamesTheWinnerOnTheWinnersSide`
/// - print the score as a probability or drop it → `testTheScoreSitsBetweenTheChances`
final class RecognizableNFLPage9483Tests: XCTestCase {

    private func reading(away: Double, home: Double, served: Bool = true) -> PrematchReading {
        PrematchReading(awayProbability: away, homeProbability: home,
                        percents: renderedDuelPercents(away: away, home: home),
                        source: PrematchReading.booksSource, isServed: served,
                        awayIsComplement: false)
    }

    private func point(_ seconds: TimeInterval, _ p: Double) -> ChartDataPoint {
        ChartDataPoint(date: Date(timeIntervalSince1970: 1_790_000_000 + seconds),
                       probability: p, source: "aggregate")
    }

    // MARK: - Scope

    func testOnlyTheNFLAndTheNBAAdoptThePage() {
        XCTAssertTrue(NFLRecognizablePage9483.applies(sportKey: "americanfootball_nfl"))
        // v328's NBA slice adopts the same headline, paired journey and deck.
        XCTAssertTrue(NFLRecognizablePage9483.applies(sportKey: "basketball_nba"))
        XCTAssertFalse(NFLRecognizablePage9483.isNFL(sportKey: "basketball_nba"), "milestones stay NFL")
        for other in ["americanfootball_ncaaf", "basketball_wnba", "basketball_ncaab", "tennis_atp", "soccer_epl", nil] {
            XCTAssertFalse(NFLRecognizablePage9483.applies(sportKey: other), "\(other ?? "nil")")
        }
    }

    // MARK: - The paired chart

    func testTheAwayLineNeedsTheBinaryAdmission() {
        XCTAssertTrue(PairedWinLines9483.admits(sportKey: "americanfootball_nfl", binaryAdmission: .admittedBinary))
        XCTAssertFalse(PairedWinLines9483.admits(sportKey: "americanfootball_nfl", binaryAdmission: .refused))
        XCTAssertTrue(PairedWinLines9483.admits(sportKey: "basketball_nba", binaryAdmission: .admittedBinary))
        XCTAssertFalse(PairedWinLines9483.admits(sportKey: "basketball_nba", binaryAdmission: .refused))
        XCTAssertFalse(PairedWinLines9483.admits(sportKey: "basketball_wnba", binaryAdmission: .admittedBinary))
    }

    func testTheAwayRunIsTheSameRunReadFromTheOtherSide() {
        let run = [point(0, 0.365), point(60, 0.52), point(120, 0.8557)]
        let away = PairedWinLines9483.awayRun(run)
        XCTAssertEqual(away.map(\.date), run.map(\.date))
        for (a, h) in zip(away, run) {
            XCTAssertEqual(a.probability + h.probability, 1, accuracy: 1e-12)
        }
        XCTAssertTrue(PairedWinLines9483.awayRun([]).isEmpty, "no run, no line")
    }

    func testTheAwayTailEndsWhereTheHomeTailEnds() {
        let from = LiveEdgeVertex(date: Date(timeIntervalSince1970: 100), probability: 0.6)
        let to = LiveEdgeVertex(date: Date(timeIntervalSince1970: 102), probability: 0.62)
        let joined = PairedWinLines9483.awayTail(LiveEdgeTail(from: from, to: to))
        XCTAssertEqual(joined.map(\.date), [from.date, to.date])
        XCTAssertEqual(joined.map(\.probability)[1], 0.38, accuracy: 1e-12)
        // A newest vertex that opens its own run (#7878) joins nothing.
        let alone = PairedWinLines9483.awayTail(LiveEdgeTail(from: nil, to: to))
        XCTAssertEqual(alone.map(\.date), [to.date])
    }

    // MARK: - The paired headline

    func testBeforeKickoffNoSideRepeatsItsPregameNumber() {
        let h = NFLPairedHeadline9483.priced(awayText: "37%", homeText: "63%", live: false,
                                             score: nil, pregame: reading(away: 0.37, home: 0.63))
        XCTAssertEqual(h.away.figure, "37%")
        XCTAssertEqual(h.home.figure, "63%")
        XCTAssertNil(h.away.pregame)
        XCTAssertNil(h.home.pregame)
        XCTAssertEqual(h.center, .versus)
        XCTAssertNil(h.centerCaption)
    }

    func testLiveEachSideCarriesItsPregameNumber() {
        let h = NFLPairedHeadline9483.priced(awayText: "14%", homeText: "86%", live: true,
                                             score: (away: 7, home: 20), pregame: reading(away: 0.64, home: 0.36))
        XCTAssertEqual(h.away.pregame, "Pre-match 64%")
        XCTAssertEqual(h.home.pregame, "Pre-match 36%")
        XCTAssertNil(h.away.won)
        // The opening-line fallback says so, as the hero's caption does.
        let opened = NFLPairedHeadline9483.priced(awayText: "14%", homeText: "86%", live: true, score: nil,
                                                  pregame: reading(away: 0.6, home: 0.4, served: false))
        XCTAssertEqual(opened.home.pregame, "Opened 40%")
        // No pregame reading, no invented one.
        let none = NFLPairedHeadline9483.priced(awayText: "14%", homeText: "86%", live: true, score: nil, pregame: nil)
        XCTAssertNil(none.home.pregame)
    }

    func testALevelOrUnresolvedFinalDeclines() {
        XCTAssertNil(NFLPairedHeadline9483.final(homeWon: nil, score: (away: 20, home: 20),
                                                 pregame: reading(away: 0.5, home: 0.5)))
    }

    func testAFinalNamesTheWinnerOnTheWinnersSide() throws {
        let h = try XCTUnwrap(NFLPairedHeadline9483.final(homeWon: false, score: (away: 37, home: 34),
                                                          pregame: reading(away: 0.38, home: 0.62)))
        XCTAssertEqual(h.away.figure, "Won")
        XCTAssertEqual(h.away.won, true)
        XCTAssertEqual(h.home.figure, "Lost")
        XCTAssertEqual(h.home.won, false)
        XCTAssertEqual(h.away.pregame, "Pre-match 38%")
        XCTAssertEqual(h.home.pregame, "Pre-match 62%")
        XCTAssertEqual(h.center, .score(away: 37, home: 34, final: true))
        XCTAssertEqual(h.centerCaption, "Final score")
    }

    func testTheScoreSitsBetweenTheChances() {
        let h = NFLPairedHeadline9483.priced(awayText: "14%", homeText: "86%", live: true,
                                             score: (away: 7, home: 20), pregame: nil)
        XCTAssertEqual(h.center, .score(away: 7, home: 20, final: false))
        XCTAssertEqual(h.centerCaption, "Score")
        XCTAssertEqual(h.accessibilityLabel(awayName: "Eagles", homeName: "Bears"),
                       "Eagles 14%. Bears 86%. Score Eagles 7, Bears 20")
    }
}
