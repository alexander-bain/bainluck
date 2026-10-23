import CryptoKit
import SwiftUI
import XCTest
@testable import Bain_Luck

/// #11296 — a soccer final compared with the 90-minute forecast before it, on
/// both finished cards, a saved pin's card and the event page's headline.
///
/// PILLARS: FORMATTING / TRUTH. SHIP: finished native cards and the generic
/// headline compare the actual result with a genuine retained forecast,
/// including evidenced ninety-minute soccer.
///
/// The producer now serves `final_score_period: "regulation"` beside a soccer
/// final whose own stored period says it ended at full time (PR #11363 detail,
/// PR #11371 list). That witness — and only it — admits the regulation
/// forecast; everything else stays withheld, as the accepted helper suite
/// (`FinalForecastComparison11296Tests`) already pins for every other gate.
///
/// FIXTURES, AND WHAT THEY ARE (UX's saved production reads of event 15330334,
/// Stuttgart 1–1 Atlético Madrid, Champions League, retained by Design under
/// `soccer-final-comparison-followthrough-20261021/reader-15330334-20261021/ux-original/`):
///
///   `servedDetail`  `/api/events/15330334`, BYTE FOR BYTE (`detail.json`,
///                   sha256 de63adf1…86b6c2 — the first test re-hashes it).
///   `leagueRow`     that event's row in `/api/leagues/soccer_uefa_champs_league`
///                   `recent_results` (`league.json`), every key verbatim, in a
///                   CONSTRUCTED one-item feed envelope (`type`/`score`/`data`).
///   `preProducerListRow`  that event's `/api/events` list row from before
///                   PR #11371 (`list.json`), trimmed to the keys named in it,
///                   values verbatim: it carries neither key, and prints nothing.
///
/// Any other state edits one key of a served body and says so: CONSTRUCTED,
/// never claimed as served.
@MainActor
final class FinalComparisonSoccerPeriod11296Tests: XCTestCase {

    private typealias F = FinalForecastComparison11296

    /// 1.5 / 1.9 goals rounds per side, half up, to Stuttgart 2, Atlético 2;
    /// four sportsbooks. A level pair prints: a league draw is a soccer result.
    private static let expected = F.Comparison(
        label: "Projection (90 min) before scheduled start", away: 2, home: 2, bookmakerCount: 4)

    // MARK: - Helpers

    private func decoder() -> JSONDecoder {
        let d = JSONDecoder()
        d.keyDecodingStrategy = .convertFromSnakeCase
        return d
    }

    private func detail(_ json: String = FinalComparisonSoccerPeriod11296Tests.servedDetail) throws -> EventDetail {
        try decoder().decode(EventDetail.self, from: Data(json.utf8))
    }

    private func feedEvent(_ data: String) throws -> FeedEventData {
        let json = #"[{"type":"event","score":40,"data":"# + data + "}]"
        let items = try decoder().decode([FeedItem].self, from: Data(json.utf8))
        return try XCTUnwrap(items.first?.event, "the card must decode")
    }

    private func sportsCard(_ e: FeedEventData) -> EventCardView {
        EventCardView(event: e, reason: nil)
    }

    private func discoverCard(_ e: FeedEventData) -> NativeEventDiscoverCard {
        NativeEventDiscoverCard(event: e, feedContext: nil, expandedContext: nil,
                                navigationPath: .constant(NavigationPath()))
    }

    /// Every surface's answer for one body: Sports card, Discover card, saved
    /// pin card, headline. The cards read the league row, the headline and the
    /// pin read the detail.
    private func surfaces(league: String, detail detailJSON: String) throws -> [String: F.Comparison?] {
        let card = try feedEvent(league)
        let page = try detail(detailJSON)
        return [
            "sports": sportsCard(card).finalForecast11296,
            "discover": discoverCard(card).finalForecast11296,
            "pin": sportsCard(FeedEventData(savedPinDetail: page)).finalForecast11296,
            "headline": EventDetailView.finalForecast11296(page),
        ]
    }

    /// One served key rewritten, exactly once; a target that is not there
    /// exactly once fails the test rather than passing on an unedited body.
    private func edited(_ body: String, _ from: String, _ to: String,
                        file: StaticString = #filePath, line: UInt = #line) -> String {
        XCTAssertEqual(body.components(separatedBy: from).count - 1, 1,
                       "edit target must occur once: \(from)", file: file, line: line)
        return body.replacingOccurrences(of: from, with: to)
    }

