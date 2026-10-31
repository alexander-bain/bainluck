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

    // MARK: - #9483 v476 adopted sides and the away endpoint label

    func testTheAdoptedFinalShowsThePregameFigureNamedAsPregameAndSaysTheResult() {
        let won = NFLPairedHeadline9483.Side(figure: "Won", pregame: "Pre-match 69%", won: true)
        let served = EventDetailView.adoptedSide9483(won, isAway: false, live: false,
                                                     pregame: reading(away: 0.31, home: 0.69))
        XCTAssertEqual(served.figure, "69%")
        XCTAssertEqual(served.caption, "Pregame win chance")
        XCTAssertEqual(served.spoken, "won, pregame win chance 69%")
        XCTAssertFalse(served.figureIsWord)
        let opened = EventDetailView.adoptedSide9483(won, isAway: false, live: false,
                                                     pregame: reading(away: 0.31, home: 0.69, served: false))
        XCTAssertEqual(opened.caption, "Pregame · opening")
        XCTAssertEqual(opened.spoken, "won, pregame opening win chance 69%")
        let lost = NFLPairedHeadline9483.Side(figure: "Lost", pregame: nil, won: false)
        let missing = EventDetailView.adoptedSide9483(lost, isAway: true, live: false, pregame: nil)
        XCTAssertEqual(missing.figure, "Unavailable", "no baseline is said, never invented")
        XCTAssertTrue(missing.figureIsWord)
        XCTAssertEqual(missing.spoken, "lost, pregame win chance unavailable")
        XCTAssertFalse(served.figure.contains("100"), "a result never becomes 100%")
    }

    func testTheAdoptedLiveSideKeepsTheCurrentFigureAndNamesItsBaseline() {
        let side = NFLPairedHeadline9483.Side(figure: "65%", pregame: "Opened 45%", won: nil)
        let opened = EventDetailView.adoptedSide9483(side, isAway: true, live: true,
                                                     pregame: reading(away: 0.45, home: 0.55, served: false))
        XCTAssertEqual(opened.figure, "65%", "the live figure is the hero's own price")
        XCTAssertEqual(opened.caption, "Pregame · opening 45%")
        XCTAssertEqual(opened.spoken, "65%, pregame opening 45%")
        let none = EventDetailView.adoptedSide9483(side, isAway: true, live: true, pregame: nil)
        XCTAssertEqual(none.caption, "Pregame unavailable")
        XCTAssertEqual(none.spoken, "65%, pregame unavailable", "the visible gap is spoken too")
        let before = NFLPairedHeadline9483.Side(figure: "38%", pregame: nil, won: nil)
        let scheduled = EventDetailView.adoptedSide9483(before, isAway: true, live: false, pregame: nil)
        XCTAssertNil(scheduled.caption, "before kickoff the price IS the pregame number")
        XCTAssertEqual(scheduled.spoken, "38%")
    }

    private let plot = CGSize(width: 300, height: 260)

    func testTheAwayLabelTakesTheSideAwayFromTheHomeNumber() throws {
        // Home high (y 60), away low (y 200), both at the live edge.
        let center = try XCTUnwrap(PairedAwayEndpointLabel9483.placement(
            tip: CGPoint(x: 290, y: 200), from: CGPoint(x: 250, y: 190),
            homeTip: CGPoint(x: 290, y: 60), homeFrom: CGPoint(x: 250, y: 70),
            label: CGSize(width: 64, height: 18), plot: plot))
        XCTAssertGreaterThan(center.y, 200, "below its own vertex, away from the home number")
        XCTAssertLessThanOrEqual(center.x + 32, plot.width, "inside the plot")
        XCTAssertFalse(LiveChartEdgeMarkerPlan.covers(center, label: CGSize(width: 64, height: 18),
                                                      from: CGPoint(x: 250, y: 190), to: CGPoint(x: 290, y: 200)))
    }

    func testTheAwayLabelIsOmittedNearACrossingOrWhereItWouldHideTheNewestMove() {
        let label = CGSize(width: 64, height: 18)
        XCTAssertNil(PairedAwayEndpointLabel9483.placement(
            tip: CGPoint(x: 290, y: 140), from: nil, homeTip: CGPoint(x: 290, y: 110), homeFrom: nil,
            label: label, plot: plot), "under 44 pt apart: the keys carry it")
        // Away at the floor: the outward spot clamps back onto its own vertex.
        XCTAssertNil(PairedAwayEndpointLabel9483.placement(
            tip: CGPoint(x: 290, y: 258), from: CGPoint(x: 250, y: 250),
            homeTip: CGPoint(x: 290, y: 2), homeFrom: nil, label: label, plot: plot),
            "a label pushed onto its own vertex is not drawn")
        // A steep newest move that runs through the outward spot.
        XCTAssertNil(PairedAwayEndpointLabel9483.placement(
            tip: CGPoint(x: 290, y: 150), from: CGPoint(x: 289, y: 190),
            homeTip: CGPoint(x: 290, y: 60), homeFrom: nil, label: label, plot: plot),
            "never over the line's newest segment")
    }

    // MARK: - #9483 v476 phone fit (design return 20261018: 375x812 NBA final)

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

    /// The adopted header's top row is the chip's height: its disclosure keeps
    /// the whole 44pt target (the button's own frame, unchanged) but overhangs
    /// the card's top inset and the row gap, each of which holds it exactly.
    func testTheDisclosureKeepsItsTargetWithoutARowOfItsOwn() throws {
        let page = try pageCode()
        let button = try span(page, from: "private func probabilityDetails(confidenceTier: String?, statusInDetails: Bool = false, ekgDrawn: Bool = false) -> some View {",
                              to: "// MARK: - Chart Header Bar")
        XCTAssertTrue(button.contains("minHeight: 44"), "control: the 44pt target itself")
        let hero = try span(page, from: "private func heroSection(", to: "static func heroBackdrop(")
        XCTAssertTrue(hero.contains("nflPairedDetails(event)\n"))
        XCTAssertTrue(hero.contains(".padding(.vertical, stacked ? 0 : -Self.adoptedDisclosureOverhang9483)"),
                      "the disclosure sets the row's height again")
        XCTAssertTrue(hero.contains("VStack(spacing: approvedPair ? Self.adoptedDisclosureOverhang9483 : 12)"),
                      "the gap below must hold the overhang")
        XCTAssertTrue(hero.contains(".padding(.top, approvedPair ? 12 : 0)"))
        XCTAssertLessThanOrEqual(EventDetailView.adoptedDisclosureOverhang9483, 12,
                                 "the overhang must stay inside the card's top inset")
        XCTAssertEqual(44 - 2 * EventDetailView.adoptedDisclosureOverhang9483, 24,
                       "the row it leaves is the chip's height")
    }

    /// A decided final's FINAL chip and its date share one row at default
    /// text, stacking from xxLarge as the legacy meta row does; a priced pair
    /// (whose chip can be empty) keeps the stacked column it had.
    func testAFinalsChipAndDateShareARowAtDefaultText() throws {
        let page = try pageCode()
        let hero = try span(page, from: "private func heroSection(", to: "static func heroBackdrop(")
        let adopted = try span(hero, from: "if approvedPair {", to: "} else {")
        XCTAssertTrue(adopted.contains("let decided = nflPairedHeadline(event, hasScore: hasScore)?.away.won != nil"))
        XCTAssertTrue(adopted.contains("let adoptedMetaLayout = decided && !stacked\n"
                                       + "                    ? metaLayout : AnyLayout(VStackLayout(alignment: .leading, spacing: 4))"),
                      "the final's chip and date are stacked again, or a priced pair shares the row")
        XCTAssertTrue(adopted.contains("adoptedMetaLayout {"))
        XCTAssertTrue(adopted.contains("if !decided {\n                        nflPairedDetails(event)"),
                      "control: a decided final mounts no disclosure")
        XCTAssertTrue(hero.contains("let metaLayout = stacked\n            ? AnyLayout(VStackLayout(alignment: .leading, spacing: 4))"),
                      "control: the shared layout stacks at large text")
    }

    /// The chart's heading no longer repeats FINAL beside "Win Probability":
    /// the hero's chip says it, and the repeat put the range picker on a row of
    /// its own (the 375pt key under the tab bar).
    func testTheChartHeadingDoesNotRepeatFinal() throws {
        let here = URL(fileURLWithPath: #filePath)
        let url = here.deletingLastPathComponent().deletingLastPathComponent()
            .appendingPathComponent("Bain Luck/Components/OddsChartView.swift")
        let chart = try String(contentsOf: url, encoding: .utf8)
        let heading = try span(chart, from: "private var chartTitleAndStatus: some View {",
                               to: "private var chartHeaderTrailingControls: some View {")
        XCTAssertTrue(heading.contains("Text(\"Win Probability\")"), "control: scanning the heading")
        XCTAssertFalse(heading.contains("Text(\"Final\")"), "the heading says FINAL a second time")
        XCTAssertFalse(heading.contains("Text(\"Live\")"), "nor Live (#8320)")
    }
}
