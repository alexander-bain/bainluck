import XCTest
@testable import Bain_Luck

/// #8320 slice 2 — THE LIVE HERO CARRIES THE STORY, NOT THE CONTEXT.
///
/// Alex, rage shake #150, White Sox–Royals (15317520), 2026-09-23 6:06 PM PDT
/// (`artifacts/event-page-feedback-20260924/user-screen-2.png`): "This whole
/// area at the top of the screen is overcrowded and clowny looking." Around
/// one blended number the live hero also drew the broadcast, the start time,
/// both records, "Royals 48% → 53% since open", a sparkline, "Proj. 6-7" and
/// "Opened 52% – 48%"; the score-by-inning table then stood between the hero
/// and the chart, and the bar said "CHW 4 - KC 4" above a hero saying 4 and 4.
///
/// After, on a LIVE game only: the hero keeps chip, crests, score and the pair;
/// records, opening line and projection join broadcast and start time in Game
/// Info; the inning table follows the chart; and the bar names the matchup
/// until the hero has scrolled under it. Scheduled and final heroes are
/// unchanged.
///
/// The placement rules are pure and tested directly. The wiring lives in
/// `View` bodies, so it is pinned by comment-stripped source scans
/// (`ALiveEventPageSaysItsFreshnessOnce8320Tests` is the model).
final class ALiveHeroCarriesTheStoryNotTheContext8320Tests: XCTestCase {

    // MARK: - The rules

    func testOnlyALiveHeroHandsItsContextOver() {
        XCTAssertFalse(EventDetailView.heroCarriesGameContext(status: "live"),
                       "the live hero still carries broadcast/records/opening/projection")
        for status in ["scheduled", "completed", "final", "suspended", "postponed"] {
            XCTAssertTrue(EventDetailView.heroCarriesGameContext(status: status),
                          "a \(status) hero lost its context; only live hands it over")
        }
        XCTAssertTrue(EventDetailView.heroCarriesGameContext(status: nil))
    }

    func testTheBarTakesTheScoreOnlyOnceTheHeroIsUnderIt() {
        // Hero on screen: its bottom is below where the bar stops covering.
        XCTAssertFalse(EventDetailView.navTitleShowsScore(heroBottom: 420, viewportTop: 116),
                       "the bar repeats the score the visible hero states")
        XCTAssertFalse(EventDetailView.navTitleShowsScore(heroBottom: 117, viewportTop: 116))
        // Hero gone under the bar.
        XCTAssertTrue(EventDetailView.navTitleShowsScore(heroBottom: 116, viewportTop: 116))
        XCTAssertTrue(EventDetailView.navTitleShowsScore(heroBottom: -300, viewportTop: 116),
                      "the score left the screen entirely once the hero scrolled away")
    }

    func testAnUnmeasuredHeroKeepsTheScoreInTheBar() {
        // A measurement that never arrives may cost a duplicate, never a score.
        XCTAssertTrue(EventDetailView.navTitleShowsScore(heroBottom: nil, viewportTop: 0))
        XCTAssertTrue(EventDetailView.navTitleShowsScore(heroBottom: nil, viewportTop: 116))
    }

    // MARK: - The wiring

