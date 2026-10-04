"""#10237 — the AFTER comparison: saved pregame chance vs ESPN's final statistic.

Contract: ``10237-AFTER-AUTHORITY-ACK-v1.md`` (+ addendum 0215Z). Two layers:

* UNIT — ``build_after_player_props`` over hand-built rows and boxes: every row
  of the contract's §6 case table, the F-1..F-7 / I-1..I-4 / E-1..E-3 reasons,
  ``record_version``, venue grade, coverage and order.
* INTEGRATED — the real ``_build_game_markets`` on a finished MLB game: the key
  is published, every existing key is byte-identical with or without it, and a
  scheduled or live game carries none.

* FIXTURE GATE (contract §8.5) — ``espn_summary_mlb_401907985_yankees_at_rays_10237.json``
  is ESPN's raw MLB summary for Yankees at Rays, 2026-10-03, copied byte for
  byte (the sha256 is pinned below). It goes through the real parser
  (``get_event_context``), the real completed-box writer and its
  ``provider_box_evidence`` marker, then this reader. It pins the
  ``STATUS_FINAL`` / ``post`` / ``completed: true`` triple behind
  ``FINAL_STATUS_NAMES`` and the batting ``hits`` / ``home runs`` keys. It is
  one game, not coverage of every MLB stat or player. The parser has no MLB
  player identities yet (Live's widening), so every actual from it stays
  ``unknown``. The marker's ``captured_at`` is when the writer ran in this
  test, not when the game ended.

The synthetic boxes elsewhere in this file are REPRESENTATIVE controls; they
do not pay the fixture gate.
"""

from __future__ import annotations

import asyncio
import contextlib
import copy
import hashlib
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.routes import events as events_route
from app.routes.events import _game_markets_cache, _pregame_mark_is_pregame, _prop_player_and_stat
from app.utils import prop_expectation_actual as after
from app.utils.event_props_matrix import blend_mean
from app.utils.prop_expectation_actual import (
    FINAL_STATUS_NAMES,
    REFUSAL_REASONS,
    box_finality,
    build_after_player_props,
    record_version,
)

COMMENCE = datetime(2026, 9, 29, 23, 5, tzinfo=timezone.utc)
PIN_SEEN = "2026-09-29T22:52:00+00:00"
FETCHED = "2026-09-30T03:30:00.123456+00:00"
ESPN_ID = "401000001"
FINAL = {"name": "STATUS_FINAL", "state": "post", "completed": True}

RICE_2 = "s:ben rice|home_runs|full_game|ge:2|over"
RICE_HR = "s:ben rice|home_runs|full_game"


def _box(players=None, identities=None, *, status=FINAL, provider_final=True,
         espn_id=ESPN_ID, fetched=FETCHED, captured=None, live=None, marker=True, **marker_over):
    box = {
        "source": "espn",
        "fetched_at": fetched,
        "players": {"Ben Rice": {"home runs": 2.0, "hits": 3.0}} if players is None else players,
        "scoring_plays": [],
        "player_identities": (
            [{"name": "Ben Rice", "athlete_id": "1000001", "team_id": "10", "side": "away"}]
            if identities is None else identities
        ),
    }
    if live is not None:
        box["live"] = live
    if marker:
        box["provider_box_evidence"] = {
            "provider": "espn",
            "provider_event_id": espn_id,
            "evidence_kind": "fresh_provider_box",
            "captured_at": fetched if captured is None else captured,
            "provider_status": dict(status),
            "provider_final": provider_final,
            **marker_over,
        }
    return box


def _row(outcome_id, market_id, outcome_name, market_name="New York at Boston: Home Runs",
         source="kalshi", **extra):
    return {
        "market_name": market_name,
        "outcome_name": outcome_name,
        "contributor_outcome_ids": [outcome_id],
        "source": source,
        "_market_id": market_id,
        "over_probability": 0.5,
        "_inverted": outcome_name.lower() in ("under", "no"),
        "observed_at": "2026-09-30T03:00:00+00:00",
        **extra,
    }


def _pin(outcomes, observed=PIN_SEEN, **extra):
    pin = {"outcomes": {str(k): v for k, v in outcomes.items()}, "commence_time": COMMENCE.isoformat()}
    if observed is not None:
        pin["observed_at"] = observed
    pin.update(extra)
    return pin


def _build(rows, box=None, *, pins=None, espn_id=ESPN_ID, sport="baseball_mlb", commence=COMMENCE):
    return build_after_player_props(
        rows,
        box_score_data=_box() if box is None else box,
        espn_id=espn_id,
        sport_key=sport,
        player_and_stat=_prop_player_and_stat,
        pregame_mark_by_market_id={1: _pin({11: 0.02})} if pins is None else pins,
        is_pregame=_pregame_mark_is_pregame,
        commence_time=commence,
        home_team="Boston Red Sox",
        away_team="New York Yankees",
    )


def _rice_rows(**extra):
    return [_row(11, 1, "Ben Rice: 2+", **extra)]


def _q(payload, key=RICE_2):
    return {q["question_key"]: q for q in payload["questions"]}[key]


def _a(payload, key=RICE_HR):
    return {a["actual_key"]: a for a in payload["actuals"]}[key]


# ═══════════════════════════════════════════════════ §6 CASE TABLE ═══


