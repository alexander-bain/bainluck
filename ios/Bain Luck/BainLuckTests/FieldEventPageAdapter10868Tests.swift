import SwiftUI
import XCTest
@testable import Bain_Luck

/// #10868 — the FIELD screen adapters' retained REAL inputs, shared by every
/// FieldEvent adapter test file, decoded exactly as the app decodes them
/// (`.convertFromSnakeCase`, `APIClient`).
///
/// PREPARED / NOT RUN (source-only hold: `xcrun swiftc -parse` only).
///
/// REDUCED VERBATIM SUBSETS. Each kept piece — a top-level `"key":value` pair, one
/// outcome object, one history line's own keys and kept points — is the server's
/// bytes, in source order, asserted as a byte-for-byte substring of its source
/// file by `/tmp/cli-10868-field/make_field_subsets.py` (run `python3 -I
/// make_field_subsets.py <design-dir> <out>`; it reuses the racing script's
/// verified-substring helpers). Only the envelope is assembled: which array
/// members are kept and the line breaks between them; every history drops its
/// `leaderboard`, `round_boundaries` and `venue_history` keys. Detail bodies keep
/// EVERY outcome except the two gate controls (volleyball, lacrosse). Sources
/// under `artifacts/discovery-containers-release-plan/event-page-design-20261011/`:
///   - rugby: the 2027 Men's Rugby World Cup Winner board and its `/history`, both
///     captured Oct 15, 2026 21:00:59Z (`rugby-history-v343/raw/manifest.json`);
///   - chess: the U.S. Women's Chess Championship Winner board and its `/history`,
///     captured Oct 15, 2026 08:59:00Z (`chess-probability-journey-v303/raw/manifest.json`);
///   - darts and cricket: the PDC World Championship Winner and 2027 IPL Champion
///     boards, captured Oct 11, 2026 05:25:18Z (`atlas-v6/raw/family-detail-manifest.json`).
///     NO `/history` body of either is retained anywhere in the artifacts;
///   - the FINAL rules are proven on the only retained RESOLVED, mutually
///     exclusive Kalshi field body with a `/history` outside golf and motorsports:
///     "Series Exact Score: Chicago WS vs Houston" (baseball), captured Oct 12,
///     2026 15:04:25Z. NOT one of this screen's routes — `applies` refuses it — and
///     its outcomes ("CWS wins 2-0") are why the contender noun is "contender"
///     outside the proven categories;
///   - gate controls: the Division I Women's Volleyball Champion board (served
///     with `llm_sport_category` "basketball") and its `/history`, captured Oct 15,
///     2026 21:31:11Z, and the LA28 men's lacrosse qualification board
///     (`mutually_exclusive` false, every probability null), Oct 15, 2026 22:06:29Z.
///
/// Any CONSTRUCTED variant is built with `replacing(_:_:with:)` (one served
/// substring, proven to occur once) and labelled where it is used; a CONSTRUCTED
/// reader clock is labelled the same way.
@MainActor
enum FieldEventAdapterFixtures10868 {
    /// `rugby-history-v343/raw/detail.json` (sha256 605d78e5c628d709a3bec6ee6f161f3ffb9a8989ce7c88f96825336d7cd49553): all 24 outcomes.
    static let rugbyBefore = #"""
    {
    "id":60473053,
    "name":"2027 Men's Rugby World Cup Winner",
    "description":null,
    "sport":null,
    "sport_name":null,
    "category":"championship",
    "llm_sport_category":"rugby",
    "status":"open",
    "source":"kalshi",
    "external_id":"KXRUGBYWC-27",
    "market_type":"field",
    "mutually_exclusive":true,
    "commence_time":"2027-11-13T23:00:00+00:00",
    "resolution_date":"2027-11-13T23:00:00+00:00",
    "outcomes":[
    {"id":225917124,"name":"Ireland","probability":0.59,"american_odds":3233,"rank":1,"rank_change_24h":null,"probability_change_24h":null,"opening_probability":null,"opening_american_odds":null,"is_winner":null,"resolution_source":null,"last_updated":"2026-10-15T20:54:48.335080+00:00","price_changed_at":"2026-10-15T06:16:57.349894+00:00"},
    {"id":225917112,"name":"South Africa","probability":0.4,"american_odds":-223,"rank":2,"rank_change_24h":null,"probability_change_24h":null,"opening_probability":0.795,"opening_american_odds":-388,"is_winner":null,"resolution_source":null,"last_updated":"2026-10-15T20:54:48.335080+00:00","price_changed_at":"2026-10-15T17:15:19.547035+00:00"},
    {"id":225917111,"name":"France","probability":0.06,"american_odds":3233,"rank":3,"rank_change_24h":null,"probability_change_24h":null,"opening_probability":0.795,"opening_american_odds":-388,"is_winner":null,"resolution_source":null,"last_updated":"2026-10-15T20:52:01.915332+00:00","price_changed_at":"2026-10-15T14:27:59.397488+00:00"},
    {"id":225917113,"name":"New Zealand","probability":0.01,"american_odds":-2400,"rank":4,"rank_change_24h":null,"probability_change_24h":null,"opening_probability":null,"opening_american_odds":null,"is_winner":null,"resolution_source":null,"last_updated":"2026-10-15T20:51:00.786291+00:00","price_changed_at":"2026-10-15T16:47:03.035709+00:00"},
    {"id":225917131,"name":"England","probability":0.01,"american_odds":-3233,"rank":5,"rank_change_24h":null,"probability_change_24h":null,"opening_probability":null,"opening_american_odds":null,"is_winner":null,"resolution_source":null,"last_updated":"2026-10-15T20:54:48.335080+00:00","price_changed_at":"2026-10-15T16:47:03.035709+00:00"},
    {"id":225917125,"name":"Scotland","probability":null,"american_odds":null,"rank":6,"rank_change_24h":null,"probability_change_24h":null,"opening_probability":null,"opening_american_odds":null,"is_winner":null,"resolution_source":null,"last_updated":"2026-09-28T22:52:00.415654+00:00","price_changed_at":null,"movement":null},
    {"id":225917116,"name":"Hong Kong China","probability":null,"american_odds":null,"rank":7,"rank_change_24h":null,"probability_change_24h":null,"opening_probability":null,"opening_american_odds":null,"is_winner":null,"resolution_source":null,"last_updated":"2026-09-28T22:52:00.415654+00:00","price_changed_at":null,"movement":null},
    {"id":225917118,"name":"Georgia","probability":null,"american_odds":null,"rank":8,"rank_change_24h":null,"probability_change_24h":null,"opening_probability":null,"opening_american_odds":null,"is_winner":null,"resolution_source":null,"last_updated":"2026-09-28T22:52:00.415654+00:00","price_changed_at":null,"movement":null},
    {"id":225917122,"name":"Spain","probability":null,"american_odds":null,"rank":9,"rank_change_24h":null,"probability_change_24h":null,"opening_probability":null,"opening_american_odds":null,"is_winner":null,"resolution_source":null,"last_updated":"2026-09-28T22:52:00.415654+00:00","price_changed_at":null,"movement":null},
    {"id":225917117,"name":"Italy","probability":null,"american_odds":null,"rank":10,"rank_change_24h":null,"probability_change_24h":null,"opening_probability":null,"opening_american_odds":null,"is_winner":null,"resolution_source":null,"last_updated":"2026-09-28T22:52:00.415654+00:00","price_changed_at":null,"movement":null},
    {"id":225917134,"name":"Zimbabwe","probability":null,"american_odds":null,"rank":11,"rank_change_24h":null,"probability_change_24h":null,"opening_probability":null,"opening_american_odds":null,"is_winner":null,"resolution_source":null,"last_updated":"2026-09-28T22:52:00.415654+00:00","price_changed_at":null,"movement":null},
    {"id":225917120,"name":"Argentina","probability":null,"american_odds":null,"rank":12,"rank_change_24h":null,"probability_change_24h":null,"opening_probability":null,"opening_american_odds":null,"is_winner":null,"resolution_source":null,"last_updated":"2026-09-28T22:52:00.415654+00:00","price_changed_at":null,"movement":null},
    {"id":225917130,"name":"Samoa","probability":null,"american_odds":null,"rank":13,"rank_change_24h":null,"probability_change_24h":null,"opening_probability":null,"opening_american_odds":null,"is_winner":null,"resolution_source":null,"last_updated":"2026-09-28T22:52:00.415654+00:00","price_changed_at":null,"movement":null},
    {"id":225917128,"name":"Japan","probability":null,"american_odds":null,"rank":14,"rank_change_24h":null,"probability_change_24h":null,"opening_probability":null,"opening_american_odds":null,"is_winner":null,"resolution_source":null,"last_updated":"2026-09-28T22:52:00.415654+00:00","price_changed_at":null,"movement":null},
    {"id":225917119,"name":"Romania","probability":null,"american_odds":null,"rank":15,"rank_change_24h":null,"probability_change_24h":null,"opening_probability":null,"opening_american_odds":null,"is_winner":null,"resolution_source":null,"last_updated":"2026-09-28T22:52:00.415654+00:00","price_changed_at":null,"movement":null},
    {"id":225917127,"name":"Portugal","probability":null,"american_odds":null,"rank":16,"rank_change_24h":null,"probability_change_24h":null,"opening_probability":null,"opening_american_odds":null,"is_winner":null,"resolution_source":null,"last_updated":"2026-09-28T22:52:00.415654+00:00","price_changed_at":null,"movement":null},
    {"id":225917126,"name":"Uruguay","probability":null,"american_odds":null,"rank":17,"rank_change_24h":null,"probability_change_24h":null,"opening_probability":null,"opening_american_odds":null,"is_winner":null,"resolution_source":null,"last_updated":"2026-09-28T22:52:00.415654+00:00","price_changed_at":null,"movement":null},
    {"id":225917133,"name":"Tonga","probability":null,"american_odds":null,"rank":18,"rank_change_24h":null,"probability_change_24h":null,"opening_probability":null,"opening_american_odds":null,"is_winner":null,"resolution_source":null,"last_updated":"2026-09-28T22:52:00.415654+00:00","price_changed_at":null,"movement":null},
    {"id":225917114,"name":"Australia","probability":null,"american_odds":null,"rank":19,"rank_change_24h":null,"probability_change_24h":null,"opening_probability":null,"opening_american_odds":null,"is_winner":null,"resolution_source":null,"last_updated":"2026-09-28T22:52:00.415654+00:00","price_changed_at":null,"movement":null},
    {"id":225917115,"name":"Chile","probability":null,"american_odds":null,"rank":20,"rank_change_24h":null,"probability_change_24h":null,"opening_probability":null,"opening_american_odds":null,"is_winner":null,"resolution_source":null,"last_updated":"2026-09-28T22:52:00.415654+00:00","price_changed_at":null,"movement":null},
    {"id":225917121,"name":"Fiji","probability":null,"american_odds":null,"rank":21,"rank_change_24h":null,"probability_change_24h":null,"opening_probability":null,"opening_american_odds":null,"is_winner":null,"resolution_source":null,"last_updated":"2026-09-28T22:52:00.415654+00:00","price_changed_at":null,"movement":null},
    {"id":225917123,"name":"Canada","probability":null,"american_odds":null,"rank":22,"rank_change_24h":null,"probability_change_24h":null,"opening_probability":null,"opening_american_odds":null,"is_winner":null,"resolution_source":null,"last_updated":"2026-09-28T22:52:00.415654+00:00","price_changed_at":null,"movement":null},
    {"id":225917129,"name":"USA","probability":null,"american_odds":null,"rank":23,"rank_change_24h":null,"probability_change_24h":null,"opening_probability":null,"opening_american_odds":null,"is_winner":null,"resolution_source":null,"last_updated":"2026-09-28T22:52:00.415654+00:00","price_changed_at":null,"movement":null},
    {"id":225917132,"name":"Wales","probability":null,"american_odds":null,"rank":24,"rank_change_24h":null,"probability_change_24h":null,"opening_probability":null,"opening_american_odds":null,"is_winner":null,"resolution_source":null,"last_updated":"2026-09-28T22:52:00.415654+00:00","price_changed_at":null,"movement":null}
    ],
    "outcome_count":24,
    "lead_outcome_id":null,
    "openings_withheld":false,
    "prices_withheld":19,
    "expired_rungs_dropped":0,
    "bookmakers":["kalshi"],
    "category_tags":["rugby"],
    "created_at":"2026-09-08T10:47:56.651907+00:00",
    "updated_at":"2026-09-28T22:52:00.415654+00:00",
    "group_id":"kalshi:KXRUGBYWC-27",
    "canonical_market_key":"rugby:RUGBY:championship:2027",
    "hook_description":null,
    "hook_withheld":false,
    "image_url":null,
    "event_concept_key":null,
    "edition_year":null,
    "hub_slug":null,
    "category_page":null,
    "sport_page_key":null,
    "container_of_event_id":null
    }
    """#

    /// `rugby-history-v343/raw/history.json` (sha256 6956a1980a0432defae8c59b9aa2a967e156bd6cdd1074d4e53ae15d2b7dfc10): lines {225917124: (3, 3), 225917112: (3, 3), 225917111: (3, 3), 225917113: (2, 2)} (head, tail); drops ['leaderboard', 'round_boundaries', 'venue_history'].
    static let rugbyHistory = #"""
    {
    "market_id":60473053,
    "market_name":"2027 Men's Rugby World Cup Winner",
    "hours":168,
    "actual_hours":720,
    "outcomes":[
    {"outcome_id":225917113,"name":"New Zealand","history":[
    {"timestamp":"2026-09-16T01:51:29.915951+00:00","probability":0.03,"american_odds":null,"bookmaker":"consensus"},
    {"timestamp":"2026-09-16T08:51:25.927369+00:00","probability":0.03,"american_odds":null,"bookmaker":"consensus"},
    {"timestamp":"2026-10-12T04:15:06.799296+00:00","probability":0.96,"american_odds":null,"bookmaker":"consensus"},
    {"timestamp":"2026-10-12T17:40:08.425584+00:00","probability":0.96,"american_odds":null,"bookmaker":"consensus"}
    ],"eliminated":false,"eliminated_at":null},
    {"outcome_id":225917112,"name":"South Africa","history":[
    {"timestamp":"2026-09-16T01:51:29.915951+00:00","probability":0.09,"american_odds":null,"bookmaker":"consensus"},
    {"timestamp":"2026-09-16T08:51:25.927369+00:00","probability":0.09,"american_odds":null,"bookmaker":"consensus"},
    {"timestamp":"2026-09-16T15:51:54.540760+00:00","probability":0.09,"american_odds":null,"bookmaker":"consensus"},
    {"timestamp":"2026-10-06T03:54:18.782985+00:00","probability":0.8,"american_odds":null,"bookmaker":"consensus"},
    {"timestamp":"2026-10-06T10:56:56.238540+00:00","probability":0.8,"american_odds":null,"bookmaker":"consensus"},
    {"timestamp":"2026-10-07T13:01:09.953967+00:00","probability":0.69,"american_odds":null,"bookmaker":"consensus"}
    ],"eliminated":false,"eliminated_at":null},
    {"outcome_id":225917111,"name":"France","history":[
    {"timestamp":"2026-09-16T01:51:29.915951+00:00","probability":0.97,"american_odds":null,"bookmaker":"consensus"},
    {"timestamp":"2026-09-16T08:51:25.927369+00:00","probability":0.97,"american_odds":null,"bookmaker":"consensus"},
    {"timestamp":"2026-09-16T15:51:54.540760+00:00","probability":0.97,"american_odds":null,"bookmaker":"consensus"},
    {"timestamp":"2026-10-07T13:01:09.953967+00:00","probability":0.03,"american_odds":null,"bookmaker":"consensus"},
    {"timestamp":"2026-10-08T05:21:17.891245+00:00","probability":0.03,"american_odds":null,"bookmaker":"consensus"},
    {"timestamp":"2026-10-08T12:47:34.213639+00:00","probability":0.03,"american_odds":null,"bookmaker":"consensus"}
    ],"eliminated":false,"eliminated_at":null},
    {"outcome_id":225917124,"name":"Ireland","history":[
    {"timestamp":"2026-10-01T08:07:08.891195+00:00","probability":0.97,"american_odds":null,"bookmaker":"consensus"},
    {"timestamp":"2026-10-02T21:18:50.422968+00:00","probability":0.03,"american_odds":null,"bookmaker":"consensus"},
    {"timestamp":"2026-10-03T04:20:39.302962+00:00","probability":0.03,"american_odds":null,"bookmaker":"consensus"},
    {"timestamp":"2026-10-07T13:01:09.953967+00:00","probability":0.03,"american_odds":null,"bookmaker":"consensus"},
    {"timestamp":"2026-10-08T05:21:17.891245+00:00","probability":0.03,"american_odds":null,"bookmaker":"consensus"},
    {"timestamp":"2026-10-08T12:47:34.213639+00:00","probability":0.03,"american_odds":null,"bookmaker":"consensus"}
    ],"eliminated":false,"eliminated_at":null}
    ],
    "total_data_points":153,
    "coverage_start":"2026-09-16T01:51:29.915951+00:00",
    "coverage_end":"2026-10-12T17:40:08.425584+00:00",
    "coverage_hours":639.81,
    "observation_times":96,
    "auto_extended":true
    }
    """#

    /// `chess-probability-journey-v303/raw/detail.json` (sha256 5d765632e942fe3ff7767b345558ab826a69db6f4196103dfd5797877eb0a578): all 12 outcomes.
    static let chessBefore = #"""
    {
    "id":62383719,
    "name":"U.S. Women's Chess Championship Winner",
    "description":null,
    "sport":null,
    "sport_name":null,
    "category":"championship",
    "llm_sport_category":"chess",
    "status":"open",
    "source":"kalshi",
    "external_id":"KXCHESSTOURNAMENT-26USWC",
    "market_type":"field",
    "mutually_exclusive":true,
    "commence_time":"2026-10-29T22:00:00+00:00",
    "resolution_date":"2026-10-22T22:00:00+00:00",
    "outcomes":[
    {"id":235705516,"name":"Alice Lee","probability":0.855,"american_odds":-217,"rank":1,"rank_change_24h":null,"probability_change_24h":null,"opening_probability":0.325,"opening_american_odds":208,"is_winner":null,"resolution_source":null,"last_updated":"2026-10-15T08:01:07.824368+00:00","price_changed_at":"2026-10-15T08:01:07.824368+00:00"},
    {"id":235705523,"name":"Rachael Li","probability":0.11,"american_odds":1900,"rank":2,"rank_change_24h":null,"probability_change_24h":null,"opening_probability":0.045,"opening_american_odds":2122,"is_winner":null,"resolution_source":null,"last_updated":"2026-10-15T08:47:06.000060+00:00","price_changed_at":"2026-10-15T08:47:06.000060+00:00"},
    {"id":235705519,"name":"Thalia Cervantes","probability":0.1,"american_odds":1900,"rank":3,"rank_change_24h":null,"probability_change_24h":null,"opening_probability":null,"opening_american_odds":null,"is_winner":null,"resolution_source":null,"last_updated":"2026-10-15T08:01:03.816953+00:00","price_changed_at":"2026-10-15T08:01:03.816953+00:00"},
    {"id":235705520,"name":"Megan Paragua","probability":0.1,"american_odds":2400,"rank":4,"rank_change_24h":null,"probability_change_24h":null,"opening_probability":null,"opening_american_odds":null,"is_winner":null,"resolution_source":null,"last_updated":"2026-10-15T08:01:04.811555+00:00","price_changed_at":"2026-10-15T08:01:04.811555+00:00"},
    {"id":235705521,"name":"Irina Krush","probability":0.055,"american_odds":3233,"rank":5,"rank_change_24h":null,"probability_change_24h":null,"opening_probability":0.065,"opening_american_odds":1438,"is_winner":null,"resolution_source":null,"last_updated":"2026-10-15T08:47:22.808236+00:00","price_changed_at":"2026-10-15T08:47:22.808236+00:00"},
    {"id":235705522,"name":"Anna Sargsyan","probability":null,"american_odds":null,"rank":8,"rank_change_24h":null,"probability_change_24h":null,"opening_probability":0.045,"opening_american_odds":2122,"is_winner":null,"resolution_source":null,"last_updated":"2026-10-13T21:14:09.458344+00:00","price_changed_at":"2026-10-13T13:13:54.709061+00:00","movement":null},
    {"id":235705517,"name":"Anna Zatonskih","probability":null,"american_odds":null,"rank":9,"rank_change_24h":null,"probability_change_24h":null,"opening_probability":null,"opening_american_odds":null,"is_winner":null,"resolution_source":null,"last_updated":"2026-10-13T21:14:14.404820+00:00","price_changed_at":"2026-10-13T13:13:54.709061+00:00","movement":null},
    {"id":235705518,"name":"Nazi Paikidze","probability":null,"american_odds":null,"rank":10,"rank_change_24h":null,"probability_change_24h":null,"opening_probability":null,"opening_american_odds":null,"is_winner":null,"resolution_source":null,"last_updated":"2026-10-13T21:14:11.361509+00:00","price_changed_at":"2026-10-13T21:14:11.361509+00:00","movement":null},
    {"id":235705526,"name":"Jennifer Yu","probability":null,"american_odds":null,"rank":11,"rank_change_24h":null,"probability_change_24h":null,"opening_probability":0.04,"opening_american_odds":2400,"is_winner":null,"resolution_source":null,"last_updated":"2026-10-13T21:14:12.404272+00:00","price_changed_at":"2026-10-13T13:13:54.709061+00:00","movement":null},
    {"id":235705524,"name":"Rose Atwell","probability":null,"american_odds":null,"rank":12,"rank_change_24h":null,"probability_change_24h":null,"opening_probability":0.04,"opening_american_odds":2400,"is_winner":null,"resolution_source":null,"last_updated":"2026-10-13T12:05:06.577579+00:00","price_changed_at":"2026-10-13T04:45:37.883861+00:00","movement":null},
    {"id":235705525,"name":"Tatev Abrahamyan","probability":0.015,"american_odds":1900,"rank":6,"rank_change_24h":null,"probability_change_24h":null,"opening_probability":0.04,"opening_american_odds":2400,"is_winner":null,"resolution_source":null,"last_updated":"2026-10-14T21:45:42.318171+00:00","price_changed_at":"2026-10-14T21:45:42.318171+00:00"},
    {"id":235705515,"name":"Carissa Yip","probability":0.01,"american_odds":1900,"rank":7,"rank_change_24h":null,"probability_change_24h":null,"opening_probability":0.325,"opening_american_odds":208,"is_winner":null,"resolution_source":null,"last_updated":"2026-10-15T07:54:10.466050+00:00","price_changed_at":"2026-10-15T07:54:10.466050+00:00"}
    ],
    "outcome_count":12,
    "lead_outcome_id":null,
    "openings_withheld":false,
    "prices_withheld":5,
    "expired_rungs_dropped":0,
    "bookmakers":["kalshi"],
    "category_tags":["chess"],
    "created_at":"2026-09-25T20:49:31.631237+00:00",
    "updated_at":"2026-09-26T05:01:22.485299+00:00",
    "group_id":"kalshi:KXCHESSTOURNAMENT-26USWC",
    "canonical_market_key":null,
    "hook_description":null,
    "hook_withheld":false,
    "image_url":null,
    "event_concept_key":null,
    "edition_year":null,
    "hub_slug":null,
    "category_page":null,
    "sport_page_key":null,
    "container_of_event_id":null
    }
    """#

    /// `chess-probability-journey-v303/raw/history.json` (sha256 1f14139ac809eec306b578fe63fac66eab3b720cd9eb20218cf9087e051bb137): lines {235705516: (3, 3), 235705523: (3, 3), 235705519: (None, None)} (head, tail); drops ['leaderboard', 'round_boundaries', 'venue_history'].
    static let chessHistory = #"""
    {
    "market_id":62383719,
    "market_name":"U.S. Women's Chess Championship Winner",
    "hours":168,
    "actual_hours":720,
    "outcomes":[
    {"outcome_id":235705516,"name":"Alice Lee","history":[
    {"timestamp":"2026-09-25T20:49:31.505270+00:00","probability":0.325,"american_odds":null,"bookmaker":"consensus"},
    {"timestamp":"2026-09-26T04:57:13.952767+00:00","probability":0.33,"american_odds":null,"bookmaker":"consensus"},
    {"timestamp":"2026-09-26T17:07:34.510686+00:00","probability":0.325,"american_odds":null,"bookmaker":"consensus"},
    {"timestamp":"2026-10-08T12:48:07.081761+00:00","probability":0.38,"american_odds":null,"bookmaker":"consensus"},
    {"timestamp":"2026-10-12T04:15:42.244947+00:00","probability":0.635,"american_odds":null,"bookmaker":"consensus"},
    {"timestamp":"2026-10-12T17:40:20.327811+00:00","probability":0.685,"american_odds":null,"bookmaker":"consensus"}
    ],"eliminated":false,"eliminated_at":null},
    {"outcome_id":235705523,"name":"Rachael Li","history":[
    {"timestamp":"2026-09-25T20:49:31.505270+00:00","probability":0.045,"american_odds":null,"bookmaker":"consensus"},
    {"timestamp":"2026-09-26T04:57:13.952767+00:00","probability":0.05,"american_odds":null,"bookmaker":"consensus"},
    {"timestamp":"2026-09-26T17:07:34.510686+00:00","probability":0.045,"american_odds":null,"bookmaker":"consensus"},
    {"timestamp":"2026-10-07T15:54:52.295713+00:00","probability":0.05,"american_odds":null,"bookmaker":"consensus"},
    {"timestamp":"2026-10-12T04:15:42.244947+00:00","probability":0.09,"american_odds":null,"bookmaker":"consensus"},
    {"timestamp":"2026-10-12T17:40:20.327811+00:00","probability":0.05,"american_odds":null,"bookmaker":"consensus"}
    ],"eliminated":false,"eliminated_at":null},
    {"outcome_id":235705519,"name":"Thalia Cervantes","history":[
    {"timestamp":"2026-10-12T04:15:42.244947+00:00","probability":0.06,"american_odds":null,"bookmaker":"consensus"},
    {"timestamp":"2026-10-12T17:40:20.327811+00:00","probability":0.05,"american_odds":null,"bookmaker":"consensus"}
    ],"eliminated":false,"eliminated_at":null}
    ],
    "total_data_points":171,
    "coverage_start":"2026-09-25T20:49:31.505270+00:00",
    "coverage_end":"2026-10-12T17:40:20.327811+00:00",
    "coverage_hours":404.85,
    "observation_times":33,
    "auto_extended":true
    }
    """#

    /// `atlas-v6/raw/field-34275792.json` (sha256 ebac320022f46264916b1de057d793ce39c6e3c055c4f531332c56eb6c7578f6): all 18 outcomes.
    static let dartsBefore = #"""
    {
    "id":34275792,
    "name":"PDC World Championship Winner",
    "description":null,
    "sport":null,
    "sport_name":null,
    "category":"championship",
    "llm_sport_category":"darts",
    "status":"open",
    "source":"kalshi",
    "external_id":"KXPDCDARTS-27",
    "market_type":"field",
    "mutually_exclusive":true,
    "commence_time":"2027-01-22T15:00:00+00:00",
    "resolution_date":"2027-01-08T15:00:00+00:00",
    "outcomes":[
    {"id":206766142,"name":"Luke Littler","probability":0.4955,"american_odds":-125,"rank":1,"rank_change_24h":null,"probability_change_24h":null,"opening_probability":null,"opening_american_odds":null,"is_winner":false,"resolution_source":"ungradeable_result","last_updated":"2026-10-10T11:49:37.412255+00:00","price_changed_at":"2026-10-10T11:49:37.412255+00:00"},
    {"id":152585733,"name":"Luke Humphries","probability":0.1607,"american_odds":456,"rank":2,"rank_change_24h":null,"probability_change_24h":null,"opening_probability":null,"opening_american_odds":null,"is_winner":false,"resolution_source":"ungradeable_result","last_updated":"2026-10-10T11:49:37.412255+00:00","price_changed_at":"2026-10-10T11:49:37.412255+00:00"},
    {"id":206766155,"name":"James Wade","probability":0.0625,"american_odds":1329,"rank":3,"rank_change_24h":null,"probability_change_24h":null,"opening_probability":null,"opening_american_odds":null,"is_winner":false,"resolution_source":"ungradeable_result","last_updated":"2026-10-10T11:49:37.412255+00:00","price_changed_at":"2026-10-10T11:49:37.412255+00:00"},
    {"id":206766146,"name":"Gerwyn Price","probability":0.0491,"american_odds":1718,"rank":4,"rank_change_24h":null,"probability_change_24h":null,"opening_probability":null,"opening_american_odds":null,"is_winner":false,"resolution_source":"ungradeable_result","last_updated":"2026-10-10T11:49:37.412255+00:00","price_changed_at":"2026-10-05T12:55:03.705245+00:00"},
    {"id":206766144,"name":"Gian van Veen","probability":0.0446,"american_odds":1900,"rank":5,"rank_change_24h":null,"probability_change_24h":null,"opening_probability":null,"opening_american_odds":null,"is_winner":false,"resolution_source":"ungradeable_result","last_updated":"2026-10-10T11:49:37.412255+00:00","price_changed_at":"2026-09-30T16:59:56.946814+00:00"},
    {"id":206766145,"name":"Wessel Nijman","probability":0.0313,"american_odds":2757,"rank":6,"rank_change_24h":null,"probability_change_24h":null,"opening_probability":null,"opening_american_odds":null,"is_winner":false,"resolution_source":"ungradeable_result","last_updated":"2026-10-10T11:49:37.412255+00:00","price_changed_at":"2026-09-29T01:02:09.632762+00:00"},
    {"id":206766150,"name":"Michael van Gerwen","probability":0.0268,"american_odds":3233,"rank":7,"rank_change_24h":null,"probability_change_24h":null,"opening_probability":null,"opening_american_odds":null,"is_winner":false,"resolution_source":"ungradeable_result","last_updated":"2026-10-10T11:49:37.412255+00:00","price_changed_at":"2026-09-21T05:50:48.815814+00:00"},
    {"id":206766148,"name":"Ryan Searle","probability":0.0179,"american_odds":4900,"rank":8,"rank_change_24h":null,"probability_change_24h":null,"opening_probability":null,"opening_american_odds":null,"is_winner":false,"resolution_source":"ungradeable_result","last_updated":"2026-10-10T11:49:37.412255+00:00","price_changed_at":"2026-09-07T16:51:33.691709+00:00"},
    {"id":206766149,"name":"Rob Cross","probability":0.0179,"american_odds":4900,"rank":9,"rank_change_24h":null,"probability_change_24h":null,"opening_probability":null,"opening_american_odds":null,"is_winner":false,"resolution_source":"ungradeable_result","last_updated":"2026-10-10T11:49:37.412255+00:00","price_changed_at":"2026-09-18T14:52:22.151835+00:00"},
    {"id":206766151,"name":"Josh Rock","probability":0.0179,"american_odds":4900,"rank":10,"rank_change_24h":null,"probability_change_24h":null,"opening_probability":null,"opening_american_odds":null,"is_winner":false,"resolution_source":"ungradeable_result","last_updated":"2026-10-10T11:49:37.412255+00:00","price_changed_at":"2026-09-24T16:52:55.521576+00:00"},
    {"id":206766152,"name":"Gary Anderson","probability":0.0179,"american_odds":4900,"rank":11,"rank_change_24h":null,"probability_change_24h":null,"opening_probability":null,"opening_american_odds":null,"is_winner":false,"resolution_source":"ungradeable_result","last_updated":"2026-10-10T11:49:37.412255+00:00","price_changed_at":"2026-09-07T02:12:41.671618+00:00"},
    {"id":206766156,"name":"Nathan Aspinall","probability":0.0179,"american_odds":4900,"rank":12,"rank_change_24h":null,"probability_change_24h":null,"opening_probability":null,"opening_american_odds":null,"is_winner":false,"resolution_source":"ungradeable_result","last_updated":"2026-10-10T11:49:37.412255+00:00","price_changed_at":"2026-09-05T01:05:15.184083+00:00"},
    {"id":206766159,"name":"Dirk van Duijvenbode","probability":0.0134,"american_odds":6567,"rank":13,"rank_change_24h":null,"probability_change_24h":null,"opening_probability":null,"opening_american_odds":null,"is_winner":false,"resolution_source":"ungradeable_result","last_updated":"2026-10-10T11:49:37.412255+00:00","price_changed_at":"2026-09-03T21:50:41.364515+00:00"},
    {"id":206766153,"name":"Jonny Clayton","probability":0.0134,"american_odds":6567,"rank":14,"rank_change_24h":null,"probability_change_24h":null,"opening_probability":null,"opening_american_odds":null,"is_winner":false,"resolution_source":"ungradeable_result","last_updated":"2026-10-10T11:49:37.412255+00:00","price_changed_at":null},
    {"id":206766147,"name":"Kevin Doets","probability":0.0134,"american_odds":6567,"rank":15,"rank_change_24h":null,"probability_change_24h":null,"opening_probability":null,"opening_american_odds":null,"is_winner":false,"resolution_source":"ungradeable_result","last_updated":"2026-10-10T11:49:37.412255+00:00","price_changed_at":"2026-09-05T01:05:15.184083+00:00"},
    {"id":206766158,"name":"Chris Dobey","probability":0.0089,"american_odds":9900,"rank":16,"rank_change_24h":null,"probability_change_24h":null,"opening_probability":null,"opening_american_odds":null,"is_winner":false,"resolution_source":"ungradeable_result","last_updated":"2026-10-10T11:49:37.412255+00:00","price_changed_at":null},
    {"id":206766154,"name":"Stephen Bunting","probability":0.0089,"american_odds":9900,"rank":17,"rank_change_24h":null,"probability_change_24h":null,"opening_probability":null,"opening_american_odds":null,"is_winner":false,"resolution_source":"ungradeable_result","last_updated":"2026-10-10T11:49:37.412255+00:00","price_changed_at":"2026-10-01T06:03:13.377965+00:00"},
    {"id":206766157,"name":"Danny Noppert","probability":0.0089,"american_odds":9900,"rank":18,"rank_change_24h":null,"probability_change_24h":null,"opening_probability":null,"opening_american_odds":null,"is_winner":false,"resolution_source":"ungradeable_result","last_updated":"2026-10-10T11:49:37.412255+00:00","price_changed_at":null}
    ],
    "outcome_count":18,
    "lead_outcome_id":null,
    "openings_withheld":true,
    "prices_withheld":0,
    "expired_rungs_dropped":0,
    "bookmakers":["kalshi"],
    "category_tags":["darts"],
    "created_at":"2026-06-09T08:47:04.116991+00:00",
    "updated_at":"2026-09-13T00:53:35.955226+00:00",
    "group_id":"kalshi:KXPDCDARTS-27",
    "canonical_market_key":null,
    "hook_description":null,
    "hook_withheld":true,
    "image_url":"https://images.pexels.com/photos/30463022/pexels-photo-30463022.jpeg?auto=compress&cs=tinysrgb&h=650&w=940",
    "event_concept_key":null,
    "hub_slug":null,
    "category_page":null,
    "sport_page_key":null,
    "container_of_event_id":null
    }
    """#

    /// `atlas-v6/raw/field-31834252.json` (sha256 7e397b293577497fcbaf64d93591ebebf736f8be252665aa75242827c0fd0092): all 10 outcomes.
    static let cricketBefore = #"""
    {
    "id":31834252,
    "name":"2027 IPL Champion",
    "description":null,
    "sport":null,
    "sport_name":null,
    "category":"championship",
    "llm_sport_category":"cricket",
    "status":"open",
    "source":"kalshi",
    "external_id":"KXIPL-27",
    "market_type":"field",
    "mutually_exclusive":true,
    "commence_time":"2027-06-20T14:00:00+00:00",
    "resolution_date":"2027-06-06T14:00:00+00:00",
    "outcomes":[
    {"id":144903806,"name":"Royal Challengers Bengaluru","probability":0.275,"american_odds":264,"rank":1,"rank_change_24h":null,"probability_change_24h":null,"opening_probability":0.165,"opening_american_odds":506,"is_winner":false,"resolution_source":"ungradeable_result","last_updated":"2026-10-08T17:20:59.169116+00:00","price_changed_at":"2026-10-08T08:54:33.416833+00:00"},
    {"id":144903807,"name":"Sunrisers Hyderabad","probability":0.095,"american_odds":953,"rank":2,"rank_change_24h":null,"probability_change_24h":null,"opening_probability":0.235,"opening_american_odds":326,"is_winner":false,"resolution_source":"ungradeable_result","last_updated":"2026-10-08T17:20:59.169116+00:00","price_changed_at":"2026-10-07T17:54:53.214027+00:00"},
    {"id":144903798,"name":"Chennai Super Kings","probability":0.085,"american_odds":1076,"rank":3,"rank_change_24h":null,"probability_change_24h":null,"opening_probability":0.235,"opening_american_odds":326,"is_winner":false,"resolution_source":"ungradeable_result","last_updated":"2026-10-08T17:20:59.169116+00:00","price_changed_at":"2026-09-21T07:52:21.075144+00:00"},
    {"id":144903802,"name":"Lucknow Super Giants","probability":0.085,"american_odds":1076,"rank":4,"rank_change_24h":null,"probability_change_24h":null,"opening_probability":0.185,"opening_american_odds":441,"is_winner":false,"resolution_source":"ungradeable_result","last_updated":"2026-10-08T17:20:59.169116+00:00","price_changed_at":"2026-09-24T03:52:16.057269+00:00"},
    {"id":144903803,"name":"Mumbai Indians","probability":0.085,"american_odds":1076,"rank":5,"rank_change_24h":null,"probability_change_24h":null,"opening_probability":0.185,"opening_american_odds":441,"is_winner":false,"resolution_source":"ungradeable_result","last_updated":"2026-10-08T17:20:59.169116+00:00","price_changed_at":"2026-09-28T15:52:08.575664+00:00"},
    {"id":144903804,"name":"Punjab Kings","probability":0.085,"american_odds":1076,"rank":6,"rank_change_24h":null,"probability_change_24h":null,"opening_probability":0.235,"opening_american_odds":326,"is_winner":false,"resolution_source":"ungradeable_result","last_updated":"2026-10-08T17:20:59.169116+00:00","price_changed_at":"2026-10-08T08:54:33.416833+00:00"},
    {"id":144903800,"name":"Gujarat Titans","probability":0.075,"american_odds":1233,"rank":7,"rank_change_24h":null,"probability_change_24h":null,"opening_probability":0.235,"opening_american_odds":326,"is_winner":false,"resolution_source":"ungradeable_result","last_updated":"2026-10-08T17:20:59.169116+00:00","price_changed_at":"2026-10-08T08:54:33.416833+00:00"},
    {"id":144903805,"name":"Rajasthan Royals","probability":0.07,"american_odds":1329,"rank":8,"rank_change_24h":null,"probability_change_24h":null,"opening_probability":0.5,"opening_american_odds":326,"is_winner":false,"resolution_source":"ungradeable_result","last_updated":"2026-10-08T17:20:59.169116+00:00","price_changed_at":"2026-10-08T08:54:33.416833+00:00"},
    {"id":144903801,"name":"Kolkata Knight Riders","probability":0.065,"american_odds":1438,"rank":9,"rank_change_24h":null,"probability_change_24h":null,"opening_probability":0.185,"opening_american_odds":441,"is_winner":false,"resolution_source":"ungradeable_result","last_updated":"2026-10-08T17:20:59.169116+00:00","price_changed_at":"2026-10-08T17:20:59.169116+00:00"},
    {"id":144903799,"name":"Delhi Capitals","probability":0.035,"american_odds":2757,"rank":10,"rank_change_24h":null,"probability_change_24h":null,"opening_probability":0.5,"opening_american_odds":326,"is_winner":false,"resolution_source":"ungradeable_result","last_updated":"2026-10-08T17:20:59.169116+00:00","price_changed_at":"2026-10-08T17:20:59.169116+00:00"}
    ],
    "outcome_count":10,
    "lead_outcome_id":null,
    "openings_withheld":false,
    "prices_withheld":0,
    "expired_rungs_dropped":0,
    "bookmakers":["kalshi"],
    "category_tags":["cricket","ipl"],
    "created_at":"2026-06-04T06:47:14.194493+00:00",
    "updated_at":"2026-09-26T02:50:41.667719+00:00",
    "group_id":"kalshi:KXIPL-27",
    "canonical_market_key":"cricket:IPL:championship:2027",
    "hook_description":null,
    "hook_withheld":true,
    "image_url":"https://images.pexels.com/photos/36230651/pexels-photo-36230651.jpeg?auto=compress&cs=tinysrgb&h=650&w=940",
    "event_concept_key":null,
    "hub_slug":null,
    "category_page":null,
    "sport_page_key":null,
    "container_of_event_id":null
    }
    """#

    /// `soccer-next-preview-v306/raw/series-62898789-detail.json` (sha256 b8aa4a91f4e5d666499a2942fcfa74d2b13796108cf8cb753c9ffcf524068090): all 4 outcomes.
    static let seriesFinal = #"""
    {
    "id":62898789,
    "name":"Series Exact Score: Chicago WS vs Houston",
    "description":null,
    "sport":null,
    "sport_name":null,
    "category":"championship",
    "llm_sport_category":"baseball",
    "status":"resolved",
    "source":"kalshi",
    "external_id":"KXMLBSERIESSCORE-26CWSHOUWC",
    "market_type":"field",
    "mutually_exclusive":true,
    "commence_time":"2026-10-27T23:00:00+00:00",
    "resolution_date":"2026-10-14T23:00:00+00:00",
    "outcomes":[
    {"id":237333168,"name":"CWS wins 2-0","probability":1.0,"american_odds":null,"rank":1,"rank_change_24h":null,"probability_change_24h":null,"opening_probability":0.215,"opening_american_odds":null,"is_winner":true,"resolution_source":"api_settlement","last_updated":"2026-10-01T01:10:25.557885+00:00","price_changed_at":"2026-10-01T01:10:25.557885+00:00"},
    {"id":237333165,"name":"HOU wins 2-0","probability":0.0,"american_odds":null,"rank":2,"rank_change_24h":null,"probability_change_24h":null,"opening_probability":0.325,"opening_american_odds":null,"is_winner":false,"resolution_source":"api_settlement","last_updated":"2026-10-01T01:10:25.557885+00:00","price_changed_at":"2026-09-30T00:52:53.595264+00:00"},
    {"id":237333166,"name":"HOU wins 2-1","probability":0.0,"american_odds":null,"rank":3,"rank_change_24h":null,"probability_change_24h":null,"opening_probability":0.275,"opening_american_odds":null,"is_winner":false,"resolution_source":"api_settlement","last_updated":"2026-10-01T01:10:25.557885+00:00","price_changed_at":"2026-10-01T01:10:25.557885+00:00"},
    {"id":237333167,"name":"CWS wins 2-1","probability":0.0,"american_odds":null,"rank":4,"rank_change_24h":null,"probability_change_24h":null,"opening_probability":0.235,"opening_american_odds":null,"is_winner":false,"resolution_source":"api_settlement","last_updated":"2026-10-01T01:10:25.557885+00:00","price_changed_at":"2026-10-01T01:10:25.557885+00:00"}
    ],
    "outcome_count":4,
    "lead_outcome_id":null,
    "openings_withheld":false,
    "prices_withheld":0,
    "expired_rungs_dropped":0,
    "bookmakers":["kalshi"],
    "category_tags":["baseball"],
    "created_at":"2026-09-27T22:51:21.381787+00:00",
    "updated_at":"2026-10-01T01:10:25.557885+00:00",
    "group_id":"kalshi:KXMLBSERIESSCORE-26CWSHOUWC",
    "canonical_market_key":"baseball::championship:2026",
    "hook_description":null,
    "hook_withheld":false,
    "image_url":null,
    "event_concept_key":null,
    "hub_slug":null,
    "category_page":null,
    "sport_page_key":null,
    "container_of_event_id":null
    }
    """#

    /// `soccer-next-preview-v306/raw/series-62898789-history.json` (sha256 a3a706d7b1757f7a286a306c6228aca3a7f25fdc9273e35afacfafc2aabab2e5): lines {237333165: (2, 2), 237333168: (2, 2), 237333167: (2, 2), 237333166: (2, 2)} (head, tail); drops ['leaderboard', 'round_boundaries', 'venue_history'].
    static let seriesHistory = #"""
    {
    "market_id":62898789,
    "market_name":"Series Exact Score: Chicago WS vs Houston",
    "hours":720,
    "actual_hours":720,
    "outcomes":[
    {"outcome_id":237333165,"name":"HOU wins 2-0","history":[
    {"timestamp":"2026-09-27T23:50:38.982020+00:00","probability":0.325,"american_odds":null,"bookmaker":"consensus"},
    {"timestamp":"2026-09-28T00:51:44.814840+00:00","probability":0.325,"american_odds":null,"bookmaker":"consensus"},
    {"timestamp":"2026-09-29T23:51:29.387320+00:00","probability":0.03,"american_odds":null,"bookmaker":"consensus"},
    {"timestamp":"2026-09-30T23:52:23.670292+00:00","probability":0.0,"american_odds":null,"bookmaker":"settlement"}
    ],"eliminated":false,"eliminated_at":null},
    {"outcome_id":237333168,"name":"CWS wins 2-0","history":[
    {"timestamp":"2026-09-27T23:50:38.982020+00:00","probability":0.215,"american_odds":null,"bookmaker":"consensus"},
    {"timestamp":"2026-09-28T00:51:44.814840+00:00","probability":0.215,"american_odds":null,"bookmaker":"consensus"},
    {"timestamp":"2026-09-30T23:52:23.670292+00:00","probability":0.7798,"american_odds":null,"bookmaker":"consensus"},
    {"timestamp":"2026-09-30T23:52:24.670292+00:00","probability":1.0,"american_odds":null,"bookmaker":"settlement"}
    ],"eliminated":false,"eliminated_at":null},
    {"outcome_id":237333167,"name":"CWS wins 2-1","history":[
    {"timestamp":"2026-09-27T23:50:38.982020+00:00","probability":0.235,"american_odds":null,"bookmaker":"consensus"},
    {"timestamp":"2026-09-28T00:51:44.814840+00:00","probability":0.235,"american_odds":null,"bookmaker":"consensus"},
    {"timestamp":"2026-09-30T23:52:23.670292+00:00","probability":0.1376,"american_odds":null,"bookmaker":"consensus"},
    {"timestamp":"2026-09-30T23:52:24.670292+00:00","probability":0.0,"american_odds":null,"bookmaker":"settlement"}
    ],"eliminated":false,"eliminated_at":null},
    {"outcome_id":237333166,"name":"HOU wins 2-1","history":[
    {"timestamp":"2026-09-27T23:50:38.982020+00:00","probability":0.275,"american_odds":null,"bookmaker":"consensus"},
    {"timestamp":"2026-09-28T00:51:44.814840+00:00","probability":0.275,"american_odds":null,"bookmaker":"consensus"},
    {"timestamp":"2026-09-30T23:52:23.670292+00:00","probability":0.0826,"american_odds":null,"bookmaker":"consensus"},
    {"timestamp":"2026-09-30T23:52:24.670292+00:00","probability":0.0,"american_odds":null,"bookmaker":"settlement"}
    ],"eliminated":false,"eliminated_at":null}
    ],
    "total_data_points":246,
    "coverage_start":"2026-09-27T23:50:38.982020+00:00",
    "coverage_end":"2026-09-30T23:52:24.670292+00:00",
    "coverage_hours":72.03,
    "observation_times":68
    }
    """#

    /// `volleyball-intake-v347/raw/detail.json` (sha256 6df1538d0911dba77d25e0f158d82e1bfd0ce821220784210d3e223ae7149643): outcomes [227644761, 227644762, 227644779] of 49.
    static let volleyballBefore = #"""
    {
    "id":60775180,
    "name":"Division I Women's Volleyball Champion",
    "description":null,
    "sport":null,
    "sport_name":null,
    "category":"championship",
    "llm_sport_category":"basketball",
    "status":"open",
    "source":"kalshi",
    "external_id":"KXNCAAWV-26",
    "market_type":"field",
    "mutually_exclusive":true,
    "commence_time":"2027-01-07T15:00:00+00:00",
    "resolution_date":"2026-12-21T04:59:59+00:00",
    "outcomes":[
    {"id":227644761,"name":"Nebraska","probability":0.43,"american_odds":125,"rank":1,"rank_change_24h":null,"probability_change_24h":null,"opening_probability":0.37,"opening_american_odds":170,"is_winner":null,"resolution_source":null,"last_updated":"2026-10-15T21:00:26.377069+00:00","price_changed_at":"2026-10-15T20:53:43.586587+00:00"},
    {"id":227644762,"name":"Pittsburgh","probability":0.225,"american_odds":212,"rank":2,"rank_change_24h":null,"probability_change_24h":null,"opening_probability":0.205,"opening_american_odds":388,"is_winner":null,"resolution_source":null,"last_updated":"2026-10-15T21:27:23.638667+00:00","price_changed_at":"2026-10-15T21:27:23.638667+00:00"},
    {"id":227644779,"name":"Texas A&M","probability":0.08,"american_odds":9900,"rank":3,"rank_change_24h":null,"probability_change_24h":null,"opening_probability":null,"opening_american_odds":null,"is_winner":null,"resolution_source":null,"last_updated":"2026-10-14T21:01:59.371327+00:00","price_changed_at":"2026-10-13T19:31:08.822186+00:00"}
    ],
    "outcome_count":49,
    "lead_outcome_id":null,
    "openings_withheld":false,
    "prices_withheld":37,
    "expired_rungs_dropped":0,
    "bookmakers":["kalshi"],
    "category_tags":["basketball"],
    "created_at":"2026-09-11T20:48:24.067433+00:00",
    "updated_at":"2026-10-12T17:35:27.892576+00:00",
    "group_id":"kalshi:KXNCAAWV-26",
    "canonical_market_key":"basketball::championship:2026",
    "hook_description":null,
    "hook_withheld":false,
    "image_url":null,
    "event_concept_key":null,
    "edition_year":null,
    "hub_slug":null,
    "category_page":null,
    "sport_page_key":null,
    "container_of_event_id":null
    }
    """#

    /// `volleyball-intake-v347/raw/history.json` (sha256 444e3d64900eb75c9f194592eee58267422728ed8b415190c4c1a331f68ef214): lines {227644761: (None, None), 227644762: (None, None), 227644779: (None, None)} (all points); drops ['leaderboard', 'round_boundaries', 'venue_history'].
    static let volleyballHistory = #"""
    {
    "market_id":60775180,
    "market_name":"Division I Women's Volleyball Champion",
    "hours":168,
    "actual_hours":720,
    "outcomes":[
    {"outcome_id":227644761,"name":"Nebraska","history":[
    {"timestamp":"2026-09-19T10:47:36.879693+00:00","probability":0.63,"american_odds":null,"bookmaker":"consensus"},
    {"timestamp":"2026-09-25T20:49:31.505270+00:00","probability":0.37,"american_odds":null,"bookmaker":"consensus"},
    {"timestamp":"2026-09-26T04:57:13.952767+00:00","probability":0.365,"american_odds":null,"bookmaker":"consensus"},
    {"timestamp":"2026-10-12T17:32:20.900242+00:00","probability":0.445,"american_odds":null,"bookmaker":"consensus"}
    ],"eliminated":false,"eliminated_at":null},
    {"outcome_id":227644762,"name":"Pittsburgh","history":[
    {"timestamp":"2026-09-19T10:47:36.879693+00:00","probability":0.74,"american_odds":null,"bookmaker":"consensus"},
    {"timestamp":"2026-10-12T17:32:20.900242+00:00","probability":0.32,"american_odds":null,"bookmaker":"consensus"}
    ],"eliminated":false,"eliminated_at":null},
    {"outcome_id":227644779,"name":"Texas A&M","history":[
    {"timestamp":"2026-10-12T17:32:20.900242+00:00","probability":0.01,"american_odds":null,"bookmaker":"consensus"}
    ],"eliminated":false,"eliminated_at":null}
    ],
    "total_data_points":19,
    "coverage_start":"2026-09-19T10:47:36.879693+00:00",
    "coverage_end":"2026-10-12T17:32:20.900242+00:00",
    "coverage_hours":558.75,
    "observation_times":4,
    "auto_extended":true
    }
    """#

    /// `lacrosse-qualification-intake-v351/raw/detail.json` (sha256 aa45397ac57381fa97b921a0e175177da44e929174e282efb8c4635404ef4614): outcomes [235632896, 235632852, 235632875] of 46.
    static let lacrosseQualification = #"""
    {
    "id":62368052,
    "name":"Which countries will qualify for LA28 men's lacrosse?",
    "description":null,
    "sport":null,
    "sport_name":null,
    "category":"championship",
    "llm_sport_category":"lacrosse",
    "status":"open",
    "source":"kalshi",
    "external_id":"KXSOLAXQUAL-28",
    "market_type":"field",
    "mutually_exclusive":false,
    "commence_time":"2028-08-01T14:00:00+00:00",
    "resolution_date":"2028-06-27T14:00:00+00:00",
    "outcomes":[
    {"id":235632896,"name":"South Africa","probability":null,"american_odds":null,"rank":1,"rank_change_24h":null,"probability_change_24h":null,"opening_probability":null,"opening_american_odds":null,"is_winner":null,"resolution_source":null,"last_updated":"2026-09-28T22:51:25.095143+00:00","price_changed_at":null},
    {"id":235632852,"name":"Brazil","probability":null,"american_odds":null,"rank":2,"rank_change_24h":null,"probability_change_24h":null,"opening_probability":null,"opening_american_odds":null,"is_winner":null,"resolution_source":null,"last_updated":"2026-09-28T22:51:25.095143+00:00","price_changed_at":null},
    {"id":235632875,"name":"France","probability":null,"american_odds":null,"rank":3,"rank_change_24h":null,"probability_change_24h":null,"opening_probability":null,"opening_american_odds":null,"is_winner":null,"resolution_source":null,"last_updated":"2026-09-28T22:51:25.095143+00:00","price_changed_at":null}
    ],
    "outcome_count":46,
    "lead_outcome_id":null,
    "openings_withheld":false,
    "prices_withheld":0,
    "expired_rungs_dropped":0,
    "bookmakers":[],
    "category_tags":["lacrosse"],
    "created_at":"2026-09-25T18:48:10.577575+00:00",
    "updated_at":"2026-09-28T22:51:25.095143+00:00",
    "group_id":"kalshi:KXSOLAXQUAL-28",
    "canonical_market_key":null,
    "hook_description":null,
    "hook_withheld":false,
    "image_url":null,
    "event_concept_key":null,
    "edition_year":null,
    "hub_slug":null,
    "category_page":null,
    "sport_page_key":null,
    "container_of_event_id":null
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

    static let enUS = Locale(identifier: "en_US")

    /// The reader's clock and calendar (CONSTRUCTED: Pacific, en_US).
    static func host(_ now: String, cohort: [Int]? = nil,
                     chosen: FieldEventPageAdapter10868.Choice? = nil) -> FieldEventPageAdapter10868.Host {
        FieldEventPageAdapter10868.Host(now: now.asDate!, calendar: pacific, locale: enUS,
                                        cohort: cohort, chosen: chosen)
    }

    /// A CONSTRUCTED held choice on this market's exact identity (its venue key
    /// and market id) for an outcome id — served or not.
    static func choice(_ id: Int, in market: FuturesMarketDetail) -> FieldEventPageAdapter10868.Choice {
        FieldEventPageAdapter10868.Choice(source: FieldEventPageAdapter10868.venueKey(market),
                                          marketID: String(market.id), outcomeID: String(id))
    }

    /// A CONSTRUCTED refresh: the body with exactly one served outcome row
    /// removed — its whole line, proven to occur once and not to be the last row.
    static func omitting(_ json: String, outcome id: Int) -> String {
        let rows = json.components(separatedBy: "\n").filter { $0.hasPrefix("{\"id\":\(id),") }
        precondition(rows.count == 1 && rows[0].hasSuffix(","), "not exactly one non-final row: \(id)")
        return replacing(json, rows[0] + "\n", with: "")
    }

    // MARK: Capture instants (each body's own manifest time)

    static let rugbyCapture = "2026-10-15T21:00:59Z"
    static let chessCapture = "2026-10-15T08:59:00Z"
    static let dartsCapture = "2026-10-11T05:25:18Z"
    static let cricketCapture = "2026-10-11T05:25:18Z"
    static let seriesCapture = "2026-10-12T15:04:25Z"
    static let volleyballCapture = "2026-10-15T21:31:11Z"
    /// CONSTRUCTED reader clocks within the futures stale bound of each body's
    /// served `last_updated` (darts 2026-10-10T11:49:37Z, cricket 2026-10-08T17:20:59Z).
    static let dartsRecentClock = "2026-10-10T12:00:00Z"
    static let cricketRecentClock = "2026-10-08T18:00:00Z"

    // MARK: Served outcome ids

    static let ireland = 225917124
    static let southAfrica = 225917112
    static let france = 225917111
    static let newZealand = 225917113
    static let england = 225917131
    /// Served on the board, with no line in the real `/history` body at all.
    static let scotland = 225917125
    static let aliceLee = 235705516
    static let rachaelLi = 235705523
    static let thaliaCervantes = 235705519
    static let annaSargsyan = 235705522
    static let tatevAbrahamyan = 235705525
    static let carissaYip = 235705515
    static let littler = 206766142
    static let cwsTwoNil = 237333168
    static let houTwoNil = 237333165
    static let houTwoOne = 237333166
    static let texasAM = 227644779
}

/// #10868 — part one (`FieldEventPageAdapter10868`): phase, contender words,
/// the catalogue, the displayed contenders and the named-chance headline, on the
/// retained real bodies above. PREPARED / NOT RUN.
@MainActor
final class FieldEventPageAdapter10868Tests: XCTestCase {
    private typealias A = FieldEventPageAdapter10868
    private typealias F = FieldEventAdapterFixtures10868

