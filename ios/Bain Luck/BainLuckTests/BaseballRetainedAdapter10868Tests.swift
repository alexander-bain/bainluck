import CryptoKit
import Foundation
import XCTest
@testable import Bain_Luck

/// #10868 — the RETAINED REAL bodies every baseball adapter test reads, decoded
/// exactly as the app decodes them (`APIClient`: `JSONDecoder` with
/// `.convertFromSnakeCase`, no date strategy). Shared here so the seven
/// baseball adapter test files read one copy.
///
/// PREPARED, NOT RUN: written under a source-only hold (no build, no XCTest).
///
/// The specimen is Chicago White Sox at Houston Astros, Wednesday, September
/// 30, 2026 (event 15321836, MLB), final 7–3 to the White Sox. Sources, under
/// `artifacts/discovery-containers-release-plan/event-page-design-20261011/`:
///
/// - `finalDetail` — `atlas-v6/raw/mlb-15321836-detail.json` (15,041 bytes,
///   sha256 1221677b9feee61a466720cbf7a2cb9f25f9b45a4189091b07392d21f9189cf2),
///   completed 3–7, captured 2026-10-11T04:56:42.524844Z. BYTE FOR BYTE.
///
/// - `finalHistory` — `atlas-v6/raw/mlb-15321836-history.json` (985,211 bytes,
///   sha256 0db9e14731d2e9f5b34248b8c6a3c1076f503d9bf8085fd57971683863a68e07),
///   `/history`, completed, captured 2026-10-11T04:57:23.592725Z. REDUCED
///   VERBATIM SUBSET. Every top-level key, in source order, is the source's
///   bytes, one per line, except (0-based element indexes kept, in source order):
///     `history` 6 of 344: [0, 1, 149, 150, 342, 343]
///     `bookmaker_history` replaced by {}
///     `espn_history` 4 of 94: [0, 1, 92, 93]
///     `win_prob_history` kalshi 2 of 425: [0, 424]; polymarket 2 of 320: [0, 319];
///       espn 2 of 78: [0, 77]; stat_model 2 of 43: [0, 42]; mlb 2 of 63: [0, 62]
///     `aggregate_line` 31 of 728: [0, 1, 2, 520–536, 600, 601, 602, 720–727]
///   Rows left out are absent, so an in-game interval across them is wider
///   than served: runs below are runs OF THE SUBSET. Kept on purpose: the last
///   pregame blend row (527, 20:58Z, 0.589), the served settlement row (727,
///   00:18Z, 0.0) and the out-of-order row before it (726, 00:46Z).
///
/// Loaded from the existing fixtures, unchanged (no new fixture file):
///
/// - `Fixtures/event-15321836-game-markets-11284-mlb-final.20260930.json` —
///   byte for byte `atlas-v6/raw/mlb-15321836-game-markets.json` (655,328
///   bytes, sha256 42dfb4898c993c2972eccee4c71634715082b2e6678f6da2c57917da2debdb89),
///   captured 2026-10-11T04:56:48.051497Z.
/// - `Fixtures/event-15321836-related-11284-mlb-final.20260930.json` — byte for
///   byte `atlas-v6/raw/mlb-15321836-related.json` (sha256
///   b844152f2a6a91dccd6bf9e76c555836bcddf3b1148dba81e41c6300b7a5f23c),
///   captured 2026-10-11T04:59:17.450119Z.
/// - `Fixtures/history-15321836-late-start.20260930T2213Z.json` (sha256
///   b0561095a63b9bd78cdb0d18629ec9feaf8418006e581044c718a3903423528d) — the
///   same game's served `/history` fetched ~23:17Z on the day, which its
///   owner (`SinceStartOpensAtObservedPlay6158Tests`) records as cut back to
///   22:13:00Z, status set to `live` and thinned 1-in-12 before 20:00Z. It
///   keeps the served `blend_edge_pinned: true`.
///
/// - `liveExtraRow` — `atlas-v6/raw/mlb-live-20260930.json` (20,129 bytes,
///   sha256 de228910db55e621930e0b7dda83957b3fe6c5c8189bdffe4ddd1c7e83324acf),
///   element 20 (0-based) ONLY, VERBATIM (393 bytes, sha256
///   66861a2fdd4ff5693a42c320c9988d255341691acc6547a5208ccb934dfb336e): the
///   same game's Kalshi "Chicago White Sox vs Houston: Extra Innings" Yes row,
///   market 62972332, outcome 237550051, `pregame_mark` 0.11,
///   `over_probability` 0.16 at 2026-09-30T23:04:20.681782Z,
///   `opening_over_probability` 0.08. The file records no capture instant.
///   Its key set is the backend's player-prop row shape; Design's receipt
///   (`BASEBALL-FIFTH-STORY-COVERAGE-CORRECTION.json`) maps it to the
///   production `GameMarketOther`, which decodes its identity and observation
///   clock but not `pregame_mark` or `over_probability`.
///
/// Subsets generated and checked by `/tmp/cli-10868-baseball/make_subsets.py`
/// (kept outside the repo): every kept element is a verbatim substring of its
/// source, and the parsed subset keeps every source key in order.
///
/// CONSTRUCTED here, and named where used: the reader's calendar (Pacific,
/// en_US); each `now`; each host clock; and the two earlier-phase variants of
/// the final detail — no live or pregame MLB detail body is retained for this
/// game. `liveEvent` changes exactly `liveEdits`' keys; `beforeEvent` changes
/// exactly `beforeEdits`' keys, its `current_odds` being the sportsbook
/// consensus row this game served at 20:58:00Z (`history` row 149: 0.589 /
/// 0.411, 3 books).
@MainActor
enum BaseballRetained10868 {
    static let eventID = 15321836
    static let pacific: Calendar = {
        var calendar = Calendar(identifier: .gregorian)
        calendar.timeZone = TimeZone(identifier: "America/Los_Angeles")!
        return calendar
    }()
    static let locale = Locale(identifier: "en_US")

    /// The listed first pitch.
    static let start = "2026-09-30T21:00:00+00:00".asDate!
    /// The final bodies' own capture instant (the `/history` capture).
    static let finalNow = "2026-10-11T04:57:23.592725+00:00".asDate!
    /// CONSTRUCTED: 33 s after the served `current_odds.captured_at`.
    static let liveNow = "2026-10-01T00:16:30+00:00".asDate!
    /// CONSTRUCTED host clock for `liveEvent`'s pair: the served `current_odds.captured_at`.
    static let liveObservedAt = "2026-10-01T00:15:57.061753+00:00".asDate!
    /// The live history fixture's own cut instant.
    static let liveHistoryNow = "2026-09-30T22:13:00+00:00".asDate!
    /// CONSTRUCTED: one minute before first pitch.
    static let beforeNow = "2026-09-30T20:59:00+00:00".asDate!
    /// CONSTRUCTED host clock for `beforeEvent`'s pair: its row's own timestamp.
    static let beforeObservedAt = "2026-09-30T20:58:00+00:00".asDate!
    /// CONSTRUCTED: 39 s after the retained extra-innings row's own clock.
    static let extraNow = "2026-09-30T23:05:00+00:00".asDate!
    /// The retained extra-innings row's own observation clock.
    static let extraRecordedAt = "2026-09-30T23:04:20.681782+00:00".asDate!