class TestTheCaseTable:

    def test_rice_saved_2pct_verified_2_hr_is_reached(self):
        payload = _build(_rice_rows())
        q, a = _q(payload), _a(payload)
        assert a["state"] == "final" and a["value"] == 2 and a["reason"] is None
        assert a["source_label"] == "ESPN final statistic"
        assert a["finality_basis"] == "espn_fresh_box_status_final"
        assert (a["provider"], a["provider_event_id"], a["athlete_id"], a["team_id"]) == (
            "espn", ESPN_ID, "1000001", "10"
        )
        assert a["captured_at"] == FETCHED
        assert q["comparison"] == {"state": "reached", "reason": None}
        assert q["actual_key"] == RICE_HR
        exp = q["expectation"]
        assert (exp["state"], exp["probability"], exp["basis"]) == ("available", 0.02, "single_source")
        assert exp["observed_at"] == PIN_SEEN
        assert exp["contributors"] == [{
            "source": "kalshi", "market_id": 1, "outcome_id": 11, "outcome_name": "Ben Rice: 2+",
            "probability": 0.02, "observed_at": PIN_SEEN, "admission": "pregame_pin_5509",
        }]
        assert q["predicate"] == {"kind": "count_at_least", "count": 2, "side": "over", "label": "2+"}

    def test_same_pin_verified_1_hr_is_below(self):
        payload = _build(_rice_rows(), _box({"Ben Rice": {"home runs": 1.0}}))
        assert _a(payload)["value"] == 1
        assert _q(payload)["comparison"]["state"] == "below"
        assert _q(payload)["expectation"]["probability"] == 0.02

    def test_a_verified_zero_is_a_real_zero(self):
        payload = _build(_rice_rows(), _box({"Ben Rice": {"home runs": 0.0}}))
        assert _a(payload)["value"] == 0 and _a(payload)["state"] == "final"
        assert _q(payload)["comparison"]["state"] == "below"

    def test_judge_no_marker_venue_says_hit_is_unknown_with_the_venue_pair_apart(self):
        rows = [_row(21, 2, "Aaron Judge: 1+", hit=True, actual=None,
                     is_winner=True, resolution_source="kalshi_settled")]
        payload = _build(rows, _box(marker=False), pins={})
        q = _q(payload, "s:aaron judge|home_runs|full_game|ge:1|over")
        a = _a(payload, "s:aaron judge|home_runs|full_game")
        assert (a["state"], a["reason"], a["value"]) == ("unknown", "no_provider_evidence", None)
        assert q["comparison"] == {"state": "unknown", "reason": "no_provider_evidence"}
        assert q["venue_grade"] == {"is_winner": True, "resolution_source": "kalshi_settled"}

    def test_a_retained_live_box_cleared_to_false_is_never_final(self):
        # Retained without a marker: unknown. Retained with the live pass's own
        # marker (provider_final False): pending.
        no_marker = _build(_rice_rows(), _box(marker=False, live=False))
        assert _a(no_marker)["state"] == "unknown"
        live_marker = _build(_rice_rows(), _box(
            live=False, provider_final=False,
            status={"name": "STATUS_IN_PROGRESS", "state": "in", "completed": False},
        ))
        assert (_a(live_marker)["state"], _a(live_marker)["reason"]) == ("pending", "provider_not_final")
        assert _q(live_marker)["comparison"]["state"] == "unknown"

    def test_provider_nonfinal_on_a_completed_row_is_pending(self):
        payload = _build(_rice_rows(), _box(
            provider_final=False, status={"name": "STATUS_POSTPONED", "state": "post", "completed": True},
        ))
        a = _a(payload)
        assert (a["state"], a["reason"], a["value"]) == ("pending", "provider_not_final", None)
        assert a["captured_at"] == FETCHED and a["record_version"] is None

    def test_stat_key_absent(self):
        payload = _build(_rice_rows(), _box({"Ben Rice": {"hits": 1.0}}))
        assert (_a(payload)["state"], _a(payload)["reason"]) == ("unknown", "stat_missing")

    def test_two_will_smiths_are_ambiguous_and_the_merged_line_is_never_read(self):
        rows = [_row(31, 3, "Will Smith: 1+")]
        box = _box(
            {"Will Smith": {"home runs": 1.0}},
            [
                {"name": "Will Smith", "athlete_id": "1", "team_id": "10"},
                {"name": "Will Smith", "athlete_id": "2", "team_id": "20"},
            ],
        )
        a = _a(_build(rows, box, pins={}), "s:will smith|home_runs|full_game")
        assert (a["state"], a["reason"], a["value"], a["athlete_id"]) == (
            "unknown", "ambiguous_player", None, None
        )

    def test_a_missing_player_is_unknown_never_dnp_or_zero(self):
        rows = [_row(41, 4, "Aaron Judge: 1+")]
        a = _a(_build(rows, pins={}), "s:aaron judge|home_runs|full_game")
        assert (a["state"], a["reason"], a["value"]) == ("unknown", "player_not_in_box", None)

    def test_correction_2_to_1_changes_value_version_and_comparison_not_expectation(self):
        before = _build(_rice_rows())
        corrected = _build(_rice_rows(), _box(
            {"Ben Rice": {"home runs": 1.0}}, fetched="2026-09-30T09:00:00+00:00",
        ))
        assert _a(before)["record_version"] != _a(corrected)["record_version"]
        assert _q(corrected)["comparison"]["state"] == "below"
        assert _q(before)["expectation"] == _q(corrected)["expectation"]

    def test_a_late_pin_and_an_opening_line_only_are_excluded(self):
        rows = [_row(11, 1, "Ben Rice: 2+", opening_over_probability=0.03, pregame_mark=0.03),
                _row(12, 1, "Ben Rice: 3+", opening_over_probability=0.01, pregame_mark=0.01)]
        late = (COMMENCE + timedelta(minutes=40)).isoformat()
        payload = _build(rows, pins={1: _pin({11: 0.05}, observed=late)})
        late_q = _q(payload)
        assert late_q["expectation"]["state"] == "unavailable"
        assert late_q["expectation"]["probability"] is None
        assert late_q["expectation"]["excluded"] == [
            {"source": "kalshi", "outcome_id": 11, "reason": "pin_after_start"}
        ]
        opening_q = _q(payload, "s:ben rice|home_runs|full_game|ge:3|over")
        assert opening_q["expectation"]["excluded"][0]["reason"] == "no_pregame_pin"
        assert opening_q["comparison"]["state"] == "below", "the actual still compares"

    def test_an_actual_only_player_never_acquires_a_probability(self):
        payload = _build(_rice_rows(), pins={})
        q = _q(payload)
        assert q["expectation"]["state"] == "unavailable" and q["expectation"]["probability"] is None
        assert q["expectation"]["reason"] == "no_admitted_pin"
        assert q["comparison"]["state"] == "reached"


# ═══════════════════════════════════════════════════ F-1..F-7 ═══


