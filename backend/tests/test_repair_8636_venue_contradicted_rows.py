"""#8636: the venue-contradicted-rows repair writes its pinned rows, the venue's way, and nothing else.

The manifest, the target rule and the refusal rule are pure and driven here. The
SQL — the bank, the guarded writes, the re-run and the undo — runs against a
real PostgreSQL in
``tests/integration/test_repair_8636_venue_contradicted_rows_pg.py``.
"""

from __future__ import annotations

import importlib.util
import sys
from collections import Counter
from pathlib import Path

import pytest

from app.utils.venue_competition import (
    POLYMARKET_EVENT_SLUG_KEY,
    polymarket_league_code,
    venue_refuses_placement,
)

_SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"


def _load():
    sys.path.insert(0, str(_SCRIPTS))
    spec = importlib.util.spec_from_file_location(
        "repair_8636_venue", _SCRIPTS / "repair_8636_venue_contradicted_rows.py"
    )
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


m = _load()

PINNED = {pin[0]: pin for pin in m.PINS}
UWCL = "soccer_uefa_champs_league_women"


class TestTheShip:
    def test_the_italy_slovenia_volleyball_card_is_retired(self):
        """The /search?q=italy card: 15316005, Volleyball European Championship."""
        pin = PINNED[15316005]
        assert pin[1] == "soccer_uefa_nations_league"
        assert m.target_for(pin[3], pin[4]) == ("retire", "voided")

    def test_roma_barcelona_reads_the_womens_champions_league(self):
        pin = PINNED[15313706]
        assert m.target_for(pin[3], pin[4]) == ("relabel", UWCL)

    @pytest.mark.parametrize(
        "event_id,code",
        [
            (15314061, "fif"),  # Lithuania v Andorra, FIFA friendly
            (15315626, "u20wwc"),  # Italy v Spain, U-20 Women's World Cup
            (15316760, "col1"),  # Medellín v Millonarios, Colombia Primera A
            (15317344, "clf"),  # Stuttgart v Heidenheim, the #8636 specimen
            (15318598, "argcopa"),  # Platense v Estudiantes, Copa Argentina
        ],
    )
    def test_a_competition_we_carry_no_league_for_goes_to_the_catch_all(self, event_id, code):
        pin = PINNED[event_id]
        assert polymarket_league_code(pin[3]) == code
        assert m.target_for(pin[3], pin[4]) == ("relabel", "soccer_other")


class TestTheManifest:
    def test_six_relabels_fourteen_retirements(self):
        actions = Counter(m.target_for(p[3], p[4])[0] for p in m.PINS)
        assert actions == {"relabel": 6, "retire": 14}

    def test_no_row_and_no_venue_event_is_pinned_twice(self):
        assert len(PINNED) == len(m.PINS)
        assert len({p[2] for p in m.PINS}) == len(m.PINS)

    def test_every_slug_is_a_game_slug(self):
        for pin in m.PINS:
            assert polymarket_league_code(pin[3]), pin

    @pytest.mark.parametrize("pin", [p for p in m.PINS if p[4] != m.VOLLEYBALL])
    def test_every_soccer_pin_is_one_the_forward_fix_now_refuses(self, pin):
        """The repair's population is exactly what #8641 stops minting: the
        venue's code contradicts the league the row was measured on."""
        meta = {POLYMARKET_EVENT_SLUG_KEY: pin[3]}
        assert venue_refuses_placement(meta, pin[1]) == polymarket_league_code(pin[3])

    @pytest.mark.parametrize("pin", [p for p in m.PINS if p[4] != m.VOLLEYBALL])
    def test_no_soccer_pin_is_relabelled_back_onto_the_league_it_left(self, pin):
        assert m.target_for(pin[3], pin[4])[1] != pin[1]

    def test_every_volleyball_pin_carries_a_volleyball_code(self):
        for pin in m.PINS:
            if pin[4] == m.VOLLEYBALL:
                assert polymarket_league_code(pin[3]).startswith("vb"), pin

    def test_a_non_game_slug_is_refused_not_guessed(self):
        with pytest.raises(ValueError):
            m.target_for("bundesliga-2027-champion", "Soccer")


def _event(**over) -> dict:
    """Italy v Slovenia 15316005 exactly as production held it on 2026-09-27."""
    row = {
        "id": 15316005,
        "sport_id": 1323,
        "sport_key": "soccer_uefa_nations_league",
        "status": "suspended",
        "llm_league": "Uefa Nations League",
        "home_team_name": "Italy",
        "away_team_name": "Slovenia",
    }
    row.update(over)
    return row


PIN = PINNED[15316005]
GROUPS = {"polymarket:1037992"}


class TestTheRule:
    def test_the_specimen_qualifies(self):
        assert m.refusal(PIN, _event(), GROUPS, set()) is None

    def test_a_matching_stamp_still_qualifies(self):
        assert m.refusal(PIN, _event(), GROUPS, {"vbeuro"}) is None

    @pytest.mark.parametrize(
        "event,groups,stamped,expected",
        [
            (None, GROUPS, set(), "gone"),
            (_event(status="voided"), GROUPS, set(), "already 'voided'"),
            (_event(status="merged"), GROUPS, set(), "already 'merged'"),
            (_event(sport_key="soccer_other"), GROUPS, set(), "now on 'soccer_other'"),
            (_event(), set(), set(), "no longer linked"),
            (_event(), {"polymarket:1"}, set(), "no longer linked"),
            (_event(), GROUPS, {"unl"}, "now names ['unl']"),
            (_event(), GROUPS, {"vbeuro", "unl"}, "now names ['unl']"),
        ],
    )
    def test_a_row_that_no_longer_qualifies_is_skipped(self, event, groups, stamped, expected):
        why = m.refusal(PIN, event, groups, stamped)
        assert why is not None and expected in why

    def test_live_and_scheduled_rows_are_written_too(self):
        """Status is not a gate: Roma v Barcelona is scheduled and must move."""
        pin = PINNED[15313706]
        ev = _event(id=15313706, sport_key="soccer_uefa_champs_league", status="scheduled")
        assert m.refusal(pin, ev, {"polymarket:1034901"}, {"uwcl"}) is None


class TestWhereItRuns:
    def test_refuses_off_the_heavy_app(self, monkeypatch):
        monkeypatch.setenv("HEROKU_APP_NAME", "bainluck")
        assert "bainluck-heavy" in m.wrong_app_refusal()
        monkeypatch.delenv("HEROKU_APP_NAME")
        assert m.wrong_app_refusal() is not None

    def test_runs_on_the_heavy_app(self, monkeypatch):
        monkeypatch.setenv("HEROKU_APP_NAME", "bainluck-heavy")
        assert m.wrong_app_refusal() is None

    def test_the_backup_is_backup_prefixed_and_its_own(self):
        assert m.BACKUP.startswith("backup_8636")

    def test_the_retired_status_is_the_one_every_surface_hides(self):
        from app.utils.event_completion import RETIRED_STATUSES

        assert m.RETIRED in RETIRED_STATUSES
        assert set(m.RETIRED_STATUSES) == set(RETIRED_STATUSES)
