"""Unit and integration tests for the ``sibling_family`` producer kind (§1.3 of ``docs/discover/grouping-types-2026-11.md``)."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

import pytest

from app.utils.roundup_containers import (
    ROUNDUP_PRODUCERS,
    RoundupMembers,
    RoundupRefusal,
    compose_roundup_container,
    compose_roundup_feed_item,
    evaluate_roundup_producer,
    insert_roundup_feed_items,
    reset_roundup_cache_for_tests,
)
from app.utils.sibling_family import (
    GTA_VI_ALBUM_FEATURES_DEFINITION,
    GTA_VI_ALBUM_FEATURES_PRODUCER,
    GTA_VI_ALBUM_FEATURES_SLUG,
    MEMBERSHIP_SIBLING_FAMILY,
    PRODUCER_KIND_SIBLING_FAMILY,
    SNOW_FIRST_FLAKES_2026_DEFINITION,
    SNOW_FIRST_FLAKES_2026_PRODUCER,
    SNOW_FIRST_FLAKES_2026_SLUG,
    detect_sibling_template_pair,
    fold_template_key,
    gta_vi_album_features,
    select_sibling_family,
    snow_first_flakes_2026,
)

NOW_NOV_3 = datetime(2026, 11, 3, 23, 0, 0, tzinfo=timezone.utc)
OBS = "2026-11-03T22:00:00Z"


def _make_binary_market(
    market_id: int,
    name: str,
    probability: float | None,
    *,
    source: str = "polymarket",
    category: str = "weather",
    resolution_date: str = "2026-11-19T04:59:00Z",
    status: str = "open",
    market_type: str = "container_member",
    is_winner: bool = False,
    resolution_source: str | None = None,
) -> dict[str, Any]:
    no_prob = round(1.0 - probability, 6) if probability is not None else None
    return {
        "id": market_id,
        "name": name,
        "status": status,
        "source": source,
        "category": category,
        "llm_sport_category": category,
        "market_tier": 2,
        "market_type": market_type,
        "mutually_exclusive": True,
        "resolution_date": resolution_date,
        "updated_at": OBS,
        "outcomes": [
            {
                "id": market_id * 10 + 1,
                "name": "Yes",
                "probability": probability,
                "is_winner": is_winner,
                "resolution_source": resolution_source,
                "observed_at": OBS,
            },
            {
                "id": market_id * 10 + 2,
                "name": "No",
                "probability": no_prob,
                "is_winner": False,
                "resolution_source": resolution_source,
                "observed_at": OBS,
            },
        ],
    }


def _live_snow_pool(*, denver_resolved: bool = True) -> list[dict[str, Any]]:
    """Today's live Polymarket snow markets (group_id='polymarket:956007'), including
    the 31-outcome combined market 60084865, the two past-deadline Oct 31 markets
    60084867-68, the 10 Nov 15 binaries, and the 17 Nov 30 binaries.
    """
    combined_60084865 = {
        "id": 60084865,
        "name": "First snow of the 2026 season",
        "status": "open",
        "source": "polymarket",
        "category": "weather",
        "market_type": "field",
        "mutually_exclusive": False,
        "resolution_date": "2026-12-04T04:59:00Z",
        "outcomes": [
            {"id": 6008486501, "name": "Buffalo by November 15", "probability": 0.45},
            {"id": 6008486502, "name": "Denver by November 30", "probability": 0.971},
            {"id": 6008486503, "name": "Salt Lake City by November 15", "probability": 0.34},
        ],
    }
    oct_31 = [
        _make_binary_market(
            60084867,
            "Will it snow in Denver, CO by October 31?",
            None,
            resolution_date="2026-11-04T04:59:00Z",
            status="resolved",
        ),
        _make_binary_market(
            60084868,
            "Will it snow in Salt Lake City, UT by October 31?",
            0.038,
            resolution_date="2026-11-04T04:59:00Z",
            status="open",
        ),
    ]
    nov_15 = [
        _make_binary_market(60087431, "Will it snow in Indianapolis, IN by November 15?", 0.485),
        _make_binary_market(60087427, "Will it snow in Buffalo, NY by November 15?", 0.45),
        _make_binary_market(60087426, "Will it snow in Boston, MA by November 15?", 0.38),
        _make_binary_market(60087435, "Will it snow in Salt Lake City, UT by November 15?", 0.34),
        _make_binary_market(60084869, "Will it snow in Kansas City, MO by November 15?", 0.255),
        _make_binary_market(60087428, "Will it snow in Chicago, IL by November 15?", 0.25),
        _make_binary_market(
            60087429,
            "Will it snow in Denver, CO by November 15?",
            1.0 if denver_resolved else 0.40,
            status="resolved" if denver_resolved else "open",
        ),
        _make_binary_market(60087430, "Will it snow in Detroit, MI by November 15?", None),
        _make_binary_market(60087433, "Will it snow in Minneapolis, MN by November 15?", None),
        _make_binary_market(60087434, "Will it snow in Pittsburgh, PA by November 15?", None),
    ]
    res_nov_30 = "2026-12-04T04:59:00Z"
    nov_30 = [
        _make_binary_market(60084875, "Will it snow in Salt Lake City, UT by November 30?", 0.9535, resolution_date=res_nov_30),
        _make_binary_market(60087449, "Will it snow in Pittsburgh, PA by November 30?", 0.86, resolution_date=res_nov_30),
        _make_binary_market(60087442, "Will it snow in Detroit, MI by November 30?", 0.85, resolution_date=res_nov_30),
        _make_binary_market(60084872, "Will it snow in Kansas City, MO by November 30?", 0.805, resolution_date=res_nov_30),
        _make_binary_market(60087445, "Will it snow in Minneapolis, MN by November 30?", 0.80, resolution_date=res_nov_30),
        _make_binary_market(60087438, "Will it snow in Chicago, IL by November 30?", 0.78, resolution_date=res_nov_30),
        _make_binary_market(60084871, "Will it snow in Indianapolis, IN by November 30?", 0.6895, resolution_date=res_nov_30),
        _make_binary_market(60084873, "Will it snow in New York City, NY by November 30?", 0.68, resolution_date=res_nov_30),
        _make_binary_market(60084870, "Will it snow in Buffalo, NY by November 30?", 0.673, resolution_date=res_nov_30),
        _make_binary_market(60087436, "Will it snow in Boston, MA by November 30?", 0.665, resolution_date=res_nov_30),
        _make_binary_market(60084876, "Will it snow in St. Louis, MO by November 30?", 0.57, resolution_date=res_nov_30),
        _make_binary_market(60104328, "Will it snow in Washington, DC by November 30?", 0.39, resolution_date=res_nov_30),
        _make_binary_market(60084874, "Will it snow in Philadelphia, PA by November 30?", 0.385, resolution_date=res_nov_30),
        _make_binary_market(60087446, "Will it snow in Nashville, TN by November 30?", 0.29, resolution_date=res_nov_30),
        _make_binary_market(60087440, "Will it snow in Dallas, TX by November 30?", 0.155, resolution_date=res_nov_30),
        _make_binary_market(60087439, "Will it snow in Cincinnati, OH by November 30?", None, resolution_date=res_nov_30),
        _make_binary_market(
            60087441,
            "Will it snow in Denver, CO by November 30?",
            1.0 if denver_resolved else 0.971,
            resolution_date=res_nov_30,
            status="resolved" if denver_resolved else "open",
        ),
    ]
    return [combined_60084865, *oct_31, *nov_15, *nov_30]


def _live_gta_pool() -> list[dict[str, Any]]:
    """Today's live Polymarket GTA VI album feature markets (group_id='polymarket:1040302'),
    including the 12-outcome combined field market 61321728 and the 12 artist binaries.
    """
    res_nov_26 = "2026-11-26T00:00:00Z"
    combined_61321728 = {
        "id": 61321728,
        "name": "Who will be featured on GTA VI: The Album?",
        "status": "open",
        "source": "polymarket",
        "category": "entertainment",
        "market_type": "field",
        "mutually_exclusive": False,
        "resolution_date": "2026-11-27T04:59:00Z",
        "outcomes": [
            {"id": 230962935, "name": "Kodak Black", "probability": 0.785},
            {"id": 230962933, "name": "Don Toliver", "probability": 0.775},
            {"id": 230843011, "name": "The Weeknd", "probability": 0.775},
        ],
    }
    binaries = [
        _make_binary_market(61353752, "Will Kodak Black be featured on GTA VI: The Album?", 0.785, category="entertainment", resolution_date=res_nov_26),
        _make_binary_market(61361196, "Will Don Toliver be featured on GTA VI: The Album?", 0.775, category="entertainment", resolution_date=res_nov_26),
        _make_binary_market(61321730, "Will The Weeknd be featured on GTA VI: The Album?", 0.775, category="entertainment", resolution_date=res_nov_26),
        _make_binary_market(61321731, "Will Bad Bunny be featured on GTA VI: The Album?", 0.375, category="entertainment", resolution_date=res_nov_26),
        _make_binary_market(61341730, "Will Drake be featured on GTA VI: The Album?", 0.32, category="entertainment", resolution_date=res_nov_26),
        _make_binary_market(61350058, "Will Sexyy Red be featured on GTA VI: The Album?", 0.315, category="entertainment", resolution_date=res_nov_26),
        _make_binary_market(61321729, "Will Playboi Carti be featured on GTA VI: The Album?", 0.26, category="entertainment", resolution_date=res_nov_26),
        _make_binary_market(61363935, "Will Kendrick Lamar be featured on GTA VI: The Album?", 0.235, category="entertainment", resolution_date=res_nov_26),
        _make_binary_market(61363937, "Will Frank Ocean be featured on GTA VI: The Album?", 0.105, category="entertainment", resolution_date=res_nov_26),
        _make_binary_market(61341729, "Will XXXTentacion be featured on GTA VI: The Album?", 0.07, category="entertainment", resolution_date=res_nov_26),
        _make_binary_market(61363930, "Will Osamason be featured on GTA VI: The Album?", None, category="entertainment", resolution_date=res_nov_26),
        _make_binary_market(61363931, "Will Nettspend be featured on GTA VI: The Album?", None, category="entertainment", resolution_date=res_nov_26),
    ]
    return [combined_61321728, *binaries]


class TestTemplateDetectionAndCaseFolding:
    def test_case_and_spacing_folded_into_one_template_key(self) -> None:
        pair, err = detect_sibling_template_pair(
            "Will Pete Buttigieg announce a Presidential run",
            "Will   Gavin Newsom  announce a presidential run?",
        )
        assert err is None
        assert pair == (
            "will * announce a presidential run",
            "Pete Buttigieg",
            "Gavin Newsom",
        )
        assert fold_template_key("Will * announce a Presidential run?") == (
            "will * announce a presidential run"
        )

    def test_refuses_when_differing_run_is_longer_than_shared_part(self) -> None:
        """Ruling 145 specimen: 'Alcaraz to win the US Open in 2026' vs
        'Sinner to win the Australian Open in 2026' has a 6-token differing run
        against 2-3 shared tokens and must be refused.
        """
        pair, err = detect_sibling_template_pair(
            "Alcaraz to win the US Open",
            "Sinner to win the Australian Open",
        )
        assert pair is None
        assert err == "differing_run_exceeds_shared"

        markets = [
            _make_binary_market(9001, "Alcaraz to win the US Open in 2026", 0.45, resolution_date="2026-12-31T00:00:00Z"),
            _make_binary_market(9002, "Sinner to win the Australian Open in 2026", 0.50, resolution_date="2026-12-31T00:00:00Z"),
            _make_binary_market(9003, "Djokovic to win the French Open in 2026", 0.30, resolution_date="2026-12-31T00:00:00Z"),
        ]
        res = select_sibling_family(markets, now=NOW_NOV_3)
        assert isinstance(res, RoundupRefusal)
        assert ("family", "differing_run_exceeds_shared") in res.reasons


class TestSiblingFamilyRefusals:
    def test_refuses_time_person_of_the_year_mixed_stored_resolution_dates(self) -> None:
        """TIME Person of the Year 2026: binaries share one title year (2026) but
        carry three stored resolution dates (Dec 31 2026, Jan 1 2027, Jul 1 2027).
        """
        markets = [
            _make_binary_market(64176401, "Will Elon Musk be TIME Person of the Year for 2026?", 0.22, category="culture", resolution_date="2026-12-31T23:59:00Z"),
            _make_binary_market(64176469, "Will Sam Altman be TIME Person of the Year for 2026?", 0.18, category="culture", resolution_date="2027-01-01T00:00:00Z"),
            _make_binary_market(27467307, "Will Donald Trump be TIME Person of the Year for 2026?", 0.15, category="culture", resolution_date="2027-07-01T00:00:00Z"),
            _make_binary_market(64176470, "Will Taylor Swift be TIME Person of the Year for 2026?", 0.09, category="culture", resolution_date="2026-12-31T23:59:00Z"),
        ]
        res = select_sibling_family(markets, now=NOW_NOV_3)
        assert isinstance(res, RoundupRefusal)
        reasons = dict(res.reasons)
        assert reasons.get("family") in {
            "resolution_date_disagrees_with_title",
            "inconsistent_resolution_dates",
        }

    def test_refuses_2028_announce_run_split_by_case_and_stored_dates(self) -> None:
        """'Announce a presidential run before 2028': split by 'Presidential' vs
        'presidential' and by stored date Dec 31, 2026 vs Jan 1, 2028. Case folding
        unites them into one family, and the stored date disagreement refuses the card.
        """
        markets = [
            _make_binary_market(7001, "Will Gavin Newsom announce a Presidential run before 2028?", 0.62, category="politics", resolution_date="2026-12-31T23:59:00Z"),
            _make_binary_market(7002, "Will Josh Shapiro announce a presidential run before 2028?", 0.48, category="politics", resolution_date="2028-01-01T00:00:00Z"),
            _make_binary_market(7003, "Will Pete Buttigieg announce a Presidential run before 2028?", 0.41, category="politics", resolution_date="2028-01-01T00:00:00Z"),
            _make_binary_market(7004, "Will Wes Moore announce a presidential run before 2028?", 0.33, category="politics", resolution_date="2028-01-01T00:00:00Z"),
        ]
        res = select_sibling_family(markets, now=NOW_NOV_3)
        assert isinstance(res, RoundupRefusal)
        reasons = dict(res.reasons)
        assert reasons.get("family") in {
            "resolution_date_disagrees_with_title",
            "inconsistent_resolution_dates",
        }

    def test_refuses_when_fewer_than_three_members_have_a_number(self) -> None:
        markets = [
            _make_binary_market(60087431, "Will it snow in Indianapolis, IN by November 15?", 0.485),
            _make_binary_market(60087427, "Will it snow in Buffalo, NY by November 15?", 0.45),
            _make_binary_market(60087430, "Will it snow in Detroit, MI by November 15?", None),
            _make_binary_market(60087433, "Will it snow in Minneapolis, MN by November 15?", None),
        ]
        res = select_sibling_family(
            markets,
            strip_state_suffix=True,
            subject_unit="cities",
            now=NOW_NOV_3,
        )
        assert isinstance(res, RoundupRefusal)
        assert ("family", "too_few_numbered_members") in res.reasons

    def test_refuses_incoherent_member_ladder_denver_65536371(self) -> None:
        """December snow totals (Kalshi): Denver 65536371 prints 'Above 6 inches'
        at 64.0% over 'Above 4 inches' at 59.5%, refusing the whole family.
        """
        res_dec = "2026-12-31T23:59:00Z"
        markets = [
            {
                "id": 65536370,
                "name": "Snow in Minneapolis in Dec 2026?",
                "status": "open",
                "source": "kalshi",
                "category": "weather",
                "mutually_exclusive": False,
                "resolution_date": res_dec,
                "outcomes": [
                    {"id": 655363701, "name": "Above 4 inches", "probability": 0.815, "observed_at": OBS},
                    {"id": 655363702, "name": "Above 6 inches", "probability": 0.65, "observed_at": OBS},
                ],
            },
            {
                "id": 65536371,
                "name": "Snow in Denver in Dec 2026?",
                "status": "open",
                "source": "kalshi",
                "category": "weather",
                "mutually_exclusive": False,
                "resolution_date": res_dec,
                "outcomes": [
                    {"id": 655363711, "name": "Above 4 inches", "probability": 0.595, "observed_at": OBS},
                    {"id": 655363712, "name": "Above 6 inches", "probability": 0.64, "observed_at": OBS},
                ],
            },
            {
                "id": 65536372,
                "name": "Snow in Pittsburgh in Dec 2026?",
                "status": "open",
                "source": "kalshi",
                "category": "weather",
                "mutually_exclusive": False,
                "resolution_date": res_dec,
                "outcomes": [
                    {"id": 655363721, "name": "Above 4 inches", "probability": 0.595, "observed_at": OBS},
                    {"id": 655363722, "name": "Above 6 inches", "probability": 0.42, "observed_at": OBS},
                ],
            },
        ]
        res = select_sibling_family(
            markets,
            outcome_name="Above 4 inches",
            now=NOW_NOV_3,
        )
        assert isinstance(res, RoundupRefusal)
        assert ("family", "incoherent_ladder:65536371") in res.reasons

    def test_refuses_incoherent_one_winner_field_next_team_67541294(self) -> None:
        """Kalshi '‹player› Next Team': Saquon Barkley 67541294 top three outcomes
        alone sum to 181.5%, refusing the family.
        """
        res_dec_1 = "2026-12-01T23:59:00Z"
        markets = [
            {
                "id": 67541294,
                "name": "Saquon Barkley Next Team",
                "status": "open",
                "source": "kalshi",
                "category": "nfl",
                "market_type": "field",
                "mutually_exclusive": True,
                "resolution_date": res_dec_1,
                "outcomes": [
                    {"id": 1, "name": "Eagles", "probability": 0.75},
                    {"id": 2, "name": "Giants", "probability": 0.58},
                    {"id": 3, "name": "Cowboys", "probability": 0.485},
                ],
            },
            {
                "id": 67541295,
                "name": " Cooper Kupp Next Team",
                "status": "open",
                "source": "kalshi",
                "category": "nfl",
                "market_type": "field",
                "mutually_exclusive": True,
                "resolution_date": res_dec_1,
                "outcomes": [
                    {"id": 4, "name": "Rams", "probability": 0.60},
                    {"id": 5, "name": "Chiefs", "probability": 0.35},
                ],
            },
        ]
        res = select_sibling_family(
            markets,
            outcome_name="Eagles",
            exclude_combined_market=False,
            now=NOW_NOV_3,
        )
        assert isinstance(res, RoundupRefusal)
        assert ("family", "incoherent_field_sum:67541294") in res.reasons

    def test_refuses_overlapping_subjects_state_sets_decision_d(self) -> None:
        """Decision D: state sets sharing states (e.g. Senate Combo sharing PA) are refused."""
        res_date = "2026-11-15T23:59:00Z"
        markets = [
            _make_binary_market(8101, "Will Democrats win Senate Combo: PA + OH by November 15?", 0.52, category="politics", resolution_date=res_date),
            _make_binary_market(8102, "Will Democrats win Senate Combo: PA + MI by November 15?", 0.48, category="politics", resolution_date=res_date),
            _make_binary_market(8103, "Will Democrats win Senate Combo: NV + AZ by November 15?", 0.44, category="politics", resolution_date=res_date),
        ]
        res = select_sibling_family(markets, now=NOW_NOV_3)
        assert isinstance(res, RoundupRefusal)
        assert ("family", "overlapping_subjects") in res.reasons

    def test_refuses_mixed_venues_one_venue_only(self) -> None:
        markets = [
            _make_binary_market(60087431, "Will it snow in Indianapolis, IN by November 15?", 0.485, source="polymarket"),
            _make_binary_market(60087427, "Will it snow in Buffalo, NY by November 15?", 0.45, source="polymarket"),
            _make_binary_market(60087426, "Will it snow in Boston, MA by November 15?", 0.38, source="kalshi"),
        ]
        res = select_sibling_family(markets, strip_state_suffix=True, now=NOW_NOV_3)
        assert isinstance(res, RoundupRefusal)
        assert ("family", "mixed_venues") in res.reasons

    def test_combined_market_excluded_or_refused_when_not_excluded(self) -> None:
        pool = _live_snow_pool()
        res_conflict = select_sibling_family(
            pool,
            strip_state_suffix=True,
            subject_unit="cities",
            exclude_combined_market=False,
            now=NOW_NOV_3,
        )
        assert isinstance(res_conflict, RoundupRefusal)
        assert ("family", "combined_market_conflict") in res_conflict.reasons


class TestLiveDefinitionsAndDecisionA:
    @pytest.mark.asyncio
    async def test_snow_first_flakes_2026_card_and_two_section_container(self) -> None:
        """Under decision A, snow leads with Nov 15 today (5 of 10 cities shown,
        3 with no number yet: Detroit, Minneapolis, Pittsburgh), excludes combined
        market 60084865 and past-deadline Oct 31 markets 60084867-68, and places
        Nov 30 (17 cities) as Section 2 of the container.
        """
        pool = _live_snow_pool(denver_resolved=True)
        members = await snow_first_flakes_2026(pool, now=NOW_NOV_3)
        assert isinstance(members, RoundupMembers)
        assert members.kicker == "SNOW · NOV 15"
        assert members.title == "Will it snow by November 15?"
        assert members.footer == "Each city is its own market. They don't add up to 100%."
        assert members.count_line == (
            "Showing 5 of 10 cities · No number yet: Detroit, Minneapolis, Pittsburgh"
        )
        assert [
            (r["market_id"], r["label"], r["rendered_percent"]) for r in members.rows
        ] == [
            (60087431, "Indianapolis", 49),
            (60087427, "Buffalo", 45),
            (60087426, "Boston", 38),
            (60087435, "Salt Lake City", 34),
            (60084869, "Kansas City", 26),
        ]

        # Combined market 60084865 and past-deadline Oct 31 markets 60084867-68 are never in members.
        all_ids = [int(m["id"]) for m in members.members]
        assert 60084865 not in all_ids
        assert 60084867 not in all_ids
        assert 60084868 not in all_ids

        # Container has Section 1 (10 Nov 15 cities) and Section 2 (17 Nov 30 cities).
        container = compose_roundup_container(SNOW_FIRST_FLAKES_2026_PRODUCER, members)
        assert container is not None
        assert container["state"] == "published"
        assert container["slug"] == SNOW_FIRST_FLAKES_2026_SLUG
        assert container["container"]["name"] == "Will it snow by November 15?"
        assert container["subtitle"] == "Each city is its own market. They don't add up to 100%."
        assert container["member_count"] == 27
        assert len(container["sections"]) == 2
        assert container["sections"][0]["title"] == "By November 15"
        assert container["sections"][0]["count"] == 10
        assert container["sections"][1]["title"] == "By November 30"
        assert container["sections"][1]["count"] == 17

        # Unnumbered members (Detroit, Minneapolis, Pittsburgh) stay in Section 1 with empty top_outcomes.
        sec1_by_id = {m["id"]: m["card"] for m in container["sections"][0]["members"]}
        for unnum_id in (60087430, 60087433, 60087434):
            assert unnum_id in sec1_by_id
            assert sec1_by_id[unnum_id]["status"] == "open"
            assert sec1_by_id[unnum_id]["top_outcomes"] == []

        # Resolved ungraded Denver (60087429) never prints 100% as an open probability.
        assert sec1_by_id[60087429]["status"] == "resolved"
        assert sec1_by_id[60087429]["top_outcomes"] == []

    @pytest.mark.asyncio
    async def test_snow_leads_with_nov_30_once_nov_15_passes(self) -> None:
        """Decision A: after Nov 15 passes, Nov 30 becomes the nearest open deadline
        with >= 3 numbered members and leads the card automatically.
        """
        pool = _live_snow_pool(denver_resolved=True)
        now_nov_16 = datetime(2026, 11, 16, 14, 0, 0, tzinfo=timezone.utc)
        obs_nov_16 = "2026-11-16T13:00:00Z"
        for m in pool:
            m["updated_at"] = obs_nov_16
            for o in m.get("outcomes") or ():
                o["observed_at"] = obs_nov_16
        members = await snow_first_flakes_2026(pool, now=now_nov_16)
        assert isinstance(members, RoundupMembers)
        assert members.kicker == "SNOW · NOV 30"
        assert members.title == "Will it snow by November 30?"
        assert members.count_line == "Showing 5 of 17 cities · No number yet: Cincinnati"
        assert len(members.sections) == 1
        assert members.sections[0]["title"] == "By November 30"
        assert members.sections[0]["count"] == 17

    def test_snow_refuses_under_single_deadline_default_when_two_deadlines_open(self) -> None:
        pool = _live_snow_pool(denver_resolved=True)
        res = select_sibling_family(
            pool,
            strip_state_suffix=True,
            subject_unit="cities",
            lead_rule="single_deadline",
            now=NOW_NOV_3,
        )
        assert isinstance(res, RoundupRefusal)
        assert ("family", "multiple_open_deadlines") in res.reasons

    @pytest.mark.asyncio
    async def test_gta_vi_album_features_card_and_container(self) -> None:
        """GTA VI: 12 binary artist markets at one deadline (Nov 26), 10 with a number,
        Kodak Black and Don Toliver on top, combined market 61321728 excluded.
        """
        pool = _live_gta_pool()
        members = await gta_vi_album_features(pool, now=NOW_NOV_3)
        assert isinstance(members, RoundupMembers)
        assert members.kicker == "GTA VI · NOV 26"
        assert members.title == "Will they be featured on GTA VI: The Album?"
        assert members.footer == "Each artist is their own market. They don't add up to 100%."
        assert members.count_line == (
            "Showing 5 of 12 artists · No number yet: Nettspend, Osamason"
        )
        assert [
            (r["market_id"], r["label"], r["rendered_percent"]) for r in members.rows
        ] == [
            (61353752, "Kodak Black", 79),
            (61361196, "Don Toliver", 78),
            (61321730, "The Weeknd", 78),
            (61321731, "Bad Bunny", 38),
            (61341730, "Drake", 32),
        ]
        all_ids = [int(m["id"]) for m in members.members]
        assert 61321728 not in all_ids
        assert len(all_ids) == 12

        feed_item = compose_roundup_feed_item(GTA_VI_ALBUM_FEATURES_PRODUCER, members)
        assert feed_item is not None
        assert feed_item["data"]["roundup"]["kicker"] == "GTA VI · NOV 26"
        assert feed_item["data"]["roundup"]["count_line"] == (
            "Showing 5 of 12 artists · No number yet: Nettspend, Osamason"
        )
        assert feed_item["data"]["collection_ref"]["slug"] == GTA_VI_ALBUM_FEATURES_SLUG
        assert feed_item["data"]["collection_ref"]["collection_count"] == 12

    def test_graded_settled_member_renders_only_graded_result(self) -> None:
        """A settled member with a graded winner carries its verdict and never an open probability."""
        markets = [
            _make_binary_market(60087431, "Will it snow in Indianapolis, IN by November 15?", 0.485),
            _make_binary_market(60087427, "Will it snow in Buffalo, NY by November 15?", 0.45),
            _make_binary_market(60087426, "Will it snow in Boston, MA by November 15?", 0.38),
            _make_binary_market(
                60087429,
                "Will it snow in Denver, CO by November 15?",
                1.0,
                status="resolved",
                is_winner=True,
                resolution_source="api_settlement",
            ),
        ]
        res = select_sibling_family(
            markets,
            strip_state_suffix=True,
            subject_unit="cities",
            now=NOW_NOV_3,
        )
        assert isinstance(res, RoundupMembers)
        assert len(res.rows) == 3
        assert all(r["market_id"] != 60087429 for r in res.rows)
        denver_entry = next(m for m in res.members if m["id"] == 60087429)
        assert denver_entry["card"]["status"] == "resolved"
        assert denver_entry["card"]["settled_winner"] == "Yes"
        assert all(
            o["probability"] is None for o in denver_entry["card"]["top_outcomes"]
        )

    @pytest.mark.asyncio
    async def test_registered_in_roundup_producers_and_folds_covered_feed_cards(self) -> None:
        # Passing ``now=NOW_NOV_3.timestamp()`` (or ``now=NOW_NOV_3``) to
        # ``evaluate_roundup_producer`` threads the clock through to
        # ``produce_sibling_family`` -> ``select_sibling_family`` (#12374).
        reset_roundup_cache_for_tests()
        assert SNOW_FIRST_FLAKES_2026_SLUG in ROUNDUP_PRODUCERS
        assert GTA_VI_ALBUM_FEATURES_SLUG in ROUNDUP_PRODUCERS
        assert SNOW_FIRST_FLAKES_2026_DEFINITION["membership"] == MEMBERSHIP_SIBLING_FAMILY
        assert GTA_VI_ALBUM_FEATURES_DEFINITION["membership"] == MEMBERSHIP_SIBLING_FAMILY
        assert (
            SNOW_FIRST_FLAKES_2026_DEFINITION["rule"]["producer"]
            == PRODUCER_KIND_SIBLING_FAMILY
        )

        snow_feed, snow_container = await evaluate_roundup_producer(
            SNOW_FIRST_FLAKES_2026_PRODUCER, _live_snow_pool(), now=NOW_NOV_3.timestamp()
        )
        assert snow_feed is not None
        assert snow_container is not None

        # When the caller passes a clock 8 days after the Nov 3 quotes, the
        # 7-day freshness rule withholds the rows and refuses the card.
        stale_now = datetime(2026, 11, 12, 0, 0, tzinfo=timezone.utc)
        stale_feed, stale_container = await evaluate_roundup_producer(
            SNOW_FIRST_FLAKES_2026_PRODUCER, _live_snow_pool(), now=stale_now
        )
        assert stale_feed is None
        assert stale_container is None

        deck: list[dict[str, Any]] = [
            {
                "type": "futures",
                "score": 90.0 - i,
                "reason": f"Card {i}",
                "headline": f"Card {i}",
                "data": {"id": 900000 + i, "name": f"Card {i}"},
            }
            for i in range(15)
        ]
        # Place Buffalo Nov 15 (60087427) at index 4; it must fold into the round-up.
        deck[4] = {
            "type": "futures",
            "score": 86.0,
            "reason": "Buffalo snow",
            "headline": "Buffalo snow",
            "data": {"id": 60087427, "name": "Will it snow in Buffalo, NY by November 15?"},
        }
        merged = insert_roundup_feed_items(deck, [snow_feed], now=NOW_NOV_3)
        standalone_ids = [
            it["data"]["id"] for it in merged if it.get("type") == "futures"
        ]
        assert 60087427 not in standalone_ids
        roundup_indices = [
            idx
            for idx, it in enumerate(merged)
            if it.get("type") == "bundle"
            and it.get("data", {}).get("id") == "roundup:snow-first-flakes-2026"
        ]
        assert roundup_indices and roundup_indices[0] >= 10

    @pytest.mark.asyncio
    async def test_a_new_subject_joins_the_card_with_no_code_or_definition_change(self) -> None:
        """Ruling 145 §4: a new subject market in the provider group joins the card
        and container automatically without editing the definition or code.
        """
        pool = _live_gta_pool()
        pool.append(
            _make_binary_market(
                61399999,
                "Will Travis Scott be featured on GTA VI: The Album?",
                0.85,
                category="entertainment",
                resolution_date="2026-11-26T00:00:00Z",
            )
        )
        members = await gta_vi_album_features(pool, now=NOW_NOV_3)
        assert isinstance(members, RoundupMembers)
        assert members.rows[0]["label"] == "Travis Scott"
        assert members.rows[0]["rendered_percent"] == 85
        assert members.count_line == (
            "Showing 5 of 13 artists · No number yet: Nettspend, Osamason"
        )
        assert len(members.members) == 13

    @pytest.mark.asyncio
    async def test_db_loader_tolerates_none_and_unrelated_fake_session_rows(self) -> None:
        """Fake test sessions passed by ``roundup_feed_items(None)`` or unrelated
        fixture sessions cleanly refuse instead of raising ``AttributeError``.
        """
        refusal_none = await snow_first_flakes_2026(None, now=NOW_NOV_3)
        assert isinstance(refusal_none, RoundupRefusal)

        class _FakeScalars:
            def all(self) -> list[dict[str, Any]]:
                return [{"team": "BUF", "win_prob": 0.55}]

        class _FakeResult:
            def scalars(self) -> _FakeScalars:
                return _FakeScalars()

        class _FakeSession:
            async def execute(self, _stmt: Any) -> _FakeResult:
                return _FakeResult()

        refusal_fake = await snow_first_flakes_2026(_FakeSession(), now=NOW_NOV_3)
        assert isinstance(refusal_fake, RoundupRefusal)


