"""Tests for model-written container captions under the no-number rule (#12233).

Covers:
1. Refusal of any caption with a number not in its set (both in commentary prose
   and in attached figure values), using ``value_appears_in_title`` from
   ``app.utils.cu_frame`` (the frame writer's check at ``cu_frame.py:191``).
2. Refusal of model-written numbers in commentary prose under the strict
   no-number rule (digits and spelled-out quantitative number words), plus voice
   guards (no ``question``, no provider names in prose, no betting advice, no
   internal jargon).
3. Member-set binding and factual claim checks:
   - Stored captions carry ``member_ids`` bound to the set they were written for;
     ``compose_container_caption`` refuses when the set rolls or ``member_ids``
     is missing (``DROP_SET_MISMATCH``).
   - ``validate_caption_claims_against_set`` checks conference, division,
     home/road site, and named opponent claims against the member rows
     (``DROP_CLAIM_MISMATCH``).
4. Every figure read from the set carries its own member row's ``observed_at`` +
   ``as_of_label`` (when it is true, never overwritten by ``default_observed_at``)
   and ``source`` + ``source_href`` (linked to its source member — the ``/evals``
   rule); missing timestamps or unlinked sources are refused.
5. Decide 61-A spend discipline: uses ``LEGACY_MODEL`` from
   ``app.services.llm_models``, prints estimated cost before running, enforces
   the ``$5.00``/run and ``$30.00``/Nov caps, and regenerates offline when a
   container's set changes.
6. Captions served on the ``subject_sequence`` container kind
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
    DROP_CLAIM_MISMATCH,
    DROP_FORBIDDEN_QUESTION_WORD,
    DROP_JARGON_IN_PROSE,
    DROP_MISSING_OBSERVED_AT,
    DROP_MODEL_WROTE_NUMBER,
    DROP_NUMBER_NOT_IN_SET,
    DROP_PROVIDER_NAME_IN_PROSE,
    DROP_SET_MISMATCH,
    DROP_UNLINKED_SOURCE,
    CaptionSpendCapExceededError,
    caption_needs_regeneration,
    compose_container_caption,
    estimate_caption_run_spend,
    extract_set_figures,
    format_caption_pre_run_spend_line,
    generate_container_captions,
    sanitize_grouping_caption,
    validate_caption_claims_against_set,
)
from app.utils.roundup_containers import (
    CONTAINERS_DATA_DIR,
    RoundupMembers,
    compose_roundup_container,
    compose_roundup_feed_item,
    load_roundup_definition,
)
from app.utils.subject_sequence import (
    CELTICS_NEXT_3_GAMES_DEFINITION,
    build_subject_sequence_producer,
    produce_subject_sequence,
)

NOW_NOV_9 = datetime(2026, 11, 9, 20, 30, 0, tzinfo=timezone.utc)
OBS_GAME_1 = "2026-11-09T20:25:35Z"
OBS_GAME_2 = "2026-11-09T20:18:10Z"
OBS_GAME_3 = "2026-11-09T19:54:00Z"


def _sample_celtics_set_members() -> list[dict[str, Any]]:
    return [
        {
            "event_id": 15344730,
            "label": "at 76ers · Tue Nov 10",
            "opponent_label": "at 76ers",
            "probability": 0.515,
            "rendered_percent": 52,
            "observed_at": OBS_GAME_1,
            "source": "blended",
            "source_href": "/events/15344730",
        },
        {
            "event_id": 15342527,
            "label": "at Raptors · Wed Nov 11",
            "opponent_label": "at Raptors",
            "probability": 0.64,
            "rendered_percent": 64,
            "observed_at": OBS_GAME_2,
            "source": "blended",
            "source_href": "/events/15342527",
        },
        {
            "event_id": 15344712,
            "label": "vs Mavericks · Sun Nov 15",
            "opponent_label": "vs Mavericks",
            "probability": 0.58,
            "rendered_percent": 58,
            "observed_at": OBS_GAME_3,
            "source": "blended",
            "source_href": "/events/15344712",
        },
    ]


def _sample_lakers_set_members() -> list[dict[str, Any]]:
    return [
        {
            "event_id": 15344868,
            "label": "at Hawks · Mon Nov 9",
            "opponent_label": "at Hawks",
            "probability": 0.54,
            "rendered_percent": 54,
            "observed_at": OBS_GAME_1,
            "source": "blended",
            "source_href": "/events/15344868",
        },
        {
            "event_id": 15342583,
            "label": "at Bucks · Wed Nov 11",
            "opponent_label": "at Bucks",
            "probability": 0.46,
            "rendered_percent": 46,
            "observed_at": OBS_GAME_2,
            "source": "blended",
            "source_href": "/events/15342583",
        },
        {
            "event_id": 15344677,
            "label": "at Suns · Sun Nov 15",
            "opponent_label": "at Suns",
            "probability": 0.49,
            "rendered_percent": 49,
            "observed_at": OBS_GAME_3,
            "source": "blended",
            "source_href": "/events/15344677",
        },
    ]


def _make_celtics_fixture_cards() -> list[dict[str, Any]]:
    return [
        {
            "id": 15344730,
            "sport": "basketball_nba",
            "status": "scheduled",
            "commence_time": "2026-11-11T01:00:00Z",
            "home_team": "Philadelphia 76ers",
            "home_team_name": "Philadelphia 76ers",
            "away_team": "Boston Celtics",
            "away_team_name": "Boston Celtics",
            "home_team_data": {
                "name": "Philadelphia 76ers",
                "short_name": "76ers",
                "standings": {"conference": "Eastern Conference", "division": "Atlantic"},
            },
            "away_team_data": {
                "name": "Boston Celtics",
                "short_name": "Celtics",
                "standings": {"conference": "Eastern Conference", "division": "Atlantic"},
            },
            "hero_probability": 0.485,
            "hero_probability_away": 0.515,
            "hero_probability_source": "blend",
            "hero_probability_observed_at": OBS_GAME_1,
            "current_odds": {"home": 0.485, "away": 0.515},
        },
        {
            "id": 15342527,
            "sport": "basketball_nba",
            "status": "scheduled",
            "commence_time": "2026-11-12T00:00:00Z",
            "home_team": "Toronto Raptors",
            "home_team_name": "Toronto Raptors",
            "away_team": "Boston Celtics",
            "away_team_name": "Boston Celtics",
            "home_team_data": {
                "name": "Toronto Raptors",
                "short_name": "Raptors",
                "standings": {"conference": "Eastern Conference", "division": "Atlantic"},
            },
            "away_team_data": {
                "name": "Boston Celtics",
                "short_name": "Celtics",
                "standings": {"conference": "Eastern Conference", "division": "Atlantic"},
            },
            "hero_probability": 0.36,
            "hero_probability_away": 0.64,
            "hero_probability_source": "blend",
            "hero_probability_observed_at": OBS_GAME_2,
            "current_odds": {"home": 0.36, "away": 0.64},
        },
        {
            "id": 15344712,
            "sport": "basketball_nba",
            "status": "scheduled",
            "commence_time": "2026-11-15T23:00:00Z",
            "home_team": "Boston Celtics",
            "home_team_name": "Boston Celtics",
            "away_team": "Dallas Mavericks",
            "away_team_name": "Dallas Mavericks",
            "home_team_data": {
                "name": "Boston Celtics",
                "short_name": "Celtics",
                "standings": {"conference": "Eastern Conference", "division": "Atlantic"},
            },
            "away_team_data": {
                "name": "Dallas Mavericks",
                "short_name": "Mavericks",
                "standings": {"conference": "Western Conference", "division": "Southwest"},
            },
            "hero_probability": 0.58,
            "hero_probability_away": 0.42,
            "hero_probability_source": "blend",
            "hero_probability_observed_at": OBS_GAME_3,
            "current_odds": {"home": 0.58, "away": 0.42},
        },
    ]


class TestCaptionNoNumberRuleAndFrameWriterCheck:
    """#12233 Exit: refuses any caption with a number not in its set, and refuses model-written numbers."""

    def test_refuses_caption_with_number_in_prose_not_in_set(self) -> None:
        members = _sample_celtics_set_members()
        # 72% is not in the set (set has 52%, 64%, 58%)
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
        members = _sample_celtics_set_members()
        figures = extract_set_figures(members)
        # Tamper with the first figure's value to a number not in the set ("91%")
        tampered = [dict(figures[0], value="91%"), *figures[1:]]
        res = sanitize_grouping_caption(
            {
                "commentary": "Two Atlantic Division road games, then Dallas visits Boston.",
                "figures": tampered,
            },
            members=members,
        )
        assert res["ok"] is False
        assert res["caption"] is None
        assert res["dropped_reason"] == DROP_NUMBER_NOT_IN_SET
        assert "91%" in res["offending_numbers"]

    def test_refuses_substring_number_collision_via_cu_frame_boundary_check(self) -> None:
        members = _sample_celtics_set_members()
        figures = extract_set_figures(members)
        # "4%" is a substring of "64%", but value_appears_in_title must reject "4%"
        tampered = [dict(figures[0], value="4%")]
        res = sanitize_grouping_caption(
            {
                "commentary": "Two Atlantic Division road games, then Dallas visits Boston.",
                "figures": tampered,
            },
            members=members,
        )
        assert res["ok"] is False
        assert res["caption"] is None
        assert res["dropped_reason"] == DROP_NUMBER_NOT_IN_SET
        assert "4%" in res["offending_numbers"]

    def test_strict_no_number_rule_refuses_model_writing_even_set_number_in_prose(self) -> None:
        members = _sample_celtics_set_members()
        # 52% IS in the set, but the model prose itself must never write a number
        res = sanitize_grouping_caption(
            {
                "commentary": "Boston opens at 52% in Philadelphia before heading to Toronto.",
            },
            members=members,
            allow_set_numbers_in_prose=False,
        )
        assert res["ok"] is False
        assert res["caption"] is None
        assert res["dropped_reason"] == DROP_MODEL_WROTE_NUMBER
        assert "52%" in res["offending_numbers"]

    def test_refuses_spelled_out_number_words_in_commentary_prose(self) -> None:
        members = _sample_celtics_set_members()
        res = sanitize_grouping_caption(
            {
                "commentary": "Two Atlantic Division road games with seventy percent road confidence.",
            },
            members=members,
        )
        assert res["ok"] is False
        assert res["caption"] is None
        assert res["dropped_reason"] in (DROP_NUMBER_NOT_IN_SET, DROP_MODEL_WROTE_NUMBER)

    def test_accepts_zero_number_commentary_with_set_figures_timestamped_and_linked(self) -> None:
        members = _sample_celtics_set_members()
        res = sanitize_grouping_caption(
            {
                "commentary": "Two Atlantic Division road games, then Dallas visits Boston.",
                "member_ids": [15344730, 15342527, 15344712],
            },
            members=members,
            default_observed_at="2026-11-09T00:00:00Z",
        )
        assert res["ok"] is True
        caption = res["caption"]
        assert caption is not None
        assert caption["no_number_verified"] is True
        assert caption["member_ids"] == [15344730, 15342527, 15344712]
        assert len(caption["figures"]) == 3
        assert [f["value"] for f in caption["figures"]] == ["52%", "64%", "58%"]
        assert [f["source_href"] for f in caption["figures"]] == [
            "/events/15344730",
            "/events/15342527",
            "/events/15344712",
        ]
        # Each figure preserves its own member row's observed_at, not default_observed_at
        assert [f["observed_at"] for f in caption["figures"]] == [
            OBS_GAME_1,
            OBS_GAME_2,
            OBS_GAME_3,
        ]
        assert [f["as_of_label"] for f in caption["figures"]] == [
            "as of Nov 09, 20:25 UTC",
            "as of Nov 09, 20:18 UTC",
            "as of Nov 09, 19:54 UTC",
        ]
        for fig in caption["figures"]:
            assert fig["source"] == "blended"


