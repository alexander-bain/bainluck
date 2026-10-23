import SwiftUI
import XCTest
@testable import Bain_Luck

/// #9483 / #11356 / #11296 — Design's first real-page reading of the adopted
/// chart (393×852, aa7d16bab9; DESIGN-RECEPTION of 10/22), one guard per finding:
///
/// - R1 cut a finished game's late collapse off the default plot (Jaguars
///   14639175: a 3.6% reading under a PHI 75% edge) →
///   `testAFinishedPrimaryKeepsItsWholeRangeOnTheDefaultPlot`,
///   `testAFinishedPrimaryCountsItsDrawnCheckpointsAndSurvivorsOnly`,
///   `testAFinishedPrimaryInventsNoEnd`, `testTheChartPassesFinishedToTheWindow`
/// - R2 a headline and a card under it comparing the final with OPPOSITE
///   pregame leaders (Packers 14780562: DAL 28–GB 27 over "Packers won as
///   projected" from a GB 27.5–DAL 26.5 history point) →
///   `testAFinishedCardComparesWithTheHeadlinesQualifiedForecast`,
///   `testWithoutTheHeadlinesForecastTheCardNamesItsOtherBasis`,
///   `testTheHistoryFallbackClaimsNoTimeItsEvidenceCannotProve` (Design on eae3:
///   the fallback's floor is the first OBSERVED game state, not kickoff),
///   `testTheBaselineChangesNothingBeforeTheFinal`,
///   `testTheQualifiedHalvesAreTheServedOnes`, `testThePageWiresOneBaselineToEveryComparison`
/// - R3 two bare "Sources" controls with different counts →
///   `testThePagesSourcesSayWhichNumberTheyMake`
/// - R4 Show/Hide stranded past the right edge at AX3, long key names cut off,
///   a 26×25pt full-size entry (and, found on the successor's own AX3 frame,
///   "Bain / Luck" broken across lines beside its reading) → `testTheFullSizeKeysControlIsOutsideTheScrollingRail`,
///   `testAKeyItemWiderThanItsRowWrapsInsideIt`, `testTheFullSizeEntryIsA44PointTarget`; V2 (Lane1b on
///   eae3: the open names rail could be chosen a few letters wide) →
///   `testTheOpenRailIsNeverChosenNarrowerThanOneReadableKey`
@MainActor
final class RealPageCorrections9483Tests: XCTestCase {

    private typealias Axis = ChartProbabilityAxis9483
    private typealias Chart = OddsChartView

    private static let start = Date(timeIntervalSince1970: 1_791_729_300)

    private func series(_ values: [Double], source: String = "aggregate") -> [ChartDataPoint] {
        values.enumerated().map { i, v in
            ChartDataPoint(date: Self.start.addingTimeInterval(Double(i) * 60), probability: v, source: source)
        }
    }

    private func ramp(_ a: Double, _ b: Double, _ n: Int) -> [Double] {
        (0..<n).map { a + (b - a) * Double($0) / Double(n - 1) }
    }

    private func window(_ lower: Int, _ upper: Int, _ ticks: [Int]) -> Axis.Window {
        Axis.Window(lowerPercent: lower, upperPercent: upper, tickPercents: ticks)
    }

    /// The Jaguars shape: a long middle, one late collapse to 3.6%, the end at 100%.
    private var collapse: [Double] { ramp(0.55, 0.80, 58) + [0.036, 1.0] }

    // MARK: - R1

