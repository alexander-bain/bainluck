import CryptoKit
import XCTest
@testable import Bain_Luck

/// #10868 — the retained golf futures bodies every golf adapter test decodes,
/// exactly as the app decodes them (`APIClient`: `JSONDecoder` with
/// `.convertFromSnakeCase`, no date strategy), into the production models
/// `FuturesMarketDetail` (`/api/futures/{id}`) and `FuturesHistoryResponse`
/// (`/api/futures/{id}/history`).
///
/// PREPARED, NOT RUN: written under a source-only hold (no build, no XCTest).
///
/// RETAINED bodies, all under `artifacts/discovery-containers-release-plan/
/// event-page-design-20261011/additional-match-v146/raw/`. Each constant is a
/// REDUCED VERBATIM SUBSET of its source: every top-level key in source order
/// with its source value, except the arrays named on its "Kept" line, which keep
/// only the listed 0-based elements, in source order, each parsed-equal to the
/// source element. For the compact server bodies (`64266833*.json`,
/// `winner-history.json`) each kept element is also a verbatim substring of the
/// source file. The `market-*.json` captures were pretty-printed by the capture
/// tool; their values are unchanged and the whitespace is compacted. Generated
/// and checked by `/tmp/cli-10868-golf/make_subsets.py` (kept outside the repo).
///
/// What the bodies are:
/// - Baycurrent Classic (DataGolf, PGA 527), Oct 8–11, 2026: the Winner market
///   (`status: resolved`, served with NO grade on any row) and its history. Every
///   golfer's served line ends on a 22:08:55Z row that re-serves the Oct 6
///   pre-tournament price after play (Brennan 1.0 at 06:41:26Z, then 0.026017).
/// - DP World India Championship (DataGolf, Euro 2026140), listed Oct 15–18,
///   captured Oct 12 before the start: the Winner, Top 5, Top 10, Top 20 and Make
///   the Cut markets (`status: open`). Alex Noren is served with no price in each
///   (an untimed `opening_probability` beside it); Shubham Jaglan's Winner price
///   is a real 0. Rory McIlroy's five outcome ids are 246352440 / 246352498 /
///   246352556 / 246352614 / 246352672, the same ids Design's retained five-finish
///   packet (`GOLF-OUTLOOK-FIVE-FINISH-RETAINED-CASES.json`) carries.
///
/// What a subset changes: left-out points are absent, so the futures chart's
/// per-series break rule (six median gaps, two hours minimum, none under four
/// points) is measured on the subset's own intervals. The tests assert the runs
/// OF THE SUBSET.
///
/// Main-actor isolated, like the test classes that read it: the app target's
/// default isolation makes the adapters' `Host` main-actor isolated.
@MainActor
enum GolfFieldRetainedBodies10868 {
    /// `64266833.json` (/api/futures/64266833, captured 2026-10-12T23:55:17Z); source sha256 74e163a4e7d585ba0fd3ceb8a2eec5be0ea0022c93fe8882982d9e35884bcbdc, 55,191 bytes.
    /// Kept: outcomes [0, 1, 2, 11, 12, 24, 72] of 155. Embedded sha256 c8d1040e95ba516fa71792ae9b63b9b6a03a74ae1a19c77e4dea69045e1cafa3.
    static let baycurrentWinner = #"{"id":64266833,"name":"Baycurrent Classic - Winner","description":null,"sport":null,"sport_name":null,"category":"championship","llm_sport_category":"golf","status":"resolved","source":"datagolf","external_id":"datagolf:pga:527:win","market_type":"field","mutually_exclusive":true,"commence_time":"2026-10-08T00:00:00+00:00","resolution_date":"2026-10-11T00:00:00+00:00","outcomes":[{"id":242242520,"name":"Xander Schauffele","probability":0.086583,"american_odds":null,"rank":1,"rank_change_24h":null,"probability_change_24h":null,"opening_probability":0.089,"opening_american_odds":null,"is_winner":null,"resolution_source":null,"last_updated":"2026-10-11T23:41:24.647652+00:00","price_changed_at":"2026-10-11T22:08:55.646035+00:00"},{"id":242242522,"name":"Wyndham Clark","probability":0.053967,"american_odds":null,"rank":2,"rank_change_24h":null,"probability_change_24h":null,"opening_probability":0.053783,"opening_american_odds":null,"is_winner":null,"resolution_source":null,"last_updated":"2026-10-11T23:41:24.647652+00:00","price_changed_at":"2026-10-11T22:08:55.646035+00:00"},{"id":242242527,"name":"Collin Morikawa","probability":0.04975,"american_odds":null,"rank":3,"rank_change_24h":null,"probability_change_24h":null,"opening_probability":0.048933,"opening_american_odds":null,"is_winner":null,"resolution_source":null,"last_updated":"2026-10-11T23:41:24.647652+00:00","price_changed_at":"2026-10-11T22:08:55.646035+00:00"},{"id":241857512,"name":"Michael Brennan","probability":0.026017,"american_odds":null,"rank":12,"rank_change_24h":null,"probability_change_24h":null,"opening_probability":0.043067,"opening_american_odds":null,"is_winner":null,"resolution_source":null,"last_updated":"2026-10-11T23:41:24.647652+00:00","price_changed_at":"2026-10-11T22:08:55.646035+00:00"},{"id":242242545,"name":"Michael Thorbjornsen","probability":0.025133,"american_odds":null,"rank":13,"rank_change_24h":null,"probability_change_24h":null,"opening_probability":0.02525,"opening_american_odds":null,"is_winner":null,"resolution_source":null,"last_updated":"2026-10-11T23:41:24.647652+00:00","price_changed_at":"2026-10-11T22:08:55.646035+00:00"},{"id":242242559,"name":"Keith Mitchell","probability":0.012733,"american_odds":null,"rank":25,"rank_change_24h":null,"probability_change_24h":null,"opening_probability":0.012467,"opening_american_odds":null,"is_winner":null,"resolution_source":null,"last_updated":"2026-10-11T23:41:24.647652+00:00","price_changed_at":"2026-10-11T22:08:55.646035+00:00"},{"id":241857553,"name":"Patrick Fishburn","probability":null,"american_odds":null,"rank":73,"rank_change_24h":null,"probability_change_24h":null,"opening_probability":0.008083,"opening_american_odds":null,"is_winner":null,"resolution_source":null,"last_updated":"2026-10-05T17:39:14.507306+00:00","price_changed_at":"2026-10-05T17:39:14.330500+00:00"}],"outcome_count":155,"lead_outcome_id":null,"openings_withheld":false,"prices_withheld":0,"expired_rungs_dropped":0,"bookmakers":["datagolf_model"],"category_tags":[],"created_at":"2026-10-05T01:07:07.475740+00:00","updated_at":"2026-10-11T21:35:25.875468+00:00","group_id":null,"canonical_market_key":null,"hook_description":null,"hook_withheld":false,"image_url":null,"event_concept_key":null,"edition_year":null,"hub_slug":"golf","category_page":null,"sport_page_key":null,"container_of_event_id":null}"#

