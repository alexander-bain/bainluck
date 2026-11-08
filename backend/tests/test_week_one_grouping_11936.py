"""Tests for the Nov 10 week-one grouping type (#11936, Decide 59-A, 60-A, 71-A, #12221 §4).

Covers:
1. "Two rivals, one market" (``sibling_family`` with ``closed_world: true`` and ``max_members: 2``,
   §1.7, Ruling 143) + ``find_sibling_family_candidates`` pair finder seeding Row 4 of #12221.
2. "This week's tournaments" (``week_events``, §1.10, Decide 59-A fallback B) +
   ``find_week_events_candidates`` across all 5 §1.10 sports.
3. Primitives model invariants (``docs/design/grouping-primitives.md``):
   - Set reproducibility from selector (identical members, order, revision, and reasons across runs).
   - Folder loading by kind (Decide 60-A).
   - Relation permission levels (Decide 71-A: ``relations`` + ``level == "member"``).
   - One on/off switch per kind (``SIBLING_FAMILY_ENABLED`` and ``WEEK_EVENTS_ENABLED``).
   - 390 px card words export (``export_roundup_card_words_390px``).
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pytest

from app.utils.roundup_containers import (
    ROUNDUP_PRODUCERS,
    RoundupMembers,
    RoundupRefusal,
    compose_roundup_container,
    compose_roundup_feed_item,
    evaluate_roundup_producer,
    reset_roundup_cache_for_tests,
    roundup_revision,
)
from app.utils.sibling_family import (
    ALCARAZ_SINNER_TWO_MAJORS_2027_DEFINITION,
    ALCARAZ_SINNER_TWO_MAJORS_2027_PRODUCER,
    ALCARAZ_SINNER_TWO_MAJORS_2027_SLUG,
    alcaraz_sinner_two_majors_2027,
    find_sibling_family_candidates,
    load_sibling_family_definitions_from_dir,
    select_sibling_family,
)
from app.utils.week_events import (
    GOLF_THIS_WEEK_DEFINITION,
    GOLF_THIS_WEEK_PRODUCER,
    GOLF_THIS_WEEK_SLUG,
    PRODUCER_KIND_WEEK_EVENTS,
    export_roundup_card_words_390px,
    find_week_events_candidates,
    golf_this_week,
    load_week_events_definitions_from_dir,
    select_week_events,
)

NOW_NOV_6 = datetime(2026, 11, 6, 22, 0, 0, tzinfo=timezone.utc)
OBS = "2026-11-06T21:00:00Z"


def _make_alcaraz_sinner_pair(
    *,
    alcaraz_two_plus: float | None,
    sinner_two_plus: float | None,
) -> list[dict[str, Any]]:
    """Build the live Kalshi Grand Slam wins in 2027 pair (66937562 & 66937563)."""
    return [
        {
            "id": 66937562,
            "name": "Carlos Alcaraz: Grand Slam wins in 2027",
            "status": "open",
            "source": "kalshi",
            "group_id": "kalshi:KXGRANDSLAM-CALC27",
            "category": "tennis",
            "llm_sport_category": "tennis",
            "market_tier": 2,
            "market_type": "other",
            "mutually_exclusive": False,
            "resolution_date": "2027-09-13T00:00:00Z",
            "updated_at": OBS,
            "outcomes": [
                {"id": 669375621, "name": "1+ Grand Slam wins", "probability": 0.775, "observed_at": OBS},
                {"id": 669375622, "name": "2+ Grand Slam wins", "probability": alcaraz_two_plus, "observed_at": OBS},
                {"id": 669375623, "name": "3+ Grand Slam wins", "probability": None, "observed_at": OBS},
                {"id": 669375624, "name": "4 Grand Slam wins", "probability": 0.1555, "observed_at": OBS},
            ],
        },
        {
            "id": 66937563,
            "name": "Jannik Sinner: Grand Slam wins in 2027",
            "status": "open",
            "source": "kalshi",
            "group_id": "kalshi:KXGRANDSLAM-JSIN27",
            "category": "tennis",
            "llm_sport_category": "tennis",
            "market_tier": 2,
            "market_type": "other",
            "mutually_exclusive": False,
            "resolution_date": "2027-09-13T00:00:00Z",
            "updated_at": OBS,
            "outcomes": [
                {"id": 669375631, "name": "1+ Grand Slam wins", "probability": None, "observed_at": OBS},
                {"id": 669375632, "name": "2+ Grand Slam wins", "probability": sinner_two_plus, "observed_at": OBS},
                {"id": 669375633, "name": "3+ Grand Slam wins", "probability": 0.50, "observed_at": OBS},
                {"id": 669375634, "name": "4 Grand Slam wins", "probability": 0.50, "observed_at": OBS},
            ],
        },
    ]


def _make_live_golf_tournaments(*, toto_flat_placeholder: bool = True) -> list[dict[str, Any]]:
    """Build today's 3 golf tournaments overlapping play week Nov 5–8, 2026."""
    abu_dhabi = {
        "key": "abu_dhabi_aldar_championship",
        "slug": "abu-dhabi-aldar-championship",
        "name": "Abu Dhabi Aldar Championship",
        "tour": "dp_world_tour",
        "tour_label": "DP World Tour",
        "start_date": "2026-11-05",
        "end_date": "2026-11-08",
        "schedule_status": "in_progress",
        "champion": None,
        "market_ids": [28862742, 65540797, 65553732, 65553915],
        "market_sources": ["datagolf", "kalshi", "polymarket"],
        "source_count": 3,
        "updated_at": OBS,
        "golfers": [
            {"name": "Rory McIlroy", "probability": 0.19125, "rank": 1, "movement_24h": 0.088, "movement_is_dated": True},
            {"name": "Tommy Fleetwood", "probability": 0.181, "rank": 2, "movement_24h": 0.097, "movement_is_dated": True},
            {"name": "Shane Lowry", "probability": 0.145, "rank": 3, "movement_24h": 0.086, "movement_is_dated": True},
        ],
        "_all_golfers": [
            {"name": "Rory McIlroy", "probability": 0.19125},
            {"name": "Tommy Fleetwood", "probability": 0.181},
            {"name": "Shane Lowry", "probability": 0.145},
            {"name": "Tyrrell Hatton", "probability": 0.11},
            {"name": "Field Remainder", "probability": 0.35},
        ],
    }
    wwt = {
        "key": "world_wide_technology_championship",
        "slug": "world-wide-technology-championship",
        "name": "World Wide Technology Championship",
        "tour": "pga_tour",
        "tour_label": "PGA Tour",
        "start_date": "2026-11-05",
        "end_date": "2026-11-08",
        "schedule_status": "in_progress",
        "champion": None,
        "market_ids": [28862743, 65540804, 65553733, 65692616],
        "market_sources": ["datagolf", "kalshi", "polymarket"],
        "source_count": 3,
        "updated_at": OBS,
        "golfers": [
            {"name": "Ben James", "probability": 0.313, "rank": 1, "movement_24h": 0.304, "movement_is_dated": True},
            {"name": "Ben Griffin", "probability": 0.156, "rank": 2, "movement_24h": 0.072, "movement_is_dated": True},
            {"name": "Matti Schmid", "probability": 0.123, "rank": 3, "movement_24h": 0.089, "movement_is_dated": True},
        ],
        "_all_golfers": [
            {"name": "Ben James", "probability": 0.313},
            {"name": "Ben Griffin", "probability": 0.156},
            {"name": "Matti Schmid", "probability": 0.123},
            {"name": "Nick Dunlap", "probability": 0.095},
            {"name": "Field Remainder", "probability": 0.29},
        ],
    }
    if toto_flat_placeholder:
        toto_golfers = [
            {"name": "Miyu Yamashita", "probability": 0.50, "rank": 1},
            {"name": "Nasa Hataoka", "probability": 0.50, "rank": 2},
            {"name": "Hana Wakimoto", "probability": 0.50, "rank": 3},
            {"name": "Chisato Iwai", "probability": 0.085, "rank": 4},
        ]
    else:
        toto_golfers = [
            {"name": "Miyu Yamashita", "probability": 0.287, "rank": 1},
            {"name": "Nasa Hataoka", "probability": 0.242, "rank": 2},
            {"name": "Hana Wakimoto", "probability": 0.193, "rank": 3},
            {"name": "Chisato Iwai", "probability": 0.085, "rank": 4},
        ]
    toto = {
        "key": "toto_japan_classic_womens",
        "slug": "toto-japan-classic-womens",
        "name": "TOTO Japan Classic",
        "tour": "lpga",
        "tour_label": "LPGA Tour",
        "start_date": "2026-11-05",
        "end_date": "2026-11-08",
        "schedule_status": "in_progress",
        "champion": None,
        "market_ids": [66654905],
        "market_sources": ["kalshi"],
        "source_count": 1,
        "updated_at": OBS,
        "golfers": toto_golfers,
        "_all_golfers": [
            *toto_golfers,
            {"name": "Field Remainder", "probability": 0.20},
        ],
    }
    return [abu_dhabi, wwt, toto]


