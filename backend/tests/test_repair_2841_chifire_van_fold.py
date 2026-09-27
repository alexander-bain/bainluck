"""#2841 — the Chicago Fire v Vancouver fold's refusals, driven with plain values.

What the repair WRITES is SQL, and the real-Postgres gate owns that
(`tests/integration/test_repair_2841_chifire_van_fold_apply_restore_pg.py`).
This file owns what it must REFUSE: every departure from the measured state,
and every way the two providers' own records could fail to place the match at
the kept row's kickoff. A refusal writes nothing, so each one here is a case
where the old behaviour — two cards for one match — is the safe answer.
"""

import importlib.util
import sys
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

_SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"


def _load():
    sys.path.insert(0, str(_SCRIPTS))
    spec = importlib.util.spec_from_file_location(
        "repair_2841_unit", _SCRIPTS / "repair_2841_chifire_van_fold.py"
    )
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


m = _load()


def _rows(**over):
    ghost = dict(
        id=m.GHOST, sport_key=m.SPORT_KEY, home_team_id=m.HOME_TEAM_ID,
        away_team_id=m.AWAY_TEAM_ID, status="scheduled", commence_time=m.GHOST_KICKOFF,
        espn_id=m.ESPN_ID, external_id=m.GHOST_ODDS_ID,
        event_tags='["league:mls", "sport:soccer"]',
    )
    canon = dict(
        id=m.CANON, sport_key=m.SPORT_KEY, home_team_id=m.HOME_TEAM_ID,
        away_team_id=m.AWAY_TEAM_ID, status="scheduled", commence_time=m.CANON_KICKOFF,
        espn_id=None, external_id=m.CANON_ODDS_ID,
        event_tags='["provenance:source:odds_api", "provenance:unanchored"]',
    )
    for key, value in over.items():
        who, col = key.split("__")
        (ghost if who == "g" else canon)[col] = value
    return {m.GHOST: ghost, m.CANON: canon}


def _market(**over):
    row = dict(id=m.GAME_MARKET, event_id=m.GHOST, source="kalshi",
               external_id=m.GAME_TICKER, name="Chicago Fire vs Vancouver", status="open")
    row.update(over)
    return row


@dataclass(frozen=True)
class _Team:
    name: str


@dataclass
class _Espn:
    date: datetime
    time_valid: bool = True
    home_team: _Team = _Team("Chicago Fire FC")
    away_team: _Team = _Team("Vancouver Whitecaps")


LISTED = {m.CANON_ODDS_ID, "some-other-mls-game"}


class TestTheMeasuredStatePasses:
    """Controls: production's shape as read 2026-09-27 ~06:30Z clears every gate."""

    def test_rows(self):
        assert m.rows_refusal(_rows(), _market(), [m.GHOST]) is None

    def test_evidence(self):
        assert m.evidence_refusal(_Espn(m.CANON_KICKOFF), LISTED) is None

    def test_a_naive_espn_clock_is_read_as_utc(self):
        naive = m.CANON_KICKOFF.replace(tzinfo=None)
        assert m.evidence_refusal(_Espn(naive), LISTED) is None

    def test_clock_a_week_out(self):
        assert m.lead_refusal(m.CANON_KICKOFF - timedelta(days=9)) is None

    def test_the_label_is_the_one_the_read_side_hides(self):
        from app.services.anchor_channel import duplicate_tag

        assert m.TAG == duplicate_tag(m.CANON)


