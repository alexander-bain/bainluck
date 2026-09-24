"""#8322 — StatPal's hockey minute is not a clock, so the live badge stops running backwards.

WHAT A READER SAW
=================
Every live NHL badge read `● 13 - 2nd Period 13`, and it moved the wrong way.
StatPal's hockey board serves `timer` as the minute of the period ELAPSED (a
bare `'13'`, counting up); ESPN's clock for the same game is the time REMAINING
(`'7:00'`, counting down). Both writers own `period`/`game_clock` on a live row,
so the stored value alternated. Paired reads, Stars–Wild 15313798, 2026-09-24:

    01:54:55Z  ESPN 19:28 left   StatPal timer '1'   row '1 - 3rd Period'
    01:56:29Z  ESPN 18:42 left   StatPal timer '2'   row '19:03 - 3rd Period'
    02:02:01Z  ESPN 15:02 left   StatPal timer '5'   row '5 - 3rd Period'

"1 minute left", then "19 minutes left", in the same period. The reversion guard
(#6056) could not order the two because a bare `'1'` does not parse as a clock,
so it stood down.

THE RULE
========
A StatPal `timer` that is not `M:SS` is never composed into `period` and never
written to `game_clock`, and a label-only write never replaces a stored value
that already places the game inside that same period. An EMPTY timer keeps its
CERT-2569 meaning (the venue stopped the clock → clear it); that path is pinned
by #5017's file and is re-asserted here so this change cannot have moved it.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from app.utils.game_state import is_countdown_clock, period_places_within
from tests.test_statpal_in_progress_period_and_clock_5017 import (
    _Fixture,
    _parse,
    _run_livescores,
)

#: Recorded from `GET /api/v1/nhl/livescores` at 2026-09-24 02:02:05Z (the
#: `events` list dropped). ESPN read `15:02 - 3rd` at 02:02:01Z.
RECORDED_LIVE_HOCKEY_ITEM = {
    "date": "24.09.2026",
    "fix_id": "950152",
    "id": "650468",
    "status": "3rd Period",
    "time": "00:00",
    "timer": "5",
    "home": {"id": "2645", "name": "Dallas Stars", "totalscore": "1"},
    "away": {"id": "2624", "name": "Minnesota Wild", "totalscore": "0"},
}

HOME, AWAY = "Dallas Stars", "Minnesota Wild"


def _hockey_fixture(timer: str | None, status: str = "3rd Period") -> _Fixture:
    """A fixture built by the REAL parser from the recorded board item."""
    parsed = _parse({**RECORDED_LIVE_HOCKEY_ITEM, "timer": timer, "status": status})
    assert parsed is not None and parsed.status == "live"
    return _Fixture(
        datetime.now(timezone.utc) - timedelta(hours=1),
        HOME,
        AWAY,
        raw_status=parsed.raw_status,
        game_clock=parsed.game_clock,
        clock_field_served=parsed.clock_field_served,
    )


async def _run(monkeypatch, fx, *, clock, period):
    rows = await _run_livescores(
        monkeypatch,
        fixtures=[fx],
        events=[(HOME, AWAY, clock, period)],
        sport_key="icehockey_nhl",
    )
    return rows[0]


# ---------------------------------------------------------------------------
# 1. The recorded board really is shaped this way
# ---------------------------------------------------------------------------


def test_the_recorded_hockey_item_parses_to_a_bare_minute():
    """If the parser ever starts converting the minute, the premise here is gone."""
    fx = _hockey_fixture("5")
    assert fx.raw_status == "3rd Period"
    assert fx.game_clock == "5"
    assert fx.clock_field_served is True


# ---------------------------------------------------------------------------
# 2. The predicates
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("value", ["7:16", "19:03", "0:04.2", "15:02", "20:00"])
def test_countdown_clocks_are_clocks(value):
    assert is_countdown_clock(value)


@pytest.mark.parametrize("value", ["13", "1", "5", "", None, "45.2", "13'"])
def test_a_minute_or_anything_else_is_not(value):
    assert not is_countdown_clock(value)


@pytest.mark.parametrize(
    "stored,label,expected",
    [
        ("18:42 - 3rd Period", "3rd Period", True),
        ("End of 3rd Period", "3rd Period", True),
        ("3:21 - OT", "OT", True),
        # A bare minute stored before this fix is what the label SHOULD replace.
        ("13 - 2nd Period", "2nd Period", False),
        ("3rd Period", "3rd Period", False),
        ("18:42 - 2nd Period", "3rd Period", False),
        ("End of 2nd Period", "3rd Period", False),
        (None, "3rd Period", False),
        ("18:42 - 3rd Period", None, False),
    ],
)
def test_period_places_within(stored, label, expected):
    assert period_places_within(stored, label) is expected


# ---------------------------------------------------------------------------
# 3. The write, through the real task
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_a_minute_never_overwrites_espns_clock_in_the_same_period(monkeypatch):
    """THE SHIP. Row holds ESPN's `18:42 - 3rd Period`; StatPal offers minute 2.

    Before: the row became `2 - 3rd Period` / `2` and the badge read two minutes
    where sixteen remained.
    """
    row = await _run(
        monkeypatch, _hockey_fixture("2"), clock="18:42", period="18:42 - 3rd Period"
    )
    assert row.period == "18:42 - 3rd Period"
    assert row.game_clock == "18:42"


@pytest.mark.asyncio
async def test_a_minute_never_overwrites_the_end_of_the_period(monkeypatch):
    """At the horn StatPal still says `3rd Period` with minute 20."""
    row = await _run(
        monkeypatch, _hockey_fixture("20"), clock=None, period="End of 3rd Period"
    )
    assert row.period == "End of 3rd Period"


@pytest.mark.asyncio
async def test_a_new_period_is_written_as_a_bare_label_and_the_old_clock_goes(
    monkeypatch,
):
    """The period moved on and StatPal is first to say so.

    The label lands (the reader must see the 3rd), the minute does not, and the
    2nd period's clock is cleared: `3rd Period` beside `0:00` would read as a
    clock that had already run out.
    """
    row = await _run(
        monkeypatch, _hockey_fixture("1"), clock="0:00", period="End of 2nd Period"
    )
    assert row.period == "3rd Period"
    assert row.game_clock is None


@pytest.mark.asyncio
async def test_a_bare_minute_stored_before_the_fix_is_healed(monkeypatch):
    """Rows written by the old code carry `13 - 2nd Period` / `13`."""
    row = await _run(
        monkeypatch, _hockey_fixture("14", "2nd Period"), clock="13", period="13 - 2nd Period"
    )
    assert row.period == "2nd Period"
    assert row.game_clock is None


@pytest.mark.asyncio
async def test_the_minute_is_never_written_on_an_empty_row(monkeypatch):
    """ESPN dark, nothing stored: the reader gets the period, not a false clock."""
    row = await _run(monkeypatch, _hockey_fixture("13", "2nd Period"), clock=None, period=None)
    assert row.period == "2nd Period"
    assert row.game_clock is None


@pytest.mark.asyncio
async def test_the_score_still_lands_when_the_period_write_is_withheld(monkeypatch):
    """Withholding the label must not withhold the goal."""
    row = await _run(
        monkeypatch, _hockey_fixture("2"), clock="18:42", period="18:42 - 3rd Period"
    )
    assert (row.home_score, row.away_score) == (7, 17)


# ---------------------------------------------------------------------------
# 4. What this change must not touch
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_a_real_countdown_clock_is_still_composed_and_written(monkeypatch):
    """Football's `7:16` keeps #5017's exact behaviour."""
    fx = _Fixture(
        datetime.now(timezone.utc) - timedelta(hours=1),
        "Los Angeles Rams",
        "San Francisco 49ers",
        raw_status="3rd Quarter",
        game_clock="7:16",
    )
    rows = await _run_livescores(
        monkeypatch,
        fixtures=[fx],
        events=[("Los Angeles Rams", "San Francisco 49ers", "9:01", "9:01 - 3rd Quarter")],
    )
    assert rows[0].period == "7:16 - 3rd Quarter"
    assert rows[0].game_clock == "7:16"


@pytest.mark.asyncio
async def test_an_empty_timer_still_clears_the_clock_in_the_same_period(monkeypatch):
    """CERT-2569: empty is the venue stopping the clock — it clears, even when
    the stored value places the game inside the same period. Only a NON-EMPTY
    non-clock is withheld."""
    fx = _Fixture(
        datetime.now(timezone.utc) - timedelta(hours=1),
        "Los Angeles Rams",
        "San Francisco 49ers",
        raw_status="2nd Quarter",
        game_clock=None,
    )
    rows = await _run_livescores(
        monkeypatch,
        fixtures=[fx],
        events=[("Los Angeles Rams", "San Francisco 49ers", "5:21", "5:21 - 2nd Quarter")],
    )
    assert rows[0].period == "2nd Quarter"
    assert rows[0].game_clock is None


def test_the_schedule_writers_position_never_carries_the_minute():
    """`statpal_live_position` must compose what the livescores writer stores."""
    from app.tasks.statpal_sync import statpal_live_position

    assert statpal_live_position(_hockey_fixture("13", "2nd Period")) == ("2nd Period", None)
    football = _Fixture(
        datetime.now(timezone.utc), "a", "b", raw_status="3rd Quarter", game_clock="7:16"
    )
    assert statpal_live_position(football) == ("7:16 - 3rd Quarter", "7:16")
