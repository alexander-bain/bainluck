"""Tests for #12288 Slice 1: topic-free container machinery (Direction 223 & Decision 224).

Proves:
1. All three Slice-1 candidate definitions (NFL Week, Oscars Best Picture, 2028 Presidential Race)
   live in ``backend/data/discover/candidates/``, stay switched OFF by default, contain ZERO
   hand-placed market or event IDs, and pass ``validate_roundup_definition`` (60-A, 71-A, 73-A).
2. ``choose_section_form`` selects each visual form purely from atom data shape (zero topic checks).
3. One single ``produce_container_machinery`` code path produces BOTH the Discover card
   (``compose_roundup_feed_item``) AND the multi-section container page (``compose_roundup_container``)
   across all three topics, reusing ``#12849``'s ``paired_metric_set`` for Oscars Best Picture,
   deduplicating members across sections, refusing non-trading/closed markets, and resolving
   verified subject imagery on teams, people, and films.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any

import pytest

from app.utils.container_machinery import (
    CANDIDATE_2028_PRESIDENTIAL_PATH,
    CANDIDATE_NFL_WEEK_PATH,
    CANDIDATE_OSCARS_BEST_PICTURE_PATH,
    MACHINERY_CANDIDATE_PATHS,
    SubjectArtResolver,
    build_container_machinery_producer,
    choose_section_form,
    container_machinery_enabled,
    load_machinery_definition,
    produce_container_machinery,
)
from app.utils.roundup_containers import (
    CONTAINERS_DATA_DIR,
    HAND_LIST_ID_RULE_KEYS,
    ROUNDUP_PRODUCERS,
    compose_roundup_container,
    compose_roundup_feed_item,
    evaluate_roundup_producer,
)

FIXED_NOW = datetime(2026, 10, 4, 16, 0, 0, tzinfo=timezone.utc)


def _sample_snapshot() -> dict[str, Any]:
    return {
        "events": [
            {
                "id": 9001,
                "sport": "americanfootball_nfl",
                "sport_name": "NFL",
                "away_team": "Baltimore Ravens",
                "home_team": "Carolina Panthers",
                "commence_time": "2026-10-04T17:00:00+00:00",
                "status": "scheduled",
                "current_odds": {"away_probability": 0.48, "home_probability": 0.52},
            },
            {
                "id": 9002,
                "sport": "americanfootball_nfl",
                "sport_name": "NFL",
                "away_team": "Chicago Bears",
                "home_team": "Detroit Lions",
                "commence_time": "2026-10-04T17:00:00+00:00",
                "status": "scheduled",
                "current_odds": {"away_probability": 0.51, "home_probability": 0.49},
            },
            {
                "id": 9003,
                "sport": "americanfootball_nfl",
                "sport_name": "NFL",
                "away_team": "Indianapolis Colts",
                "home_team": "Houston Texans",
                "commence_time": "2026-10-04T20:05:00+00:00",
                "status": "scheduled",
                "current_odds": {"away_probability": 0.15, "home_probability": 0.85},
            },
            {
                "id": 9004,
                "sport": "americanfootball_nfl",
                "sport_name": "NFL",
                "away_team": "Tennessee Titans",
                "home_team": "Dallas Cowboys",
                "commence_time": "2026-10-04T20:25:00+00:00",
                "status": "scheduled",
                "current_odds": {"away_probability": 0.21, "home_probability": 0.79},
            },
        ],
        "paired_sets": {
            "oscars-2027-best-picture": {
                "set_id": "oscars-2027-best-picture",
                "category": "entertainment",
                "kicker": "THE OSCARS · BEST PICTURE",
                "title": "The Odyssey leads Best Picture",
                "subtitle": "Nominated % and Wins % side by side",
                "stage_1_label": "Nominated",
                "stage_2_label": "Wins",
                "stage_1_settled_yes_label": "Nominated",
                "stage_1_settled_no_label": "Not nominated",
                "stage_1_market": {"id": 5165726, "name": "Oscar Nominee: Best Picture", "source": "kalshi"},
                "stage_2_market": {"id": 6173044, "name": "Oscar Winner: Best Picture", "source": "kalshi"},
                "entries": [
                    {
                        "subject_key": "the-odyssey",
                        "subject": "The Odyssey",
                        "detail": "Christopher Nolan",
                        "stage_1_market_id": 5165726,
                        "stage_1_probability": 0.94,
                        "stage_2_market_id": 6173044,
                        "stage_2_probability": 0.52,
                        "art": {
                            "kind": "tmdb_poster",
                            "url": "https://image.tmdb.org/t/p/w342/krVa7rKCQb4OBfsr2LTJv4rTz5q.jpg",
                            "adult": False,
                            "kid_safe_vetted": True,
                        },
                    },
                    {
                        "subject_key": "you-can-see-everything",
                        "subject": "You Can See Everything",
                        "detail": "Feature film",
                        "stage_1_market_id": 5165726,
                        "stage_1_probability": 0.85,
                        "stage_2_market_id": 6173044,
                        "stage_2_probability": 0.20,
                        "art": {
                            "kind": "tmdb_poster",
                            "url": "https://image.tmdb.org/t/p/w342/Ap8QwmKfSjYbWC4XIP8w9pdn72O.jpg",
                            "adult": False,
                            "kid_safe_vetted": True,
                        },
                    },
                    {
                        "subject_key": "dune-part-three",
                        "subject": "Dune: Part Three",
                        "detail": "Denis Villeneuve",
                        "stage_1_market_id": 5165726,
                        "stage_1_probability": 0.81,
                        "stage_2_market_id": 6173044,
                        "stage_2_probability": 0.12,
                        "art": {
                            "kind": "tmdb_poster",
                            "url": "https://image.tmdb.org/t/p/w342/glt0v4I89rMWstDNCaFXc5SNyO1.jpg",
                            "adult": False,
                            "kid_safe_vetted": True,
                        },
                    },
                ],
            }
        },
        "markets": [
            {
                "id": 40532,
                "name": "MVP Winner?",
                "status": "open",
                "source": "kalshi",
                "top_outcomes": [
                    {"id": 1, "name": "Joe Burrow", "probability": 0.48},
                    {"id": 2, "name": "Brock Purdy", "probability": 0.16},
                    {"id": 3, "name": "Josh Allen", "probability": 0.14},
                    {"id": 4, "name": "Trevor Lawrence", "probability": 0.08},
                ],
            },
            {
                "id": 7266303,
                "name": "NFL Passing Touchdowns Leader",
                "status": "open",
                "source": "kalshi",
                "top_outcomes": [
                    {"id": 1001, "name": "Joe Burrow", "probability": 0.68},
                    {"id": 1002, "name": "Jordan Love", "probability": 0.04},
                    {"id": 1003, "name": "Dak Prescott", "probability": 0.02},
                ],
            },
            {
                "id": 7186380,
                "name": "NFL Rushing Touchdowns Leader",
                "status": "open",
                "source": "kalshi",
                "top_outcomes": [
                    {"id": 1011, "name": "Jahmyr Gibbs", "probability": 0.32},
                    {"id": 1012, "name": "Josh Allen", "probability": 0.23},
                    {"id": 1013, "name": "James Cook III", "probability": 0.09},
                ],
            },
            {
                "id": 7266301,
                "name": "NFL Receiving Touchdowns Leader",
                "status": "open",
                "source": "kalshi",
                "top_outcomes": [
                    {"id": 1021, "name": "Jaxon Smith-Njigba", "probability": 0.38},
                    {"id": 1022, "name": "Ja'Marr Chase", "probability": 0.07},
                    {"id": 1023, "name": "CeeDee Lamb", "probability": 0.06},
                ],
            },
            {
                "id": 2279147,
                "name": "NFL: NFC North Champion",
                "status": "open",
                "source": "polymarket",
                "top_outcomes": [
                    {"id": 11, "name": "Minnesota Vikings", "probability": 0.38},
                    {"id": 12, "name": "Chicago Bears", "probability": 0.34},
                    {"id": 13, "name": "Detroit Lions", "probability": 0.28},
                ],
            },
            {
                "id": 2248389,
                "name": "NFL: AFC North Champion",
                "status": "open",
                "source": "polymarket",
                "top_outcomes": [
                    {"id": 21, "name": "Cincinnati Bengals", "probability": 0.62},
                    {"id": 22, "name": "Pittsburgh Steelers", "probability": 0.22},
                    {"id": 23, "name": "Baltimore Ravens", "probability": 0.16},
                ],
            },
            {
                "id": 5869747,
                "name": "Oscar Winner: Best Director",
                "status": "open",
                "source": "kalshi",
                "top_outcomes": [
                    {"id": 31, "name": "Christopher Nolan", "probability": 0.55},
                    {"id": 32, "name": "Denis Villeneuve", "probability": 0.20},
                    {"id": 33, "name": "Nathan Fielder", "probability": 0.13},
                ],
            },
            {
                "id": 5869749,
                "name": "Oscar Winner: Best Actor",
                "status": "open",
                "source": "kalshi",
                "top_outcomes": [
                    {"id": 41, "name": "John Malkovich", "probability": 0.43},
                    {"id": 42, "name": "Andrew Scott", "probability": 0.21},
                    {"id": 43, "name": "Matt Damon", "probability": 0.16},
                ],
            },
            {
                "id": 5869748,
                "name": "Oscar winner: Best Actress",
                "status": "open",
                "source": "kalshi",
                "top_outcomes": [
                    {"id": 51, "name": "Julianne Moore", "probability": 0.75, "opening_probability": 0.68},
                    {"id": 52, "name": "Renate Reinsve", "probability": 0.14, "opening_probability": 0.18},
                    {"id": 53, "name": "Sandra Hüller", "probability": 0.08, "opening_probability": 0.09},
                ],
            },
            {
                "id": 52755611,
                "name": "Oscar winner: Best Supporting Actor",
                "status": "open",
                "source": "kalshi",
                "top_outcomes": [
                    {"id": 54, "name": "Paul Giamatti", "probability": 0.44, "opening_probability": 0.39},
                    {"id": 55, "name": "Andrew Garfield", "probability": 0.24, "opening_probability": 0.28},
                    {"id": 56, "name": "Guitarricadelafuente", "probability": 0.12, "opening_probability": 0.10},
                ],
            },
            {
                "id": 52755610,
                "name": "Oscar Winner: Best Supporting Actress",
                "status": "open",
                "source": "kalshi",
                "top_outcomes": [
                    {"id": 57, "name": "Anne Hathaway", "probability": 0.55, "opening_probability": 0.49},
                    {"id": 58, "name": "Renate Reinsve", "probability": 0.20, "opening_probability": 0.22},
                    {"id": 59, "name": "Julianne Moore", "probability": 0.11, "opening_probability": 0.12},
                ],
            },
            {
                "id": 108327,
                "name": "2028 Presidential Election winner? (Party)",
                "status": "open",
                "source": "kalshi",
                "top_outcomes": [
                    {"id": 61, "name": "Democratic party", "probability": 0.68},
                    {"id": 62, "name": "Republican party", "probability": 0.32},
                ],
            },
            {
                "id": 112897,
                "name": "Presidential Election Winner 2028",
                "status": "open",
                "source": "polymarket",
                "top_outcomes": [
                    {"id": 71, "name": "Jon Ossoff", "probability": 0.18},
                    {"id": 72, "name": "JD Vance", "probability": 0.15},
                    {"id": 73, "name": "Alexandria Ocasio-Cortez", "probability": 0.09},
                    {"id": 74, "name": "Gavin Newsom", "probability": 0.08},
                ],
            },
            {
                "id": 112895,
                "name": "Democratic Presidential Nominee 2028",
                "status": "open",
                "source": "polymarket",
                "top_outcomes": [
                    {"id": 81, "name": "Jon Ossoff", "probability": 0.26},
                    {"id": 82, "name": "Alexandria Ocasio-Cortez", "probability": 0.15},
                    {"id": 83, "name": "Gavin Newsom", "probability": 0.10},
                ],
            },
            {
                "id": 112900,
                "name": "Republican Presidential Nominee 2028",
                "status": "open",
                "source": "polymarket",
                "top_outcomes": [
                    {"id": 91, "name": "J.D. Vance", "probability": 0.37},
                    {"id": 92, "name": "Marco Rubio", "probability": 0.16},
                    {"id": 93, "name": "Ron DeSantis", "probability": 0.15},
                ],
            },
            {
                "id": 131074,
                "name": "Will the 2028 Democratic Presidential nominee be a woman?",
                "status": "open",
                "source": "kalshi",
                "top_outcomes": [{"id": 101, "name": "Yes", "probability": 0.22}],
            },
            {
                "id": 108442,
                "name": "Will a Trump family member be the 2028 Republican presidential nominee?",
                "status": "open",
                "source": "kalshi",
                "top_outcomes": [{"id": 102, "name": "Yes", "probability": 0.04}],
            },
            {
                "id": 63115850,
                "name": "2028 U.S. Vice-Presidential Election winner",
                "status": "open",
                "source": "kalshi",
                "top_outcomes": [
                    {"id": 201, "name": "James Talarico", "probability": 0.16, "opening_probability": 0.09},
                    {"id": 202, "name": "Alexandria Ocasio-Cortez", "probability": 0.09, "opening_probability": 0.11},
                    {"id": 203, "name": "Pete Buttigieg", "probability": 0.05, "opening_probability": 0.06},
                ],
            },
            {
                "id": 68980426,
                "name": "Iowa Republican Presidential Caucus Winner 2028",
                "status": "open",
                "source": "polymarket",
                "top_outcomes": [
                    {"id": 231, "name": "J.D. Vance", "probability": 0.34},
                    {"id": 232, "name": "Marco Rubio", "probability": 0.21},
                    {"id": 233, "name": "Ron DeSantis", "probability": 0.12},
                ],
            },
            {
                "id": 67861937,
                "name": "2028 Presidential Election: North Carolina Winner",
                "status": "open",
                "source": "polymarket",
                "top_outcomes": [
                    {"id": 241, "name": "Democratic Party", "probability": 0.692},
                    {"id": 242, "name": "Republican Party", "probability": 0.308},
                ],
            },
            {
                "id": 25922306,
                "name": "2028 House winner",
                "status": "open",
                "source": "kalshi",
                "top_outcomes": [
                    {"id": 211, "name": "Democratic party", "probability": 0.79, "opening_probability": 0.74},
                    {"id": 212, "name": "Republican party", "probability": 0.21, "opening_probability": 0.26},
                ],
            },
            {
                "id": 108398,
                "name": "Ohio Senate winner? (2028)",
                "status": "open",
                "source": "kalshi",
                "top_outcomes": [
                    {"id": 221, "name": "Democratic party", "probability": 0.52, "opening_probability": 0.48},
                    {"id": 222, "name": "Republican party", "probability": 0.48, "opening_probability": 0.52},
                ],
            },
            {
                "id": 108399,
                "name": "Hawaii Senate winner? (2028)",
                "status": "open",
                "source": "kalshi",
                "top_outcomes": [
                    {"id": 225, "name": "Democratic party", "probability": 0.95, "opening_probability": 0.91},
                    {"id": 226, "name": "Republican party", "probability": 0.05, "opening_probability": 0.09},
                ],
            },
            {
                "id": 57574217,
                "name": "Fed Decision in January?",
                "status": "open",
                "source": "kalshi",
                "top_outcomes": [
                    {"id": 301, "name": "25 bps increase", "probability": 0.61, "opening_probability": 0.52},
                    {"id": 302, "name": "No change", "probability": 0.37, "opening_probability": 0.44},
                    {"id": 303, "name": "25 bps decrease", "probability": 0.01, "opening_probability": 0.02},
                    {"id": 304, "name": "50+ bps increase", "probability": 0.01, "opening_probability": 0.02},
                ],
            },
            {
                "id": 68032108,
                "name": "Fed decision in Apr 2027?",
                "status": "open",
                "source": "kalshi",
                "top_outcomes": [
                    {"id": 305, "name": "Fed maintains rate", "probability": 0.60},
                    {"id": 306, "name": "Hike 25bps", "probability": 0.24},
                    {"id": 307, "name": "Cut 25bps", "probability": 0.10},
                    {"id": 308, "name": "Cut >25bps", "probability": 0.06},
                ],
            },
            {
                "id": 114367,
                "name": "What will the Fed rate be at the end of 2026?",
                "status": "open",
                "source": "kalshi",
                "top_outcomes": [
                    {"id": 311, "name": "4.25%", "probability": 0.88, "opening_probability": 0.82},
                    {"id": 312, "name": "≥ 4.5%", "probability": 0.06, "opening_probability": 0.08},
                    {"id": 313, "name": "4.0%", "probability": 0.04, "opening_probability": 0.07},
                    {"id": 314, "name": "3.75%", "probability": 0.01, "opening_probability": 0.02},
                ],
            },
            {
                "id": 70732744,
                "name": "How many Fed rate hikes in 2026?",
                "status": "open",
                "source": "kalshi",
                "top_outcomes": [
                    {"id": 321, "name": "2 (50 bps)", "probability": 0.92, "opening_probability": 0.85},
                    {"id": 322, "name": "3 (75 bps)", "probability": 0.04, "opening_probability": 0.07},
                    {"id": 323, "name": "1 (25 bps)", "probability": 0.03, "opening_probability": 0.06},
                    {"id": 324, "name": "5+ (125+ bps)", "probability": 0.01, "opening_probability": 0.02},
                ],
            },
            {
                "id": 57574250,
                "name": "Fed Decision in December?",
                "status": "open",
                "source": "kalshi",
                "top_outcomes": [
                    {"id": 331, "name": "25 bps increase", "probability": 0.92, "opening_probability": 0.84},
                    {"id": 332, "name": "50+ bps increase", "probability": 0.04, "opening_probability": 0.06},
                    {"id": 333, "name": "No change", "probability": 0.03, "opening_probability": 0.08},
                ],
            },
            {
                "id": 113883,
                "name": "Fed rate cut by...?",
                "status": "open",
                "source": "kalshi",
                "top_outcomes": [
                    {"id": 341, "name": "April 2027 Meeting", "probability": 0.30, "opening_probability": 0.34},
                    {"id": 342, "name": "June 2027 Meeting", "probability": 0.26, "opening_probability": 0.24},
                    {"id": 343, "name": "March 2027 Meeting", "probability": 0.09, "opening_probability": 0.12},
                ],
            },
            {
                "id": 68169138,
                "name": "US GDP growth in Q4 2026?",
                "status": "open",
                "source": "kalshi",
                "top_outcomes": [
                    {"id": 371, "name": "2.5% to 3.0%", "probability": 0.31},
                    {"id": 372, "name": "2.0% to 2.5%", "probability": 0.28},
                    {"id": 373, "name": "≥4.0%", "probability": 0.18},
                ],
            },
            {
                "id": 109668,
                "name": "Unemployment rate in Nov 2026?",
                "status": "open",
                "source": "kalshi",
                "top_outcomes": [
                    {"id": 381, "name": "Exactly 4.1%", "probability": 0.34},
                    {"id": 382, "name": "Exactly 4.2%", "probability": 0.30},
                    {"id": 383, "name": "Exactly 4.0%", "probability": 0.19},
                ],
            },
            {
                "id": 114551,
                "name": "Predicted Fed rate under each Fed Chair",
                "status": "open",
                "source": "kalshi",
                "top_outcomes": [
                    {"id": 351, "name": "Kevin Warsh & Rate > 2.5%", "probability": 0.99, "opening_probability": 0.93},
                    {"id": 352, "name": "Rick Rieder & Rate ≤ 2.5%", "probability": 0.01, "opening_probability": 0.04},
                    {"id": 353, "name": "Kevin Warsh & Rate ≤ 2.5%", "probability": 0.01, "opening_probability": 0.02},
                ],
            },
            {
                "id": 12924898,
                "name": "Recession in 2027?",
                "status": "open",
                "source": "kalshi",
                "top_outcomes": [{"id": 361, "name": "Yes", "probability": 0.23}],
            },
            {
                "id": 58492239,
                "name": "Oscars 2027: Best Animated Feature Film Winner",
                "status": "open",
                "source": "kalshi",
                "top_outcomes": [
                    {"id": 601, "name": "Wildwood", "probability": 0.86, "opening_probability": 0.80},
                    {"id": 602, "name": "Toy Story 5", "probability": 0.08, "opening_probability": 0.12},
                    {"id": 603, "name": "Shrek 5", "probability": 0.04, "opening_probability": 0.05},
                ],
            },
            {
                "id": 58492242,
                "name": "Oscars 2027: Best International Feature Film Winner",
                "status": "open",
                "source": "kalshi",
                "top_outcomes": [
                    {"id": 611, "name": "La Bola Negra", "probability": 0.81, "opening_probability": 0.74},
                    {"id": 612, "name": "Sentimental Value", "probability": 0.12, "opening_probability": 0.16},
                    {"id": 613, "name": "Alpha", "probability": 0.05, "opening_probability": 0.06},
                ],
            },
            {
                "id": 999999,
                "name": "Closed stale 2028 Presidential Election winner? (Party)",
                "status": "closed",
                "source": "kalshi",
                "top_outcomes": [
                    {"id": 901, "name": "Democratic party", "probability": 0.50},
                    {"id": 902, "name": "Republican party", "probability": 0.50},
                ],
            },
        ],
        "market_histories": {
            # Oscars companion awards (real 7d movement >= 3pp)
            54: [{"t": "2026-09-28T00:00:00+00:00", "probability": 0.37}, {"t": "2026-10-04T12:00:00+00:00", "probability": 0.44}],
            57: [{"t": "2026-09-28T00:00:00+00:00", "probability": 0.48}, {"t": "2026-10-04T12:00:00+00:00", "probability": 0.55}],
            601: [{"t": "2026-09-28T00:00:00+00:00", "probability": 0.79}, {"t": "2026-10-04T12:00:00+00:00", "probability": 0.86}],
            611: [{"t": "2026-09-28T00:00:00+00:00", "probability": 0.74}, {"t": "2026-10-04T12:00:00+00:00", "probability": 0.81}],
            # 2028 Presidential primary, battleground, and VP movement
            201: [{"t": "2026-09-28T00:00:00+00:00", "probability": 0.10}, {"t": "2026-10-04T12:00:00+00:00", "probability": 0.16}],
            231: [{"t": "2026-09-28T00:00:00+00:00", "probability": 0.18}, {"t": "2026-10-04T12:00:00+00:00", "probability": 0.34}],
            241: [{"t": "2026-09-28T00:00:00+00:00", "probability": 0.56}, {"t": "2026-10-04T12:00:00+00:00", "probability": 0.69}],
            # Fed & Macro real 7d movement (January card + FOMC/cut + GDP/Unemployment)
            301: [{"t": "2026-09-28T00:00:00+00:00", "probability": 0.48}, {"t": "2026-10-04T12:00:00+00:00", "probability": 0.61}],
            305: [{"t": "2026-09-28T00:00:00+00:00", "probability": 0.46}, {"t": "2026-10-04T12:00:00+00:00", "probability": 0.60}],
            331: [{"t": "2026-09-28T00:00:00+00:00", "probability": 0.84}, {"t": "2026-10-04T12:00:00+00:00", "probability": 0.92}],
            341: [{"t": "2026-09-28T00:00:00+00:00", "probability": 0.19}, {"t": "2026-10-04T12:00:00+00:00", "probability": 0.30}],
            371: [{"t": "2026-09-28T00:00:00+00:00", "probability": 0.15}, {"t": "2026-10-04T12:00:00+00:00", "probability": 0.31}],
            381: [{"t": "2026-09-28T00:00:00+00:00", "probability": 0.24}, {"t": "2026-10-04T12:00:00+00:00", "probability": 0.34}],
            # 99% pinned lock with tail wiggle (must NOT count as moving)
            351: [{"t": "2026-09-28T00:00:00+00:00", "probability": 0.98}, {"t": "2026-10-04T12:00:00+00:00", "probability": 0.99}],
            352: [{"t": "2026-09-28T00:00:00+00:00", "probability": 0.04}, {"t": "2026-10-04T12:00:00+00:00", "probability": 0.01}],
        },
    }


def test_slice1_candidates_are_switched_off_and_contain_zero_hand_placed_ids() -> None:
    assert container_machinery_enabled() is False
    for path in MACHINERY_CANDIDATE_PATHS:
        assert path.exists()
        assert not (CONTAINERS_DATA_DIR / path.name).exists()
        raw = json.loads(path.read_text(encoding="utf-8"))
        validated = load_machinery_definition(path)
        assert validated["slug"] not in ROUNDUP_PRODUCERS
        for bad_key in HAND_LIST_ID_RULE_KEYS:
            assert bad_key not in raw.get("rule", {})
        serialized = json.dumps(raw)
        assert "market_id" not in serialized
        assert "event_id" not in serialized


def test_choose_section_form_is_purely_data_shape_driven() -> None:
    assert choose_section_form("paired_stage", [{}, {}, {}]) == "paired_stage_bars"
    assert (
        choose_section_form("events", [{"fav_prob": 0.52}, {"fav_prob": 0.58}])
        == "coin_flip_matchups"
    )
    assert (
        choose_section_form("events", [{"fav_prob": 0.85}, {"fav_prob": 0.79}])
        == "matchup_slate"
    )
    assert choose_section_form("markets", [{"outcomes": [{}, {}]}]) == "duel_bar"
    assert (
        choose_section_form("markets", [{"outcomes": [{}, {}, {}, {}]}])
        == "contender_spotlight"
    )
    assert (
        choose_section_form(
            "markets", [{"outcomes": [{}, {}, {}]}, {"outcomes": [{}, {}, {}]}]
        )
        == "sibling_fields_grid"
    )
    assert (
        choose_section_form("markets", [{"outcomes": [{}]}, {"outcomes": [{}]}])
        == "benchmark_strip"
    )


@pytest.mark.asyncio
async def test_same_code_path_produces_card_and_container_for_nfl_awards_and_politics() -> None:
    snap = _sample_snapshot()

    # 1. NFL Week
    nfl_def = load_machinery_definition(CANDIDATE_NFL_WEEK_PATH)
    nfl_prod = build_container_machinery_producer(nfl_def, enabled=lambda: True)
    nfl_card, nfl_page = await evaluate_roundup_producer(nfl_prod, snap, now=FIXED_NOW)
    assert nfl_card is not None and nfl_page is not None
    assert nfl_card["data"]["collection_ref"]["href"] == "/collections/machinery-nfl-week"
    assert nfl_card["data"]["roundup"]["machinery_card"]["form_id"] == "coin_flip_matchups"
    nfl_forms = [s["visual_block"]["form_id"] for s in nfl_page["sections"]]
    assert nfl_forms == [
        "coin_flip_matchups",
        "sibling_fields_grid",
        "matchup_slate",
        "contender_spotlight",
        "sibling_fields_grid",
    ]
    # Disjoint member IDs across sections so parseCollection never marks partial
    nfl_sec_ids = [[m["id"] for m in s["members"]] for s in nfl_page["sections"]]
    flat_nfl_ids = [i for sub in nfl_sec_ids for i in sub]
    assert len(flat_nfl_ids) == len(set(flat_nfl_ids))
    # Every NFL MVP contender and prop leader resolves a verified ESPN image URL
    mvp_outcomes = nfl_page["sections"][3]["visual_block"]["items"][0]["outcomes"]
    assert all(o["art"]["url"].startswith("https://a.espncdn.com/") for o in mvp_outcomes)

    # 2. Oscars Best Picture (reuses #12849 paired_metric_set on card and page + history chart)
    osc_def = load_machinery_definition(CANDIDATE_OSCARS_BEST_PICTURE_PATH)
    osc_prod = build_container_machinery_producer(osc_def, enabled=lambda: True)
    osc_card, osc_page = await evaluate_roundup_producer(osc_prod, snap, now=FIXED_NOW)
    assert osc_card is not None and osc_page is not None
    assert osc_card["data"]["roundup"]["paired_metric_set"]["set_id"] == "oscars-2027-best-picture"
    osc_forms = [s["visual_block"]["form_id"] for s in osc_page["sections"]]
    assert osc_forms == [
        "paired_stage_bars",
        "probability_history_chart",
        "contender_spotlight",
        "contender_spotlight",
    ] or osc_forms[:3] == [
        "paired_stage_bars",
        "probability_history_chart",
        "contender_spotlight",
    ]
    dir_outcomes = osc_page["sections"][2]["visual_block"]["items"][0]["outcomes"]
    assert all(o["art"]["url"].startswith("https://image.tmdb.org/") for o in dir_outcomes)

    # 3. 2028 Presidential Race (refuses closed market 999999; resolves verified portraits + history chart)
    pol_def = load_machinery_definition(CANDIDATE_2028_PRESIDENTIAL_PATH)
    pol_prod = build_container_machinery_producer(pol_def, enabled=lambda: True)
    pol_card, pol_page = await evaluate_roundup_producer(pol_prod, snap, now=FIXED_NOW)
    assert pol_card is not None and pol_page is not None
    assert pol_card["data"]["roundup"]["machinery_card"]["form_id"] == "contender_spotlight"
    pol_forms = [s["visual_block"]["form_id"] for s in pol_page["sections"]]
    assert pol_forms == [
        "duel_bar",
        "contender_spotlight",
        "probability_history_chart",
        "sibling_fields_grid",
    ]
    pol_member_ids = {m["id"] for s in pol_page["sections"] for m in s["members"]}
    assert 999999 not in pol_member_ids
    pres_outcomes = pol_page["sections"][1]["visual_block"]["items"][0]["outcomes"]
    assert all(o["art"]["url"].startswith("https://thumb.wikimedia.org/") for o in pres_outcomes)
    assert compose_roundup_container(pol_prod, await produce_container_machinery(snap, pol_def, now=FIXED_NOW)) is not None
    assert compose_roundup_feed_item(pol_prod, await produce_container_machinery(snap, pol_def, now=FIXED_NOW)) is not None


def test_subject_art_resolver_excludes_horror_and_falls_back_to_monogram() -> None:
    resolver = SubjectArtResolver()
    burrow = resolver.resolve("Joe Burrow")
    assert burrow["url"] == "https://a.espncdn.com/i/headshots/nfl/players/full/3915511.png"
    vance = resolver.resolve("J.D. Vance")
    assert vance["url"] and "wikimedia.org" in vance["url"]
    unknown = resolver.resolve("Unlisted Challenger")
    assert unknown["url"] is None
    assert unknown["initials"] == "UC"


def test_slice2_bar_no_question_word_proper_case_and_definition_only_fourth_grouping(
    tmp_path: Any,
) -> None:
    from app.utils.container_machinery import (
        _proper_case_outcome_label,
        discover_machinery_candidate_paths,
    )

    # 1. All 4 core unlike groupings discovered automatically (plus any definition-only candidates)
    paths = discover_machinery_candidate_paths()
    slugs = [load_machinery_definition(p)["slug"] for p in paths]
    assert {
        "machinery-2028-presidential",
        "machinery-fed-and-macro",
        "machinery-nfl-week",
        "machinery-oscars-best-picture",
    }.issubset(set(slugs))
    for p in paths:
        assert not (CONTAINERS_DATA_DIR / p.name).exists()
        raw_p = json.loads(p.read_text(encoding="utf-8"))
        for bad_key in HAND_LIST_ID_RULE_KEYS:
            assert bad_key not in raw_p.get("rule", {})
        ser_p = json.dumps(raw_p)
        assert "market_id" not in ser_p
        assert "event_id" not in ser_p

    # 2. Proper-casing miscased names without mangling numeric/rate brackets
    assert _proper_case_outcome_label("Anne hathaway") == "Anne Hathaway"
    assert _proper_case_outcome_label("Hike 25bps") == "Hike 25bps"
    assert _proper_case_outcome_label("Fed maintains rate") == "Fed maintains rate"
    assert _proper_case_outcome_label("Democratic party") == "Democratic party"

    # 3. Calling a market a 'question' in definition copy is rejected
    bad = json.loads(CANDIDATE_2028_PRESIDENTIAL_PATH.read_text(encoding="utf-8"))
    bad["rule"]["sections"][-1]["note"] = "Yes-or-no questions on the ticket."
    bad_path = tmp_path / "machinery-bad.json"
    bad_path.write_text(json.dumps(bad), encoding="utf-8")
    with pytest.raises(ValueError, match="question"):
        load_machinery_definition(bad_path)


@pytest.mark.asyncio
async def test_ruling_227a_visual_diversity_report_and_primitives_doc() -> None:
    from pathlib import Path
    from app.utils.container_machinery import (
        CANDIDATE_FED_AND_MACRO_PATH,
        compute_visual_diversity_report,
    )

    # 1. docs/design/grouping-primitives.md records 227: A under Sets and Presentations
    doc_path = Path(__file__).resolve().parents[2] / "docs" / "design" / "grouping-primitives.md"
    doc_text = doc_path.read_text(encoding="utf-8")
    sets_part = doc_text.split("### 3. Sets", 1)[1].split("### 4. Presentations", 1)[0]
    pres_part = doc_text.split("### 4. Presentations", 1)[1].split("### 5. Triggers", 1)[0]
    assert "227: A" in sets_part and "60%" in sets_part
    assert "227: A" in pres_part and "A picture on every screen" in pres_part

    # 2. Report-only diversity report computes points 1–4 without blocking serving
    snap = _sample_snapshot()
    nfl_def = load_machinery_definition(CANDIDATE_NFL_WEEK_PATH)
    nfl_prod = build_container_machinery_producer(nfl_def, enabled=lambda: True)
    nfl_card, nfl_page = await evaluate_roundup_producer(nfl_prod, snap, now=FIXED_NOW)
    rep = compute_visual_diversity_report(nfl_def, nfl_card, nfl_page)
    assert rep["standard"] == "227-A"
    assert rep["report_only"] is True
    assert rep["card"]["point_1_pictures_per_screen_390px"]["passes"] is True
    assert rep["page"]["point_1_pictures_per_screen_390px"]["passes"] is True
    assert rep["page"]["point_3_forms"]["form_count"] == 4
    assert rep["page"]["point_4_content_mix"]["content_kinds"]["games"] >= 1
    assert rep["page"]["point_4_content_mix"]["content_kinds"]["futures"] >= 1

    # Fed & Macro definition loads cleanly as 4th topic with zero topic code
    fed_def = load_machinery_definition(CANDIDATE_FED_AND_MACRO_PATH)
    assert fed_def["slug"] == "machinery-fed-and-macro"


@pytest.mark.asyncio
async def test_admin_only_machinery_preview_blocks_public_and_serves_admin(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from types import SimpleNamespace
    from fastapi import HTTPException
    from app.routes import admin_utils
    from app.routes.containers import get_container, get_machinery_preview
    from app.utils import container_corrections

    monkeypatch.setenv("CONTAINERS_READ_ENABLED", "true")
    monkeypatch.setenv("CONTAINER_MACHINERY_SLICE1_ENABLED", "false")

    snap = _sample_snapshot()
    req_signed_out = SimpleNamespace(
        headers={}, url=SimpleNamespace(path="/api/containers/preview/machinery")
    )
    req_signed_in_non_admin = SimpleNamespace(
        headers={"Authorization": "Bearer user-not-admin-token"},
        url=SimpleNamespace(path="/api/containers/preview/machinery"),
    )
    req_admin = SimpleNamespace(
        headers={"Authorization": "Bearer admin-ok"},
        url=SimpleNamespace(path="/api/containers/preview/machinery"),
    )

    async def _fake_admin_auth(secret: Any, request: Any, db: Any = None) -> bool:
        auth = (getattr(request, "headers", None) or {}).get("Authorization", "")
        return auth == "Bearer admin-ok"

    async def _fake_read_published(_db: Any, slug: str, *, include_headers: bool) -> Any:
        return SimpleNamespace(
            state=container_corrections.READ_UNAVAILABLE,
            slug=slug,
            revision=None,
            members=[],
        )

    monkeypatch.setattr(admin_utils, "_check_admin_auth", _fake_admin_auth)
    monkeypatch.setattr("app.routes.containers.read_published", _fake_read_published)

    # 1. Signed-out reader AND signed-in non-admin are both refused (403) on preview read
    for caller in (req_signed_out, req_signed_in_non_admin):
        with pytest.raises(HTTPException) as exc_preview:
            await get_machinery_preview(request=caller, slugs="machinery-nfl-week", db=snap)
        assert exc_preview.value.status_code == 403

        # 2. Both signed-out and signed-in non-admin are refused (404) on direct machinery-* page
        with pytest.raises(HTTPException) as exc_direct:
            await get_container(
                request=caller,
                slug="machinery-nfl-week",
                include_children=True,
                revision=None,
                cursor=None,
                limit=None,
                market_revision=None,
                market_cursor=None,
                market_limit=None,
                compact=True,
                debug_timing=False,
                db=snap,
            )
        assert exc_direct.value.status_code == 404

    # 3. Admin caller receives preview items + 227-A diversity_report while switch stays OFF
    preview_res = await get_machinery_preview(
        request=req_admin, slugs="machinery-nfl-week,machinery-2028-presidential", db=snap
    )
    assert preview_res["public_switch_enabled"] is False
    assert preview_res["count"] == 2
    assert [it["slug"] for it in preview_res["items"]] == [
        "machinery-nfl-week",
        "machinery-2028-presidential",
    ]
    assert preview_res["items"][0]["diversity_report"]["standard"] == "227-A"

    # 4. Direct /api/containers/machinery-nfl-week returns 200 for admin while global switch is OFF
    hub_res = await get_container(
        request=req_admin,
        slug="machinery-nfl-week",
        include_children=True,
        revision=None,
        cursor=None,
        limit=None,
        market_revision=None,
        market_cursor=None,
        market_limit=None,
        compact=True,
        debug_timing=False,
        db=snap,
    )
    assert hub_res["slug"] == "machinery-nfl-week"
    assert hub_res["state"] == "published"

    # 5. Even AFTER an admin previews, ROUNDUP_PRODUCERS holds zero machinery-* slugs
    #    so neither a signed-out reader nor a signed-in non-admin sees any machinery card
    #    on Discover, and both remain refused on subsequent direct reads.
    assert [s for s in ROUNDUP_PRODUCERS if s.startswith("machinery-")] == []
    for caller in (req_signed_out, req_signed_in_non_admin):
        with pytest.raises(HTTPException) as exc_after:
            await get_container(
                request=caller,
                slug="machinery-nfl-week",
                include_children=True,
                revision=None,
                cursor=None,
                limit=None,
                market_revision=None,
                market_cursor=None,
                market_limit=None,
                compact=True,
                debug_timing=False,
                db=snap,
            )
        assert exc_after.value.status_code == 404


@pytest.mark.asyncio
async def test_slice3_all_four_groupings_pass_227a_and_direction_228() -> None:
    import copy
    import re
    from app.utils.container_machinery import (
        CANDIDATE_FED_AND_MACRO_PATH,
        compute_visual_diversity_report,
        evaluate_machinery_candidates_preview,
    )

    snap = _sample_snapshot()
    core_slugs = [
        "machinery-nfl-week",
        "machinery-oscars-best-picture",
        "machinery-2028-presidential",
        "machinery-fed-and-macro",
    ]
    items = await evaluate_machinery_candidates_preview(snap, slugs=core_slugs, now=FIXED_NOW)
    assert [it["slug"] for it in items] == core_slugs

    for it in items:
        rep = it["diversity_report"]
        assert rep["overall_passes"] is True, f"{it['slug']} failed: {rep}"
        assert rep["card"]["overall_passes"] is True
        assert rep["page"]["overall_passes"] is True
        assert rep["page"]["point_2_longest_form_run"]["longest_row_run"] <= 3
        assert rep["page"]["point_4_content_mix"]["passes"] is True
        assert rep["page"]["direction_228_numerical_scale_order"]["passes"] is True
        # Slice 3 Item 5: settlement filler sentence dropped from card faces and page subtitles
        assert it["container"]["subtitle"] == ""
        card_contract = it["feed_item"]["data"]["roundup"]["machinery_card"]
        assert card_contract["footer"] == ""

    by_slug = {it["slug"]: it for it in items}

    # Slice 3 Item 3 & 4: NFL Week has prop leaders, names game + dates, never week number
    nfl_mix = by_slug["machinery-nfl-week"]["diversity_report"]["page"]["point_4_content_mix"]["content_kinds"]
    assert nfl_mix.get("props", 0) >= 2
    nfl_title = by_slug["machinery-nfl-week"]["container"]["container"]["name"]
    assert not re.search(r"\bweek\s+\d+\b", nfl_title, re.I)
    assert "Oct 4" in nfl_title and "toss-up" in nfl_title

    # Slice 3 Item 4: dynamic set-built title updates when set numbers change
    snap_shifted = copy.deepcopy(snap)
    snap_shifted["paired_sets"]["oscars-2027-best-picture"]["entries"][0]["stage_2_probability"] = 0.64
    shifted_items = await evaluate_machinery_candidates_preview(
        snap_shifted, slugs=["machinery-oscars-best-picture"], now=FIXED_NOW
    )
    assert "64%" in shifted_items[0]["container"]["container"]["name"]

    # Direction 228 (#12885): Fed & Macro scale rows run ascending by value, never by probability
    fed_page = by_slug["machinery-fed-and-macro"]["container"]
    jan_sec = next(s for s in fed_page["sections"] if s["class"] == "jan_fomc")
    jan_names = [o["name"] for o in jan_sec["visual_block"]["items"][0]["outcomes"]]
    assert jan_names == [
        "25 bps decrease",
        "No change",
        "25 bps increase",
        "50+ bps increase",
    ]
    rate_sec = next(s for s in fed_page["sections"] if s["class"] == "rate_path")
    by_mid = {m["market_id"]: [o["name"] for o in m["outcomes"]] for m in rate_sec["visual_block"]["items"]}
    assert by_mid[114367] == ["3.75%", "4.0%", "4.25%", "≥ 4.5%"]
    assert by_mid[70732744] == ["1 (25 bps)", "2 (50 bps)", "3 (75 bps)", "5+ (125+ bps)"]

    # Negative check: scrambling a numerical-scale market fails direction_228_numerical_scale_order
    tampered = copy.deepcopy(fed_page)
    for sec in tampered["sections"]:
        if sec["class"] == "rate_path":
            sec["visual_block"]["items"][0]["outcomes"] = list(
                reversed(sec["visual_block"]["items"][0]["outcomes"])
            )
    fed_def = load_machinery_definition(CANDIDATE_FED_AND_MACRO_PATH)
    bad_rep = compute_visual_diversity_report(
        fed_def, by_slug["machinery-fed-and-macro"]["feed_item"], tampered
    )
    assert bad_rep["overall_passes"] is False
    assert "direction_228_numerical_scale_order" in bad_rep["page"]["failing_points"]


@pytest.mark.asyncio
async def test_slice4_card_charts_own_headline_flat_line_is_not_picture_and_natural_prose_titles() -> None:
    import copy
    from app.utils.container_machinery import (
        CANDIDATE_FED_AND_MACRO_PATH,
        compute_visual_diversity_report,
        evaluate_machinery_candidates_preview,
    )

    snap = _sample_snapshot()
    items = await evaluate_machinery_candidates_preview(
        snap,
        slugs=[
            "machinery-nfl-week",
            "machinery-oscars-best-picture",
            "machinery-2028-presidential",
            "machinery-fed-and-macro",
        ],
        now=FIXED_NOW,
    )
    by_slug = {it["slug"]: it for it in items}

    # 1. Card's mini_chart shows the card's OWN headline market (57574217 "Fed Decision in January"),
    #    never a different market from another section ("Predicted Fed rate under each Fed Chair").
    fed_card = by_slug["machinery-fed-and-macro"]["feed_item"]["data"]["roundup"]["machinery_card"]
    assert "mini_chart" in fed_card
    assert fed_card["mini_chart"]["market_id"] == 57574217
    assert "January" in fed_card["mini_chart"]["title"]

    # 2. Natural prose market phrases in dynamic titles (no Title-Case market title dropped in capitals).
    pol_title = by_slug["machinery-2028-presidential"]["container"]["container"]["name"]
    assert "Presidential Election Winner" not in pol_title
    assert "presidential race" in pol_title
    assert "Democrats" in pol_title or "Republicans" in pol_title

    fed_title = by_slug["machinery-fed-and-macro"]["container"]["container"]["name"]
    assert "End-of-2026 Fed Rate" not in fed_title
    assert "The January Fed decision prices" in fed_title
    assert "end-of-2026 Fed rate" in fed_title

    # 3. A flat line is not a picture:
    #    (a) When all matched history markets are flat (opening_probability == probability),
    #        the section switches to a native market form instead of probability_history_chart.
    snap_flat = copy.deepcopy(snap)
    for m in snap_flat["markets"]:
        for o in m.get("top_outcomes") or ():
            o["opening_probability"] = o["probability"]
    snap_flat["market_histories"] = {}
    flat_fed = await evaluate_machinery_candidates_preview(
        snap_flat, slugs=["machinery-fed-and-macro"], now=FIXED_NOW
    )
    assert len(flat_fed) == 1
    # Card's mini_chart is omitted when the headline market did not move
    assert "mini_chart" not in flat_fed[0]["feed_item"]["data"]["roundup"]["machinery_card"]
    # And rate_history switched off probability_history_chart to a native shape form
    flat_forms = [s["visual_block"]["form_id"] for s in flat_fed[0]["container"]["sections"]]
    assert "probability_history_chart" not in flat_forms

    #    (b) Directly feeding a flat probability_history_chart into compute_visual_diversity_report
    #        counts 0 pictures toward Point 1 ("a picture on every screen").
    fed_def = load_machinery_definition(CANDIDATE_FED_AND_MACRO_PATH)
    flat_chart_page = {
        "member_count": 6,
        "container": {"name": "Fed"},
        "sections": [
            {
                "class": "rate_history",
                "layout": "probability_history_chart",
                "members": [{"type": "market", "id": 1, "card": {"content_kind": "history"}}],
                "visual_block": {
                    "form_id": "probability_history_chart",
                    "initial_visible_limit": 3,
                    "items": [
                        {
                            "market_id": 1,
                            "title": "Flat Market",
                            "moved": False,
                            "series": [{"outcome_id": 11, "points": [{"t": "t0", "pct": 84}, {"t": "t1", "pct": 84}]}],
                        }
                    ],
                },
            }
        ],
    }
    rep_flat = compute_visual_diversity_report(
        fed_def, flat_fed[0]["feed_item"], flat_chart_page
    )
    assert rep_flat["page"]["point_1_pictures_per_screen_390px"]["screens"] == [0]
    assert rep_flat["page"]["point_1_pictures_per_screen_390px"]["passes"] is False


@pytest.mark.asyncio
async def test_slice5_fable_six_notes_pairs_moving_charts_subject_headings_titles_and_fed_screen3() -> None:
    import copy
    from app.utils.container_machinery import (
        SubjectArtResolver,
        _clean_outcome_label,
        _clean_section_market_label,
        _history_chart_moved,
        _hydrate_event_visual_item,
        _hydrate_market_visual_item,
        evaluate_machinery_candidates_preview,
    )

    resolver = SubjectArtResolver()

    # 1. Two-way pairs MUST add to 100 (Ravens/Panthers, Jets/Chargers, Democratic/Republican).
    ravens_panthers = _hydrate_event_visual_item(
        {
            "id": 50001,
            "sport": "americanfootball_nfl",
            "away_team": "Baltimore Ravens",
            "home_team": "Carolina Panthers",
            "commence_time": "2026-11-22T18:00:00+00:00",
            "status": "scheduled",
            "current_odds": {"away_probability": 0.435, "home_probability": 0.565},
        },
        resolver=resolver,
    )
    assert ravens_panthers is not None
    assert (ravens_panthers["away_pct"], ravens_panthers["home_pct"]) == (43, 57)
    assert ravens_panthers["away_pct"] + ravens_panthers["home_pct"] == 100
    assert ravens_panthers["card"]["rendered_away_percent"] + ravens_panthers["card"]["rendered_home_percent"] == 100

    jets_chargers = _hydrate_event_visual_item(
        {
            "id": 50002,
            "sport": "americanfootball_nfl",
            "away_team": "New York Jets",
            "home_team": "Los Angeles Chargers",
            "commence_time": "2026-11-22T21:25:00+00:00",
            "status": "scheduled",
            "current_odds": {"away_probability": 0.375, "home_probability": 0.625},
        },
        resolver=resolver,
    )
    assert jets_chargers is not None
    assert (jets_chargers["away_pct"], jets_chargers["home_pct"]) == (37, 63)
    assert jets_chargers["away_pct"] + jets_chargers["home_pct"] == 100

    party_market = _hydrate_market_visual_item(
        {
            "id": 108327,
            "name": "2028 Presidential Election winner? (Party)",
            "status": "open",
            "source": "kalshi",
            "top_outcomes": [
                {"id": 61, "name": "Democratic party", "probability": 0.675},
                {"id": 62, "name": "Republican party", "probability": 0.325},
            ],
        },
        max_outcomes=2,
        resolver=resolver,
    )
    party_pcts = [o["rendered_percent"] for o in party_market["outcomes"]]
    assert party_pcts == [68, 32]
    assert sum(party_pcts) == 100
    assert [o["name"] for o in party_market["outcomes"]] == ["Democratic Party", "Republican Party"]

    # 2. No flat chart: 98-99% ceiling lock ("Kevin Warsh & Rate > 2.5%") fails moving-line test
    #    and opening_probability alone (without observed snapshots) never fakes movement.
    pinned_lock_chart = {
        "series": [
            {"outcome_id": 351, "current_pct": 99, "points": [{"t": "t0", "pct": 98}, {"t": "t1", "pct": 99}]},
            {"outcome_id": 352, "current_pct": 1, "points": [{"t": "t0", "pct": 4}, {"t": "t1", "pct": 1}]},
        ]
    }
    assert _history_chart_moved(pinned_lock_chart) is False

    snap = _sample_snapshot()
    items = await evaluate_machinery_candidates_preview(
        snap,
        slugs=[
            "machinery-nfl-week",
            "machinery-oscars-best-picture",
            "machinery-2028-presidential",
            "machinery-fed-and-macro",
        ],
        now=FIXED_NOW,
    )
    by_slug = {it["slug"]: it for it in items}

    # 3. Charts on the grouping's subject: 2028 Presidential never seats Senate or House seats.
    pol_sections = by_slug["machinery-2028-presidential"]["container"]["sections"]
    pol_member_ids = {m["id"] for s in pol_sections for m in s["members"]}
    assert 108398 not in pol_member_ids  # Ohio Senate
    assert 108399 not in pol_member_ids  # Hawaii Senate
    assert 25922306 not in pol_member_ids  # House
    # And Fed never seats "Predicted Fed rate under each Fed Chair" (114551)
    fed_sections = by_slug["machinery-fed-and-macro"]["container"]["sections"]
    fed_member_ids = {m["id"] for s in fed_sections for m in s["members"]}
    assert 114551 not in fed_member_ids

    # 4. Section title and description match BOTH the rendered form AND the actual rendered items.
    osc_hist_sec = next(
        s for s in by_slug["machinery-oscars-best-picture"]["container"]["sections"] if s["class"] == "best_picture_history"
    )
    assert osc_hist_sec["layout"] == "probability_history_chart"
    osc_shown_titles = [it["title"] for it in osc_hist_sec["visual_block"]["items"][:3]]
    for shown_t in osc_shown_titles:
        assert shown_t in osc_hist_sec["note"]
    assert "Best Actress" not in osc_hist_sec["note"]  # Best Actress is in acting_categories, not best_picture_history

    snap_no_hist = copy.deepcopy(snap)
    snap_no_hist["market_histories"] = {}
    osc_flat_res = await evaluate_machinery_candidates_preview(
        snap_no_hist, slugs=["machinery-oscars-best-picture"], now=FIXED_NOW
    )
    osc_fb_sec = next(
        s for s in osc_flat_res[0]["container"]["sections"] if s["class"] == "best_picture_history"
    )
    assert osc_fb_sec["layout"] == "sibling_fields_grid"
    assert osc_fb_sec["title"] == "Companion Category Odds"
    assert "Past Week" not in osc_fb_sec["title"]
    assert osc_fb_sec["note"].startswith("Current leaders across ")
    for shown_t in [it["title"] for it in osc_fb_sec["visual_block"]["items"][:3]]:
        assert shown_t in osc_fb_sec["note"]

    # 5. Our titles and outcome labels, never raw venue interrogatives or mixed bps phrasing.
    assert _clean_section_market_label("Hawaii Senate winner? (2028)") == "Hawaii Senate Race"
    assert _clean_section_market_label("What will Fed Rate hit before 2027?") == "Fed Rate Highs & Lows Before 2027"
    assert _clean_section_market_label("Fed decision in Apr 2027?") == "April 2027 Fed Decision"
    assert _clean_section_market_label("Oscar Winner: Best Music (Original Score)") == "Best Original Score"
    assert _clean_outcome_label("Hike 25bps") == "25 bps increase"
    assert _clean_outcome_label("Hike >25bps") == "50+ bps increase"
    assert _clean_outcome_label("Cut 25bps") == "25 bps decrease"
    assert _clean_outcome_label("Cut >25bps") == "50+ bps decrease"
    assert _clean_outcome_label("Fed maintains rate") == "No change"
    assert _clean_outcome_label("Exactly 4.1%") == "4.1%"

    # 6. Fed's third screen has a real picture (moving chart) and passes 227: A across all screens.
    fed_p1 = by_slug["machinery-fed-and-macro"]["diversity_report"]["page"]["point_1_pictures_per_screen_390px"]
    assert len(fed_p1["screens"]) >= 3
    assert fed_p1["min_pictures_per_screen"] >= 1
    assert fed_p1["passes"] is True