class TestTheRowsMustBeAsMeasured:
    @pytest.mark.parametrize(
        "over, fragment",
        [
            ({"g__sport_key": "soccer_other"}, "not 'soccer_usa_mls'"),
            ({"c__home_team_id": 99}, "names teams 99/"),
            ({"g__status": "live"}, "'live'"),
            ({"c__status": "completed"}, "'completed'"),
            ({"g__event_tags": '["provenance:duplicate-of:1"]'}, "already carries"),
            ({"c__event_tags": '["provenance:duplicate-of:1"]'}, "already carries"),
            ({"g__commence_time": m.CANON_KICKOFF}, "kickoff moved"),
            ({"c__commence_time": m.GHOST_KICKOFF}, "kickoff moved"),
            ({"g__espn_id": "999"}, "holds ESPN '999'"),
            ({"c__espn_id": "761660"}, "already holds ESPN"),
            ({"g__external_id": "reissued-again"}, "Odds API ids changed"),
        ],
    )
    def test_a_moved_row_refuses(self, over, fragment):
        refusal = m.rows_refusal(_rows(**over), _market(), [m.GHOST])
        assert refusal and fragment in refusal

    def test_a_missing_row_refuses(self):
        rows = _rows()
        del rows[m.CANON]
        assert "is gone" in m.rows_refusal(rows, _market(), [m.GHOST])

    def test_espn_held_by_a_third_row_refuses(self):
        refusal = m.rows_refusal(_rows(), _market(), [m.GHOST, 777])
        assert "held by" in refusal

    @pytest.mark.parametrize(
        "market, fragment",
        [
            (None, "is gone"),
            (_market(external_id="KXMLSGAME-26OCT06CHIVANX"), "kalshi:KXMLSGAME-26OCT06CHIVANX"),
            (_market(source="polymarket"), "polymarket:"),
            (_market(event_id=m.CANON), f"linked to {m.CANON}"),
            (_market(status="resolved"), "'resolved'"),
        ],
    )
    def test_a_moved_market_refuses(self, market, fragment):
        refusal = m.rows_refusal(_rows(), market, [m.GHOST])
        assert refusal and fragment in refusal


class TestBothProvidersMustPlaceItAtTheKeptRow:
    def test_espn_silent(self):
        assert "did not answer" in m.evidence_refusal(None, LISTED)

    def test_espn_placeholder_time(self):
        refusal = m.evidence_refusal(_Espn(m.CANON_KICKOFF, time_valid=False), LISTED)
        assert "placeholder" in refusal

    def test_espn_agrees_with_the_stale_row(self):
        assert "not 2026-10-07" in m.evidence_refusal(_Espn(m.GHOST_KICKOFF), LISTED)

    def test_espn_names_another_match(self):
        other = _Espn(m.CANON_KICKOFF, home_team=_Team("Chicago Fire FC"),
                      away_team=_Team("Seattle Sounders FC"))
        assert "seattle" in m.evidence_refusal(other, LISTED)

    def test_espn_home_and_away_swapped(self):
        swapped = _Espn(m.CANON_KICKOFF, home_team=_Team("Vancouver Whitecaps"),
                        away_team=_Team("Chicago Fire FC"))
        assert m.evidence_refusal(swapped, LISTED) is not None

    def test_odds_schedule_unread(self):
        assert "not read" in m.evidence_refusal(_Espn(m.CANON_KICKOFF), None)

    def test_odds_no_longer_lists_the_kept_row(self):
        assert "no longer lists" in m.evidence_refusal(_Espn(m.CANON_KICKOFF), {"x"})

    def test_odds_still_lists_the_stale_row(self):
        both = LISTED | {m.GHOST_ODDS_ID}
        assert "not a re-issue" in m.evidence_refusal(_Espn(m.CANON_KICKOFF), both)


class TestTheClockAndTheApp:
    def test_inside_the_last_hour_refuses(self):
        assert m.lead_refusal(m.CANON_KICKOFF - timedelta(minutes=59)) is not None

    def test_after_kickoff_refuses(self):
        assert m.lead_refusal(m.CANON_KICKOFF + timedelta(hours=2)) is not None

    def test_an_hour_and_a_minute_out_passes(self):
        assert m.lead_refusal(m.CANON_KICKOFF - timedelta(minutes=61)) is None

    @pytest.mark.parametrize("app", [None, "bainluck", "bainluck-staging"])
    def test_refuses_off_the_heavy_app(self, monkeypatch, app):
        if app is None:
            monkeypatch.delenv("HEROKU_APP_NAME", raising=False)
        else:
            monkeypatch.setenv("HEROKU_APP_NAME", app)
        assert m.wrong_app_refusal() is not None

    def test_runs_on_the_heavy_app(self, monkeypatch):
        monkeypatch.setenv("HEROKU_APP_NAME", "bainluck-heavy")
        assert m.wrong_app_refusal() is None


def test_the_pinned_ids_match_the_measured_rows():
    """The docstring's measurement and the constants are one statement."""
    assert (m.GHOST, m.CANON, m.ESPN_ID, m.GAME_MARKET) == (14969919, 15316563, "761660", 62383846)
    assert m.GHOST_KICKOFF == datetime(2026, 10, 6, 18, 0, tzinfo=timezone.utc)
    assert m.CANON_KICKOFF == datetime(2026, 10, 7, 0, 30, tzinfo=timezone.utc)
    assert m.GAME_TICKER == "KXMLSGAME-26OCT06CHIVAN"
