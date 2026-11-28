"""Guard tests for #13511: fan-English nugget wording and team-prop routing."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
import pytest

from app.utils.game_nuggets import (
    _extract_candidates,
    match_claim_template,
    rank_game_nuggets,
)

# Pregame snapshot captured from production event 14792841 (Michigan at Ohio State, 2026-11-28T15:56:42Z).
_NOW_14792841 = datetime.fromisoformat("2026-11-28T15:56:42.596566+00:00")
_EVENT_INFO_14792841 = {
    "event_id": 14792841,
    "home_team": "Ohio State Buckeyes",
    "away_team": "Michigan Wolverines",
    "sport": "americanfootball_ncaaf",
    "status": "scheduled",
    "commence_time": "2026-11-28T17:00:00+00:00",
}
_GAME_MARKETS_14792841 = {
    "event_id": 14792841,
    "home_team": "Ohio State Buckeyes",
    "away_team": "Michigan Wolverines",
    "status": "scheduled",
    "totals": [
        {
            "_market_id": 72031745,
            "market_name": "Michigan vs. Ohio State: O/U 35.5",
            "outcome_name": "Over",
            "threshold": 35.5,
            "over_probability": 0.555,
            "period": None,
            "market_type": "game_total",
            "observed_at": "2026-11-28T15:34:31.450482+00:00",
            "pregame_mark": 0.59,
            "pregame_mark_source": "opening",
            "source": "polymarket"
        },
        {
            "_market_id": 71852827,
            "market_name": "Michigan vs. Ohio State: O/U 37.5",
            "outcome_name": "Under",
            "threshold": 37.5,
            "over_probability": 0.485,
            "period": None,
            "market_type": "game_total",
            "observed_at": "2026-11-28T15:34:31.450482+00:00",
            "pregame_mark": 0.505,
            "pregame_mark_source": "opening",
            "source": "polymarket"
        },
        {
            "_market_id": 72031747,
            "market_name": "Michigan vs. Ohio State: O/U 39.5",
            "outcome_name": "Under",
            "threshold": 39.5,
            "over_probability": 0.42,
            "period": None,
            "market_type": "game_total",
            "observed_at": "2026-11-28T15:45:58.303092+00:00",
            "pregame_mark": 0.465,
            "pregame_mark_source": "opening",
            "source": "polymarket"
        },
        {
            "_market_id": 72031748,
            "market_name": "Michigan vs. Ohio State: O/U 41.5",
            "outcome_name": "Under",
            "threshold": 41.5,
            "over_probability": 0.35,
            "period": None,
            "market_type": "game_total",
            "observed_at": "2026-11-28T15:53:46.274876+00:00",
            "pregame_mark": 0.4,
            "pregame_mark_source": "opening",
            "source": "polymarket"
        }
    ],
    "spreads": [
        {
            "_market_id": 72031759,
            "market_name": "Spread: Ohio State (-12.5)",
            "outcome_name": "Michigan",
            "threshold": None,
            "probability": 0.555,
            "observed_at": "2026-11-28T15:47:50.609265+00:00",
            "pregame_mark": 0.56,
            "pregame_mark_source": "opening",
            "source": "polymarket"
        },
        {
            "_market_id": 72031759,
            "market_name": "Spread: Ohio State (-12.5)",
            "outcome_name": "Ohio State",
            "threshold": None,
            "probability": 0.445,
            "observed_at": "2026-11-28T15:47:50.609265+00:00",
            "pregame_mark": 0.44,
            "pregame_mark_source": "opening",
            "source": "polymarket"
        },
        {
            "_market_id": 72031734,
            "market_name": "Spread: Ohio State (-4.5)",
            "outcome_name": "Ohio State",
            "threshold": None,
            "probability": 0.665,
            "observed_at": "2026-11-28T15:34:31.450482+00:00",
            "pregame_mark": 0.645,
            "pregame_mark_source": "opening",
            "source": "polymarket"
        },
        {
            "_market_id": 72031734,
            "market_name": "Spread: Ohio State (-4.5)",
            "outcome_name": "Michigan",
            "threshold": None,
            "probability": 0.335,
            "observed_at": "2026-11-28T15:34:31.450482+00:00",
            "pregame_mark": 0.355,
            "pregame_mark_source": "opening",
            "source": "polymarket"
        },
        {
            "_market_id": 71414314,
            "market_name": "Spread: Ohio State (-10.5)",
            "outcome_name": "Michigan",
            "threshold": None,
            "probability": 0.515,
            "observed_at": "2026-11-28T15:34:31.450482+00:00",
            "pregame_mark": 0.525,
            "pregame_mark_source": "opening",
            "source": "polymarket"
        },
        {
            "_market_id": 71414314,
            "market_name": "Spread: Ohio State (-10.5)",
            "outcome_name": "Ohio State",
            "threshold": None,
            "probability": 0.485,
            "observed_at": "2026-11-28T15:34:31.450482+00:00",
            "pregame_mark": 0.475,
            "pregame_mark_source": "opening",
            "source": "polymarket"
        }
    ],
    "player_props": [
        {
            "_market_id": 72478381,
            "market_name": "Michigan vs Ohio St.: Team Rushing Yards",
            "outcome_name": "Michigan: 50+",
            "threshold": 50.0,
            "over_probability": 0.77,
            "side": None,
            "period": None,
            "observed_at": "2026-11-28T15:47:00.708983+00:00",
            "pregame_mark": 0.77,
            "pregame_mark_source": "opening",
            "source": "kalshi",
            "typing_refusal": "team_subject"
        },
        {
            "_market_id": 72478381,
            "market_name": "Michigan vs Ohio St.: Team Rushing Yards",
            "outcome_name": "Michigan: 75+",
            "threshold": 75.0,
            "over_probability": 0.77,
            "side": None,
            "period": None,
            "observed_at": "2026-11-28T15:47:00.708983+00:00",
            "pregame_mark": 0.765,
            "pregame_mark_source": "opening",
            "source": "kalshi",
            "typing_refusal": "team_subject"
        },
        {
            "_market_id": 72478381,
            "market_name": "Michigan vs Ohio St.: Team Rushing Yards",
            "outcome_name": "Michigan: 100+",
            "threshold": 100.0,
            "over_probability": 0.715,
            "side": None,
            "period": None,
            "observed_at": "2026-11-28T15:55:05.724911+00:00",
            "pregame_mark": 0.68,
            "pregame_mark_source": "opening",
            "source": "kalshi",
            "typing_refusal": "team_subject"
        },
        {
            "_market_id": 72478381,
            "market_name": "Michigan vs Ohio St.: Team Rushing Yards",
            "outcome_name": "Michigan: 125+",
            "threshold": 125.0,
            "over_probability": 0.38,
            "side": None,
            "period": None,
            "observed_at": "2026-11-28T15:56:40.122261+00:00",
            "pregame_mark": 0.455,
            "pregame_mark_source": "opening",
            "source": "kalshi",
            "typing_refusal": "team_subject"
        },
        {
            "_market_id": 72478381,
            "market_name": "Michigan vs Ohio St.: Team Rushing Yards",
            "outcome_name": "Michigan: 150+",
            "threshold": 150.0,
            "over_probability": 0.335,
            "side": None,
            "period": None,
            "observed_at": "2026-11-28T15:54:31.550096+00:00",
            "pregame_mark": 0.275,
            "pregame_mark_source": "opening",
            "source": "kalshi",
            "typing_refusal": "team_subject"
        },
        {
            "_market_id": 72478381,
            "market_name": "Michigan vs Ohio St.: Team Rushing Yards",
            "outcome_name": "Ohio St.: 100+",
            "threshold": 100.0,
            "over_probability": 0.565,
            "side": None,
            "period": None,
            "observed_at": "2026-11-28T15:55:55.756740+00:00",
            "pregame_mark": 0.64,
            "pregame_mark_source": "opening",
            "source": "kalshi",
            "typing_refusal": "untyped_stat"
        },
        {
            "_market_id": 72478381,
            "market_name": "Michigan vs Ohio St.: Team Rushing Yards",
            "outcome_name": "Ohio St.: 125+",
            "threshold": 125.0,
            "over_probability": 0.335,
            "side": None,
            "period": None,
            "observed_at": "2026-11-28T15:49:14.816683+00:00",
            "pregame_mark": 0.405,
            "pregame_mark_source": "opening",
            "source": "kalshi",
            "typing_refusal": "untyped_stat"
        },
        {
            "_market_id": 72478381,
            "market_name": "Michigan vs Ohio St.: Team Rushing Yards",
            "outcome_name": "Ohio St.: 150+",
            "threshold": 150.0,
            "over_probability": 0.3,
            "side": None,
            "period": None,
            "observed_at": "2026-11-28T15:56:17.272058+00:00",
            "pregame_mark": 0.245,
            "pregame_mark_source": "opening",
            "source": "kalshi",
            "typing_refusal": "untyped_stat"
        },
        {
            "_market_id": 72478381,
            "market_name": "Michigan vs Ohio St.: Team Rushing Yards",
            "outcome_name": "Ohio St.: 175+",
            "threshold": 175.0,
            "over_probability": 0.205,
            "side": None,
            "period": None,
            "observed_at": "2026-11-28T15:47:43.946175+00:00",
            "pregame_mark": 0.185,
            "pregame_mark_source": "opening",
            "source": "kalshi",
            "typing_refusal": "untyped_stat"
        },
        {
            "_market_id": 72478381,
            "market_name": "Michigan vs Ohio St.: Team Rushing Yards",
            "outcome_name": "Ohio St.: 200+",
            "threshold": 200.0,
            "over_probability": 0.185,
            "side": None,
            "period": None,
            "observed_at": "2026-11-28T15:55:46.339341+00:00",
            "pregame_mark": 0.175,
            "pregame_mark_source": "opening",
            "source": "kalshi",
            "typing_refusal": "untyped_stat"
        },
        {
            "_market_id": 72478381,
            "market_name": "Michigan vs Ohio St.: Team Rushing Yards",
            "outcome_name": "Ohio St.: 225+",
            "threshold": 225.0,
            "over_probability": 0.075,
            "side": None,
            "period": None,
            "observed_at": "2026-11-28T15:52:30.950590+00:00",
            "pregame_mark": 0.075,
            "pregame_mark_source": "opening",
            "source": "kalshi",
            "typing_refusal": "untyped_stat"
        },
        {
            "_market_id": 72524375,
            "market_name": "Michigan vs Ohio St.: Team Receiving Yards",
            "outcome_name": "Michigan: 50+",
            "threshold": 50.0,
            "over_probability": 0.8,
            "side": None,
            "period": None,
            "observed_at": "2026-11-28T15:50:30.083581+00:00",
            "pregame_mark": 0.76,
            "pregame_mark_source": "opening",
            "source": "kalshi",
            "typing_refusal": "team_subject"
        },
        {
            "_market_id": 72524375,
            "market_name": "Michigan vs Ohio St.: Team Receiving Yards",
            "outcome_name": "Michigan: 75+",
            "threshold": 75.0,
            "over_probability": 0.785,
            "side": None,
            "period": None,
            "observed_at": "2026-11-28T15:52:30.950590+00:00",
            "pregame_mark": 0.76,
            "pregame_mark_source": "opening",
            "source": "kalshi",
            "typing_refusal": "team_subject"
        },
        {
            "_market_id": 72524375,
            "market_name": "Michigan vs Ohio St.: Team Receiving Yards",
            "outcome_name": "Michigan: 100+",
            "threshold": 100.0,
            "over_probability": 0.69,
            "side": None,
            "period": None,
            "observed_at": "2026-11-28T15:52:13.865320+00:00",
            "pregame_mark": 0.73,
            "pregame_mark_source": "opening",
            "source": "kalshi",
            "typing_refusal": "team_subject"
        },
        {
            "_market_id": 72524375,
            "market_name": "Michigan vs Ohio St.: Team Receiving Yards",
            "outcome_name": "Michigan: 125+",
            "threshold": 125.0,
            "over_probability": 0.52,
            "side": None,
            "period": None,
            "observed_at": "2026-11-28T15:55:48.716196+00:00",
            "pregame_mark": 0.615,
            "pregame_mark_source": "opening",
            "source": "kalshi",
            "typing_refusal": "team_subject"
        },
        {
            "_market_id": 72524375,
            "market_name": "Michigan vs Ohio St.: Team Receiving Yards",
            "outcome_name": "Michigan: 150+",
            "threshold": 150.0,
            "over_probability": 0.41,
            "side": None,
            "period": None,
            "observed_at": "2026-11-28T15:54:10.288959+00:00",
            "pregame_mark": 0.405,
            "pregame_mark_source": "opening",
            "source": "kalshi",
            "typing_refusal": "team_subject"
        },
        {
            "_market_id": 72524375,
            "market_name": "Michigan vs Ohio St.: Team Receiving Yards",
            "outcome_name": "Michigan: 175+",
            "threshold": 175.0,
            "over_probability": 0.25,
            "side": None,
            "period": None,
            "observed_at": "2026-11-28T15:44:43.369177+00:00",
            "pregame_mark": 0.335,
            "pregame_mark_source": "opening",
            "source": "kalshi",
            "typing_refusal": "team_subject"
        },
        {
            "_market_id": 72524375,
            "market_name": "Michigan vs Ohio St.: Team Receiving Yards",
            "outcome_name": "Michigan: 200+",
            "threshold": 200.0,
            "over_probability": 0.16,
            "side": None,
            "period": None,
            "observed_at": "2026-11-28T15:53:04.973709+00:00",
            "pregame_mark": 0.16,
            "pregame_mark_source": "opening",
            "source": "kalshi",
            "typing_refusal": "team_subject"
        },
        {
            "_market_id": 72524375,
            "market_name": "Michigan vs Ohio St.: Team Receiving Yards",
            "outcome_name": "Ohio St.: 150+",
            "threshold": 150.0,
            "over_probability": 0.725,
            "side": None,
            "period": None,
            "observed_at": "2026-11-28T15:54:22.073489+00:00",
            "pregame_mark": None,
            "pregame_mark_source": None,
            "source": "kalshi",
            "typing_refusal": "untyped_stat"
        },
        {
            "_market_id": 72524375,
            "market_name": "Michigan vs Ohio St.: Team Receiving Yards",
            "outcome_name": "Ohio St.: 175+",
            "threshold": 175.0,
            "over_probability": 0.65,
            "side": None,
            "period": None,
            "observed_at": "2026-11-28T15:54:22.073489+00:00",
            "pregame_mark": 0.745,
            "pregame_mark_source": "opening",
            "source": "kalshi",
            "typing_refusal": "untyped_stat"
        },
        {
            "_market_id": 72524375,
            "market_name": "Michigan vs Ohio St.: Team Receiving Yards",
            "outcome_name": "Ohio St.: 200+",
            "threshold": 200.0,
            "over_probability": 0.58,
            "side": None,
            "period": None,
            "observed_at": "2026-11-28T15:54:53.121110+00:00",
            "pregame_mark": 0.645,
            "pregame_mark_source": "opening",
            "source": "kalshi",
            "typing_refusal": "untyped_stat"
        },
        {
            "_market_id": 72524375,
            "market_name": "Michigan vs Ohio St.: Team Receiving Yards",
            "outcome_name": "Ohio St.: 225+",
            "threshold": 225.0,
            "over_probability": 0.465,
            "side": None,
            "period": None,
            "observed_at": "2026-11-28T15:54:53.121110+00:00",
            "pregame_mark": None,
            "pregame_mark_source": None,
            "source": "kalshi",
            "typing_refusal": "untyped_stat"
        },
        {
            "_market_id": 72524375,
            "market_name": "Michigan vs Ohio St.: Team Receiving Yards",
            "outcome_name": "Ohio St.: 250+",
            "threshold": 250.0,
            "over_probability": 0.43,
            "side": None,
            "period": None,
            "observed_at": "2026-11-28T15:56:35.454794+00:00",
            "pregame_mark": 0.36,
            "pregame_mark_source": "opening",
            "source": "kalshi",
            "typing_refusal": "untyped_stat"
        },
        {
            "_market_id": 72524375,
            "market_name": "Michigan vs Ohio St.: Team Receiving Yards",
            "outcome_name": "Ohio St.: 275+",
            "threshold": 275.0,
            "over_probability": 0.245,
            "side": None,
            "period": None,
            "observed_at": "2026-11-28T15:55:35.178819+00:00",
            "pregame_mark": 0.24,
            "pregame_mark_source": "opening",
            "source": "kalshi",
            "typing_refusal": "untyped_stat"
        },
        {
            "_market_id": 72524375,
            "market_name": "Michigan vs Ohio St.: Team Receiving Yards",
            "outcome_name": "Ohio St.: 300+",
            "threshold": 300.0,
            "over_probability": 0.215,
            "side": None,
            "period": None,
            "observed_at": "2026-11-28T15:55:52.986033+00:00",
            "pregame_mark": 0.15,
            "pregame_mark_source": "opening",
            "source": "kalshi",
            "typing_refusal": "untyped_stat"
        },
        {
            "_market_id": 72478412,
            "market_name": "Michigan vs Ohio St.: Team Receiving Touchdowns",
            "outcome_name": "Ohio St.: 1+",
            "threshold": 1.0,
            "over_probability": 0.74,
            "side": None,
            "period": None,
            "observed_at": "2026-11-28T15:56:02.856887+00:00",
            "pregame_mark": 0.8,
            "pregame_mark_source": "opening",
            "source": "kalshi",
            "typing_refusal": "untyped_stat"
        },
        {
            "_market_id": 72478412,
            "market_name": "Michigan vs Ohio St.: Team Receiving Touchdowns",
            "outcome_name": "Ohio St.: 2+",
            "threshold": 2.0,
            "over_probability": 0.42,
            "side": None,
            "period": None,
            "observed_at": "2026-11-28T15:54:35.627479+00:00",
            "pregame_mark": 0.615,
            "pregame_mark_source": "opening",
            "source": "kalshi",
            "typing_refusal": "untyped_stat"
        },
        {
            "_market_id": 72478412,
            "market_name": "Michigan vs Ohio St.: Team Receiving Touchdowns",
            "outcome_name": "Ohio St.: 3+",
            "threshold": 3.0,
            "over_probability": 0.18,
            "side": None,
            "period": None,
            "observed_at": "2026-11-28T15:48:58.770421+00:00",
            "pregame_mark": 0.495,
            "pregame_mark_source": "opening",
            "source": "kalshi",
            "typing_refusal": "untyped_stat"
        },
        {
            "_market_id": 72478412,
            "market_name": "Michigan vs Ohio St.: Team Receiving Touchdowns",
            "outcome_name": "Michigan: 2+",
            "threshold": 2.0,
            "over_probability": 0.095,
            "side": None,
            "period": None,
            "observed_at": "2026-11-28T15:46:37.206869+00:00",
            "pregame_mark": 0.215,
            "pregame_mark_source": "opening",
            "source": "kalshi",
            "typing_refusal": "team_subject"
        },
        {
            "_market_id": 72478412,
            "market_name": "Michigan vs Ohio St.: Team Receiving Touchdowns",
            "outcome_name": "Michigan: 3+",
            "threshold": 3.0,
            "over_probability": 0.07,
            "side": None,
            "period": None,
            "observed_at": "2026-11-28T15:43:51.243248+00:00",
            "pregame_mark": 0.18,
            "pregame_mark_source": "opening",
            "source": "kalshi",
            "typing_refusal": "team_subject"
        }
    ],
    "period_markets": [
        {
            "_market_id": 72272757,
            "market_name": "Michigan vs. Ohio State: 1H Moneyline",
            "outcome_name": "Ohio State",
            "threshold": None,
            "probability": 0.745,
            "period": "1H",
            "market_type": "half_winner",
            "observed_at": "2026-11-28T15:48:00.647716+00:00",
            "pregame_mark": 0.745,
            "pregame_mark_source": "opening",
            "source": "polymarket"
        },
        {
            "_market_id": 72272757,
            "market_name": "Michigan vs. Ohio State: 1H Moneyline",
            "outcome_name": "Michigan",
            "threshold": None,
            "probability": 0.255,
            "period": "1H",
            "market_type": "half_winner",
            "observed_at": "2026-11-28T15:48:00.647716+00:00",
            "pregame_mark": 0.255,
            "pregame_mark_source": "opening",
            "source": "polymarket"
        },
        {
            "_market_id": 72272758,
            "market_name": "Michigan vs. Ohio State: 1Q Moneyline",
            "outcome_name": "Ohio State",
            "threshold": None,
            "probability": 0.695,
            "period": "1Q",
            "market_type": "quarter_winner",
            "observed_at": "2026-11-28T15:34:31.450482+00:00",
            "pregame_mark": 0.695,
            "pregame_mark_source": "opening",
            "source": "polymarket"
        },
        {
            "_market_id": 72272758,
            "market_name": "Michigan vs. Ohio State: 1Q Moneyline",
            "outcome_name": "Michigan",
            "threshold": None,
            "probability": 0.305,
            "period": "1Q",
            "market_type": "quarter_winner",
            "observed_at": "2026-11-28T15:34:31.450482+00:00",
            "pregame_mark": 0.305,
            "pregame_mark_source": "opening",
            "source": "polymarket"
        },
        {
            "_market_id": 72478356,
            "market_name": "Michigan vs Ohio St.: 4th Quarter Winner",
            "outcome_name": "Ohio St.",
            "threshold": None,
            "probability": 0.52,
            "period": "4Q",
            "market_type": "quarter_winner",
            "observed_at": "2026-11-28T15:52:43.415580+00:00",
            "pregame_mark": 0.49,
            "pregame_mark_source": "opening",
            "source": "kalshi"
        },
        {
            "_market_id": 72478356,
            "market_name": "Michigan vs Ohio St.: 4th Quarter Winner",
            "outcome_name": "Michigan",
            "threshold": None,
            "probability": 0.295,
            "period": "4Q",
            "market_type": "quarter_winner",
            "observed_at": "2026-11-28T15:52:43.415580+00:00",
            "pregame_mark": 0.17,
            "pregame_mark_source": "opening",
            "source": "kalshi"
        },
        {
            "_market_id": 72478356,
            "market_name": "Michigan vs Ohio St.: 4th Quarter Winner",
            "outcome_name": "Tie",
            "threshold": None,
            "probability": 0.185,
            "period": "4Q",
            "market_type": "quarter_winner",
            "observed_at": "2026-11-28T15:52:43.415580+00:00",
            "pregame_mark": 0.12,
            "pregame_mark_source": "opening",
            "source": "kalshi"
        },
        {
            "_market_id": 72478330,
            "market_name": "Michigan vs Ohio St.: 3rd Quarter Winner",
            "outcome_name": "Ohio St.",
            "threshold": None,
            "probability": 0.525,
            "period": "3Q",
            "market_type": "quarter_winner",
            "observed_at": "2026-11-28T15:52:43.415580+00:00",
            "pregame_mark": 0.495,
            "pregame_mark_source": "opening",
            "source": "kalshi"
        },
        {
            "_market_id": 72478330,
            "market_name": "Michigan vs Ohio St.: 3rd Quarter Winner",
            "outcome_name": "Michigan",
            "threshold": None,
            "probability": 0.26,
            "period": "3Q",
            "market_type": "quarter_winner",
            "observed_at": "2026-11-28T15:52:43.415580+00:00",
            "pregame_mark": 0.15,
            "pregame_mark_source": "opening",
            "source": "kalshi"
        },
        {
            "_market_id": 72478330,
            "market_name": "Michigan vs Ohio St.: 3rd Quarter Winner",
            "outcome_name": "Tie",
            "threshold": None,
            "probability": 0.195,
            "period": "3Q",
            "market_type": "quarter_winner",
            "observed_at": "2026-11-28T15:52:43.415580+00:00",
            "pregame_mark": 0.135,
            "pregame_mark_source": "opening",
            "source": "kalshi"
        },
        {
            "_market_id": 72478285,
            "market_name": "Michigan vs Ohio St.: 1st Quarter Winner",
            "outcome_name": "Ohio St.",
            "threshold": None,
            "probability": 0.52,
            "period": "1Q",
            "market_type": "quarter_winner",
            "observed_at": "2026-11-28T15:54:44.922584+00:00",
            "pregame_mark": 0.335,
            "pregame_mark_source": "opening",
            "source": "kalshi"
        },
        {
            "_market_id": 72478285,
            "market_name": "Michigan vs Ohio St.: 1st Quarter Winner",
            "outcome_name": "Michigan",
            "threshold": None,
            "probability": 0.235,
            "period": "1Q",
            "market_type": "quarter_winner",
            "observed_at": "2026-11-28T15:44:43.369177+00:00",
            "pregame_mark": 0.225,
            "pregame_mark_source": "opening",
            "source": "kalshi"
        },
        {
            "_market_id": 72478285,
            "market_name": "Michigan vs Ohio St.: 1st Quarter Winner",
            "outcome_name": "Tie",
            "threshold": None,
            "probability": 0.225,
            "period": "1Q",
            "market_type": "quarter_winner",
            "observed_at": "2026-11-28T15:44:43.369177+00:00",
            "pregame_mark": 0.235,
            "pregame_mark_source": "opening",
            "source": "kalshi"
        },
        {
            "_market_id": 72478304,
            "market_name": "Michigan vs Ohio St.: 2nd Quarter Winner",
            "outcome_name": "Ohio St.",
            "threshold": None,
            "probability": 0.605,
            "period": "2Q",
            "market_type": "quarter_winner",
            "observed_at": "2026-11-28T15:52:43.415580+00:00",
            "pregame_mark": 0.525,
            "pregame_mark_source": "opening",
            "source": "kalshi"
        },
        {
            "_market_id": 72478304,
            "market_name": "Michigan vs Ohio St.: 2nd Quarter Winner",
            "outcome_name": "Michigan",
            "threshold": None,
            "probability": 0.255,
            "period": "2Q",
            "market_type": "quarter_winner",
            "observed_at": "2026-11-28T15:52:43.415580+00:00",
            "pregame_mark": 0.155,
            "pregame_mark_source": "opening",
            "source": "kalshi"
        },
        {
            "_market_id": 72478304,
            "market_name": "Michigan vs Ohio St.: 2nd Quarter Winner",
            "outcome_name": "Tie",
            "threshold": None,
            "probability": 0.135,
            "period": "2Q",
            "market_type": "quarter_winner",
            "observed_at": "2026-11-28T15:52:43.415580+00:00",
            "pregame_mark": 0.105,
            "pregame_mark_source": "opening",
            "source": "kalshi"
        }
    ],
    "other": [
        {
            "_market_id": 70638440,
            "market_name": "Michigan vs. Ohio State",
            "outcome_name": "Ohio State",
            "probability": 0.775,
            "market_type": "moneyline",
            "observed_at": "2026-11-28T15:34:31.450482+00:00",
            "pregame_mark": 0.755,
            "pregame_mark_source": "opening",
            "source": "polymarket"
        },
        {
            "_market_id": 70638440,
            "market_name": "Michigan vs. Ohio State",
            "outcome_name": "Michigan",
            "probability": 0.225,
            "market_type": "moneyline",
            "observed_at": "2026-11-28T15:34:31.450482+00:00",
            "pregame_mark": 0.245,
            "pregame_mark_source": "opening",
            "source": "polymarket"
        },
        {
            "_market_id": 72478396,
            "market_name": "Michigan vs Ohio St.: D/ST Touchdown",
            "outcome_name": "D/ST touchdown",
            "probability": 0.26,
            "observed_at": "2026-11-28T15:56:35.454794+00:00",
            "pregame_mark": 0.345,
            "pregame_mark_source": "opening",
            "source": "kalshi"
        },
        {
            "_market_id": 72095804,
            "market_name": "Michigan vs Ohio St.: First Team to Score a TD",
            "outcome_name": "Ohio St.",
            "probability": 0.67875648,
            "observed_at": "2026-11-28T15:56:29.007172+00:00",
            "pregame_mark": 0.645,
            "pregame_mark_source": "opening",
            "source": "kalshi"
        },
        {
            "_market_id": 72095804,
            "market_name": "Michigan vs Ohio St.: First Team to Score a TD",
            "outcome_name": "Michigan",
            "probability": 0.30569948,
            "observed_at": "2026-11-28T15:56:02.856887+00:00",
            "pregame_mark": 0.23,
            "pregame_mark_source": "opening",
            "source": "kalshi"
        },
        {
            "_market_id": 72095804,
            "market_name": "Michigan vs Ohio St.: First Team to Score a TD",
            "outcome_name": "No team",
            "probability": 0.01554404,
            "observed_at": "2026-11-28T15:52:43.415580+00:00",
            "pregame_mark": 0.055,
            "pregame_mark_source": "opening",
            "source": "kalshi"
        }
    ],
    "team_totals": []
}


def _fresh_ts(now: datetime, hours_ago: float = 0.25) -> str:
    return (now - timedelta(hours=hours_ago)).isoformat()


def test_event_14792841_nuggets_wording_teams_routing_and_probabilities():
    res = rank_game_nuggets(
        event_info=_EVENT_INFO_14792841,
        game_markets=_GAME_MARKETS_14792841,
        related_futures={},
        team_progression={},
        now=_NOW_14792841,
    )
    cands, kind_counts, _ = _extract_candidates(
        event_info=_EVENT_INFO_14792841,
        game_markets=_GAME_MARKETS_14792841,
        related_futures={},
        team_progression={},
        now=_NOW_14792841,
    )

    assert kind_counts["players"] == 0
    assert kind_counts["teams"] == 5
    assert [c for c in cands if c["kind"] == "players"] == []
    assert [n for n in res["nuggets"] if n["kind"] == "players"] == []

    for item in [*cands, *res["nuggets"]]:
        claim = item["claim"]
        assert "line is" not in claim.lower(), claim
        assert "is set at" not in claim.lower(), claim
        assert match_claim_template(claim) is not None, claim

    team_claims = {c["claim"]: c for c in cands if c["kind"] == "teams"}
    assert team_claims["Ohio State Buckeyes rush for 100 or more yards"]["probability"] == pytest.approx(0.565)
    assert team_claims["Ohio State Buckeyes rush for 100 or more yards"]["percent"] == 56
    assert team_claims["Michigan Wolverines rush for 125 or more yards"]["probability"] == pytest.approx(0.38)
    assert team_claims["Michigan Wolverines rush for 125 or more yards"]["percent"] == 38
    assert team_claims["Ohio State Buckeyes have 225 or more receiving yards"]["probability"] == pytest.approx(0.465)
    assert team_claims["Ohio State Buckeyes have 225 or more receiving yards"]["percent"] == 46
    assert team_claims["Michigan Wolverines have 125 or more receiving yards"]["probability"] == pytest.approx(0.52)
    assert team_claims["Michigan Wolverines have 125 or more receiving yards"]["percent"] == 52
    assert team_claims["Ohio State Buckeyes score 2 or more receiving touchdowns"]["probability"] == pytest.approx(0.42)
    assert team_claims["Ohio State Buckeyes score 2 or more receiving touchdowns"]["percent"] == 42

    total_nugget = next(n for n in res["nuggets"] if n["source_market_id"] == 71852827)
    assert total_nugget["claim"] == "38 or more total points"
    assert total_nugget["probability"] == pytest.approx(0.485)
    assert total_nugget["percent"] == 48


def test_over_probability_axis_vs_raw_under_probability():
    now = datetime(2026, 11, 28, 16, 0, tzinfo=timezone.utc)
    base_event = {
        "event_id": 991001,
        "home_team": "Ohio State Buckeyes",
        "away_team": "Michigan Wolverines",
        "sport": "americanfootball_ncaaf",
        "status": "scheduled",
        "commence_time": (now + timedelta(hours=1)).isoformat(),
    }

    # Game total carrying `over_probability` with complementary outcome_name="Under" -> Over claim
    over_res = rank_game_nuggets(
        event_info=base_event,
        game_markets={
            "totals": [
                {
                    "_market_id": 71852827,
                    "market_name": "Michigan vs. Ohio State: O/U 37.5",
                    "outcome_name": "Under",
                    "threshold": 37.5,
                    "over_probability": 0.485,
                    "observed_at": _fresh_ts(now),
                }
            ],
            "team_totals": [
                {
                    "_market_id": 81001,
                    "team_name": "Ohio State Buckeyes",
                    "team_side": "home",
                    "outcome_name": "Under",
                    "threshold": 24.5,
                    "over_probability": 0.52,
                    "observed_at": _fresh_ts(now),
                }
            ],
        },
        related_futures={},
        team_progression={},
        now=now,
    )
    over_claims = {n["claim"]: n for n in over_res["nuggets"]}
    assert "38 or more total points" in over_claims
    assert over_claims["38 or more total points"]["percent"] == 48
    assert "Ohio State Buckeyes score 25 or more points" in over_claims
    assert over_claims["Ohio State Buckeyes score 25 or more points"]["percent"] == 52

    # Raw Under probability (no `over_probability`) -> Under claim
    under_res = rank_game_nuggets(
        event_info=base_event,
        game_markets={
            "totals": [
                {
                    "_market_id": 71852828,
                    "market_name": "Michigan vs. Ohio State: O/U 37.5",
                    "outcome_name": "Under",
                    "threshold": 37.5,
                    "probability": 0.515,
                    "observed_at": _fresh_ts(now),
                }
            ],
            "team_totals": [
                {
                    "_market_id": 81002,
                    "team_name": "Ohio State Buckeyes",
                    "team_side": "home",
                    "side": "under",
                    "outcome_name": "Under",
                    "threshold": 24.5,
                    "probability": 0.49,
                    "observed_at": _fresh_ts(now),
                }
            ],
        },
        related_futures={},
        team_progression={},
        now=now,
    )
    under_claims = {n["claim"]: n for n in under_res["nuggets"]}
    assert "37 or fewer total points" in under_claims
    assert under_claims["37 or fewer total points"]["percent"] == 52
    assert "Ohio State Buckeyes score 24 or fewer points" in under_claims
    assert under_claims["Ohio State Buckeyes score 24 or fewer points"]["percent"] == 49


def test_singular_and_plural_subject_verb_agreement_and_player_control():
    now = datetime(2026, 11, 28, 16, 0, tzinfo=timezone.utc)
    singular_res = rank_game_nuggets(
        event_info={
            "event_id": 991002,
            "home_team": "Ohio State",
            "away_team": "Michigan",
            "sport": "americanfootball_ncaaf",
            "status": "scheduled",
            "commence_time": (now + timedelta(hours=1)).isoformat(),
        },
        game_markets={
            "player_props": [
                {
                    "_market_id": 1001,
                    "market_name": "Michigan vs Ohio St.: Team Rushing Yards",
                    "outcome_name": "Ohio St.: 100+",
                    "threshold": 100.0,
                    "over_probability": 0.60,
                    "observed_at": _fresh_ts(now),
                    "typing_refusal": "team_subject",
                },
                {
                    "_market_id": 1002,
                    "market_name": "Michigan vs Ohio St.: Team Receiving Yards",
                    "outcome_name": "Ohio St.: 225+",
                    "threshold": 225.0,
                    "over_probability": 0.51,
                    "observed_at": _fresh_ts(now),
                    "typing_refusal": "team_subject",
                },
                {
                    "_market_id": 1003,
                    "market_name": "Michigan vs Ohio St.: Team Receiving Touchdowns",
                    "outcome_name": "Ohio St.: 2+",
                    "threshold": 2.0,
                    "over_probability": 0.45,
                    "observed_at": _fresh_ts(now),
                    "typing_refusal": "team_subject",
                },
                {
                    "_market_id": 1004,
                    "player": {"key": "jayden daniels", "name": "Jayden Daniels"},
                    "player_headshot": "https://cdn.example/daniels.png",
                    "stat": {"key": "rushing_yards", "label": "Rushing Yards"},
                    "line": {"kind": "count_at_least", "value": 50, "label": "50+"},
                    "over_probability": 0.54,
                    "side": "over",
                    "observed_at": _fresh_ts(now),
                },
            ]
        },
        related_futures={},
        team_progression={},
        now=now,
    )
    by_mid = {n["source_market_id"]: n for n in singular_res["nuggets"]}
    assert by_mid[1001]["kind"] == "teams"
    assert by_mid[1001]["claim"] == "Ohio State rushes for 100 or more yards"
    assert by_mid[1002]["kind"] == "teams"
    assert by_mid[1002]["claim"] == "Ohio State has 225 or more receiving yards"
    assert by_mid[1003]["kind"] == "teams"
    assert by_mid[1003]["claim"] == "Ohio State scores 2 or more receiving touchdowns"
    assert by_mid[1004]["kind"] == "players"
    assert by_mid[1004]["claim"] == "Jayden Daniels rushes for 50 or more yards"

    plural_res = rank_game_nuggets(
        event_info={
            "event_id": 991003,
            "home_team": "Ohio State Buckeyes",
            "away_team": "Michigan Wolverines",
            "sport": "americanfootball_ncaaf",
            "status": "scheduled",
            "commence_time": (now + timedelta(hours=1)).isoformat(),
        },
        game_markets={
            "player_props": [
                {
                    "_market_id": 2001,
                    "market_name": "Michigan vs Ohio St.: Team Rushing Yards",
                    "outcome_name": "Ohio St.: 100+",
                    "threshold": 100.0,
                    "over_probability": 0.60,
                    "observed_at": _fresh_ts(now),
                    "typing_refusal": "team_subject",
                },
                {
                    "_market_id": 2002,
                    "market_name": "Michigan vs Ohio St.: Team Receiving Yards",
                    "outcome_name": "Ohio St.: 225+",
                    "threshold": 225.0,
                    "over_probability": 0.51,
                    "observed_at": _fresh_ts(now),
                    "typing_refusal": "team_subject",
                },
                {
                    "_market_id": 2003,
                    "market_name": "Michigan vs Ohio St.: Team Receiving Touchdowns",
                    "outcome_name": "Ohio St.: 2+",
                    "threshold": 2.0,
                    "over_probability": 0.45,
                    "observed_at": _fresh_ts(now),
                    "typing_refusal": "team_subject",
                },
            ]
        },
        related_futures={},
        team_progression={},
        now=now,
    )
    plural_by_mid = {n["source_market_id"]: n for n in plural_res["nuggets"]}
    assert plural_by_mid[2001]["claim"] == "Ohio State Buckeyes rush for 100 or more yards"
    assert plural_by_mid[2002]["claim"] == "Ohio State Buckeyes have 225 or more receiving yards"
    assert plural_by_mid[2003]["claim"] == "Ohio State Buckeyes score 2 or more receiving touchdowns"


@pytest.mark.parametrize(
    "legacy_claim",
    [
        "Ohio St.'s team rushing line is 100 yards",
        "The total is set at 47.5 points",
        "Michigan team total is set at 17.5 points",
        "The third quarter total is set at 13.5 points",
    ],
)
def test_legacy_jargon_claims_are_rejected_by_match_claim_template(legacy_claim: str):
    assert match_claim_template(legacy_claim) is None