class TestFinality:

    def test_every_gate_in_order(self):
        cases = [
            (dict(sport="americanfootball_nfl"), _box(), "unknown", "sport_not_supported"),
            ({}, None, "unknown", "no_provider_evidence"),
            ({}, _box(marker=False), "unknown", "no_provider_evidence"),
            ({}, _box(evidence_kind="retained_box"), "unknown", "evidence_kind_not_accepted"),
            ({}, _box(provider="statpal"), "unknown", "evidence_kind_not_accepted"),
            ({}, _box(espn_id="401000999"), "unknown", "provider_event_mismatch"),
            ({}, _box(captured="2026-09-30T03:29:00+00:00"), "unknown", "evidence_clock_mismatch"),
            ({}, _box(players={}), "unknown", "evidence_box_empty"),
            ({}, _box(live=True), "pending", "live_capture"),
            ({}, _box(provider_final=False), "pending", "provider_not_final"),
            ({}, _box(status={**FINAL, "completed": False}), "pending", "provider_not_final"),
            ({}, _box(status={**FINAL, "completed": "true"}), "pending", "provider_not_final"),
        ]
        for kw, box, state, reason in cases:
            got = box_finality(box, ESPN_ID, kw.get("sport", "baseball_mlb"))
            assert (got["state"], got["reason"]) == (state, reason), (kw, reason)

    def test_an_espn_id_re_key_cannot_carry_the_old_box(self):
        assert box_finality(_box(), "401000002", "baseball_mlb")["reason"] == "provider_event_mismatch"
        assert box_finality(_box(), None, "baseball_mlb")["reason"] == "provider_event_mismatch"
        assert box_finality(_box(), int(ESPN_ID), "baseball_mlb")["state"] == "final"

    def test_an_unknown_status_name_fails_closed(self):
        for name in ("STATUS_FINAL_PEN", "STATUS_END_OF_GAME", "STATUS_SHORTENED", None):
            got = box_finality(_box(status={**FINAL, "name": name}), ESPN_ID, "baseball_mlb")
            assert (got["state"], got["reason"]) == ("pending", "provider_not_final"), name

    def test_the_allowlist_is_mlb_status_final_only(self):
        assert FINAL_STATUS_NAMES == {"baseball_mlb": frozenset({"STATUS_FINAL"})}

    def test_nothing_else_is_finality(self):
        # A box with no marker stays unknown whatever the row and event say.
        box = _box(marker=False)
        box.update({"live": False, "completed_at": FETCHED})
        payload = _build(_rice_rows(hit=True, is_winner=True, resolution_source="box_score", actual=2), box)
        assert _a(payload)["state"] == "unknown"


# ═══════════════════════════════════════════════════ I-1..I-4 ═══


class TestIdentityAndValue:

    def test_a_malformed_twin_makes_the_name_ambiguous(self):
        box = _box(identities=[
            {"name": "Ben Rice", "athlete_id": "1000001", "team_id": "10"},
            {"name": "Ben Rice", "athlete_id": "", "team_id": "10"},
        ])
        assert _a(_build(_rice_rows(), box))["reason"] == "ambiguous_player"

    def test_the_same_athlete_listed_twice_is_one_identity(self):
        entry = {"name": "Ben Rice", "athlete_id": "1000001", "team_id": "10"}
        assert _a(_build(_rice_rows(), _box(identities=[entry, dict(entry)])))["state"] == "final"

    def test_identity_matches_on_the_a2_key(self):
        rows = [_row(51, 5, "Julio Rodriguez: 1+")]
        box = _box({"Julio Rodríguez": {"home runs": 1.0}},
                   [{"name": "Julio Rodríguez", "athlete_id": "7", "team_id": "12"}])
        a = _a(_build(rows, box, pins={}), "s:julio rodriguez|home_runs|full_game")
        assert (a["state"], a["value"]) == ("final", 1)

    def test_no_identity_list_is_player_not_in_box(self):
        # MLB identities ship only with Live's widening; reader-first is safe.
        assert _a(_build(_rice_rows(), _box(identities=[])))["reason"] == "player_not_in_box"

    @pytest.mark.parametrize("value,expected", [(2.0, 2), (2, 2), (0.0, 0)])
    def test_integer_counts(self, value, expected):
        assert _a(_build(_rice_rows(), _box({"Ben Rice": {"home runs": value}})))["value"] == expected

    @pytest.mark.parametrize("value", [2.5, -1.0, float("nan"), float("inf"), None, "2", True])
    def test_non_counts_are_refused(self, value):
        a = _a(_build(_rice_rows(), _box({"Ben Rice": {"home runs": value}})))
        assert (a["state"], a["reason"], a["value"]) == ("unknown", "stat_not_integer_count", None)

    def test_hits_reads_the_batting_key_never_hits_allowed(self):
        rows = [_row(61, 6, "Ben Rice: 2+", market_name="New York at Boston: Hits")]
        box = _box({"Ben Rice": {"hits": 1.0, "pitching hits allowed": 5.0}})
        payload = _build(rows, box, pins={})
        assert _a(payload, "s:ben rice|hits|full_game")["value"] == 1


# ═══════════════════════════════════════════════════ §5 VERSION ═══


class TestRecordVersion:

    def test_a_captured_at_only_re_fetch_keeps_the_version(self):
        first = _a(_build(_rice_rows()))
        refetch = _a(_build(_rice_rows(), _box(fetched="2026-09-30T08:00:00+00:00")))
        assert refetch["captured_at"] != first["captured_at"]
        assert refetch["record_version"] == first["record_version"]

    def test_the_version_is_the_specified_hash(self):
        import hashlib, json
        expected = hashlib.sha256(json.dumps(
            ["espn", ESPN_ID, "1000001", "10", "home_runs", "full_game", 2], separators=(",", ":"),
        ).encode()).hexdigest()[:16]
        assert _a(_build(_rice_rows()))["record_version"] == expected
        assert record_version("espn", ESPN_ID, "1000001", "10", "home_runs", "full_game", 2) == expected

    def test_a_non_final_actual_has_no_version(self):
        assert _a(_build(_rice_rows(), _box(live=True)))["record_version"] is None


# ═══════════════════════════════════════════════════ §4 EXPECTATION ═══