    /// `64266833-history.json` (/api/futures/64266833/history?hours=336&top_n=10, captured 2026-10-12T23:55:18Z); source sha256 2f12c258c1d345b4a0773d14930d21e99c2918c251d49c9c59d076c947eb0152, 309,774 bytes.
    /// Kept: outcome 5 (Wyndham Clark) points [0, 1, 2, 3, 4, 5, 6, 7, 160, 161, 162] of 163; outcome 8 (Xander Schauffele) points [0, 1, 2, 3, 4, 5, 6, 7, 318, 319, 320] of 321; outcome 9 (Collin Morikawa) points [0, 1, 2, 3, 4, 5, 6, 7, 207, 208, 209] of 210; leaderboard [0, 1] of 72. Embedded sha256 32d0ec5482d526621c74bb8b7f56ef8d16fd16163d689cfe59db1b2a275a0739.
    static let baycurrentHistory = #"{"market_id":64266833,"market_name":"Baycurrent Classic - Winner","hours":336,"actual_hours":336,"outcomes":[{"outcome_id":242242522,"name":"Wyndham Clark","history":[{"timestamp":"2026-10-05T17:39:14.507306+00:00","probability":0.053783,"american_odds":null,"bookmaker":"consensus"},{"timestamp":"2026-10-06T13:08:40.644152+00:00","probability":0.053967,"american_odds":null,"bookmaker":"consensus"},{"timestamp":"2026-10-08T00:02:03.231914+00:00","probability":0.052477,"american_odds":null,"bookmaker":"consensus"},{"timestamp":"2026-10-08T00:06:33.172825+00:00","probability":0.055269,"american_odds":null,"bookmaker":"consensus"},{"timestamp":"2026-10-08T00:11:13.058928+00:00","probability":0.053125,"american_odds":null,"bookmaker":"consensus"},{"timestamp":"2026-10-08T00:16:55.542752+00:00","probability":0.054196,"american_odds":null,"bookmaker":"consensus"},{"timestamp":"2026-10-08T00:27:33.145591+00:00","probability":0.057036,"american_odds":null,"bookmaker":"consensus"},{"timestamp":"2026-10-08T00:32:03.148937+00:00","probability":0.054589,"american_odds":null,"bookmaker":"consensus"},{"timestamp":"2026-10-10T02:01:32.388551+00:00","probability":0.00014,"american_odds":null,"bookmaker":"consensus"},{"timestamp":"2026-10-10T02:27:02.431908+00:00","probability":0.0,"american_odds":null,"bookmaker":"consensus"},{"timestamp":"2026-10-11T22:08:55.891004+00:00","probability":0.053967,"american_odds":null,"bookmaker":"consensus"}],"eliminated":false,"eliminated_at":null},{"outcome_id":242242520,"name":"Xander Schauffele","history":[{"timestamp":"2026-10-05T17:39:14.507306+00:00","probability":0.089,"american_odds":null,"bookmaker":"consensus"},{"timestamp":"2026-10-06T13:08:40.644152+00:00","probability":0.086583,"american_odds":null,"bookmaker":"consensus"},{"timestamp":"2026-10-08T00:02:03.231914+00:00","probability":0.084473,"american_odds":null,"bookmaker":"consensus"},{"timestamp":"2026-10-08T00:06:33.172825+00:00","probability":0.090287,"american_odds":null,"bookmaker":"consensus"},{"timestamp":"2026-10-08T00:11:13.058928+00:00","probability":0.087947,"american_odds":null,"bookmaker":"consensus"},{"timestamp":"2026-10-08T00:16:55.542752+00:00","probability":0.089341,"american_odds":null,"bookmaker":"consensus"},{"timestamp":"2026-10-08T00:23:03.133505+00:00","probability":0.087687,"american_odds":null,"bookmaker":"consensus"},{"timestamp":"2026-10-08T00:27:33.145591+00:00","probability":0.090256,"american_odds":null,"bookmaker":"consensus"},{"timestamp":"2026-10-11T06:02:25.916250+00:00","probability":0.095147,"american_odds":null,"bookmaker":"consensus"},{"timestamp":"2026-10-11T06:06:55.965994+00:00","probability":0.0,"american_odds":null,"bookmaker":"consensus"},{"timestamp":"2026-10-11T22:08:55.891004+00:00","probability":0.086583,"american_odds":null,"bookmaker":"consensus"}],"eliminated":false,"eliminated_at":null},{"outcome_id":242242527,"name":"Collin Morikawa","history":[{"timestamp":"2026-10-05T17:39:14.507306+00:00","probability":0.048933,"american_odds":null,"bookmaker":"consensus"},{"timestamp":"2026-10-06T13:08:40.644152+00:00","probability":0.04975,"american_odds":null,"bookmaker":"consensus"},{"timestamp":"2026-10-08T00:02:03.231914+00:00","probability":0.050024,"american_odds":null,"bookmaker":"consensus"},{"timestamp":"2026-10-08T00:11:13.058928+00:00","probability":0.047803,"american_odds":null,"bookmaker":"consensus"},{"timestamp":"2026-10-08T00:16:55.542752+00:00","probability":0.050429,"american_odds":null,"bookmaker":"consensus"},{"timestamp":"2026-10-08T00:23:03.133505+00:00","probability":0.051017,"american_odds":null,"bookmaker":"consensus"},{"timestamp":"2026-10-08T00:27:33.145591+00:00","probability":0.05025,"american_odds":null,"bookmaker":"consensus"},{"timestamp":"2026-10-08T00:36:33.267676+00:00","probability":0.05207,"american_odds":null,"bookmaker":"consensus"},{"timestamp":"2026-10-10T06:52:32.921891+00:00","probability":0.00014,"american_odds":null,"bookmaker":"consensus"},{"timestamp":"2026-10-10T06:57:03.118947+00:00","probability":0.0,"american_odds":null,"bookmaker":"consensus"},{"timestamp":"2026-10-11T22:08:55.891004+00:00","probability":0.04975,"american_odds":null,"bookmaker":"consensus"}],"eliminated":false,"eliminated_at":null}],"round_boundaries":[{"timestamp":"2026-10-08T00:02:03.231914+00:00","label":"R1"},{"timestamp":"2026-10-09T00:02:01.806162+00:00","label":"R2"},{"timestamp":"2026-10-10T00:01:32.121700+00:00","label":"R3"},{"timestamp":"2026-10-11T00:02:37.532470+00:00","label":"R4"}],"leaderboard":[{"name":"Michael Brennan","thru":"18","dg_id":29197,"position":"1","today_score":-3,"total_score":-16,"current_round":4},{"name":"Jackson Suber","thru":"18","dg_id":29279,"position":"T41","today_score":-1,"total_score":-5,"current_round":4}],"total_data_points":2564,"coverage_start":"2026-10-05T01:08:38.821032+00:00","coverage_end":"2026-10-11T22:08:55.891004+00:00","coverage_hours":165.0,"observation_times":341}"#

