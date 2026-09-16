import Foundation

/// A verbatim slice of production `GET /api/feed?sport=ufc&limit=50&offset=0`,
/// captured 2026-09-15 while Alex's UFC card was opening to a blank white page
/// (#1471 / #6444). Four futures and three concepts in their served order.
///
/// CAPTURED, NOT WRITTEN. The defect this feeds is a decode/render drop, and a
/// hand-authored fixture can only contain the shapes its author already thought
/// of — which is exactly the set that was already working. Do not "tidy" it.
enum SportCategoryUFCFixture {
    static let json = #"""
{
  "items": [
    {
      "type": "futures",
      "score": 78,
      "reason": "Justin Gaethje is up 77.5 points since Feb 3 in Lightweight Title Holder on Dec 31, 2026?",
      "headline": "Justin Gaethje up 77.5 points since Feb 3",
      "context_summary": "Justin Gaethje up 77.5 points since Feb 3",
      "data": {
        "id": 197,
        "name": "Lightweight Title Holder on Dec 31, 2026?",
        "sport": null,
        "sport_name": null,
        "llm_sport_category": "mma",
        "source": "kalshi",
        "source_count": 2,
        "sources": [
          "kalshi",
          "polymarket"
        ],
        "market_tier": 1,
        "market_type": "field",
        "status": "open",
        "resolution_date": "2026-12-31T17:00:00+00:00",
        "price_observed_at": "2026-09-15T20:50:42+00:00",
        "top_outcomes": [
          {
            "id": 1206,
            "name": "Justin Gaethje",
            "probability": 0.8249,
            "rank": 1,
            "movement": null,
            "rendered_percent": 82
          },
          {
            "id": 206772215,
            "name": "Mauricio Ruffy",
            "probability": 0.0461,
            "rank": 2,
            "movement": null,
            "rendered_percent": 5
          },
          {
            "id": 1210,
            "name": "Arman Tsarukyan",
            "probability": 0.0323,
            "rank": 3,
            "movement": null,
            "rendered_percent": 3
          }
        ],
        "card_sum_reason": null,
        "outcome_count": 12,
        "canonical_market_key": "mma::championship:2026",
        "group_id": "kalshi:KXUFCLIGHTWEIGHTTITLE-26",
        "group_type": "kalshi_event",
        "discover_card": {
          "suggested_format": "outcome_distribution",
          "bundle_candidate": false,
          "comparison_theme": null,
          "threshold_points": [],
          "ladder_treatment_refused": false,
          "distribution_outcomes": [
            {
              "label": "Justin Gaethje",
              "probability": 0.8249,
              "movement": null
            },
            {
              "label": "Mauricio Ruffy",
              "probability": 0.0461,
              "movement": null
            },
            {
              "label": "Arman Tsarukyan",
              "probability": 0.0323,
              "movement": null
            },
            {
              "label": "Ilia Topuria",
              "probability": 0.0138,
              "movement": null
            },
            {
              "label": "Charles Oliveira",
              "probability": 0.0138,
              "movement": null
            },
            {
              "label": "Paddy Pimblett",
              "probability": 0.0138,
              "movement": null
            },
            {
              "label": "Islam Makhachev",
              "probability": 0.0092,
              "movement": null
            },
            {
              "label": "Mateusz Gamrot",
              "probability": 0.0092,
              "movement": null
            }
          ],
          "remaining_outcome_count": 4,
          "qa_signals": [
            "multi_source_consistency_check"
          ],
          "public_source_disagreement": false,
          "reasons": [
            "multi_outcome_distribution"
          ]
        },
        "image_url": "https://images.pexels.com/photos/11391881/pexels-photo-11391881.jpeg?auto=compress&cs=tinysrgb&h=350",
        "image_width": 525,
        "image_height": 350,
        "hook_description": null,
        "temporal_badge": null,
        "confidence_tier": "moderate",
        "confidence_score": 0.5294,
        "confidence_signals": {
          "has_closing_line": false
        },
        "interestingness_score": 38.69,
        "interestingness_reasons": [
          "multi_source",
          "trading_volume"
        ],
        "market_tags": [
          "category:championship",
          "league:ufc",
          "market_status:open",
          "source:kalshi",
          "sport:mma",
          "tier:1"
        ]
      }
    },
    {
      "type": "futures",
      "score": 76,
      "reason": "Alexander Volkanovski (47%) leads Featherweight Title Holder on Dec 31, 2026?",
      "headline": "Alexander Volkanovski leads at 47%",
      "context_summary": "Alexander Volkanovski leads at 47%",
      "data": {
        "id": 201,
        "name": "Featherweight Title Holder on Dec 31, 2026?",
        "sport": null,
        "sport_name": null,
        "llm_sport_category": "mma",
        "source": "kalshi",
        "source_count": 2,
        "sources": [
          "kalshi",
          "polymarket"
        ],
        "market_tier": 1,
        "market_type": "field",
        "status": "open",
        "resolution_date": "2026-12-31T17:00:00+00:00",
        "price_observed_at": "2026-09-15T22:55:34+00:00",
        "top_outcomes": [
          {
            "id": 1247,
            "name": "Alexander Volkanovski",
            "probability": 0.4692,
            "rank": 1,
            "movement": null,
            "rendered_percent": 47
          },
          {
            "id": 1243,
            "name": "Movsar Evloev",
            "probability": 0.4313,
            "rank": 2,
            "movement": null,
            "rendered_percent": 43
          },
          {
            "id": 1245,
            "name": "Diego Lopes",
            "probability": 0.019,
            "rank": 3,
            "movement": null,
            "rendered_percent": 2
          }
        ],
        "card_sum_reason": null,
        "outcome_count": 11,
        "canonical_market_key": "mma::championship:2026",
        "group_id": "kalshi:KXUFCFEATHERWEIGHTTITLE-26",
        "group_type": "kalshi_event",
        "discover_card": {
          "suggested_format": "outcome_distribution",
          "bundle_candidate": false,
          "comparison_theme": null,
          "threshold_points": [],
          "ladder_treatment_refused": false,
          "distribution_outcomes": [
            {
              "label": "Alexander Volkanovski",
              "probability": 0.4692,
              "movement": null
            },
            {
              "label": "Movsar Evloev",
              "probability": 0.4313,
              "movement": null
            },
            {
              "label": "Diego Lopes",
              "probability": 0.019,
              "movement": null
            },
            {
              "label": "Jean Silva",
              "probability": 0.0142,
              "movement": null
            },
            {
              "label": "Yair Rodriguez",
              "probability": 0.0095,
              "movement": null
            },
            {
              "label": "Brian Ortega",
              "probability": 0.0095,
              "movement": null
            },
            {
              "label": "Youssef Zalal",
              "probability": 0.0095,
              "movement": null
            },
            {
              "label": "Ilia Topuria",
              "probability": 0.0095,
              "movement": null
            }
          ],
          "remaining_outcome_count": 3,
          "qa_signals": [
            "multi_source_consistency_check"
          ],
          "public_source_disagreement": false,
          "reasons": [
            "multi_outcome_distribution"
          ]
        },
        "image_url": "https://images.pexels.com/photos/28098115/pexels-photo-28098115.jpeg?auto=compress&cs=tinysrgb&h=650&w=940",
        "image_width": 940,
        "image_height": 627,
        "hook_description": null,
        "temporal_badge": null,
        "confidence_tier": "moderate",
        "confidence_score": 0.5294,
        "confidence_signals": {
          "has_closing_line": false
        },
        "interestingness_score": 28.73,
        "interestingness_reasons": [
          "multi_source"
        ],
        "market_tags": [
          "category:championship",
          "league:ufc",
          "market_status:open",
          "source:kalshi",
          "sport:mma",
          "tier:1"
        ]
      }
    },
    {
      "type": "concept",
      "score": 85,
      "reason": "",
      "headline": "Live",
      "data": {
        "key": "event:ufc:26sep16",
        "name": "Mayton Perea vs Zevan Hunt",
        "domain": "ufc",
        "status": "live",
        "start_date": "2026-09-16T00:51:00+00:00",
        "is_major": false,
        "fight_count": 3,
        "entry_count": 0,
        "is_marquee": false,
        "marquee_whathit": false,
        "leader": {
          "name": "Zevan Hunt",
          "probability": 0.5217,
          "movement_24h": null,
          "field_size": 2,
          "price_observed_at": null
        },
        "price_observed_at": null,
        "headline_bout": {
          "competitors": [
            {
              "name": "Zevan Hunt",
              "probability": 0.5217
            },
            {
              "name": "Mayton Perea",
              "probability": 0.4783
            }
          ],
          "commence_time": null
        }
      }
    },
    {
      "type": "futures",
      "score": 77,
      "reason": "Joshua Van is up 22.5 points since Feb 3 in Flyweight Title Holder on Dec 31, 2026?",
      "headline": "Joshua Van up 22.5 points since Feb 3",
      "context_summary": "Joshua Van up 22.5 points since Feb 3",
      "data": {
        "id": 200,
        "name": "Flyweight Title Holder on Dec 31, 2026?",
        "sport": null,
        "sport_name": null,
        "llm_sport_category": "mma",
        "source": "kalshi",
        "source_count": 2,
        "sources": [
          "kalshi",
          "polymarket"
        ],
        "market_tier": 1,
        "market_type": "field",
        "status": "open",
        "resolution_date": "2026-12-31T17:00:00+00:00",
        "price_observed_at": "2026-09-15T22:55:19+00:00",
        "top_outcomes": [
          {
            "id": 1236,
            "name": "Joshua Van",
            "probability": 0.4787,
            "rank": 1,
            "movement": null,
            "rendered_percent": 48
          },
          {
            "id": 1239,
            "name": "Alexandre Pantoja",
            "probability": 0.4502,
            "rank": 2,
            "movement": null,
            "rendered_percent": 45
          },
          {
            "id": 1234,
            "name": "Manel Kape",
            "probability": 0.0142,
            "rank": 3,
            "movement": null,
            "rendered_percent": 1
          }
        ],
        "card_sum_reason": null,
        "outcome_count": 9,
        "canonical_market_key": "mma::championship:2026",
        "group_id": "kalshi:KXUFCFLYWEIGHTTITLE-26",
        "group_type": "kalshi_event",
        "discover_card": {
          "suggested_format": "outcome_distribution",
          "bundle_candidate": false,
          "comparison_theme": null,
          "threshold_points": [],
          "ladder_treatment_refused": false,
          "distribution_outcomes": [
            {
              "label": "Joshua Van",
              "probability": 0.4787,
              "movement": null
            },
            {
              "label": "Alexandre Pantoja",
              "probability": 0.4502,
              "movement": null
            },
            {
              "label": "Manel Kape",
              "probability": 0.0142,
              "movement": null
            },
            {
              "label": "Amir Albazi",
              "probability": 0.0095,
              "movement": null
            },
            {
              "label": "Brandon Royval",
              "probability": 0.0095,
              "movement": null
            },
            {
              "label": "Brandon Moreno",
              "probability": 0.0095,
              "movement": null
            },
            {
              "label": "Muhammad Mokaev",
              "probability": 0.0095,
              "movement": null
            },
            {
              "label": "Kai Kara-France",
              "probability": 0.0095,
              "movement": null
            }
          ],
          "remaining_outcome_count": 1,
          "qa_signals": [
            "multi_source_consistency_check"
          ],
          "public_source_disagreement": false,
          "reasons": [
            "multi_outcome_distribution"
          ]
        },
        "image_url": "https://images.pexels.com/photos/11391881/pexels-photo-11391881.jpeg?auto=compress&cs=tinysrgb&h=350",
        "image_width": 525,
        "image_height": 350,
        "hook_description": null,
        "temporal_badge": null,
        "confidence_tier": "moderate",
        "confidence_score": 0.5294,
        "confidence_signals": {
          "has_closing_line": false
        },
        "interestingness_score": 34.18,
        "interestingness_reasons": [
          "multi_source"
        ],
        "market_tags": [
          "category:championship",
          "league:ufc",
          "market_status:open",
          "source:kalshi",
          "sport:mma",
          "tier:1"
        ]
      }
    },
    {
      "type": "futures",
      "score": 63,
      "reason": "Khamzat Chimaev is down 56.5 points since Feb 3 in Middleweight Title Holder on Dec 31, 2026?",
      "headline": "Khamzat Chimaev down 56.5 points since Feb 3",
      "context_summary": "Khamzat Chimaev down 56.5 points since Feb 3; Sean Strickland leads at 58%",
      "data": {
        "id": 196,
        "name": "Middleweight Title Holder on Dec 31, 2026?",
        "sport": null,
        "sport_name": null,
        "llm_sport_category": "mma",
        "source": "kalshi",
        "source_count": 2,
        "sources": [
          "kalshi",
          "polymarket"
        ],
        "market_tier": 1,
        "market_type": "field",
        "status": "open",
        "resolution_date": "2026-12-31T17:00:00+00:00",
        "price_observed_at": "2026-09-15T20:50:45+00:00",
        "top_outcomes": [
          {
            "id": 1193,
            "name": "Sean Strickland",
            "probability": 0.575,
            "rank": 1,
            "movement": null,
            "rendered_percent": 58
          },
          {
            "id": 1195,
            "name": "Nassourdine Imavov",
            "probability": 0.38,
            "rank": 2,
            "movement": null,
            "rendered_percent": 38
          },
          {
            "id": 1196,
            "name": "Khamzat Chimaev",
            "probability": 0.025,
            "rank": 3,
            "movement": null,
            "rendered_percent": 3
          }
        ],
        "card_sum_reason": null,
        "outcome_count": 8,
        "canonical_market_key": "mma::championship:2026",
        "group_id": "kalshi:KXUFCMIDDLEWEIGHTTITLE-26",
        "group_type": "kalshi_event",
        "discover_card": {
          "suggested_format": "outcome_distribution",
          "bundle_candidate": false,
          "comparison_theme": null,
          "threshold_points": [],
          "ladder_treatment_refused": false,
          "distribution_outcomes": [
            {
              "label": "Sean Strickland",
              "probability": 0.575,
              "movement": null
            },
            {
              "label": "Nassourdine Imavov",
              "probability": 0.38,
              "movement": null
            },
            {
              "label": "Khamzat Chimaev",
              "probability": 0.025,
              "movement": null
            },
            {
              "label": "Dricus Du Plessis",
              "probability": 0.01,
              "movement": null
            },
            {
              "label": "Israel Adesanya",
              "probability": 0.01,
              "movement": null
            },
            {
              "label": "Reinier de Ridder",
              "probability": 0.01,
              "movement": null
            },
            {
              "label": "Caio Borralho",
              "probability": 0.01,
              "movement": null
            },
            {
              "label": "Anthony Hernandez",
              "probability": 0.01,
              "movement": null
            }
          ],
          "remaining_outcome_count": 0,
          "qa_signals": [
            "multi_source_consistency_check"
          ],
          "public_source_disagreement": false,
          "reasons": [
            "multi_outcome_distribution"
          ]
        },
        "image_url": "https://images.pexels.com/photos/11391881/pexels-photo-11391881.jpeg?auto=compress&cs=tinysrgb&h=350",
        "image_width": 525,
        "image_height": 350,
        "hook_description": null,
        "temporal_badge": null,
        "confidence_tier": "moderate",
        "confidence_score": 0.5294,
        "confidence_signals": {
          "has_closing_line": false
        },
        "interestingness_score": 36.39,
        "interestingness_reasons": [
          "multi_source"
        ],
        "market_tags": [
          "category:championship",
          "league:ufc",
          "market_status:open",
          "source:kalshi",
          "sport:mma",
          "tier:1"
        ]
      }
    },
    {
      "type": "concept",
      "score": 53,
      "reason": "",
      "headline": "This week",
      "data": {
        "key": "event:ufc:26sep19",
        "name": "331: Van vs Pantoja",
        "domain": "ufc",
        "status": "upcoming",
        "start_date": "2026-09-19T23:45:00+00:00",
        "is_major": false,
        "fight_count": 12,
        "entry_count": 0,
        "is_marquee": false,
        "marquee_whathit": false,
        "leader": {
          "name": "Joshua van",
          "probability": 0.565,
          "movement_24h": null,
          "field_size": 2,
          "price_observed_at": "2026-09-16T02:28:42+00:00"
        },
        "price_observed_at": "2026-09-16T02:28:42+00:00",
        "headline_bout": {
          "competitors": [
            {
              "name": "Joshua van",
              "probability": 0.565
            },
            {
              "name": "Alexandre Pantoja",
              "probability": 0.435
            }
          ],
          "commence_time": "2026-09-20T07:20:00+00:00"
        }
      }
    },
    {
      "type": "concept",
      "score": 30,
      "reason": "",
      "headline": null,
      "data": {
        "key": "event:ufc:26oct04",
        "name": "Natalia Silva vs Wang Cong",
        "domain": "ufc",
        "status": "upcoming",
        "start_date": "2026-10-04T04:30:00+00:00",
        "is_major": false,
        "fight_count": 3,
        "entry_count": 0,
        "is_marquee": false,
        "marquee_whathit": false,
        "leader": {
          "name": "Natalia Silva",
          "probability": 0.6456,
          "movement_24h": null,
          "field_size": 2,
          "price_observed_at": null
        },
        "price_observed_at": null,
        "headline_bout": {
          "competitors": [
            {
              "name": "Natalia Silva",
              "probability": 0.6456
            },
            {
              "name": "Wang Cong",
              "probability": 0.3544
            }
          ],
          "commence_time": null
        }
      }
    }
  ],
  "total": 7,
  "limit": 50,
  "offset": 0,
  "has_more": false
}
"""#
}
