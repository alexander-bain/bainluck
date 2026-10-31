import CryptoKit
import SwiftUI
import XCTest
@testable import Bain_Luck

/// #10868 — the cricket Test-match adapter, part two (the three-original
/// history), decoded exactly as the app decodes (`APIClient`: `JSONDecoder` with
/// `.convertFromSnakeCase`, no date strategy).
///
/// PREPARED, NOT RUN: written under a source-only hold (no build, no XCTest).
///
/// NO CRICKET `/history` BODY IS RETAINED anywhere under
/// `artifacts/discovery-containers-release-plan/event-page-design-20261011/`
/// (the cricket capture directories hold Kalshi venue bodies, not Bain Luck
/// `/api/events/{id}/history`). The line rules are the hockey candidate's
/// reviewed rules, so they are proved here on the NEAREST REAL `/history` BODY,
/// the one those rules were accepted on, labelled as such:
///
/// - `devilsKnightsDetail` — `shipping-adoption-20261027/cli-candidate-20261030/
///   retained-payloads/nhl-15338496-detail-20261030T201355Z.json`, BYTE FOR BYTE
///   (sha256 50fbf4678a308e40481340e9b998a2a0870795dd8b04dfdfb05e31caf3dcc1da).
///   New Jersey Devils at Vegas Golden Knights, scheduled 22:00Z.
/// - `devilsKnightsHistory` — the REDUCED VERBATIM SUBSET of the same directory's
///   `nhl-15338496-history-20261030T201355Z.json` (430,695 bytes, sha256
///   0fe7e8cd334d2b32b5d808bd2dbdec974bef052a53775991b1457bd37fafe812) that
///   `HockeyJourneyHistoryAdapter10868Tests` embeds, copied unchanged:
///     `history`            9 of 62: 5–8, 57–61
///     `bookmaker_history`  emptied to {}
///     `win_prob_history`   polymarket 0, 984 of 985; kalshi 0, 551 of 552
///     `aggregate_line`     26 of 1103: 54–62, 513–521, 1095–1102
///
/// CONSTRUCTED, named where used: the detail's `sport` set to
/// `cricket_test_match` (one key) so the screen's rules read a Test match; a
/// sportsbooks-only history (`win_prob_history` and `aggregate_line` removed, two
/// keys); the reader's calendar (Pacific, en_US) and `now`.
@MainActor
final class CricketHistoryAdapter10868Tests: XCTestCase {
    private typealias H = CricketHistoryAdapter10868
    private typealias Rules = HockeyJourneyHistoryAdapter10868

    private func readerHost(_ now: String) -> Rules.Host {
        Rules.Host(now: now.asDate!, calendar: CricketEventPageAdapter10868Tests.pacific,
                   locale: Locale(identifier: "en_US"))
    }

    private func decoder() -> JSONDecoder {
        let decoder = JSONDecoder()
        decoder.keyDecodingStrategy = .convertFromSnakeCase
        return decoder
    }

    /// CONSTRUCTED: the served detail with `sport` set to `cricket_test_match`.
    private func testMatch() throws -> EventDetail {
        try CricketEventPageAdapter10868Tests.detail(Self.devilsKnightsDetail, setting: "sport", to: "cricket_test_match")
    }

    private func response(_ json: String, removing: [String] = []) throws -> EventHistoryResponse {
        var object = try XCTUnwrap(JSONSerialization.jsonObject(with: Data(json.utf8)) as? [String: Any])
        for key in removing { object.removeValue(forKey: key) }
        return try decoder().decode(EventHistoryResponse.self, from: JSONSerialization.data(withJSONObject: object))
    }

    private func x(_ stamp: String) -> Double { stamp.asDate!.timeIntervalSince1970 }