    /// `winner-history.json` (/api/futures/64266833/history?hours=336&outcome_id=241857512, captured 2026-10-12T23:56:42Z); source sha256 2acb56af0fb6efbf5f5b3670718f27b656e1dea15f7ac5677173bbb49770de9e, 48,472 bytes.
    /// Kept: outcome 0 (Michael Brennan) points [0, 1, 2, 3, 4, 5, 6, 7, 331, 332, 333, 334] of 335; leaderboard [0, 1] of 72. Embedded sha256 711ae778c8d93ed0c3e2308eef74cee8ee4373662d43f920e7280524d80dfdc9.
    static let brennanHistory = #"{"market_id":64266833,"market_name":"Baycurrent Classic - Winner","hours":336,"actual_hours":336,"outcomes":[{"outcome_id":241857512,"name":"Michael Brennan","history":[{"timestamp":"2026-10-05T01:08:38.821032+00:00","probability":0.043067,"american_odds":null,"bookmaker":"consensus"},{"timestamp":"2026-10-05T17:39:14.507306+00:00","probability":0.026167,"american_odds":null,"bookmaker":"consensus"},{"timestamp":"2026-10-06T13:08:40.644152+00:00","probability":0.026017,"american_odds":null,"bookmaker":"consensus"},{"timestamp":"2026-10-08T00:02:03.231914+00:00","probability":0.024326,"american_odds":null,"bookmaker":"consensus"},{"timestamp":"2026-10-08T00:11:13.058928+00:00","probability":0.026065,"american_odds":null,"bookmaker":"consensus"},{"timestamp":"2026-10-08T00:16:55.542752+00:00","probability":0.025622,"american_odds":null,"bookmaker":"consensus"},{"timestamp":"2026-10-08T00:23:03.133505+00:00","probability":0.014292,"american_odds":null,"bookmaker":"consensus"},{"timestamp":"2026-10-08T00:27:33.145591+00:00","probability":0.015469,"american_odds":null,"bookmaker":"consensus"},{"timestamp":"2026-10-11T06:32:25.936365+00:00","probability":0.746772,"american_odds":null,"bookmaker":"consensus"},{"timestamp":"2026-10-11T06:36:56.060523+00:00","probability":0.74375,"american_odds":null,"bookmaker":"consensus"},{"timestamp":"2026-10-11T06:41:26.165769+00:00","probability":1.0,"american_odds":null,"bookmaker":"consensus"},{"timestamp":"2026-10-11T22:08:55.891004+00:00","probability":0.026017,"american_odds":null,"bookmaker":"consensus"}],"eliminated":false,"eliminated_at":null}],"round_boundaries":[{"timestamp":"2026-10-08T00:02:03.231914+00:00","label":"R1"},{"timestamp":"2026-10-09T00:02:01.806162+00:00","label":"R2"},{"timestamp":"2026-10-10T00:01:32.121700+00:00","label":"R3"},{"timestamp":"2026-10-11T00:02:37.532470+00:00","label":"R4"}],"leaderboard":[{"name":"Michael Brennan","thru":"18","dg_id":29197,"position":"1","today_score":-3,"total_score":-16,"current_round":4},{"name":"Jackson Suber","thru":"18","dg_id":29279,"position":"T41","today_score":-1,"total_score":-5,"current_round":4}],"total_data_points":335,"coverage_start":"2026-10-05T01:08:38.821032+00:00","coverage_end":"2026-10-11T22:08:55.891004+00:00","coverage_hours":165.0,"observation_times":335}"#