    private func clock(_ iso: String, _ host: A.Host) -> String {
        A.clockWords(iso.asDate!, host: host)
    }

    private func figures(_ input: FieldHeadlineInput10868) -> [[String?]] {
        FieldHeadlineModel10868(input).competitors.map { $0.metrics.map(FieldChaseModel10868.figure) }
    }

    private func words(_ input: FieldHeadlineInput10868) -> [[String?]] {
        FieldHeadlineModel10868(input).competitors.map { $0.metrics.map(FieldChaseModel10868.words) }
    }

    private func plan(_ input: FieldHeadlineInput10868, _ id: Int) throws -> FieldChooserDisplayPlan10868 {
        try XCTUnwrap(input.catalogue.first { $0.ref.outcomeID == String(id) }).plan
    }

    // MARK: Phase and words

    func testAnOpenFieldIsBeforeAndOnlyAResolvedOneIsFinal() throws {
        for body in [F.rugbyBefore, F.chessBefore, F.dartsBefore, F.cricketBefore] {
            XCTAssertEqual(A.phase(try F.market(body)), .before)
        }
        XCTAssertEqual(A.phase(try F.market(F.seriesFinal)), .final)
    }

    func testTheContenderWordComesFromServedFieldsForProvenCategoriesOnly() throws {
        XCTAssertEqual(A.contender(try F.market(F.cricketBefore)), .team)
        XCTAssertEqual(A.contender(try F.market(F.rugbyBefore)), .team)
        XCTAssertEqual(A.contender(try F.market(F.dartsBefore)), .player)
        XCTAssertEqual(A.contender(try F.market(F.chessBefore)), .player)
        // A championship board of a team sport whose outcomes are exact scores.
        XCTAssertEqual(A.contender(try F.market(F.seriesFinal)), .contender)
        // The volleyball board is served as basketball: no word is guessed from its name.
        XCTAssertEqual(A.contender(try F.market(F.volleyballBefore)), .contender)
        XCTAssertEqual(A.sportWords(try F.market(F.rugbyBefore)), "Rugby")
        XCTAssertEqual(A.sportWords(try F.market(F.dartsBefore)), "Darts")
        XCTAssertEqual(A.sportWords(try F.market(F.volleyballBefore)), "Basketball")
    }

