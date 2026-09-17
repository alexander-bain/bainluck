import Foundation

/// A verbatim slice of production `GET /api/leagues/basketball_nba`, captured
/// 2026-09-17 while the NBA league page was rendering **no market sections at
/// all** (#888).
///
/// CAPTURED, NOT WRITTEN. #888's second defect is a decode drop, and a
/// hand-authored fixture can only contain the shapes its author already thought
/// of — which is exactly the set that was already working. In particular
/// nobody would have written the `"probability": null` outcomes below, and they
/// are the reason `LossyArray` is in the league decode path rather than a plain
/// array. Do not "tidy" it.
///
/// ELIDED, AND SAID OUT LOUD: the live payload is 111 KB and carries
/// `upcoming_games`, `recent_results`, `unreported_games`, `pool_counts`,
/// `section_counts`, `record_n`, `tier`, `built_at` and `availability` beside
/// the three keys `LeagueMarketsResponse` reads. Those are dropped here, and
/// each section is cut to its first market plus, where the section had one, the
/// first market carrying a null-probability outcome. Every retained byte is the
/// server's own. `total_markets` is left at the SERVED 64 on purpose — it is
/// what the server said it was sending, not a count of this slice, and a test
/// that quietly rewrote it would lose the only field that can catch a partial
/// decode.
enum LeagueMarketsNBAFixture {
    static let json = #"""
{
  "sport_key": "basketball_nba",
  "sections": {
    "awards": [
      {
        "id": 58015765,
        "name": "Pro Basketball Sixth Man of the Year Winner",
        "source": "kalshi",
        "external_id": "KXNBASIXTH-27",
        "market_tier": 3,
        "category": "championship",
        "resolution_date": "2027-07-08T14:00:00+00:00",
        "outcome_count": 74,
        "top_outcomes": [
          {
            "id": 222313467,
            "name": "Shaedon Sharpe",
            "probability": 0.5,
            "opening_probability": null,
            "rank": 1,
            "movement_24h": null,
            "team_id": null,
            "settled": false,
            "is_winner": false
          },
          {
            "id": 219764286,
            "name": "Naz Reid",
            "probability": 0.4,
            "opening_probability": null,
            "rank": 2,
            "movement_24h": null,
            "team_id": null,
            "settled": false,
            "is_winner": false
          },
          {
            "id": 219764287,
            "name": "Donte DiVincenzo",
            "probability": 0.4,
            "opening_probability": null,
            "rank": 3,
            "movement_24h": null,
            "team_id": null,
            "settled": false,
            "is_winner": false
          },
          {
            "id": 219764288,
            "name": "Keldon Johnson",
            "probability": 0.35,
            "opening_probability": null,
            "rank": 4,
            "movement_24h": null,
            "team_id": null,
            "settled": false,
            "is_winner": false
          },
          {
            "id": 219764293,
            "name": "Jaime Jaquez Jr.",
            "probability": 0.29,
            "opening_probability": 0.15,
            "rank": 5,
            "movement_24h": null,
            "team_id": null,
            "settled": false,
            "is_winner": false
          },
          {
            "id": 219764285,
            "name": "Collin Sexton",
            "probability": 0.25,
            "opening_probability": null,
            "rank": 6,
            "movement_24h": null,
            "team_id": null,
            "settled": false,
            "is_winner": false
          },
          {
            "id": 219764289,
            "name": "Daniel Gafford",
            "probability": 0.25,
            "opening_probability": null,
            "rank": 7,
            "movement_24h": null,
            "team_id": null,
            "settled": false,
            "is_winner": false
          },
          {
            "id": 222313473,
            "name": "Aaron Wiggins",
            "probability": 0.225,
            "opening_probability": 0.225,
            "rank": 7,
            "movement_24h": null,
            "team_id": null,
            "settled": false,
            "is_winner": false
          },
          {
            "id": 222313477,
            "name": "Bennedict Mathurin",
            "probability": 0.2,
            "opening_probability": null,
            "rank": 9,
            "movement_24h": null,
            "team_id": null,
            "settled": false,
            "is_winner": false
          },
          {
            "id": 222313476,
            "name": "Damian Lillard",
            "probability": 0.2,
            "opening_probability": null,
            "rank": 8,
            "movement_24h": null,
            "team_id": null,
            "settled": false,
            "is_winner": false
          }
        ],
        "canonical_market_key": "basketball::sixth_man:2027",
        "group_id": "kalshi:KXNBASIXTH-27",
        "section": "awards"
      }
    ],
    "props": [
      {
        "id": 52755800,
        "name": "Pro Basketball Players Traded",
        "source": "kalshi",
        "external_id": "KXNBATRADE-27FEB12",
        "market_tier": 5,
        "category": "championship",
        "resolution_date": "2027-02-12T04:59:00+00:00",
        "outcome_count": 58,
        "top_outcomes": [
          {
            "id": 225945745,
            "name": "Stephen Curry",
            "probability": 0.115,
            "opening_probability": 0.115,
            "rank": 53,
            "movement_24h": null,
            "team_id": null,
            "settled": false,
            "is_winner": null
          },
          {
            "id": 222323510,
            "name": "Nikola Joki\u0107",
            "probability": 0.08,
            "opening_probability": 0.05,
            "rank": 56,
            "movement_24h": null,
            "team_id": null,
            "settled": false,
            "is_winner": false
          },
          {
            "id": 198633450,
            "name": "Luguentz Dort",
            "probability": 0.99,
            "opening_probability": null,
            "rank": 3,
            "movement_24h": null,
            "team_id": null,
            "settled": true,
            "is_winner": true
          },
          {
            "id": 198633432,
            "name": "Jaylen Brown",
            "probability": 0.99,
            "opening_probability": null,
            "rank": 1,
            "movement_24h": null,
            "team_id": null,
            "settled": true,
            "is_winner": true
          },
          {
            "id": 198633433,
            "name": "Nic Claxton",
            "probability": 0.99,
            "opening_probability": 0.99,
            "rank": 2,
            "movement_24h": null,
            "team_id": null,
            "settled": true,
            "is_winner": true
          },
          {
            "id": 198633435,
            "name": "Miles Bridges",
            "probability": 0.98,
            "opening_probability": 0.99,
            "rank": 6,
            "movement_24h": null,
            "team_id": null,
            "settled": true,
            "is_winner": true
          },
          {
            "id": 198633439,
            "name": "Ja Morant",
            "probability": 0.98,
            "opening_probability": null,
            "rank": 4,
            "movement_24h": null,
            "team_id": null,
            "settled": true,
            "is_winner": true
          },
          {
            "id": 198633440,
            "name": "Jerami Grant",
            "probability": 0.98,
            "opening_probability": null,
            "rank": 6,
            "movement_24h": null,
            "team_id": null,
            "settled": true,
            "is_winner": true
          },
          {
            "id": 198633441,
            "name": "LaMelo Ball",
            "probability": 0.98,
            "opening_probability": 0.955,
            "rank": 7,
            "movement_24h": null,
            "team_id": null,
            "settled": true,
            "is_winner": true
          },
          {
            "id": 198633434,
            "name": "Isaiah Joe",
            "probability": 0.98,
            "opening_probability": 0.99,
            "rank": 5,
            "movement_24h": null,
            "team_id": null,
            "settled": true,
            "is_winner": true
          }
        ],
        "canonical_market_key": "basketball::championship:2027",
        "group_id": "kalshi:KXNBATRADE-27FEB12",
        "section": "props"
      },
      {
        "id": 58598376,
        "name": "2027 NBA Draft Lottery: 1st Pick",
        "source": "polymarket",
        "external_id": "811221",
        "market_tier": 5,
        "category": "championship",
        "resolution_date": "2027-05-18T23:59:00+00:00",
        "outcome_count": 30,
        "top_outcomes": [
          {
            "id": 217454946,
            "name": "Brooklyn Nets",
            "probability": 0.12,
            "opening_probability": 0.09,
            "rank": 2,
            "movement_24h": null,
            "team_id": null,
            "settled": false,
            "is_winner": false
          },
          {
            "id": 217454972,
            "name": "Golden State Warriors",
            "probability": 0.04,
            "opening_probability": 0.04,
            "rank": 16,
            "movement_24h": null,
            "team_id": null,
            "settled": false,
            "is_winner": false
          },
          {
            "id": 217454961,
            "name": "Oklahoma City Thunder",
            "probability": 0.04,
            "opening_probability": 0.04,
            "rank": 22,
            "movement_24h": null,
            "team_id": null,
            "settled": false,
            "is_winner": false
          },
          {
            "id": 217454962,
            "name": "Orlando Magic",
            "probability": 0.0355,
            "opening_probability": 0.25,
            "rank": 28,
            "movement_24h": null,
            "team_id": null,
            "settled": false,
            "is_winner": false
          },
          {
            "id": 217454964,
            "name": "Phoenix Suns",
            "probability": 0.0355,
            "opening_probability": 0.25,
            "rank": 30,
            "movement_24h": null,
            "team_id": null,
            "settled": false,
            "is_winner": false
          },
          {
            "id": 217454963,
            "name": "Philadelphia 76ers",
            "probability": 0.0355,
            "opening_probability": 0.0355,
            "rank": 29,
            "movement_24h": null,
            "team_id": null,
            "settled": false,
            "is_winner": false
          },
          {
            "id": 217454949,
            "name": "Dallas Mavericks",
            "probability": null,
            "opening_probability": 0.065,
            "rank": 8,
            "movement_24h": null,
            "team_id": null,
            "settled": false,
            "is_winner": false
          },
          {
            "id": 217454955,
            "name": "Memphis Grizzlies",
            "probability": null,
            "opening_probability": 0.11,
            "rank": 1,
            "movement_24h": null,
            "team_id": null,
            "settled": false,
            "is_winner": false
          },
          {
            "id": 217454957,
            "name": "Milwaukee Bucks",
            "probability": null,
            "opening_probability": 0.08,
            "rank": 5,
            "movement_24h": null,
            "team_id": null,
            "settled": false,
            "is_winner": false
          },
          {
            "id": 217454953,
            "name": "Los Angeles Clippers",
            "probability": null,
            "opening_probability": 0.08,
            "rank": 4,
            "movement_24h": null,
            "team_id": null,
            "settled": false,
            "is_winner": false
          }
        ],
        "canonical_market_key": "basketball:NBA:championship:2026-27",
        "group_id": "polymarket:811221",
        "section": "props"
      }
    ],
    "season_stats": [
      {
        "id": 55674214,
        "name": "Pro Basketball: Best Regular Season Record",
        "source": "kalshi",
        "external_id": "KXNBARECORD-27BEST",
        "market_tier": 5,
        "category": "championship",
        "resolution_date": "2027-05-31T14:00:00+00:00",
        "outcome_count": 30,
        "top_outcomes": [
          {
            "id": 210865597,
            "name": "Oklahoma City",
            "probability": 0.395,
            "opening_probability": 0.125,
            "rank": 1,
            "movement_24h": null,
            "team_id": null,
            "settled": false,
            "is_winner": false
          },
          {
            "id": 211333556,
            "name": "San Antonio",
            "probability": 0.32,
            "opening_probability": 0.355,
            "rank": 2,
            "movement_24h": null,
            "team_id": null,
            "settled": false,
            "is_winner": false
          },
          {
            "id": 214449613,
            "name": "Philadelphia",
            "probability": 0.07,
            "opening_probability": 0.115,
            "rank": 4,
            "movement_24h": null,
            "team_id": null,
            "settled": false,
            "is_winner": false
          },
          {
            "id": 214449615,
            "name": "New York",
            "probability": 0.07,
            "opening_probability": 0.11,
            "rank": 3,
            "movement_24h": null,
            "team_id": null,
            "settled": false,
            "is_winner": false
          },
          {
            "id": 214449636,
            "name": "Cleveland",
            "probability": 0.045,
            "opening_probability": 0.06,
            "rank": 5,
            "movement_24h": null,
            "team_id": null,
            "settled": false,
            "is_winner": false
          },
          {
            "id": 214449614,
            "name": "Los Angeles L",
            "probability": 0.04,
            "opening_probability": null,
            "rank": 8,
            "movement_24h": null,
            "team_id": null,
            "settled": false,
            "is_winner": false
          },
          {
            "id": 206747241,
            "name": "Minnesota",
            "probability": 0.04,
            "opening_probability": 0.065,
            "rank": 9,
            "movement_24h": null,
            "team_id": null,
            "settled": false,
            "is_winner": false
          },
          {
            "id": 214449617,
            "name": "Indiana",
            "probability": 0.04,
            "opening_probability": null,
            "rank": 6,
            "movement_24h": null,
            "team_id": null,
            "settled": false,
            "is_winner": false
          },
          {
            "id": 214449624,
            "name": "Los Angeles C",
            "probability": 0.04,
            "opening_probability": null,
            "rank": 7,
            "movement_24h": null,
            "team_id": null,
            "settled": false,
            "is_winner": false
          },
          {
            "id": 214449634,
            "name": "Boston",
            "probability": 0.035,
            "opening_probability": 0.075,
            "rank": 10,
            "movement_24h": null,
            "team_id": null,
            "settled": false,
            "is_winner": false
          }
        ],
        "canonical_market_key": "basketball::championship:2027",
        "group_id": "kalshi:KXNBARECORD-27BEST",
        "section": "season_stats"
      }
    ],
    "more_markets": [
      {
        "id": 58728381,
        "name": "Kevin Love Next Team",
        "source": "kalshi",
        "external_id": "KXNBANEXTTEAM-26KLOVE42",
        "market_tier": 5,
        "category": "championship",
        "resolution_date": "2026-10-21T03:59:00+00:00",
        "outcome_count": 31,
        "top_outcomes": [
          {
            "id": 218007757,
            "name": "Minnesota",
            "probability": 0.43,
            "opening_probability": 0.06,
            "rank": 2,
            "movement_24h": null,
            "team_id": null,
            "settled": false,
            "is_winner": false
          },
          {
            "id": 218007754,
            "name": "Retires / No Team",
            "probability": 0.295,
            "opening_probability": 0.225,
            "rank": 1,
            "movement_24h": null,
            "team_id": null,
            "settled": false,
            "is_winner": false
          },
          {
            "id": 218007753,
            "name": "Philadelphia",
            "probability": 0.08,
            "opening_probability": 0.385,
            "rank": 5,
            "movement_24h": null,
            "team_id": null,
            "settled": false,
            "is_winner": false
          },
          {
            "id": 218007756,
            "name": "Utah",
            "probability": 0.075,
            "opening_probability": 0.075,
            "rank": 3,
            "movement_24h": null,
            "team_id": null,
            "settled": false,
            "is_winner": false
          },
          {
            "id": 218007776,
            "name": "Los Angeles L",
            "probability": 0.06,
            "opening_probability": null,
            "rank": 4,
            "movement_24h": null,
            "team_id": null,
            "settled": false,
            "is_winner": false
          },
          {
            "id": 218007755,
            "name": "Cleveland",
            "probability": 0.025,
            "opening_probability": 0.09,
            "rank": 12,
            "movement_24h": null,
            "team_id": null,
            "settled": false,
            "is_winner": false
          },
          {
            "id": 218007769,
            "name": "Miami",
            "probability": 0.02,
            "opening_probability": 0.025,
            "rank": 6,
            "movement_24h": null,
            "team_id": null,
            "settled": false,
            "is_winner": false
          },
          {
            "id": 218007759,
            "name": "Boston",
            "probability": 0.01,
            "opening_probability": null,
            "rank": 7,
            "movement_24h": null,
            "team_id": null,
            "settled": false,
            "is_winner": false
          },
          {
            "id": 218007760,
            "name": "Brooklyn",
            "probability": 0.01,
            "opening_probability": null,
            "rank": 8,
            "movement_24h": null,
            "team_id": null,
            "settled": false,
            "is_winner": false
          },
          {
            "id": 218007761,
            "name": "New York",
            "probability": 0.01,
            "opening_probability": null,
            "rank": 9,
            "movement_24h": null,
            "team_id": null,
            "settled": false,
            "is_winner": false
          }
        ],
        "canonical_market_key": "basketball::championship:2026",
        "group_id": "kalshi:KXNBANEXTTEAM-26KLOVE42",
        "section": "more_markets"
      },
      {
        "id": 57774296,
        "name": "Pro Basketball: Single Game Specials",
        "source": "kalshi",
        "external_id": "KXNBAGAMESPECIALS-27",
        "market_tier": 5,
        "category": "championship",
        "resolution_date": "2027-05-08T14:00:00+00:00",
        "outcome_count": 27,
        "top_outcomes": [
          {
            "id": 214434991,
            "name": "Any player to record 60+ points in a game",
            "probability": 0.81,
            "opening_probability": 0.79,
            "rank": 1,
            "movement_24h": null,
            "team_id": null,
            "settled": false,
            "is_winner": false
          },
          {
            "id": 219767356,
            "name": "Any player to record 8+ blocks in a game",
            "probability": 0.8,
            "opening_probability": 0.8,
            "rank": 3,
            "movement_24h": null,
            "team_id": null,
            "settled": false,
            "is_winner": false
          },
          {
            "id": 219767355,
            "name": "Any player to record 55+ points in a game",
            "probability": 0.8,
            "opening_probability": 0.8,
            "rank": 2,
            "movement_24h": null,
            "team_id": null,
            "settled": false,
            "is_winner": false
          },
          {
            "id": 214434992,
            "name": "Any player to record 20+ rebounds in a game",
            "probability": 0.77,
            "opening_probability": 0.745,
            "rank": 4,
            "movement_24h": null,
            "team_id": null,
            "settled": false,
            "is_winner": false
          },
          {
            "id": 225938438,
            "name": "Any player to record 20+ points in a single quarter",
            "probability": 0.745,
            "opening_probability": 0.745,
            "rank": 5,
            "movement_24h": null,
            "team_id": null,
            "settled": false,
            "is_winner": null
          },
          {
            "id": 214434993,
            "name": "Any player to record 15+ offensive rebounds in a game",
            "probability": 0.26,
            "opening_probability": 0.26,
            "rank": 6,
            "movement_24h": null,
            "team_id": null,
            "settled": false,
            "is_winner": false
          },
          {
            "id": 225938423,
            "name": "Any player to record 20+ assists in a game",
            "probability": null,
            "opening_probability": null,
            "rank": 10,
            "movement_24h": null,
            "team_id": null,
            "settled": false,
            "is_winner": null
          },
          {
            "id": 225938424,
            "name": "Any player to record 25+ assists in a game",
            "probability": null,
            "opening_probability": null,
            "rank": 11,
            "movement_24h": null,
            "team_id": null,
            "settled": false,
            "is_winner": null
          },
          {
            "id": 225938427,
            "name": "Any player to record 10+ three pointers in a game",
            "probability": null,
            "opening_probability": null,
            "rank": 14,
            "movement_24h": null,
            "team_id": null,
            "settled": false,
            "is_winner": null
          },
          {
            "id": 225938428,
            "name": "Any player to record 12+ three pointers in a game",
            "probability": null,
            "opening_probability": null,
            "rank": 15,
            "movement_24h": null,
            "team_id": null,
            "settled": false,
            "is_winner": null
          }
        ],
        "canonical_market_key": "basketball::championship:2027",
        "group_id": "kalshi:KXNBAGAMESPECIALS-27",
        "section": "more_markets"
      }
    ]
  },
  "total_markets": 64
}
"""#
}