class TestMemberSetBindingAndClaimValidation:
    """Fable review: bind stored captions to member_ids and verify claims against member rows."""

    def test_refuses_caption_when_set_rolls_or_member_ids_missing(self) -> None:
        celtics_members = _sample_celtics_set_members()
        # Stored caption bound to today's set [15344730, 15342527, 15344712]
        stored_caption = {
            "commentary": "Two Atlantic Division road games, then Dallas visits Boston.",
            "member_ids": [15344730, 15342527, 15344712],
        }
        assert compose_container_caption({"caption": stored_caption}, members=celtics_members) is not None

        # Now the set rolls: game 15344730 finishes and a new game 15349999 enters the 3-game window
        rolled_members = [
            celtics_members[1],
            celtics_members[2],
            {
                "event_id": 15349999,
                "label": "vs Cavaliers · Tue Nov 17",
                "opponent_label": "vs Cavaliers",
                "probability": 0.61,
                "rendered_percent": 61,
                "observed_at": OBS_GAME_1,
                "source": "blended",
                "source_href": "/events/15349999",
            },
        ]
        assert compose_container_caption({"caption": stored_caption}, members=rolled_members) is None
        san = sanitize_grouping_caption(
            stored_caption,
            members=rolled_members,
            require_member_ids=True,
        )
        assert san["ok"] is False
        assert san["dropped_reason"] == DROP_SET_MISMATCH
        assert caption_needs_regeneration(stored_caption, rolled_members) is True

        # Unbound stored caption (missing member_ids) is also refused by compose_container_caption
        unbound = {"commentary": "Two Atlantic Division road games, then Dallas visits Boston."}
        assert compose_container_caption({"caption": unbound}, members=celtics_members) is None

    def test_refuses_false_conference_division_and_site_claims(self) -> None:
        lakers_members = _sample_lakers_set_members()
        # Lakers play at Atlanta (East), at Milwaukee (East), at Phoenix (West):
        # claiming a "western slate" is false and must be refused.
        ok, reason = validate_caption_claims_against_set(
            "Los Angeles faces a compact western slate on the road.",
            lakers_members,
        )
        assert ok is False
        assert reason == DROP_CLAIM_MISMATCH

        # "eastern division" is not a real NBA division (it's Eastern Conference or Atlantic Division)
        celtics_members = _sample_celtics_set_members()
        ok_div, reason_div = validate_caption_claims_against_set(
            "Boston's upcoming stretch pairs eastern division tests.",
            celtics_members,
        )
        assert ok_div is False
        assert reason_div == DROP_CLAIM_MISMATCH

        # Wrong count: claiming three Atlantic Division road games when only two are Atlantic road games
        ok_cnt, reason_cnt = validate_caption_claims_against_set(
            "Three Atlantic Division road games open Boston's week.",
            celtics_members,
        )
        assert ok_cnt is False
        assert reason_cnt == DROP_CLAIM_MISMATCH

        # Wrong site for named opponent: claiming Phoenix visits Los Angeles when Lakers are AT Phoenix
        ok_site, reason_site = validate_caption_claims_against_set(
            "Two road games in the East, then Phoenix visits Los Angeles.",
            lakers_members,
        )
        assert ok_site is False
        assert reason_site == DROP_CLAIM_MISMATCH

        # Truthful Lakers and Celtics lines pass claim validation
        ok_lakers, _ = validate_caption_claims_against_set(
            "Two road games in the East, then a Western Conference trip to Phoenix.",
            lakers_members,
        )
        assert ok_lakers is True
        ok_celtics, _ = validate_caption_claims_against_set(
            "Two Atlantic Division road games, then Dallas visits Boston.",
            celtics_members,
        )
        assert ok_celtics is True


