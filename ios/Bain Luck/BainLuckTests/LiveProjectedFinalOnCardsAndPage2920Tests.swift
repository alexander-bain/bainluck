import XCTest
import SwiftUI
@testable import Bain_Luck

/// #2920 — the live projected final, as the two native cards and the event page
/// read it from the row they hold (`LiveProjectedFinal2920`).
///
/// `LiveProjectedFinalAdmission2920Tests` decides every gate of the helper; this
/// suite decides the WIRING: that each surface hands the helper its own row —
/// `currentOdds.liveProjection`, the row's start and flags, the score it prints,
/// soccer's served period — and that nothing else (the bare `projected_*` pair,
/// the ladders on a refused object) reaches a live surface.
///
/// FIXTURES: `nflObject` and `soccerObject` are the accepted producer's own
/// output (`a8df6e34cd`), carried verbatim from the decoder suite; `servedUGA`
/// is event 14870008's served `current_odds` body (bare pair 36.9 / 10.7), as
/// carried by the helper suite. The ROWS around them — status, start, score,
/// period — are CONSTRUCTED and say so. The producer's start is 2026-10-19
/// 20:25Z, so the wall clock is past it.
@MainActor
final class LiveProjectedFinalOnCardsAndPage2920Tests: XCTestCase {

    private typealias P = LiveProjectedFinalAdmission2920

    // MARK: - Fixtures