    /// `market-65391342.json` (/api/futures/65391342, captured 2026-10-12T23:28:52Z); source sha256 580b4fa8b32d644f2ec16a12f4f7ca16439e6793e431becf8ae7676fa99ec3d1, 89,160 bytes.
    /// Kept: outcomes [0, 114, 142, 144] of 190. Embedded sha256 19a801ec43076d4be148884e8bb5d6601b0464f079d0fe3e7bdaa741e3b8368b.
    static let indiaWin = #"{"id":65391342,"name":"DP World India Championship - Winner","description":null,"sport":null,"sport_name":null,"category":"championship","llm_sport_category":"golf","status":"open","source":"datagolf","external_id":"datagolf:euro:2026140:win","market_type":"field","mutually_exclusive":true,"commence_time":"2026-10-15T00:00:00+00:00","resolution_date":"2026-10-18T00:00:00+00:00","outcomes":[{"id":246352440,"name":"Rory McIlroy","probability":0.1271,"american_odds":null,"rank":1,"rank_change_24h":null,"probability_change_24h":null,"opening_probability":0.1271,"opening_american_odds":null,"is_winner":null,"resolution_source":null,"last_updated":"2026-10-12T23:11:05.501054+00:00","price_changed_at":null},{"id":246352472,"name":"Shubhankar Sharma","probability":0.000383,"american_odds":null,"rank":115,"rank_change_24h":null,"probability_change_24h":null,"opening_probability":0.000383,"opening_american_odds":null,"is_winner":null,"resolution_source":null,"last_updated":"2026-10-12T23:11:05.501054+00:00","price_changed_at":null},{"id":246352496,"name":"Shubham Jaglan","probability":0.0,"american_odds":null,"rank":143,"rank_change_24h":null,"probability_change_24h":null,"opening_probability":null,"opening_american_odds":null,"is_winner":null,"resolution_source":null,"last_updated":"2026-10-12T23:11:05.501054+00:00","price_changed_at":null},{"id":245904632,"name":"Alex Noren","probability":null,"american_odds":null,"rank":145,"rank_change_24h":null,"probability_change_24h":null,"opening_probability":0.0283,"opening_american_odds":null,"is_winner":null,"resolution_source":null,"last_updated":"2026-10-12T19:09:44.432467+00:00","price_changed_at":"2026-10-12T19:09:40.403188+00:00"}],"outcome_count":190,"lead_outcome_id":null,"openings_withheld":false,"prices_withheld":0,"expired_rungs_dropped":0,"bookmakers":["datagolf_model"],"category_tags":[],"created_at":"2026-10-11T21:37:10.727631+00:00","updated_at":"2026-10-12T00:08:37.971814+00:00","group_id":null,"canonical_market_key":null,"hook_description":null,"hook_withheld":false,"image_url":null,"event_concept_key":null,"edition_year":null,"hub_slug":"golf","category_page":null,"sport_page_key":null,"container_of_event_id":null}"#