class TestExpectation:

    def test_the_a0_pair_blends_its_pins(self):
        rows = [
            _row(11, 1, "Ben Rice: 2+"),
            _row(21, 2, "Over", market_name="Ben Rice: Home Runs O/U 1.5", source="polymarket"),
        ]
        later = "2026-09-29T22:58:00+00:00"
        payload = _build(rows, pins={1: _pin({11: 0.02}), 2: _pin({21: 0.04}, observed=later)})
        exp = _q(payload)["expectation"]
        assert exp["basis"] == "blend_mean" and exp["probability"] == blend_mean([0.02, 0.04]) == 0.03
        assert [c["source"] for c in exp["contributors"]] == ["kalshi", "polymarket"]
        assert exp["observed_at"] == later, "the latest admitted pin's own clock"
        assert _q(payload)["contributor_outcome_ids"] == [11, 21]

    def test_one_admitted_of_two_is_single_source_and_names_the_exclusion(self):
        rows = [
            _row(11, 1, "Ben Rice: 2+"),
            _row(21, 2, "Over", market_name="Ben Rice: Home Runs O/U 1.5", source="polymarket"),
        ]
        payload = _build(rows, pins={1: _pin({11: 0.02})})
        exp = _q(payload)["expectation"]
        assert (exp["basis"], exp["probability"]) == ("single_source", 0.02)
        assert exp["excluded"] == [{"source": "polymarket", "outcome_id": 21, "reason": "no_pregame_pin"}]

    def test_an_unjudgeable_pin_is_not_proof(self):
        # #5509 admits it (no clock); E-3 does not.
        pin = _pin({11: 0.02}, observed=None)
        assert _pregame_mark_is_pregame(pin, COMMENCE) is True, "control: the #5509 gate admits it"
        exp = _q(_build(_rice_rows(), pins={1: pin}))["expectation"]
        assert exp["excluded"][0]["reason"] == "pin_unjudgeable"

    def test_a_pin_with_no_commence_anywhere_is_unjudgeable(self):
        pin = _pin({11: 0.02})
        pin.pop("commence_time")
        exp = _q(_build(_rice_rows(), pins={1: pin}, commence=None))["expectation"]
        assert exp["excluded"][0]["reason"] == "pin_unjudgeable"

    def test_a_legacy_captured_at_pin_is_admitted_on_its_own_clock(self):
        pin = _pin({11: 0.02}, observed=None, captured_at="2026-09-29T22:30:00+00:00")
        exp = _q(_build(_rice_rows(), pins={1: pin}))["expectation"]
        assert exp["state"] == "available" and exp["observed_at"] == "2026-09-29T22:30:00+00:00"

    @pytest.mark.parametrize("raw", [None, 1.2, -0.1, float("nan"), "x", True])
    def test_a_non_probability_pin_is_no_pin(self, raw):
        exp = _q(_build(_rice_rows(), pins={1: _pin({11: raw})}))["expectation"]
        assert exp["excluded"][0]["reason"] == "no_pregame_pin"

    def test_the_pin_reads_through_the_routes_gate(self, monkeypatch):
        calls = []
        def gate(pm, commence):
            calls.append((pm, commence))
            return False
        payload = build_after_player_props(
            _rice_rows(), box_score_data=_box(), espn_id=ESPN_ID, sport_key="baseball_mlb",
            player_and_stat=_prop_player_and_stat, pregame_mark_by_market_id={1: _pin({11: 0.02})},
            is_pregame=gate, commence_time=COMMENCE, home_team="Boston Red Sox", away_team="New York Yankees",
        )
        assert calls and calls[0][1] == COMMENCE
        assert _q(payload)["expectation"]["excluded"][0]["reason"] == "pin_after_start"


RICE_1 = "s:ben rice|home_runs|full_game|ge:1|over"
RICE_3 = "s:ben rice|home_runs|full_game|ge:3|over"


def _ou(outcome_id, market_id, line, player="Ben Rice", stat="Home Runs"):
    return _row(outcome_id, market_id, "Over", market_name=f"{player}: {stat} O/U {line}", source="polymarket")