    // MARK: Before — each contender's own recent chance

    func testEachDisplayedTeamShowsItsOwnRecentChanceWithItsOwnClock() throws {
        let market = try F.market(F.rugbyBefore)
        let host = F.host(F.rugbyCapture)
        let input = A.headline(market, host: host)
        XCTAssertEqual(input.phase, .before)
        XCTAssertEqual(input.scope, "field:60473053:before:contenders")
        // The production chart's default: the first three served outcomes.
        XCTAssertEqual(input.displayed.map(\.name), ["Ireland", "South Africa", "France"])
        XCTAssertEqual(input.displayed.map(\.ref.outcomeID), ["225917124", "225917112", "225917111"])
        XCTAssertEqual(Set(input.displayed.map(\.ref.source)), ["kalshi"])
        XCTAssertEqual(input.displayed.map(\.keyShape), [.circle, .diamond, .square])
        XCTAssertEqual(input.displayed.map(\.compactName), [nil, nil, nil])
        XCTAssertEqual(figures(input), [["59%"], ["40%"], ["6%"]])
        XCTAssertEqual(try plan(input, F.ireland), .single(FieldChooserReading10868(
            label: "Win chance",
            value: .recorded(text: "59%", detail: "\(clock("2026-10-15T20:54:48.335080+00:00", host)) · Kalshi"))))
        // Each raw value is its own: never normalized, summed or complemented.
        XCTAssertEqual(input.pairs.compactMap { $0.before?.probability }, [0.59, 0.4, 0.06])
        XCTAssertEqual(input.pairs.compactMap(\.later).count, 0)
        XCTAssertEqual(input.finishes, [])
        XCTAssertNil(input.state)
        // No start reaches the app: keys stay neutral and recorded.
        XCTAssertEqual(input.keyTreatment, .neutralRecorded)
        XCTAssertFalse(FieldHeadlineModel10868(input).keyIsHollow)
        XCTAssertEqual(input.copy.eyebrow, "Rugby · Recorded probabilities")
        XCTAssertEqual(input.copy.title, "2027 Men's Rugby World Cup Winner")
        XCTAssertEqual(input.copy.beforeLabel, "Win chance")
        XCTAssertEqual(input.copy.empty, "No teams in this update")
        XCTAssertEqual(input.unavailableWords, "Team unavailable in this update")
        XCTAssertEqual(input.copy.openHint, "Opens this team’s win history")
    }