    private func pageCode() throws -> String {
        let url = URL(fileURLWithPath: #filePath)
            .deletingLastPathComponent()   // BainLuckTests
            .deletingLastPathComponent()   // Bain Luck (project dir)
            .appendingPathComponent("Bain Luck")
            .appendingPathComponent("Views")
            .appendingPathComponent("EventDetailView.swift")
        return try String(contentsOf: url, encoding: .utf8)
            .split(separator: "\n", omittingEmptySubsequences: false)
            .map { line -> String in
                guard let slashes = line.range(of: "//") else { return String(line) }
                return String(line[line.startIndex..<slashes.lowerBound])
            }
            .joined(separator: "\n")
            .filter { !$0.isWhitespace }
    }

    /// The code between two anchors, each of which must occur exactly once.
    private func span(_ code: String, from start: String, to end: String,
                      file: StaticString = #filePath, line: UInt = #line) throws -> String {
        let starts = code.components(separatedBy: start).count - 1
        XCTAssertEqual(starts, 1, "anchor \(start) found \(starts) times", file: file, line: line)
        let lower = try XCTUnwrap(code.range(of: start), file: file, line: line)
        let upper = try XCTUnwrap(code.range(of: end, range: lower.upperBound..<code.endIndex),
                                  "no \(end) after \(start)", file: file, line: line)
        return String(code[lower.lowerBound..<upper.lowerBound])
    }

    private func heroCode() throws -> String {
        try span(pageCode(), from: "privatefuncheroSection(", to: "staticletverdictSlotWidth")
    }

    func testTheScanCanSeeTheFileItIsAbout() throws {
        let code = try pageCode()
        XCTAssertTrue(code.contains("structEventDetailView:View{"))
        XCTAssertGreaterThan(try heroCode().count, 3_000, "the hero span is far too short")
    }

    func testTheHeroGatesEveryPieceOfContextOnTheOneRule() throws {
        let hero = try heroCode()
        XCTAssertTrue(hero.contains(
            "letcarriesContext=EventDetailView.heroCarriesGameContext(status:event.status)"))
        for gated in [
            "ifcarriesContext,letbroadcast=event.espn?.broadcast",
            "ifcarriesContext,letcommenceTime=event.commenceTime",
            "ifcarriesContext,letrecord=event.awayTeamData?.record",
            "ifcarriesContext,letrecord=event.homeTeamData?.record",
            "ifcarriesContext,letcaption=SinceOpenCaption.caption(",
            "ifcarriesContext,letprojection=projectionText(event,hasScore:hasScore)",
        ] {
            XCTAssertTrue(hero.contains(gated), "the hero no longer gates: \(gated)")
        }
    }

    func testTheSparklineAndTheLiveOpenedLineAreGoneFromTheHero() throws {
        let code = try pageCode()
        XCTAssertFalse(code.contains("LiveSparklineChart("),
                       "the hero sparkline is back; it thumbnails the chart one card below")
        XCTAssertFalse(code.contains("ifisLive,letopened="),
                       "the hero's live 'Opened' line is back")
    }

    func testGameInfoReceivesWhatTheLiveHeroHandedOver() throws {
        let info = try span(pageCode(), from: "privatefuncespnSection(", to: "staticfunchasAnyProbabilityEvidence(")
        XCTAssertTrue(info.contains("EventDetailView.heroCarriesGameContext(status:event.status)?[]:["),
                      "Game Info no longer keys its extra rows on the hero's rule")
        for fact in ["recordsText(event)", "openedText(event)", "projectionText("] {
            XCTAssertTrue(info.contains(fact), "Game Info lost \(fact)")
        }
        XCTAssertTrue(info.contains("!handedOver.isEmpty"),
                      "a live game with only handed-over facts would hide the card")
        XCTAssertTrue(info.contains("ForEach(handedOver"))
    }

    func testTheInningTableFollowsTheChart() throws {
        let content = try span(pageCode(), from: "privatevarcontentView:someView{",
                               to: "privatefuncgameMarketsHaveContent(")
        let chart = try XCTUnwrap(content.range(of: "OddsChartView(eventId:"))
        let segments = try XCTUnwrap(content.range(of: "GameSegmentsView("))
        let hero = try XCTUnwrap(content.range(of: "heroSection(event)"))
        XCTAssertLessThan(hero.lowerBound, chart.lowerBound)
        XCTAssertLessThan(chart.lowerBound, segments.lowerBound,
                          "the inning table stands between the hero and the chart again")
        XCTAssertEqual(content.components(separatedBy: "GameSegmentsView(").count - 1, 1)
    }

    func testTheBarReadsTheMeasuredHero() throws {
        let code = try pageCode()
        let title = try span(code, from: "privatevarnavTitleView:someView{",
                             to: "privatefuncscoreProtectedTitle(")
        XCTAssertTrue(title.contains(
            "Self.navTitleShowsScore(heroBottom:heroBottom,viewportTop:scrollViewportTop)"))
        XCTAssertTrue(title.contains("Text(scorelessTitle)"),
                      "the fallback title still prints dynamicTitle, which carries the score")
        XCTAssertFalse(title.contains("Text(dynamicTitle)"))
        // Both measurements are actually published and received.
        XCTAssertTrue(code.contains(".onPreferenceChange(HeroBottomPreferenceKey.self){heroBottom=$0}"))
        XCTAssertTrue(code.contains(
            ".onPreferenceChange(ScrollViewportTopPreferenceKey.self){scrollViewportTop=$0}"))
        XCTAssertTrue(code.contains(
            "key:HeroBottomPreferenceKey.self,value:proxy.frame(in:.named(Self.scrollSpace)).maxY"))
        XCTAssertTrue(code.contains(".coordinateSpace(name:Self.scrollSpace)"))
    }
}