class TestLadderInversion:
    """SD@MIL 15322620 (native, #10237 comment 5979520656): Machado HR 1+
    pinned 0.075 (pm 63967831 O/U 0.5) and 2+ pinned 0.485 (pm 63865773 O/U
    1.5), both admitted. P(2+) > P(1+) is impossible; both rungs withheld."""

    def test_the_machado_specimen_withholds_both_rungs(self):
        rows = [_ou(31, 3, "0.5"), _ou(21, 2, "1.5")]
        payload = _build(rows, pins={3: _pin({31: 0.075}), 2: _pin({21: 0.485})})
        for key, oid in ((RICE_1, 31), (RICE_2, 21)):
            exp = _q(payload, key)["expectation"]
            assert (exp["state"], exp["reason"], exp["probability"]) == (
                "unavailable", after.LADDER_INVERTED, None)
            assert exp["contributors"] == [] and exp["basis"] is None and exp["observed_at"] is None
            assert exp["excluded"] == [{"source": "polymarket", "outcome_id": oid, "reason": "ladder_inverted"}]
        assert payload["coverage"]["expectation_available"] == 0
        # The comparison still runs: the final count is a separate channel.
        assert _q(payload, RICE_2)["comparison"]["state"] == "reached"

    @pytest.mark.parametrize("p1, p2", [(0.30, 0.05), (0.10, 0.10)])
    def test_a_monotone_or_flat_ladder_is_untouched(self, p1, p2):
        rows = [_ou(31, 3, "0.5"), _ou(21, 2, "1.5")]
        payload = _build(rows, pins={3: _pin({31: p1}), 2: _pin({21: p2})})
        assert _q(payload, RICE_1)["expectation"]["probability"] == p1
        assert _q(payload, RICE_2)["expectation"]["probability"] == p2
        assert payload["coverage"]["expectation_available"] == 2

    def test_only_the_rungs_of_an_inverted_pair_are_withheld(self):
        rows = [_ou(31, 3, "0.5"), _ou(21, 2, "1.5"), _ou(41, 4, "2.5")]
        payload = _build(rows, pins={3: _pin({31: 0.30}), 2: _pin({21: 0.50}), 4: _pin({41: 0.01})})
        assert _q(payload, RICE_1)["expectation"]["reason"] == "ladder_inverted"
        assert _q(payload, RICE_2)["expectation"]["reason"] == "ladder_inverted"
        assert _q(payload, RICE_3)["expectation"]["probability"] == 0.01

    def test_a_non_adjacent_inversion_is_caught(self):
        # 1+ ≥ 2+ holds and 2+ < 3+ is adjacent; only 1+ < 3+ names the 1+ rung.
        rows = [_ou(31, 3, "0.5"), _ou(21, 2, "1.5"), _ou(41, 4, "2.5")]
        payload = _build(rows, pins={3: _pin({31: 0.10}), 2: _pin({21: 0.08}), 4: _pin({41: 0.12})})
        assert {_q(payload, k)["expectation"]["reason"] for k in (RICE_1, RICE_2, RICE_3)} == {"ladder_inverted"}

    def test_an_unavailable_rung_is_not_part_of_the_ladder(self):
        rows = [_ou(31, 3, "0.5"), _ou(21, 2, "1.5")]
        payload = _build(rows, pins={2: _pin({21: 0.485})})
        assert _q(payload, RICE_1)["expectation"]["reason"] == "no_admitted_pin"
        assert _q(payload, RICE_2)["expectation"]["probability"] == 0.485

    def test_ladders_are_per_player_and_stat(self):
        rows = [
            _ou(31, 3, "0.5"),
            _ou(51, 5, "1.5", stat="Hits"),
            _ou(61, 6, "1.5", player="Aaron Judge"),
        ]
        pins = {3: _pin({31: 0.075}), 5: _pin({51: 0.40}), 6: _pin({61: 0.30})}
        payload = _build(rows, pins=pins)
        assert payload["coverage"]["expectation_available"] == 3

    def test_a_blended_rung_moves_every_contributor_to_excluded(self):
        rows = [_ou(31, 3, "0.5"), _row(11, 1, "Ben Rice: 2+"), _ou(21, 2, "1.5")]
        pins = {3: _pin({31: 0.05}), 1: _pin({11: 0.06}), 2: _pin({21: 0.485})}
        exp = _q(_build(rows, pins=pins), RICE_2)["expectation"]
        assert exp["state"] == "unavailable"
        assert [(e["source"], e["outcome_id"], e["reason"]) for e in exp["excluded"]] == [
            ("kalshi", 11, "ladder_inverted"), ("polymarket", 21, "ladder_inverted")]

    def test_strawman_without_the_rule_serves_the_impossible_chance(self, monkeypatch):
        monkeypatch.setattr(after, "_withhold_inverted_ladders", lambda questions: None)
        rows = [_ou(31, 3, "0.5"), _ou(21, 2, "1.5")]
        payload = _build(rows, pins={3: _pin({31: 0.075}), 2: _pin({21: 0.485})})
        assert _q(payload, RICE_2)["expectation"]["probability"] == 0.485


# ═══════════════════════════════════════════════════ ruling 003 ═══


class TestTheActualNeverReadsHit:

    def test_a_venue_typed_hit_cannot_render_an_official_check(self):
        rows = _rice_rows(hit=True, actual=2, is_winner=False, resolution_source=None)
        payload = _build(rows, _box(marker=False))
        assert _q(payload)["comparison"]["state"] == "unknown"
        assert _q(payload)["venue_grade"] is None, "no resolution_source, no venue pair"

    def test_the_box_wins_over_a_contrary_row_hit(self):
        rows = _rice_rows(hit=True, actual=2, is_winner=True, resolution_source="kalshi_settled")
        payload = _build(rows, _box({"Ben Rice": {"home runs": 1.0}}))
        assert _q(payload)["comparison"]["state"] == "below"
        assert _q(payload)["venue_grade"] == {"is_winner": True, "resolution_source": "kalshi_settled"}

    def test_a_strawman_that_grades_off_hit_is_caught(self, monkeypatch):
        """Mutant: the actual taken from the row's `hit`. The two tests above
        must fail against it — this proves they can."""
        real = after.build_actual

        def strawman(box, finality, subject_key, subject_label, stat_key):
            a = real(box, finality, subject_key, subject_label, stat_key)
            return {**a, "state": "final", "value": 2, "reason": None}

        monkeypatch.setattr(after, "build_actual", strawman)
        rows = _rice_rows(hit=True, actual=2, resolution_source=None)
        assert _q(_build(rows, _box(marker=False)))["comparison"]["state"] == "reached"
        with pytest.raises(AssertionError):
            TestTheActualNeverReadsHit().test_a_venue_typed_hit_cannot_render_an_official_check()

    def test_a_box_computed_verdict_is_not_a_venue_grade(self):
        rows = _rice_rows(is_winner=True, resolution_source="box_score")
        assert _q(_build(rows))["venue_grade"] is None

    def test_a_venue_void_sits_beside_a_verified_stat(self):
        rows = _rice_rows(is_winner=False, resolution_source="kalshi_void")
        q = _q(_build(rows))
        assert q["comparison"]["state"] == "reached"
        assert q["venue_grade"] == {"is_winner": False, "resolution_source": "kalshi_void"}


# ═══════════════════════════════════════════════════ shape / coverage ═══


