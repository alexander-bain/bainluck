import Foundation

/// The four `results` rows behind Alex's 2026-09-15 phone screenshot, as served.
///
/// `GET /api/events/search?q=Boston Red Sox` on production, captured
/// 2026-09-15 for #6444. The screenshot
/// (`artifacts/alex-phone-20260915/Screenshot 2026-09-15 at 3.47.41 PM.png`)
/// shows three rows, one under the other:
///
///     Boston Red Sox vs Baltimore Orioles    3 - 1   😴 34   >
///     MLB  FINAL
///     Boston Red Sox vs Baltimore Orioles    1 - 0   ⚡ 72   >
///     MLB  FINAL
///     Boston Red Sox vs Baltimore Orioles    6 - 5           >
///     MLB  FINAL
///
/// Those are events 15305465, 15302361 and 15293868 — September 6, 4 and 3, the
/// three games of one series — and the rows here are those three, plus the
/// first scheduled row of the same response as the control that must not move.
///
/// WHAT IS VERBATIM AND WHAT IS NOT, said plainly because a fixture that is
/// "basically the payload" is a fixture nobody can reason about: every ROW is
/// the server's object untouched, every key, including the `bookmaker_odds`
/// block that is 5 KB of the 10 KB each and which this ship never reads. The
/// ENVELOPE is minimal — `query`, `teams`, `results`, `futures`, `sports` —
/// because the whole response is 248 KB of 23 events and 10 futures, and the
/// rows are the specimen. `sports` is kept whole: it is the two filter pills in
/// the same screenshot. Alex's second pill read **"baseball_other"** and this
/// capture's reads `name: "Other Baseball"` beside the same key — that is
/// #5657 (lane1, server-side) having landed between his build and this capture,
/// not a repair in this diff.
enum SearchRedSoxProdFixture {
    static let json = #"""
{
  "query": "Boston Red Sox",
  "teams": [],
  "results": [
    {
      "id": 15313146,
      "external_id": "080879497a1aa1cc2674f615e55cc797",
      "sport": "baseball_mlb",
      "sport_name": "MLB",
      "home_team": "Texas Rangers",
      "away_team": "Boston Red Sox",
      "commence_time": "2026-09-17T00:05:00+00:00",
      "completed_at": null,
      "status": "scheduled",
      "started_without_result": false,
      "home_score": null,
      "away_score": null,
      "home_team_data": {
        "team_id": 10742,
        "slug": "texas-rangers-mlb",
        "primary_color": "#003278",
        "secondary_color": "#c0111f",
        "logo_small": "https://a.espncdn.com/i/teamlogos/mlb/500/scoreboard/tex.png",
        "logo_large": "https://a.espncdn.com/i/teamlogos/mlb/500/scoreboard/tex.png",
        "record": "75-76",
        "abbreviation": "TEX",
        "standings": {
          "pct": ".493",
          "wins": 74,
          "losses": 76,
          "div_rank": 2,
          "division": "West",
          "conference": "American League",
          "home_record": "40-32"
        }
      },
      "away_team_data": {
        "team_id": 10709,
        "slug": "boston-red-sox-mlb",
        "primary_color": "#0d2b56",
        "secondary_color": "#bd3039",
        "logo_small": "https://a.espncdn.com/i/teamlogos/mlb/500/scoreboard/bos.png",
        "logo_large": "https://a.espncdn.com/i/teamlogos/mlb/500/scoreboard/bos.png",
        "record": "82-69",
        "abbreviation": "BOS",
        "standings": {
          "pct": ".547",
          "wins": 82,
          "losses": 68,
          "div_rank": 3,
          "division": "East",
          "conference": "American League",
          "home_record": "38-37"
        }
      },
      "metadata": {
        "gender": "men",
        "level": "professional",
        "league": "MLB",
        "importance": "regular_season"
      },
      "espn": {
        "espn_id": "401816966",
        "probability_sources": {
          "kalshi": 0.515,
          "betting": 0.5043,
          "polymarket": 0.515,
          "betting_book_count": 18.0
        }
      },
      "win_probability_sources": {
        "kalshi": {
          "value": 0.515,
          "display_name": "Kalshi",
          "type": "market",
          "color": "#22c55e",
          "updated_at": "2026-09-16T04:49:00.537522+00:00",
          "evidence_status": "verified",
          "verified_scope": "full_event_winner",
          "contract_version": "live_blend.admissible_as_blend_speaker@5031"
        },
        "betting": {
          "value": 0.5043,
          "display_name": "Betting Odds",
          "type": "market",
          "color": "#374151",
          "updated_at": "2026-09-16T05:00:45.818327+00:00",
          "evidence_status": "not_applicable"
        },
        "polymarket": {
          "value": 0.515,
          "display_name": "Polymarket",
          "type": "market",
          "color": "#3b82f6",
          "updated_at": "2026-09-16T04:08:01.948721+00:00",
          "evidence_status": "verified",
          "verified_scope": "full_event_winner",
          "contract_version": "live_blend.admissible_as_blend_speaker@5031"
        },
        "betting_book_count": {
          "value": 18.0,
          "display_name": "betting_book_count",
          "type": "model",
          "color": "#6b7280",
          "evidence_status": "not_applicable"
        }
      },
      "current_odds": {
        "captured_at": "2026-09-16T04:59:15.752274+00:00",
        "home_probability": 0.515,
        "away_probability": 0.485,
        "spread": 0.6,
        "over_under": 7.6,
        "projected_home_score": 3.6,
        "projected_away_score": 4.1,
        "bookmaker_count": 19
      },
      "bookmaker_odds": [
        {
          "bookmaker": "ballybet",
          "home_moneyline": -114,
          "away_moneyline": -107,
          "home_probability": 0.5075,
          "away_probability": 0.4925,
          "captured_at": "2026-09-16T01:05:00.985094+00:00",
          "spread": 1.0,
          "over_under": 7.5,
          "projected_home_score": 3.2,
          "projected_away_score": 4.2
        },
        {
          "bookmaker": "betanysports",
          "home_moneyline": -105,
          "away_moneyline": -105,
          "home_probability": 0.5,
          "away_probability": 0.5,
          "captured_at": "2026-09-16T03:33:05.926389+00:00",
          "spread": -1.5,
          "over_under": 8.0,
          "projected_home_score": 4.8,
          "projected_away_score": 3.2
        },
        {
          "bookmaker": "betmgm",
          "home_moneyline": -115,
          "away_moneyline": -105,
          "home_probability": 0.5108,
          "away_probability": 0.4892,
          "captured_at": "2026-09-16T04:36:36.811384+00:00",
          "spread": 1.5,
          "over_under": 8.0,
          "projected_home_score": 3.2,
          "projected_away_score": 4.8
        },
        {
          "bookmaker": "betonlineag",
          "home_moneyline": -105,
          "away_moneyline": -105,
          "home_probability": 0.5,
          "away_probability": 0.5,
          "captured_at": "2026-09-16T04:36:36.798428+00:00",
          "spread": -1.5,
          "over_under": 7.5,
          "projected_home_score": 4.5,
          "projected_away_score": 3.0
        },
        {
          "bookmaker": "betparx",
          "home_moneyline": -114,
          "away_moneyline": -107,
          "home_probability": 0.5075,
          "away_probability": 0.4925,
          "captured_at": "2026-09-16T01:05:00.980267+00:00",
          "spread": 1.0,
          "over_under": 7.5,
          "projected_home_score": 3.2,
          "projected_away_score": 4.2
        },
        {
          "bookmaker": "betrivers",
          "home_moneyline": -113,
          "away_moneyline": -106,
          "home_probability": 0.5076,
          "away_probability": 0.4924,
          "captured_at": "2026-09-16T04:36:36.827806+00:00",
          "spread": 1.0,
          "over_under": 7.5,
          "projected_home_score": 3.2,
          "projected_away_score": 4.2
        },
        {
          "bookmaker": "betus",
          "home_moneyline": -105,
          "away_moneyline": -105,
          "home_probability": 0.5,
          "away_probability": 0.5,
          "captured_at": "2026-09-16T04:36:36.825576+00:00",
          "spread": -1.5,
          "over_under": 7.5,
          "projected_home_score": 4.5,
          "projected_away_score": 3.0
        },
        {
          "bookmaker": "bovada",
          "home_moneyline": -108,
          "away_moneyline": -112,
          "home_probability": 0.4957,
          "away_probability": 0.5043,
          "captured_at": "2026-09-16T04:40:57.330596+00:00",
          "spread": 1.5,
          "over_under": 8.0,
          "projected_home_score": 3.2,
          "projected_away_score": 4.8
        },
        {
          "bookmaker": "courtside",
          "home_moneyline": -109,
          "away_moneyline": -106,
          "home_probability": 0.5034,
          "away_probability": 0.4966,
          "captured_at": "2026-09-16T04:59:15.752274+00:00",
          "spread": null,
          "over_under": 6.0,
          "projected_home_score": null,
          "projected_away_score": null
        },
        {
          "bookmaker": "draftkings",
          "home_moneyline": -111,
          "away_moneyline": -108,
          "home_probability": 0.5033,
          "away_probability": 0.4967,
          "captured_at": "2026-09-16T04:36:36.787425+00:00",
          "spread": 1.5,
          "over_under": 8.0,
          "projected_home_score": 3.2,
          "projected_away_score": 4.8
        },
        {
          "bookmaker": "espnbet",
          "home_moneyline": -120,
          "away_moneyline": 100,
          "home_probability": 0.5217,
          "away_probability": 0.4783,
          "captured_at": "2026-09-15T21:50:01.505882+00:00",
          "spread": 1.5,
          "over_under": 7.5,
          "projected_home_score": 3.0,
          "projected_away_score": 4.5
        },
        {
          "bookmaker": "fanatics",
          "home_moneyline": -110,
          "away_moneyline": -110,
          "home_probability": 0.5,
          "away_probability": 0.5,
          "captured_at": "2026-09-16T04:36:36.795993+00:00",
          "spread": 1.5,
          "over_under": 8.0,
          "projected_home_score": 3.2,
          "projected_away_score": 4.8
        },
        {
          "bookmaker": "fanduel",
          "home_moneyline": -118,
          "away_moneyline": 100,
          "home_probability": 0.5198,
          "away_probability": 0.4802,
          "captured_at": "2026-09-16T04:36:36.813668+00:00",
          "spread": 1.5,
          "over_under": 7.5,
          "projected_home_score": 3.0,
          "projected_away_score": 4.5
        },
        {
          "bookmaker": "fliff",
          "home_moneyline": -115,
          "away_moneyline": -110,
          "home_probability": 0.5052,
          "away_probability": 0.4948,
          "captured_at": "2026-09-16T04:26:15.655067+00:00",
          "spread": 1.5,
          "over_under": 7.5,
          "projected_home_score": 3.0,
          "projected_away_score": 4.5
        },
        {
          "bookmaker": "hardrockbet",
          "home_moneyline": -115,
          "away_moneyline": -105,
          "home_probability": 0.5108,
          "away_probability": 0.4892,
          "captured_at": "2026-09-15T23:06:23.052190+00:00",
          "spread": 1.5,
          "over_under": 7.5,
          "projected_home_score": 3.0,
          "projected_away_score": 4.5
        },
        {
          "bookmaker": "lowvig",
          "home_moneyline": -105,
          "away_moneyline": -105,
          "home_probability": 0.5,
          "away_probability": 0.5,
          "captured_at": "2026-09-16T04:36:36.788809+00:00",
          "spread": -1.5,
          "over_under": 7.5,
          "projected_home_score": 4.5,
          "projected_away_score": 3.0
        },
        {
          "bookmaker": "mybookieag",
          "home_moneyline": -111,
          "away_moneyline": -106,
          "home_probability": 0.5055,
          "away_probability": 0.4945,
          "captured_at": "2026-09-16T04:36:36.805449+00:00",
          "spread": 1.5,
          "over_under": null,
          "projected_home_score": null,
          "projected_away_score": null
        },
        {
          "bookmaker": "rebet",
          "home_moneyline": -115,
          "away_moneyline": -110,
          "home_probability": 0.5052,
          "away_probability": 0.4948,
          "captured_at": "2026-09-16T03:24:35.687566+00:00",
          "spread": 1.0,
          "over_under": 8.0,
          "projected_home_score": 3.5,
          "projected_away_score": 4.5
        },
        {
          "bookmaker": "williamhill_us",
          "home_moneyline": -110,
          "away_moneyline": -110,
          "home_probability": 0.5,
          "away_probability": 0.5,
          "captured_at": "2026-09-16T04:36:36.801869+00:00",
          "spread": -1.5,
          "over_under": 8.0,
          "projected_home_score": 4.8,
          "projected_away_score": 3.2
        }
      ],
      "hero_probability": 0.515,
      "hero_probability_away": 0.485,
      "hero_probability_source": "blend",
      "highlight": {
        "score": 20,
        "reasons": [
          "tier_1"
        ],
        "label": null,
        "should_feature": false,
        "flags": {
          "is_live": false,
          "is_close_matchup": true,
          "is_blowout": false,
          "favorite_switched": false,
          "probability_swing": "stable",
          "score_swing": "stable",
          "is_starting_soon": false,
          "is_recently_finished": false,
          "is_upset": false,
          "league_tier": 1,
          "is_volatile": false,
          "has_lead_changes": false,
          "has_recent_momentum": false
        }
      }
    },
    {
      "id": 15305465,
      "external_id": "27dbceeb05fa78d858bc4c8e0fce75ba",
      "sport": "baseball_mlb",
      "sport_name": "MLB",
      "home_team": "Baltimore Orioles",
      "away_team": "Boston Red Sox",
      "commence_time": "2026-09-06T17:35:00+00:00",
      "completed_at": "2026-09-06T20:21:42.792482+00:00",
      "status": "completed",
      "started_without_result": false,
      "home_score": 1,
      "away_score": 3,
      "home_team_data": {
        "team_id": 10738,
        "slug": "baltimore-orioles-mlb",
        "primary_color": "#df4601",
        "secondary_color": "#000000",
        "logo_small": "https://a.espncdn.com/i/teamlogos/mlb/500/scoreboard/bal.png",
        "logo_large": "https://a.espncdn.com/i/teamlogos/mlb/500/scoreboard/bal.png",
        "record": "74-78",
        "abbreviation": "BAL",
        "standings": {
          "pct": ".480",
          "wins": 72,
          "losses": 78,
          "div_rank": 5,
          "division": "East",
          "conference": "American League",
          "home_record": "36-39"
        }
      },
      "away_team_data": {
        "team_id": 10709,
        "slug": "boston-red-sox-mlb",
        "primary_color": "#0d2b56",
        "secondary_color": "#bd3039",
        "logo_small": "https://a.espncdn.com/i/teamlogos/mlb/500/scoreboard/bos.png",
        "logo_large": "https://a.espncdn.com/i/teamlogos/mlb/500/scoreboard/bos.png",
        "record": "82-69",
        "abbreviation": "BOS",
        "standings": {
          "pct": ".547",
          "wins": 82,
          "losses": 68,
          "div_rank": 3,
          "division": "East",
          "conference": "American League",
          "home_record": "38-37"
        }
      },
      "metadata": {
        "gender": "men",
        "level": "professional",
        "league": "MLB",
        "importance": "regular_season"
      },
      "espn": {
        "espn_id": "401816829",
        "broadcast": "MLB.TV, MASN, NESN",
        "win_probability": 0.309,
        "probability_sources": {
          "mlb": 0.124,
          "espn": 0.309,
          "betting": 0.0549,
          "stat_model": 0.001,
          "betting_book_count": 8.0
        }
      },
      "win_probability_sources": {
        "mlb": {
          "value": 0.124,
          "display_name": "MLB Model",
          "type": "model",
          "color": "#06b6d4",
          "updated_at": "2026-09-06T20:19:52.139033+00:00",
          "evidence_status": "not_applicable"
        },
        "espn": {
          "value": 0.309,
          "display_name": "ESPN",
          "type": "model",
          "color": "#f97316",
          "updated_at": "2026-09-06T18:31:41.205974+00:00",
          "evidence_status": "not_applicable"
        },
        "betting": {
          "value": 0.0549,
          "display_name": "Betting Odds",
          "type": "market",
          "color": "#374151",
          "updated_at": "2026-09-06T20:32:09.507895+00:00",
          "evidence_status": "not_applicable"
        },
        "stat_model": {
          "value": 0.001,
          "display_name": "Bain Luck Model",
          "type": "model",
          "color": "#8b5cf6",
          "updated_at": "2026-09-06T20:18:13.981723+00:00",
          "evidence_status": "not_applicable"
        },
        "betting_book_count": {
          "value": 8.0,
          "display_name": "betting_book_count",
          "type": "model",
          "color": "#6b7280",
          "evidence_status": "not_applicable"
        }
      },
      "ei": {
        "score": 34,
        "raw_score": 62,
        "status": "quiet",
        "label": "Quiet",
        "emoji": "😴",
        "metadata": {
          "raw_ei": 0.9764,
          "lead_changes": 2,
          "comeback_factor": 0.4216,
          "snapshot_count": 330
        }
      },
      "pulse": {
        "score": 34,
        "raw_score": 62,
        "status": "quiet",
        "label": "Quiet",
        "emoji": "😴",
        "metadata": {
          "raw_ei": 0.9764,
          "lead_changes": 2,
          "comeback_factor": 0.4216,
          "snapshot_count": 330
        }
      },
      "current_odds": {
        "captured_at": "2026-09-06T20:20:09.846641+00:00",
        "home_probability": 0.0549,
        "away_probability": 0.9451,
        "spread": 1.5,
        "over_under": 5.3,
        "projected_home_score": 1.9,
        "projected_away_score": 3.4,
        "bookmaker_count": 13
      },
      "bookmaker_odds": [
        {
          "bookmaker": "ballybet",
          "home_moneyline": null,
          "away_moneyline": null,
          "home_probability": null,
          "away_probability": null,
          "captured_at": "2026-09-06T20:19:01.884374+00:00",
          "spread": 1.5,
          "over_under": 4.5,
          "projected_home_score": 1.5,
          "projected_away_score": 3.0
        },
        {
          "bookmaker": "betanysports",
          "home_moneyline": 114,
          "away_moneyline": -128,
          "home_probability": 0.4543,
          "away_probability": 0.5457,
          "captured_at": "2026-09-06T17:31:50.687123+00:00",
          "spread": 1.5,
          "over_under": 7.0,
          "projected_home_score": 2.8,
          "projected_away_score": 4.2
        },
        {
          "bookmaker": "betmgm",
          "home_moneyline": 2200,
          "away_moneyline": -10000,
          "home_probability": 0.0421,
          "away_probability": 0.9579,
          "captured_at": "2026-09-06T20:20:09.814711+00:00",
          "spread": 1.5,
          "over_under": 4.5,
          "projected_home_score": 1.5,
          "projected_away_score": 3.0
        },
        {
          "bookmaker": "betonlineag",
          "home_moneyline": 115,
          "away_moneyline": -127,
          "home_probability": 0.454,
          "away_probability": 0.546,
          "captured_at": "2026-09-06T17:40:13.789626+00:00",
          "spread": 1.5,
          "over_under": 7.0,
          "projected_home_score": 2.8,
          "projected_away_score": 4.2
        },
        {
          "bookmaker": "betparx",
          "home_moneyline": 2000,
          "away_moneyline": -10000,
          "home_probability": 0.0459,
          "away_probability": 0.9541,
          "captured_at": "2026-09-06T20:20:09.846641+00:00",
          "spread": 1.5,
          "over_under": 4.5,
          "projected_home_score": 1.5,
          "projected_away_score": 3.0
        },
        {
          "bookmaker": "betrivers",
          "home_moneyline": null,
          "away_moneyline": null,
          "home_probability": null,
          "away_probability": null,
          "captured_at": "2026-09-06T20:19:01.859089+00:00",
          "spread": 1.5,
          "over_under": 4.5,
          "projected_home_score": 1.5,
          "projected_away_score": 3.0
        },
        {
          "bookmaker": "betus",
          "home_moneyline": 116,
          "away_moneyline": -127,
          "home_probability": 0.4528,
          "away_probability": 0.5472,
          "captured_at": "2026-09-06T17:40:13.977531+00:00",
          "spread": 1.5,
          "over_under": 7.0,
          "projected_home_score": 2.8,
          "projected_away_score": 4.2
        },
        {
          "bookmaker": "bovada",
          "home_moneyline": null,
          "away_moneyline": null,
          "home_probability": null,
          "away_probability": null,
          "captured_at": "2026-09-06T20:19:01.844029+00:00",
          "spread": 1.5,
          "over_under": 4.5,
          "projected_home_score": 1.5,
          "projected_away_score": 3.0
        },
        {
          "bookmaker": "draftkings",
          "home_moneyline": 1380,
          "away_moneyline": -10000,
          "home_probability": 0.0639,
          "away_probability": 0.9361,
          "captured_at": "2026-09-06T20:19:01.720868+00:00",
          "spread": 1.5,
          "over_under": 4.5,
          "projected_home_score": 1.5,
          "projected_away_score": 3.0
        },
        {
          "bookmaker": "espnbet",
          "home_moneyline": 800,
          "away_moneyline": -2500,
          "home_probability": 0.1036,
          "away_probability": 0.8964,
          "captured_at": "2026-09-06T20:19:01.757972+00:00",
          "spread": 1.5,
          "over_under": null,
          "projected_home_score": null,
          "projected_away_score": null
        },
        {
          "bookmaker": "fanatics",
          "home_moneyline": 2200,
          "away_moneyline": -8000,
          "home_probability": 0.0422,
          "away_probability": 0.9578,
          "captured_at": "2026-09-06T20:19:01.923537+00:00",
          "spread": 1.5,
          "over_under": 4.5,
          "projected_home_score": 1.5,
          "projected_away_score": 3.0
        },
        {
          "bookmaker": "fanduel",
          "home_moneyline": 2000,
          "away_moneyline": -20000,
          "home_probability": 0.0457,
          "away_probability": 0.9543,
          "captured_at": "2026-09-06T20:20:09.806478+00:00",
          "spread": null,
          "over_under": null,
          "projected_home_score": null,
          "projected_away_score": null
        },
        {
          "bookmaker": "fliff",
          "home_moneyline": null,
          "away_moneyline": null,
          "home_probability": null,
          "away_probability": null,
          "captured_at": "2026-09-06T20:19:01.722923+00:00",
          "spread": 1.5,
          "over_under": 4.5,
          "projected_home_score": 1.5,
          "projected_away_score": 3.0
        },
        {
          "bookmaker": "hardrockbet",
          "home_moneyline": null,
          "away_moneyline": null,
          "home_probability": null,
          "away_probability": null,
          "captured_at": "2026-09-06T20:20:09.812493+00:00",
          "spread": 1.5,
          "over_under": 4.5,
          "projected_home_score": 1.5,
          "projected_away_score": 3.0
        },
        {
          "bookmaker": "lowvig",
          "home_moneyline": 115,
          "away_moneyline": -127,
          "home_probability": 0.454,
          "away_probability": 0.546,
          "captured_at": "2026-09-06T17:40:13.847019+00:00",
          "spread": 1.5,
          "over_under": 7.0,
          "projected_home_score": 2.8,
          "projected_away_score": 4.2
        },
        {
          "bookmaker": "mybookieag",
          "home_moneyline": 750,
          "away_moneyline": -1667,
          "home_probability": 0.1109,
          "away_probability": 0.8891,
          "captured_at": "2026-09-06T20:08:08.126862+00:00",
          "spread": null,
          "over_under": null,
          "projected_home_score": null,
          "projected_away_score": null
        },
        {
          "bookmaker": "rebet",
          "home_moneyline": 900,
          "away_moneyline": -10000,
          "home_probability": 0.0917,
          "away_probability": 0.9083,
          "captured_at": "2026-09-06T20:19:01.728064+00:00",
          "spread": 1.5,
          "over_under": null,
          "projected_home_score": null,
          "projected_away_score": null
        },
        {
          "bookmaker": "williamhill_us",
          "home_moneyline": 1200,
          "away_moneyline": -4000,
          "home_probability": 0.0731,
          "away_probability": 0.9269,
          "captured_at": "2026-09-06T20:19:01.743125+00:00",
          "spread": 1.5,
          "over_under": null,
          "projected_home_score": null,
          "projected_away_score": null
        }
      ],
      "hero_probability": 0.0,
      "hero_probability_away": 1.0,
      "hero_probability_source": "settled",
      "hero_settled_result": "away",
      "highlight": {
        "score": 30,
        "reasons": [
          "tier_1",
          "blowout",
          "major_prob_swing",
          "major_score_swing"
        ],
        "label": null,
        "should_feature": true,
        "flags": {
          "is_live": false,
          "is_close_matchup": false,
          "is_blowout": true,
          "favorite_switched": false,
          "probability_swing": "major",
          "score_swing": "major",
          "is_starting_soon": false,
          "is_recently_finished": false,
          "is_upset": false,
          "league_tier": 1,
          "is_volatile": false,
          "has_lead_changes": false,
          "has_recent_momentum": false
        }
      },
      "opening_odds": {
        "home_probability": 0.4536,
        "away_probability": 0.5464,
        "spread": 1.5,
        "over_under": 7.0,
        "favorite": "away"
      }
    },
    {
      "id": 15302361,
      "external_id": "d19f536dd30580edd3b97db60957866f",
      "sport": "baseball_mlb",
      "sport_name": "MLB",
      "home_team": "Baltimore Orioles",
      "away_team": "Boston Red Sox",
      "commence_time": "2026-09-04T23:05:00+00:00",
      "completed_at": "2026-09-05T01:41:40.768947+00:00",
      "status": "completed",
      "started_without_result": false,
      "home_score": 0,
      "away_score": 1,
      "home_team_data": {
        "team_id": 10738,
        "slug": "baltimore-orioles-mlb",
        "primary_color": "#df4601",
        "secondary_color": "#000000",
        "logo_small": "https://a.espncdn.com/i/teamlogos/mlb/500/scoreboard/bal.png",
        "logo_large": "https://a.espncdn.com/i/teamlogos/mlb/500/scoreboard/bal.png",
        "record": "74-78",
        "abbreviation": "BAL",
        "standings": {
          "pct": ".480",
          "wins": 72,
          "losses": 78,
          "div_rank": 5,
          "division": "East",
          "conference": "American League",
          "home_record": "36-39"
        }
      },
      "away_team_data": {
        "team_id": 10709,
        "slug": "boston-red-sox-mlb",
        "primary_color": "#0d2b56",
        "secondary_color": "#bd3039",
        "logo_small": "https://a.espncdn.com/i/teamlogos/mlb/500/scoreboard/bos.png",
        "logo_large": "https://a.espncdn.com/i/teamlogos/mlb/500/scoreboard/bos.png",
        "record": "82-69",
        "abbreviation": "BOS",
        "standings": {
          "pct": ".547",
          "wins": 82,
          "losses": 68,
          "div_rank": 3,
          "division": "East",
          "conference": "American League",
          "home_record": "38-37"
        }
      },
      "metadata": {
        "gender": "men",
        "level": "professional",
        "league": "MLB",
        "importance": "regular_season"
      },
      "espn": {
        "espn_id": "401816799",
        "broadcast": "MLB.TV, MASN, NESN",
        "win_probability": 0.388,
        "probability_sources": {
          "mlb": 0.115,
          "espn": 0.388,
          "betting": 0.0659,
          "stat_model": 0.001,
          "betting_book_count": 6.0,
          "kalshi": 0.01
        }
      },
      "win_probability_sources": {
        "mlb": {
          "value": 0.115,
          "display_name": "MLB Model",
          "type": "model",
          "color": "#06b6d4",
          "updated_at": "2026-09-05T01:36:05.026205+00:00",
          "evidence_status": "not_applicable"
        },
        "espn": {
          "value": 0.388,
          "display_name": "ESPN",
          "type": "model",
          "color": "#f97316",
          "updated_at": "2026-09-04T23:59:04.852097+00:00",
          "evidence_status": "not_applicable"
        },
        "betting": {
          "value": 0.0659,
          "display_name": "Betting Odds",
          "type": "market",
          "color": "#374151",
          "updated_at": "2026-09-05T01:54:05.964721+00:00",
          "evidence_status": "not_applicable"
        },
        "stat_model": {
          "value": 0.001,
          "display_name": "Bain Luck Model",
          "type": "model",
          "color": "#8b5cf6",
          "updated_at": "2026-09-05T01:41:06.543331+00:00",
          "evidence_status": "not_applicable"
        },
        "betting_book_count": {
          "value": 6.0,
          "display_name": "betting_book_count",
          "type": "model",
          "color": "#6b7280",
          "evidence_status": "not_applicable"
        },
        "kalshi": {
          "value": 0.01,
          "display_name": "Kalshi",
          "type": "market",
          "color": "#22c55e",
          "updated_at": "2026-09-05T04:34:53.032881+00:00",
          "evidence_status": "unverified"
        }
      },
      "ei": {
        "score": 72,
        "raw_score": 84,
        "status": "exciting",
        "label": "Exciting",
        "emoji": "⚡",
        "metadata": {
          "raw_ei": 1.7715,
          "lead_changes": 0,
          "comeback_factor": 0.5052,
          "snapshot_count": 313
        }
      },
      "pulse": {
        "score": 72,
        "raw_score": 84,
        "status": "exciting",
        "label": "Exciting",
        "emoji": "⚡",
        "metadata": {
          "raw_ei": 1.7715,
          "lead_changes": 0,
          "comeback_factor": 0.5052,
          "snapshot_count": 313
        }
      },
      "current_odds": {
        "captured_at": "2026-09-05T01:41:32.797712+00:00",
        "home_probability": 0.0659,
        "away_probability": 0.9341,
        "spread": 1.1,
        "over_under": 3.7,
        "projected_home_score": 3.0,
        "projected_away_score": 3.9,
        "bookmaker_count": 15
      },
      "bookmaker_odds": [
        {
          "bookmaker": "ballybet",
          "home_moneyline": null,
          "away_moneyline": null,
          "home_probability": null,
          "away_probability": null,
          "captured_at": "2026-09-05T01:39:28.329559+00:00",
          "spread": null,
          "over_under": 2.5,
          "projected_home_score": null,
          "projected_away_score": null
        },
        {
          "bookmaker": "betanysports",
          "home_moneyline": 102,
          "away_moneyline": -115,
          "home_probability": 0.4807,
          "away_probability": 0.5193,
          "captured_at": "2026-09-04T20:50:28.326326+00:00",
          "spread": 1.5,
          "over_under": 8.0,
          "projected_home_score": 3.2,
          "projected_away_score": 4.8
        },
        {
          "bookmaker": "betmgm",
          "home_moneyline": 1400,
          "away_moneyline": -10000,
          "home_probability": 0.0631,
          "away_probability": 0.9369,
          "captured_at": "2026-09-05T01:41:32.797712+00:00",
          "spread": -1.5,
          "over_under": 2.5,
          "projected_home_score": 2.0,
          "projected_away_score": 0.5
        },
        {
          "bookmaker": "betonlineag",
          "home_moneyline": 100,
          "away_moneyline": -110,
          "home_probability": 0.4884,
          "away_probability": 0.5116,
          "captured_at": "2026-09-04T23:08:46.879046+00:00",
          "spread": 1.5,
          "over_under": 8.0,
          "projected_home_score": 3.2,
          "projected_away_score": 4.8
        },
        {
          "bookmaker": "betparx",
          "home_moneyline": 700,
          "away_moneyline": -1430,
          "home_probability": 0.118,
          "away_probability": 0.882,
          "captured_at": "2026-09-05T01:38:43.328158+00:00",
          "spread": null,
          "over_under": 2.5,
          "projected_home_score": null,
          "projected_away_score": null
        },
        {
          "bookmaker": "betrivers",
          "home_moneyline": null,
          "away_moneyline": null,
          "home_probability": null,
          "away_probability": null,
          "captured_at": "2026-09-05T01:38:43.323053+00:00",
          "spread": null,
          "over_under": 2.5,
          "projected_home_score": null,
          "projected_away_score": null
        },
        {
          "bookmaker": "betus",
          "home_moneyline": -101,
          "away_moneyline": -109,
          "home_probability": 0.4907,
          "away_probability": 0.5093,
          "captured_at": "2026-09-04T23:08:46.919579+00:00",
          "spread": 1.5,
          "over_under": 8.0,
          "projected_home_score": 3.2,
          "projected_away_score": 4.8
        },
        {
          "bookmaker": "bovada",
          "home_moneyline": 1600,
          "away_moneyline": -7500,
          "home_probability": 0.0563,
          "away_probability": 0.9437,
          "captured_at": "2026-09-05T01:39:28.299634+00:00",
          "spread": null,
          "over_under": 1.5,
          "projected_home_score": null,
          "projected_away_score": null
        },
        {
          "bookmaker": "draftkings",
          "home_moneyline": 1120,
          "away_moneyline": -5700,
          "home_probability": 0.077,
          "away_probability": 0.923,
          "captured_at": "2026-09-05T01:39:28.292016+00:00",
          "spread": null,
          "over_under": 1.5,
          "projected_home_score": null,
          "projected_away_score": null
        },
        {
          "bookmaker": "espnbet",
          "home_moneyline": 1500,
          "away_moneyline": -7500,
          "home_probability": 0.0596,
          "away_probability": 0.9404,
          "captured_at": "2026-09-05T01:39:28.275377+00:00",
          "spread": null,
          "over_under": null,
          "projected_home_score": null,
          "projected_away_score": null
        },
        {
          "bookmaker": "fanatics",
          "home_moneyline": 1300,
          "away_moneyline": -3000,
          "home_probability": 0.0687,
          "away_probability": 0.9313,
          "captured_at": "2026-09-05T01:39:28.247191+00:00",
          "spread": null,
          "over_under": 1.5,
          "projected_home_score": null,
          "projected_away_score": null
        },
        {
          "bookmaker": "fanduel",
          "home_moneyline": 900,
          "away_moneyline": -2500,
          "home_probability": 0.0942,
          "away_probability": 0.9058,
          "captured_at": "2026-09-05T01:38:43.236180+00:00",
          "spread": null,
          "over_under": 1.5,
          "projected_home_score": null,
          "projected_away_score": null
        },
        {
          "bookmaker": "fliff",
          "home_moneyline": null,
          "away_moneyline": null,
          "home_probability": null,
          "away_probability": null,
          "captured_at": "2026-09-05T01:39:28.251784+00:00",
          "spread": null,
          "over_under": 2.5,
          "projected_home_score": null,
          "projected_away_score": null
        },
        {
          "bookmaker": "hardrockbet",
          "home_moneyline": 1500,
          "away_moneyline": -4000,
          "home_probability": 0.0602,
          "away_probability": 0.9398,
          "captured_at": "2026-09-05T01:39:28.320914+00:00",
          "spread": null,
          "over_under": 2.5,
          "projected_home_score": null,
          "projected_away_score": null
        },
        {
          "bookmaker": "lowvig",
          "home_moneyline": 100,
          "away_moneyline": -110,
          "home_probability": 0.4884,
          "away_probability": 0.5116,
          "captured_at": "2026-09-04T23:08:46.889068+00:00",
          "spread": 1.5,
          "over_under": 8.0,
          "projected_home_score": 3.2,
          "projected_away_score": 4.8
        },
        {
          "bookmaker": "mybookieag",
          "home_moneyline": 525,
          "away_moneyline": -833,
          "home_probability": 0.152,
          "away_probability": 0.848,
          "captured_at": "2026-09-05T01:38:43.261207+00:00",
          "spread": 1.5,
          "over_under": null,
          "projected_home_score": null,
          "projected_away_score": null
        },
        {
          "bookmaker": "rebet",
          "home_moneyline": 900,
          "away_moneyline": -10000,
          "home_probability": 0.0917,
          "away_probability": 0.9083,
          "captured_at": "2026-09-05T01:38:43.255611+00:00",
          "spread": 1.5,
          "over_under": null,
          "projected_home_score": null,
          "projected_away_score": null
        },
        {
          "bookmaker": "williamhill_us",
          "home_moneyline": 1800,
          "away_moneyline": -6000,
          "home_probability": 0.0508,
          "away_probability": 0.9492,
          "captured_at": "2026-09-05T01:39:28.306533+00:00",
          "spread": null,
          "over_under": 2.5,
          "projected_home_score": null,
          "projected_away_score": null
        }
      ],
      "hero_probability": 0.0,
      "hero_probability_away": 1.0,
      "hero_probability_source": "settled",
      "hero_settled_result": "away",
      "highlight": {
        "score": 30,
        "reasons": [
          "tier_1",
          "blowout",
          "major_prob_swing",
          "major_score_swing"
        ],
        "label": null,
        "should_feature": true,
        "flags": {
          "is_live": false,
          "is_close_matchup": false,
          "is_blowout": true,
          "favorite_switched": false,
          "probability_swing": "major",
          "score_swing": "major",
          "is_starting_soon": false,
          "is_recently_finished": false,
          "is_upset": false,
          "league_tier": 1,
          "is_volatile": false,
          "has_lead_changes": false,
          "has_recent_momentum": false
        }
      },
      "opening_odds": {
        "home_probability": 0.487,
        "away_probability": 0.513,
        "spread": 1.5,
        "over_under": 8.0,
        "favorite": "even"
      }
    },
    {
      "id": 15293868,
      "external_id": null,
      "sport": "baseball_mlb",
      "sport_name": "MLB",
      "home_team": "Baltimore Orioles",
      "away_team": "Boston Red Sox",
      "commence_time": "2026-09-03T23:15:00+00:00",
      "completed_at": "2026-09-04T02:30:00+00:00",
      "status": "completed",
      "started_without_result": false,
      "home_score": 5,
      "away_score": 6,
      "home_team_data": {
        "team_id": 10738,
        "slug": "baltimore-orioles-mlb",
        "primary_color": "#df4601",
        "secondary_color": "#000000",
        "logo_small": "https://a.espncdn.com/i/teamlogos/mlb/500/scoreboard/bal.png",
        "logo_large": "https://a.espncdn.com/i/teamlogos/mlb/500/scoreboard/bal.png",
        "record": "74-78",
        "abbreviation": "BAL",
        "standings": {
          "pct": ".480",
          "wins": 72,
          "losses": 78,
          "div_rank": 5,
          "division": "East",
          "conference": "American League",
          "home_record": "36-39"
        }
      },
      "away_team_data": {
        "team_id": 10709,
        "slug": "boston-red-sox-mlb",
        "primary_color": "#0d2b56",
        "secondary_color": "#bd3039",
        "logo_small": "https://a.espncdn.com/i/teamlogos/mlb/500/scoreboard/bos.png",
        "logo_large": "https://a.espncdn.com/i/teamlogos/mlb/500/scoreboard/bos.png",
        "record": "82-69",
        "abbreviation": "BOS",
        "standings": {
          "pct": ".547",
          "wins": 82,
          "losses": 68,
          "div_rank": 3,
          "division": "East",
          "conference": "American League",
          "home_record": "38-37"
        }
      },
      "metadata": {
        "gender": "men",
        "level": "professional",
        "league": "MLB",
        "importance": "regular_season"
      },
      "espn": {
        "broadcast": "MLB.TV, FOX",
        "probability_sources": {
          "mlb": 0.047,
          "kalshi": 0.01
        }
      },
      "win_probability_sources": {
        "mlb": {
          "value": 0.047,
          "display_name": "MLB Model",
          "type": "model",
          "color": "#06b6d4",
          "updated_at": "2026-09-04T01:52:11.932356+00:00",
          "evidence_status": "not_applicable"
        },
        "kalshi": {
          "value": 0.01,
          "display_name": "Kalshi",
          "type": "market",
          "color": "#22c55e",
          "updated_at": "2026-09-04T04:45:12.011975+00:00",
          "evidence_status": "unverified"
        }
      },
      "hero_probability": 0.0,
      "hero_probability_away": 1.0,
      "hero_probability_source": "settled",
      "hero_settled_result": "away",
      "highlight": {
        "score": 20,
        "reasons": [
          "tier_1"
        ],
        "label": null,
        "should_feature": false,
        "flags": {
          "is_live": false,
          "is_close_matchup": false,
          "is_blowout": false,
          "favorite_switched": false,
          "probability_swing": "stable",
          "score_swing": "stable",
          "is_starting_soon": false,
          "is_recently_finished": false,
          "is_upset": false,
          "league_tier": 1,
          "is_volatile": false,
          "has_lead_changes": false,
          "has_recent_momentum": false
        }
      }
    }
  ],
  "futures": [],
  "sports": [
    {
      "key": "baseball_mlb",
      "name": "MLB",
      "count": 22
    },
    {
      "key": "baseball_other",
      "name": "Other Baseball",
      "count": 1
    }
  ]
}
"""#
}