    func testEveryServedOutcomeIsInTheCatalogueOnceInServedOrder() throws {
        let market = try F.market(F.rugbyBefore)
        let input = A.headline(market, host: F.host(F.rugbyCapture))
        XCTAssertEqual(input.catalogue.count, 24)
        XCTAssertEqual(input.catalogue.map(\.name), market.outcomes.map(\.name))
        XCTAssertEqual(Set(input.catalogue.map(\.ref)).count, 24)
        // Only displayed contenders carry a chart colour.
        XCTAssertEqual(input.catalogue.prefix(3).filter { $0.accent != nil }.count, 3)
        XCTAssertEqual(input.catalogue.dropFirst(3).filter { $0.accent != nil }.count, 0)
        XCTAssertEqual(input.catalogue.compactMap(\.result).count, 0)
        // A served null is unavailable, never 0%.
        XCTAssertEqual(try plan(input, F.scotland), .single(FieldChooserReading10868(
            label: "Win chance", value: .missing(AllMarketsCatalogView9483.unavailablePrice))))
    }

    func testAnUnpricedOrStaleChessRowIsNeverACurrentChance() throws {
        let market = try F.market(F.chessBefore)
        let host = F.host(F.chessCapture)
        let input = A.headline(market, host: host)
        XCTAssertEqual(input.displayed.map(\.name), ["Alice Lee", "Rachael Li", "Thalia Cervantes"])
        XCTAssertEqual(figures(input), [["86%"], ["11%"], ["10%"]])
        XCTAssertEqual(input.copy.empty, "No players in this update")
        XCTAssertEqual(input.unavailableWords, "Player unavailable in this update")
        // Served null.
        XCTAssertEqual(try plan(input, F.annaSargsyan), .single(FieldChooserReading10868(
            label: "Win chance", value: .missing(AllMarketsCatalogView9483.unavailablePrice))))
        // Written 11 h 13 m before the capture: older than the futures bound.
        XCTAssertEqual(try plan(input, F.tatevAbrahamyan), .single(FieldChooserReading10868(
            label: "Win chance", value: .missing(AllMarketsCatalogView9483.noRecentPrice))))
        // Written 65 minutes before: recent, and a real 1% is printed as 1%.
        XCTAssertEqual(try plan(input, F.carissaYip), .single(FieldChooserReading10868(
            label: "Win chance",
            value: .recorded(text: "1%", detail: "\(clock("2026-10-15T07:54:10.466050+00:00", host)) · Kalshi"))))
    }

