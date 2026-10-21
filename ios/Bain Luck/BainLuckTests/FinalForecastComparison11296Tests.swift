import XCTest
import SwiftUI
@testable import Bain_Luck

/// #11296 — the forecast line under a native finished card's actual result.
///
/// Ported gate for gate from the accepted web helper's suite
/// (`frontend/__tests__/lib/finalForecastComparison11296.test.ts`). Every
/// refusal sits beside a positive control that differs from it in the one
/// field under test, so a refusal can only pass because that field refused it.
///
/// FIXTURE, AND WHAT IT IS: `Self.servedItems` below is TRIMMED from
/// Authority's served capture
/// `~/bainluck-dev/authority/artifacts-authority-11296-d2b-served/api_feed_mode_sports.json`
/// (production `/api/feed?mode=sports`, sha256 `0d66af94…52eb4`, 2026-10-20
/// 07:10Z). Five event items, in this order, each keeping its served `type`,
/// `score`, `reason`, `headline`, and these `data` keys verbatim: id,
/// external_id, sport, sport_name, home_team, away_team, commence_time,
/// start_is_tbd, start_is_from_schedule, status, home_score, away_score,
/// ended_at, and whichever of pregame_projection /
/// pregame_projection_unavailable the row carried. Every other key was dropped
/// (none is read here). Embedded rather than a Fixtures file because this
/// slice's grant names five paths and a fixture file would be a sixth.
///
///   14780563  NFL  Commanders 17 @ 49ers 23   served home 29.4 / away 22.2, 21 books
///   15326903  soccer, a served positive (1.2 / 0.8, regulation) — withheld here
///   15332425  NHL   format_unsupported
///   15330968  WNBA  no_pregame_reading
///   15332758  MLB   format_unsupported
///
/// Cases that need another state build a `PregameProjection` or edit one value
/// of a served body and say so: those are CONSTRUCTED, never claimed as served.
@MainActor
final class FinalForecastComparison11296Tests: XCTestCase {

    private typealias F = FinalForecastComparison11296

    private static let expectedNFL = F.Comparison(
        label: "Projection before scheduled start", away: 22, home: 29, bookmakerCount: 21)

    // MARK: - Helpers

    private func decoder() -> JSONDecoder {
        let d = JSONDecoder()
        d.keyDecodingStrategy = .convertFromSnakeCase
        return d
    }

    private func items(_ json: String = FinalForecastComparison11296Tests.servedItems) throws -> [FeedItem] {
        try decoder().decode([FeedItem].self, from: Data(json.utf8))
    }

    private func served(_ id: Int) throws -> FeedEventData {
        try XCTUnwrap(items().compactMap(\.event).first { $0.id == id }, "served event \(id) did not decode")
    }

    private func sportsCard(_ e: FeedEventData) -> EventCardView {
        EventCardView(event: e, reason: nil)
    }

    private func discoverCard(_ e: FeedEventData) -> NativeEventDiscoverCard {
        NativeEventDiscoverCard(event: e, feedContext: nil, expandedContext: nil,
                                navigationPath: .constant(NavigationPath()))
    }

    /// The served NFL projection, field for field; each argument overrides one.
    private func projection(
        home: Double? = 29.4,
        away: Double? = 22.2,
        kind: String? = "last_before_scheduled_start",
        earliest: String? = "2026-10-19T22:15:21.773164+00:00",
        latest: String? = "2026-10-20T00:12:13.153004+00:00",
        boundary: String? = "scheduled_start",
        boundaryAt: String? = "2026-10-20T00:15:00+00:00",
        source: String? = "sportsbooks",
        basis: String? = "consensus_spread_total",
        books: Double? = 21,
        unit: String? = "points",
        period: String? = "full_game"
    ) -> PregameProjection {
        PregameProjection(
            projectedHomeScore: home, projectedAwayScore: away, kind: kind,
            earliestCapturedAt: earliest, latestCapturedAt: latest, boundary: boundary,
            boundaryAt: boundaryAt, source: source, basis: basis, bookmakerCount: books,
            unit: unit, period: period)
    }