    func testAFinishedPrimaryKeepsItsWholeRangeOnTheDefaultPlot() {
        let points = series(collapse)
        let open = Chart.probabilityWindow9483(points: points, defaultSources: ["aggregate"], revealed: [])
        XCTAssertFalse(open.domain.contains(0.036), "control: the percentile window cuts the collapse (\(open))")
        let finished = Chart.probabilityWindow9483(points: points, defaultSources: ["aggregate"], revealed: [],
                                                   primaryClosed: true)
        XCTAssertEqual(finished, window(0, 100, [0, 25, 50, 75, 100]))
        XCTAssertTrue(collapse.allSatisfy { finished.domain.contains($0) }, "every drawn reading is on the plot")
        XCTAssertEqual(points.map(\.probability), collapse, "no reading is edited")
        // Pre-game and live keep the percentile focus: not finished is the old window.
        XCTAssertEqual(Chart.probabilityWindow9483(points: points, defaultSources: ["aggregate"], revealed: [],
                                                   primaryClosed: false), open)
    }

    /// Under a checkpoint mount the journey is what the mount draws: the
    /// survivors and every drawn checkpoint, not a raw reading it cut.
    func testAFinishedPrimaryCountsItsDrawnCheckpointsAndSurvivorsOnly() {
        let survivors = series(ramp(0.60, 0.70, 60))
        let early = PublicationJourney4974.Checkpoint(
            vertex: PublicationCheckpointVertex(rev: 1, t: Self.start.ISO8601Format(), p: 0.20), date: Self.start)
        let lateDate = Self.start.addingTimeInterval(1_700)
        let latest = PublicationJourney4974.Checkpoint(
            vertex: PublicationCheckpointVertex(rev: 2, t: lateDate.ISO8601Format(), p: 0.66), date: lateDate)
        let open = Chart.probabilityWindow9483(points: survivors, defaultSources: ["aggregate"], revealed: [],
                                               checkpoints: [latest, early], blendSurvivors: survivors)
        XCTAssertFalse(open.domain.contains(0.20), "control: an early checkpoint is only a reading (\(open))")
        let finished = Chart.probabilityWindow9483(points: survivors, defaultSources: ["aggregate"], revealed: [],
                                                   checkpoints: [latest, early], blendSurvivors: survivors,
                                                   primaryClosed: true)
        XCTAssertTrue(finished.domain.contains(0.20), "the finished journey's drawn low (\(finished))")

        let raw = series([0.05] + ramp(0.60, 0.70, 30))
        let cut = Array(raw.dropFirst())
        XCTAssertEqual(
            Chart.probabilityWindow9483(points: raw, defaultSources: ["aggregate"], revealed: [],
                                        blendSurvivors: cut, primaryClosed: true),
            Chart.probabilityWindow9483(points: cut, defaultSources: ["aggregate"], revealed: [],
                                        primaryClosed: true),
            "a reading the mount does not draw sizes nothing")
    }

    /// The window's ends are axis furniture: a finished line that never went
    /// near 0 or 100 is not stretched to them, and a revealed source is not
    /// the primary's range.
    func testAFinishedPrimaryInventsNoEnd() {
        let calm = series(ramp(0.58, 0.72, 40))
        let finished = Chart.probabilityWindow9483(points: calm, defaultSources: ["aggregate"], revealed: [],
                                                   primaryClosed: true)
        XCTAssertEqual(finished, Chart.probabilityWindow9483(points: calm, defaultSources: ["aggregate"], revealed: []))
        XCTAssertGreaterThan(finished.lowerPercent, 0)
        XCTAssertLessThan(finished.upperPercent, 100)
        // Without a blend the primary is the consensus line, never another source.
        let noBlend = series(ramp(0.58, 0.72, 40), source: "consensus") + series(ramp(0.10, 0.12, 40), source: "kalshi")
        let w = Chart.probabilityWindow9483(points: noBlend, defaultSources: ["consensus"], revealed: [],
                                            primaryClosed: true)
        XCTAssertFalse(w.domain.contains(0.10), "an undrawn source is not the finished primary (\(w))")
    }

    func testTheChartPassesFinishedToTheWindow() throws {
        let chart = try code("Components", "OddsChartView.swift")
        XCTAssertTrue(chart.contains("liveAndOpen:status==\"live\"&&!EventState.isFinished(status)&&!venueSettled,"
                                     + "primaryClosed:EventState.isFinished(status))"),
                      "the default axis plan learns the game is finished")
    }