    func testEveryDartsReadingOlderThanTheBoundSaysNoRecentProbability() throws {
        let market = try F.market(F.dartsBefore)
        // At the capture every served value is 17 h 36 m old.
        let atCapture = A.headline(market, host: F.host(F.dartsCapture))
        XCTAssertEqual(atCapture.displayed.map(\.name), ["Luke Littler", "Luke Humphries", "James Wade"])
        XCTAssertEqual(figures(atCapture), [[nil], [nil], [nil]])
        let stale: [String?] = [AllMarketsCatalogView9483.noRecentPrice]
        XCTAssertEqual(words(atCapture), [stale, stale, stale])
        XCTAssertEqual(atCapture.pairs.compactMap(\.before).count, 0)
        // CONSTRUCTED reader clock ten minutes after the served write: recent.
        let recent = A.headline(market, host: F.host(F.dartsRecentClock))
        XCTAssertEqual(figures(recent), [["50%"], ["16%"], ["6%"]])
        XCTAssertEqual(recent.pairs.compactMap { $0.before?.probability }, [0.4955, 0.1607, 0.0625])
        // One second inside the bound is recent; one second past it is not.
        let written = "2026-10-10T11:49:37.412255+00:00".asDate!
        let inside = A.Host(now: written.addingTimeInterval(SourceAge.futuresStaleAfter - 1), calendar: F.pacific, locale: F.enUS)
        let past = A.Host(now: written.addingTimeInterval(SourceAge.futuresStaleAfter + 1), calendar: F.pacific, locale: F.enUS)
        XCTAssertEqual(figures(A.headline(market, host: inside)).first, ["50%"])
        XCTAssertEqual(figures(A.headline(market, host: past)).first, [nil])
    }