    /// The served NFL final's inputs; each argument overrides one.
    private func resolve(
        _ p: PregameProjection?,
        sport: String? = "americanfootball_nfl",
        status: String? = "completed",
        home: Int? = 23,
        away: Int? = 17,
        period: F.ScorePeriod? = .fullGame
    ) -> F.Comparison? {
        F.resolve(sport: sport, status: status, homeScore: home, awayScore: away,
                  actualPeriod: period, projection: p)
    }

    // MARK: - The served fixture decodes through the real feed path

    func testTheServedItemsDecodeThroughFeedItemWithTheirProjectionsIntact() throws {
        let decoded = try items()
        XCTAssertEqual(decoded.count, 5, "a served item was dropped in decode")
        XCTAssertEqual(decoded.map(\.type), Array(repeating: "event", count: 5))
        XCTAssertEqual(decoded.compactMap(\.event).map(\.id),
                       [14780563, 15326903, 15332425, 15330968, 15332758])

        let nfl = try served(14780563)
        XCTAssertEqual(nfl.sport, "americanfootball_nfl")
        XCTAssertEqual(nfl.awayTeam, "Washington Commanders")
        XCTAssertEqual(nfl.homeTeam, "San Francisco 49ers")
        XCTAssertEqual(nfl.awayScore, 17)
        XCTAssertEqual(nfl.homeScore, 23)
        XCTAssertEqual(nfl.pregameProjection, projection(), "every served field must decode as served")
        XCTAssertNil(nfl.pregameProjectionUnavailable)

        let soccer = try served(15326903)
        XCTAssertEqual(soccer.pregameProjection, projection(
            home: 1.2, away: 0.8,
            earliest: "2026-10-20T00:05:34.521964+00:00",
            latest: "2026-10-20T00:14:51.898122+00:00",
            books: 3, unit: "goals", period: "regulation"))

        for (id, reason) in [(15332425, "format_unsupported"), (15330968, "no_pregame_reading"),
                             (15332758, "format_unsupported")] {
            let e = try served(id)
            XCTAssertNil(e.pregameProjection, "\(id) served no projection")
            XCTAssertEqual(e.pregameProjectionUnavailable, reason, "\(id)")
        }
    }

    // MARK: - Admitted: the served NFL final

    func testTheServedNFLFinalPrintsItsPregamePairOnBothCards() throws {
        let e = try served(14780563)
        XCTAssertEqual(resolve(e.pregameProjection), Self.expectedNFL)
        XCTAssertEqual(sportsCard(e).finalForecast11296, Self.expectedNFL, "Sports card wiring")
        XCTAssertEqual(discoverCard(e).finalForecast11296, Self.expectedNFL, "Discover card wiring")
        // The actual final is untouched: the card keeps printing 17 and 23.
        XCTAssertEqual(e.awayScore, 17)
        XCTAssertEqual(e.homeScore, 23)
    }

    func testTheLineReadsAwayOverHomeWithEachCardsOwnFullNames() throws {
        let e = try served(14780563)
        let c = try XCTUnwrap(sportsCard(e).finalForecast11296)
        XCTAssertEqual(F.label, "Projection before scheduled start", "web's FINAL_FORECAST_LABEL, verbatim")
        XCTAssertEqual(c.label, F.label)
        XCTAssertEqual(F.pairText(c, awayName: e.awayTeam, homeName: e.homeTeam),
                       "Washington Commanders\u{00A0}22 · San Francisco 49ers\u{00A0}29")
        XCTAssertEqual(F.spokenText(c, awayName: e.awayTeam, homeName: e.homeTeam),
                       "Projection before scheduled start: Washington Commanders 22, San Francisco 49ers 29")
        XCTAssertFalse(c.label.lowercased().contains("kickoff"), "the boundary is the SCHEDULED start")
    }

    func testTheComparisonCarriesNoGrading() throws {
        let c = try XCTUnwrap(resolve(projection()))
        XCTAssertEqual(Mirror(reflecting: c).children.compactMap(\.label),
                       ["label", "away", "home", "bookmakerCount"],
                       "no winner, hit/miss or colour field")
    }

    // MARK: - Orientation is keyed, never by value

