"""Tests for #11949 Orders 2–4: ``field_leaders`` producer kind and new ``sibling_family`` definitions."""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

from app.utils.field_leaders import (
    OPENING_WEEKEND_SLUG,
    THIS_WEEKS_ECONOMIC_DATA_SLUG,
    TOMORROWS_HIGHS_SLUG,
    opening_weekend,
    select_field_leaders,
    this_weeks_economic_data,
    tomorrows_highs,
)
from app.utils.roundup_containers import (
    ROUNDUP_PRODUCERS,
    RoundupMembers,
    RoundupRefusal,
)
from app.utils.sibling_family import (
    RT_SCORES_THIS_WEEK_SLUG,
    WHO_ANNOUNCES_BEFORE_2027_SLUG,
    rt_scores_this_week,
    who_announces_before_2027,
)

NOW_UTC = datetime(2026, 11, 5, 18, 0, 0, tzinfo=timezone.utc)


def _city_market(
    mid: int,
    city: str,
    buckets: list[tuple[str, float]],
    *,
    title_date: str = "Nov 6",
    res_iso: str = "2026-11-06T16:00:00Z",
    obs_iso: str = "2026-11-05T17:30:00Z",
    mutually_exclusive: bool = True,
) -> dict:
    return {
        "id": mid,
        "name": f"Highest temperature in {city} on {title_date}?",
        "subject": city,
        "status": "open",
        "source": "kalshi",
        "category": "weather",
        "mutually_exclusive": mutually_exclusive,
        "resolution_date": res_iso,
        "prices_updated_at": obs_iso,
        "outcomes": [
            {
                "id": mid * 100 + idx + 1,
                "name": label,
                "probability": prob,
                "observed_at": obs_iso,
            }
            for idx, (label, prob) in enumerate(buckets)
        ],
    }


def test_roundup_producers_registered():
    for slug in (
        TOMORROWS_HIGHS_SLUG,
        OPENING_WEEKEND_SLUG,
        THIS_WEEKS_ECONOMIC_DATA_SLUG,
        RT_SCORES_THIS_WEEK_SLUG,
        WHO_ANNOUNCES_BEFORE_2027_SLUG,
    ):
        assert slug in ROUNDUP_PRODUCERS


@pytest.mark.asyncio
async def test_tomorrows_highs_least_likely_leaders_and_verbatim_bucket_labels():
    markets = [
        _city_market(101, "New York", [("52°–53°", 0.25), ("54°–55°", 0.34), ("56°–57°", 0.41)]),
        _city_market(102, "Chicago", [("44°–45°", 0.38), ("46°–47°", 0.32), ("48°–49°", 0.30)]),
        _city_market(103, "Miami", [("80°–81°", 0.48), ("82°–83°", 0.32), ("84°–85°", 0.20)]),
        _city_market(104, "Phoenix", [("86°–87°", 0.72), ("88°–89°", 0.18), ("90°–91°", 0.10)]),
    ]
    res = await tomorrows_highs(markets, now=NOW_UTC)
    assert isinstance(res, RoundupMembers)
    # Phoenix (72%) is excluded because least_likely_leader picks Chicago (38%), New York (41%), Miami (48%);
    # rows are ordered highest-first for RoundupCard display.
    labels = [r["label"] for r in res.rows]
    assert labels == [
        "Miami · 80°–81°",
        "New York · 56°–57°",
        "Chicago · 44°–45°",
    ]
    assert [r["rendered_percent"] for r in res.rows] == [48, 41, 38]