class TestTwoRivalsOneMarketClosedWorld:
    """§1.7 'Two rivals, one market' (sibling_family with closed_world: true, Ruling 143)."""

    @pytest.mark.asyncio
    async def test_cert_430_refuses_while_either_leg_has_no_reading(self) -> None:
        """CERT-430: alcaraz-sinner-two-majors-2027 is held when either or both legs have None."""
        # Today's live state: both 2+ Grand Slam wins outcomes are None.
        both_unpriced = _make_alcaraz_sinner_pair(
            alcaraz_two_plus=None, sinner_two_plus=None
        )
        res_both = await alcaraz_sinner_two_majors_2027(both_unpriced, now=NOW_NOV_6)
        assert isinstance(res_both, RoundupRefusal)
        reasons_both = dict(res_both.reasons)
        assert reasons_both.get("family") == "unpriced_legs"
        assert reasons_both.get("unpriced_legs") == (
            "Carlos Alcaraz",
            "Jannik Sinner",
        )

        # One leg priced, one leg None: still refused, naming only the unpriced leg.
        one_unpriced = _make_alcaraz_sinner_pair(
            alcaraz_two_plus=0.42, sinner_two_plus=None
        )
        res_one = await alcaraz_sinner_two_majors_2027(one_unpriced, now=NOW_NOV_6)
        assert isinstance(res_one, RoundupRefusal)
        reasons_one = dict(res_one.reasons)
        assert reasons_one.get("family") == "unpriced_legs"
        assert reasons_one.get("unpriced_legs") == ("Jannik Sinner",)

    @pytest.mark.asyncio
    async def test_serves_two_row_head_to_head_card_when_both_legs_priced(self) -> None:
        """When both 2+ legs carry a reading, serves a 2-row HEAD TO HEAD card with no count line and no normalization."""
        priced_pair = _make_alcaraz_sinner_pair(
            alcaraz_two_plus=0.42, sinner_two_plus=0.38
        )
        members = await alcaraz_sinner_two_majors_2027(priced_pair, now=NOW_NOV_6)
        assert isinstance(members, RoundupMembers)
        assert members.kicker == "HEAD TO HEAD"
        assert members.title == "Who wins 2+ Grand Slams in 2027?"
        assert members.footer == "Each player is their own market; both can win 2+."
        assert members.count_line is None
        assert [
            (r["market_id"], r["label"], r["rendered_percent"]) for r in members.rows
        ] == [
            (66937562, "Carlos Alcaraz", 42),
            (66937563, "Jannik Sinner", 38),
        ]
        assert len(members.sections) == 1
        assert members.sections[0]["title"] == "2027 Grand Slams"
        assert members.sections[0]["count"] == 2

        words = export_roundup_card_words_390px(
            members, ALCARAZ_SINNER_TWO_MAJORS_2027_DEFINITION
        )
        assert words["kicker"] == "HEAD TO HEAD"
        assert words["tag"] == "TENNIS"
        assert words["rows"] == [
            {"label": "Carlos Alcaraz", "value": "42%", "market_id": 66937562},
            {"label": "Jannik Sinner", "value": "38%", "market_id": 66937563},
        ]

    @pytest.mark.asyncio
    async def test_ruling_143_refuses_when_third_member_exists(self) -> None:
        """Ruling 143: if a 3rd sibling market exists under the template, closed_world=True refuses."""
        three_players = _make_alcaraz_sinner_pair(
            alcaraz_two_plus=0.42, sinner_two_plus=0.38
        )
        three_players.append(
            {
                "id": 66937564,
                "name": "Novak Djokovic: Grand Slam wins in 2027",
                "status": "open",
                "source": "kalshi",
                "group_id": "kalshi:KXGRANDSLAM-NDJO27",
                "category": "tennis",
                "resolution_date": "2027-09-13T00:00:00Z",
                "outcomes": [
                    {"id": 669375642, "name": "2+ Grand Slam wins", "probability": 0.12, "observed_at": OBS},
                ],
            }
        )
        res = await alcaraz_sinner_two_majors_2027(three_players, now=NOW_NOV_6)
        assert isinstance(res, RoundupRefusal)
        assert ("family", "closed_world_exceeded") in res.reasons

    def test_pair_finder_lists_would_be_cards_with_refusal_reasons(self) -> None:
        """Decide 59-A & #12221 §4: pair finder lists every candidate pair with refusal reasons."""
        pool = [
            *_make_alcaraz_sinner_pair(alcaraz_two_plus=None, sinner_two_plus=None),
            # A 3-member family in the same pool must be refused under closed_world=True
            {
                "id": 9101,
                "name": "Will Boston, MA get snow in December 2026?",
                "status": "open",
                "source": "kalshi",
                "category": "weather",
                "resolution_date": "2026-12-31T23:59:00Z",
                "outcomes": [{"id": 91011, "name": "Yes", "probability": 0.65}],
            },
            {
                "id": 9102,
                "name": "Will Chicago, IL get snow in December 2026?",
                "status": "open",
                "source": "kalshi",
                "category": "weather",
                "resolution_date": "2026-12-31T23:59:00Z",
                "outcomes": [{"id": 91021, "name": "Yes", "probability": 0.72}],
            },
            {
                "id": 9103,
                "name": "Will Denver, CO get snow in December 2026?",
                "status": "open",
                "source": "kalshi",
                "category": "weather",
                "resolution_date": "2026-12-31T23:59:00Z",
                "outcomes": [{"id": 91031, "name": "Yes", "probability": 0.88}],
            },
        ]
        candidates = find_sibling_family_candidates(
            pool, closed_world=True, now=NOW_NOV_6
        )
        by_template = {c["template_key"]: c for c in candidates}
        assert "* grand slam wins" in by_template
        slam_cand = by_template["* grand slam wins"]
        assert slam_cand["verdict"] == "refuse"
        assert slam_cand["refusal_reasons"] == ["unpriced_legs"]
        assert slam_cand["unpriced_legs"] == ["Carlos Alcaraz", "Jannik Sinner"]
        assert slam_cand["relations"] == ["same_measure", "same_window", "sibling"]
        assert slam_cand["level"] == "member"

        snow_cand = by_template["will * get snow"]
        assert snow_cand["verdict"] == "refuse"
        assert snow_cand["refusal_reasons"] == ["closed_world_exceeded"]