class TestShapeAndCoverage:

    def test_refusals_counted_in_legs_once_each(self):
        rows = [
            _row(1, 9, "Ben Rice: 2+", market_name="New York at Boston: Outs Recorded"),   # untyped_stat
            _row(2, 9, "Ben Rice: 1.5+"),                                                   # untyped_predicate
            _row(3, 9, "Over", market_name="Ben Rice: Home Runs O/U 1"),                    # untyped_predicate
            _row(4, 9, "Boston Red Sox: 2+"),                                                     # team_subject
            _row(5, 9, "Under", market_name="Ben Rice: Home Runs O/U 1.5", source="polymarket"),  # under_side
            _row(6, 9, "Ben Rice: 2+", market_name="New York at Boston: Total Bases"),      # not in set
            _row(11, 1, "Ben Rice: 2+"),
        ]
        cov = _build(rows)["coverage"]
        assert cov["refused"] == {
            "untyped_stat": 1, "untyped_predicate": 2, "ambiguous_subject": 0, "team_subject": 1,
            "under_side": 1, "stat_not_in_after_set": 1,
        }
        assert tuple(cov["refused"]) == REFUSAL_REASONS
        assert {k: cov[k] for k in ("questions", "actuals", "final", "pending", "unknown",
                                     "expectation_available")} == {
            "questions": 1, "actuals": 1, "final": 1, "pending": 0, "unknown": 0, "expectation_available": 1,
        }
        assert cov["scope"] == "linked_markets_loaded_for_event"

    def test_null_when_nothing_types(self):
        assert _build([_row(1, 9, "Over", market_name="Ben Rice: Outs Recorded O/U 16.5")]) is None
        assert _build([]) is None

    def test_the_final_count_appears_once_per_player(self):
        rows = [_row(11, 1, "Ben Rice: 1+"), _row(12, 1, "Ben Rice: 2+"), _row(13, 1, "Ben Rice: 3+")]
        payload = _build(rows, pins={})
        assert len(payload["actuals"]) == 1
        assert {q["actual_key"] for q in payload["questions"]} == {RICE_HR}
        assert [q["comparison"]["state"] for q in payload["questions"]] == ["reached", "reached", "below"]
        assert all("value" not in q for q in payload["questions"])

    def test_server_order_and_stats(self):
        rows = [
            _row(71, 7, "Ben Rice: 2+", market_name="New York at Boston: Hits"),
            _row(13, 1, "Ben Rice: 3+"),
            _row(81, 8, "Aaron Judge: 1+"),
            _row(11, 1, "Ben Rice: 1+"),
        ]
        payload = _build(rows, pins={})
        assert [(q["stat_key"], q["subject"]["label"], q["predicate"]["count"]) for q in payload["questions"]] == [
            ("hits", "Ben Rice", 2), ("home_runs", "Aaron Judge", 1),
            ("home_runs", "Ben Rice", 1), ("home_runs", "Ben Rice", 3),
        ]
        assert [(a["stat_key"], a["subject"]["label"]) for a in payload["actuals"]] == [
            ("hits", "Ben Rice"), ("home_runs", "Aaron Judge"), ("home_runs", "Ben Rice"),
        ]
        assert [s["stat_key"] for s in payload["stats"]] == ["hits", "home_runs"]
        assert payload["stats"][1] == {
            "stat_key": "home_runs", "label": "Home Runs", "unit_singular": "home run",
            "unit_plural": "home runs", "period_key": "full_game", "period_label": "Game",
            "predicate": "count_at_least",
        }
        assert payload["contract"] == "10237.v1"

    def test_every_emitted_reason_is_in_the_closed_sets(self):
        actual_reasons = {None, "sport_not_supported", "no_provider_evidence", "evidence_kind_not_accepted",
                          "provider_event_mismatch", "evidence_clock_mismatch", "evidence_box_empty",
                          "live_capture", "provider_not_final", "player_not_in_box", "ambiguous_player",
                          "stat_missing", "stat_not_integer_count"}
        boxes = [_box(), _box(marker=False), _box(live=True), _box(players={}), _box(provider_final=False),
                 _box({"Ben Rice": {"hits": 1.0}}), _box(identities=[])]
        for box in boxes:
            payload = _build(_rice_rows(), box)
            for a in payload["actuals"]:
                assert a["reason"] in actual_reasons
                assert a["state"] in ("final", "pending", "unknown")
            for q in payload["questions"]:
                assert q["comparison"]["state"] in ("reached", "below", "unknown")

    def test_the_input_rows_are_not_mutated(self):
        rows = _rice_rows(hit=True, is_winner=True, resolution_source="kalshi_settled")
        snapshot = copy.deepcopy(rows)
        _build(rows)
        assert rows == snapshot


# ═══════════════════════════════════════════════════ INTEGRATED ═══


@pytest.fixture(autouse=True)
def _clear_cache():
    _game_markets_cache.clear()
    yield
    _game_markets_cache.clear()


def _result(scalar=None, rows=None, all_rows=None):
    result = MagicMock()
    result.scalar_one_or_none.return_value = scalar
    result.scalars.return_value.all.return_value = rows or []
    result.all.return_value = all_rows if all_rows is not None else []
    return result


def _event(*, status, commence, box):
    event = MagicMock()
    event.id = 15320207
    event.home_team_name = "Boston Red Sox"
    event.away_team_name = "New York Yankees"
    event.status = status
    event.sport_id = None
    event.sport = MagicMock()
    event.sport.key = "baseball_mlb"
    event.commence_time = commence
    event.home_score, event.away_score = 2, 5
    event.period, event.game_clock = None, None
    event.completed_at = None
    event.box_score_data = box
    event.espn_id = ESPN_ID
    event.score_source = event.score_observed_at = None
    return event


def _market(*, id, name, source, commence, pin=None, status="resolved"):
    market = MagicMock()
    market.id = id
    market.name = name
    market.external_id = f"KX-{id}" if source == "kalshi" else f"0x{id:064x}"
    market.event_id = 15320207
    market.category = "game_prop"
    market.status = status
    market.source = source
    market.sport_id = None
    market.llm_sport_category = "baseball"
    market.commence_time = commence
    market.market_type = None
    market.group_id = None
    market.group_type = None
    market.market_metadata = {"pregame_mark": pin} if pin is not None else None
    return market


def _outcome(*, id, market_id, name, prob, is_winner=None, resolution_source=None):
    outcome = MagicMock()
    outcome.id = id
    outcome.market_id = market_id
    outcome.name = name
    outcome.current_probability = prob
    outcome.opening_probability = None
    outcome.resolution_source = resolution_source
    outcome.is_winner = is_winner
    return outcome


def _db(event, markets, outcomes):
    db = AsyncMock()
    db.execute = AsyncMock(side_effect=[
        _result(scalar=event),
        _result(rows=[]),          # #2693 folded_event_ids
        _result(rows=markets),
        _result(all_rows=[]),      # polymarket parent groups
        _result(rows=[]),          # unlinked fallback
        _result(rows=outcomes),
        _result(all_rows=[]),      # #4970 observation load
    ] + [_result() for _ in range(20)])
    return db