@pytest.mark.asyncio
async def test_tomorrows_highs_drops_tie_within_one_point_and_refuses_below_three():
    markets = [
        # Top two within 1 percentage point (40% vs 39.5%) -> dropped
        _city_market(101, "New York", [("52°–53°", 0.40), ("54°–55°", 0.395), ("56°–57°", 0.205)]),
        _city_market(102, "Chicago", [("44°–45°", 0.45), ("46°–47°", 0.35), ("48°–49°", 0.20)]),
        _city_market(103, "Miami", [("80°–81°", 0.50), ("82°–83°", 0.30), ("84°–85°", 0.20)]),
    ]
    res = await tomorrows_highs(markets, now=NOW_UTC)
    assert isinstance(res, RoundupRefusal)
    assert ("field_leaders", "too_few_coherent_members") in res.reasons


@pytest.mark.asyncio
async def test_tomorrows_highs_refuses_title_date_mismatch_and_stale_observation():
    mismatch_markets = [
        _city_market(101, "New York", [("52°–53°", 0.50), ("54°–55°", 0.50)], title_date="Nov 9"),
        _city_market(102, "Chicago", [("44°–45°", 0.55), ("46°–47°", 0.45)]),
        _city_market(103, "Miami", [("80°–81°", 0.60), ("82°–83°", 0.40)]),
    ]
    res_mismatch = await tomorrows_highs(mismatch_markets, now=NOW_UTC)
    assert isinstance(res_mismatch, RoundupRefusal)
    assert ("field_leaders", "title_date_mismatch:101") in res_mismatch.reasons

    stale_markets = [
        _city_market(
            101,
            "New York",
            [("52°–53°", 0.55), ("54°–55°", 0.45)],
            obs_iso="2026-11-05T08:00:00Z",  # 10 hours old > 6h limit
        ),
        _city_market(102, "Chicago", [("44°–45°", 0.55), ("46°–47°", 0.45)]),
        _city_market(103, "Miami", [("80°–81°", 0.60), ("82°–83°", 0.40)]),
    ]
    res_stale = await tomorrows_highs(stale_markets, now=NOW_UTC)
    assert isinstance(res_stale, RoundupRefusal)
    assert ("field_leaders", "stale_observation:101") in res_stale.reasons


@pytest.mark.asyncio
async def test_opening_weekend_withholds_under_three_and_emits_at_three():
    two_films = [
        {
            "id": 201,
            "name": "Wicked: For Good opening weekend box office",
            "status": "open",
            "source": "kalshi",
            "category": "entertainment",
            "mutually_exclusive": True,
            "resolution_date": "2026-11-09T12:00:00Z",
            "prices_updated_at": "2026-11-05T17:00:00Z",
            "outcomes": [
                {"id": 2011, "name": "$90M–$110M", "probability": 0.52},
                {"id": 2012, "name": "$110M+", "probability": 0.48},
            ],
        },
        {
            "id": 202,
            "name": "Gladiator II opening weekend box office",
            "status": "open",
            "source": "kalshi",
            "category": "entertainment",
            "mutually_exclusive": True,
            "resolution_date": "2026-11-09T12:00:00Z",
            "prices_updated_at": "2026-11-05T17:00:00Z",
            "outcomes": [
                {"id": 2021, "name": "$60M–$75M", "probability": 0.58},
                {"id": 2022, "name": "$75M+", "probability": 0.42},
            ],
        },
    ]
    refused = await opening_weekend(two_films, now=NOW_UTC)
    assert isinstance(refused, RoundupRefusal)

    three_films = two_films + [
        {
            "id": 203,
            "name": "Moana 2 opening weekend box office",
            "status": "open",
            "source": "kalshi",
            "category": "entertainment",
            "mutually_exclusive": True,
            "resolution_date": "2026-11-09T12:00:00Z",
            "prices_updated_at": "2026-11-05T17:00:00Z",
            "outcomes": [
                {"id": 2031, "name": "$120M–$140M", "probability": 0.64},
                {"id": 2032, "name": "$140M+", "probability": 0.36},
            ],
        }
    ]
    emitted = await opening_weekend(three_films, now=NOW_UTC)
    assert isinstance(emitted, RoundupMembers)
    assert [r["label"] for r in emitted.rows] == [
        "Moana 2 · $120M–$140M",
        "Gladiator II · $60M–$75M",
        "Wicked: For Good · $90M–$110M",
    ]


