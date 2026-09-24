"""#7994 — the repair closes exactly the stroke-play rows we minted for a team match-play event.

Population rows are verbatim from production `futures_markets` (2026-09-24 05:40Z).
The controls matter more than the positives: a real tournament's Winner market,
a team-event MATCHUP row, a non-datagolf id and a truncated id must never be
selected, and a write must refuse anywhere but the producer app.
"""

import asyncio
import importlib.util
import os
from types import SimpleNamespace
from unittest.mock import patch

import pytest

_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "scripts",
    "repair_7994_close_team_matchplay_datagolf_rows.py",
)
_spec = importlib.util.spec_from_file_location("repair_7994", _PATH)
repair = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(repair)

PRODUCTION_ROWS = [
    (61720777, "Presidents Cup - Winner", "datagolf:pga:500:win"),
    (61720778, "Presidents Cup - Top 5 Finish", "datagolf:pga:500:top_5"),
    (61720779, "Presidents Cup - Top 10 Finish", "datagolf:pga:500:top_10"),
    (61720780, "Presidents Cup - Top 20 Finish", "datagolf:pga:500:top_20"),
    (61720781, "Presidents Cup - Make the Cut", "datagolf:pga:500:make_cut"),
]


class TestThePopulation:
    @pytest.mark.parametrize("market_id,name,external_id", PRODUCTION_ROWS)
    def test_every_production_row_is_in_scope(self, market_id, name, external_id):
        assert repair.in_scope(name, external_id), (market_id, name)

    def test_the_ryder_cup_shape_is_in_scope(self):
        assert repair.in_scope("Ryder Cup - Winner", "datagolf:euro:600:win")

    @pytest.mark.parametrize(
        "name,external_id",
        [
            ("TOUR Championship - Winner", "datagolf:pga:60:win"),
            ("Presidents Cup - Matchups", "datagolf:pga:500:matchups"),
            ("Presidents Cup - Winner", "KXPGAPRESCUP-26-USA"),
            ("Presidents Cup - Winner", "datagolf:pga:win"),
            ("Presidents Cup - Winner", None),
            (None, "datagolf:pga:500:win"),
        ],
    )
    def test_controls_are_never_selected(self, name, external_id):
        assert not repair.in_scope(name, external_id)


class TestOnlyTheProducerAppWrites:
    def test_a_dry_run_runs_anywhere(self):
        assert repair.wrong_app_refusal(False, None) is None
        assert repair.wrong_app_refusal(False, "bainluck-heavy") is None

    def test_a_write_on_the_producer_app_is_allowed(self):
        assert repair.wrong_app_refusal(True, "bainluck") is None

    @pytest.mark.parametrize("app", ["bainluck-heavy", None, ""])
    def test_a_write_anywhere_else_refuses(self, app):
        assert "REFUSING" in (repair.wrong_app_refusal(True, app) or "")

    @pytest.mark.parametrize(
        "flags", [{"backup": True}, {"apply": True}, {"restore": True}]
    )
    def test_run_refuses_before_opening_a_session(self, flags):
        args = SimpleNamespace(backup=False, apply=False, restore=False, **{})
        for k, v in flags.items():
            setattr(args, k, v)
        with patch.dict(os.environ, {"HEROKU_APP_NAME": "bainluck-heavy"}), patch(
            "app.tasks.base.get_task_session",
            side_effect=AssertionError("opened a DB session on the wrong app"),
        ):
            assert asyncio.run(repair.run(args)) == 2