def _page(*, status="completed", box="final", hours_ago=5, settled=True):
    """A finished MLB game: Kalshi's Home Runs ladder for Rice with pregame
    pins, Polymarket's Rice O/U 1.5 pair, and a Judge rung with no pin."""
    commence = datetime.now(timezone.utc).replace(microsecond=0) - timedelta(hours=hours_ago)
    pin_seen = (commence - timedelta(minutes=10)).isoformat()
    pin = lambda o: {"outcomes": {str(k): v for k, v in o.items()},
                     "observed_at": pin_seen, "commence_time": commence.isoformat()}
    mstatus = "resolved" if settled else "open"
    markets = [
        _market(id=501, name="New York at Boston: Home Runs", source="kalshi", commence=commence,
                pin=pin({5011: 0.31, 5012: 0.02}), status=mstatus),
        _market(id=502, name="Ben Rice: Home Runs O/U 1.5", source="polymarket", commence=commence,
                pin=pin({5021: 0.04, 5022: 0.96}), status=mstatus),
    ]
    outcomes = [
        _outcome(id=5011, market_id=501, name="Ben Rice: 1+", prob=0.99,
                 is_winner=True, resolution_source="kalshi_settled"),
        _outcome(id=5012, market_id=501, name="Ben Rice: 2+", prob=0.99,
                 is_winner=True, resolution_source="kalshi_settled"),
        _outcome(id=5013, market_id=501, name="Aaron Judge: 1+", prob=0.01,
                 is_winner=False, resolution_source="kalshi_settled"),
        _outcome(id=5021, market_id=502, name="Over", prob=0.99),
        _outcome(id=5022, market_id=502, name="Under", prob=0.01),
    ]
    if not settled:
        # An unsettled page: mid prices, no verdicts, so props reach the reader.
        for o in outcomes:
            o.current_probability, o.is_winner, o.resolution_source = 0.4, None, None
    boxes = {"final": _box(), "none": None, "live": _box(live=True, provider_final=False)}
    event = _event(status=status, commence=commence, box=boxes[box])
    response, _status, _ids = asyncio.run(
        events_route._build_game_markets(event.id, _db(event, markets, outcomes))
    )
    return response


class TestTheServedComparison:

    def test_a_finished_game_publishes_the_comparison(self):
        payload = _page()
        after_props = payload["after_player_props"]
        assert after_props is not None and payload["during_player_props"] is None
        q = _q(after_props)
        assert q["contributor_outcome_ids"] == [5012, 5021]
        assert q["expectation"]["probability"] == blend_mean([0.02, 0.04])
        assert q["comparison"]["state"] == "reached"
        assert q["venue_grade"] == {"is_winner": True, "resolution_source": "kalshi_settled"}
        judge = _q(after_props, "s:aaron judge|home_runs|full_game|ge:1|over")
        assert judge["comparison"] == {"state": "unknown", "reason": "player_not_in_box"}
        assert after_props["coverage"]["refused"]["under_side"] == 1

    def test_a_finished_game_whose_box_has_no_marker_still_publishes_unknowns(self):
        after_props = _page(box="none")["after_player_props"]
        assert {a["state"] for a in after_props["actuals"]} == {"unknown"}

    @pytest.mark.parametrize("status,hours_ago", [
        ("scheduled", -2),
        ("live", 1),
        ("completed", -3),   # a completed row with a future start is not finished
    ])
    def test_null_unless_the_game_is_finished(self, status, hours_ago):
        payload = _page(status=status, hours_ago=hours_ago, box="final", settled=False)
        assert payload["player_props"], "control: the page has props the builder could have typed"
        assert payload["after_player_props"] is None

    def test_every_existing_key_is_byte_identical_with_or_without_the_comparison(self, monkeypatch):
        with_after = _page()
        assert with_after["after_player_props"] is not None
        _game_markets_cache.clear()
        monkeypatch.setattr(events_route, "build_after_player_props", lambda *a, **k: None)
        without = _page()
        with_after.pop("after_player_props")
        without.pop("after_player_props")
        assert _strip_clocks(with_after) == _strip_clocks(without)

    def test_a_builder_error_never_fails_the_page(self, monkeypatch):
        def boom(*a, **k):
            raise RuntimeError("bad box")
        monkeypatch.setattr(events_route, "build_after_player_props", boom)
        payload = _page()
        assert payload["after_player_props"] is None and "player_props" in payload


def _strip_clocks(payload):
    clock_keys = ("observed_at", "observed_at_by_source", "outcome_observed_at")
    def walk(node):
        if isinstance(node, dict):
            return {k: (None if k in clock_keys else walk(v)) for k, v in node.items()}
        if isinstance(node, list):
            return [walk(v) for v in node]
        return node
    return walk(payload)


# ═══════════════════════════════════════════════ §8.5 FIXTURE GATE ═══

MLB_FIXTURE = (
    Path(__file__).parent / "fixtures" / "espn_summary_mlb_401907985_yankees_at_rays_10237.json"
)
MLB_FIXTURE_SHA256 = "d07bc1299d852496b182918e9f9550af39bd0ebcefb0030d3a934fb870e8874e"
MLB_ESPN_ID = "401907985"
MLB_FINAL = {"name": "STATUS_FINAL", "state": "post", "completed": True}


def _raw_summary():
    return json.loads(MLB_FIXTURE.read_bytes())


async def _real_context(summary):
    from app.services.espn_api import ESPNAPIService

    svc = ESPNAPIService()
    try:
        with patch.object(svc, "_get", AsyncMock(return_value=summary)):
            return await svc.get_event_context("baseball_mlb", MLB_ESPN_ID)
    finally:
        await svc.close()


class _Rows:
    def __init__(self, rows):
        self._rows = rows

    def scalars(self):
        return self

    def all(self):
        return self._rows


class _WriteRecorder:
    def __init__(self, event):
        self._event = event
        self.writes: list = []

    async def execute(self, statement, params=None):
        if params is None:
            return _Rows([self._event])
        self.writes.append(params)
        return _Rows([])

    def begin_nested(self):
        return contextlib.nullcontext()


async def _real_stored_box(context):
    """The box the real completed-game writer stores for this response."""
    from app.utils import espn_helpers

    event = MagicMock()
    event.id, event.espn_id, event.status, event.box_score_data = 1, MLB_ESPN_ID, "completed", None
    event.home_score, event.away_score = 1, 0
    event.sport = MagicMock()
    event.sport.key = "baseball_mlb"
    service = MagicMock()
    service.get_event_context = AsyncMock(return_value=context)
    service.close = AsyncMock()
    session = _WriteRecorder(event)
    with patch("app.services.espn_api.ESPNAPIService", return_value=service):
        await espn_helpers.fetch_completed_box_scores(session, {})
    assert len(session.writes) == 1
    return json.loads(session.writes[0]["bsd"])