class TestWeekEventsThisWeeksTournaments:
    """§1.10 'This week's tournaments' (week_events, Decide 59-A fallback B)."""

    @pytest.mark.asyncio
    async def test_golf_this_week_serves_coherent_tournaments_and_excludes_placeholder(self) -> None:
        """When TOTO Japan Classic has a flat 3x50% placeholder field, golf-this-week excludes it and serves the 2 coherent tournaments."""
        tournaments = _make_live_golf_tournaments(toto_flat_placeholder=True)
        members = await golf_this_week(tournaments, now=NOW_NOV_6)
        assert isinstance(members, RoundupMembers)
        assert members.kicker == "GOLF · THIS WEEK"
        assert members.title == "Two tournaments"
        assert members.footer == "Each row is the leader in its own tournament."
        assert members.count_line is None
        assert [
            (r["label"], r["rendered_percent"]) for r in members.rows
        ] == [
            ("World Wide Technology Championship \u00b7 Nov 5\u20138 \u00b7 Ben James", 31),
            ("Abu Dhabi Aldar Championship \u00b7 Nov 5\u20138 \u00b7 Rory McIlroy", 19),
        ]

        # When TOTO Japan Classic has a coherent field, all 3 tournaments serve on the card.
        coherent_three = _make_live_golf_tournaments(toto_flat_placeholder=False)
        members_three = await golf_this_week(coherent_three, now=NOW_NOV_6)
        assert isinstance(members_three, RoundupMembers)
        assert members_three.title == "Three tournaments"
        assert [
            (r["label"], r["rendered_percent"]) for r in members_three.rows
        ] == [
            ("World Wide Technology Championship \u00b7 Nov 5\u20138 \u00b7 Ben James", 31),
            ("TOTO Japan Classic \u00b7 Nov 5\u20138 \u00b7 Miyu Yamashita", 29),
            ("Abu Dhabi Aldar Championship \u00b7 Nov 5\u20138 \u00b7 Rory McIlroy", 19),
        ]

        feed_item = compose_roundup_feed_item(GOLF_THIS_WEEK_PRODUCER, members_three)
        container = compose_roundup_container(GOLF_THIS_WEEK_PRODUCER, members_three)
        assert feed_item is not None
        assert container is not None
        assert feed_item["data"]["roundup"]["kicker"] == "GOLF · THIS WEEK"
        assert container["slug"] == GOLF_THIS_WEEK_SLUG
        assert container["member_count"] == 3

    def test_week_events_finder_across_all_five_sports(self) -> None:
        """Finder evaluates golf, tennis, ufc, motorsport, and esports with exact refusal reasons."""
        pools_by_sport = {
            "golf": _make_live_golf_tournaments(toto_flat_placeholder=True),
            "tennis": [
                {
                    "name": "WTA Chennai Open",
                    "sport": "tennis",
                    "start_date": None,
                    "end_date": None,
                    "commence_time": "2026-11-08T10:00:00Z",
                    "golfers": [{"name": "Linda Fruhvirtova", "probability": 0.24}],
                },
                {
                    "name": "WTA Hong Kong Open",
                    "sport": "tennis",
                    "start_date": None,
                    "end_date": None,
                    "commence_time": "2026-11-08T10:00:00Z",
                    "golfers": [{"name": "Diana Shnaider", "probability": 0.28}],
                },
            ],
            "ufc": [
                {
                    "key": "ufc_fight_night_nov_7",
                    "name": "UFC Fight Night: Bonfim vs. Brown",
                    "sport": "ufc",
                    "start_date": "2026-11-07",
                    "end_date": "2026-11-07",
                    "golfers": [{"name": "Gabriel Bonfim", "probability": 0.64}],
                },
                {
                    "key": "ufc_fight_night_nov_7",
                    "name": "UFC Fight Night: Bonfim vs. Brown",
                    "sport": "ufc",
                    "start_date": "2026-11-07",
                    "end_date": "2026-11-07",
                    "golfers": [{"name": "Gabriel Bonfim", "probability": 0.64}],
                },
            ],
            "motorsport": [
                {
                    "name": "MotoGP Grand Prix of Malaysia",
                    "sport": "motorsport",
                    "start_date": "2026-11-06",
                    "end_date": "2026-11-08",
                    "golfers": [{"name": "Jorge Martin", "probability": 0.38}],
                }
            ],
            "esports": [
                {
                    "name": "League of Legends Worlds 2026",
                    "sport": "esports",
                    "start_date": None,
                    "end_date": None,
                    "golfers": [{"name": "T1", "probability": 0.52}],
                }
            ],
        }
        report = find_week_events_candidates(pools_by_sport, now=NOW_NOV_6)
        by_slug = {r["slug"]: r for r in report}

        assert by_slug["golf-this-week"]["verdict"] == "serve"
        assert by_slug["golf-this-week"]["served_row_count"] == 2
        assert by_slug["golf-this-week"]["card_words_390px"] is not None

        assert by_slug["tennis-this-week"]["verdict"] == "refuse"
        assert by_slug["tennis-this-week"]["tournament_refusals"] == [
            {"tournament": "WTA Chennai Open", "reason": "missing_published_dates"},
            {"tournament": "WTA Hong Kong Open", "reason": "missing_published_dates"},
        ]

        assert by_slug["ufc-this-weekend"]["verdict"] == "refuse"
        assert by_slug["ufc-this-weekend"]["tournament_refusals"] == [
            {"tournament": "UFC Fight Night: Bonfim vs. Brown", "reason": "duplicate_event"},
        ]

        assert by_slug["motorsport-this-weekend"]["verdict"] == "refuse"
        assert by_slug["motorsport-this-weekend"]["refusal_reasons"] == ["too_few_tournaments"]

        assert by_slug["esports-this-week"]["verdict"] == "refuse"
        assert by_slug["esports-this-week"]["tournament_refusals"] == [
            {"tournament": "League of Legends Worlds 2026", "reason": "missing_published_dates"},
        ]