    // MARK: - R2

    private func pair(_ minutes: Double, home: Double, away: Double) -> ProjectedFinalPointsSeries.Pair {
        .init(at: Self.start.addingTimeInterval(minutes * 60), home: home, away: away, homeProbability: nil,
              kind: .recorded)
    }

    /// Packers 14780562's shape: home GB, away DAL; the history's last point
    /// before play favours GB 27.5–26.5, the final is GB 23–13.
    private func packersInput(final: Bool = true, sport: String = "americanfootball_nfl")
        -> ProjectedFinalPointsSeries.Input {
        .init(sportKey: sport, sourceKey: "draftkings", basis: .sameBookSameCaptureFullGameSpreadAndTotal,
              pairs: [pair(-30, home: 27.5, away: 26.5), pair(60, home: 25, away: 17)],
              actuals: final ? [.init(at: Self.start.addingTimeInterval(200 * 60), home: 23, away: 13)] : [],
              kickoffAt: nil, scoreObservationStartAt: Self.start,
              finalAt: final ? Self.start.addingTimeInterval(200 * 60) : nil,
              asOf: Self.start.addingTimeInterval((final ? 200 : 65) * 60),
              windowStartAt: nil, requestCutoffAt: nil)
    }

    /// The headline's served projection: away 27.6 / home 26.5 (DAL favoured).
    private let headlineHalves = (away: 27.6, home: 26.5)

    func testAFinishedCardComparesWithTheHeadlinesQualifiedForecast() throws {
        let history = try XCTUnwrap(NFLFinishCard9483.build(packersInput()))
        XCTAssertEqual(history.headline(awayName: "Cowboys", homeName: "Packers"), "Packers won as projected",
                       "control: the history point favours the winner")
        let card = try XCTUnwrap(NFLFinishCard9483.build(packersInput(), finalBaseline: headlineHalves))
        XCTAssertEqual(card.phase, .after)
        XCTAssertEqual(card.pregameBasis, .scheduledStart)
        XCTAssertEqual(card.pregame.away, 27.6, "keyed by team, never by value")
        XCTAssertEqual(card.pregame.home, 26.5)
        XCTAssertNil(card.pregame.at, "a capture range claims no single clock")
        XCTAssertEqual(card.headline(awayName: "Cowboys", homeName: "Packers"), "Packers beat the forecast")
        XCTAssertEqual(card.final?.home, 23, "the actual is unchanged")
        XCTAssertEqual(card.final?.away, 13)
        XCTAssertEqual(card.pregameLabel, "pregame projection")
        XCTAssertFalse(card.namesDistinctBasis)
        XCTAssertEqual(card.ladderPregame?.away, 27.6, "the NBA margin and total read the same pair")
        XCTAssertEqual(card.ladderPregame?.home, 26.5)
        XCTAssertEqual(card.withoutProjectedNow.pregameBasis, .scheduledStart, "expiry keeps the basis")
    }

    func testWithoutTheHeadlinesForecastTheCardNamesItsOtherBasis() throws {
        for baseline in [nil, (away: Double.nan, home: 26.5)] as [(away: Double, home: Double)?] {
            let card = try XCTUnwrap(NFLFinishCard9483.build(packersInput(), finalBaseline: baseline))
            XCTAssertEqual(card.pregameBasis, .history)
            XCTAssertEqual(card.pregame.home, 27.5, "the history point is kept, never zero or a current number")
            XCTAssertTrue(card.namesDistinctBasis)
            XCTAssertEqual(card.pregameLabel, "earlier forecast", "it does not borrow \"pregame projection\"")
            XCTAssertNil(card.ladderPregame, "no unqualified history pair reaches the ladders' \"Pregame projection\"")
        }
        // The baseline never creates a card the history refuses.
        let noHistory = ProjectedFinalPointsSeries.Input(
            sportKey: "americanfootball_nfl", sourceKey: "draftkings", basis: .sameBookSameCaptureFullGameSpreadAndTotal,
            pairs: [pair(60, home: 25, away: 17)],
            actuals: [.init(at: Self.start.addingTimeInterval(200 * 60), home: 23, away: 13)],
            kickoffAt: nil, scoreObservationStartAt: Self.start, finalAt: Self.start.addingTimeInterval(200 * 60),
            asOf: Self.start.addingTimeInterval(200 * 60), windowStartAt: nil, requestCutoffAt: nil)
        XCTAssertNil(NFLFinishCard9483.build(noHistory, finalBaseline: headlineHalves))
    }