    func testTheEmbeddedDetailIsTheRetainedBytesAndTheSubsetDecodes() throws {
        let hash = SHA256.hash(data: Data(Self.devilsKnightsDetail.utf8)).map { String(format: "%02x", $0) }.joined()
        XCTAssertEqual(hash, "50fbf4678a308e40481340e9b998a2a0870795dd8b04dfdfb05e31caf3dcc1da")
        let history = try response(Self.devilsKnightsHistory)
        XCTAssertEqual(history.eventId, 15338496)
        XCTAssertEqual(history.aggregateLine?.count, 26)
        XCTAssertEqual(history.blendEdgePinned, true)
        XCTAssertTrue(try XCTUnwrap(history.aggregateLine).allSatisfy { $0.awayProbability == nil },
                      "the served blend is home-only: its away side is only the remainder")
        XCTAssertEqual(Rules.line(history), .blend)
    }

    func testBeforeTheStartTheHomeLineDrawsAndTheAwayAndDrawKeepTheirOwnWords() throws {
        let event = try testMatch()
        let history = try response(Self.devilsKnightsHistory)
        let host = readerHost("2026-10-30T20:13:55Z")
        XCTAssertEqual(CricketEventPageAdapter10868.phase(event, now: host.now), .before)
        let input = H.history(history, event: event, phase: .before, host: host)

        XCTAssertEqual(input.title, "Win probability")
        XCTAssertEqual(input.series.map(\.name), ["Vegas Golden Knights", "New Jersey Devils", "Draw / tie"])
        XCTAssertEqual(input.series.map(\.shape), [.circle, .diamond, .square], "part one's keys, by original")
        XCTAssertEqual(input.series.map(\.id), ["aggregate:15338496:home", "aggregate:15338496:away",
                                                "aggregate:15338496:draw"])

        // The home line: the reviewed rule's pregame day, ending at the last pregame
        // reading (20:11), one run, the pin removed.
        let home = input.series[0]
        let points = home.segments.flatMap(\.points)
        XCTAssertEqual(home.segments.count, 1)
        XCTAssertEqual(points.count, 25)
        XCTAssertEqual(points.first?.x, x("2026-10-29T21:58:00+00:00"),
                       "the last pregame reading less one day — not the listed start less one day (22:00)")
        XCTAssertTrue(points.allSatisfy { $0.x >= x("2026-10-30T20:11:00+00:00") - Rules.beforeWindow },
                      "never older than one day before the last pregame reading")
        let pin = try XCTUnwrap(history.aggregateLine?.last)
        XCTAssertFalse(points.contains { $0.x == x(pin.timestamp) }, "the pinned edge is the hero's, not a recorded row")
        XCTAssertEqual(points.last?.x, x("2026-10-30T20:11:00+00:00"))
        XCTAssertEqual(points.last?.isPregame, true, "the last pregame reading, drawn hollow")
        XCTAssertEqual(points.filter(\.isPregame).count, 1)
        XCTAssertEqual(points.last?.id, Rules.pointID(home.id, "2026-10-30T20:11:00+00:00"))
        XCTAssertEqual(points.last?.probability, 0.505)

        // The away side: every blend row's away value is only the remainder, so on
        // a screen that lists a draw it is a gap — never a mirrored line.
        let away = input.series[1]
        XCTAssertEqual(away.segments, [])
        XCTAssertEqual(away.absentWords, "Win chance unavailable")
        let draw = input.series[2]
        XCTAssertEqual(draw.segments, [])
        XCTAssertEqual(draw.absentWords, "Draw chance unavailable")

        XCTAssertEqual(input.domain, CricketHistoryDomain10868(lower: x("2026-10-29T21:58:00+00:00"),
                                                               upper: x("2026-10-30T20:11:00+00:00")))
        XCTAssertEqual(input.yTicks, [CricketHistoryTick10868(value: 0, lines: ["0%"]),
                                      CricketHistoryTick10868(value: 0.5, lines: ["50%"]),
                                      CricketHistoryTick10868(value: 1, lines: ["100%"])])
        let domain = "2026-10-29T21:58:00+00:00".asDate!..."2026-10-30T20:11:00+00:00".asDate!
        XCTAssertEqual(input.xTicks.map(\.value), Rules.xTicks(domain, host: host).map(\.value))
        XCTAssertEqual(input.pregameKey, "Pregame")
        let context = try XCTUnwrap(input.context)
        XCTAssertTrue(context.hasPrefix("Source: Bain Luck."))
        XCTAssertTrue(context.contains(H.Words.independent))
        XCTAssertTrue(context.contains("Gaps remain blank."))
        XCTAssertFalse(context.contains(H.Words.unconfirmedStart), "the listed start is a confirmed kick-off")
        XCTAssertTrue(context.contains("Times in "))
        XCTAssertEqual(input.summary, "Recorded win probability for Vegas Golden Knights. "
                       + "Chance unavailable for New Jersey Devils and Draw / tie.")
        XCTAssertEqual(input.expand, CricketHistoryControl10868(label: "Full chart", isAvailable: true))
        XCTAssertNil(input.inspection)
        XCTAssertNil(input.window)
        XCTAssertNil(input.previous)
        XCTAssertNil(input.next)
    }