    func testSwappingTheServedHalvesSwapsThePrintedHalvesAndNothingElse() {
        XCTAssertEqual(resolve(projection())?.away, 22)
        XCTAssertEqual(resolve(projection())?.home, 29)
        let swapped = resolve(projection(home: 22.2, away: 29.4))
        XCTAssertEqual(swapped?.away, 29)
        XCTAssertEqual(swapped?.home, 22)
    }

    func testTheActualScoresOrderDoesNotMoveTheForecast() {
        XCTAssertEqual(resolve(projection(), home: 10, away: 40), Self.expectedNFL)
    }

    // MARK: - Served refusals

    func testTheServedSoccerPositiveIsWithheldWithoutRegulationEvidence() throws {
        let e = try served(15326903)
        XCTAssertNotNil(e.pregameProjection, "precondition: the producer served it")
        XCTAssertNil(sportsCard(e).finalForecast11296)
        XCTAssertNil(discoverCard(e).finalForecast11296)
        for period: F.ScorePeriod? in [.fullGame, nil] {
            XCTAssertNil(resolve(e.pregameProjection, sport: e.sport, home: 1, away: 1, period: period))
        }
        // Control: the gate is the PERIOD, not the sport. With regulation
        // evidence (which no payload carries today) the same object prints,
        // level included — a league draw is a soccer result.
        XCTAssertEqual(
            resolve(e.pregameProjection, sport: e.sport, home: 1, away: 1, period: .regulation),
            F.Comparison(label: F.label, away: 1, home: 1, bookmakerCount: 3))
    }

    func testTheServedUnavailableRowsPrintNothing() throws {
        for id in [15332425, 15330968, 15332758] {
            let e = try served(id)
            XCTAssertNil(sportsCard(e).finalForecast11296, "\(id)")
            XCTAssertNil(discoverCard(e).finalForecast11296, "\(id)")
        }
    }

    func testTheWNBARefusalIsTheAbsentProjectionNotTheSport() throws {
        // CONSTRUCTED: the served WNBA final given a points projection.
        var e = try served(15330968)
        e.pregameProjection = projection(home: 70.2, away: 79.6)
        XCTAssertEqual(sportsCard(e).finalForecast11296,
                       F.Comparison(label: F.label, away: 80, home: 70, bookmakerCount: 21))
        XCTAssertEqual(discoverCard(e).finalForecast11296?.away, 80)
    }

    func testTheNHLAndMLBRefusalsHoldEvenWithAProjection() throws {
        // CONSTRUCTED: an otherwise-admitted object on the served hockey and
        // baseball finals. Their sportsbook pair is not a final score.
        for (id, unit) in [(15332425, "goals"), (15332425, "points"), (15332758, "points")] {
            var e = try served(id)
            e.pregameProjection = projection(home: 3.6, away: 2.4, unit: unit)
            XCTAssertNil(sportsCard(e).finalForecast11296, "\(id) \(unit)")
            XCTAssertNil(discoverCard(e).finalForecast11296, "\(id) \(unit)")
        }
    }

    // MARK: - Finished means completed or closed