@pytest.mark.asyncio
async def test_this_weeks_economic_data_refuses_missing_release_time_and_cumulative_ladders():
    missing_release = [
        {
            "id": 301,
            "name": "Core CPI MoM in October 2026",
            "status": "open",
            "source": "kalshi",
            "category": "economics",
            "mutually_exclusive": True,
            "prices_updated_at": "2026-11-05T17:00:00Z",
            "outcomes": [
                {"id": 3011, "name": "0.2%", "probability": 0.55},
                {"id": 3012, "name": "0.3%", "probability": 0.45},
            ],
        }
    ]
    res_missing = await this_weeks_economic_data(missing_release, now=NOW_UTC)
    assert isinstance(res_missing, RoundupRefusal)
    assert ("field_leaders", "missing_release_time:301") in res_missing.reasons

    cumulative_ladder = [
        {
            "id": 302,
            "name": "U.S. Payrolls in October 2026",
            "status": "open",
            "source": "kalshi",
            "category": "economics",
            "mutually_exclusive": True,
            "release_at": "2026-11-06T13:30:00Z",
            "prices_updated_at": "2026-11-05T17:00:00Z",
            "outcomes": [
                {"id": 3021, "name": "Above 100k", "probability": 0.72},
                {"id": 3022, "name": "Above 150k", "probability": 0.48},
                {"id": 3023, "name": "Above 200k", "probability": 0.21},
            ],
        }
    ]
    res_cum = await this_weeks_economic_data(cumulative_ladder, now=NOW_UTC)
    assert isinstance(res_cum, RoundupRefusal)
    assert ("field_leaders", "cumulative_ladder_not_allowed:302") in res_cum.reasons


@pytest.mark.asyncio
async def test_rt_scores_this_week_auto_shared_rung_and_refusals():
    # Three films with strict "Above X" rungs where "Above 70" has all 3 inside 5-95%
    valid_films = [
        {
            "id": 401,
            "name": "Predator: Badlands Rotten Tomatoes score?",
            "status": "open",
            "source": "kalshi",
            "category": "entertainment",
            "resolution_date": "2026-11-10T00:00:00Z",
            "prices_updated_at": "2026-11-05T17:00:00Z",
            "outcomes": [
                {"id": 4011, "name": "Above 60", "probability": 0.85},
                {"id": 4012, "name": "Above 70", "probability": 0.62},
                {"id": 4013, "name": "Above 80", "probability": 0.31},
            ],
        },
        {
            "id": 402,
            "name": "Die My Love Rotten Tomatoes score?",
            "status": "open",
            "source": "kalshi",
            "category": "entertainment",
            "resolution_date": "2026-11-10T00:00:00Z",
            "prices_updated_at": "2026-11-05T17:00:00Z",
            "outcomes": [
                {"id": 4021, "name": "Above 60", "probability": 0.78},
                {"id": 4022, "name": "Above 70", "probability": 0.54},
                {"id": 4023, "name": "Above 80", "probability": 0.22},
            ],
        },
        {
            "id": 403,
            "name": "Christy Rotten Tomatoes score?",
            "status": "open",
            "source": "kalshi",
            "category": "entertainment",
            "resolution_date": "2026-11-10T00:00:00Z",
            "prices_updated_at": "2026-11-05T17:00:00Z",
            "outcomes": [
                {"id": 4031, "name": "Above 60", "probability": 0.71},
                {"id": 4032, "name": "Above 70", "probability": 0.48},
                {"id": 4033, "name": "Above 80", "probability": 0.19},
            ],
        },
    ]
    emitted = await rt_scores_this_week(valid_films, now=NOW_UTC)
    assert isinstance(emitted, RoundupMembers)
    # Highest qualifying shared rung is Above 80 (all 3 are in [0.05, 0.95]: 31%, 22%, 19%)
    assert [r["rendered_percent"] for r in emitted.rows] == [31, 22, 19]

    # When 2 of 3 films are at 99.5% on the only shared rung -> refuses
    saturated_films = [
        {
            **valid_films[0],
            "outcomes": [{"id": 4011, "name": "Above 70", "probability": 0.995}],
        },
        {
            **valid_films[1],
            "outcomes": [{"id": 4021, "name": "Above 70", "probability": 0.995}],
        },
        {
            **valid_films[2],
            "outcomes": [{"id": 4031, "name": "Above 70", "probability": 0.715}],
        },
    ]
    refused_sat = await rt_scores_this_week(saturated_films, now=NOW_UTC)
    assert isinstance(refused_sat, RoundupRefusal)
    assert ("family", "no_shared_rung_in_band") in refused_sat.reasons

    # When a film has a non-strict "50 or more" rung -> refuses
    non_strict = [
        valid_films[0],
        valid_films[1],
        {
            **valid_films[2],
            "outcomes": [
                {"id": 4031, "name": "50 or more", "probability": 0.80},
                {"id": 4032, "name": "Above 70", "probability": 0.48},
            ],
        },
    ]
    refused_ns = await rt_scores_this_week(non_strict, now=NOW_UTC)
    assert isinstance(refused_ns, RoundupRefusal)
    assert ("family", "non_strict_rung:403") in refused_ns.reasons