    /// `market-65391343.json` (/api/futures/65391343, captured 2026-10-12T23:28:33Z); source sha256 4860ab13ce7c869d91a10db3d7fd393d04849a26b3e9c055bc962c315e3c6402, 89,324 bytes.
    /// Kept: outcomes [0, 111, 163] of 190. Embedded sha256 cb5e13fb9c2eb790278411819e9ee1de6b9c193fc53d750aaea68db669460b87.
    static let indiaTop5 = #"{"id":65391343,"name":"DP World India Championship - Top 5 Finish","description":null,"sport":null,"sport_name":null,"category":"placement","llm_sport_category":"golf","status":"open","source":"datagolf","external_id":"datagolf:euro:2026140:top_5","market_type":"participation","mutually_exclusive":false,"commence_time":"2026-10-15T00:00:00+00:00","resolution_date":"2026-10-18T00:00:00+00:00","outcomes":[{"id":246352498,"name":"Rory McIlroy","probability":0.351696,"american_odds":null,"rank":1,"rank_change_24h":null,"probability_change_24h":null,"opening_probability":0.351696,"opening_american_odds":null,"is_winner":null,"resolution_source":null,"last_updated":"2026-10-12T23:11:06.747890+00:00","price_changed_at":null},{"id":246352530,"name":"Shubhankar Sharma","probability":0.003972,"american_odds":null,"rank":112,"rank_change_24h":null,"probability_change_24h":null,"opening_probability":0.003972,"opening_american_odds":null,"is_winner":null,"resolution_source":null,"last_updated":"2026-10-12T23:11:06.747890+00:00","price_changed_at":null},{"id":245904764,"name":"Alex Noren","probability":null,"american_odds":null,"rank":164,"rank_change_24h":null,"probability_change_24h":null,"opening_probability":0.129657,"opening_american_odds":null,"is_winner":null,"resolution_source":null,"last_updated":"2026-10-12T19:09:46.711391+00:00","price_changed_at":"2026-10-12T19:09:40.403188+00:00"}],"outcome_count":190,"lead_outcome_id":null,"openings_withheld":false,"prices_withheld":0,"expired_rungs_dropped":0,"bookmakers":["datagolf_model"],"category_tags":[],"created_at":"2026-10-11T21:37:10.727631+00:00","updated_at":"2026-10-12T00:07:53.017020+00:00","group_id":null,"canonical_market_key":null,"hook_description":null,"hook_withheld":false,"image_url":null,"event_concept_key":null,"edition_year":null,"hub_slug":"golf","category_page":null,"sport_page_key":null,"container_of_event_id":null}"#

