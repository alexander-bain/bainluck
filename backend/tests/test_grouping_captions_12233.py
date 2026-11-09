"""Tests for model-written container captions under the no-number rule (#12233).

Covers:
1. Refusal of any caption with a number not in its set (both in commentary prose
   and in attached figure values), using ``value_appears_in_title`` from
   ``app.utils.cu_frame`` (the frame writer's check at ``cu_frame.py:191``).
2. Refusal of model-written numbers in commentary prose under the strict
   no-number rule (digits and spelled-out quantitative number words), plus voice
   guards (no ``question``, no provider names in prose, no betting advice).
3. Every figure read from the set carries ``observed_at`` + ``as_of_label``
   (when it is true) and ``source`` + ``source_href`` (linked to its source
   member — the ``/evals`` rule); missing timestamps or unlinked sources are
   refused.
4. Decide 61-A spend discipline: uses ``LEGACY_MODEL`` from
   ``app.services.llm_models``, prints estimated cost before running, and
   enforces the ``$5.00``/run and ``$30.00``/Nov caps.
5. Captions served on the ``subject_sequence`` container kind
   (``celtics-next-3-games``, ``lakers-next-3-games``) through both
   ``compose_roundup_container`` and ``compose_roundup_feed_item``.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

import pytest

from app.services.llm_models import LEGACY_MODEL
from app.utils.grouping_captions import (
    CAPTION_MONTHLY_CAP_USD,
    CAPTION_RUN_CAP_USD,
    DEFAULT_CAPTION_MODEL,
    DROP_BETTING_ADVICE,
    DROP_FORBIDDEN_QUESTION_WORD,
    DROP_MISSING_OBSERVED_AT,
    DROP_MODEL_WROTE_NUMBER,
    DROP_NUMBER_NOT_IN_SET,
    DROP_PROVIDER_NAME_IN_PROSE,
    DROP_UNLINKED_SOURCE,
    CaptionSpendCapExceededError,
    compose_container_caption,
    estimate_caption_run_spend,
    extract_set_figures,
    format_caption_pre_run_spend_line,
    generate_container_captions,
    sanitize_grouping_caption,
)
from app.utils.roundup_containers import (
    ROUNDUP_PRODUCERS,
    RoundupMembers,
    compose_roundup_container,
    compose_roundup_feed_item,
    load_roundup_definition,
    CONTAINERS_DATA_DIR,
)
from app.utils.subject_sequence import (
    CELTICS_NEXT_3_GAMES_DEFINITION,
    build_subject_sequence_producer,
    produce_subject_sequence,
)

NOW_NOV_8 = datetime(2026, 11, 8, 19, 30, 0, tzinfo=timezone.utc)
OBS_NOV_8 = "2026-11-08T19:20:00Z"


def _sample_set_members() -> list[dict[str, Any]]:
    return [
        {
            "event_id": 15343971,
            "label": "at Bucks · Sun Nov 8",
            "probability": 0.855,
            "rendered_percent": 86,
            "observed_at": OBS_NOV_8,
            "source": "blended",
            "source_href": "/events/15343971",
        },
        {
            "event_id": 15341912,
            "label": "at 76ers · Tue Nov 10",
            "probability": 0.50,
            "rendered_percent": 50,
            "observed_at": OBS_NOV_8,
            "source": "blended",
            "source_href": "/events/15341912",
        },
        {
            "event_id": 15342527,
            "label": "vs Raptors · Wed Nov 11",
            "probability": 0.64,
            "rendered_percent": 64,
            "observed_at": OBS_NOV_8,
            "source": "blended",
            "source_href": "/events/15342527",
        },
    ]


def _make_celtics_fixture_cards() -> list[dict[str, Any]]:
    return [
        {
            "id": 15343971,
            "sport": "basketball_nba",
            "status": "scheduled",
            "commence_time": "2026-11-09T01:00:00Z",
            "home_team": "Milwaukee Bucks",
            "home_team_name": "Milwaukee Bucks",
            "away_team": "Boston Celtics",
            "away_team_name": "Boston Celtics",
            "home_team_data": {"name": "Milwaukee Bucks", "short_name": "Bucks"},
            "away_team_data": {"name": "Boston Celtics", "short_name": "Celtics"},
            "hero_probability": 0.145,
            "hero_probability_away": 0.855,
            "hero_probability_source": "blend",
            "hero_probability_observed_at": OBS_NOV_8,
            "current_odds": {"home": 0.145, "away": 0.855},
        },
        {
            "id": 15341912,
            "sport": "basketball_nba",
            "status": "scheduled",
            "commence_time": "2026-11-11T01:00:00Z",
            "home_team": "Philadelphia 76ers",
            "home_team_name": "Philadelphia 76ers",
            "away_team": "Boston Celtics",
            "away_team_name": "Boston Celtics",
            "home_team_data": {"name": "Philadelphia 76ers", "short_name": "76ers"},
            "away_team_data": {"name": "Boston Celtics", "short_name": "Celtics"},
            "hero_probability": 0.50,
            "hero_probability_away": 0.50,
            "hero_probability_source": "blend",
            "hero_probability_observed_at": OBS_NOV_8,
            "current_odds": {"home": 0.50, "away": 0.50},
        },
        {
            "id": 15342527,
            "sport": "basketball_nba",
            "status": "scheduled",
            "commence_time": "2026-11-12T00:00:00Z",
            "home_team": "Boston Celtics",
            "home_team_name": "Boston Celtics",
            "away_team": "Toronto Raptors",
            "away_team_name": "Toronto Raptors",
            "home_team_data": {"name": "Boston Celtics", "short_name": "Celtics"},
            "away_team_data": {"name": "Toronto Raptors", "short_name": "Raptors"},
            "hero_probability": 0.64,
            "hero_probability_away": 0.36,
            "hero_probability_source": "blend",
            "hero_probability_observed_at": OBS_NOV_8,
            "current_odds": {"home": 0.64, "away": 0.36},
        },
    ]


class TestCaptionNoNumberRuleAndFrameWriterCheck:
    """#12233 Exit: refuses any caption with a number not in its set, and refuses model-written numbers."""

    def test_refuses_caption_with_number_in_prose_not_in_set(self) -> None:
        members = _sample_set_members()
        # 72% is not in the set (set has 86%, 50%, 64%)
        res = sanitize_grouping_caption(
            {
                "commentary": "Boston enters this stretch as a 72% favorite on the road.",
            },
            members=members,
            allow_set_numbers_in_prose=True,
        )
        assert res["ok"] is False
        assert res["caption"] is None
        assert res["dropped_reason"] == DROP_NUMBER_NOT_IN_SET
        assert "72%" in res["offending_numbers"]

    def test_refuses_caption_with_figure_value_not_in_set(self) -> None:
        members = _sample_set_members()
        figures = extract_set_figures(members)
        # Tamper with the first figure's value to a number not in the set ("91%")
        tampered = [dict(figures[0], value="91%"), *figures[1:]]
        res = sanitize_grouping_caption(
            {
                "commentary": "Boston's upcoming stretch pairs eastern division tests in schedule order.",
                "figures": tampered,
            },
            members=members,
        )
        assert res["ok"] is False
        assert res["caption"] is None
        assert res["dropped_reason"] == DROP_NUMBER_NOT_IN_SET
        assert "91%" in res["offending_numbers"]

    def test_refuses_substring_number_collision_via_cu_frame_boundary_check(self) -> None:
        members = _sample_set_members()
        figures = extract_set_figures(members)
        # "6%" is a substring of "86%", but value_appears_in_title must reject "6%"
        tampered = [dict(figures[0], value="6%")]
        res = sanitize_grouping_caption(
            {
                "commentary": "Boston's upcoming stretch pairs eastern division tests in schedule order.",
                "figures": tampered,
            },
            members=members,
        )
        assert res["ok"] is False
        assert res["caption"] is None
        assert res["dropped_reason"] == DROP_NUMBER_NOT_IN_SET
        assert "6%" in res["offending_numbers"]

    def test_strict_no_number_rule_refuses_model_writing_even_set_number_in_prose(self) -> None:
        members = _sample_set_members()
        # 86% IS in the set, but the model prose itself must never write a number
        res = sanitize_grouping_caption(
            {
                "commentary": "Boston opens at 86% in Milwaukee before heading to Philadelphia.",
            },
            members=members,
            allow_set_numbers_in_prose=False,
        )
        assert res["ok"] is False
        assert res["caption"] is None
        assert res["dropped_reason"] == DROP_MODEL_WROTE_NUMBER
        assert "86%" in res["offending_numbers"]

    def test_refuses_spelled_out_number_words_in_commentary_prose(self) -> None:
        members = _sample_set_members()
        res = sanitize_grouping_caption(
            {
                "commentary": "Boston faces three eastern contenders with seventy percent road confidence.",
            },
            members=members,
        )
        assert res["ok"] is False
        assert res["caption"] is None
        assert res["dropped_reason"] in (DROP_NUMBER_NOT_IN_SET, DROP_MODEL_WROTE_NUMBER)

    def test_accepts_zero_number_commentary_with_set_figures_timestamped_and_linked(self) -> None:
        members = _sample_set_members()
        res = sanitize_grouping_caption(
            {
                "commentary": "Boston's upcoming stretch pairs eastern division tests with immediate tip-off readings for each game in schedule order.",
            },
            members=members,
        )
        assert res["ok"] is True
        caption = res["caption"]
        assert caption is not None
        assert caption["no_number_verified"] is True
        assert len(caption["figures"]) == 3
        assert [f["value"] for f in caption["figures"]] == ["86%", "50%", "64%"]
        assert [f["source_href"] for f in caption["figures"]] == [
            "/events/15343971",
            "/events/15341912",
            "/events/15342527",
        ]
        for fig in caption["figures"]:
            assert fig["observed_at"] == OBS_NOV_8
            assert fig["as_of_label"].startswith("as of Nov 08, 19:20 UTC")
            assert fig["source"] == "blended"


