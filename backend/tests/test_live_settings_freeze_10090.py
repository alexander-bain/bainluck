"""#10090 settings freeze (2026-11-02): every value production ran as a Heroku var is the code default.

One row per var in docs/live-settings.md whose decision is "Default". Each row reads the setting through the
code's own reader with the var unset and asserts production's value by name. A change to any of these defaults
is a PR against docs/live-settings.md and this table, never a bare `config:set`.
"""

from pathlib import Path

import pytest

from app.tasks import (
    live_blend_refresh as lbr,
    polymarket_open_contracts as poc,
    polymarket_ws as pmws,
    speed_switches as sw,
    venue_poll_30s,
    venue_poll_pm_clob,
    ws_consumer_sessions as wcs,
)
from app.utils import blend_preview, preview_reservations, sports_market_metadata_reuse

DOC = Path(__file__).resolve().parents[2] / "docs" / "live-settings.md"

#: var -> (production value on 2026-11-01, read the code default with the var unset)
FROZEN = {
    "SPEED_SWITCH_TODAY_PREVIEW_AT_RECEIPT": (1, lambda: sw.SPECS["preview_at_receipt"]["today"]),
    "SPEED_SWITCH_TODAY_HANDOVER_FRESH": (1, lambda: sw.SPECS["handover_fresh"]["today"]),
    "SPEED_SWITCH_TODAY_OWED_PAST_WITHDRAWAL": (1, lambda: sw.SPECS["owed_past_withdrawal"]["today"]),
    "SPEED_SWITCH_TRIALS": (True, sw.trials_enabled),
    "PREVIEW_AT_RECEIPT_VENUES": (
        {"kalshi": True, "polymarket": True},
        lambda: {v: lbr._receipt_venue(v) for v in ("kalshi", "polymarket")},
    ),
    "POLYMARKET_WS_OPEN_SCOPE": ("slate", poc.open_contract_scope),
    "PM_WS_PROPS_TO_POLL": (True, poc.props_to_poll_enabled),
    "VENUE_POLL_30S_ENABLED": (frozenset({"polymarket"}), lambda: venue_poll_30s.enabled_venues({})),
    "VENUE_POLL_30S_PM_SOURCE": ("clob", lambda: venue_poll_pm_clob.pm_source({})),
    "PM_WS_REPEAT_SKIP_MS": (3.0, pmws._repeat_skip_window_s),
    "PM_WS_UPCOMING_HOURS": (1, pmws._upcoming_hours_env),
    "PM_WS_BLEND_FLOOR_SECONDS": (5.0, lambda: pmws.PM_WS_BLEND_FLOOR_DEFAULT_S),
    "STAMP_HELD_OWED_FRESH": (True, lbr.stamp_held_owed_fresh_on),
    "STAMP_WRITE_UNDER_QUEUED": (9, lbr.stamp_write_under_queued),
    "FEED_SPORTS_METADATA_REUSE": (True, sports_market_metadata_reuse.reuse_enabled),
    "LIVE_BLEND_PREVIEW_RESERVATIONS": (
        (96, 48, 192, 128, 448, 112),
        lambda: preview_reservations.ReservationPolicy.configured().limits,
    ),
    "LIVE_BLEND_PREVIEW_MAX_UNCOMMITTED_S": (180.0, blend_preview._max_uncommitted_s),
}

#: Read once at import: the module constant is the default whenever the var is unset in this process.
FROZEN_AT_IMPORT = {
    "FRESH_FLUSH_PENDING_ATTEMPTS": (3, lambda: lbr.FRESH_FLUSH_PENDING_ATTEMPTS),
    "ADMITTED_STAMP_BATCH": (4, lambda: lbr.ADMITTED_STAMP_BATCH),
    "ADMITTED_LIVE_BATCH": (4, lambda: lbr.ADMITTED_LIVE_BATCH),
    "WS_CONSUMER_POOL_PRE_PING": (False, lambda: wcs.CONSUMER_POOL_PRE_PING),
}


@pytest.mark.parametrize("var", sorted(FROZEN))
def test_the_code_default_is_productions_value(var, monkeypatch):
    monkeypatch.delenv(var, raising=False)
    production, read = FROZEN[var]
    assert read() == production, var


@pytest.mark.parametrize("var", sorted(FROZEN_AT_IMPORT))
def test_the_import_time_default_is_productions_value(var):
    import os

    assert os.environ.get(var) is None, f"{var} is set in the test environment; the default is unreadable"
    production, read = FROZEN_AT_IMPORT[var]
    assert read() == production, var


def test_every_frozen_var_is_a_default_row_in_live_settings():
    rows = {
        line.split("|")[1].strip().strip("`"): line
        for line in DOC.read_text().splitlines()
        if line.startswith("| `")
    }
    for var in {**FROZEN, **FROZEN_AT_IMPORT}:
        assert var in rows, var
        assert "Default" in rows[var].split("|")[4], var


def test_trial_switches_still_turn_a_default_off(monkeypatch):
    """A frozen default stays a switch: its documented off value still reads off."""
    for var, off in (("PM_WS_PROPS_TO_POLL", "0"), ("STAMP_HELD_OWED_FRESH", "0"),
                     ("FEED_SPORTS_METADATA_REUSE", "0"), ("SPEED_SWITCH_TRIALS", "0")):
        monkeypatch.setenv(var, off)
    assert not poc.props_to_poll_enabled()
    assert not lbr.stamp_held_owed_fresh_on()
    assert not sports_market_metadata_reuse.reuse_enabled()
    assert not sw.trials_enabled()