@pytest.fixture(scope="module")
def real_mlb():
    context = asyncio.run(_real_context(_raw_summary()))
    return context, asyncio.run(_real_stored_box(context))


def _real_build(box, rows, *, espn_id=MLB_ESPN_ID, sport="baseball_mlb"):
    return build_after_player_props(
        rows,
        box_score_data=box,
        espn_id=espn_id,
        sport_key=sport,
        player_and_stat=_prop_player_and_stat,
        pregame_mark_by_market_id={},
        is_pregame=_pregame_mark_is_pregame,
        commence_time=datetime(2026, 10, 3, 22, 30, tzinfo=timezone.utc),
        home_team="Tampa Bay Rays",
        away_team="New York Yankees",
    )


class TestTheRealFinishedMlbSummary:

    def test_the_fixture_is_the_accepted_raw_bytes(self):
        raw = MLB_FIXTURE.read_bytes()
        assert (len(raw), hashlib.sha256(raw).hexdigest()) == (892795, MLB_FIXTURE_SHA256)

    def test_STATUS_FINAL_the_raw_summary_carries_the_triple_and_its_own_id(self):
        summary = _raw_summary()
        competition = summary["header"]["competitions"][0]
        assert summary["header"]["id"] == competition["id"] == MLB_ESPN_ID
        status = competition["status"]["type"]
        assert {k: status[k] for k in MLB_FINAL} == MLB_FINAL
        assert status["name"] in FINAL_STATUS_NAMES["baseball_mlb"]
        assert len(summary["boxscore"]["players"]) == 2

    def test_the_parser_reads_the_triple_and_the_id_from_the_response(self, real_mlb):
        scores = real_mlb[0]["scores"]
        assert scores["provider_status"] == MLB_FINAL
        assert scores["provider_event_id"] == MLB_ESPN_ID
        assert (scores["home_score"], scores["away_score"]) == (1, 0)

    def test_the_v1_stats_are_batting_keys_and_zero_is_a_real_zero(self, real_mlb):
        players = real_mlb[0]["box_score"]
        assert len(players) == 27
        assert set(after.AFTER_STAT_BOX_KEYS.values()) <= set(players["Ben Rice"])
        assert (players["Ben Rice"]["hits"], players["Ben Rice"]["home runs"]) == (0.0, 0.0)
        assert players["Jonathan Aranda"]["home runs"] == 1.0
        # A pitcher's line carries hits ALLOWED under its own key, never `hits`.
        cole = players["Gerrit Cole"]
        assert "hits" not in cole and "home runs" not in cole
        assert cole["pitching hits allowed"] == 5.0

    def test_the_parser_keeps_each_mlb_athletes_id_and_team(self, real_mlb):
        # Flipped when live's #10421 (`BOX_SCORE_IDENTITY_SPORTS` += MLB) landed with this reader.
        context, box = real_mlb
        identities = context["box_score_player_identities"]
        assert len(identities) == len(box["player_identities"]) == 27
        by_name = {i["name"]: i for i in identities}
        assert {k: by_name["Ben Rice"][k] for k in ("athlete_id", "team_id", "side")} == {
            "athlete_id": "5016968", "team_id": "10", "side": "away",
        }
        assert {k: by_name["Jonathan Aranda"][k] for k in ("athlete_id", "team_id", "side")} == {
            "athlete_id": "40810", "team_id": "30", "side": "home",
        }

    def test_the_real_writer_marks_it_final_and_the_reader_accepts_it(self, real_mlb):
        box = real_mlb[1]
        evidence = box["provider_box_evidence"]
        assert evidence["provider_status"] == MLB_FINAL and evidence["provider_final"] is True
        # The writer's own clock, not the game's end.
        assert evidence["captured_at"] == box["fetched_at"]
        got = box_finality(box, MLB_ESPN_ID, "baseball_mlb")
        assert (got["state"], got["reason"], got["evidence"]) == ("final", None, evidence)

    def test_CONTROL_the_same_box_under_another_id_or_sport_is_refused(self, real_mlb):
        box = real_mlb[1]
        assert box_finality(box, "401907986", "baseball_mlb")["reason"] == "provider_event_mismatch"
        assert box_finality(box, MLB_ESPN_ID, "americanfootball_nfl")["reason"] == "sport_not_supported"

    _REAL_ROWS = (
        (71, 7, "Ben Rice: 1+", "New York at Tampa Bay: Hits"),
        (72, 8, "Jonathan Aranda: 1+", "New York at Tampa Bay: Home Runs"),
    )

    def _real_rows(self):
        return [_row(o, m, name, market_name=market) for o, m, name, market in self._REAL_ROWS]

    def test_with_identities_each_actual_is_espns_final_count(self, real_mlb):
        payload = _real_build(real_mlb[1], self._real_rows())
        assert len(payload["actuals"]) == len(payload["questions"]) == 2, payload
        got = {
            a["actual_key"]: (a["state"], a["reason"], a["value"], a["athlete_id"], a["team_id"])
            for a in payload["actuals"]
        }
        assert got == {
            "s:ben rice|hits|full_game": ("final", None, 0, "5016968", "10"),
            "s:jonathan aranda|home_runs|full_game": ("final", None, 1, "40810", "30"),
        }
        assert {q["actual_key"]: q["comparison"]["state"] for q in payload["questions"]} == {
            "s:ben rice|hits|full_game": "below",
            "s:jonathan aranda|home_runs|full_game": "reached",
        }
        assert (payload["coverage"]["final"], payload["coverage"]["unknown"]) == (2, 0)

    def test_CONTROL_the_same_real_box_without_identities_stays_unknown(self, real_mlb):
        box = copy.deepcopy(real_mlb[1])
        box.pop("player_identities", None)
        payload = _real_build(box, self._real_rows())
        assert len(payload["actuals"]) == len(payload["questions"]) == 2, payload
        for actual in payload["actuals"]:
            assert (actual["state"], actual["reason"], actual["value"]) == (
                "unknown", "player_not_in_box", None,
            ), actual
        for question in payload["questions"]:
            assert question["comparison"]["state"] == "unknown", question
