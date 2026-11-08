"""Tests for #12371: One definition path (Decide 60-A, 71-A, 73-A).

Exit criteria covered:
1. Adding one new ``.json`` definition file to ``backend/data/containers/`` (via
   ``register_roundup_definitions_from_dir``), with no code change, serves both
   its Discover card (``roundup_feed_items``) and its container (``serve_roundup``).
2. Every file in ``backend/data/containers/`` validates at load time: declares
   non-empty ``relations`` from ``CLOSED_GROUPING_RELATIONS`` and ``level`` from
   ``CLOSED_PERMISSION_LEVELS`` (71-A); a definition with a missing/unknown
   relation, an unknown level, or ``level == "equivalent"`` without ``"twin"``
   is refused with a clear ``ValueError``.
3. ``validate_roundup_definition`` refuses a definition whose only member source
   is a hand list of market IDs without ``id_list_reason`` (73-A), while allowing
   occasion IDs (``field``, ``register``, ``anchor``) as "an id, never a member".
4. ``rt-scores-this-week.json`` has no ``candidates`` list, selects by title
   pattern (``title_ilike``) within a release window (``release_window_days``),
   excludes out-of-window December releases, and automatically picks up a newly
   added Rotten Tomatoes film market (including multi-word titles) with no code
   or definition change.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pytest

from app.utils.roundup_containers import (
    CLOSED_GROUPING_RELATIONS,
    CLOSED_PERMISSION_LEVELS,
    CONTAINERS_DATA_DIR,
    RoundupMembers,
    build_roundup_producer_from_definition,
    load_roundup_definition,
    load_roundup_definitions_from_dir,
    register_roundup_definitions_from_dir,
    reset_roundup_cache_for_tests,
    roundup_feed_items,
    serve_roundup,
    validate_roundup_definition,
)
from app.utils.sibling_family import (
    RT_SCORES_THIS_WEEK_DEFINITION,
    rt_scores_this_week,
)

NOW_NOV_8 = datetime(2026, 11, 8, 18, 0, 0, tzinfo=timezone.utc)
OBS_NOV_8 = "2026-11-08T17:30:00Z"


class TestOneDefinitionPathFolderRegistration:
    """Exit #1 (60-A): dropping one new .json definition file in a folder serves both its card and its container with no code change."""

    @pytest.mark.asyncio
    async def test_adding_one_json_file_serves_discover_card_and_container_with_no_code_change(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        reset_roundup_cache_for_tests()
        slug = "box-office-holiday-preview-test"
        defn = {
            "slug": slug,
            "membership": "sibling_family",
            "kind": "roundup",
            "relations": ["same_measure", "same_window", "sibling"],
            "level": "member",
            "kicker": "BOX OFFICE · NOV 25",
            "name": "Will it top $50M opening weekend?",
            "category": "entertainment",
            "tag": "MOVIES",
            "section_title": "Holiday releases",
            "subtitle": "Each film is its own market. They don't add up to 100%.",
            "footer": "Each film is its own market. They don't add up to 100%.",
            "rule": {
                "producer": "sibling_family",
                "source": "kalshi",
                "title_ilike": "%top $50M opening weekend%",
                "template": "will * top $50m opening weekend",
                "subject_unit": "films",
                "lead_rule": "single_deadline",
                "min_numbered_members": 3,
                "max_card_rows": 5,
            },
        }
        (tmp_path / f"{slug}.json").write_text(json.dumps(defn), encoding="utf-8")

        isolated_registry: dict[str, Any] = {}
        monkeypatch.setattr(
            "app.utils.roundup_containers.ROUNDUP_PRODUCERS",
            isolated_registry,
        )

        registered = register_roundup_definitions_from_dir(tmp_path)
        assert slug in registered
        assert slug in isolated_registry
        producer = isolated_registry[slug]
        assert producer.relations == ("same_measure", "same_window", "sibling")
        assert producer.level == "member"

        pool = [
            {
                "id": 910001,
                "name": "Will Wicked: For Good top $50M opening weekend?",
                "status": "open",
                "source": "kalshi",
                "category": "entertainment",
                "resolution_date": "2026-11-25T16:00:00Z",
                "prices_updated_at": OBS_NOV_8,
                "outcomes": [
                    {"id": 9100011, "name": "Yes", "probability": 0.88, "observed_at": OBS_NOV_8},
                    {"id": 9100012, "name": "No", "probability": 0.12, "observed_at": OBS_NOV_8},
                ],
            },
            {
                "id": 910002,
                "name": "Will Zootopia 2 top $50M opening weekend?",
                "status": "open",
                "source": "kalshi",
                "category": "entertainment",
                "resolution_date": "2026-11-25T16:00:00Z",
                "prices_updated_at": OBS_NOV_8,
                "outcomes": [
                    {"id": 9100021, "name": "Yes", "probability": 0.76, "observed_at": OBS_NOV_8},
                    {"id": 9100022, "name": "No", "probability": 0.24, "observed_at": OBS_NOV_8},
                ],
            },
            {
                "id": 910003,
                "name": "Will The Running Man top $50M opening weekend?",
                "status": "open",
                "source": "kalshi",
                "category": "entertainment",
                "resolution_date": "2026-11-25T16:00:00Z",
                "prices_updated_at": OBS_NOV_8,
                "outcomes": [
                    {"id": 9100031, "name": "Yes", "probability": 0.34, "observed_at": OBS_NOV_8},
                    {"id": 9100032, "name": "No", "probability": 0.66, "observed_at": OBS_NOV_8},
                ],
            },
        ]

        cards = await roundup_feed_items(pool)
        assert len(cards) == 1
        card = cards[0]
        assert card["type"] == "bundle"
        assert card["data"]["kind"] == "roundup"
        assert card["data"]["collection_ref"]["slug"] == slug
        assert card["data"]["roundup"]["relations"] == [
            "same_measure",
            "same_window",
            "sibling",
        ]
        assert card["data"]["roundup"]["level"] == "member"
        assert [
            (r["label"], r["rendered_percent"])
            for r in card["data"]["roundup"]["rows"]
        ] == [
            ("Wicked: For Good", 88),
            ("Zootopia 2", 76),
            ("The Running Man", 34),
        ]

        reset_roundup_cache_for_tests()
        container = await serve_roundup(slug, pool)
        assert container is not None
        assert container["state"] == "published"
        assert container["slug"] == slug
        assert container["relations"] == ["same_measure", "same_window", "sibling"]
        assert container["level"] == "member"
        assert container["member_count"] == 3

    def test_every_producer_kind_in_containers_dir_builds_via_unified_builder(self) -> None:
        """All 9 producer kinds in backend/data/containers/ build cleanly via build_roundup_producer_from_definition."""
        defs = load_roundup_definitions_from_dir(CONTAINERS_DATA_DIR)
        assert len(defs) >= 18
        seen_kinds: set[str] = set()
        for defn in defs:
            producer = build_roundup_producer_from_definition(defn)
            assert producer.slug == defn["slug"]
            assert producer.relations == tuple(defn["relations"])
            assert producer.level == defn["level"]
            seen_kinds.add(str(defn["rule"]["producer"]))

        assert seen_kinds == {
            "sibling_family",
            "same_deadline_board",
            "yardstick_pair",
            "field_leaders",
            "field_band",
            "week_events",
            "window_events_closest",
            "register_closest",
            "awards_category_roundup",
        }


class TestRelationAndPermissionValidation:
    """Exit #2 & #3 (71-A & 73-A): every file names its relations and level; hand lists require a selector or reason."""

    def test_all_files_in_containers_dir_declare_valid_relations_and_level(self) -> None:
        files = sorted(CONTAINERS_DATA_DIR.glob("*.json"))
        assert len(files) >= 18
        for path in files:
            raw = json.loads(path.read_text(encoding="utf-8"))
            # Must be explicitly declared in the JSON file itself, not merely defaulted
            raw_relations = raw.get("relations") or (raw.get("rule") or {}).get("relations")
            raw_level = raw.get("level") or (raw.get("rule") or {}).get("level")
            assert isinstance(raw_relations, list) and len(raw_relations) >= 1, (
                f"{path.name} is missing explicit 'relations'"
            )
            assert set(raw_relations) <= CLOSED_GROUPING_RELATIONS, (
                f"{path.name} has unknown relations: {raw_relations}"
            )
            assert raw_level in CLOSED_PERMISSION_LEVELS, (
                f"{path.name} is missing or has invalid 'level': {raw_level!r}"
            )

            validated = load_roundup_definition(path)
            assert validated["relations"] == raw_relations
            assert validated["level"] == raw_level

    @pytest.mark.parametrize(
        ("override", "expected_match"),
        [
            ({"relations": []}, "relations"),
            ({"relations": None}, "relations"),
            ({"relations": ["same_measure", "made_up_relation"]}, "made_up_relation"),
            ({"level": ""}, "level"),
            ({"level": "admin_only"}, "level"),
            # Decide 71-A: equivalent is permitted ONLY for twin
            ({"relations": ["same_measure", "sibling"], "level": "equivalent"}, "twin"),
        ],
    )
    def test_invalid_relations_or_level_refused_at_load_time(
        self,
        override: dict[str, Any],
        expected_match: str,
    ) -> None:
        base = {
            "slug": "test-bad-definition",
            "membership": "sibling_family",
            "kind": "roundup",
            "relations": ["same_measure", "sibling"],
            "level": "member",
            "name": "Test card",
            "category": "entertainment",
            "section_title": "Test",
            "footer": "Each item is its own market.",
            "rule": {
                "producer": "sibling_family",
                "source": "kalshi",
                "title_ilike": "%test%",
            },
            **override,
        }
        with pytest.raises(ValueError, match=expected_match):
            validate_roundup_definition(base)

    def test_hand_list_without_selector_or_reason_is_refused_73a(self) -> None:
        """Decide 73-A: a definition whose only member source is a hand list of IDs without id_list_reason is refused."""
        hand_list_only = {
            "slug": "hand-list-without-selector",
            "membership": "sibling_family",
            "kind": "roundup",
            "relations": ["same_measure", "sibling"],
            "level": "member",
            "name": "Hand-picked markets",
            "category": "entertainment",
            "section_title": "This week",
            "footer": "Each film is its own market.",
            "rule": {
                "producer": "sibling_family",
                "source": "kalshi",
                "candidates": ["kalshi:60481116", "kalshi:62383659", "kalshi:65536662"],
            },
        }
        with pytest.raises(ValueError, match="id_list_reason|selector"):
            validate_roundup_definition(hand_list_only)

        # With an explicit id_list_reason, the bounded exception is documented and accepted.
        with_reason = {
            **hand_list_only,
            "id_list_reason": "Fallback candidate pool while venue series code is absent.",
        }
        validated = validate_roundup_definition(with_reason)
        assert validated["id_list_reason"].startswith("Fallback candidate pool")

        # An occasion ID (field / register / anchor) is "an id, never a member" and is accepted without id_list_reason.
        occasion_def = {
            "slug": "occasion-field-example",
            "membership": "field_band",
            "kind": "roundup",
            "relations": ["same_event"],
            "level": "member",
            "name": "Example tournament bubble",
            "category": "sports",
            "section_title": "On the bubble",
            "footer": "Playoff qualifiers",
            "rule": {
                "producer": "field_band",
                "field": "kalshi:KXEXAMPLE-26",
                "band": [0.15, 0.85],
            },
        }
        validated_occ = validate_roundup_definition(occasion_def)
        assert validated_occ["slug"] == "occasion-field-example"


class TestRottenTomatoesSelectorAndReleaseWindow:
    """Exit #3 (73-A): rt-scores-this-week uses a title pattern + release window, never a fixed ID list."""

    def test_rt_scores_definition_uses_title_pattern_and_window_with_no_candidates_list(self) -> None:
        rule = RT_SCORES_THIS_WEEK_DEFINITION["rule"]
        assert "candidates" not in rule
        assert "market_ids" not in rule
        assert rule.get("title_ilike") == "%Rotten Tomatoes score%"
        assert int(rule.get("release_window_days", 0)) == 14
        assert RT_SCORES_THIS_WEEK_DEFINITION["relations"] == [
            "same_measure",
            "same_window",
            "sibling",
        ]
        assert RT_SCORES_THIS_WEEK_DEFINITION["level"] == "member"

    @pytest.mark.asyncio
    async def test_rt_scores_picks_up_new_film_in_window_and_excludes_out_of_window_films(self) -> None:
        """A newly added film in the release window (including a multi-word title with a middle dot)
        joins the card automatically, while next week's single early film and December's out-of-window
        films do not break or pollute this week's cohort.
        """
        pool = [
            # Original 3 Nov 10 films
            {
                "id": 60481116,
                "name": "Predator: Badlands Rotten Tomatoes score?",
                "status": "open",
                "source": "kalshi",
                "category": "entertainment",
                "resolution_date": "2026-11-10T15:00:00Z",
                "prices_updated_at": OBS_NOV_8,
                "outcomes": [
                    {"id": 604811161, "name": "Above 60", "probability": 0.92, "observed_at": OBS_NOV_8},
                    {"id": 604811162, "name": "Above 70", "probability": 0.78, "observed_at": OBS_NOV_8},
                    {"id": 604811163, "name": "Above 80", "probability": 0.54, "observed_at": OBS_NOV_8},
                ],
            },
            {
                "id": 62383659,
                "name": "Die My Love Rotten Tomatoes score?",
                "status": "open",
                "source": "kalshi",
                "category": "entertainment",
                "resolution_date": "2026-11-10T15:00:00Z",
                "prices_updated_at": OBS_NOV_8,
                "outcomes": [
                    {"id": 623836591, "name": "Above 60", "probability": 0.85, "observed_at": OBS_NOV_8},
                    {"id": 623836592, "name": "Above 70", "probability": 0.64, "observed_at": OBS_NOV_8},
                    {"id": 623836593, "name": "Above 80", "probability": 0.31, "observed_at": OBS_NOV_8},
                ],
            },
            {
                "id": 65536662,
                "name": "Christy Rotten Tomatoes score?",
                "status": "open",
                "source": "kalshi",
                "category": "entertainment",
                "resolution_date": "2026-11-10T15:00:00Z",
                "prices_updated_at": OBS_NOV_8,
                "outcomes": [
                    {"id": 655366621, "name": "Above 60", "probability": 0.74, "observed_at": OBS_NOV_8},
                    {"id": 655366622, "name": "Above 70", "probability": 0.49, "observed_at": OBS_NOV_8},
                    {"id": 655366623, "name": "Above 80", "probability": 0.19, "observed_at": OBS_NOV_8},
                ],
            },
            # Newly added 4th film in the same release cohort with a 6-word title and middle dot
            {
                "id": 66999001,
                "name": "The Cat in the Hat \u00b7 Rotten Tomatoes score",
                "status": "open",
                "source": "kalshi",
                "category": "entertainment",
                "resolution_date": "2026-11-10T15:00:00Z",
                "prices_updated_at": OBS_NOV_8,
                "outcomes": [
                    {"id": 669990011, "name": "Above 60", "probability": 0.81, "observed_at": OBS_NOV_8},
                    {"id": 669990012, "name": "Above 70", "probability": 0.68, "observed_at": OBS_NOV_8},
                    {"id": 669990013, "name": "Above 80", "probability": 0.42, "observed_at": OBS_NOV_8},
                ],
            },
            # Next week's single early film (Nov 16) that only has Above 50 / Above 75 rungs
            {
                "id": 66855794,
                "name": "Ebenezer \u00b7 Rotten Tomatoes score",
                "status": "open",
                "source": "kalshi",
                "category": "entertainment",
                "resolution_date": "2026-11-16T15:00:00Z",
                "prices_updated_at": OBS_NOV_8,
                "outcomes": [
                    {"id": 668557941, "name": "Above 50", "probability": 0.50, "observed_at": OBS_NOV_8},
                    {"id": 668557942, "name": "Above 75", "probability": 0.50, "observed_at": OBS_NOV_8},
                ],
            },
            # Out-of-window December film (Dec 22 > 14 days from Nov 8) with a non-strict rung
            {
                "id": 61251665,
                "name": "Avatar: Fire and Ash \u00b7 Rotten Tomatoes score",
                "status": "open",
                "source": "kalshi",
                "category": "entertainment",
                "resolution_date": "2026-12-22T15:00:00Z",
                "prices_updated_at": OBS_NOV_8,
                "outcomes": [
                    {"id": 612516651, "name": "50 or more", "probability": 0.95, "observed_at": OBS_NOV_8},
                    {"id": 612516652, "name": "Above 80", "probability": 0.61, "observed_at": OBS_NOV_8},
                ],
            },
        ]

        res = await rt_scores_this_week(pool, now=NOW_NOV_8)
        assert isinstance(res, RoundupMembers)
        # All 4 Nov 10 films (including "The Cat in the Hat") are included at the shared Above 80 rung;
        # card_rows=3 shows the top 3 on the card while res.members holds all 4!
        assert [
            (r["market_id"], r["label"], r["rendered_percent"]) for r in res.rows
        ] == [
            (60481116, "Predator: Badlands", 54),
            (66999001, "The Cat in the Hat", 42),
            (62383659, "Die My Love", 31),
        ]
        assert res.count_line == "Showing 3 of 4 films"
        member_ids = [int(m["id"]) for m in res.members]
        assert member_ids == [60481116, 66999001, 62383659, 65536662]
        assert 61251665 not in member_ids
        assert 66855794 not in member_ids


class TestKindModuleFirstImport:
    """Importing any round-up kind module first in a fresh Python interpreter must exit 0."""

    @pytest.mark.parametrize(
        "module_name",
        [
            "app.utils.awards_category_roundup",
            "app.utils.discover_bundles",
            "app.utils.field_band",
            "app.utils.field_leaders",
            "app.utils.register_closest",
            "app.utils.roundup_containers",
            "app.utils.same_deadline_board",
            "app.utils.sibling_family",
            "app.utils.week_events",
            "app.utils.window_events_closest",
            "app.utils.yardstick_pair",
        ],
    )
    def test_importing_kind_module_first_exits_zero(
        self, module_name: str
    ) -> None:
        import subprocess
        import sys

        backend_root = str(Path(__file__).resolve().parents[1])
        proc = subprocess.run(
            [
                sys.executable,
                "-c",
                f"import {module_name}; from app.utils.roundup_containers import ROUNDUP_PRODUCERS; assert len(ROUNDUP_PRODUCERS) >= 19",
            ],
            cwd=backend_root,
            capture_output=True,
            text=True,
            timeout=15,
            check=False,
        )
        assert proc.returncode == 0, (
            f"Importing {module_name} first failed with code {proc.returncode}:\n"
            f"stdout: {proc.stdout}\nstderr: {proc.stderr}"
        )