    func testOnlyAFinishedStatusIsAdmitted() throws {
        for status in ["completed", "closed"] {
            XCTAssertEqual(resolve(projection(), status: status), Self.expectedNFL, status)
        }
        for status: String? in ["scheduled", "live", "suspended", "final", "", nil] {
            XCTAssertNil(resolve(projection(), status: status), String(describing: status))
        }
        // CONSTRUCTED: the served NFL body, status edited. The cards follow.
        let live = Self.servedItems.replacingOccurrences(
            of: #""status": "completed",\#n      "home_score": 23"#,
            with: #""status": "live",\#n      "home_score": 23"#)
        XCTAssertNotEqual(live, Self.servedItems, "precondition: the edit landed")
        let e = try XCTUnwrap(items(live).compactMap(\.event).first { $0.id == 14780563 })
        XCTAssertEqual(e.status, "live")
        XCTAssertNil(sportsCard(e).finalForecast11296)
        XCTAssertNil(discoverCard(e).finalForecast11296)
    }

    // MARK: - Kind, boundary, source, basis

    func testOnlyTheProducedKindIsAdmitted() {
        for kind: String? in ["latest_before_play", "opening", "closing", "", nil] {
            XCTAssertNil(resolve(projection(kind: kind)), String(describing: kind))
        }
        XCTAssertNotNil(resolve(projection(kind: "last_before_scheduled_start")))
    }

    func testOnlyTheScheduledStartBoundaryIsAdmitted() {
        for boundary: String? in ["observed_start", "market_close", "", nil] {
            XCTAssertNil(resolve(projection(boundary: boundary)), String(describing: boundary))
        }
        XCTAssertNotNil(resolve(projection(boundary: "scheduled_start")))
    }

    func testOnlySportsbooksAndTheConsensusBasisAreAdmitted() {
        for source: String? in ["kalshi", "polymarket", "", nil] {
            XCTAssertNil(resolve(projection(source: source)), String(describing: source))
        }
        for basis: String? in ["model_fair_line", "moneyline", "", nil] {
            XCTAssertNil(resolve(projection(basis: basis)), String(describing: basis))
        }
        XCTAssertNotNil(resolve(projection(source: "sportsbooks", basis: "consensus_spread_total")))
    }

    // MARK: - Unit and period

    func testTheUnitMustMatchTheSport() {
        XCTAssertNil(resolve(projection(unit: "goals")))
        XCTAssertNil(resolve(projection(unit: nil)))
        XCTAssertNotNil(resolve(projection(unit: "points")))
    }

    func testTheActualPeriodMustMatchWhatTheLinesSettleOn() {
        for period: F.ScorePeriod? in [nil, .regulation] {
            XCTAssertNil(resolve(projection(), period: period), String(describing: period))
        }
        XCTAssertNil(resolve(projection(period: "regulation")), "an NFL forecast served as regulation")
        XCTAssertNil(resolve(projection(period: nil)))
        XCTAssertNotNil(resolve(projection(), period: .fullGame))
    }

    func testSportsWhosePairIsNotAFinalScoreAreRefused() {
        let cases: [(String?, String)] = [
            ("icehockey_nhl", "goals"), ("icehockey_ahl", "goals"), ("baseball_mlb", "points"),
            ("tennis_atp_shanghai", "points"), ("mma_mixed_martial_arts", "points"),
            ("boxing_boxing", "points"), (nil, "points"), ("", "points"),
        ]
        for (sport, unit) in cases {
            XCTAssertNil(resolve(projection(unit: unit), sport: sport, home: 4, away: 3),
                         String(describing: sport))
        }
        XCTAssertNotNil(resolve(projection(), home: 4, away: 3), "control: the same payload on NFL")
        XCTAssertNotNil(resolve(projection(home: 118.6, away: 112.2), sport: "basketball_nba"),
                        "control: basketball is admitted")
    }

    // MARK: - Stamps and counts

    func testMalformedStampsAreRefused() {
        XCTAssertNil(resolve(projection(earliest: "2026-10-20T00:13:00+00:00")), "earliest after latest")
        XCTAssertNil(resolve(projection(latest: "2026-10-20T00:15:00+00:00")), "latest AT the boundary")
        XCTAssertNil(resolve(projection(latest: "2026-10-20T03:25:00+00:00")), "latest after the boundary")
        XCTAssertNil(resolve(projection(earliest: "yesterday")), "unparseable earliest")
        XCTAssertNil(resolve(projection(boundaryAt: "")), "empty boundary_at")
        XCTAssertNil(resolve(projection(latest: nil)), "absent latest")
    }

    func testMalformedCountsAreRefused() {
        for books: Double? in [0, -1, 1.5, nil, .infinity, .nan, 1e19] {
            XCTAssertNil(resolve(projection(books: books)), String(describing: books))
        }
        // Controls: a whole count Int can hold prints, however large, so 1e19
        // is refused for being unrepresentable, not for being big.
        XCTAssertEqual(resolve(projection(books: 21))?.bookmakerCount, 21, "control: the served count")
        XCTAssertEqual(resolve(projection(books: 1e15))?.bookmakerCount, 1_000_000_000_000_000,
                       "control: a large representable count")
    }

    func testOneBookOneStampJustBeforeTheBoundaryIsAdmitted() {
        let p = projection(earliest: "2026-10-20T00:14:59+00:00", latest: "2026-10-20T00:14:59+00:00", books: 1)
        XCTAssertEqual(resolve(p)?.bookmakerCount, 1)
    }

    /// The served stamps: microseconds on the readings, whole seconds on the
    /// boundary. `String.asDate` keeps whole milliseconds (`ISO8601Stamp`), so
    /// the strict `latest < boundary` comparison runs on these values.
    func testTheServedStampsParseAtTheirServedPrecision() throws {
        let earliest = try XCTUnwrap("2026-10-19T22:15:21.773164+00:00".asDate)
        XCTAssertEqual(earliest.timeIntervalSince1970, 1_792_448_121.773, accuracy: 0.0005)
        XCTAssertGreaterThan(abs(earliest.timeIntervalSince1970 - 1_792_448_121.773164), 0.0001,
                             "the fraction is kept to whole milliseconds, as the formatter keeps it")
        let latest = try XCTUnwrap("2026-10-20T00:12:13.153004+00:00".asDate)
        XCTAssertEqual(latest.timeIntervalSince1970, 1_792_455_133.153, accuracy: 0.0005)
        let boundary = try XCTUnwrap("2026-10-20T00:15:00+00:00".asDate)
        XCTAssertEqual(boundary.timeIntervalSince1970, 1_792_455_300)
        XCTAssertLessThan(earliest, latest)
        XCTAssertLessThan(latest, boundary)
    }

    // MARK: - Values and rounding

    func testNonPositiveOrAbsentForecastHalvesAreRefused() {
        for v: Double? in [0, -0.5, nil, .infinity, .nan, 1e19] {
            XCTAssertNil(resolve(projection(home: v)), "home \(String(describing: v))")
            XCTAssertNil(resolve(projection(away: v)), "away \(String(describing: v))")
        }
        // Controls: the served halves print, and so does a large half Int can
        // hold, so 1e19 is refused for being unrepresentable, not for being big.
        XCTAssertEqual(resolve(projection())?.home, 29, "control: the served home half")
        XCTAssertEqual(resolve(projection())?.away, 22, "control: the served away half")
        XCTAssertEqual(resolve(projection(home: 1e15))?.home, 1_000_000_000_000_000,
                       "control: a large representable home half")
        XCTAssertEqual(resolve(projection(away: 1e15))?.away, 1_000_000_000_000_000,
                       "control: a large representable away half")
    }

    func testAbsentOrNegativeActualScoresAreRefused() {
        for v: Int? in [nil, -1] {
            XCTAssertNil(resolve(projection(), home: v), "home \(String(describing: v))")
            XCTAssertNil(resolve(projection(), away: v), "away \(String(describing: v))")
        }
        XCTAssertNotNil(resolve(projection(), home: 0, away: 0), "control: 0–0 is a finite final")
    }

    func testRoundingIsPerSideHalfUp() {
        let c = resolve(projection(home: 24.5, away: 20.49))
        XCTAssertEqual(c?.home, 25)
        XCTAssertEqual(c?.away, 20)
    }

    /// Web's `cardProjectedFinal` refuses a level pair only where the sport
    /// cannot end level (#8156). Basketball cannot; the NFL can (a tie after
    /// one overtime), so a level NFL pair prints on web and prints here.
    func testALevelPairIsRefusedOnlyWhereTheSportCannotEndLevel() {
        let level = projection(home: 110.4, away: 110.2)
        XCTAssertNil(resolve(level, sport: "basketball_nba", home: 112, away: 118))
        XCTAssertEqual(
            resolve(projection(home: 118.6, away: 112.2), sport: "basketball_nba", home: 112, away: 118),
            F.Comparison(label: F.label, away: 112, home: 119, bookmakerCount: 21),
            "control: an unlevel NBA pair")
        XCTAssertEqual(resolve(projection(home: 24.4, away: 23.6))?.home, 24)
        XCTAssertEqual(resolve(projection(home: 24.4, away: 23.6))?.away, 24)
    }

    // MARK: - A malformed projection never drops the card

    func testAMalformedProjectionStillDecodesTheCardAndPrintsNothing() throws {
        let valid = #"{"projected_home_score": 29.4, "projected_away_score": 22.2, "kind": "last_before_scheduled_start", "earliest_captured_at": "2026-10-19T22:15:21.773164+00:00", "latest_captured_at": "2026-10-20T00:12:13.153004+00:00", "boundary": "scheduled_start", "boundary_at": "2026-10-20T00:15:00+00:00", "source": "sportsbooks", "basis": "consensus_spread_total", "bookmaker_count": 21, "unit": "points", "period": "full_game"}"#
        func card(_ projectionJSON: String) throws -> FeedEventData? {
            let json = #"[{"type": "event", "score": 35, "data": {"id": 14780563, "sport": "americanfootball_nfl", "home_team": "San Francisco 49ers", "away_team": "Washington Commanders", "status": "completed", "home_score": 23, "away_score": 17, "pregame_projection": "#
                + projectionJSON + "}}]"
            return try items(json).first?.event
        }
        // Control: the envelope with the served object prints.
        XCTAssertEqual(try card(valid).flatMap { sportsCard($0).finalForecast11296 }, Self.expectedNFL)

        let malformed = [
            "null",
            #""oops""#,
            "[1, 2]",
            "{}",
            valid.replacingOccurrences(of: #""projected_home_score": 29.4"#, with: #""projected_home_score": "29.4""#),
            valid.replacingOccurrences(of: #""bookmaker_count": 21"#, with: #""bookmaker_count": "21""#),
        ]
        for body in malformed {
            XCTAssertNotEqual(body, valid, "precondition: the mutation landed")
            let e = try XCTUnwrap(try card(body), "the card must still decode: \(body)")
            XCTAssertEqual(e.homeScore, 23, "the rest of the card decodes")
            XCTAssertNil(sportsCard(e).finalForecast11296, body)
            XCTAssertNil(discoverCard(e).finalForecast11296, body)
        }
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

    func testBothCardsDrawTheLineOnceThroughTheHelper() throws {
        let sports = try source("Components/EventCardView.swift")
        let discover = try source("Components/DiscoverEventCard.swift")
        XCTAssertTrue(sports.contains("structEventCardView:View{"), "anti-vacuity")
        XCTAssertTrue(discover.contains("structNativeEventDiscoverCard:View{"), "anti-vacuity")
        for (name, code) in [("EventCardView", sports), ("DiscoverEventCard", discover)] {
            XCTAssertEqual(occurrences("FinalForecastLine11296(", in: code), 1, name)
            XCTAssertEqual(occurrences("ifletfinalForecast=finalForecast11296{", in: code), 1, name)
            XCTAssertEqual(occurrences("FinalForecastLine11296(comparison:finalForecast,awayName:event.awayTeam,homeName:event.homeTeam)", in: code), 1, name)
            XCTAssertTrue(code.contains("actualPeriod:.fullGame,projection:event.pregameProjection)"), name)
            XCTAssertFalse(code.contains("Projectionbeforescheduledstart"), "\(name): the label is the helper's one spelling")
            XCTAssertFalse(code.contains("pregameProjectionUnavailable"), "\(name): the refusal reason renders nowhere")
        }
    }

    func testTheLineWrapsAndIsNeverTruncated() throws {
        let helper = try source("Utilities/FinalForecastComparison11296.swift")
        let start = try XCTUnwrap(helper.range(of: "structFinalForecastLine11296:View{"))
        let line = String(helper[start.lowerBound...])
        XCTAssertFalse(line.contains(".lineLimit("), "full names wrap; nothing is cut")
        XCTAssertTrue(line.contains(".fixedSize(horizontal:false,vertical:true)"))
        XCTAssertTrue(line.contains(".font(.caption)"), "a text style, so Dynamic Type ramps it")
        XCTAssertTrue(line.contains(".foregroundStyle(.secondary)"), "secondary to the actual final")
    }

    // MARK: - The trimmed served fixture

    private static let servedItems = #"""
    [
      {
        "type": "event",
        "score": 35,
        "reason": "",
        "headline": null,
        "data": {
          "id": 14780563,
          "external_id": "f122527f003276d3bca19efa48c902c1",
          "sport": "americanfootball_nfl",
          "sport_name": "NFL",
          "home_team": "San Francisco 49ers",
          "away_team": "Washington Commanders",
          "commence_time": "2026-10-20T00:15:00+00:00",
          "start_is_tbd": false,
          "start_is_from_schedule": true,
          "status": "completed",
          "home_score": 23,
          "away_score": 17,
          "ended_at": "2026-10-20T03:22:26.523221+00:00",
          "pregame_projection": {
            "projected_home_score": 29.4,
            "projected_away_score": 22.2,
            "kind": "last_before_scheduled_start",
            "earliest_captured_at": "2026-10-19T22:15:21.773164+00:00",
            "latest_captured_at": "2026-10-20T00:12:13.153004+00:00",
            "boundary": "scheduled_start",
            "boundary_at": "2026-10-20T00:15:00+00:00",
            "source": "sportsbooks",
            "basis": "consensus_spread_total",
            "bookmaker_count": 21,
            "unit": "points",
            "period": "full_game"
          }
        }
      },
      {
        "type": "event",
        "score": 28,
        "reason": "",
        "headline": null,
        "data": {
          "id": 15326903,
          "external_id": "475ceeb0bfb323ff19700f0b90ed6980",
          "sport": "soccer_argentina_primera_division",
          "sport_name": "Primera División - Argentina",
          "home_team": "Deportivo Riestra",
          "away_team": "Union Santa Fe",
          "commence_time": "2026-10-20T00:15:00+00:00",
          "start_is_tbd": false,
          "start_is_from_schedule": true,
          "status": "completed",
          "home_score": 1,
          "away_score": 1,
          "ended_at": "2026-10-20T02:10:36.340211+00:00",
          "pregame_projection": {
            "projected_home_score": 1.2,
            "projected_away_score": 0.8,
            "kind": "last_before_scheduled_start",
            "earliest_captured_at": "2026-10-20T00:05:34.521964+00:00",
            "latest_captured_at": "2026-10-20T00:14:51.898122+00:00",
            "boundary": "scheduled_start",
            "boundary_at": "2026-10-20T00:15:00+00:00",
            "source": "sportsbooks",
            "basis": "consensus_spread_total",
            "bookmaker_count": 3,
            "unit": "goals",
            "period": "regulation"
          }
        }
      },
      {
        "type": "event",
        "score": 49,
        "reason": "Philadelphia Flyers won as a 30% underdog",
        "headline": "Recent upset",
        "data": {
          "id": 15332425,
          "external_id": "c8d71abe9d49ca6ea219b84923b9a48c",
          "sport": "icehockey_nhl",
          "sport_name": "NHL",
          "home_team": "Philadelphia Flyers",
          "away_team": "Colorado Avalanche",
          "commence_time": "2026-10-19T23:00:00+00:00",
          "start_is_tbd": false,
          "start_is_from_schedule": true,
          "status": "completed",
          "home_score": 3,
          "away_score": 2,
          "ended_at": "2026-10-20T01:45:30.701420+00:00",
          "pregame_projection_unavailable": "format_unsupported"
        }
      },
      {
        "type": "event",
        "score": 22,
        "reason": "",
        "headline": "Playoff game",
        "data": {
          "id": 15330968,
          "external_id": null,
          "sport": "basketball_wnba",
          "sport_name": "WNBA",
          "home_team": "Golden State Valkyries",
          "away_team": "Atlanta Dream",
          "commence_time": "2026-10-20T00:00:00+00:00",
          "start_is_tbd": false,
          "start_is_from_schedule": true,
          "status": "completed",
          "home_score": 65,
          "away_score": 79,
          "ended_at": "2026-10-20T02:24:30.896718+00:00",
          "pregame_projection_unavailable": "no_pregame_reading"
        }
      },
      {
        "type": "event",
        "score": 56,
        "reason": "",
        "headline": "Playoff game",
        "data": {
          "id": 15332758,
          "external_id": "be50f6c59c20efa430eec6f146a0fcb1",
          "sport": "baseball_mlb",
          "sport_name": "MLB",
          "home_team": "Tampa Bay Rays",
          "away_team": "Cleveland Guardians",
          "commence_time": "2026-10-20T00:00:00+00:00",
          "start_is_tbd": false,
          "start_is_from_schedule": true,
          "status": "completed",
          "home_score": 7,
          "away_score": 3,
          "ended_at": "2026-10-20T03:09:34.641577+00:00",
          "pregame_projection_unavailable": "format_unsupported"
        }
      }
    ]
    """#
}