    static let marketsFile = "event-15321836-game-markets-11284-mlb-final.20260930.json"
    static let relatedFile = "event-15321836-related-11284-mlb-final.20260930.json"
    static let liveHistoryFile = "history-15321836-late-start.20260930T2213Z.json"

    /// The keys `liveEvent` changes: in play, no completion, no settled verdict.
    static let liveEdits: [String: Any] = [
        "status": "live", "completed_at": NSNull(), "hero_settled_result": NSNull(),
        "hero_probability": NSNull(), "hero_probability_away": NSNull(), "hero_probability_source": NSNull(),
    ]

    /// The keys `beforeEvent` changes: scheduled, no score, no completion, no
    /// settled verdict, and the 20:58:00Z consensus row as its current odds.
    static let beforeEdits: [String: Any] = [
        "status": "scheduled", "completed_at": NSNull(), "home_score": NSNull(), "away_score": NSNull(),
        "hero_settled_result": NSNull(), "hero_probability": NSNull(), "hero_probability_away": NSNull(),
        "hero_probability_source": NSNull(),
        "current_odds": ["captured_at": "2026-09-30T20:58:00+00:00", "home_probability": 0.589,
                         "away_probability": 0.411, "over_under": 7.5, "bookmaker_count": 3] as [String: Any],
    ]

    static func decoder() -> JSONDecoder {
        let decoder = JSONDecoder()
        decoder.keyDecodingStrategy = .convertFromSnakeCase
        return decoder
    }

    static func detail(_ json: String) throws -> EventDetail {
        try decoder().decode(EventDetail.self, from: Data(json.utf8))
    }

    static func history(_ json: String) throws -> EventHistoryResponse {
        try decoder().decode(EventHistoryResponse.self, from: Data(json.utf8))
    }