    /// CONSTRUCTED: the sportsbooks-only history (`win_prob_history` and
    /// `aggregate_line` removed). Each consensus row serves both sides, and each
    /// pair sums to one — a complement pair — so the away side is still a gap.
    func testOnTheSportsbookLineARowSummingToOneIsAGapForTheAwaySide() throws {
        let event = try testMatch()
        let history = try response(Self.devilsKnightsHistory, removing: ["win_prob_history", "aggregate_line"])
        XCTAssertEqual(Rules.line(history), .consensus)
        XCTAssertTrue(history.history.allSatisfy { isComplementPair([$0.awayProbability, $0.homeProbability]) })
        let input = H.history(history, event: event, phase: .before, host: readerHost("2026-10-30T20:13:55Z"))
        let home = input.series[0]
        XCTAssertEqual(home.id, "consensus:15338496:home")
        XCTAssertEqual(home.segments.flatMap(\.points).count, 9, "21:36 Oct 29 through 20:11 Oct 30")
        XCTAssertEqual(home.segments.flatMap(\.points).first?.x, x("2026-10-29T21:36:00+00:00"),
                       "the sportsbook line's own last pregame reading (20:11) less one day")
        XCTAssertEqual(input.series[1].segments, [])
        XCTAssertTrue(try XCTUnwrap(input.context).hasPrefix("Source: Sportsbook Consensus (market)."))
    }

    /// The rows the reviewed rule reads, with this screen's one change.
    func testTheRowsKeepEveryHomeValueAndNoRemainderAway() throws {
        let event = try testMatch()
        let history = try response(Self.devilsKnightsHistory)
        let served = Rules.servedRows(history, line: .blend, sport: event.sport)
        let rows = H.rows(history, line: .blend, event: event)
        XCTAssertEqual(rows.map(\.home), served.map(\.home))
        XCTAssertEqual(rows.map(\.index), served.map(\.index))
        XCTAssertTrue(served.allSatisfy(\.awayIsComplement), "the reviewed rule fills the blend's away as the remainder")
        XCTAssertTrue(rows.allSatisfy { $0.away == nil && !$0.awayIsComplement })
    }

    /// CONSTRUCTED: the retained subset with only `event_id` changed to a
    /// different event's id. Nothing is placed: the history reads exactly as with
    /// no response.
    func testAnotherEventsHistoryPlacesNothingAndReadsAsUnavailable() throws {
        let event = try testMatch()
        var object = try XCTUnwrap(JSONSerialization.jsonObject(with: Data(Self.devilsKnightsHistory.utf8)) as? [String: Any])
        object["event_id"] = 15338497
        let foreign = try decoder().decode(EventHistoryResponse.self, from: JSONSerialization.data(withJSONObject: object))
        let input = H.history(foreign, event: event, phase: .before, host: readerHost("2026-10-30T20:13:55Z"))
        XCTAssertEqual(input, H.unavailable(event))
        XCTAssertTrue(input.series.allSatisfy { $0.segments.isEmpty })
        XCTAssertNil(input.expand)
    }