    func testARetractedGradeOnAnOpenCricketBoardStaysAPriceNeverALoss() throws {
        let market = try F.market(F.cricketBefore)
        // Every row is served `is_winner: false, resolution_source: "ungradeable_result"`.
        XCTAssertEqual(market.outcomes.compactMap(\.resolutionSource), Array(repeating: "ungradeable_result", count: 10))
        let input = A.headline(market, host: F.host(F.cricketRecentClock))
        XCTAssertEqual(input.displayed.map(\.name), ["Royal Challengers Bengaluru", "Sunrisers Hyderabad", "Chennai Super Kings"])
        XCTAssertEqual(figures(input), [["28%"], ["10%"], ["9%"]])
        XCTAssertEqual(input.catalogue.compactMap(\.result).count, 0)
        XCTAssertEqual(input.copy.eyebrow, "Cricket · Recorded probabilities")
    }

    // MARK: The cohort

    func testTheChosenContenderLeadsThenServedOrderFillsToThree() throws {
        let market = try F.market(F.rugbyBefore)
        let chosen = A.headline(market, host: F.host(F.rugbyCapture, chosen: F.choice(F.england, in: market)))
        XCTAssertEqual(chosen.displayed.map(\.name), ["England", "Ireland", "South Africa"])
        XCTAssertEqual(chosen.displayed.map(\.keyShape), [.circle, .diamond, .square])
        XCTAssertEqual(figures(chosen), [["1%"], ["59%"], ["40%"]])
        XCTAssertEqual(chosen.unavailableWords, "Team unavailable in this update")
        // CONSTRUCTED held cohort: kept in its order, once each, served ids only.
        let held = A.headline(market, host: F.host(F.rugbyCapture, cohort: [F.france, F.ireland, F.france, 999],
                                                    chosen: F.choice(F.england, in: market)))
        XCTAssertEqual(held.displayed.map(\.name), ["France", "Ireland"])
    }