@pytest.mark.asyncio
async def test_who_announces_before_2027_groups_capitalized_and_lowercase_presidential():
    candidates = [
        {
            "id": 501,
            "name": "Will Gavin Newsom announce a Presidential run before 2027?",
            "status": "open",
            "source": "kalshi",
            "category": "politics",
            "resolution_date": "2026-12-31T23:59:00Z",
            "prices_updated_at": "2026-11-05T17:00:00Z",
            "outcomes": [
                {"id": 5011, "name": "Yes", "probability": 0.25},
                {"id": 5012, "name": "No", "probability": 0.75},
            ],
        },
        {
            "id": 502,
            "name": "Will Pete Buttigieg announce a presidential run before 2027?",
            "status": "open",
            "source": "kalshi",
            "category": "politics",
            "resolution_date": "2026-12-31T23:59:00Z",
            "prices_updated_at": "2026-11-05T17:00:00Z",
            "outcomes": [
                {"id": 5021, "name": "Yes", "probability": 0.25},
                {"id": 5022, "name": "No", "probability": 0.75},
            ],
        },
        {
            "id": 503,
            "name": "Will Alexandria Ocasio-Cortez announce a presidential run before 2027?",
            "status": "open",
            "source": "kalshi",
            "category": "politics",
            "resolution_date": "2026-12-31T23:59:00Z",
            "prices_updated_at": "2026-11-05T17:00:00Z",
            "outcomes": [
                {"id": 5031, "name": "Yes", "probability": 0.22},
                {"id": 5032, "name": "No", "probability": 0.78},
            ],
        },
        {
            "id": 504,
            "name": "Will Josh Shapiro announce a presidential run before 2027?",
            "status": "open",
            "source": "kalshi",
            "category": "politics",
            "resolution_date": "2026-12-31T23:59:00Z",
            "prices_updated_at": "2026-11-05T17:00:00Z",
            "outcomes": [
                {"id": 5041, "name": "Yes", "probability": 0.16},
                {"id": 5042, "name": "No", "probability": 0.84},
            ],
        },
    ]
    res = await who_announces_before_2027(candidates, now=NOW_UTC)
    assert isinstance(res, RoundupMembers)
    labels = [r["label"] for r in res.rows]
    assert "Gavin Newsom" in labels
    assert "Pete Buttigieg" in labels
    assert len(res.rows) == 3
    assert len(res.members) == 4