class TestCaptionEvalsRuleAndVoiceGuards:
    """#12233: every figure requires observed_at and linked source_href; voice guards enforced."""

    def test_refuses_figure_missing_observed_at(self) -> None:
        members = _sample_set_members()
        figures = extract_set_figures(members)
        figures[0]["observed_at"] = ""
        res = sanitize_grouping_caption(
            {
                "commentary": "Boston's upcoming stretch pairs eastern division tests in schedule order.",
                "figures": figures,
            },
            members=members,
            default_observed_at="",
        )
        assert res["ok"] is False
        assert res["dropped_reason"] == DROP_MISSING_OBSERVED_AT

    def test_refuses_figure_with_unlinked_or_foreign_source_href(self) -> None:
        members = _sample_set_members()
        figures = extract_set_figures(members)
        figures[0]["source_href"] = "/events/99999999"  # Not in the set!
        res = sanitize_grouping_caption(
            {
                "commentary": "Boston's upcoming stretch pairs eastern division tests in schedule order.",
                "figures": figures,
            },
            members=members,
        )
        assert res["ok"] is False
        assert res["dropped_reason"] == DROP_UNLINKED_SOURCE

    def test_refuses_forbidden_question_word_provider_names_and_betting_advice(self) -> None:
        members = _sample_set_members()
        q_res = sanitize_grouping_caption(
            {"commentary": "Each question on the slate tracks Boston's road trip."},
            members=members,
        )
        assert q_res["ok"] is False
        assert q_res["dropped_reason"] == DROP_FORBIDDEN_QUESTION_WORD

        p_res = sanitize_grouping_caption(
            {"commentary": "Kalshi prices Boston ahead in Milwaukee before the home stand."},
            members=members,
        )
        assert p_res["ok"] is False
        assert p_res["dropped_reason"] == DROP_PROVIDER_NAME_IN_PROSE

        b_res = sanitize_grouping_caption(
            {"commentary": "Hammer the road trip parlay before tip-off tonight."},
            members=members,
        )
        assert b_res["ok"] is False
        assert b_res["dropped_reason"] == DROP_BETTING_ADVICE