class TestCaptionEvalsRuleAndVoiceGuards:
    """#12233: every figure requires observed_at and linked source_href; voice guards enforced."""

    def test_refuses_figure_missing_observed_at(self) -> None:
        members = [dict(m, observed_at="") for m in _sample_celtics_set_members()]
        figures = extract_set_figures(members)
        res = sanitize_grouping_caption(
            {
                "commentary": "Two Atlantic Division road games, then Dallas visits Boston.",
                "figures": figures,
            },
            members=members,
            default_observed_at="",
        )
        assert res["ok"] is False
        assert res["dropped_reason"] == DROP_MISSING_OBSERVED_AT

    def test_refuses_figure_with_unlinked_or_foreign_source_href(self) -> None:
        members = _sample_celtics_set_members()
        figures = extract_set_figures(members)
        figures[0]["source_href"] = "/events/99999999"  # Not in the set!
        res = sanitize_grouping_caption(
            {
                "commentary": "Two Atlantic Division road games, then Dallas visits Boston.",
                "figures": figures,
            },
            members=members,
        )
        assert res["ok"] is False
        assert res["dropped_reason"] == DROP_UNLINKED_SOURCE

    def test_refuses_forbidden_question_word_provider_names_betting_advice_and_jargon(self) -> None:
        members = _sample_celtics_set_members()
        q_res = sanitize_grouping_caption(
            {"commentary": "Each question on the slate tracks Boston's road trip."},
            members=members,
        )
        assert q_res["ok"] is False
        assert q_res["dropped_reason"] == DROP_FORBIDDEN_QUESTION_WORD

        p_res = sanitize_grouping_caption(
            {"commentary": "Kalshi prices Boston ahead in Philadelphia before Toronto."},
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

        j_res = sanitize_grouping_caption(
            {"commentary": "Two road games with immediate tip-off readings for each matchup."},
            members=members,
        )
        assert j_res["ok"] is False
        assert j_res["dropped_reason"] == DROP_JARGON_IN_PROSE


class TestCaptionSpendDiscipline61A:
    """#12233 / Decide 61-A: uses LEGACY_MODEL, prints spend before running, enforces $5/run and $30/Nov caps."""

    def test_uses_registered_legacy_model_prints_spend_checks_claims_and_binds_member_ids(self) -> None:
        assert DEFAULT_CAPTION_MODEL == LEGACY_MODEL
        assert CAPTION_RUN_CAP_USD == 5.00
        assert CAPTION_MONTHLY_CAP_USD == 30.00

        printed: list[str] = []
        celtics_members = _sample_celtics_set_members()
        lakers_members = _sample_lakers_set_members()
        out = generate_container_captions(
            [
                {
                    "id": "celtics-next-3-games",
                    "members": celtics_members,
                    "candidate_commentary": (
                        "Two Atlantic Division road games, then Dallas visits Boston."
                    ),
                },
                {
                    "id": "bad-number-container",
                    "members": celtics_members,
                    "candidate_commentary": "Boston has a 74% edge across the next 3 games.",
                },
                {
                    "id": "false-claim-container",
                    "members": lakers_members,
                    "candidate_commentary": "Los Angeles faces a compact western slate on the road.",
                },
            ],
            print_fn=printed.append,
        )
        assert len(printed) == 1
        assert "[grouping-captions]" in printed[0]
        assert f"model={LEGACY_MODEL}" in printed[0]
        assert len(out["accepted"]) == 1
        assert out["accepted"][0]["container_id"] == "celtics-next-3-games"
        assert out["accepted"][0]["caption"]["member_ids"] == [
            15344730,
            15342527,
            15344712,
        ]
        assert len(out["refused"]) == 2
        assert out["refused"][0]["container_id"] == "bad-number-container"
        assert out["refused"][0]["dropped_reason"] == DROP_NUMBER_NOT_IN_SET
        assert out["refused"][1]["container_id"] == "false-claim-container"
        assert out["refused"][1]["dropped_reason"] == DROP_CLAIM_MISMATCH

    def test_raises_when_run_or_monthly_cap_exceeded(self) -> None:
        with pytest.raises(CaptionSpendCapExceededError):
            generate_container_captions(
                [{"id": "c1", "members": _sample_celtics_set_members()}],
                prior_november_spend_usd=29.99999,
                avg_input_tokens=500_000,
                print_fn=lambda _: None,
            )


class TestCaptionsServedOnSubjectSequenceKind:
    """#12233 Exit: captions served on one container kind (subject_sequence) and refused when set rolls."""

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
        assert celtics_defn["caption"]["member_ids"] == [15344730, 15342527, 15344712]
        assert lakers_defn["caption"]["member_ids"] == [15344868, 15342583, 15344677]

        cards = _make_celtics_fixture_cards()
        producer = build_subject_sequence_producer(CELTICS_NEXT_3_GAMES_DEFINITION)
        members = await produce_subject_sequence(
            CELTICS_NEXT_3_GAMES_DEFINITION,
            cards,
            now=NOW_NOV_9,
        )
        assert isinstance(members, RoundupMembers)
        assert members.caption is not None
        assert members.caption["no_number_verified"] is True
        assert members.caption["member_ids"] == [15344730, 15342527, 15344712]

        container_payload = compose_roundup_container(producer, members)
        assert container_payload is not None
        assert container_payload["caption"] is not None
        assert container_payload["caption"]["no_number_verified"] is True
        assert (
            container_payload["caption"]["commentary"]
            == "Two Atlantic Division road games, then Dallas visits Boston."
        )
        assert [f["value"] for f in container_payload["caption"]["figures"]] == [
            "52%",
            "64%",
            "58%",
        ]
        assert [f["source_href"] for f in container_payload["caption"]["figures"]] == [
            "/events/15344730",
            "/events/15342527",
            "/events/15344712",
        ]
        assert [f["observed_at"] for f in container_payload["caption"]["figures"]] == [
            OBS_GAME_1,
            OBS_GAME_2,
            OBS_GAME_3,
        ]

        feed_item = compose_roundup_feed_item(producer, members)
        assert feed_item is not None
        roundup_meta = feed_item["data"]["roundup"]
        assert "caption" in roundup_meta
        assert roundup_meta["caption"] == container_payload["caption"]

        # Verify Lakers definition caption against Lakers member set
        lakers_caption = compose_container_caption(
            lakers_defn,
            members=_sample_lakers_set_members(),
        )
        assert lakers_caption is not None
        assert (
            lakers_caption["commentary"]
            == "Two road games in the East, then a Western Conference trip to Phoenix."
        )
        assert lakers_caption["member_ids"] == [15344868, 15342583, 15344677]

        # When the Celtics set rolls (first game finishes and a fourth game enters),
        # produce_subject_sequence and compose_roundup_container refuse the stale caption
        rolled_cards = [
            cards[1],
            cards[2],
            {
                **cards[2],
                "id": 15349999,
                "commence_time": "2026-11-17T00:30:00Z",
                "away_team": "Cleveland Cavaliers",
                "away_team_name": "Cleveland Cavaliers",
                "away_team_data": {"name": "Cleveland Cavaliers", "short_name": "Cavaliers"},
            },
        ]
        rolled_members = await produce_subject_sequence(
            CELTICS_NEXT_3_GAMES_DEFINITION,
            rolled_cards,
            now=NOW_NOV_9,
        )
        assert isinstance(rolled_members, RoundupMembers)
        assert rolled_members.caption is None
        rolled_container = compose_roundup_container(producer, rolled_members)
        assert rolled_container is not None
        assert rolled_container["caption"] is None