    private static let nflObject = #"""
    {"projected_home_score": 29.5, "projected_away_score": 19.0, "kind": "in_play", "boundary": "commence_time", "boundary_at": "2026-10-19T20:25:00+00:00", "earliest_confirmed_at": "2026-10-19T21:06:00+00:00", "latest_captured_at": "2026-10-19T21:06:00+00:00", "source": "sportsbooks", "basis": "consensus_spread_total", "bookmaker_count": 2, "unit": "points", "period": "full_game"}
    """#

    private static let soccerObject = #"""
    {"projected_home_score": 1.5, "projected_away_score": 1.0, "kind": "in_play", "boundary": "commence_time", "boundary_at": "2026-10-19T20:25:00+00:00", "earliest_confirmed_at": "2026-10-19T21:05:00+00:00", "latest_captured_at": "2026-10-19T21:05:00+00:00", "source": "sportsbooks", "basis": "consensus_spread_total", "bookmaker_count": 2, "unit": "goals", "period": "regulation"}
    """#

    /// Event 14870008's served `current_odds`; `LIVE_PROJECTION` marks the splice.
    private static let servedUGA = #"""
    {"captured_at": "2026-09-26T20:36:31.263891+00:00", "home_probability": 0.9369, "away_probability": 0.0631, "away_rendered_percent": 6, "home_rendered_percent": 94, "spread": -26.1, "over_under": 47.6, "projected_home_score": 36.9, "projected_away_score": 10.7, "bookmaker_count": 3LIVE_PROJECTION}
    """#

    private static let producerStart = "2026-10-19T20:25:00+00:00"

    // MARK: - Helpers

    private func decoder() -> JSONDecoder {
        let d = JSONDecoder()
        d.keyDecodingStrategy = .convertFromSnakeCase
        return d
    }

    /// A CONSTRUCTED live row around the served body, as JSON both models read.
    /// `liveProjection` is raw JSON spliced in as `"live_projection"`, or no key.
    private func rowJSON(
        sport: String = "americanfootball_nfl",
        status: String = "live",
        start: String = LiveProjectedFinalOnCardsAndPage2920Tests.producerStart,
        home: Int? = 14, away: Int? = 10,
        period: String? = "Q3",
        tbd: Bool = false,
        liveProjection: String?
    ) -> String {
        let odds = Self.servedUGA.replacingOccurrences(
            of: "LIVE_PROJECTION", with: liveProjection.map { #", "live_projection": "# + $0 } ?? "")
        let score: (Int?) -> String = { $0.map(String.init) ?? "null" }
        let espn = period.map { #"{"period": "\#($0)"}"# } ?? "null"
        return #"""
        {"id": 14870008, "sport": "\#(sport)", "home_team": "Georgia Bulldogs", "away_team": "Oklahoma Sooners", "commence_time": "\#(start)", "start_is_tbd": \#(tbd), "start_is_from_schedule": true, "status": "\#(status)", "home_score": \#(score(home)), "away_score": \#(score(away)), "current_odds": \#(odds), "espn": \#(espn)}
        """#
    }

    private func feedEvent(_ json: String, file: StaticString = #filePath, line: UInt = #line) throws -> FeedEventData {
        do { return try decoder().decode(FeedEventData.self, from: Data(json.utf8)) } catch {
            XCTFail("row did not decode: \(error)", file: file, line: line); throw error
        }
    }

    private func detail(_ json: String, file: StaticString = #filePath, line: UInt = #line) throws -> EventDetail {
        do { return try decoder().decode(EventDetail.self, from: Data(json.utf8)) } catch {
            XCTFail("row did not decode: \(error)", file: file, line: line); throw error
        }
    }

    private func sportsCard(_ e: FeedEventData) -> EventCardView {
        EventCardView(event: e, reason: nil)
    }

    private func discoverCard(_ e: FeedEventData) -> NativeEventDiscoverCard {
        NativeEventDiscoverCard(event: e, feedContext: nil, expandedContext: nil,
                                navigationPath: .constant(NavigationPath()))
    }

    /// Both cards' answers for one row.
    private func cards(_ json: String, file: StaticString = #filePath, line: UInt = #line)
        throws -> (sports: P.Printed?, discover: P.Printed?) {
        let e = try feedEvent(json, file: file, line: line)
        return (sportsCard(e).liveProjectedFinal2920, discoverCard(e).liveProjectedFinal2920)
    }

    // MARK: - Cards

    func testBothLiveCardsPrintTheObjectsPairAndNeverTheBarePair() throws {
        // The served body carries 36.9 / 10.7 (37 – 11); the object 29.5 / 19.0.
        // 30 – 19 can only have come from the object.
        let (sports, discover) = try cards(rowJSON(liveProjection: Self.nflObject))
        let p = try XCTUnwrap(sports, "Sports card wiring")
        XCTAssertEqual([p.home, p.away], [30, 19])
        XCTAssertEqual(p.label, "Projected final")
        XCTAssertEqual(discover, p, "Discover card wiring: the same answer as the Sports card")
        XCTAssertEqual(LiveProjectedFinal2920.pairText(p, awayName: "Oklahoma Sooners", homeName: "Georgia Bulldogs"),
                       "Oklahoma Sooners\u{00A0}19 · Georgia Bulldogs\u{00A0}30",
                       "away over home, as both cards stack the rows")
        XCTAssertEqual(LiveProjectedFinal2920.spokenText(p, awayName: "Oklahoma Sooners", homeName: "Georgia Bulldogs"),
                       "Projected final: Oklahoma Sooners 19, Georgia Bulldogs 30")
    }

    func testWithNoObjectServedALiveCardPrintsNothingThoughTheBarePairIsThere() throws {
        let row = rowJSON(liveProjection: nil)
        XCTAssertEqual(try feedEvent(row).currentOdds?.projectedHomeScore, 36.9, "anti-vacuity: the bare pair is on the row")
        let (sports, discover) = try cards(row)
        XCTAssertNil(sports)
        XCTAssertNil(discover)
        let (s2, d2) = try cards(rowJSON(liveProjection: "null"))
        XCTAssertNil(s2, "null is absent")
        XCTAssertNil(d2, "null is absent")
    }

    func testAMalformedObjectWithholdsAndNeverFallsBackToTheBarePair() throws {
        for bad in [#""in_play""#, "{}", "[]", "29.5"] {
            let row = rowJSON(liveProjection: bad)
            XCTAssertNotNil(try feedEvent(row).currentOdds?.liveProjection, "\(bad): a present value decodes non-nil")
            let (sports, discover) = try cards(row)
            XCTAssertNil(sports, bad)
            XCTAssertNil(discover, bad)
        }
    }

    func testOnlyALiveCardPrintsTheLiveObject() throws {
        XCTAssertNotNil(try cards(rowJSON(liveProjection: Self.nflObject)).sports, "positive control")
        for status in ["scheduled", "completed", "closed", "suspended", "postponed"] {
            let (sports, discover) = try cards(rowJSON(status: status, liveProjection: Self.nflObject))
            XCTAssertNil(sports, status)
            XCTAssertNil(discover, status)
        }
        // The row's own start says placeholder: the object no longer matches it.
        let tbd = try cards(rowJSON(tbd: true, liveProjection: Self.nflObject))
        XCTAssertNil(tbd.sports, "placeholder start")
        XCTAssertNil(tbd.discover, "placeholder start")
        XCTAssertEqual(LiveProjectedFinal2920.page(try detail(rowJSON(tbd: true, liveProjection: Self.nflObject))),
                       .withheld, "placeholder start on the page")
        // A live status whose start is still ahead is not live yet.
        let ahead = ISO8601DateFormatter().string(from: Date().addingTimeInterval(3600))
        XCTAssertNil(try cards(rowJSON(start: ahead, liveProjection: Self.nflObject)).sports, "not started")
    }

    func testTheCardReadsTheScoreItPrints() throws {
        // 30 – 19 is reachable from 14 – 10; one point past the home half is not.
        XCTAssertNotNil(try cards(rowJSON(home: 30, away: 19, liveProjection: Self.nflObject)).sports,
                        "equal to the projection is reachable")
        XCTAssertNil(try cards(rowJSON(home: 31, away: 10, liveProjection: Self.nflObject)).sports, "home passed")
        XCTAssertNil(try cards(rowJSON(home: 14, away: 20, liveProjection: Self.nflObject)).discover, "away passed")
        XCTAssertNil(try cards(rowJSON(home: nil, away: nil, liveProjection: Self.nflObject)).sports, "no score")
    }

    func testASoccerCardFollowsTheServedPeriod() throws {
        let soccer = { (period: String?) in
            self.rowJSON(sport: "soccer_epl", home: 1, away: 0, period: period, liveProjection: Self.soccerObject)
        }
        let p = try XCTUnwrap(try cards(soccer("67'")).sports, "regulation minute prints")
        XCTAssertEqual([p.home, p.away], [2, 1])
        XCTAssertEqual(p.label, "Projected final (90 min)")
        XCTAssertEqual(try cards(soccer("90'+4'")).discover, p, "stoppage after 90 is regulation")
        for period in ["91'", "ET", "AET", "Pen.", "FT", nil] as [String?] {
            let (sports, discover) = try cards(soccer(period))
            XCTAssertNil(sports, period ?? "nil")
            XCTAssertNil(discover, period ?? "nil")
        }
    }

    func testAnUnsupportedSportsLiveCardPrintsNothing() throws {
        for sport in ["icehockey_nhl", "baseball_mlb", "tennis_atp_paris"] {
            XCTAssertNil(try cards(rowJSON(sport: sport, liveProjection: Self.nflObject)).sports, sport)
        }
    }

    // MARK: - Event page

    func testThePageReadsTheSameObjectTheCardReads() throws {
        let row = rowJSON(liveProjection: Self.nflObject)
        guard case .admitted(let p) = LiveProjectedFinal2920.page(try detail(row)) else {
            return XCTFail("the page must admit the object the card admits")
        }
        XCTAssertEqual(p, try cards(row).sports, "card and page: one answer")
        XCTAssertEqual([p.admitted.home, p.admitted.away], [29.5, 19.0], "the raw pair the page's gates round")
    }

    func testThePageWithholdsARefusedObjectAndOnlyAnAbsentOneKeepsTheLadders() throws {
        XCTAssertEqual(LiveProjectedFinal2920.page(try detail(rowJSON(liveProjection: nil))), .absent)
        XCTAssertEqual(LiveProjectedFinal2920.page(try detail(rowJSON(liveProjection: "null"))), .absent)
        XCTAssertEqual(LiveProjectedFinal2920.page(try detail(rowJSON(liveProjection: "{}"))), .withheld,
                       "a malformed object is refused, not absent")
        XCTAssertEqual(LiveProjectedFinal2920.page(try detail(rowJSON(home: 31, away: 10, liveProjection: Self.nflObject))),
                       .withheld, "an unreachable pair is refused")
        XCTAssertEqual(LiveProjectedFinal2920.page(try detail(rowJSON(sport: "soccer_epl", period: "ET",
                                                                     liveProjection: Self.soccerObject))),
                       .withheld, "extra time refuses the held regulation object")
    }

    func testThePagesPreGameAndFinishedRulesAreNotTheLiveOnes() throws {
        for status in ["scheduled", "completed", "suspended"] {
            XCTAssertEqual(LiveProjectedFinal2920.page(try detail(rowJSON(status: status, liveProjection: Self.nflObject))),
                           .notLive, status)
        }
        let ahead = ISO8601DateFormatter().string(from: Date().addingTimeInterval(3600))
        XCTAssertEqual(LiveProjectedFinal2920.page(try detail(rowJSON(start: ahead, liveProjection: Self.nflObject))),
                       .notLive, "live but not started keeps the pre-game rule, as the card does")
    }

    func testOnALiveGameTheLaddersPrintOnlyWhenTheCallerSaysNoObjectWasServed() {
        let underway = Date(timeIntervalSince1970: 1_760_905_500) // a fixed past start
        let now = underway.addingTimeInterval(2700)
        XCTAssertEqual(EventDetailView.projectionText(
            sport: "americanfootball_nfl", status: "live", commenceTime: underway,
            projectedHome: nil, projectedAway: nil, ladderHome: 27.2, ladderAway: 20.4,
            ladderWhileLive: true, hasScore: true, now: now), "Proj. 20-27")
        XCTAssertNil(EventDetailView.projectionText(
            sport: "americanfootball_nfl", status: "live", commenceTime: underway,
            projectedHome: nil, projectedAway: nil, ladderHome: 27.2, ladderAway: 20.4,
            hasScore: true, now: now), "by default a live game never reads the ladders")
    }

    // MARK: - Wiring (source guards)

    private func source(_ path: String) throws -> String {
        let url = URL(fileURLWithPath: #filePath)
            .deletingLastPathComponent()   // BainLuckTests
            .deletingLastPathComponent()   // Bain Luck (project dir)
            .appendingPathComponent("Bain Luck")
            .appendingPathComponent(path)
        let text = try String(contentsOf: url, encoding: .utf8)
        return text.split(separator: "\n", omittingEmptySubsequences: false)
            .map { line -> String in
                guard let slashes = line.range(of: "//") else { return String(line) }
                return String(line[line.startIndex..<slashes.lowerBound])
            }
            .joined(separator: "\n")
            .filter { !$0.isWhitespace }
    }

    private func occurrences(_ needle: String, in haystack: String) -> Int {
        haystack.components(separatedBy: needle).count - 1
    }

    func testBothCardsDrawTheLiveLineOnceThroughTheHelper() throws {
        let sports = try source("Components/EventCardView.swift")
        let discover = try source("Components/DiscoverEventCard.swift")
        XCTAssertTrue(sports.contains("structEventCardView:View{"), "anti-vacuity")
        XCTAssertTrue(discover.contains("structNativeEventDiscoverCard:View{"), "anti-vacuity")
        for (name, code) in [("EventCardView", sports), ("DiscoverEventCard", discover)] {
            XCTAssertEqual(occurrences("LiveProjectedFinalLine2920(", in: code), 1, name)
            XCTAssertEqual(occurrences("ifletliveProjection=liveProjectedFinal2920{", in: code), 1, name)
            XCTAssertTrue(code.contains("guardisLive,!isSuspendedelse{returnnil}returnLiveProjectedFinal2920.card(event)"), name)
            XCTAssertFalse(code.contains("liveProjection?."), "\(name): the card never reads the object's fields itself")
            XCTAssertFalse(code.contains("projectedHomeScore"), "\(name): no live card reads the bare pair")
        }
    }

    func testThePageChoosesItsPairThroughTheLiveReader() throws {
        let page = try source("Views/EventDetailView.swift")
        let start = try XCTUnwrap(page.range(of: "privatefuncprojectionText(_event:EventDetail,hasScore:Bool)->String?{"))
        let end = try XCTUnwrap(page.range(of: "staticfuncprojectionText(", range: start.upperBound..<page.endIndex))
        let body = String(page[start.upperBound..<end.lowerBound])
        XCTAssertTrue(body.contains("letlive=LiveProjectedFinal2920.page(event)"))
        XCTAssertTrue(body.contains("case.withheld:returnnil"), "a refused object prints nothing")
        XCTAssertTrue(body.contains("case.absent:projected=(nil,nil)"), "no object: never the bare pair")
        XCTAssertTrue(body.contains("case.admitted(letprinted):projected=(printed.admitted.home,printed.admitted.away)"))
        XCTAssertTrue(body.contains("ladderWhileLive:live==.absent"), "the ladders only when nothing was served")
        XCTAssertEqual(occurrences("liveProjection", in: page), 0, "the page never reads the object's fields itself")
    }
}