    /// The history point is the last one before the instrument's first
    /// observed game state; production passes `kickoffAt: nil`, so nothing
    /// proves it preceded the start. Its caption, legend clause and spoken
    /// intro say "Earlier forecast" and claim no time; the qualified
    /// scheduled-start comparison keeps its words.
    func testTheHistoryFallbackClaimsNoTimeItsEvidenceCannotProve() throws {
        let fallback = try XCTUnwrap(NFLFinishCard9483.build(packersInput()))
        XCTAssertTrue(fallback.namesDistinctBasis, "control: the history fallback")
        XCTAssertEqual(NFLFinishCard9483.earlierForecast, "Earlier forecast")
        XCTAssertEqual(fallback.pregameLabel, "earlier forecast")
        let qualified = try XCTUnwrap(NFLFinishCard9483.build(packersInput(), finalBaseline: headlineHalves))
        XCTAssertEqual(qualified.pregameLabel, "pregame projection", "the qualified comparison is unchanged")
        XCTAssertEqual(fallback.key, "Points · outline = earlier forecast · cross = final",
                       "the legend clause names the earlier forecast")
        XCTAssertEqual(qualified.key, "Points · outline = pregame · cross = final", "the qualified legend is unchanged")
        XCTAssertEqual(fallback.pregameName, "Earlier forecast", "the spoken intro names the earlier forecast")
        XCTAssertEqual(qualified.pregameName, "Pregame projection", "the qualified one still says pregame")
        let view = try code("Components", "NFLEventCards9483.swift")
        XCTAssertTrue(view.contains("Text(card.key)"), "the legend is the card's own key")
        XCTAssertTrue(view.contains("\"\\(card.pregameName)\""), "the spoken intro is the card's own name")
        // The ladders' own "Before kickoff" (a different basis) is not this claim.
        for claim in ["beforeplay", "projectionbefore"] {
            XCTAssertFalse(view.lowercased().contains(claim), "the card view claims \"\(claim)\" again")
        }
    }

    func testTheBaselineChangesNothingBeforeTheFinal() throws {
        let live = try XCTUnwrap(NFLFinishCard9483.build(packersInput(final: false), finalBaseline: headlineHalves))
        XCTAssertEqual(live.phase, .during, "control: live")
        XCTAssertEqual(live, try XCTUnwrap(NFLFinishCard9483.build(packersInput(final: false))))
        // #9483 A3 — live on the history point: named for what it is, and no
        // unqualified pair reaches the ladders' "Pregame projection".
        XCTAssertEqual(live.pregameLabel, "earlier forecast")
        XCTAssertNil(live.ladderPregame)
    }

    private func projection(home: Double = 26.5, away: Double = 27.6, kind: String = "last_before_scheduled_start")
        -> PregameProjection {
        PregameProjection(projectedHomeScore: home, projectedAwayScore: away, kind: kind,
                          earliestCapturedAt: "2026-10-19T23:00:00Z", latestCapturedAt: "2026-10-20T00:10:00Z",
                          boundary: "scheduled_start", boundaryAt: "2026-10-20T00:20:00Z", source: "sportsbooks",
                          basis: "consensus_spread_total", bookmakerCount: 7, unit: "points", period: "full_game")
    }