    /// No history response: only the history says so; nothing is placed or offered.
    func testWithoutAHistoryResponseEverySeriesSaysHistoryUnavailable() throws {
        let event = try CricketEventPageAdapter10868Tests.detail(CricketEventPageAdapter10868Tests.pakistanSriLanka)
        let input = H.unavailable(event)
        XCTAssertEqual(input.series.map(\.name), ["Pakistan", "Sri Lanka", "Draw / tie"])
        XCTAssertTrue(input.series.allSatisfy { $0.segments.isEmpty && $0.absentWords == "History unavailable" })
        XCTAssertEqual(input.summary, "History unavailable")
        XCTAssertNil(input.context, "no source is named for a history that did not arrive")
        XCTAssertNil(input.expand)
        XCTAssertNil(input.pregameKey)
        XCTAssertEqual(input.yTicks, [])
        XCTAssertEqual(input.xTicks, [])
    }

    // MARK: Retained payloads

    /// `shipping-adoption-20261027/cli-candidate-20261030/retained-payloads/nhl-15338496-detail-20261030T201355Z.json` · sha256 50fbf4678a308e40481340e9b998a2a0870795dd8b04dfdfb05e31caf3dcc1da
    private static let devilsKnightsDetail = ##"""
{"id":15338496,"external_id":"5c712e15e1cd4b9283b4bf410fb334f4","sport":"icehockey_nhl","sport_name":"NHL","home_team":"Vegas Golden Knights","away_team":"New Jersey Devils","commence_time":"2026-10-30T22:00:00+00:00","start_is_tbd":false,"start_is_from_schedule":true,"completed_at":null,"status":"scheduled","started_without_result":false,"home_score":null,"away_score":null,"home_team_data":{"team_id":63,"slug":"vegas-golden-knights","primary_color":"#344043","secondary_color":"#b4975a","logo_small":"https://a.espncdn.com/i/teamlogos/nhl/500/scoreboard/vgk.png","logo_large":"https://a.espncdn.com/i/teamlogos/nhl/500/scoreboard/vgk.png","record":"9-4-1","abbreviation":"VGK","standings":{"pct":".692","wins":9,"losses":4,"points":19,"streak":"W1","div_rank":2,"division":"Pacific Division","goals_for":51,"conference":"Western Conference","home_record":"6-2-0","road_record":"3-2-1","goals_against":39,"draws":1}},"away_team_data":{"team_id":53,"slug":"new-jersey-devils","primary_color":"#e30b2b","secondary_color":"#000000","logo_small":"https://a.espncdn.com/i/teamlogos/nhl/500/scoreboard/nj.png","logo_large":"https://a.espncdn.com/i/teamlogos/nhl/500/scoreboard/nj.png","record":"8-5-0","abbreviation":"NJ","standings":{"pct":".615","wins":8,"losses":5,"points":16,"streak":"L1","div_rank":2,"division":"Metropolitan Division","goals_for":43,"conference":"Eastern Conference","home_record":"6-2-0","road_record":"2-3-0","goals_against":38,"draws":0}},"metadata":{"gender":"men","level":"professional","league":"NHL","importance":"regular_season"},"espn":{"espn_id":"401892611","broadcast":"NHL Net, MSGSN, Scripps Sports","probability_sources":{"kalshi":0.505,"betting":0.5052,"polymarket":0.505,"betting_book_count":19.0}},"win_probability_sources":{"kalshi":{"value":0.505,"display_name":"Kalshi","type":"market","color":"#22c55e","updated_at":"2026-10-30T20:12:18.516253+00:00","evidence_status":"verified","verified_scope":"full_event_winner","contract_version":"live_blend.admissible_as_blend_speaker@5031"},"betting":{"value":0.5052,"display_name":"Betting Odds","type":"market","color":"#374151","updated_at":"2026-10-30T20:11:38.149122+00:00","evidence_status":"not_applicable"},"polymarket":{"value":0.505,"display_name":"Polymarket","type":"market","color":"#3b82f6","updated_at":"2026-10-30T20:13:34.913575+00:00","evidence_status":"verified","verified_scope":"full_event_winner","contract_version":"live_blend.admissible_as_blend_speaker@5031","price_evidence":"unproven"},"betting_book_count":{"value":19.0,"display_name":"betting_book_count","type":"model","color":"#6b7280","evidence_status":"not_applicable"}},"event_tags":["audience:national_interest","class:pro_major","competitive_structure:head_to_head","gender:men","importance:regular_season","league:nhl","level:professional","sport:hockey","stakes:playoff_race","status:scheduled","tier:1"],"standings_context":{"home":"9-4-1, #2 Pacific, 19 pts","away":"8-5-0, #2 Metropolitan, 16 pts"},"current_odds":{"captured_at":"2026-10-30T20:11:38.123766+00:00","home_probability":0.505,"away_probability":0.495,"away_rendered_percent":49,"home_rendered_percent":51,"spread":-0.8,"over_under":5.9,"projected_home_score":3.5,"projected_away_score":2.5,"bookmaker_count":19},"bookmaker_odds":[{"bookmaker":"ballybet","home_moneyline":-115,"away_moneyline":-104,"home_probability":0.512,"away_probability":0.488,"captured_at":"2026-10-30T20:00:18.560393+00:00","spread":-1.5,"over_under":5.5,"projected_home_score":3.5,"projected_away_score":2.0},{"bookmaker":"betanysports","home_moneyline":-115,"away_moneyline":-105,"home_probability":0.5108,"away_probability":0.4892,"captured_at":"2026-10-30T03:36:59.763124+00:00","spread":-1.5,"over_under":6.0,"projected_home_score":3.8,"projected_away_score":2.2},{"bookmaker":"betmgm","home_moneyline":-110,"away_moneyline":-110,"home_probability":0.5,"away_probability":0.5,"captured_at":"2026-10-30T20:11:38.046354+00:00","spread":1.5,"over_under":6.0,"projected_home_score":2.2,"projected_away_score":3.8},{"bookmaker":"betonlineag","home_moneyline":-111,"away_moneyline":-103,"home_probability":0.509,"away_probability":0.491,"captured_at":"2026-10-30T20:11:37.968853+00:00","spread":-1.5,"over_under":6.0,"projected_home_score":3.8,"projected_away_score":2.2},{"bookmaker":"betparx","home_moneyline":-115,"away_moneyline":-104,"home_probability":0.512,"away_probability":0.488,"captured_at":"2026-10-30T20:00:18.492035+00:00","spread":-1.5,"over_under":5.5,"projected_home_score":3.5,"projected_away_score":2.0},{"bookmaker":"betrivers","home_moneyline":-115,"away_moneyline":-104,"home_probability":0.512,"away_probability":0.488,"captured_at":"2026-10-30T20:11:38.094426+00:00","spread":-1.5,"over_under":5.5,"projected_home_score":3.5,"projected_away_score":2.0},{"bookmaker":"betus","home_moneyline":-110,"away_moneyline":-110,"home_probability":0.5,"away_probability":0.5,"captured_at":"2026-10-30T20:11:38.062081+00:00","spread":-1.5,"over_under":6.0,"projected_home_score":3.8,"projected_away_score":2.2},{"bookmaker":"bovada","home_moneyline":-117,"away_moneyline":-103,"home_probability":0.5152,"away_probability":0.4848,"captured_at":"2026-10-30T20:11:38.123766+00:00","spread":-1.5,"over_under":6.0,"projected_home_score":3.8,"projected_away_score":2.2},{"bookmaker":"courtside","home_moneyline":-113,"away_moneyline":-103,"home_probability":0.5111,"away_probability":0.4889,"captured_at":"2026-10-30T20:00:18.410992+00:00","spread":1.5,"over_under":6.5,"projected_home_score":null,"projected_away_score":null},{"bookmaker":"draftkings","home_moneyline":-115,"away_moneyline":-105,"home_probability":0.5108,"away_probability":0.4892,"captured_at":"2026-10-30T20:11:37.932302+00:00","spread":-1.5,"over_under":6.5,"projected_home_score":4.0,"projected_away_score":2.5},{"bookmaker":"espnbet","home_moneyline":-110,"away_moneyline":-110,"home_probability":0.5,"away_probability":0.5,"captured_at":"2026-10-30T20:00:18.476701+00:00","spread":1.5,"over_under":5.5,"projected_home_score":2.0,"projected_away_score":3.5},{"bookmaker":"fanatics","home_moneyline":-110,"away_moneyline":-110,"home_probability":0.5,"away_probability":0.5,"captured_at":"2026-10-30T20:11:37.999661+00:00","spread":-1.5,"over_under":6.5,"projected_home_score":4.0,"projected_away_score":2.5},{"bookmaker":"fanduel","home_moneyline":-110,"away_moneyline":-110,"home_probability":0.5,"away_probability":0.5,"captured_at":"2026-10-30T20:11:38.069388+00:00","spread":-1.5,"over_under":6.5,"projected_home_score":4.0,"projected_away_score":2.5},{"bookmaker":"fliff","home_moneyline":-115,"away_moneyline":-110,"home_probability":0.5052,"away_probability":0.4948,"captured_at":"2026-10-30T20:00:18.608502+00:00","spread":-1.5,"over_under":5.5,"projected_home_score":3.5,"projected_away_score":2.0},{"bookmaker":"hardrockbet","home_moneyline":-110,"away_moneyline":-110,"home_probability":0.5,"away_probability":0.5,"captured_at":"2026-10-30T20:00:18.569776+00:00","spread":1.5,"over_under":5.5,"projected_home_score":2.0,"projected_away_score":3.5},{"bookmaker":"lowvig","home_moneyline":-111,"away_moneyline":-103,"home_probability":0.509,"away_probability":0.491,"captured_at":"2026-10-30T20:11:37.938462+00:00","spread":-1.5,"over_under":6.0,"projected_home_score":3.8,"projected_away_score":2.2},{"bookmaker":"mybookieag","home_moneyline":-112,"away_moneyline":-109,"home_probability":0.5032,"away_probability":0.4968,"captured_at":"2026-10-30T20:11:38.114699+00:00","spread":-1.5,"over_under":6.0,"projected_home_score":3.8,"projected_away_score":2.2},{"bookmaker":"rebet","home_moneyline":-112,"away_moneyline":-109,"home_probability":0.5032,"away_probability":0.4968,"captured_at":"2026-10-30T20:00:18.375868+00:00","spread":-1.5,"over_under":6.0,"projected_home_score":3.8,"projected_away_score":2.2},{"bookmaker":"williamhill_us","home_moneyline":-111,"away_moneyline":-110,"home_probability":0.5011,"away_probability":0.4989,"captured_at":"2026-10-30T20:11:38.036259+00:00","spread":null,"over_under":6.0,"projected_home_score":null,"projected_away_score":null}],"hero_probability_observed_at":"2026-10-30T20:13:34.913575+00:00","blend_fold_revision":{"15338496":2376},"hero_probability":0.505,"hero_probability_away":0.495,"hero_probability_source":"blend","hero_sportsbook_count":19,"state_read_not_before":"2026-10-30T20:13:55.425936+00:00","state_read_not_after":"2026-10-30T20:13:55.430779+00:00","state_read_fresh":true}
"""##

    /// Reduced verbatim subset of `nhl-15338496-history-20261030T201355Z.json` (see the type's note).
    private static let devilsKnightsHistory = ##"""
{"event_id":15338496,
"home_team":"Vegas Golden Knights",
"away_team":"New Jersey Devils",
"commence_time":"2026-10-30T22:00:00+00:00",
"completed_at":null,
"status":"scheduled",
"time_domain":{"start":"2026-10-29T20:13:00+00:00","end":"2026-10-30T20:13:59.771239+00:00","is_live":false,"min_window_seconds":1800},
"history":[
{"timestamp":"2026-10-29T21:36:00+00:00","home_probability":0.508,"away_probability":0.492,"over_under":null,"projected_home_score":null,"projected_away_score":null,"bookmaker_count":9,"probability_range":{"min":0.5,"max":0.5164}},
{"timestamp":"2026-10-29T21:37:00+00:00","home_probability":0.5083,"away_probability":0.4917,"over_under":6.3,"projected_home_score":3.9,"projected_away_score":2.4,"bookmaker_count":11,"probability_range":{"min":0.5,"max":0.5164}},
{"timestamp":"2026-10-29T22:04:00+00:00","home_probability":0.5118,"away_probability":0.4882,"over_under":6.0,"projected_home_score":3.8,"projected_away_score":2.2,"bookmaker_count":1,"probability_range":{"min":0.5118,"max":0.5118}},
{"timestamp":"2026-10-29T22:10:00+00:00","home_probability":0.518,"away_probability":0.482,"over_under":6.2,"projected_home_score":3.9,"projected_away_score":2.3,"bookmaker_count":3,"probability_range":{"min":0.5162,"max":0.5217}},
{"timestamp":"2026-10-30T19:38:00+00:00","home_probability":0.5076,"away_probability":0.4924,"over_under":null,"projected_home_score":null,"projected_away_score":null,"bookmaker_count":2,"probability_range":{"min":0.5,"max":0.5152}},
{"timestamp":"2026-10-30T20:00:00+00:00","home_probability":0.5063,"away_probability":0.4937,"over_under":5.9,"projected_home_score":3.4,"projected_away_score":2.5,"bookmaker_count":18,"probability_range":{"min":0.5,"max":0.5152}},
{"timestamp":"2026-10-30T20:06:00+00:00","home_probability":0.5032,"away_probability":0.4968,"over_under":6.0,"projected_home_score":3.8,"projected_away_score":2.2,"bookmaker_count":1,"probability_range":{"min":0.5032,"max":0.5032}},
{"timestamp":"2026-10-30T20:07:00+00:00","home_probability":0.5065,"away_probability":0.4935,"over_under":null,"projected_home_score":null,"projected_away_score":null,"bookmaker_count":11,"probability_range":{"min":0.5,"max":0.5152}},
{"timestamp":"2026-10-30T20:11:00+00:00","home_probability":0.5055,"away_probability":0.4945,"over_under":6.1,"projected_home_score":3.7,"projected_away_score":2.4,"bookmaker_count":11,"probability_range":{"min":0.5,"max":0.5152}}
],
"bookmaker_history":{},
"score_history":[],
"espn_history":[],
"win_prob_history":{
"polymarket":[
{"timestamp":"2026-10-29T20:15:56.356074+00:00","home_probability":0.515,"away_probability":0.485,"draw_probability":null,"game_state":null},
{"timestamp":"2026-10-30T19:02:26.684116+00:00","home_probability":0.505,"away_probability":0.495,"draw_probability":null,"game_state":null}
],
"kalshi":[
{"timestamp":"2026-10-29T20:21:37.596394+00:00","home_probability":0.515,"away_probability":0.485,"draw_probability":null,"game_state":null},
{"timestamp":"2026-10-30T20:12:18.516253+00:00","home_probability":0.505,"away_probability":0.495,"draw_probability":null,"game_state":null}
]
},
"evidence_contract":{"v":"7878.v1","resolution_s":300},
"win_prob_sources":{"polymarket":{"display_name":"Polymarket","type":"market","color":"#3b82f6","dash_pattern":"8 4","description":"Win probability from Polymarket, the world's largest prediction market by volume. Polymarket prices reflect the consensus of thousands of traders betting real money on game outcomes.","methodology":"The outcome price from Polymarket's CLOB (Central Limit Order Book). Prices range from $0.00 to $1.00 and directly represent implied probability. For binary markets, the 'Yes' price equals the market's probability estimate.","attribution_url":"https://polymarket.com","attribution_name":"Polymarket","snapshot_count":985},"kalshi":{"display_name":"Kalshi","type":"market","color":"#22c55e","dash_pattern":"8 4","description":"Win probability from Kalshi, a CFTC-regulated prediction market where real money is traded on event outcomes. Kalshi odds represent the consensus of market participants betting on game outcomes.","methodology":"The midpoint of the bid/ask spread for the 'Yes' contract on the game outcome market. Kalshi contracts settle at $1 if the event occurs and $0 otherwise, so the price directly represents the market's implied probability.","attribution_url":"https://kalshi.com","attribution_name":"Kalshi","snapshot_count":552}},
"scoring_plays":[],
"moments":[],
"period_markers":[],
"aggregate_line":[
{"timestamp":"2026-10-29T21:58:00+00:00","home_probability":0.515},
{"timestamp":"2026-10-29T21:59:00+00:00","home_probability":0.515},
{"timestamp":"2026-10-29T22:00:00+00:00","home_probability":0.515},
{"timestamp":"2026-10-29T22:03:00+00:00","home_probability":0.515},
{"timestamp":"2026-10-29T22:04:00+00:00","home_probability":0.515},
{"timestamp":"2026-10-29T22:05:00+00:00","home_probability":0.515},
{"timestamp":"2026-10-29T22:06:00+00:00","home_probability":0.515},
{"timestamp":"2026-10-29T22:07:00+00:00","home_probability":0.515},
{"timestamp":"2026-10-29T22:08:00+00:00","home_probability":0.515},
{"timestamp":"2026-10-30T08:00:00+00:00","home_probability":0.525},
{"timestamp":"2026-10-30T08:01:00+00:00","home_probability":0.525},
{"timestamp":"2026-10-30T08:02:00+00:00","home_probability":0.525},
{"timestamp":"2026-10-30T08:03:00+00:00","home_probability":0.525},
{"timestamp":"2026-10-30T08:04:00+00:00","home_probability":0.525},
{"timestamp":"2026-10-30T08:06:00+00:00","home_probability":0.525},
{"timestamp":"2026-10-30T08:07:00+00:00","home_probability":0.525},
{"timestamp":"2026-10-30T08:08:00+00:00","home_probability":0.525},
{"timestamp":"2026-10-30T08:09:00+00:00","home_probability":0.525},
{"timestamp":"2026-10-30T20:00:00+00:00","home_probability":0.505},
{"timestamp":"2026-10-30T20:03:00+00:00","home_probability":0.505},
{"timestamp":"2026-10-30T20:04:00+00:00","home_probability":0.505},
{"timestamp":"2026-10-30T20:06:00+00:00","home_probability":0.505},
{"timestamp":"2026-10-30T20:07:00+00:00","home_probability":0.505},
{"timestamp":"2026-10-30T20:09:00+00:00","home_probability":0.505},
{"timestamp":"2026-10-30T20:11:00+00:00","home_probability":0.505},
{"timestamp":"2026-10-30T20:12:00+00:00","home_probability":0.505}
],
"blend_edge_pinned":true,
"blend_edge_observed_at":"2026-10-30T20:13:34.913575+00:00",
"blend_edge_fold_revision":{"15338496":2376},
"history_fold_revision":null,
"pre_window_omitted":false,
"commence_time_is_kickoff":true,
"pm_spread_data":{"implied_spreads":{"kalshi":{"spread":-0.1,"home_margin":0.1,"confidence":0.85,"contracts":[{"threshold":-2.5,"probability":0.825},{"threshold":-1.5,"probability":0.725},{"threshold":1.5,"probability":0.295},{"threshold":2.5,"probability":0.19}]},"sportsbook":{"spread":-1.3,"home_margin":1.3,"confidence":1.0,"contracts":[]}},"implied_totals":{"kalshi":{"total":6.0,"confidence":0.9,"contracts":[{"threshold":1.5,"probability":0.985},{"threshold":2.5,"probability":0.97},{"threshold":3.5,"probability":0.865},{"threshold":4.5,"probability":0.785},{"threshold":5.5,"probability":0.55},{"threshold":6.5,"probability":0.445},{"threshold":7.5,"probability":0.25},{"threshold":8.5,"probability":0.175},{"threshold":9.5,"probability":0.075}]},"polymarket":{"total":6.1,"confidence":0.5,"contracts":[{"threshold":2.5,"probability":0.9715},{"threshold":3.5,"probability":0.865},{"threshold":8.5,"probability":0.175},{"threshold":9.5,"probability":0.075}]},"sportsbook":{"total":6.1,"confidence":1.0,"contracts":[]}},"projected_final":{"home_score":3.7,"away_score":2.4,"spread_source":"sportsbook","total_source":"sportsbook"}},
"points":62,
"bookmaker_count":19,
"snapshot_count":476,
"espn_snapshot_count":0,
"on_demand_backfill":null}
"""##
}