    static func fixture(_ name: String) throws -> Data {
        try Data(contentsOf: URL(fileURLWithPath: #filePath).deletingLastPathComponent()
            .appendingPathComponent("Fixtures").appendingPathComponent(name))
    }

    static func markets() throws -> GameMarketsResponse {
        try decoder().decode(GameMarketsResponse.self, from: fixture(marketsFile))
    }

    static func related() throws -> RelatedFuturesResponse {
        try decoder().decode(RelatedFuturesResponse.self, from: fixture(relatedFile))
    }

    static func liveHistory() throws -> EventHistoryResponse {
        try decoder().decode(EventHistoryResponse.self, from: fixture(liveHistoryFile))
    }

    static func finalEvent() throws -> EventDetail { try detail(finalDetail) }

    /// The retained live extra-innings row through the production decoder.
    static func liveExtraOther() throws -> GameMarketOther {
        try decoder().decode(GameMarketOther.self, from: Data(liveExtraRow.utf8))
    }

    /// CONSTRUCTED: a live `/game-markets` body for `eventID` whose only
    /// `other` rows are `rows` (default: the retained live row, verbatim). It is
    /// never the final body, which serves no such row.
    static func liveExtraMarkets(eventID: Int = eventID, rows: [String]? = nil) throws -> GameMarketsResponse {
        let others = (rows ?? [liveExtraRow]).joined(separator: ",")
        let body = "{\"event_id\":\(eventID),\"status\":\"live\",\"other\":[\(others)]}"
        return try decoder().decode(GameMarketsResponse.self, from: Data(body.utf8))
    }

    /// The retained row's own served values that `GameMarketOther` does not
    /// decode, read here the way the owner's admission would read them.
    nonisolated struct ServedExtraRow: Decodable {
        let _marketId: Int?
        let contributorOutcomeIds: [Int]?
        let source: String?
        let pregameMark: Double?
        let overProbability: Double?
        let openingOverProbability: Double?
        let observedAt: String?
    }

    static func servedExtraRow() throws -> ServedExtraRow {
        try decoder().decode(ServedExtraRow.self, from: Data(liveExtraRow.utf8))
    }

    /// The owner's admission of the retained row, from its own served values:
    /// identity from `_market_id` / `contributor_outcome_ids` / `source`, the
    /// pregame chance from `pregame_mark` (never `opening_over_probability`),
    /// the recorded chance from `over_probability` at its own `observed_at`.
    static func liveExtraAdmission() throws -> BaseballExtraInningsAdmission10868 {
        let row = try servedExtraRow()
        return BaseballExtraInningsAdmission10868(
            marketID: try XCTUnwrap(row._marketId), outcomeIDs: try XCTUnwrap(row.contributorOutcomeIds),
            source: try XCTUnwrap(row.source), pregame: row.pregameMark, recorded: row.overProbability,
            recordedAt: row.observedAt)
    }

    /// CONSTRUCTED: the final detail with exactly `liveEdits`' keys (and any
    /// `extra` keys the caller names) changed.
    static func liveEvent(_ extra: [String: Any] = [:]) throws -> EventDetail {
        try detail(edited(finalDetail, setting: liveEdits.merging(extra) { _, new in new }))
    }

    /// CONSTRUCTED: the final detail with exactly `beforeEdits`' keys (and any
    /// `extra` keys the caller names) changed.
    static func beforeEvent(_ extra: [String: Any] = [:]) throws -> EventDetail {
        try detail(edited(finalDetail, setting: beforeEdits.merging(extra) { _, new in new }))
    }

    /// A served body with top-level keys removed or replaced: CONSTRUCTED.
    static func edited(_ json: String, removing: [String] = [], setting: [String: Any] = [:]) throws -> String {
        var object = try XCTUnwrap(JSONSerialization.jsonObject(with: Data(json.utf8)) as? [String: Any])
        for key in removing { object.removeValue(forKey: key) }
        for (key, value) in setting { object[key] = value }
        return String(decoding: try JSONSerialization.data(withJSONObject: object), as: UTF8.self)
    }

    /// CONSTRUCTED: `/game-markets` with exactly the named keys of the one
    /// matrix option `optionKey` replaced. Every other byte's value is served.
    static func markets(editingOption optionKey: String, setting: [String: Any]) throws -> GameMarketsResponse {
        var body = try XCTUnwrap(JSONSerialization.jsonObject(with: fixture(marketsFile)) as? [String: Any])
        var matrix = try XCTUnwrap(body["game_question_matrix"] as? [String: Any])
        var questions = try XCTUnwrap(matrix["questions"] as? [[String: Any]])
        var edits = 0
        for index in questions.indices {
            guard var options = questions[index]["options"] as? [[String: Any]] else { continue }
            for option in options.indices where options[option]["option_key"] as? String == optionKey {
                for (key, value) in setting { options[option][key] = value }
                edits += 1
            }
            questions[index]["options"] = options
        }
        XCTAssertEqual(edits, 1, "exactly one option carries \(optionKey)")
        matrix["questions"] = questions
        body["game_question_matrix"] = matrix
        return try decoder().decode(GameMarketsResponse.self, from: JSONSerialization.data(withJSONObject: body))
    }

    static func sha256(_ data: Data) -> String {
        SHA256.hash(data: data).map { String(format: "%02x", $0) }.joined()
    }

    static func sha256(_ text: String) -> String { sha256(Data(text.utf8)) }

    static func pageHost(_ now: Date, observedAt: Date?,
                         interrupted: Bool = false) -> BaseballGamePageAdapter10868.Host {
        BaseballGamePageAdapter10868.Host(probabilityObservedAt: observedAt, deliveryInterrupted: interrupted,
                                          now: now, calendar: pacific, locale: locale)
    }

    static func historyHost(_ now: Date) -> BaseballHistoryAdapter10868.Host {
        BaseballHistoryAdapter10868.Host(now: now, calendar: pacific, locale: locale)
    }

    static func milestoneHost(_ now: Date) -> BaseballRunMilestonesAdapter10868.Host {
        BaseballRunMilestonesAdapter10868.Host(now: now, calendar: pacific, locale: locale)
    }

    static func originalsHost(_ now: Date) -> BaseballOriginalsAdapter10868.Host {
        BaseballOriginalsAdapter10868.Host(now: now, calendar: pacific, locale: locale)
    }

    static let finalDetail = ##"""
{"id":15321836,"external_id":"766096a9312f4528ba2e8b59fe9550fd","sport":"baseball_mlb","sport_name":"MLB","home_team":"Houston Astros","away_team":"Chicago White Sox","commence_time":"2026-09-30T21:00:00+00:00","start_is_tbd":false,"completed_at":"2026-10-01T00:18:08.432634+00:00","status":"completed","started_without_result":false,"home_score":3,"away_score":7,"home_team_data":{"team_id":10715,"slug":"houston-astros-mlb","primary_color":"#002d62","secondary_color":"#eb6e1f","logo_small":"https://a.espncdn.com/i/teamlogos/mlb/500/scoreboard/hou.png","logo_large":"https://a.espncdn.com/i/teamlogos/mlb/500/scoreboard/hou.png","record":"81-81","abbreviation":"HOU","standings":{"pct":".500","wins":81,"losses":81,"div_rank":1,"division":"West","conference":"American League","home_record":"39-42"}},"away_team_data":{"team_id":10734,"slug":"chicago-white-sox-mlb","primary_color":"#000000","secondary_color":"#c4ced4","logo_small":"https://a.espncdn.com/i/teamlogos/mlb/500/scoreboard/chw.png","logo_large":"https://a.espncdn.com/i/teamlogos/mlb/500/scoreboard/chw.png","record":"84-78","abbreviation":"CHW","standings":{"pct":".519","wins":84,"losses":78,"div_rank":2,"division":"Central","conference":"American League","home_record":"48-33"}},"metadata":{"gender":"men","level":"professional","league":"MLB","importance":"playoff"},"espn":{"espn_id":"401907897","broadcast":"Peacock, NBCSN","win_probability":0.043,"probability_sources":{"mlb":0.001,"espn":0.043,"stat_model":0.001,"betting_book_count":1.0}},"win_probability_sources":{"mlb":{"value":0.001,"display_name":"MLB Model","type":"model","color":"#06b6d4","updated_at":"2026-10-01T00:15:55.738185+00:00","evidence_status":"not_applicable"},"espn":{"value":0.043,"display_name":"ESPN","type":"model","color":"#f97316","updated_at":"2026-09-30T23:54:07.021895+00:00","evidence_status":"not_applicable"},"stat_model":{"value":0.001,"display_name":"Bain Luck Model","type":"model","color":"#8b5cf6","updated_at":"2026-10-01T00:17:07.134209+00:00","evidence_status":"not_applicable"},"betting_book_count":{"value":1.0,"display_name":"betting_book_count","type":"model","color":"#6b7280","evidence_status":"not_applicable"}},"ei":{"score":63,"raw_score":81,"status":"exciting","label":"Engaging","emoji":"⚡","metadata":{"raw_ei":1.6267,"lead_changes":7,"comeback_factor":0.4176,"snapshot_count":396}},"pulse":{"score":63,"raw_score":81,"status":"exciting","label":"Engaging","emoji":"⚡","metadata":{"raw_ei":1.6267,"lead_changes":7,"comeback_factor":0.4176,"snapshot_count":396}},"event_tags":["audience:national_interest","class:pro_major","competitive_structure:head_to_head","ei:must_watch","gender:men","importance:playoff","league:mlb","level:professional","sport:baseball","stakes:playoff_race","status:completed","tier:1","timing:national_tv"],"standings_context":{"home":"81-81, #1 West","away":"84-78, #2 Central","stakes":"Playoff game"},"current_odds":{"captured_at":"2026-10-01T00:15:57.061753+00:00","home_probability":0.001,"away_probability":0.999,"away_rendered_percent":100,"home_rendered_percent":0,"spread":2.4,"over_under":9.9,"projected_home_score":null,"projected_away_score":null,"bookmaker_count":8},"bookmaker_odds":[{"bookmaker":"ballybet","home_moneyline":null,"away_moneyline":null,"home_probability":null,"away_probability":null,"captured_at":"2026-10-01T00:13:57.123985+00:00","spread":3.5,"over_under":10.5,"projected_home_score":null,"projected_away_score":null},{"bookmaker":"betanysports","home_moneyline":-153,"away_moneyline":135,"home_probability":0.587,"away_probability":0.413,"captured_at":"2026-09-30T21:03:56.602892+00:00","spread":-1.5,"over_under":7.5,"projected_home_score":null,"projected_away_score":null},{"bookmaker":"betmgm","home_moneyline":3300,"away_moneyline":-10000,"home_probability":0.0288,"away_probability":0.9712,"captured_at":"2026-10-01T00:13:57.112124+00:00","spread":3.5,"over_under":10.5,"projected_home_score":null,"projected_away_score":null},{"bookmaker":"betonlineag","home_moneyline":-149,"away_moneyline":135,"home_probability":0.5844,"away_probability":0.4156,"captured_at":"2026-09-30T21:07:26.061118+00:00","spread":-1.5,"over_under":7.5,"projected_home_score":null,"projected_away_score":null},{"bookmaker":"betparx","home_moneyline":null,"away_moneyline":null,"home_probability":null,"away_probability":null,"captured_at":"2026-10-01T00:14:26.587562+00:00","spread":3.5,"over_under":10.5,"projected_home_score":null,"projected_away_score":null},{"bookmaker":"betrivers","home_moneyline":null,"away_moneyline":null,"home_probability":null,"away_probability":null,"captured_at":"2026-10-01T00:04:26.729801+00:00","spread":3.5,"over_under":10.5,"projected_home_score":null,"projected_away_score":null},{"bookmaker":"betus","home_moneyline":-147,"away_moneyline":132,"home_probability":0.58,"away_probability":0.42,"captured_at":"2026-09-30T21:10:05.557385+00:00","spread":-1.5,"over_under":7.5,"projected_home_score":null,"projected_away_score":null},{"bookmaker":"bovada","home_moneyline":null,"away_moneyline":null,"home_probability":null,"away_probability":null,"captured_at":"2026-09-30T23:55:57.154973+00:00","spread":4.0,"over_under":10.5,"projected_home_score":null,"projected_away_score":null},{"bookmaker":"courtside","home_moneyline":null,"away_moneyline":null,"home_probability":null,"away_probability":null,"captured_at":"2026-10-01T00:04:57.085853+00:00","spread":3.5,"over_under":10.5,"projected_home_score":null,"projected_away_score":null},{"bookmaker":"draftkings","home_moneyline":null,"away_moneyline":null,"home_probability":null,"away_probability":null,"captured_at":"2026-10-01T00:06:05.513039+00:00","spread":3.5,"over_under":10.5,"projected_home_score":null,"projected_away_score":null},{"bookmaker":"espnbet","home_moneyline":2000,"away_moneyline":-20000,"home_probability":0.0457,"away_probability":0.9543,"captured_at":"2026-10-01T00:07:57.095535+00:00","spread":null,"over_under":null,"projected_home_score":null,"projected_away_score":null},{"bookmaker":"fanatics","home_moneyline":null,"away_moneyline":null,"home_probability":null,"away_probability":null,"captured_at":"2026-10-01T00:14:26.603812+00:00","spread":3.5,"over_under":10.5,"projected_home_score":null,"projected_away_score":null},{"bookmaker":"fanduel","home_moneyline":null,"away_moneyline":null,"home_probability":null,"away_probability":null,"captured_at":"2026-10-01T00:12:26.697188+00:00","spread":3.5,"over_under":10.5,"projected_home_score":null,"projected_away_score":null},{"bookmaker":"fliff","home_moneyline":null,"away_moneyline":null,"home_probability":null,"away_probability":null,"captured_at":"2026-10-01T00:05:26.526414+00:00","spread":3.5,"over_under":10.5,"projected_home_score":null,"projected_away_score":null},{"bookmaker":"hardrockbet","home_moneyline":null,"away_moneyline":null,"home_probability":null,"away_probability":null,"captured_at":"2026-10-01T00:15:57.061753+00:00","spread":null,"over_under":10.5,"projected_home_score":null,"projected_away_score":null},{"bookmaker":"lowvig","home_moneyline":-149,"away_moneyline":135,"home_probability":0.5844,"away_probability":0.4156,"captured_at":"2026-09-30T21:07:26.056800+00:00","spread":-1.5,"over_under":7.5,"projected_home_score":null,"projected_away_score":null},{"bookmaker":"mybookieag","home_moneyline":1125,"away_moneyline":-5000,"home_probability":0.0769,"away_probability":0.9231,"captured_at":"2026-09-30T23:46:26.366098+00:00","spread":3.5,"over_under":10.5,"projected_home_score":null,"projected_away_score":null},{"bookmaker":"rebet","home_moneyline":550,"away_moneyline":-2000,"home_probability":0.1391,"away_probability":0.8609,"captured_at":"2026-09-30T23:20:57.287441+00:00","spread":3.5,"over_under":12.5,"projected_home_score":null,"projected_away_score":null},{"bookmaker":"williamhill_us","home_moneyline":null,"away_moneyline":null,"home_probability":null,"away_probability":null,"captured_at":"2026-10-01T00:15:57.037855+00:00","spread":3.5,"over_under":10.5,"projected_home_score":null,"projected_away_score":null}],"opening_odds":{"home_probability":0.5802,"away_probability":0.4198,"spread":-1.5,"over_under":7.5,"favorite":"home"},"prematch_odds":{"home_probability":0.585,"away_probability":0.415,"home_rendered_percent":59,"away_rendered_percent":41,"source":"kalshi"},"hero_probability_observed_at":null,"blend_fold_revision":{"15321836":3176},"hero_probability":0.0,"hero_probability_away":1.0,"hero_probability_source":"settled","hero_settled_result":"away","box_score_data":{"players":{"Cam Smith":{"hits":1.0,"rbis":1.0,"runs":1.0,"walks":0.0,"at bats":3.0,"home runs":1.0,"strikeouts":2.0,"pitches seen":20.0,"batting average":0.286,"on base percentage":0.375,"slugging percentage":0.714},"Kyle Teel":{"hits":2.0,"rbis":1.0,"runs":1.0,"walks":0.0,"at bats":5.0,"home runs":0.0,"strikeouts":3.0,"pitches seen":18.0,"batting average":0.3,"on base percentage":0.3,"slugging percentage":0.3},"Josh Hader":{"era":0.0,"earned runs":0.0,"pitch count":22.0,"innings pitched":1.1,"pitching strikeouts":1.0,"pitching hits allowed":2.0,"pitching runs allowed":0.0,"pitching walks allowed":0.0,"pitching home runs allowed":0.0},"Nick Allen":{"hits":0.0,"rbis":0.0,"runs":0.0,"walks":0.0,"at bats":3.0,"home runs":0.0,"strikeouts":1.0,"pitches seen":9.0,"batting average":0.0,"on base percentage":0.0,"slugging percentage":0.0},"Sean Burke":{"era":6.75,"earned runs":3.0,"pitch count":72.0,"innings pitched":4.0,"pitching strikeouts":8.0,"pitching hits allowed":4.0,"pitching runs allowed":3.0,"pitching walks allowed":0.0,"pitching home runs allowed":3.0},"AJ Blubaugh":{"era":0.0,"earned runs":0.0,"pitch count":15.0,"innings pitched":1.1,"pitching strikeouts":2.0,"pitching hits allowed":0.0,"pitching runs allowed":0.0,"pitching walks allowed":0.0,"pitching home runs allowed":0.0},"Anthony Kay":{"era":0.0,"earned runs":0.0,"pitch count":11.0,"innings pitched":0.2,"pitching strikeouts":0.0,"pitching hits allowed":0.0,"pitching runs allowed":0.0,"pitching walks allowed":1.0,"pitching home runs allowed":0.0},"Bryan Abreu":{"era":2.45,"earned runs":1.0,"pitch count":44.0,"innings pitched":2.2,"pitching strikeouts":6.0,"pitching hits allowed":1.0,"pitching runs allowed":1.0,"pitching walks allowed":1.0,"pitching home runs allowed":1.0},"Erick Fedde":{"era":0.0,"earned runs":0.0,"pitch count":34.0,"innings pitched":2.0,"pitching strikeouts":3.0,"pitching hits allowed":0.0,"pitching runs allowed":0.0,"pitching walks allowed":0.0,"pitching home runs allowed":0.0},"Jeremy Pena":{"hits":2.0,"rbis":1.0,"runs":1.0,"walks":0.0,"at bats":4.0,"home runs":1.0,"strikeouts":2.0,"pitches seen":17.0,"batting average":0.375,"on base percentage":0.375,"slugging percentage":0.75},"Jose Altuve":{"hits":2.0,"rbis":1.0,"runs":1.0,"walks":0.0,"at bats":4.0,"home runs":1.0,"strikeouts":1.0,"pitches seen":12.0,"batting average":0.25,"on base percentage":0.25,"slugging percentage":0.625},"Yainer Diaz":{"hits":0.0,"rbis":0.0,"runs":0.0,"walks":0.0,"at bats":4.0,"home runs":0.0,"strikeouts":2.0,"pitches seen":16.0,"batting average":0.0,"on base percentage":0.0,"slugging percentage":0.0},"Hunter Brown":{"era":40.5,"earned runs":3.0,"pitch count":36.0,"innings pitched":0.2,"pitching strikeouts":2.0,"pitching hits allowed":5.0,"pitching runs allowed":4.0,"pitching walks allowed":1.0,"pitching home runs allowed":0.0},"Jordan Hicks":{"era":0.0,"earned runs":0.0,"pitch count":21.0,"innings pitched":2.0,"pitching strikeouts":3.0,"pitching hits allowed":0.0,"pitching runs allowed":0.0,"pitching walks allowed":0.0,"pitching home runs allowed":0.0},"Lucas Spence":{"hits":0.0,"rbis":0.0,"runs":0.0,"walks":0.0,"at bats":4.0,"home runs":0.0,"strikeouts":1.0,"pitches seen":17.0,"batting average":0.125,"on base percentage":0.125,"slugging percentage":0.125},"Brenton Doyle":{"hits":1.0,"rbis":0.0,"runs":0.0,"walks":0.0,"at bats":1.0,"home runs":0.0,"strikeouts":0.0,"pitches seen":3.0,"batting average":1.0,"on base percentage":1.0,"slugging percentage":1.0},"Isaac Paredes":{"hits":0.0,"rbis":0.0,"runs":0.0,"walks":1.0,"at bats":2.0,"home runs":0.0,"strikeouts":1.0,"pitches seen":24.0,"batting average":0.167,"on base percentage":0.375,"slugging percentage":0.167},"Miguel Vargas":{"hits":0.0,"rbis":0.0,"runs":1.0,"walks":0.0,"at bats":5.0,"home runs":0.0,"strikeouts":2.0,"pitches seen":23.0,"batting average":0.0,"on base percentage":0.1,"slugging percentage":0.0},"Peter Lambert":{"era":6.0,"earned runs":2.0,"pitch count":48.0,"innings pitched":3.0,"pitching strikeouts":2.0,"pitching hits allowed":0.0,"pitching runs allowed":2.0,"pitching walks allowed":2.0,"pitching home runs allowed":0.0},"Sam Antonacci":{"hits":1.0,"rbis":0.0,"runs":1.0,"walks":0.0,"at bats":4.0,"home runs":0.0,"strikeouts":1.0,"pitches seen":14.0,"batting average":0.286,"on base percentage":0.444,"slugging percentage":0.429},"Chase Meidroth":{"hits":2.0,"rbis":3.0,"runs":1.0,"walks":1.0,"at bats":3.0,"home runs":1.0,"strikeouts":0.0,"pitches seen":24.0,"batting average":0.571,"on base percentage":0.625,"slugging percentage":1.0},"Tristan Peters":{"hits":1.0,"rbis":1.0,"runs":1.0,"walks":1.0,"at bats":3.0,"home runs":0.0,"strikeouts":1.0,"pitches seen":17.0,"batting average":0.286,"on base percentage":0.375,"slugging percentage":0.286},"Yordan Alvarez":{"hits":0.0,"rbis":0.0,"runs":0.0,"walks":0.0,"at bats":4.0,"home runs":0.0,"strikeouts":2.0,"pitches seen":19.0,"batting average":0.125,"on base percentage":0.125,"slugging percentage":0.125},"Luisangel Acuna":{"hits":0.0,"rbis":0.0,"runs":1.0,"walks":0.0,"at bats":1.0,"home runs":0.0,"strikeouts":0.0,"pitches seen":2.0,"batting average":0.0,"on base percentage":0.0,"slugging percentage":0.0},"Christian Walker":{"hits":0.0,"rbis":0.0,"runs":0.0,"walks":0.0,"at bats":4.0,"home runs":0.0,"strikeouts":3.0,"pitches seen":20.0,"batting average":0.0,"on base percentage":0.25,"slugging percentage":0.0},"Huascar Brazoban":{"era":0.0,"earned runs":0.0,"pitch count":16.0,"innings pitched":0.1,"pitching strikeouts":1.0,"pitching hits allowed":1.0,"pitching runs allowed":0.0,"pitching walks allowed":0.0,"pitching home runs allowed":0.0},"Andrew Benintendi":{"hits":1.0,"rbis":1.0,"runs":1.0,"walks":1.0,"at bats":2.0,"home runs":0.0,"strikeouts":0.0,"pitches seen":13.0,"batting average":0.333,"on base percentage":0.6,"slugging percentage":0.333},"Braden Montgomery":{"hits":0.0,"rbis":0.0,"runs":0.0,"walks":0.0,"at bats":4.0,"home runs":0.0,"strikeouts":1.0,"pitches seen":9.0,"batting average":0.25,"on base percentage":0.25,"slugging percentage":0.25},"Colson Montgomery":{"hits":0.0,"rbis":0.0,"runs":0.0,"walks":1.0,"at bats":3.0,"home runs":0.0,"strikeouts":2.0,"pitches seen":18.0,"batting average":0.167,"on base percentage":0.375,"slugging percentage":0.667},"Munetaka Murakami":{"hits":0.0,"rbis":0.0,"runs":0.0,"walks":0.0,"at bats":5.0,"home runs":0.0,"strikeouts":3.0,"pitches seen":24.0,"batting average":0.125,"on base percentage":0.2,"slugging percentage":0.125}},"home_period_scores":[1,1,0,1,0,0,0,0,0],"away_period_scores":[4,0,0,0,0,3,0,0,0]}}
"""##

    static let liveExtraRow = ##"""
{
  "market_name": "Chicago White Sox vs Houston: Extra Innings",
  "outcome_name": "Yes",
  "observed_at": "2026-09-30T23:04:20.681782+00:00",
  "contributor_outcome_ids": [
   237550051
  ],
  "threshold": null,
  "over_probability": 0.16,
  "opening_over_probability": 0.08,
  "pregame_mark": 0.11,
  "_inverted": false,
  "source": "kalshi",
  "movement": 0.08,
  "_market_id": 62972332
 }
"""##

    static let finalHistory = ##"""
{"event_id":15321836,
"home_team":"Houston Astros",
"away_team":"Chicago White Sox",
"commence_time":"2026-09-30T21:00:00+00:00",
"completed_at":"2026-10-01T00:18:08.432634+00:00",
"status":"completed",
"time_domain":{"start":"2026-09-30T21:00:00+00:00","end":"2026-10-01T00:48:08.432634+00:00","is_live":false,"min_window_seconds":1800},
"history":[{"timestamp":"2026-09-30T00:23:00+00:00","home_probability":0.5775,"away_probability":0.4225,"over_under":8.0,"projected_home_score":null,"projected_away_score":null,"bookmaker_count":1,"probability_range":{"min":0.5775,"max":0.5775}},{"timestamp":"2026-09-30T00:25:00+00:00","home_probability":0.5724,"away_probability":0.4276,"over_under":7.5,"projected_home_score":null,"projected_away_score":null,"bookmaker_count":2,"probability_range":{"min":0.5671,"max":0.5776}},{"timestamp":"2026-09-30T20:58:00+00:00","home_probability":0.589,"away_probability":0.411,"over_under":7.5,"projected_home_score":null,"projected_away_score":null,"bookmaker_count":3,"probability_range":{"min":0.5885,"max":0.5892}},{"timestamp":"2026-09-30T21:00:00+00:00","home_probability":0.5743,"away_probability":0.4257,"over_under":7.5,"projected_home_score":null,"projected_away_score":null,"bookmaker_count":4,"probability_range":{"min":0.558,"max":0.5807}},{"timestamp":"2026-10-01T00:15:00+00:00","home_probability":null,"away_probability":null,"over_under":10.5,"projected_home_score":null,"projected_away_score":null,"bookmaker_count":0,"probability_range":{"min":null,"max":null}},{"timestamp":"2026-10-01T00:18:00+00:00","home_probability":0.0,"away_probability":1.0,"over_under":null,"projected_home_score":null,"projected_away_score":null,"bookmaker_count":0,"probability_range":{"min":0.0,"max":0.0}}],
"bookmaker_history":{},
"score_history":[{"timestamp":"2026-09-30T21:13:06.610471+00:00","home_score":0,"away_score":0},{"timestamp":"2026-09-30T21:14:06.905216+00:00","home_score":0,"away_score":1},{"timestamp":"2026-09-30T21:21:07.543514+00:00","home_score":0,"away_score":3},{"timestamp":"2026-09-30T21:22:07.777909+00:00","home_score":0,"away_score":4},{"timestamp":"2026-09-30T21:38:11.351896+00:00","home_score":1,"away_score":4},{"timestamp":"2026-09-30T22:01:07.013893+00:00","home_score":2,"away_score":4},{"timestamp":"2026-09-30T22:34:06.992527+00:00","home_score":3,"away_score":4},{"timestamp":"2026-09-30T23:14:07.058172+00:00","home_score":3,"away_score":7}],
"espn_history":[{"timestamp":"2026-09-30T21:13:55.561111+00:00","home_probability":0.372,"away_probability":0.628,"home_score":0,"away_score":1,"game_clock":null,"period":null},{"timestamp":"2026-09-30T21:14:06.905216+00:00","home_probability":0.4783,"away_probability":0.5217,"home_score":0,"away_score":1,"game_clock":null,"period":"Top 1st"},{"timestamp":"2026-10-01T00:15:55.701687+00:00","home_probability":0.001,"away_probability":0.999,"home_score":3,"away_score":7,"game_clock":null,"period":null},{"timestamp":"2026-10-01T00:18:00+00:00","home_probability":0.0,"away_probability":1.0,"home_score":3,"away_score":7,"game_clock":"Final","period":"Final"}],
"win_prob_history":{"kalshi":[{"timestamp":"2026-09-28T01:56:00+00:00","home_probability":0.49,"away_probability":0.51,"draw_probability":null,"game_state":null,"evidence":{"kind":"candle"}},{"timestamp":"2026-10-01T00:18:00+00:00","home_probability":0.0,"away_probability":1.0,"draw_probability":null,"game_state":null,"evidence":{"kind":"final"}}],"polymarket":[{"timestamp":"2026-09-28T13:30:18+00:00","home_probability":0.5,"away_probability":0.5,"draw_probability":null,"game_state":null,"evidence":{"kind":"price_history"}},{"timestamp":"2026-10-01T00:18:00+00:00","home_probability":0.0,"away_probability":1.0,"draw_probability":null,"game_state":null,"evidence":{"kind":"final"}}],"espn":[{"timestamp":"2026-09-30T21:12:47+00:00","home_probability":0.52,"away_probability":0.48,"draw_probability":null,"game_state":null,"evidence":{"kind":"play_history"}},{"timestamp":"2026-10-01T00:18:00+00:00","home_probability":0.0,"away_probability":1.0,"draw_probability":null,"game_state":null,"evidence":{"kind":"final"}}],"stat_model":[{"timestamp":"2026-09-30T21:13:06.610471+00:00","home_probability":0.6117,"away_probability":0.3883,"draw_probability":null,"game_state":{"clock":"0:00","period":"Top 1st","away_score":0,"home_score":0,"time_source":"espn"}},{"timestamp":"2026-10-01T00:18:00+00:00","home_probability":0.0,"away_probability":1.0,"draw_probability":null,"game_state":null,"evidence":{"kind":"final"}}],"mlb":[{"timestamp":"2026-09-30T21:13:55.561111+00:00","home_probability":0.372,"away_probability":0.628,"draw_probability":null,"game_state":{"away_score":1,"home_score":0}},{"timestamp":"2026-10-01T00:18:00+00:00","home_probability":0.0,"away_probability":1.0,"draw_probability":null,"game_state":null,"evidence":{"kind":"final"}}]},
"evidence_contract":{"v":"7878.v1","resolution_s":300},
"win_prob_sources":{"kalshi":{"display_name":"Kalshi","type":"market","color":"#22c55e","dash_pattern":"8 4","description":"Win probability from Kalshi, a CFTC-regulated prediction market where real money is traded on event outcomes. Kalshi odds represent the consensus of market participants betting on game outcomes.","methodology":"The midpoint of the bid/ask spread for the 'Yes' contract on the game outcome market. Kalshi contracts settle at $1 if the event occurs and $0 otherwise, so the price directly represents the market's implied probability.","attribution_url":"https://kalshi.com","attribution_name":"Kalshi","snapshot_count":424},"polymarket":{"display_name":"Polymarket","type":"market","color":"#3b82f6","dash_pattern":"8 4","description":"Win probability from Polymarket, the world's largest prediction market by volume. Polymarket prices reflect the consensus of thousands of traders betting real money on game outcomes.","methodology":"The outcome price from Polymarket's CLOB (Central Limit Order Book). Prices range from $0.00 to $1.00 and directly represent implied probability. For binary markets, the 'Yes' price equals the market's probability estimate.","attribution_url":"https://polymarket.com","attribution_name":"Polymarket","snapshot_count":319},"espn":{"display_name":"ESPN","type":"model","color":"#f97316","dash_pattern":"6 3","description":"ESPN's proprietary predictive model that updates on every play during live games. Uses game situation data including score, field position, down, distance, and time remaining.","methodology":"ESPN's internal win probability model, same data shown on ESPN.com game pages. Methodology is not publicly documented.","attribution_url":"https://www.espn.com","attribution_name":"ESPN","snapshot_count":77},"stat_model":{"display_name":"Bain Luck Model","type":"model","color":"#8b5cf6","dash_pattern":"4 4","description":"An open win probability model using sport-specific methodology. Clock sports (NFL, NBA, NHL) use a normal distribution model inspired by nflfastR. Baseball uses a Poisson run-scoring model based on Tom Tango's methodology.","methodology":"Clock sports: Based on Hal Stern's research. Final margin modeled as N(score_diff + spread × remaining_fraction, base_std × √remaining_fraction). Baseball: Based on Tom Tango's 'The Book'. Remaining runs modeled as Poisson(runs_per_half_inning × half_innings_remaining). Normal approximation gives P(home wins) accounting for asymmetric half-innings, walk-off rule, and home field advantage (~54% historical home win rate).","attribution_url":"https://www.pro-football-reference.com/about/win_prob.htm","attribution_name":"nflfastR / PFR methodology","snapshot_count":42},"mlb":{"display_name":"MLB Model","type":"model","color":"#06b6d4","dash_pattern":"4 4","description":"Official MLB win probability from the MLB Stats API. Computed from play-by-play data using run expectancy tables, leverage index, and game state (inning, outs, runners, score).","methodology":"MLB's win probability model is based on historical play-by-play data across MLB seasons. It uses run expectancy matrices (based on base/out state), score differential, inning, home-field advantage, and updates on every pitch. Data sourced from the official MLB Stats API (statsapi.mlb.com).","attribution_url":"https://statsapi.mlb.com","attribution_name":"MLB Stats API","snapshot_count":62}},
"scoring_plays":[],
"moments":[{"ts":"2026-09-30T21:21:55.529714+00:00","label":"Chicago White Sox score — win prob +19.7 pts","confidence":1.0,"moment_type":"score","actor_team":"Chicago White Sox","prob_delta":0.197,"period":null},{"ts":"2026-09-30T21:37:55.531496+00:00","label":"Houston Astros score — win prob +7.1 pts","confidence":0.737,"moment_type":"score","actor_team":"Houston Astros","prob_delta":0.071,"period":null},{"ts":"2026-09-30T22:01:55.543890+00:00","label":"Houston Astros score — win prob +6.9 pts","confidence":0.73,"moment_type":"score","actor_team":"Houston Astros","prob_delta":0.069,"period":null},{"ts":"2026-09-30T22:33:55.523213+00:00","label":"Houston Astros score — win prob +11.7 pts","confidence":0.89,"moment_type":"score","actor_team":"Houston Astros","prob_delta":0.117,"period":null},{"ts":"2026-09-30T23:13:55.560967+00:00","label":"Chicago White Sox score — win prob +7.7 pts","confidence":0.757,"moment_type":"score","actor_team":"Chicago White Sox","prob_delta":0.077,"period":null}],
"period_markers":[{"timestamp":"2026-09-30T21:13:06.610471+00:00","period":"Top 1st","source":"win_prob"},{"timestamp":"2026-09-30T21:33:06.887811+00:00","period":"Middle 1st","source":"win_prob"},{"timestamp":"2026-09-30T21:35:06.853357+00:00","period":"Bottom 1st","source":"win_prob"},{"timestamp":"2026-09-30T21:48:07.094755+00:00","period":"End 1st","source":"win_prob"},{"timestamp":"2026-09-30T21:50:07.862264+00:00","period":"Top 2nd","source":"win_prob"},{"timestamp":"2026-09-30T21:55:06.649605+00:00","period":"Middle 2nd","source":"win_prob"},{"timestamp":"2026-09-30T21:57:06.650276+00:00","period":"Bottom 2nd","source":"win_prob"},{"timestamp":"2026-09-30T22:02:06.737210+00:00","period":"End 2nd","source":"win_prob"},{"timestamp":"2026-09-30T22:03:06.569653+00:00","period":"Top 3rd","source":"win_prob"},{"timestamp":"2026-09-30T22:11:06.769245+00:00","period":"Middle 3rd","source":"win_prob"},{"timestamp":"2026-09-30T22:13:06.989539+00:00","period":"Bottom 3rd","source":"win_prob"},{"timestamp":"2026-09-30T22:23:06.814091+00:00","period":"End 3rd","source":"win_prob"},{"timestamp":"2026-09-30T22:25:06.956831+00:00","period":"Top 4th","source":"win_prob"},{"timestamp":"2026-09-30T22:30:06.859180+00:00","period":"Middle 4th","source":"win_prob"},{"timestamp":"2026-09-30T22:32:06.841901+00:00","period":"Bottom 4th","source":"win_prob"},{"timestamp":"2026-09-30T22:39:06.992889+00:00","period":"End 4th","source":"win_prob"},{"timestamp":"2026-09-30T22:41:06.529186+00:00","period":"Top 5th","source":"win_prob"},{"timestamp":"2026-09-30T22:45:06.890635+00:00","period":"Middle 5th","source":"win_prob"},{"timestamp":"2026-09-30T22:46:06.884636+00:00","period":"Bottom 5th","source":"win_prob"},{"timestamp":"2026-09-30T23:02:06.500911+00:00","period":"End 5th","source":"win_prob"},{"timestamp":"2026-09-30T23:16:07.115790+00:00","period":"Top 6th","source":"win_prob"},{"timestamp":"2026-09-30T23:18:06.570847+00:00","period":"Middle 6th","source":"win_prob"},{"timestamp":"2026-09-30T23:20:06.984862+00:00","period":"Bottom 6th","source":"win_prob"},{"timestamp":"2026-09-30T23:25:06.371519+00:00","period":"End 6th","source":"win_prob"},{"timestamp":"2026-09-30T23:27:07.245023+00:00","period":"Top 7th","source":"win_prob"},{"timestamp":"2026-09-30T23:33:07.243905+00:00","period":"Middle 7th","source":"win_prob"},{"timestamp":"2026-09-30T23:35:07.392991+00:00","period":"Bottom 7th","source":"win_prob"},{"timestamp":"2026-09-30T23:40:08.597488+00:00","period":"End 7th","source":"win_prob"},{"timestamp":"2026-09-30T23:42:07.452731+00:00","period":"Top 8th","source":"win_prob"},{"timestamp":"2026-09-30T23:49:06.609077+00:00","period":"Middle 8th","source":"win_prob"},{"timestamp":"2026-09-30T23:54:06.930916+00:00","period":"Bottom 8th","source":"win_prob"},{"timestamp":"2026-09-30T23:57:07.012159+00:00","period":"End 8th","source":"win_prob"},{"timestamp":"2026-09-30T23:59:06.886401+00:00","period":"Top 9th","source":"win_prob"},{"timestamp":"2026-10-01T00:08:06.922682+00:00","period":"Middle 9th","source":"win_prob"},{"timestamp":"2026-10-01T00:10:07.136776+00:00","period":"Bottom 9th","source":"win_prob"}],
"aggregate_line":[{"timestamp":"2026-09-28T01:56:00+00:00","home_probability":0.49},{"timestamp":"2026-09-28T01:58:00+00:00","home_probability":0.69},{"timestamp":"2026-09-28T01:59:00+00:00","home_probability":0.95},{"timestamp":"2026-09-30T20:47:00+00:00","home_probability":0.585},{"timestamp":"2026-09-30T20:48:00+00:00","home_probability":0.585},{"timestamp":"2026-09-30T20:51:00+00:00","home_probability":0.585},{"timestamp":"2026-09-30T20:53:00+00:00","home_probability":0.585},{"timestamp":"2026-09-30T20:55:00+00:00","home_probability":0.585},{"timestamp":"2026-09-30T20:56:00+00:00","home_probability":0.585},{"timestamp":"2026-09-30T20:57:00+00:00","home_probability":0.585},{"timestamp":"2026-09-30T20:58:00+00:00","home_probability":0.589},{"timestamp":"2026-09-30T21:00:00+00:00","home_probability":0.5755},{"timestamp":"2026-09-30T21:01:00+00:00","home_probability":0.579289},{"timestamp":"2026-09-30T21:02:00+00:00","home_probability":0.578895},{"timestamp":"2026-09-30T21:03:00+00:00","home_probability":0.583658},{"timestamp":"2026-09-30T21:04:00+00:00","home_probability":0.583184},{"timestamp":"2026-09-30T21:05:00+00:00","home_probability":0.581605},{"timestamp":"2026-09-30T21:07:00+00:00","home_probability":0.581684},{"timestamp":"2026-09-30T21:08:00+00:00","home_probability":0.575053},{"timestamp":"2026-09-30T21:09:00+00:00","home_probability":0.592895},{"timestamp":"2026-09-30T22:13:00+00:00","home_probability":0.348376},{"timestamp":"2026-09-30T22:14:00+00:00","home_probability":0.345465},{"timestamp":"2026-09-30T22:15:00+00:00","home_probability":0.334731},{"timestamp":"2026-10-01T00:13:00+00:00","home_probability":0.012084},{"timestamp":"2026-10-01T00:14:00+00:00","home_probability":0.011394},{"timestamp":"2026-10-01T00:15:00+00:00","home_probability":0.010757},{"timestamp":"2026-10-01T00:16:00+00:00","home_probability":0.010611},{"timestamp":"2026-10-01T00:17:00+00:00","home_probability":0.010558},{"timestamp":"2026-10-01T00:18:00+00:00","home_probability":0.010558},{"timestamp":"2026-10-01T00:46:00+00:00","home_probability":0.007921},{"timestamp":"2026-10-01T00:18:00+00:00","home_probability":0.0}],
"blend_edge_pinned":false,
"blend_edge_observed_at":null,
"blend_edge_fold_revision":null,
"pre_window_omitted":false,
"commence_time_is_kickoff":true,
"pm_spread_data":{"implied_spreads":{},"implied_totals":{"sportsbook":{"total":10.5,"confidence":1.0,"contracts":[]}},"projected_final":null},
"points":344,
"bookmaker_count":19,
"snapshot_count":2618,
"espn_snapshot_count":94,
"on_demand_backfill":null}
"""##
}

@MainActor
final class BaseballRetainedAdapter10868Tests: XCTestCase {
    private typealias F = BaseballRetained10868

    func testTheEmbeddedDetailIsTheRetainedBytesAndTheFixturesAreTheNamedCaptures() throws {
        XCTAssertEqual(F.sha256(F.finalDetail), "1221677b9feee61a466720cbf7a2cb9f25f9b45a4189091b07392d21f9189cf2")
        XCTAssertEqual(F.sha256(try F.fixture(F.marketsFile)),
                       "42dfb4898c993c2972eccee4c71634715082b2e6678f6da2c57917da2debdb89")
        XCTAssertEqual(F.sha256(try F.fixture(F.relatedFile)),
                       "b844152f2a6a91dccd6bf9e76c555836bcddf3b1148dba81e41c6300b7a5f23c")
        XCTAssertEqual(F.sha256(try F.fixture(F.liveHistoryFile)),
                       "b0561095a63b9bd78cdb0d18629ec9feaf8418006e581044c718a3903423528d")
        XCTAssertEqual(F.sha256(F.liveExtraRow), "66861a2fdd4ff5693a42c320c9988d255341691acc6547a5208ccb934dfb336e",
                       "element 20 of mlb-live-20260930.json, verbatim")
    }

    func testEveryBodyDecodesThroughTheProductionModels() throws {
        let final = try F.finalEvent()
        XCTAssertEqual(final.id, F.eventID)
        XCTAssertEqual(final.sport, "baseball_mlb")
        XCTAssertTrue(EventState.isFinished(final.status))
        XCTAssertEqual(final.homeScore, 3)
        XCTAssertEqual(final.awayScore, 7)
        XCTAssertEqual(final.heroSettledResult, "away")
        XCTAssertEqual(final.prematchOdds?.homeRenderedPercent, 59)

        let history = try F.history(F.finalHistory)
        XCTAssertEqual(history.eventId, F.eventID)
        XCTAssertEqual(history.aggregateLine?.count, 31)
        XCTAssertEqual(history.history.count, 6)
        XCTAssertEqual(history.espnHistory?.count, 4)

        XCTAssertEqual(try F.markets().eventId, F.eventID)
        XCTAssertEqual(try F.related().eventId, F.eventID)
        XCTAssertEqual(try F.liveHistory().status, "live")
    }

    func testTheConstructedPhasesChangeOnlyTheirNamedKeys() throws {
        let live = try F.liveEvent()
        XCTAssertEqual(live.status, "live")
        XCTAssertNil(live.heroSettledResult)
        XCTAssertEqual(live.homeScore, 3, "the served score is kept")
        XCTAssertEqual(live.currentOdds?.capturedAt, "2026-10-01T00:15:57.061753+00:00", "served, unchanged")

        let before = try F.beforeEvent()
        XCTAssertEqual(before.status, "scheduled")
        XCTAssertNil(before.homeScore)
        XCTAssertNil(before.awayScore)
        XCTAssertEqual(before.currentOdds?.homeProbability, 0.589)
        XCTAssertNil(before.currentOdds?.homeRenderedPercent, "the consensus row serves no rendered pair")
        XCTAssertEqual(before.prematchOdds?.homeProbability, 0.585, "served, unchanged")
        XCTAssertEqual(before.prematchOdds?.source, "kalshi", "served, unchanged")
    }
}