class TestPrimitivesInvariantsAndFolderLoading:
    """Invariants from docs/design/grouping-primitives.md, Decide 60-A, and Decide 71-A."""

    def test_reproducibility_from_selector(self) -> None:
        """Given the same atoms in any input order and the same definition, two runs produce identical members, order, revision, and reasons."""
        golf_a = _make_live_golf_tournaments(toto_flat_placeholder=False)
        golf_b = list(reversed(golf_a))
        res_a = select_week_events(golf_a, now=NOW_NOV_6)
        res_b = select_week_events(golf_b, now=NOW_NOV_6)
        assert isinstance(res_a, RoundupMembers)
        assert isinstance(res_b, RoundupMembers)
        assert res_a.rows == res_b.rows
        assert [m["id"] for m in res_a.members] == [m["id"] for m in res_b.members]
        assert roundup_revision(res_a.revision_ids) == roundup_revision(res_b.revision_ids)

        pair_a = _make_alcaraz_sinner_pair(alcaraz_two_plus=0.42, sinner_two_plus=0.38)
        pair_b = list(reversed(pair_a))
        s_a = select_sibling_family(
            pair_a,
            expected_source="kalshi",
            template="* grand slam wins in 2027",
            outcome_name="2+ Grand Slam wins",
            closed_world=True,
            now=NOW_NOV_6,
        )
        s_b = select_sibling_family(
            pair_b,
            expected_source="kalshi",
            template="* grand slam wins in 2027",
            outcome_name="2+ Grand Slam wins",
            closed_world=True,
            now=NOW_NOV_6,
        )
        assert isinstance(s_a, RoundupMembers)
        assert isinstance(s_b, RoundupMembers)
        assert s_a.rows == s_b.rows
        assert roundup_revision(s_a.revision_ids) == roundup_revision(s_b.revision_ids)

    def test_folder_loading_by_kind_and_relation_levels(self, tmp_path: Path) -> None:
        """Decide 60-A & 71-A: definitions in a folder load by kind and normalize relations + level."""
        assert ALCARAZ_SINNER_TWO_MAJORS_2027_SLUG in ROUNDUP_PRODUCERS
        assert GOLF_THIS_WEEK_SLUG in ROUNDUP_PRODUCERS
        assert ALCARAZ_SINNER_TWO_MAJORS_2027_DEFINITION["relations"] == [
            "same_measure",
            "same_window",
            "sibling",
        ]
        assert ALCARAZ_SINNER_TWO_MAJORS_2027_DEFINITION["level"] == "member"
        assert GOLF_THIS_WEEK_DEFINITION["relations"] == [
            "same_measure",
            "same_window",
        ]
        assert GOLF_THIS_WEEK_DEFINITION["level"] == "member"

        # Dropping a new JSON file in a folder loads it by kind with no code change.
        new_file = tmp_path / "tennis-this-week.json"
        new_file.write_text(
            json.dumps(
                {
                    "slug": "tennis-this-week",
                    "membership": "event-derived",
                    "kind": "roundup",
                    "relations": ["same_measure", "same_window"],
                    "level": "member",
                    "kicker": "TENNIS · THIS WEEK",
                    "name": "This week's tournaments",
                    "category": "tennis",
                    "tag": "TENNIS",
                    "section_title": "This week's tournaments",
                    "footer": "Each row is the leader in its own tournament.",
                    "rule": {
                        "producer": PRODUCER_KIND_WEEK_EVENTS,
                        "sport": "tennis",
                    },
                }
            ),
            encoding="utf-8",
        )
        loaded_we = load_week_events_definitions_from_dir(tmp_path)
        assert len(loaded_we) == 1
        assert loaded_we[0]["slug"] == "tennis-this-week"
        assert loaded_we[0]["relations"] == ["same_measure", "same_window"]
        assert loaded_we[0]["level"] == "member"
        assert load_sibling_family_definitions_from_dir(tmp_path) == []

    @pytest.mark.asyncio
    async def test_one_on_off_switch_per_kind(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """#12221 §4 item 5: one env switch per kind disables the producer cleanly."""
        reset_roundup_cache_for_tests()
        tournaments = _make_live_golf_tournaments(toto_flat_placeholder=False)
        monkeypatch.setenv("WEEK_EVENTS_ENABLED", "false")
        fi, cp = await evaluate_roundup_producer(GOLF_THIS_WEEK_PRODUCER, tournaments)
        assert fi is None and cp is None

        monkeypatch.setenv("WEEK_EVENTS_ENABLED", "true")
        fi_on, cp_on = await evaluate_roundup_producer(
            GOLF_THIS_WEEK_PRODUCER, tournaments
        )
        assert fi_on is not None and cp_on is not None

    def test_main_import_registers_golf_this_week_and_alcaraz_sinner_in_roundup_producers(
        self,
    ) -> None:
        """Importing app.main and running _register_builtin_producers() registers both producers."""
        import app.main  # noqa: F401
        from app.utils.roundup_containers import _register_builtin_producers

        ROUNDUP_PRODUCERS.pop(GOLF_THIS_WEEK_SLUG, None)
        ROUNDUP_PRODUCERS.pop(ALCARAZ_SINNER_TWO_MAJORS_2027_SLUG, None)
        _register_builtin_producers()
        assert GOLF_THIS_WEEK_SLUG in ROUNDUP_PRODUCERS
        assert ALCARAZ_SINNER_TWO_MAJORS_2027_SLUG in ROUNDUP_PRODUCERS

    @pytest.mark.asyncio
    async def test_db_loader_failure_and_unsupported_sport_do_not_masquerade_as_empty_pool(
        self,
        monkeypatch: pytest.MonkeyPatch,
        caplog: pytest.LogCaptureFixture,
    ) -> None:
        """A get_golf_base failure returns source_unavailable (never empty_pool), and non-golf sports return unsupported_sport."""
        from unittest.mock import MagicMock
        from sqlalchemy.ext.asyncio import AsyncSession
        import app.utils.golf_base as golf_base_mod
        from app.utils.week_events import produce_week_events

        fake_session = MagicMock(spec=AsyncSession)

        async def _boom(db: Any, now: Any) -> Any:
            raise RuntimeError("golf_base connection timeout")

        monkeypatch.setattr(golf_base_mod, "get_golf_base", _boom)

        res_err = await produce_week_events(
            fake_session,
            GOLF_THIS_WEEK_DEFINITION,
            now=NOW_NOV_6,
        )
        assert isinstance(res_err, RoundupRefusal)
        assert ("sport", "source_unavailable") in res_err.reasons
        assert ("sport", "empty_pool") not in res_err.reasons
        assert "failed to load tournaments from shared base" in caplog.text

        tennis_def = {
            **GOLF_THIS_WEEK_DEFINITION,
            "slug": "tennis-this-week",
            "category": "tennis",
            "rule": {"producer": PRODUCER_KIND_WEEK_EVENTS, "sport": "tennis"},
        }
        res_unsupported = await produce_week_events(
            fake_session,
            tennis_def,
            now=NOW_NOV_6,
        )
        assert isinstance(res_unsupported, RoundupRefusal)
        assert ("sport", "unsupported_sport") in res_unsupported.reasons

        res_no_db = await produce_week_events(
            None,
            GOLF_THIS_WEEK_DEFINITION,
            now=NOW_NOV_6,
        )
        assert isinstance(res_no_db, RoundupRefusal)
        assert ("sport", "missing_db_session") in res_no_db.reasons

    @pytest.mark.asyncio
    async def test_spent_budget_logs_warning_and_per_producer_timeout_preserves_other_cards(
        self,
        monkeypatch: pytest.MonkeyPatch,
        caplog: pytest.LogCaptureFixture,
    ) -> None:
        """#11936 / #12148 card half:
        1. A spent budget (budget_seconds <= 0) logs a warning instead of skipping silently.
        2. A slow/timed-out middle producer rolls back db and does not discard earlier
           or later round-up cards (e.g. closest-games-tonight + golf-this-week).
        3. Cacheable refusals are cached for 60s under CONTAINERS_READ_CACHE_ENABLED=true,
           while transient source_unavailable refusals are never cached.
        """
        import asyncio
        import logging
        from app.utils.roundup_containers import (
            RoundupProducer,
            add_roundup_feed_items,
        )

        reset_roundup_cache_for_tests()
        deck = [
            {
                "type": "futures",
                "score": float(100 - idx),
                "_rank_score": float(100 - idx),
                "reason": f"Story {idx}",
                "headline": f"Story {idx}",
                "data": {"id": 80000 + idx, "name": f"Market {idx}"},
            }
            for idx in range(15)
        ]

        with caplog.at_level(logging.WARNING):
            unchanged = await add_roundup_feed_items(
                object(),
                deck,
                budget_seconds=0.0,
            )
        assert unchanged is deck
        assert "Discover round-up stage skipped: feed budget exhausted" in caplog.text

        # Now verify per-producer timeout isolation: producer 1 succeeds, producer 2 hangs
        # past ROUNDUP_PRODUCER_TIMEOUT_SECONDS, producer 3 (golf-this-week) succeeds.
        rollback_calls = 0

        class _RollbackSession:
            async def rollback(self) -> None:
                nonlocal rollback_calls
                rollback_calls += 1

        tournaments = _make_live_golf_tournaments(toto_flat_placeholder=False)

        def _fast_first(_db: Any) -> Any:
            return RoundupMembers(
                members=[
                    {
                        "id": 9101,
                        "name": "Game 1",
                        "top_outcomes": [{"name": "Celtics", "probability": 0.52}],
                    }
                ],
                rows=[
                    {
                        "event_id": 9101,
                        "label": "Knicks at Celtics: Celtics",
                        "probability": 0.52,
                        "observed_at": "2026-11-06T22:00:00Z",
                    }
                ],
                footer="Combined probability · the 4 closest of 12 games tonight",
            )

        async def _hanging_middle(_db: Any) -> Any:
            await asyncio.sleep(0.25)
            return None

        def _golf_third(_db: Any) -> Any:
            return select_week_events(tournaments, now=NOW_NOV_6)

        p1 = RoundupProducer(
            slug="roundup-closest-games-tonight",
            name="The closest games tonight",
            kind="roundup",
            category="sports",
            section_title="The 4 closest games",
            footer="Combined probability · the 4 closest of 12 games tonight",
            produce=_fast_first,
        )
        p2 = RoundupProducer(
            slug="roundup-cfp-picture",
            name="The College Football Playoff picture",
            kind="roundup",
            category="ncaaf",
            section_title="On the bubble",
            footer="Playoff qualifiers",
            produce=_hanging_middle,
        )
        p3 = RoundupProducer(
            slug=GOLF_THIS_WEEK_SLUG,
            name="This week's tournaments",
            kind="roundup",
            category="golf",
            section_title="This week's tournaments",
            footer="Each row is the leader in its own tournament.",
            produce=_golf_third,
            kicker="GOLF · THIS WEEK",
        )
        monkeypatch.setattr(
            "app.utils.roundup_containers.ROUNDUP_PRODUCERS",
            {p1.slug: p1, p2.slug: p2, p3.slug: p3},
        )
        monkeypatch.setattr(
            "app.utils.roundup_containers.ROUNDUP_PRODUCER_TIMEOUT_SECONDS",
            0.05,
        )
        monkeypatch.setenv("CONTAINERS_READ_CACHE_ENABLED", "false")

        caplog.clear()
        with caplog.at_level(logging.WARNING):
            placed = await add_roundup_feed_items(
                _RollbackSession(),
                deck,
                budget_seconds=1.5,
                now=NOW_NOV_6,
            )
        assert rollback_calls == 1
        assert "Discover round-up read failed for roundup-cfp-picture" in caplog.text
        roundup_slugs = [
            it["data"]["collection_ref"]["slug"]
            for it in placed
            if it.get("type") == "bundle" and it.get("data", {}).get("kind") == "roundup"
        ]
        assert roundup_slugs == [
            "roundup-closest-games-tonight",
            GOLF_THIS_WEEK_SLUG,
        ]

        # Verify cacheable vs transient refusal caching under CONTAINERS_READ_CACHE_ENABLED=true
        monkeypatch.setenv("CONTAINERS_READ_CACHE_ENABLED", "true")
        reset_roundup_cache_for_tests()
        data_refusal_calls = 0

        def _data_refusal(_db: Any) -> Any:
            nonlocal data_refusal_calls
            data_refusal_calls += 1
            return RoundupRefusal((("sport", "too_few_tournaments"),))

        refusing_producer = RoundupProducer(
            slug="roundup-refused-data",
            name="Refused data",
            kind="roundup",
            category="golf",
            section_title="Section",
            footer="Footer",
            produce=_data_refusal,
        )
        db_marker = object()
        await evaluate_roundup_producer(refusing_producer, db_marker, now=1000.0)
        await evaluate_roundup_producer(refusing_producer, db_marker, now=1010.0)
        assert data_refusal_calls == 1

        transient_calls = 0

        def _transient_refusal(_db: Any) -> Any:
            nonlocal transient_calls
            transient_calls += 1
            return RoundupRefusal((("sport", "source_unavailable"),))

        transient_producer = RoundupProducer(
            slug="roundup-refused-transient",
            name="Refused transient",
            kind="roundup",
            category="golf",
            section_title="Section",
            footer="Footer",
            produce=_transient_refusal,
        )
        await evaluate_roundup_producer(transient_producer, db_marker, now=1000.0)
        await evaluate_roundup_producer(transient_producer, db_marker, now=1010.0)
        assert transient_calls == 2

        # Verify a timed-out producer is cached as a refusal for the 60s TTL so
        # subsequent builds skip it without paying the timeout again, and that
        # stage_budget_seconds allows the prewarm call site to run past 2.5s.
        reset_roundup_cache_for_tests()
        hanging_calls = 0

        async def _counted_hanging(_db: Any) -> Any:
            nonlocal hanging_calls
            hanging_calls += 1
            await asyncio.sleep(0.25)
            return None

        p2_cached = RoundupProducer(
            slug="roundup-cfp-picture",
            name="The College Football Playoff picture",
            kind="roundup",
            category="ncaaf",
            section_title="On the bubble",
            footer="Playoff qualifiers",
            produce=_counted_hanging,
        )
        monkeypatch.setattr(
            "app.utils.roundup_containers.ROUNDUP_PRODUCERS",
            {p1.slug: p1, p2_cached.slug: p2_cached, p3.slug: p3},
        )
        shared_session = _RollbackSession()
        first_placed = await add_roundup_feed_items(
            shared_session,
            deck,
            budget_seconds=10.0,
            stage_budget_seconds=10.0,
            now=NOW_NOV_6,
        )
        second_placed = await add_roundup_feed_items(
            shared_session,
            deck,
            budget_seconds=2.5,
            now=NOW_NOV_6,
        )
        assert hanging_calls == 1
        for result_deck in (first_placed, second_placed):
            slugs = [
                it["data"]["collection_ref"]["slug"]
                for it in result_deck
                if it.get("type") == "bundle"
                and it.get("data", {}).get("kind") == "roundup"
            ]
            assert slugs == ["roundup-closest-games-tonight", GOLF_THIS_WEEK_SLUG]

        # Verify stage_budget_seconds caps default reader builds while allowing
        # the prewarm call site to pass a larger stage budget.
        reset_roundup_cache_for_tests()
        monkeypatch.setattr(
            "app.utils.roundup_containers.ROUNDUP_READ_BUDGET_SECONDS",
            0.03,
        )
        monkeypatch.setattr(
            "app.utils.roundup_containers.ROUNDUP_PRODUCER_TIMEOUT_SECONDS",
            0.2,
        )

        async def _slow_first(_db: Any) -> Any:
            await asyncio.sleep(0.05)
            return _fast_first(_db)

        p1_slow = RoundupProducer(
            slug="roundup-closest-games-tonight",
            name="The closest games tonight",
            kind="roundup",
            category="sports",
            section_title="The 4 closest games",
            footer="Combined probability · the 4 closest of 12 games tonight",
            produce=_slow_first,
        )
        monkeypatch.setattr(
            "app.utils.roundup_containers.ROUNDUP_PRODUCERS",
            {p1_slow.slug: p1_slow, p3.slug: p3},
        )
        reader_deck = await add_roundup_feed_items(
            object(),
            deck,
            budget_seconds=5.0,
            now=NOW_NOV_6,
        )
        reader_slugs = [
            it["data"]["collection_ref"]["slug"]
            for it in reader_deck
            if it.get("type") == "bundle" and it.get("data", {}).get("kind") == "roundup"
        ]
        assert reader_slugs == []

        reset_roundup_cache_for_tests()
        prewarm_deck = await add_roundup_feed_items(
            object(),
            deck,
            budget_seconds=5.0,
            stage_budget_seconds=1.0,
            now=NOW_NOV_6,
        )
        prewarm_slugs = [
            it["data"]["collection_ref"]["slug"]
            for it in prewarm_deck
            if it.get("type") == "bundle" and it.get("data", {}).get("kind") == "roundup"
        ]
        assert prewarm_slugs == ["roundup-closest-games-tonight", GOLF_THIS_WEEK_SLUG]