    /// `market-65391344.json` (/api/futures/65391344, captured 2026-10-12T23:28:33Z); source sha256 c65ab2a4f99bf63ba84134c1b356e639c1f6fb2091905b1b9d98e747c71702b9, 89,445 bytes.
    /// Kept: outcomes [0, 111, 178] of 190. Embedded sha256 42751e65b86db101489e0352aa2eed8c98db5938603636cfaff40970057d56bc.
    static let indiaTop10 = #"{"id":65391344,"name":"DP World India Championship - Top 10 Finish","description":null,"sport":null,"sport_name":null,"category":"placement","llm_sport_category":"golf","status":"open","source":"datagolf","external_id":"datagolf:euro:2026140:top_10","market_type":"participation","mutually_exclusive":false,"commence_time":"2026-10-15T00:00:00+00:00","resolution_date":"2026-10-18T00:00:00+00:00","outcomes":[{"id":246352556,"name":"Rory McIlroy","probability":0.498592,"american_odds":null,"rank":1,"rank_change_24h":null,"probability_change_24h":null,"opening_probability":0.498592,"opening_american_odds":null,"is_winner":null,"resolution_source":null,"last_updated":"2026-10-12T23:11:07.952964+00:00","price_changed_at":null},{"id":246352588,"name":"Shubhankar Sharma","probability":0.012081,"american_odds":null,"rank":112,"rank_change_24h":null,"probability_change_24h":null,"opening_probability":0.012081,"opening_american_odds":null,"is_winner":null,"resolution_source":null,"last_updated":"2026-10-12T23:11:07.952964+00:00","price_changed_at":null},{"id":245904896,"name":"Alex Noren","probability":null,"american_odds":null,"rank":179,"rank_change_24h":null,"probability_change_24h":null,"opening_probability":0.230104,"opening_american_odds":null,"is_winner":null,"resolution_source":null,"last_updated":"2026-10-12T19:09:47.805511+00:00","price_changed_at":"2026-10-12T19:09:40.403188+00:00"}],"outcome_count":190,"lead_outcome_id":null,"openings_withheld":false,"prices_withheld":0,"expired_rungs_dropped":0,"bookmakers":["datagolf_model"],"category_tags":[],"created_at":"2026-10-11T21:37:10.727631+00:00","updated_at":"2026-10-12T00:07:53.017020+00:00","group_id":null,"canonical_market_key":null,"hook_description":null,"hook_withheld":false,"image_url":null,"event_concept_key":null,"edition_year":null,"hub_slug":"golf","category_page":null,"sport_page_key":null,"container_of_event_id":null}"#

    /// `market-65391345.json` (/api/futures/65391345, captured 2026-10-12T23:28:34Z); source sha256 eaab47d03aac26b39728aedb5b1dd55769a3264bc5c7d8dfd386ce5b354218b6, 89,353 bytes.
    /// Kept: outcomes [0, 113, 145] of 190. Embedded sha256 37d852680f622813b0473d29024f2175294b26ea9043b0dc2ab8ba1be1e6e6cd.
    static let indiaTop20 = #"{"id":65391345,"name":"DP World India Championship - Top 20 Finish","description":null,"sport":null,"sport_name":null,"category":"placement","llm_sport_category":"golf","status":"open","source":"datagolf","external_id":"datagolf:euro:2026140:top_20","market_type":"participation","mutually_exclusive":false,"commence_time":"2026-10-15T00:00:00+00:00","resolution_date":"2026-10-18T00:00:00+00:00","outcomes":[{"id":246352614,"name":"Rory McIlroy","probability":0.665303,"american_odds":null,"rank":1,"rank_change_24h":null,"probability_change_24h":null,"opening_probability":0.665303,"opening_american_odds":null,"is_winner":null,"resolution_source":null,"last_updated":"2026-10-12T23:11:09.073291+00:00","price_changed_at":null},{"id":246352646,"name":"Shubhankar Sharma","probability":0.034549,"american_odds":null,"rank":114,"rank_change_24h":null,"probability_change_24h":null,"opening_probability":0.034549,"opening_american_odds":null,"is_winner":null,"resolution_source":null,"last_updated":"2026-10-12T23:11:09.073291+00:00","price_changed_at":null},{"id":245905028,"name":"Alex Noren","probability":null,"american_odds":null,"rank":146,"rank_change_24h":null,"probability_change_24h":null,"opening_probability":0.391612,"opening_american_odds":null,"is_winner":null,"resolution_source":null,"last_updated":"2026-10-12T19:09:49.369336+00:00","price_changed_at":"2026-10-12T19:09:40.403188+00:00"}],"outcome_count":190,"lead_outcome_id":null,"openings_withheld":false,"prices_withheld":0,"expired_rungs_dropped":0,"bookmakers":["datagolf_model"],"category_tags":[],"created_at":"2026-10-11T21:37:10.727631+00:00","updated_at":"2026-10-12T00:07:53.017020+00:00","group_id":null,"canonical_market_key":null,"hook_description":null,"hook_withheld":false,"image_url":null,"event_concept_key":null,"edition_year":null,"hub_slug":"golf","category_page":null,"sport_page_key":null,"container_of_event_id":null}"#