    private static let servedWitness = #""final_score_period":"regulation""#

    // MARK: - The saved reads decode through the real models

    func testTheServedDetailIsTheSavedBytesAndDecodesItsWitnessAndForecast() throws {
        let digest = SHA256.hash(data: Data(Self.servedDetail.utf8))
            .map { String(format: "%02x", $0) }.joined()
        XCTAssertEqual(digest, "de63adf164674eac7e1ab4f415a75b367bf82b0089bb3f355c2b60b98586b6c2",
                       "the embedded detail is UX's saved read, byte for byte")

        let e = try detail()
        XCTAssertEqual(e.sport, "soccer_uefa_champs_league")
        XCTAssertEqual(e.status, "completed")
        XCTAssertEqual(e.homeTeam, "VfB Stuttgart")
        XCTAssertEqual(e.awayTeam, "Atlético Madrid")
        XCTAssertEqual(e.homeScore, 1)
        XCTAssertEqual(e.awayScore, 1)
        XCTAssertEqual(e.finalScorePeriod, "regulation")
        XCTAssertEqual(e.pregameProjection, PregameProjection(
            projectedHomeScore: 1.5, projectedAwayScore: 1.9, kind: "last_before_scheduled_start",
            earliestCapturedAt: "2026-10-20T18:37:57.209904+00:00",
            latestCapturedAt: "2026-10-20T18:56:23.853083+00:00",
            boundary: "scheduled_start", boundaryAt: "2026-10-20T19:00:00+00:00",
            source: "sportsbooks", basis: "consensus_spread_total", bookmakerCount: 4,
            unit: "goals", period: "regulation"))

        let card = try feedEvent(Self.leagueRow)
        XCTAssertEqual(card.finalScorePeriod, "regulation")
        XCTAssertEqual(card.pregameProjection, e.pregameProjection, "the list and the page serve one object")
    }

    // MARK: - Admitted: the served regulation final

    func testEverySurfacePrintsTheNinetyMinuteForecastBesideTheActualDraw() throws {
        let answers = try surfaces(league: Self.leagueRow, detail: Self.servedDetail)
        XCTAssertEqual(answers.count, 4)
        for (surface, answer) in answers {
            XCTAssertEqual(answer, Self.expected, surface)
        }
        XCTAssertEqual(F.label90Min, "Projection (90 min) before scheduled start",
                       "web's FINAL_FORECAST_LABEL_90_MIN, verbatim")
        // The actual result is untouched: every surface keeps printing 1 and 1.
        let page = try detail()
        XCTAssertEqual([page.awayScore, page.homeScore], [1, 1])
        // Each team beside its own number, away then home as every arm lays them out.
        XCTAssertEqual(F.pairText(Self.expected, awayName: page.awayTeam, homeName: page.homeTeam),
                       "Atlético Madrid\u{00A0}2 · VfB Stuttgart\u{00A0}2")
        XCTAssertEqual(F.spokenText(Self.expected, awayName: page.awayTeam, homeName: page.homeTeam),
                       "Projection (90 min) before scheduled start: Atlético Madrid 2, VfB Stuttgart 2")
    }