    func testTheQualifiedHalvesAreTheServedOnes() throws {
        func q(_ p: PregameProjection) -> FinalForecastComparison11296.Qualified? {
            FinalForecastComparison11296.qualified(sport: "americanfootball_nfl", status: "completed",
                                                   homeScore: 23, awayScore: 13, actualPeriod: .fullGame, projection: p)
        }
        let qualified = try XCTUnwrap(q(projection()))
        XCTAssertEqual(qualified.away, 27.6)
        XCTAssertEqual(qualified.home, 26.5)
        XCTAssertEqual(qualified.comparison.away, 28, "the headline still rounds per side")
        XCTAssertEqual(qualified.comparison.home, 27)
        XCTAssertEqual(qualified.comparison, FinalForecastComparison11296.resolve(
            sport: "americanfootball_nfl", status: "completed", homeScore: 23, awayScore: 13,
            actualPeriod: .fullGame, projection: projection()), "one set of gates")
        XCTAssertNil(q(projection(kind: "opening")), "a refused projection gives no halves either")
        XCTAssertNil(FinalForecastComparison11296.qualified(
            sport: "americanfootball_nfl", status: "live", homeScore: 13, awayScore: 10,
            actualPeriod: .fullGame, projection: projection()), "finished only")
    }

    func testThePageWiresOneBaselineToEveryComparison() throws {
        let page = try code("Views", "EventDetailView.swift")
        XCTAssertTrue(page.contains("staticfuncfinalForecast11296(_event:EventDetail)->FinalForecastComparison11296.Comparison?{"
                                    + "qualifiedFinalForecast11296(event)?.comparison}"),
                      "the headline is the qualified forecast's own pair")
        XCTAssertTrue(page.contains("NFLFinishCard9483.build(projectedInput,finalBaseline:"
                                    + "Self.qualifiedFinalForecast11296(event).map{(away:$0.away,home:$0.home)},"
                                    + "liveBaseline:liveCardBaseline11296(event))"),
                      "the card compares with the same forecast")
        XCTAssertTrue(page.contains("pregameProjection:finish?.ladderPregame,"),
                      "the NBA margin and total read the card's pair")
        XCTAssertFalse(page.contains("finish.map{(home:$0.pregame.home,away:$0.pregame.away)}"),
                       "the ladders' old unqualified read is gone")
        let view = try code("Components", "NFLEventCards9483.swift")
        XCTAssertEqual(view.components(separatedBy: "label:card.pregameLabel").count - 1, 2, "both row layouts")
        XCTAssertFalse(view.contains("label:\"pregameprojection\""), "no row hard-codes the ordinary basis")
    }

    // MARK: - R3

    func testThePagesSourcesSayWhichNumberTheyMake() {
        XCTAssertEqual(EventDetailView.sourcesToggleLabel(sourceCount: 3), "Latest number's sources (3)")
        XCTAssertEqual(EventDetailView.sourcesToggleLabel(sourceCount: 1), "Latest number's sources (1)",
                       "the real count, never the chart's")
        XCTAssertFalse(EventDetailView.sourcesToggleLabel(sourceCount: 3).hasPrefix("Sources"),
                       "a second bare \"Sources\" beside the chart's")
        XCTAssertEqual(EventDetailView.sourcesToggleLabel(sourceCount: 0), "Individual Sportsbooks")
    }

    // MARK: - R4

