import Foundation

/// The 2026-09-05 production `GET /api/events/search?q=US Open` payload, verbatim.
///
/// Captured for #3124 — `SearchResponse` decoded neither `event_concepts` nor
/// `futures_families`, so the server did the grouping and the phone threw it
/// away, drawing 10 sibling futures rows where the payload describes
/// 1 family and 4 concepts. This is that measurement made
/// permanent, so the class of defect — a wire shape the model does not name,
/// dropped in silence by `Decodable` — is caught by the suite and not by a
/// person searching for a tournament during that tournament.
///
/// WHY VERBATIM: the defect was keys the decoder did not expect. Any trimming is
/// a guess about which keys matter, made by the judgement that already missed
/// two. Nothing is stripped — not `pagination`, not the empty `teams`/`results`,
/// not the `american_odds` the app never prints.
///
/// As served: 0 events, 0 teams, 10 flat futures,
/// 4 event concepts, 1 futures family.
/// The family is `story:grand_slam_tennis` ("Grand Slam Tennis"):
/// headline 34277822 + 4 members, `more_count` 4,
/// `member_count` 19. All 5 of its shown markets are also in the
/// flat ten, which is exactly why the phone drew them twice.
///
/// WHAT THIS FIXTURE CANNOT PROVE, stated so nobody reads more into it: every one
/// of its four `event_concepts` points at a market the page already draws, so it
/// pins the duplicate-suppressing branch of `novelConcepts` and NOT the branch
/// that surfaces a novel concept. That branch is covered by a synthetic case,
/// and no live query has yet been found that exercises it (eight measured).
enum SearchProdFixture {
    static let usOpenJSON = #"""
{
  "query": "US Open",
  "teams": [],
  "event_concepts": [
    {
      "key": "event:tennis:us-open-men-s-singles-winner",
      "name": "US Open Men's Singles",
      "domain": "tennis",
      "market_id": 34277822
    },
    {
      "key": "event:tennis:2026-women-s-us-open-winner-tennis",
      "name": "2026 Women’s US Open Winner (Tennis)",
      "domain": "tennis",
      "market_id": 114160
    },
    {
      "key": "event:tennis:2026-men-s-us-open-winner-tennis",
      "name": "2026 Men’s US Open Winner (Tennis)",
      "domain": "tennis",
      "market_id": 114159
    },
    {
      "key": "event:tennis:us-open-women-s-singles-winner",
      "name": "US Open Women's Singles",
      "domain": "tennis",
      "market_id": 34277839
    }
  ],
  "results": [],
  "futures": [
    {
      "id": 34277822,
      "name": "US Open Men's Singles Winner",
      "sport": null,
      "sport_name": null,
      "category": "championship",
      "llm_sport_category": "tennis",
      "market_tier": 1,
      "market_type_label": "Championship",
      "status": "open",
      "source": "kalshi",
      "resolution_date": "2026-09-28T02:00:00+00:00",
      "top_outcomes": [
        {
          "id": 152600805,
          "name": "Carlos Alcaraz",
          "probability": 0.455,
          "american_odds": 120,
          "rank": 1,
          "movement": null
        },
        {
          "id": 152600808,
          "name": "Alexander Zverev",
          "probability": 0.205,
          "american_odds": 388,
          "rank": 2,
          "movement": null
        },
        {
          "id": 206838311,
          "name": "Taylor Fritz",
          "probability": 0.105,
          "american_odds": 852,
          "rank": 3,
          "movement": null
        },
        {
          "id": 152600813,
          "name": "Ben Shelton",
          "probability": 0.095,
          "american_odds": 953,
          "rank": 4,
          "movement": null
        },
        {
          "id": 152600810,
          "name": "Daniil Medvedev",
          "probability": 0.055,
          "american_odds": 1718,
          "rank": 5,
          "movement": null
        }
      ],
      "outcome_count": 48,
      "updated_at": "2026-09-05T07:12:10.833681+00:00"
    },
    {
      "id": 114160,
      "name": "2026 Women’s US Open Winner (Tennis)",
      "sport": null,
      "sport_name": null,
      "category": "championship",
      "llm_sport_category": "tennis",
      "market_tier": 1,
      "market_type_label": "Championship",
      "status": "open",
      "source": "polymarket",
      "resolution_date": "2026-09-13T00:00:00+00:00",
      "top_outcomes": [
        {
          "id": 1632749,
          "name": "Aryna Sabalenka",
          "probability": 0.24,
          "american_odds": 317,
          "rank": 1,
          "movement": null
        },
        {
          "id": 1632754,
          "name": "Coco Gauff",
          "probability": 0.184,
          "american_odds": 443,
          "rank": 4,
          "movement": null
        },
        {
          "id": 1632750,
          "name": "Iga Swiatek",
          "probability": 0.145,
          "american_odds": 590,
          "rank": 2,
          "movement": null
        },
        {
          "id": 1632773,
          "name": "Jessica Pegula",
          "probability": 0.085,
          "american_odds": 1076,
          "rank": 8,
          "movement": null
        }
      ],
      "outcome_count": 41,
      "updated_at": "2026-09-04T12:52:30.289795+00:00"
    },
    {
      "id": 114159,
      "name": "2026 Men’s US Open Winner (Tennis)",
      "sport": null,
      "sport_name": null,
      "category": "championship",
      "llm_sport_category": "tennis",
      "market_tier": 1,
      "market_type_label": "Championship",
      "status": "open",
      "source": "polymarket",
      "resolution_date": "2026-09-13T00:00:00+00:00",
      "top_outcomes": [
        {
          "id": 1632728,
          "name": "Carlos Alcaraz",
          "probability": 0.455,
          "american_odds": 120,
          "rank": 2,
          "movement": null
        },
        {
          "id": 1632731,
          "name": "Alexander Zverev",
          "probability": 0.203,
          "american_odds": 393,
          "rank": 3,
          "movement": null
        },
        {
          "id": 1632735,
          "name": "Taylor Fritz",
          "probability": 0.1005,
          "american_odds": 895,
          "rank": 6,
          "movement": null
        },
        {
          "id": 1632730,
          "name": "Ben Shelton",
          "probability": 0.086,
          "american_odds": 1063,
          "rank": 5,
          "movement": null
        }
      ],
      "outcome_count": 23,
      "updated_at": "2026-09-04T12:30:00.737177+00:00"
    },
    {
      "id": 34277839,
      "name": "US Open Women's Singles Winner",
      "sport": null,
      "sport_name": null,
      "category": "championship",
      "llm_sport_category": "tennis",
      "market_tier": 1,
      "market_type_label": "Championship",
      "status": "open",
      "source": "kalshi",
      "resolution_date": "2026-09-27T02:00:00+00:00",
      "top_outcomes": [
        {
          "id": 152600872,
          "name": "Aryna Sabalenka",
          "probability": 0.235,
          "american_odds": 326,
          "rank": 1,
          "movement": null
        },
        {
          "id": 152600880,
          "name": "Coco Gauff",
          "probability": 0.185,
          "american_odds": 441,
          "rank": 2,
          "movement": null
        },
        {
          "id": 206838394,
          "name": "Iga Swiatek",
          "probability": 0.135,
          "american_odds": 641,
          "rank": 3,
          "movement": null
        },
        {
          "id": 152600875,
          "name": "Jessica Pegula",
          "probability": 0.085,
          "american_odds": 1076,
          "rank": 4,
          "movement": null
        },
        {
          "id": 152600873,
          "name": "Elena Rybakina",
          "probability": 0.065,
          "american_odds": 1438,
          "rank": 5,
          "movement": null
        }
      ],
      "outcome_count": 30,
      "updated_at": "2026-09-05T07:12:10.833681+00:00"
    },
    {
      "id": 7,
      "name": "US Open Winner",
      "sport": null,
      "sport_name": null,
      "category": "championship",
      "llm_sport_category": "golf",
      "market_tier": 1,
      "market_type_label": "Championship",
      "status": "open",
      "source": "odds_api",
      "resolution_date": null,
      "top_outcomes": [
        {
          "id": 546,
          "name": "Scottie Scheffler",
          "probability": 0.1303,
          "american_odds": 667,
          "rank": 1,
          "movement": null
        },
        {
          "id": 547,
          "name": "Rory McIlroy",
          "probability": 0.0762,
          "american_odds": 1213,
          "rank": 2,
          "movement": null
        },
        {
          "id": 549,
          "name": "Jon Rahm",
          "probability": 0.0498,
          "american_odds": 1910,
          "rank": 3,
          "movement": null
        },
        {
          "id": 550,
          "name": "Xander Schauffele",
          "probability": 0.0402,
          "american_odds": 2390,
          "rank": 4,
          "movement": null
        },
        {
          "id": 552,
          "name": "Ludvig Aberg",
          "probability": 0.0355,
          "american_odds": 2720,
          "rank": 5,
          "movement": null
        }
      ],
      "outcome_count": 205,
      "updated_at": "2026-09-05T08:32:50.861922+00:00"
    },
    {
      "id": 59559187,
      "name": "Will Jasmine Paolini advance to the Quarterfinals in Women's Singles at the 2026 US Open?",
      "sport": null,
      "sport_name": null,
      "category": "game_prop",
      "llm_sport_category": "tennis",
      "market_tier": 2,
      "market_type_label": "Conference",
      "status": "open",
      "source": "polymarket",
      "resolution_date": "2026-09-09T23:59:00+00:00",
      "top_outcomes": [
        {
          "id": 221667274,
          "name": "No",
          "probability": 0.91,
          "american_odds": -1011,
          "rank": 2,
          "movement": null
        },
        {
          "id": 221667273,
          "name": "Yes",
          "probability": 0.09,
          "american_odds": 1011,
          "rank": 1,
          "movement": null
        }
      ],
      "outcome_count": 2,
      "updated_at": "2026-09-05T08:50:00.384292+00:00"
    },
    {
      "id": 59556735,
      "name": "Will Carlos Alcaraz advance to the Semifinals in Men's Singles at the 2026 US Open?",
      "sport": null,
      "sport_name": null,
      "category": "game_prop",
      "llm_sport_category": "tennis",
      "market_tier": 2,
      "market_type_label": "Conference",
      "status": "open",
      "source": "polymarket",
      "resolution_date": "2026-09-10T23:59:00+00:00",
      "top_outcomes": [
        {
          "id": 221650932,
          "name": "Yes",
          "probability": 0.675,
          "american_odds": -208,
          "rank": 1,
          "movement": 0.085
        },
        {
          "id": 221650933,
          "name": "No",
          "probability": 0.325,
          "american_odds": 208,
          "rank": 2,
          "movement": null
        }
      ],
      "outcome_count": 2,
      "updated_at": "2026-09-05T08:42:04.441052+00:00"
    },
    {
      "id": 59556738,
      "name": "Will Flavio Cobolli advance to the Semifinals in Men's Singles at the 2026 US Open?",
      "sport": null,
      "sport_name": null,
      "category": "game_prop",
      "llm_sport_category": "tennis",
      "market_tier": 2,
      "market_type_label": "Conference",
      "status": "open",
      "source": "polymarket",
      "resolution_date": "2026-09-10T23:59:00+00:00",
      "top_outcomes": [
        {
          "id": 221650939,
          "name": "No",
          "probability": 0.91,
          "american_odds": -1011,
          "rank": 2,
          "movement": null
        },
        {
          "id": 221650938,
          "name": "Yes",
          "probability": 0.09,
          "american_odds": 1011,
          "rank": 1,
          "movement": null
        }
      ],
      "outcome_count": 2,
      "updated_at": "2026-09-05T08:42:04.441052+00:00"
    },
    {
      "id": 59556741,
      "name": "Will Ben Shelton advance to the Semifinals in Men's Singles at the 2026 US Open?",
      "sport": null,
      "sport_name": null,
      "category": "game_prop",
      "llm_sport_category": "tennis",
      "market_tier": 2,
      "market_type_label": "Conference",
      "status": "open",
      "source": "polymarket",
      "resolution_date": "2026-09-10T23:59:00+00:00",
      "top_outcomes": [
        {
          "id": 221650945,
          "name": "No",
          "probability": 0.78,
          "american_odds": -355,
          "rank": 2,
          "movement": null
        },
        {
          "id": 221650944,
          "name": "Yes",
          "probability": 0.22,
          "american_odds": 355,
          "rank": 1,
          "movement": 0.015
        }
      ],
      "outcome_count": 2,
      "updated_at": "2026-09-05T08:42:04.441052+00:00"
    },
    {
      "id": 59556742,
      "name": "Will Taylor Fritz advance to the Semifinals in Men's Singles at the 2026 US Open?",
      "sport": null,
      "sport_name": null,
      "category": "game_prop",
      "llm_sport_category": "tennis",
      "market_tier": 2,
      "market_type_label": "Conference",
      "status": "open",
      "source": "polymarket",
      "resolution_date": "2026-09-10T23:59:00+00:00",
      "top_outcomes": [
        {
          "id": 221650946,
          "name": "Yes",
          "probability": 0.545,
          "american_odds": -120,
          "rank": 1,
          "movement": 0.005
        },
        {
          "id": 221650947,
          "name": "No",
          "probability": 0.455,
          "american_odds": 120,
          "rank": 2,
          "movement": null
        }
      ],
      "outcome_count": 2,
      "updated_at": "2026-09-05T08:42:04.441052+00:00"
    }
  ],
  "futures_families": [
    {
      "family_key": "story:grand_slam_tennis",
      "label": "Grand Slam Tennis",
      "headline": {
        "id": 34277822,
        "name": "US Open Men's Singles Winner",
        "sport": null,
        "sport_name": null,
        "category": "championship",
        "llm_sport_category": "tennis",
        "market_tier": 1,
        "market_type_label": "Championship",
        "status": "open",
        "source": "kalshi",
        "resolution_date": "2026-09-28T02:00:00+00:00",
        "top_outcomes": [
          {
            "id": 152600805,
            "name": "Carlos Alcaraz",
            "probability": 0.455,
            "american_odds": 120,
            "rank": 1,
            "movement": null
          },
          {
            "id": 152600808,
            "name": "Alexander Zverev",
            "probability": 0.205,
            "american_odds": 388,
            "rank": 2,
            "movement": null
          },
          {
            "id": 206838311,
            "name": "Taylor Fritz",
            "probability": 0.105,
            "american_odds": 852,
            "rank": 3,
            "movement": null
          },
          {
            "id": 152600813,
            "name": "Ben Shelton",
            "probability": 0.095,
            "american_odds": 953,
            "rank": 4,
            "movement": null
          },
          {
            "id": 152600810,
            "name": "Daniil Medvedev",
            "probability": 0.055,
            "american_odds": 1718,
            "rank": 5,
            "movement": null
          }
        ],
        "outcome_count": 48,
        "updated_at": "2026-09-05T07:12:10.833681+00:00"
      },
      "members": [
        {
          "id": 114160,
          "name": "2026 Women’s US Open Winner (Tennis)",
          "sport": null,
          "sport_name": null,
          "category": "championship",
          "llm_sport_category": "tennis",
          "market_tier": 1,
          "market_type_label": "Championship",
          "status": "open",
          "source": "polymarket",
          "resolution_date": "2026-09-13T00:00:00+00:00",
          "top_outcomes": [
            {
              "id": 1632749,
              "name": "Aryna Sabalenka",
              "probability": 0.24,
              "american_odds": 317,
              "rank": 1,
              "movement": null
            },
            {
              "id": 1632754,
              "name": "Coco Gauff",
              "probability": 0.184,
              "american_odds": 443,
              "rank": 4,
              "movement": null
            },
            {
              "id": 1632750,
              "name": "Iga Swiatek",
              "probability": 0.145,
              "american_odds": 590,
              "rank": 2,
              "movement": null
            },
            {
              "id": 1632773,
              "name": "Jessica Pegula",
              "probability": 0.085,
              "american_odds": 1076,
              "rank": 8,
              "movement": null
            }
          ],
          "outcome_count": 41,
          "updated_at": "2026-09-04T12:52:30.289795+00:00"
        },
        {
          "id": 114159,
          "name": "2026 Men’s US Open Winner (Tennis)",
          "sport": null,
          "sport_name": null,
          "category": "championship",
          "llm_sport_category": "tennis",
          "market_tier": 1,
          "market_type_label": "Championship",
          "status": "open",
          "source": "polymarket",
          "resolution_date": "2026-09-13T00:00:00+00:00",
          "top_outcomes": [
            {
              "id": 1632728,
              "name": "Carlos Alcaraz",
              "probability": 0.455,
              "american_odds": 120,
              "rank": 2,
              "movement": null
            },
            {
              "id": 1632731,
              "name": "Alexander Zverev",
              "probability": 0.203,
              "american_odds": 393,
              "rank": 3,
              "movement": null
            },
            {
              "id": 1632735,
              "name": "Taylor Fritz",
              "probability": 0.1005,
              "american_odds": 895,
              "rank": 6,
              "movement": null
            },
            {
              "id": 1632730,
              "name": "Ben Shelton",
              "probability": 0.086,
              "american_odds": 1063,
              "rank": 5,
              "movement": null
            }
          ],
          "outcome_count": 23,
          "updated_at": "2026-09-04T12:30:00.737177+00:00"
        },
        {
          "id": 34277839,
          "name": "US Open Women's Singles Winner",
          "sport": null,
          "sport_name": null,
          "category": "championship",
          "llm_sport_category": "tennis",
          "market_tier": 1,
          "market_type_label": "Championship",
          "status": "open",
          "source": "kalshi",
          "resolution_date": "2026-09-27T02:00:00+00:00",
          "top_outcomes": [
            {
              "id": 152600872,
              "name": "Aryna Sabalenka",
              "probability": 0.235,
              "american_odds": 326,
              "rank": 1,
              "movement": null
            },
            {
              "id": 152600880,
              "name": "Coco Gauff",
              "probability": 0.185,
              "american_odds": 441,
              "rank": 2,
              "movement": null
            },
            {
              "id": 206838394,
              "name": "Iga Swiatek",
              "probability": 0.135,
              "american_odds": 641,
              "rank": 3,
              "movement": null
            },
            {
              "id": 152600875,
              "name": "Jessica Pegula",
              "probability": 0.085,
              "american_odds": 1076,
              "rank": 4,
              "movement": null
            },
            {
              "id": 152600873,
              "name": "Elena Rybakina",
              "probability": 0.065,
              "american_odds": 1438,
              "rank": 5,
              "movement": null
            }
          ],
          "outcome_count": 30,
          "updated_at": "2026-09-05T07:12:10.833681+00:00"
        },
        {
          "id": 59559187,
          "name": "Will Jasmine Paolini advance to the Quarterfinals in Women's Singles at the 2026 US Open?",
          "sport": null,
          "sport_name": null,
          "category": "game_prop",
          "llm_sport_category": "tennis",
          "market_tier": 2,
          "market_type_label": "Conference",
          "status": "open",
          "source": "polymarket",
          "resolution_date": "2026-09-09T23:59:00+00:00",
          "top_outcomes": [
            {
              "id": 221667274,
              "name": "No",
              "probability": 0.91,
              "american_odds": -1011,
              "rank": 2,
              "movement": null
            },
            {
              "id": 221667273,
              "name": "Yes",
              "probability": 0.09,
              "american_odds": 1011,
              "rank": 1,
              "movement": null
            }
          ],
          "outcome_count": 2,
          "updated_at": "2026-09-05T08:50:00.384292+00:00"
        }
      ],
      "more_count": 4,
      "member_count": 19
    }
  ],
  "pagination": {
    "page": 1,
    "per_page": 25,
    "total_results": 0,
    "total_pages": 0,
    "has_next": false,
    "has_prev": false
  },
  "sports": [],
  "filters": {
    "sport": null,
    "days_back": 30,
    "include_upcoming": true
  }
}
"""#
}