    func testSwappingTheServedHalvesSwapsThePrintedHalvesOnTheHeadline() throws {
        // CONSTRUCTED: 1.5 / 1.9 → 0.6 / 2.6, so a home/away swap is visible.
        let body = edited(Self.servedDetail,
                          #""projected_home_score":1.5,"projected_away_score":1.9"#,
                          #""projected_home_score":0.6,"projected_away_score":2.6"#)
        let c = try XCTUnwrap(EventDetailView.finalForecast11296(try detail(body)))
        XCTAssertEqual([c.away, c.home], [3, 1], "Atlético's 2.6 prints beside Atlético")
    }

    // MARK: - Withheld: anything but the served regulation witness

    func testEveryOtherServedPeriodWithholdsTheLineAndNeverTheCard() throws {
        let replacements: [(String, String)] = [
            ("absent", ""),
            ("null", #""final_score_period":null"#),
            ("full_game", #""final_score_period":"full_game""#),
            ("extra_time", #""final_score_period":"extra_time""#),
            ("penalties", #""final_score_period":"penalties""#),
            ("unknown", #""final_score_period":"unknown""#),
            ("capitalised", #""final_score_period":"Regulation""#),
            ("empty", #""final_score_period":"""#),
            ("number", #""final_score_period":90"#),
            ("object", #""final_score_period":{"value":"regulation"}"#),
        ]
        for (name, replacement) in replacements {
            func swap(_ body: String) -> String {
                // "absent" drops the key with its leading comma.
                replacement.isEmpty
                    ? edited(body, "," + Self.servedWitness, "")
                    : edited(body, Self.servedWitness, replacement)
            }
            let league = swap(Self.leagueRow)
            let answers = try surfaces(league: league, detail: swap(Self.servedDetail))
            for (surface, answer) in answers {
                XCTAssertNil(answer, "\(name): \(surface)")
            }
            // The card and the page still decode with their result.
            XCTAssertEqual(try feedEvent(league).homeScore, 1, name)
            XCTAssertEqual(try detail(swap(Self.servedDetail)).awayScore, 1, name)
        }
    }

    func testTheFullTimeClockIsNotAWitness() throws {
        // The detail still says FT on ESPN's clock and the forecast still says
        // regulation; without the producer's witness neither is read as one.
        let body = edited(Self.servedDetail, "," + Self.servedWitness, "")
        let page = try detail(body)
        XCTAssertEqual(page.espn?.period, "FT", "precondition: the clock still reads FT")
        XCTAssertEqual(page.pregameProjection?.period, "regulation", "precondition")
        XCTAssertNil(page.finalScorePeriod)
        XCTAssertNil(EventDetailView.finalForecast11296(page))
    }

    func testTheCurrentOddsPairIsNeverTheForecast() throws {
        // `current_odds` on this final is the sportsbooks' latest, in-play
        // reading (1.5 / 2.0, captured 21:01Z) — it rounds to the same 2–2, so
        // only its absence from the answer proves it is not substituted.
        let page = try detail(edited(Self.servedDetail,
                                     #""pregame_projection":{"#, #""pregame_projection_off":{"#))
        XCTAssertEqual(page.currentOdds?.projectedAwayScore, 2.0, "precondition: the in-play pair is served")
        XCTAssertNil(page.pregameProjection)
        XCTAssertEqual(page.finalScorePeriod, "regulation", "precondition: the witness stays")
        XCTAssertNil(EventDetailView.finalForecast11296(page))
    }

    func testTheWitnessDoesNotAdmitAForecastOfAnotherPeriodOrUnit() throws {
        for (from, to) in [(#""period":"regulation""#, #""period":"full_game""#),
                           (#""unit":"goals""#, #""unit":"points""#),
                           (#""kind":"last_before_scheduled_start""#, #""kind":"latest_before_play""#)] {
            XCTAssertNil(EventDetailView.finalForecast11296(try detail(edited(Self.servedDetail, from, to))), to)
        }
    }

    func testOnlyAFinishedHeadlinePrintsIt() throws {
        for status in ["live", "scheduled", "suspended"] {
            let body = edited(Self.servedDetail, #""status":"completed""#, #""status":"\#(status)""#)
            XCTAssertNil(EventDetailView.finalForecast11296(try detail(body)), status)
        }
        let closed = edited(Self.servedDetail, #""status":"completed""#, #""status":"closed""#)
        XCTAssertEqual(EventDetailView.finalForecast11296(try detail(closed)), Self.expected, "control: closed is finished")
    }

    func testTheRowServedBeforeTheListProducerPrintsNothing() throws {
        let e = try feedEvent(Self.preProducerListRow)
        XCTAssertNil(e.pregameProjection)
        XCTAssertNil(e.finalScorePeriod)
        XCTAssertNil(sportsCard(e).finalForecast11296)
        XCTAssertNil(discoverCard(e).finalForecast11296)
        XCTAssertEqual([e.awayScore, e.homeScore], [1, 1], "the result still prints")
    }

    // MARK: - The period rule, per sport

    func testFootballAndBasketballFinalsAreTheFullGameWhateverIsServed() {
        for sport in ["americanfootball_nfl", "americanfootball_ncaaf", "basketball_nba", "basketball_wnba"] {
            for served: String? in [nil, "regulation", "extra_time"] {
                XCTAssertEqual(F.actualPeriod(sport: sport, servedFinalScorePeriod: served), .fullGame,
                               "\(sport) \(served ?? "nil")")
            }
        }
        // Their label keeps its meaning: no "(90 min)" on a full-game pair.
        let nfl = PregameProjection(
            projectedHomeScore: 29.4, projectedAwayScore: 22.2, kind: "last_before_scheduled_start",
            earliestCapturedAt: "2026-10-19T22:15:21.773164+00:00",
            latestCapturedAt: "2026-10-20T00:12:13.153004+00:00",
            boundary: "scheduled_start", boundaryAt: "2026-10-20T00:15:00+00:00",
            source: "sportsbooks", basis: "consensus_spread_total", bookmakerCount: 21,
            unit: "points", period: "full_game")
        XCTAssertEqual(
            F.resolve(sport: "americanfootball_nfl", status: "completed", homeScore: 23, awayScore: 17,
                      actualPeriod: F.actualPeriod(sport: "americanfootball_nfl", servedFinalScorePeriod: nil),
                      projection: nfl)?.label,
            "Projection before scheduled start")
    }

    func testSoccerIsRegulationOnlyOnTheServedWitnessAndOtherSportsAreNothing() {
        XCTAssertEqual(F.actualPeriod(sport: "soccer_uefa_champs_league", servedFinalScorePeriod: "regulation"),
                       .regulation)
        for served: String? in [nil, "full_game", "extra_time", "penalties", "Regulation", ""] {
            XCTAssertNil(F.actualPeriod(sport: "soccer_epl", servedFinalScorePeriod: served), served ?? "nil")
        }
        for sport: String? in ["icehockey_nhl", "baseball_mlb", "tennis_atp_us_open", "mma_mixed_martial_arts", nil] {
            XCTAssertNil(F.actualPeriod(sport: sport, servedFinalScorePeriod: "regulation"), sport ?? "nil")
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

    func testTheHeadlineDrawsTheCardsOneLineOnceThroughTheHelper() throws {
        let page = try source("Views/EventDetailView.swift")
        XCTAssertTrue(page.contains("privatefuncheroSection(_event:EventDetail)->someView{"), "anti-vacuity")
        XCTAssertEqual(occurrences("FinalForecastLine11296(", in: page), 1)
        XCTAssertEqual(occurrences(
            "ifletfinalForecast=Self.finalForecast11296(event){FinalForecastLine11296(comparison:finalForecast,awayName:event.awayTeam,homeName:event.homeTeam)}",
            in: page), 1)
        // Inside the hero, after its arms and before its own padding.
        let hero = try XCTUnwrap(page.range(of: "privatefuncheroSection(_event:EventDetail)->someView{"))
        let line = try XCTUnwrap(page.range(of: "ifletfinalForecast=Self.finalForecast11296(event){"))
        let heroEnd = try XCTUnwrap(page.range(of: ".padding(approvedPair?.horizontal:.all)", range: hero.upperBound..<page.endIndex))
        XCTAssertTrue(hero.upperBound < line.lowerBound && line.upperBound < heroEnd.lowerBound)
        XCTAssertTrue(page.contains(
            "actualPeriod:FinalForecastComparison11296.actualPeriod(sport:event.sport,servedFinalScorePeriod:event.finalScorePeriod),projection:event.pregameProjection)"))
        XCTAssertFalse(page.contains("Projectionbeforescheduledstart"), "the label is the helper's one spelling")
        XCTAssertFalse(page.contains("Projection(90min)beforescheduledstart"), "the label is the helper's one spelling")
    }

    // MARK: - Saved reads

    private static let servedDetail = ##"""
    {"id":15330334,"external_id":"56989e10c299aba1a0fce210bb214775","sport":"soccer_uefa_champs_league","sport_name":"UEFA Champions League","home_team":"VfB Stuttgart","away_team":"Atlético Madrid","commence_time":"2026-10-20T19:00:00+00:00","start_is_tbd":false,"start_is_from_schedule":true,"completed_at":"2026-10-20T20:52:00.499184+00:00","status":"completed","started_without_result":false,"home_score":1,"away_score":1,"score_source":"espn","score_observed_at":"2026-10-21T00:59:19.870317+00:00","home_team_data":{"team_id":18819,"slug":"vfb-stuttgart-ucl","primary_color":"#ffffff","secondary_color":"#DA0308","logo_small":"https://a.espncdn.com/i/teamlogos/soccer/500/134.png","logo_large":"https://a.espncdn.com/i/teamlogos/soccer/500/134.png","record":"2-1-0","abbreviation":"VFB"},"away_team_data":{"team_id":2293,"slug":"atltico-madrid-league","primary_color":"#ca3624","secondary_color":"#000000","logo_small":"https://a.espncdn.com/i/teamlogos/soccer/500/1068.png","logo_large":"https://a.espncdn.com/i/teamlogos/soccer/500/1068.png","record":"1-1-1","abbreviation":"ATM"},"metadata":{"gender":"men","level":"professional","league":"Champions_League","importance":"regular_season"},"espn":{"espn_id":"401915392","game_clock":"90'+4'","period":"FT","broadcast":"Paramount+","probability_sources":{"betting":0.0558,"betting_book_count":5.0}},"win_probability_sources":{"betting":{"value":0.0558,"display_name":"Betting Odds","type":"market","color":"#374151","updated_at":"2026-10-20T21:03:09.927225+00:00","evidence_status":"not_applicable"},"betting_book_count":{"value":5.0,"display_name":"betting_book_count","type":"model","color":"#6b7280","evidence_status":"not_applicable"}},"ei":{"score":89,"raw_score":66,"status":"incredible","label":"Must-Watch","emoji":"🔥","metadata":{"raw_ei":1.0806,"lead_changes":2,"comeback_factor":0.4243,"snapshot_count":222}},"pulse":{"score":89,"raw_score":66,"status":"incredible","label":"Must-Watch","emoji":"🔥","metadata":{"raw_ei":1.0806,"lead_changes":2,"comeback_factor":0.4243,"snapshot_count":222}},"event_tags":["audience:national_interest","class:international","competitive_structure:head_to_head","ei:engaging","gender:men","importance:regular_season","league:champions_league","level:professional","sport:soccer","stakes:playoff_race","status:completed","tier:1","timing:national_tv"],"current_odds":{"captured_at":"2026-10-20T21:01:22.240418+00:00","home_probability":0.0558,"away_probability":null,"away_rendered_percent":null,"home_rendered_percent":6,"spread":0.3,"over_under":3.1,"projected_home_score":1.5,"projected_away_score":2.0,"bookmaker_count":10},"bookmaker_odds":[{"bookmaker":"betmgm","home_moneyline":2200,"away_moneyline":5000,"home_probability":0.0417,"away_probability":0.0188,"captured_at":"2026-10-20T20:50:24.870547+00:00","spread":null,"over_under":null,"projected_home_score":null,"projected_away_score":null},{"bookmaker":"betonlineag","home_moneyline":224,"away_moneyline":112,"home_probability":0.2983,"away_probability":0.4558,"captured_at":"2026-10-20T19:00:32.077376+00:00","spread":0.5,"over_under":3.5,"projected_home_score":1.5,"projected_away_score":2.0},{"bookmaker":"betrivers","home_moneyline":1300,"away_moneyline":2400,"home_probability":0.0671,"away_probability":0.0376,"captured_at":"2026-10-20T20:49:53.318564+00:00","spread":null,"over_under":2.5,"projected_home_score":null,"projected_away_score":null},{"bookmaker":"betus","home_moneyline":200,"away_moneyline":120,"home_probability":0.3171,"away_probability":0.4325,"captured_at":"2026-10-20T19:01:36.527319+00:00","spread":0.5,"over_under":3.5,"projected_home_score":1.5,"projected_away_score":2.0},{"bookmaker":"bovada","home_moneyline":600,"away_moneyline":2200,"home_probability":0.1346,"away_probability":0.041,"captured_at":"2026-10-20T21:01:22.240418+00:00","spread":-0.3,"over_under":2.5,"projected_home_score":null,"projected_away_score":null},{"bookmaker":"draftkings","home_moneyline":650,"away_moneyline":3000,"home_probability":0.1251,"away_probability":0.0303,"captured_at":"2026-10-20T20:49:22.538004+00:00","spread":null,"over_under":null,"projected_home_score":null,"projected_away_score":null},{"bookmaker":"fanatics","home_moneyline":4500,"away_moneyline":6500,"home_probability":0.0211,"away_probability":0.0147,"captured_at":"2026-10-20T20:51:08.868932+00:00","spread":null,"over_under":null,"projected_home_score":null,"projected_away_score":null},{"bookmaker":"fanduel","home_moneyline":1600,"away_moneyline":6500,"home_probability":0.0558,"away_probability":0.0144,"captured_at":"2026-10-20T20:51:59.256847+00:00","spread":null,"over_under":null,"projected_home_score":null,"projected_away_score":null},{"bookmaker":"lowvig","home_moneyline":224,"away_moneyline":112,"home_probability":0.2983,"away_probability":0.4558,"captured_at":"2026-10-20T19:00:32.071524+00:00","spread":0.5,"over_under":3.5,"projected_home_score":1.5,"projected_away_score":2.0},{"bookmaker":"williamhill_us","home_moneyline":340,"away_moneyline":1200,"home_probability":0.2132,"away_probability":0.0722,"captured_at":"2026-10-20T20:44:10.113221+00:00","spread":null,"over_under":null,"projected_home_score":null,"projected_away_score":null}],"opening_odds":{"home_probability":0.3169,"away_probability":0.4339,"spread":0.5,"over_under":3.5,"favorite":"away"},"prematch_odds":{"home_probability":0.295,"away_probability":0.46,"home_rendered_percent":30,"away_rendered_percent":46,"source":"polymarket"},"pregame_projection":{"projected_home_score":1.5,"projected_away_score":1.9,"kind":"last_before_scheduled_start","earliest_captured_at":"2026-10-20T18:37:57.209904+00:00","latest_captured_at":"2026-10-20T18:56:23.853083+00:00","boundary":"scheduled_start","boundary_at":"2026-10-20T19:00:00+00:00","source":"sportsbooks","basis":"consensus_spread_total","bookmaker_count":4,"unit":"goals","period":"regulation"},"final_score_period":"regulation","hero_probability_observed_at":null,"blend_fold_revision":{"15330334":677,"15326586":853},"hero_probability":0.5,"hero_probability_away":0.5,"hero_probability_source":"settled","hero_settled_result":"draw","state_read_not_before":"2026-10-21T14:01:52.443675+00:00","state_read_not_after":"2026-10-21T14:01:52.448083+00:00"}
    """##

    private static let leagueRow = ##"""
    {"id":15330334,"external_id":"56989e10c299aba1a0fce210bb214775","sport":"soccer_uefa_champs_league","home_team":"VfB Stuttgart","away_team":"Atlético Madrid","commence_time":"2026-10-20T19:00:00+00:00","completed_at":"2026-10-20T20:52:00.499184+00:00","status":"completed","home_score":1,"away_score":1,"home_win_probability":0.0558,"current_odds":{"home_probability":0.0558,"away_probability":0.9442},"opening_odds":{"home_probability":0.3169,"away_probability":0.4339},"home_team_data":{"team_id":18819,"slug":"vfb-stuttgart-ucl","primary_color":"#ffffff","secondary_color":"#DA0308","logo_small":"https://a.espncdn.com/i/teamlogos/soccer/500/134.png","logo_large":"https://a.espncdn.com/i/teamlogos/soccer/500/134.png","record":"2-1-0","abbreviation":"VFB"},"away_team_data":{"team_id":2293,"slug":"atltico-madrid-league","primary_color":"#ca3624","secondary_color":"#000000","logo_small":"https://a.espncdn.com/i/teamlogos/soccer/500/1068.png","logo_large":"https://a.espncdn.com/i/teamlogos/soccer/500/1068.png","record":"1-1-1","abbreviation":"ATM"},"espn":{"period":"FT","game_clock":"90'+4'","broadcast":"Paramount+"},"pregame_projection":{"projected_home_score":1.5,"projected_away_score":1.9,"kind":"last_before_scheduled_start","earliest_captured_at":"2026-10-20T18:37:57.209904+00:00","latest_captured_at":"2026-10-20T18:56:23.853083+00:00","boundary":"scheduled_start","boundary_at":"2026-10-20T19:00:00+00:00","source":"sportsbooks","basis":"consensus_spread_total","bookmaker_count":4,"unit":"goals","period":"regulation"},"final_score_period":"regulation"}
    """##

    private static let preProducerListRow = ##"""
    {"id":15330334,"external_id":"56989e10c299aba1a0fce210bb214775","sport":"soccer_uefa_champs_league","sport_name":"UEFA Champions League","home_team":"VfB Stuttgart","away_team":"Atlético Madrid","commence_time":"2026-10-20T19:00:00+00:00","status":"completed","home_score":1,"away_score":1,"score_source":"espn","espn":{"espn_id":"401915392","game_clock":"90'+4'","period":"FT","broadcast":"Paramount+","probability_sources":{"betting":0.0558,"betting_book_count":5.0}}}
    """##
}