    func testTheFullSizeKeysControlIsOutsideTheScrollingRail() throws {
        let chart = try code("Components", "OddsChartView.swift")
        let start = try XCTUnwrap(chart.range(of: "ifrail{letprimaryKey=legendKey("))
        let end = try XCTUnwrap(chart.range(of: "}else{FlowLayout(", range: start.upperBound..<chart.endIndex))
        let rail = String(chart[start.lowerBound..<end.lowerBound])
        let scroll = try XCTUnwrap(rail.range(of: "letnames=ScrollView(.horizontal"))
        let railEnd = try XCTUnwrap(rail.range(of: "Self.railRow9483(", range: scroll.upperBound..<rail.endIndex))
        let scrolled = String(rail[scroll.lowerBound..<railEnd.lowerBound])
        XCTAssertFalse(scrolled.contains("sourcesShowButton("), "Show is back inside the rail")
        XCTAssertFalse(scrolled.contains("sourcesHideButton("), "Hide is back inside the rail")
        XCTAssertFalse(scrolled.contains("primaryKey"), "the blend's name is back inside the rail")
        XCTAssertTrue(rail.contains("Self.railRow9483(primaryKey:primaryKey,control:control,names:names,"
                                    + "readableWidth:railReadableWidth9483)"),
                      "the full-size key lays out through the one row chooser")
        let row = try XCTUnwrap(chart.range(of: "staticfuncrailRow9483<"))
        let rowEnd = try XCTUnwrap(chart.range(of: "privatefuncrailControl9483(", range: row.upperBound..<chart.endIndex))
        let chooser = String(chart[row.lowerBound..<rowEnd.lowerBound])
        XCTAssertTrue(chooser.contains("ViewThatFits(in:.horizontal){HStack(spacing:12){primaryKey;control;rail}"
                                       + "VStack(alignment:.leading,spacing:0){primaryKeyHStack(spacing:12){control;rail}}}"),
                      "one row when it fits, the control and rail on a second row when not")
        let control = try XCTUnwrap(chart.range(of: "privatefuncrailControl9483("))
        let controlEnd = try XCTUnwrap(chart.range(of: "privatefuncsourcesShowButton(", range: control.upperBound..<chart.endIndex))
        let body = String(chart[control.lowerBound..<controlEnd.lowerBound])
        XCTAssertEqual(body.components(separatedBy: ".hidden().accessibilityHidden(true)").count - 1, 2,
                       "each state reserves the other's width, so tapping it moves nothing")
    }

    /// A key name wider than the inline row wraps inside it instead of
    /// running past the edge; items that fit are laid out as before.
    func testAKeyItemWiderThanItsRowWrapsInsideIt() {
        let long = "Sportsbook Consensus (market) and a much longer explanatory source name"
        func height(_ width: CGFloat) -> CGFloat {
            let view = FlowLayout(spacing: 8) {
                Text(long).font(.caption2).fixedSize(horizontal: false, vertical: true)
            }
            let host = hostForMeasurement(view.frame(width: width))
            return host.sizeThatFits(in: CGSize(width: width, height: 10_000)).height
        }
        let oneLine = height(2_000)
        XCTAssertGreaterThan(oneLine, 0, "control: the item draws")
        XCTAssertGreaterThan(height(120), oneLine * 1.5, "it wraps at the row's width")
        let chart = (try? code("Components", "OddsChartView.swift")) ?? ""
        XCTAssertFalse(chart.contains("Text(displayNameForSource(source,sources:sources)).font(isPrimary?.caption2.weight(.semibold):.caption2)"
                                      + ".foregroundStyle(isPrimary?.primary:.secondary).lineLimit(1).fixedSize()"),
                       "the key's name is pinned to one uncut line again")
        XCTAssertTrue(chart.contains("ViewThatFits(in:.horizontal){HStack(spacing:4){name;last.padding(.leading,2)}"
                                     + "VStack(alignment:.leading,spacing:1){name;last}}"),
                      "a key too wide for its row stacks its reading under the name, never breaking the name first")
    }