    /// `market-65391346.json` (/api/futures/65391346, captured 2026-10-12T23:28:34Z); source sha256 76afc29c849e2451835c1638f082ce7bd0074cf1daa77a302ec20eefc848f811, 89,295 bytes.
    /// Kept: outcomes [0, 112, 163] of 190. Embedded sha256 a3995e7415fd9d128b538a2ffaaef5225bc18fadf5cf0baa6a361aa82c2e5317.
    static let indiaMakeCut = #"{"id":65391346,"name":"DP World India Championship - Make the Cut","description":null,"sport":null,"sport_name":null,"category":"make_cut","llm_sport_category":"golf","status":"open","source":"datagolf","external_id":"datagolf:euro:2026140:make_cut","market_type":"participation","mutually_exclusive":false,"commence_time":"2026-10-15T00:00:00+00:00","resolution_date":"2026-10-18T00:00:00+00:00","outcomes":[{"id":246352672,"name":"Rory McIlroy","probability":0.896383,"american_odds":null,"rank":1,"rank_change_24h":null,"probability_change_24h":null,"opening_probability":0.896383,"opening_american_odds":null,"is_winner":null,"resolution_source":null,"last_updated":"2026-10-12T23:11:10.724619+00:00","price_changed_at":null},{"id":246352704,"name":"Shubhankar Sharma","probability":0.345817,"american_odds":null,"rank":113,"rank_change_24h":null,"probability_change_24h":null,"opening_probability":0.345817,"opening_american_odds":null,"is_winner":null,"resolution_source":null,"last_updated":"2026-10-12T23:11:10.724619+00:00","price_changed_at":null},{"id":245905160,"name":"Alex Noren","probability":null,"american_odds":null,"rank":164,"rank_change_24h":null,"probability_change_24h":null,"opening_probability":0.78065,"opening_american_odds":null,"is_winner":null,"resolution_source":null,"last_updated":"2026-10-12T19:09:51.639944+00:00","price_changed_at":"2026-10-12T19:09:40.403188+00:00"}],"outcome_count":190,"lead_outcome_id":null,"openings_withheld":false,"prices_withheld":0,"expired_rungs_dropped":0,"bookmakers":["datagolf_model"],"category_tags":[],"created_at":"2026-10-11T21:37:10.727631+00:00","updated_at":"2026-10-12T00:07:53.017020+00:00","group_id":null,"canonical_market_key":null,"hook_description":null,"hook_withheld":false,"image_url":null,"event_concept_key":null,"edition_year":null,"hub_slug":"golf","category_page":null,"sport_page_key":null,"container_of_event_id":null}"#

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

    /// A served body with one nested value replaced: CONSTRUCTED. `path` walks
    /// object keys and array indexes; only the named key changes.
    static func edited(_ json: String, _ path: [Any], to value: Any) throws -> String {
        let object = try JSONSerialization.jsonObject(with: Data(json.utf8))
        let changed = try replace(object, path[...], with: value)
        let data = try JSONSerialization.data(withJSONObject: changed)
        return String(decoding: data, as: UTF8.self)
    }

    private static func replace(_ node: Any, _ path: ArraySlice<Any>, with value: Any) throws -> Any {
        guard let step = path.first else { return value }
        if let key = step as? String, var object = node as? [String: Any], let child = object[key] {
            object[key] = try replace(child, path.dropFirst(), with: value)
            return object
        }
        if let index = step as? Int, var array = node as? [Any], array.indices.contains(index) {
            array[index] = try replace(array[index], path.dropFirst(), with: value)
            return array
        }
        throw CocoaError(.coderValueNotFound)
    }

    /// The reader's calendar the tests speak in: Pacific, en_US.
    static let pacific: Calendar = {
        var calendar = Calendar(identifier: .gregorian)
        calendar.timeZone = TimeZone(identifier: "America/Los_Angeles")!
        return calendar
    }()

    static func host(_ now: String) -> GolfFieldPageAdapter10868.Host {
        GolfFieldPageAdapter10868.Host(now: now.asDate!, calendar: pacific, locale: Locale(identifier: "en_US"))
    }