    func testAChoiceThisUpdateDoesNotServeKeepsTheFirstSlotUnavailableAndPromotesNoOne() throws {
        let market = try F.market(F.rugbyBefore)
        // CONSTRUCTED: this board's own identity with an outcome id it does not serve.
        let missing = A.headline(market, host: F.host(F.rugbyCapture, chosen: F.choice(999, in: market)))
        XCTAssertEqual(missing.displayed.map(\.ref.outcomeID), ["999", String(F.ireland), String(F.southAfrica)])
        XCTAssertEqual(missing.displayed.map(\.name), ["", "Ireland", "South Africa"])
        XCTAssertEqual(missing.displayed.map(\.keyShape), [.circle, .diamond, .square])
        XCTAssertEqual(missing.pairs.map(\.ref.outcomeID), [String(F.ireland), String(F.southAfrica)])
        XCTAssertEqual(missing.unavailableWords, "Chosen team unavailable in this update")
        let model = FieldHeadlineModel10868(missing)
        XCTAssertEqual(model.competitors[0].resolution, .unavailable)
        XCTAssertTrue(model.competitors[0].metrics.isEmpty, "no figure for the omitted choice")
        XCTAssertEqual(model.competitorSummary(model.competitors[0]), "Chosen team unavailable in this update")
        XCTAssertEqual(figures(missing), [[], ["59%"], ["40%"]])
        // The two served teams keep the catalogue colours of their display positions.
        let ireland = try XCTUnwrap(missing.catalogue.first { $0.ref.outcomeID == String(F.ireland) })
        XCTAssertEqual(ireland.accent, A.tint(1))
        XCTAssertNil(missing.catalogue.first { $0.ref.outcomeID == String(F.france) }?.accent)
        // CONSTRUCTED: another market's choice with an outcome id this board serves is no choice here.
        let foreign = A.Choice(source: "kalshi", marketID: "62383719", outcomeID: String(F.england))
        let other = A.headline(market, host: F.host(F.rugbyCapture, chosen: foreign))
        XCTAssertEqual(other.displayed.map(\.name), ["Ireland", "South Africa", "France"])
        XCTAssertEqual(other.unavailableWords, "Team unavailable in this update")
    }