    /// Lane1b on eae3: with an ideal width of 0 the one-row arm won whenever
    /// the name and the control fit, so the opened names got whatever was
    /// left — about 40pt at xxxLarge, a swatch and a few letters. The rail
    /// now counts as one readable key, so the second row wins first, open or
    /// closed alike.
    func testTheOpenRailIsNeverChosenNarrowerThanOneReadableKey() throws {
        func height(name: CGFloat, open: Bool, readable: CGFloat) -> CGFloat {
            let names = ScrollView(.horizontal, showsIndicators: false) {
                HStack(spacing: 12) {
                    if open { Color.clear.frame(width: 300, height: 14) }
                }
                .fixedSize(horizontal: true, vertical: false)
            }
            let row = Chart.railRow9483(primaryKey: Color.clear.frame(width: name, height: 20),
                                        control: Color.clear.frame(width: 90, height: 44),
                                        names: names, readableWidth: readable)
            let host = hostForMeasurement(row.frame(width: 337))
            return host.sizeThatFits(in: CGSize(width: 337, height: 10_000)).height
        }
        let readable = Chart.railReadableKeyWidth9483
        XCTAssertGreaterThanOrEqual(readable, 14 + 4 + 40, "a swatch and a name, never a sliver")
        // xxxLarge: a 180pt name and a 90pt control leave 43pt beside them.
        let sliver = height(name: 180, open: true, readable: 0)
        XCTAssertGreaterThan(sliver, 0, "control: the row draws")
        let opened = height(name: 180, open: true, readable: readable)
        XCTAssertGreaterThan(opened, sliver + 10, "the control and rail take the second row instead of a 43pt rail")
        XCTAssertEqual(height(name: 180, open: false, readable: readable), opened, accuracy: 0.5,
                       "closed chooses the same row: Sources never moves the plot")
        // Normal text: the blend's name is about 123pt at 393, and one row still fits.
        let normal = height(name: 123, open: true, readable: readable)
        XCTAssertEqual(normal, height(name: 123, open: true, readable: 0), accuracy: 0.5, "normal size keeps one row")
        XCTAssertEqual(height(name: 123, open: false, readable: readable), normal, accuracy: 0.5)
        let chart = try code("Components", "OddsChartView.swift")
        XCTAssertTrue(chart.contains("@ScaledMetric(relativeTo:.caption2)privatevarrailReadableWidth9483:CGFloat="
                                     + "OddsChartView.railReadableKeyWidth9483"),
                      "the readable width scales with the key's text")
        XCTAssertFalse(chart.contains("names.frame(idealWidth:0"), "the rail is back to an ideal width of 0")
    }

    func testTheFullSizeEntryIsA44PointTarget() throws {
        let chart = try code("Components", "OddsChartView.swift")
        let start = try XCTUnwrap(chart.range(of: "privatevarchartHeaderTrailingControls:someView{"))
        let end = try XCTUnwrap(chart.range(of: "privatevartimeRangePicker:someView{", range: start.upperBound..<chart.endIndex))
        let entry = String(chart[start.lowerBound..<end.lowerBound])
        XCTAssertTrue(entry.contains("Image(systemName:\"arrow.up.left.and.arrow.down.right\")"), "control: the entry")
        XCTAssertTrue(entry.contains(".frame(minWidth:44,minHeight:44).contentShape(Rectangle())"),
                      "the whole 44pt square is the target")
        XCTAssertFalse(entry.contains(".padding(6)"), "the 26×25 target is back")
    }

    // MARK: - Source scans

    private func code(_ folder: String, _ file: String) throws -> String {
        let url = URL(fileURLWithPath: #filePath)
            .deletingLastPathComponent()
            .deletingLastPathComponent()
            .appendingPathComponent("Bain Luck/\(folder)/\(file)")
        return try String(contentsOf: url, encoding: .utf8)
            .split(separator: "\n", omittingEmptySubsequences: false)
            .map { line -> String in
                guard let slashes = line.range(of: "//") else { return String(line) }
                return String(line[line.startIndex..<slashes.lowerBound])
            }
            .joined(separator: "\n")
            .filter { !$0.isWhitespace }
    }
}