class TestCaptionSpendDiscipline61A:
    """#12233 / Decide 61-A: uses LEGACY_MODEL, prints spend before running, enforces $5/run and $30/Nov caps."""

    def test_uses_registered_legacy_model_and_prints_spend_before_run(self) -> None:
        assert DEFAULT_CAPTION_MODEL == LEGACY_MODEL
        assert CAPTION_RUN_CAP_USD == 5.00
        assert CAPTION_MONTHLY_CAP_USD == 30.00

        printed: list[str] = []
        members = _sample_set_members()
        out = generate_container_captions(
            [
                {
                    "id": "celtics-next-3-games",
                    "members": members,
                    "observed_at": OBS_NOV_8,
                    "candidate_commentary": (
                        "Boston's upcoming stretch pairs eastern division tests with "
                        "immediate tip-off readings for each game in schedule order."
                    ),
                },
                {
                    "id": "bad-number-container",
                    "members": members,
                    "observed_at": OBS_NOV_8,
                    "candidate_commentary": "Boston has a 74% edge across the next 3 games.",
                },
            ],
            print_fn=printed.append,
        )
        assert len(printed) == 1
        assert "[grouping-captions]" in printed[0]
        assert f"model={LEGACY_MODEL}" in printed[0]
        assert len(out["accepted"]) == 1
        assert out["accepted"][0]["container_id"] == "celtics-next-3-games"
        assert len(out["refused"]) == 1
        assert out["refused"][0]["container_id"] == "bad-number-container"
        assert out["refused"][0]["dropped_reason"] == DROP_NUMBER_NOT_IN_SET

    def test_raises_when_run_or_monthly_cap_exceeded(self) -> None:
        with pytest.raises(CaptionSpendCapExceededError):
            generate_container_captions(
                [{"id": "c1", "members": _sample_set_members()}],
                prior_november_spend_usd=29.99999,
                avg_input_tokens=500_000,
                print_fn=lambda _: None,
            )