    // MARK: Final — a settled value is a result

    func testAtTheFinalASettledValueIsAResultNeverAChance() throws {
        let market = try F.market(F.seriesFinal)
        let input = A.headline(market, host: F.host(F.seriesCapture))
        XCTAssertEqual(input.phase, .final)
        XCTAssertEqual(input.scope, "field:62898789:final:contenders")
        XCTAssertEqual(input.displayed.map(\.name), ["CWS wins 2-0", "HOU wins 2-0", "HOU wins 2-1"])
        // No figure: the served 1.0 / 0.0 are the settlement, and no start elects a pre-event reading.
        XCTAssertEqual(figures(input), [[nil, nil], [nil, nil], [nil, nil]])
        let slot: [String?] = ["Pre-event chance unavailable", "Final placing unavailable"]
        XCTAssertEqual(words(input), [slot, slot, slot])
        XCTAssertEqual(input.pairs.compactMap(\.before).count, 0)
        XCTAssertEqual(input.catalogue.map { $0.result?.words }, ["Won", "Lost", "Lost", "Lost"])
        XCTAssertEqual(Set(input.catalogue.compactMap { $0.result?.title }), ["Result"])
        XCTAssertEqual(input.copy.eyebrow, "Baseball · Settled market")
        XCTAssertEqual(input.copy.beforeLabel, "Pre-event win")
        XCTAssertEqual(input.copy.finishLabel, "Final placing")
        XCTAssertEqual(input.keyTreatment, .neutralRecorded)
    }

    // MARK: Reader heading and About

    func testTheReaderHeadingAndAboutSayWhatThePageReads() throws {
        let rugby = try F.market(F.rugbyBefore)
        XCTAssertEqual(A.readerHeader(rugby), FieldEventPageReaderHeader10868(
            title: "2027 Men's Rugby World Cup Winner", state: "Recorded win chances"))
        let about = A.about(rugby)
        XCTAssertEqual(about.title, "How these chances are recorded")
        XCTAssertEqual(about.paragraphs.count, 3)
        XCTAssertTrue(about.paragraphs[0].contains("Each team’s chance is that team’s own Kalshi probability"))
        XCTAssertTrue(about.paragraphs[0].contains("not adjusted to add up to 100%"))
        XCTAssertTrue(about.paragraphs[2].contains("last 6 hours"))
        let series = try F.market(F.seriesFinal)
        XCTAssertEqual(A.readerHeader(series).state, "Settled market")
        let final = A.about(series)
        XCTAssertEqual(final.paragraphs.count, 4)
        XCTAssertTrue(final.paragraphs[3].contains("Results come only from Kalshi’s settlement"))
        // No reader word is a pipeline word.
        for words in about.paragraphs + final.paragraphs {
            for banned in ["served", "admitted", "withheld", "payload", "price"] {
                XCTAssertFalse(words.lowercased().contains(banned), "\(banned) in \(words)")
            }
        }
    }
}