    // Golfers (Winner outcome ids).
    static let schauffele = 242242520
    static let clark = 242242522
    static let morikawa = 242242527
    static let brennan = 241857512
    static let thorbjornsen = 242242545
    static let mitchell = 242242559
    static let fishburn = 241857553
    static let rory = 246352440
    static let sharma = 246352472
    static let jaglan = 246352496
    static let noren = 245904632
}

@MainActor
final class GolfFieldRetainedBodiesAdapter10868Tests: XCTestCase {
    private typealias R = GolfFieldRetainedBodies10868

    func testEmbeddedSubsetsArePinnedAndDecodeThroughTheProductionModels() throws {
        func sha256(_ text: String) -> String {
            SHA256.hash(data: Data(text.utf8)).map { String(format: "%02x", $0) }.joined()
        }
        let pinned: [(String, String, String)] = [
            ("baycurrentWinner", R.baycurrentWinner, "c8d1040e95ba516fa71792ae9b63b9b6a03a74ae1a19c77e4dea69045e1cafa3"),
            ("baycurrentHistory", R.baycurrentHistory, "32d0ec5482d526621c74bb8b7f56ef8d16fd16163d689cfe59db1b2a275a0739"),
            ("brennanHistory", R.brennanHistory, "711ae778c8d93ed0c3e2308eef74cee8ee4373662d43f920e7280524d80dfdc9"),
            ("indiaWin", R.indiaWin, "19a801ec43076d4be148884e8bb5d6601b0464f079d0fe3e7bdaa741e3b8368b"),
            ("indiaTop5", R.indiaTop5, "cb5e13fb9c2eb790278411819e9ee1de6b9c193fc53d750aaea68db669460b87"),
            ("indiaTop10", R.indiaTop10, "42751e65b86db101489e0352aa2eed8c98db5938603636cfaff40970057d56bc"),
            ("indiaTop20", R.indiaTop20, "37d852680f622813b0473d29024f2175294b26ea9043b0dc2ab8ba1be1e6e6cd"),
            ("indiaMakeCut", R.indiaMakeCut, "a3995e7415fd9d128b538a2ffaaef5225bc18fadf5cf0baa6a361aa82c2e5317"),
        ]
        for (name, body, hash) in pinned {
            XCTAssertEqual(sha256(body), hash, name)
        }

        let winner = try R.market(R.baycurrentWinner)
        XCTAssertEqual(winner.id, 64266833)
        XCTAssertEqual(winner.status, "resolved")
        XCTAssertEqual(winner.source, "datagolf")
        XCTAssertEqual(winner.outcomes.map(\.id),
                       [R.schauffele, R.clark, R.morikawa, R.brennan, R.thorbjornsen, R.mitchell, R.fishburn])
        XCTAssertTrue(winner.outcomes.allSatisfy { $0.isWinner == nil && $0.resolutionSource == nil },
                      "resolved, and no row carries a grade")
        XCTAssertNil(winner.outcomes.last?.probability, "Fishburn is served with no price")

        let history = try R.history(R.baycurrentHistory)
        XCTAssertEqual(history.marketId, 64266833)
        XCTAssertEqual(history.outcomes.map(\.outcomeId), [R.clark, R.schauffele, R.morikawa])
        XCTAssertEqual(history.outcomes.map(\.history.count), [11, 11, 11])
        XCTAssertFalse(history.outcomes.flatMap(\.history).contains { $0.isSettlement })

        let brennan = try R.history(R.brennanHistory)
        XCTAssertEqual(brennan.outcomes.map(\.outcomeId), [R.brennan])
        XCTAssertEqual(brennan.outcomes[0].history[10].probability, 1.0)
        XCTAssertEqual(brennan.outcomes[0].history.last?.timestamp, "2026-10-11T22:08:55.891004+00:00")
        XCTAssertEqual(brennan.outcomes[0].history.last?.probability, 0.026017)

        let india = try R.market(R.indiaWin)
        XCTAssertEqual(india.status, "open")
        XCTAssertEqual(india.outcomes.map(\.id), [R.rory, R.sharma, R.jaglan, R.noren])
        XCTAssertEqual(india.outcomes.first { $0.id == R.jaglan }?.probability, 0)
        XCTAssertNil(india.outcomes.first { $0.id == R.noren }?.probability)
        XCTAssertEqual(india.outcomes.first { $0.id == R.noren }?.openingProbability, 0.0283)
        for (json, id) in [(R.indiaTop5, 65391343), (R.indiaTop10, 65391344), (R.indiaTop20, 65391345),
                           (R.indiaMakeCut, 65391346)] {
            let market = try R.market(json)
            XCTAssertEqual(market.id, id)
            XCTAssertEqual(market.outcomes.count, 3)
        }
    }
}
