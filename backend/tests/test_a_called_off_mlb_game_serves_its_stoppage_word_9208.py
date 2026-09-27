"""#9208: a postponed or canceled MLB game serves ESPN's stoppage word.

Orioles @ Yankees 15319530 (2026-09-27) was rain-delayed, then called off:
ESPN 401817103 read `STATUS_CANCELED`, and the live pass stored the row
`suspended` / `period='Postponed'` / `game_clock='0:00'`. The page still printed
"No result reported" over a "Start" chart line, because the baseball branch of
`normalize_live_game_state` kept only inning labels and served no period at
all — so the web's `authorityStoppageLabel` (#8810) had no word to read. The
soccer twin 15315470 served `espn.period = "Postponed"` and read right.
"""
import re
from datetime import datetime, timezone
from pathlib import Path

import pytest

from app.models import Event, Sport
from app.routes.events import _format_event
from app.utils.game_state import _AUTHORITY_STOPPAGE_WORDS, normalize_live_game_state

_FRONTEND_LABELS = (
    Path(__file__).resolve().parents[2] / "frontend" / "lib" / "gameTimeLabel.ts"
)


def _specimen(period="Postponed", game_clock="0:00", status="suspended"):
    """15319530's stored shape, as the live pass left it."""
    sport = Sport(id=1, key="baseball_mlb", name="MLB")
    return Event(
        id=15319530,
        sport_id=1,
        sport=sport,
        home_team_name="New York Yankees",
        away_team_name="Baltimore Orioles",
        commence_time=datetime(2026, 9, 27, 17, 5, tzinfo=timezone.utc),
        status=status,
        home_score=None,
        away_score=None,
        period=period,
        game_clock=game_clock,
        espn_id="401817103",
    )


@pytest.mark.parametrize(
    ("stored", "served"),
    [
        ("Postponed", "Postponed"),
        ("Canceled", "Canceled"),
        ("Cancelled", "Canceled"),
        ("  postponed ", "Postponed"),
    ],
)
def test_a_called_off_game_keeps_its_word_and_drops_the_filler_clock(stored, served):
    assert normalize_live_game_state("baseball_mlb", stored, "0:00") == (served, None)


def test_the_specimen_row_serves_postponed_on_the_event_payload():
    data = _format_event(_specimen())

    assert data["espn"]["period"] == "Postponed"
    assert "game_clock" not in data["espn"]


# ── Controls: everything the baseball branch did before is unchanged ─────────


@pytest.mark.parametrize(
    ("stored", "clock", "served"),
    [
        ("Top 1st", "Top 1", "Top 1st"),
        ("HT", "Bottom 2", "Bottom 2nd"),
        ("End 11", "12:00", "End 11th"),
    ],
)
def test_innings_still_serve_as_before(stored, clock, served):
    assert normalize_live_game_state("baseball_mlb", stored, clock) == (served, None)


@pytest.mark.parametrize("stored", ["Rain Delay", "Delayed", "Scheduled", "Final", "2H", None])
def test_a_word_outside_the_allowlist_still_serves_nothing(stored):
    """An exact allowlist, like the web's: an unlisted word keeps the old answer."""
    assert normalize_live_game_state("baseball_mlb", stored, "0:00") == (None, None)


def test_a_stoppage_word_in_the_clock_field_is_not_read():
    """Only the period carries ESPN's detail; the clock is never promoted."""
    assert normalize_live_game_state("baseball_mlb", None, "Postponed") == (None, None)


def test_non_baseball_passthrough_is_unchanged():
    assert normalize_live_game_state("soccer_england_league2", "Postponed", "0'") == (
        "Postponed",
        "0'",
    )


def test_strawman_the_old_rule_served_nothing_for_the_specimen():
    """What the page received before #9208: no word, so 'No result reported'."""
    from app.utils.game_state import _baseball_inning_label

    assert _baseball_inning_label("Postponed") is None
    assert _baseball_inning_label("0:00") is None


def test_the_word_set_is_the_web_allowlist():
    """Two records of one vocabulary drift; the web's map is the reader's."""
    src = _FRONTEND_LABELS.read_text()
    block = re.search(
        r"const AUTHORITY_STOPPAGE_WORDS[^{]*\{(.*?)\};", src, re.S
    )
    assert block, "AUTHORITY_STOPPAGE_WORDS moved out of gameTimeLabel.ts"
    web = dict(re.findall(r'(\w+):\s*"([^"]+)"', block.group(1)))
    assert web == _AUTHORITY_STOPPAGE_WORDS
