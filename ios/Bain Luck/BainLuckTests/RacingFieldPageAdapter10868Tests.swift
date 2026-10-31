import SwiftUI
import XCTest
@testable import Bain_Luck

/// #10868 — the racing adapters' retained REAL inputs, shared by every racing
/// adapter test file, decoded exactly as the app decodes them
/// (`.convertFromSnakeCase`, `APIClient`).
///
/// REDUCED VERBATIM SUBSETS. Each kept piece — a top-level `"key":value` pair, one
/// outcome object, one history line's own keys and kept points — is the server's
/// bytes, in source order, asserted as a byte-for-byte substring of its source
/// file by `/tmp/cli-10868-racing/make_subsets.py` (run `python3 -I
/// make_subsets.py <design-dir> <out>`). Only the envelope is assembled: which
/// array members are kept and the line breaks between them; the history drops
/// its `leaderboard`, `round_boundaries` and `venue_history` keys. Sources under
/// `artifacts/discovery-containers-release-plan/event-page-design-20261011/`:
///   - the Singapore Grand Prix (Oct 11, 2026) driver-winner and podium markets,
///     before the race (atlas-v6, captured Oct 11 ~05:00Z, ~7 h before the 12:00Z
///     start) and after it (racing-expectations-v74, captured Oct 12 07:47Z,
///     `status: resolved`, `resolution_source: api_settlement`);
///   - NO `/api/futures/{id}/history` body of any race market is retained. Part
///     two's rules are therefore proven on a retained REAL futures `/history`
///     body of another independent multi-outcome board — the Kalshi "Boston vs
///     Minnesota: Total Goals" ladder, settled, with one settlement point per
///     line — and its detail. Not a racing body; a racing capture is owed.
@MainActor
enum RacingAdapterFixtures10868 {
    /// `atlas-v6/raw/field-63989371.json` (sha256 4ad65b60…bd01): outcomes [241675151, 241675152, 241675153, 241675154] of 23.
    static let winnerBefore = #"""
    {
    "id":63989371,
    "name":"Singapore Grand Prix: Driver Winner",
    "description":null,
    "sport":null,
    "sport_name":null,
    "category":"championship",
    "llm_sport_category":"motorsports",
    "status":"open",
    "source":"polymarket",
    "external_id":"1123912",
    "market_type":"field",
    "mutually_exclusive":true,
    "commence_time":"2026-10-03T11:30:31+00:00",
    "resolution_date":"2026-10-18T12:00:00+00:00",
    "outcomes":[
    {"id":241675151,"name":"Max Verstappen","probability":0.6162,"american_odds":-190,"rank":1,"rank_change_24h":null,"probability_change_24h":null,"opening_probability":null,"opening_american_odds":null,"is_winner":null,"resolution_source":null,"last_updated":"2026-10-11T04:07:53.654130+00:00","price_changed_at":"2026-10-11T04:07:53.654130+00:00"},
    {"id":241675153,"name":"Lewis Hamilton","probability":0.1364,"american_odds":590,"rank":2,"rank_change_24h":null,"probability_change_24h":null,"opening_probability":null,"opening_american_odds":null,"is_winner":null,"resolution_source":null,"last_updated":"2026-10-11T04:07:53.654130+00:00","price_changed_at":"2026-10-11T04:07:53.654130+00:00"},
    {"id":241675154,"name":"Charles Leclerc","probability":0.127,"american_odds":641,"rank":3,"rank_change_24h":null,"probability_change_24h":null,"opening_probability":null,"opening_american_odds":null,"is_winner":null,"resolution_source":null,"last_updated":"2026-10-11T04:07:53.654130+00:00","price_changed_at":"2026-10-11T04:07:53.654130+00:00"},
    {"id":241675152,"name":"Kimi Antonelli","probability":0.0706,"american_odds":1233,"rank":4,"rank_change_24h":null,"probability_change_24h":null,"opening_probability":null,"opening_american_odds":null,"is_winner":null,"resolution_source":null,"last_updated":"2026-10-11T04:07:53.654130+00:00","price_changed_at":"2026-10-11T04:07:53.654130+00:00"}
    ],
    "outcome_count":23,
    "lead_outcome_id":null,
    "openings_withheld":true,
    "prices_withheld":0,
    "expired_rungs_dropped":0,
    "bookmakers":["polymarket"],
    "category_tags":["motorsports"],
    "created_at":"2026-10-03T12:15:51.012496+00:00",
    "updated_at":"2026-10-11T04:07:53.654130+00:00",
    "group_id":"polymarket:1123912",
    "canonical_market_key":null,
    "hook_description":null,
    "hook_withheld":false,
    "image_url":"https://images.pexels.com/photos/29309757/pexels-photo-29309757.jpeg?auto=compress&cs=tinysrgb&h=650&w=940",
    "event_concept_key":"event:f1:singapore-grand-prix-driver-winner",
    "hub_slug":null,
    "category_page":null,
    "sport_page_key":null,
    "container_of_event_id":null
    }
    """#

    /// `racing-expectations-v74/raw/field-63989371.json` (sha256 27668efc…d313): outcomes [241675151, 241675152, 241675153, 241675154, 241675158, 241675161] of 23.
    static let winnerFinal = #"""
    {
    "id":63989371,
    "name":"Singapore Grand Prix: Driver Winner",
    "description":null,
    "sport":null,
    "sport_name":null,
    "category":"championship",
    "llm_sport_category":"motorsports",
    "status":"resolved",
    "source":"polymarket",
    "external_id":"1123912",
    "market_type":"field",
    "mutually_exclusive":true,
    "commence_time":"2026-10-03T11:30:31+00:00",
    "resolution_date":"2026-10-18T12:00:00+00:00",
    "outcomes":[
    {"id":241675151,"name":"Max Verstappen","probability":1.0,"american_odds":null,"rank":1,"rank_change_24h":null,"probability_change_24h":null,"opening_probability":0.335,"opening_american_odds":199,"is_winner":true,"resolution_source":"api_settlement","last_updated":"2026-10-11T17:44:12.917499+00:00","price_changed_at":"2026-10-12T05:37:43.468694+00:00"},
    {"id":241675161,"name":"Arvid Lindblad","probability":0.0,"american_odds":null,"rank":2,"rank_change_24h":null,"probability_change_24h":null,"opening_probability":0.015,"opening_american_odds":6567,"is_winner":false,"resolution_source":"api_settlement","last_updated":"2026-10-11T17:44:12.917499+00:00","price_changed_at":"2026-10-12T05:37:43.468694+00:00"},
    {"id":241675158,"name":"Yuki Tsunoda","probability":0.0,"american_odds":null,"rank":3,"rank_change_24h":null,"probability_change_24h":null,"opening_probability":0.0305,"opening_american_odds":3179,"is_winner":false,"resolution_source":"api_settlement","last_updated":"2026-10-11T17:44:12.917499+00:00","price_changed_at":"2026-10-12T05:37:43.468694+00:00"},
    {"id":241675153,"name":"Lewis Hamilton","probability":0.0,"american_odds":null,"rank":8,"rank_change_24h":null,"probability_change_24h":null,"opening_probability":0.105,"opening_american_odds":852,"is_winner":false,"resolution_source":"api_settlement","last_updated":"2026-10-11T17:44:12.917499+00:00","price_changed_at":"2026-10-12T05:37:43.468694+00:00"},
    {"id":241675154,"name":"Charles Leclerc","probability":0.0,"american_odds":null,"rank":11,"rank_change_24h":null,"probability_change_24h":null,"opening_probability":0.1,"opening_american_odds":900,"is_winner":false,"resolution_source":"api_settlement","last_updated":"2026-10-11T17:44:12.917499+00:00","price_changed_at":"2026-10-12T05:37:43.468694+00:00"},
    {"id":241675152,"name":"Kimi Antonelli","probability":0.0,"american_odds":null,"rank":15,"rank_change_24h":null,"probability_change_24h":null,"opening_probability":0.25,"opening_american_odds":300,"is_winner":false,"resolution_source":"api_settlement","last_updated":"2026-10-11T17:44:12.917499+00:00","price_changed_at":"2026-10-12T05:37:43.468694+00:00"}
    ],
    "outcome_count":23,
    "lead_outcome_id":null,
    "openings_withheld":false,
    "prices_withheld":0,
    "expired_rungs_dropped":0,
    "bookmakers":["polymarket"],
    "category_tags":["motorsports"],
    "created_at":"2026-10-03T12:15:51.012496+00:00",
    "updated_at":"2026-10-12T00:51:26.020311+00:00",
    "group_id":"polymarket:1123912",
    "canonical_market_key":null,
    "hook_description":null,
    "hook_withheld":false,
    "image_url":"https://images.pexels.com/photos/29309757/pexels-photo-29309757.jpeg?auto=compress&cs=tinysrgb&h=650&w=940",
    "event_concept_key":"event:f1:singapore-grand-prix-driver-winner",
    "hub_slug":null,
    "category_page":null,
    "sport_page_key":null,
    "container_of_event_id":null
    }
    """#

    /// `atlas-v6/raw/field-63989361.json` (sha256 6b447d4e…1748): outcomes of 23.
    static let podiumBefore = #"""
    {
    "id":63989361,
    "name":"Singapore Grand Prix: Driver Podium Finish",
    "description":null,
    "sport":null,
    "sport_name":null,
    "category":"championship",
    "llm_sport_category":"motorsports",
    "status":"open",
    "source":"polymarket",
    "external_id":"1123926",
    "market_type":"field",
    "mutually_exclusive":false,
    "commence_time":"2026-10-03T11:30:58+00:00",
    "resolution_date":"2026-10-18T12:00:00+00:00",
    "outcomes":[
    {"id":242933922,"name":"Max Verstappen","probability":0.81,"american_odds":-441,"rank":1,"rank_change_24h":null,"probability_change_24h":null,"opening_probability":0.62,"opening_american_odds":-163,"is_winner":null,"resolution_source":null,"last_updated":"2026-10-11T04:55:26.893131+00:00","price_changed_at":"2026-10-11T04:55:26.893131+00:00"},
    {"id":243467981,"name":"Charles Leclerc","probability":0.63,"american_odds":-167,"rank":2,"rank_change_24h":null,"probability_change_24h":null,"opening_probability":0.47,"opening_american_odds":113,"is_winner":null,"resolution_source":null,"last_updated":"2026-10-11T04:49:59.592455+00:00","price_changed_at":"2026-10-11T04:33:05.344973+00:00"},
    {"id":243467982,"name":"Lewis Hamilton","probability":0.6,"american_odds":-144,"rank":3,"rank_change_24h":null,"probability_change_24h":null,"opening_probability":0.44,"opening_american_odds":127,"is_winner":null,"resolution_source":null,"last_updated":"2026-10-11T04:55:35.729598+00:00","price_changed_at":"2026-10-11T04:55:35.729598+00:00"}
    ],
    "outcome_count":23,
    "lead_outcome_id":null,
    "openings_withheld":false,
    "prices_withheld":0,
    "expired_rungs_dropped":0,
    "bookmakers":["polymarket"],
    "category_tags":["motorsports"],
    "created_at":"2026-10-03T12:15:51.012496+00:00",
    "updated_at":"2026-10-11T04:07:53.654130+00:00",
    "group_id":"polymarket:1123926",
    "canonical_market_key":null,
    "hook_description":null,
    "hook_withheld":false,
    "image_url":"https://images.pexels.com/photos/29309757/pexels-photo-29309757.jpeg?auto=compress&cs=tinysrgb&h=650&w=940",
    "event_concept_key":null,
    "hub_slug":null,
    "category_page":null,
    "sport_page_key":null,
    "container_of_event_id":null
    }
    """#

    /// `racing-expectations-v74/raw/field-63989361.json` (sha256 861a74ef…ae08): outcomes [242025505, 242933922, 243467981, 243467982] of 23.
    static let podiumFinal = #"""
    {
    "id":63989361,
    "name":"Singapore Grand Prix: Driver Podium Finish",
    "description":null,
    "sport":null,
    "sport_name":null,
    "category":"championship",
    "llm_sport_category":"motorsports",
    "status":"resolved",
    "source":"polymarket",
    "external_id":"1123926",
    "market_type":"field",
    "mutually_exclusive":false,
    "commence_time":"2026-10-03T11:30:58+00:00",
    "resolution_date":"2026-10-18T12:00:00+00:00",
    "outcomes":[
    {"id":242025505,"name":"Kimi Antonelli","probability":1.0,"american_odds":null,"rank":1,"rank_change_24h":null,"probability_change_24h":null,"opening_probability":0.62,"opening_american_odds":-163,"is_winner":true,"resolution_source":"api_settlement","last_updated":"2026-10-11T18:23:37.404379+00:00","price_changed_at":"2026-10-12T05:37:43.468694+00:00"},
    {"id":242933922,"name":"Max Verstappen","probability":1.0,"american_odds":null,"rank":2,"rank_change_24h":null,"probability_change_24h":null,"opening_probability":0.62,"opening_american_odds":-163,"is_winner":true,"resolution_source":"api_settlement","last_updated":"2026-10-11T17:44:12.917499+00:00","price_changed_at":"2026-10-12T05:37:43.468694+00:00"},
    {"id":243467981,"name":"Charles Leclerc","probability":1.0,"american_odds":null,"rank":3,"rank_change_24h":null,"probability_change_24h":null,"opening_probability":0.47,"opening_american_odds":113,"is_winner":true,"resolution_source":"api_settlement","last_updated":"2026-10-11T17:44:12.917499+00:00","price_changed_at":"2026-10-12T05:37:43.468694+00:00"},
    {"id":243467982,"name":"Lewis Hamilton","probability":0.0,"american_odds":null,"rank":8,"rank_change_24h":null,"probability_change_24h":null,"opening_probability":0.44,"opening_american_odds":127,"is_winner":false,"resolution_source":"api_settlement","last_updated":"2026-10-11T17:44:12.917499+00:00","price_changed_at":"2026-10-12T05:37:43.468694+00:00"}
    ],
    "outcome_count":23,
    "lead_outcome_id":null,
    "openings_withheld":false,
    "prices_withheld":0,
    "expired_rungs_dropped":0,
    "bookmakers":["polymarket"],
    "category_tags":["motorsports"],
    "created_at":"2026-10-03T12:15:51.012496+00:00",
    "updated_at":"2026-10-11T17:44:12.917499+00:00",
    "group_id":"polymarket:1123926",
    "canonical_market_key":null,
    "hook_description":null,
    "hook_withheld":false,
    "image_url":"https://images.pexels.com/photos/29309757/pexels-photo-29309757.jpeg?auto=compress&cs=tinysrgb&h=650&w=940",
    "event_concept_key":null,
    "hub_slug":null,
    "category_page":null,
    "sport_page_key":null,
    "container_of_event_id":null
    }
    """#

    /// `racing-expectations-v74/raw/hockey-63539066-detail.json` (sha256 fe94cfa4…d807): outcomes [239380537, 239380538, 239380539, 239380540] of 9.
    static let ladderDetail = #"""
    {
    "id":63539066,
    "name":"Boston vs Minnesota: Total Goals",
    "description":null,
    "sport":"icehockey_nhl",
    "sport_name":"NHL",
    "category":"game_prop",
    "llm_sport_category":"hockey",
    "status":"resolved",
    "source":"kalshi",
    "external_id":"KXNHLTOTAL-26OCT03BOSMIN",
    "market_type":"quantity",
    "mutually_exclusive":false,
    "commence_time":"2026-10-04T00:00:00+00:00",
    "resolution_date":"2026-10-06T00:00:00+00:00",
    "outcomes":[
    {"id":239380537,"name":"Over 2.5 goals scored","probability":1.0,"american_odds":null,"rank":1,"rank_change_24h":null,"probability_change_24h":null,"opening_probability":0.96,"opening_american_odds":-2400,"is_winner":true,"resolution_source":"api_settlement","last_updated":"2026-10-04T02:51:05.580551+00:00","price_changed_at":"2026-10-04T02:51:05.580551+00:00"},
    {"id":239380538,"name":"Over 1.5 goals scored","probability":1.0,"american_odds":null,"rank":2,"rank_change_24h":null,"probability_change_24h":null,"opening_probability":0.95,"opening_american_odds":-1900,"is_winner":true,"resolution_source":"api_settlement","last_updated":"2026-10-04T02:51:05.366298+00:00","price_changed_at":"2026-10-04T02:51:05.366298+00:00"},
    {"id":239380540,"name":"Over 4.5 goals scored","probability":1.0,"american_odds":null,"rank":3,"rank_change_24h":null,"probability_change_24h":null,"opening_probability":0.75,"opening_american_odds":-300,"is_winner":true,"resolution_source":"api_settlement","last_updated":"2026-10-04T02:51:06.001508+00:00","price_changed_at":"2026-10-04T02:51:06.001508+00:00"},
    {"id":239380539,"name":"Over 3.5 goals scored","probability":1.0,"american_odds":null,"rank":4,"rank_change_24h":null,"probability_change_24h":null,"opening_probability":0.85,"opening_american_odds":-567,"is_winner":true,"resolution_source":"api_settlement","last_updated":"2026-10-04T02:51:05.783182+00:00","price_changed_at":"2026-10-04T02:51:05.783182+00:00"}
    ],
    "outcome_count":9,
    "lead_outcome_id":null,
    "openings_withheld":false,
    "prices_withheld":0,
    "expired_rungs_dropped":0,
    "bookmakers":["kalshi"],
    "category_tags":["game_prop","hockey"],
    "created_at":"2026-10-01T03:03:21.010252+00:00",
    "updated_at":"2026-10-04T02:51:06.780990+00:00",
    "group_id":"kalshi:KXNHLTOTAL-26OCT03BOSMIN",
    "canonical_market_key":"hockey::championship:2026",
    "hook_description":null,
    "hook_withheld":false,
    "image_url":null,
    "event_concept_key":null,
    "hub_slug":null,
    "category_page":null,
    "sport_page_key":"icehockey_nhl",
    "container_of_event_id":null
    }
    """#

    /// `racing-expectations-v74/raw/hockey-63539066-history.json` (sha256 8b80b083…935f): lines 239380538/543/537/540, points [0..5] + last 4 of 109.
    static let ladderHistory = #"""
    {
    "market_id":63539066,
    "market_name":"Boston vs Minnesota: Total Goals",
    "hours":336,
    "actual_hours":336,
    "outcomes":[
    {"outcome_id":239380538,"name":"Over 1.5 goals scored","history":[
    {"timestamp":"2026-10-01T03:03:04.721898+00:00","probability":0.95,"american_odds":null,"bookmaker":"consensus"},
    {"timestamp":"2026-10-01T03:37:07.957531+00:00","probability":0.97,"american_odds":null,"bookmaker":"consensus"},
    {"timestamp":"2026-10-01T04:41:22.673271+00:00","probability":0.98,"american_odds":null,"bookmaker":"consensus"},
    {"timestamp":"2026-10-01T05:06:09.660961+00:00","probability":0.98,"american_odds":null,"bookmaker":"consensus"},
    {"timestamp":"2026-10-01T05:34:41.569493+00:00","probability":0.98,"american_odds":null,"bookmaker":"consensus"},
    {"timestamp":"2026-10-01T06:20:00.064669+00:00","probability":0.98,"american_odds":null,"bookmaker":"consensus"},
    {"timestamp":"2026-10-04T02:38:43.350688+00:00","probability":0.995,"american_odds":null,"bookmaker":"consensus"},
    {"timestamp":"2026-10-04T02:42:43.402425+00:00","probability":0.995,"american_odds":null,"bookmaker":"consensus"},
    {"timestamp":"2026-10-04T02:46:43.395259+00:00","probability":0.995,"american_odds":null,"bookmaker":"consensus"},
    {"timestamp":"2026-10-06T00:00:00+00:00","probability":1.0,"american_odds":null,"bookmaker":"settlement"}
    ],"eliminated":false,"eliminated_at":null},
    {"outcome_id":239380543,"name":"Over 7.5 goals scored","history":[
    {"timestamp":"2026-10-01T03:03:04.721898+00:00","probability":0.245,"american_odds":null,"bookmaker":"consensus"},
    {"timestamp":"2026-10-01T03:37:07.957531+00:00","probability":0.245,"american_odds":null,"bookmaker":"consensus"},
    {"timestamp":"2026-10-01T04:41:22.673271+00:00","probability":0.245,"american_odds":null,"bookmaker":"consensus"},
    {"timestamp":"2026-10-01T05:06:09.660961+00:00","probability":0.245,"american_odds":null,"bookmaker":"consensus"},
    {"timestamp":"2026-10-01T05:34:41.569493+00:00","probability":0.245,"american_odds":null,"bookmaker":"consensus"},
    {"timestamp":"2026-10-01T06:20:00.064669+00:00","probability":0.245,"american_odds":null,"bookmaker":"consensus"},
    {"timestamp":"2026-10-04T02:38:43.350688+00:00","probability":0.065,"american_odds":null,"bookmaker":"consensus"},
    {"timestamp":"2026-10-04T02:42:43.402425+00:00","probability":0.01,"american_odds":null,"bookmaker":"consensus"},
    {"timestamp":"2026-10-04T02:46:43.395259+00:00","probability":0.02,"american_odds":null,"bookmaker":"consensus"},
    {"timestamp":"2026-10-06T00:00:00+00:00","probability":0.0,"american_odds":null,"bookmaker":"settlement"}
    ],"eliminated":false,"eliminated_at":null},
    {"outcome_id":239380537,"name":"Over 2.5 goals scored","history":[
    {"timestamp":"2026-10-01T03:03:04.721898+00:00","probability":0.96,"american_odds":null,"bookmaker":"consensus"},
    {"timestamp":"2026-10-01T03:37:07.957531+00:00","probability":0.955,"american_odds":null,"bookmaker":"consensus"},
    {"timestamp":"2026-10-01T04:41:22.673271+00:00","probability":0.96,"american_odds":null,"bookmaker":"consensus"},
    {"timestamp":"2026-10-01T05:06:09.660961+00:00","probability":0.96,"american_odds":null,"bookmaker":"consensus"},
    {"timestamp":"2026-10-01T05:34:41.569493+00:00","probability":0.96,"american_odds":null,"bookmaker":"consensus"},
    {"timestamp":"2026-10-01T06:20:00.064669+00:00","probability":0.96,"american_odds":null,"bookmaker":"consensus"},
    {"timestamp":"2026-10-04T02:38:43.350688+00:00","probability":0.995,"american_odds":null,"bookmaker":"consensus"},
    {"timestamp":"2026-10-04T02:42:43.402425+00:00","probability":0.995,"american_odds":null,"bookmaker":"consensus"},
    {"timestamp":"2026-10-04T02:46:43.395259+00:00","probability":0.995,"american_odds":null,"bookmaker":"consensus"},
    {"timestamp":"2026-10-06T00:00:00+00:00","probability":1.0,"american_odds":null,"bookmaker":"settlement"}
    ],"eliminated":false,"eliminated_at":null},
    {"outcome_id":239380540,"name":"Over 4.5 goals scored","history":[
    {"timestamp":"2026-10-01T03:03:04.721898+00:00","probability":0.75,"american_odds":null,"bookmaker":"consensus"},
    {"timestamp":"2026-10-01T03:37:07.957531+00:00","probability":0.75,"american_odds":null,"bookmaker":"consensus"},
    {"timestamp":"2026-10-01T04:41:22.673271+00:00","probability":0.765,"american_odds":null,"bookmaker":"consensus"},
    {"timestamp":"2026-10-01T05:06:09.660961+00:00","probability":0.76,"american_odds":null,"bookmaker":"consensus"},
    {"timestamp":"2026-10-01T05:34:41.569493+00:00","probability":0.76,"american_odds":null,"bookmaker":"consensus"},
    {"timestamp":"2026-10-01T06:20:00.064669+00:00","probability":0.76,"american_odds":null,"bookmaker":"consensus"},
    {"timestamp":"2026-10-04T02:38:43.350688+00:00","probability":0.765,"american_odds":null,"bookmaker":"consensus"},
    {"timestamp":"2026-10-04T02:42:43.402425+00:00","probability":0.67,"american_odds":null,"bookmaker":"consensus"},
    {"timestamp":"2026-10-04T02:46:43.395259+00:00","probability":0.995,"american_odds":null,"bookmaker":"consensus"},
    {"timestamp":"2026-10-06T00:00:00+00:00","probability":1.0,"american_odds":null,"bookmaker":"settlement"}
    ],"eliminated":false,"eliminated_at":null}
    ],
    "total_data_points":972,
    "coverage_start":"2026-10-01T03:03:04.721898+00:00",
    "coverage_end":"2026-10-06T00:00:00+00:00",
    "coverage_hours":116.95,
    "observation_times":109
    }
    """#
    /// The decoder `APIClient` uses.
    static func decoder() -> JSONDecoder {
        let decoder = JSONDecoder()
        decoder.keyDecodingStrategy = .convertFromSnakeCase
        return decoder
    }

    static func market(_ json: String) throws -> FuturesMarketDetail {
        try decoder().decode(FuturesMarketDetail.self, from: Data(json.utf8))
    }

    static func history(_ json: String) throws -> FuturesHistoryResponse {
        try decoder().decode(FuturesHistoryResponse.self, from: Data(json.utf8))
    }

    /// A CONSTRUCTED variant: exactly one served substring replaced, and the
    /// replacement proven to have happened once.
    static func replacing(_ json: String, _ served: String, with constructed: String) -> String {
        precondition(json.components(separatedBy: served).count == 2, "not exactly one: \(served)")
        return json.replacingOccurrences(of: served, with: constructed)
    }

    static let pacific: Calendar = {
        var calendar = Calendar(identifier: .gregorian)
        calendar.timeZone = TimeZone(identifier: "America/Los_Angeles")!
        return calendar
    }()

    /// The reader's clock and calendar (CONSTRUCTED: Pacific, en_US).
    static func host(_ now: String, cohort: [Int]? = nil) -> RacingFieldPageAdapter10868.Host {
        RacingFieldPageAdapter10868.Host(now: now.asDate!, calendar: pacific, locale: Locale(identifier: "en_US"),
                                         cohort: cohort)
    }

    /// The winner body's capture instant, the reader's "now" before the race.
    static let beforeCapture = "2026-10-11T05:07:16Z"
    /// The final bodies' capture instant.
    static let finalCapture = "2026-10-12T07:47:00Z"
    /// Every kept winner outcome's served `last_updated` before the race.
    static let beforeStamp = "2026-10-11T04:07:53.654130+00:00"

    static let verstappen = 241675151
    static let hamilton = 241675153
    static let leclerc = 241675154
    static let antonelli = 241675152
}

@MainActor
final class RacingFieldPageAdapter10868Tests: XCTestCase {
    private typealias A = RacingFieldPageAdapter10868
    private typealias F = RacingAdapterFixtures10868

    private func clock(_ iso: String, _ host: A.Host) -> String {
        A.clockWords(iso.asDate!, host: host)
    }

    private func figures(_ input: FieldHeadlineInput10868) -> [[String?]] {
        FieldHeadlineModel10868(input).competitors.map { $0.metrics.map(FieldChaseModel10868.figure) }
    }

    private func words(_ input: FieldHeadlineInput10868) -> [[String?]] {
        FieldHeadlineModel10868(input).competitors.map { $0.metrics.map(FieldChaseModel10868.words) }
    }

    // MARK: Phase

    func testAnOpenRaceMarketIsBeforeAndOnlyAResolvedOneIsFinal() throws {
        XCTAssertEqual(A.phase(try F.market(F.winnerBefore)), .before)
        XCTAssertEqual(A.phase(try F.market(F.winnerFinal)), .final)
        // Nothing in a futures body says a race started: an open board stays before.
        XCTAssertEqual(A.phase(try F.market(F.podiumBefore)), .before)
    }

    // MARK: Before — each driver's own recent price

    func testEachDisplayedDriverShowsItsOwnRecentPriceWithItsOwnClock() throws {
        let market = try F.market(F.winnerBefore)
        let host = F.host(F.beforeCapture)
        let input = A.headline(market, host: host)
        XCTAssertEqual(input.phase, .before)
        XCTAssertEqual(input.scope, "racing:63989371:before:field")
        // The production chart's default selection: the first three served outcomes.
        XCTAssertEqual(input.displayed.map(\.name), ["Max Verstappen", "Lewis Hamilton", "Charles Leclerc"])
        XCTAssertEqual(input.displayed.map(\.ref.outcomeID), ["241675151", "241675153", "241675154"])
        XCTAssertEqual(Set(input.displayed.map(\.ref.marketID)), ["63989371"])
        XCTAssertEqual(Set(input.displayed.map(\.ref.source)), ["polymarket"])
        XCTAssertEqual(input.displayed.map(\.keyShape), [.circle, .diamond, .square])
        XCTAssertEqual(input.displayed.map(\.compactName), [nil, nil, nil])
        XCTAssertEqual(figures(input), [["62%"], ["14%"], ["13%"]])

        let detail = "\(clock(F.beforeStamp, host)) · Polymarket"
        let verstappen = try XCTUnwrap(input.catalogue.first { $0.ref.outcomeID == "241675151" })
        XCTAssertEqual(verstappen.plan, .single(FieldChooserReading10868(
            label: "Win chance", value: .recorded(text: "62%", detail: detail))))
        // Each raw price is its own: never normalized, summed or complemented.
        XCTAssertEqual(input.pairs.compactMap { $0.before?.probability }, [0.6162, 0.1364, 0.127])
        XCTAssertNil(input.pairs.first?.later)
        XCTAssertEqual(input.finishes, [])
        XCTAssertNil(input.state)
    }

    func testEveryServedOutcomeIsInTheCatalogueOnceInServedOrder() throws {
        let market = try F.market(F.winnerBefore)
        let input = A.headline(market, host: F.host(F.beforeCapture))
        XCTAssertEqual(input.catalogue.map(\.name), ["Max Verstappen", "Lewis Hamilton", "Charles Leclerc", "Kimi Antonelli"])
        XCTAssertEqual(Set(input.catalogue.map(\.ref)).count, 4)
        // Only displayed drivers carry a chart colour.
        XCTAssertNil(input.catalogue[3].accent)
        XCTAssertNotNil(input.catalogue[0].accent)
        XCTAssertEqual(input.catalogue.map(\.result), [nil, nil, nil, nil])
    }

    func testAPriceOlderThanTheFuturesBoundIsNeverTheCurrentChance() throws {
        let market = try F.market(F.winnerBefore)
        // CONSTRUCTED reader clock: 6 h 22 m after every kept price was last written.
        let late = A.headline(market, host: F.host("2026-10-11T10:30:00Z"))
        XCTAssertEqual(figures(late), [[nil], [nil], [nil]])
        let stale: [String?] = [AllMarketsCatalogView9483.noRecentPrice]
        XCTAssertEqual(words(late).first, stale)
        XCTAssertEqual(late.pairs.compactMap(\.before).count, 0)
        // One second inside the bound is still recent; one second past it is not.
        let written = F.beforeStamp.asDate!
        let inside = A.Host(now: written.addingTimeInterval(SourceAge.futuresStaleAfter - 1),
                            calendar: F.pacific, locale: Locale(identifier: "en_US"))
        let past = A.Host(now: written.addingTimeInterval(SourceAge.futuresStaleAfter + 1),
                          calendar: F.pacific, locale: Locale(identifier: "en_US"))
        XCTAssertEqual(figures(A.headline(market, host: inside)).first, ["62%"])
        XCTAssertEqual(figures(A.headline(market, host: past)).first, [nil])
    }

    func testTheHostsHeldCohortIsKeptInItsOrderOnceEach() throws {
        let market = try F.market(F.winnerBefore)
        // CONSTRUCTED held cohort: a repeat and an id the market does not serve.
        let input = A.headline(market, host: F.host(F.beforeCapture, cohort: [F.leclerc, F.verstappen, F.leclerc, 999]))
        XCTAssertEqual(input.displayed.map(\.name), ["Charles Leclerc", "Max Verstappen"])
        XCTAssertEqual(input.displayed.map(\.keyShape), [.circle, .diamond])
        XCTAssertEqual(figures(input), [["13%"], ["62%"]])
    }

    // MARK: Final — a settled price is a result

    func testAtTheFinalASettledPriceIsAResultNeverAChance() throws {
        let market = try F.market(F.winnerFinal)
        let host = F.host(F.finalCapture, cohort: [F.verstappen, F.leclerc, F.hamilton])
        let input = A.headline(market, host: host)
        XCTAssertEqual(input.phase, .final)
        XCTAssertEqual(input.scope, "racing:63989371:final:field")
        XCTAssertEqual(figures(input), [[nil, nil], [nil, nil], [nil, nil]])
        let absent: [[String?]] = Array(repeating: ["Pre-race chance unavailable", "Finish unavailable"], count: 3)
        XCTAssertEqual(words(input), absent)
        // The served 1.0 / 0.0 never becomes a figure anywhere in the catalogue.
        for original in input.catalogue {
            if case .recorded = FieldOutlookModel10868.beforeReading(original.plan).value {
                XCTFail("\(original.name) shows a settled price as a chance")
            }
        }
        let results = Dictionary(uniqueKeysWithValues: input.catalogue.map { ($0.name, $0.result?.words) })
        XCTAssertEqual(results["Max Verstappen"], "Won")
        XCTAssertEqual(results["Charles Leclerc"], "Lost")
        XCTAssertEqual(results["Lewis Hamilton"], "Lost")
        XCTAssertEqual(input.catalogue.first?.result?.title, "Prop result")
        XCTAssertEqual(input.pairs.compactMap(\.before).count, 0)
    }

    func testAnUntiedHeadlineSlotSaysTheChanceIsUnavailableNeverThatItWasNotRecorded() throws {
        // The shared headline puts `beforeUnavailable` in place of a slot that has no tied reading; the
        // readings may exist (the history beside it can show them), so the words say unavailable.
        let before = A.headlineCopy(try F.market(F.winnerBefore), phase: .before)
        let final = A.headlineCopy(try F.market(F.winnerFinal), phase: .final)
        XCTAssertEqual(before.beforeUnavailable, "Win chance unavailable")
        XCTAssertEqual(final.beforeUnavailable, "Pre-race chance unavailable")
    }

    func testTheRaceKeysAreNeutralRecordedNeverAQualifiedPreRaceBaseline() throws {
        // No race start reaches the app: the keys are neutral and recorded in every phase (Design 2026-10-31).
        let before = A.headline(try F.market(F.winnerBefore), host: F.host(F.beforeStamp))
        let final = A.headline(try F.market(F.winnerFinal), host: F.host(F.finalCapture))
        XCTAssertEqual(before.phase, .before)
        XCTAssertEqual(before.keyTreatment, .neutralRecorded)
        XCTAssertFalse(FieldHeadlineModel10868(before).keyIsHollow)
        XCTAssertEqual(final.keyTreatment, .neutralRecorded)
        XCTAssertFalse(FieldHeadlineModel10868(final).keyIsHollow)
        XCTAssertEqual(before.copy.eyebrow?.hasSuffix("Recorded probabilities"), true)
    }

    func testWithoutAHeldCohortTheFinalShowsTheServedOrder() throws {
        // A known gap, pinned: after settlement the served order follows the
        // settled prices, so a meaningful final cohort is the host's to hold.
        let input = A.headline(try F.market(F.winnerFinal), host: F.host(F.finalCapture))
        XCTAssertEqual(input.displayed.map(\.name), ["Max Verstappen", "Arvid Lindblad", "Yuki Tsunoda"])
    }

    // MARK: Copy

    func testTheWordsNeverSayPreRaceBeforeTheMarketSettles() throws {
        let market = try F.market(F.winnerBefore)
        let input = A.headline(market, host: F.host(F.beforeCapture))
        XCTAssertEqual(input.copy.eyebrow, "Motorsports · Recorded probabilities")
        XCTAssertEqual(input.copy.title, "Singapore Grand Prix: Driver Winner")
        XCTAssertEqual(input.copy.beforeLabel, "Win chance")
        XCTAssertEqual(Set(input.catalogue.map { FieldOutlookModel10868.beforeReading($0.plan).label }), ["Win chance"])
        let compact = A.headline(market, host: F.host(F.beforeCapture), compact: true)
        XCTAssertNil(compact.copy.eyebrow)
        XCTAssertNil(compact.copy.title)
    }

    func testTheReaderHeadingAndAboutSayWhatIsUnavailable() throws {
        let before = try F.market(F.winnerBefore)
        XCTAssertEqual(A.readerHeader(before), RacingEventPageReaderHeader10868(
            title: "Singapore Grand Prix: Driver Winner", state: "Race progress unavailable"))
        let about = A.raceAbout(before)
        XCTAssertEqual(about.title, "How this race is recorded")
        XCTAssertEqual(about.paragraphs.count, 3)
        XCTAssertTrue(about.paragraphs[0].contains("own Polymarket price"))
        XCTAssertTrue(about.paragraphs[0].contains("not adjusted to add up to 100%"))
        XCTAssertTrue(about.paragraphs[2].contains("last 6 hours"))
        let final = A.raceAbout(try F.market(F.winnerFinal))
        XCTAssertEqual(final.paragraphs.count, 4)
        XCTAssertTrue(final.paragraphs[3].hasPrefix("Results come only from Polymarket's settlement"))
    }
}