class TestCaptionsServedOnSubjectSequenceKind:
    """#12233 Exit: captions served on one container kind (subject_sequence)."""

    @pytest.mark.asyncio
    async def test_celtics_and_lakers_subject_sequence_definitions_serve_verified_captions(
        self,
    ) -> None:
        celtics_defn = load_roundup_definition(
            CONTAINERS_DATA_DIR / "celtics-next-3-games.json"
        )
        lakers_defn = load_roundup_definition(
            CONTAINERS_DATA_DIR / "lakers-next-3-games.json"
        )
        assert "caption" in celtics_defn
        assert "caption" in lakers_defn

        cards = _make_celtics_fixture_cards()
        producer = build_subject_sequence_producer(CELTICS_NEXT_3_GAMES_DEFINITION)
        members = await produce_subject_sequence(
            CELTICS_NEXT_3_GAMES_DEFINITION,
            cards,
            now=NOW_NOV_8,
        )
        assert isinstance(members, RoundupMembers)
        assert members.caption is not None
        assert members.caption["no_number_verified"] is True

        container_payload = compose_roundup_container(producer, members)
        assert container_payload is not None
        assert container_payload["caption"] is not None
        assert container_payload["caption"]["no_number_verified"] is True
        assert (
            container_payload["caption"]["commentary"]
            == "Boston's upcoming stretch pairs eastern division tests with immediate tip-off readings for each game in schedule order."
        )
        assert [f["value"] for f in container_payload["caption"]["figures"]] == [
            "86%",
            "50%",
            "64%",
        ]
        assert [f["source_href"] for f in container_payload["caption"]["figures"]] == [
            "/events/15343971",
            "/events/15341912",
            "/events/15342527",
        ]

        feed_item = compose_roundup_feed_item(producer, members)
        assert feed_item is not None
        roundup_meta = feed_item["data"]["roundup"]
        assert "caption" in roundup_meta
        assert roundup_meta["caption"] == container_payload["caption"]
        assert compose_container_caption({"caption": "Boston is a 99% lock"}, members=members.rows) is None
