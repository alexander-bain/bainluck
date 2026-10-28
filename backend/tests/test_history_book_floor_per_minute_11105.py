"""#11105 / #10090 — the served history line obeys ruling 051's book floor per minute.

THE SPECIMEN, measured by latency on production 2026-10-28 (390px, ordinary loads):

    /events/15336073 — JYP v Tappara, Liiga, live.

    Two sportsbooks quoted the whole game (draftkings, betrivers). Ruling 051's
    `BETTING_BOOK_FLOOR = 3` refused them, so the headline — and every live frame
    a held page appends — was Polymarket alone. The served history line still
    weighed the two books at 3.0 in every minute (#9081 withdraws them at the
    right edge only), so a page held from 17:40Z drew the frame value in minutes
    that had a frame and the sportsbook-weighted value in minutes that did not:
    17:41 0.165 beside a fresh load's 0.1744, 17:46 0.145 beside 0.1592. That
    alternation is the jagged held tail Alex reported on build 88.

The fixture is the stored shape of that game, read from the served payload
(`tests/fixtures/held_tail_book_floor_15336073.json`, provenance inside): each
book's recorded rows with their `valid_until`, and Polymarket's readings.

Route-level for the ship (the #6863 lesson: a unit guard on a helper passes just
as happily when the call site never asks it), unit-level for the count.
"""

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

import app.routes.events as events_route
from app.routes.events import (
    EVENT_HISTORY_IN_WINDOW_SNAPSHOT_CAP,
    EVENT_HISTORY_PRE_WINDOW_SNAPSHOT_CAP,
    _snapshot_read_complete_until,
    _sportsbook_floor_spans,
    get_event_odds_history,
)
from tests.test_history_end_cap_hides_every_point import _DispatchingSession

UTC = timezone.utc
_FIXTURE = json.loads(
    (Path(__file__).parent / "fixtures" / "held_tail_book_floor_15336073.json").read_text()
)
_SPECIMEN_ID = _FIXTURE["event_id"]

#: The stored read ended at 17:52:43Z. Shifted by whole minutes so the stored
#: minute boundaries survive, and so the newest stored stamp lands 17 s before
#: the route's own clock. Offset first, then truncate: no branch (gotcha #44).
_STORED_ANCHOR = datetime(2026, 10, 28, 17, 53, tzinfo=UTC)
_HELD_FROM = datetime(2026, 10, 28, 17, 40, tzinfo=UTC)

_ELIGIBLE = {
    "v": 1,
    "rule": "live_blend.admissible_as_blend_speaker@5031",
    "scope": "full_event_winner",
    "status": "verified",
}


def _offset() -> timedelta:
    return datetime.now(UTC).replace(second=0, microsecond=0) - _STORED_ANCHOR


def _at(stamp: str | None, offset: timedelta) -> datetime | None:
    return None if stamp is None else datetime.fromisoformat(stamp) + offset


_ROW_IDS = iter(range(1, 1_000_000))


def _book(bookmaker, captured, until, prob):
    return SimpleNamespace(
        id=next(_ROW_IDS),
        event_id=_SPECIMEN_ID,
        bookmaker=bookmaker,
        captured_at=captured,
        valid_until=until,
        home_win_probability=prob,
        away_win_probability=round(1.0 - prob, 4),
        home_spread=None,
        away_spread=None,
        over_under=None,
        projected_home_score=None,
        projected_away_score=None,
        home_moneyline=None,
        away_moneyline=None,
        reading_count=1,
    )


def _wp(when, prob, game_state=None):
    return SimpleNamespace(
        event_id=_SPECIMEN_ID,
        captured_at=when,
        source="polymarket",
        home_win_probability=prob,
        away_win_probability=None if prob is None else round(1.0 - prob, 4),
        draw_probability=None,
        game_state=game_state,
    )


def _specimen(offset):
    odds = [
        _book(
            r["bookmaker"],
            _at(r["captured_at"], offset),
            _at(r["valid_until"], offset),
            r["home_probability"],
        )
        for r in _FIXTURE["odds_rows"]
    ]
    wp = [
        _wp(_at(r["captured_at"], offset), r["home_probability"], r["game_state"])
        for r in _FIXTURE["polymarket_rows"]
    ]
    return wp, odds


def _event(offset, *, betting=None, book_count=2, status="live"):
    """The specimen's row: Polymarket speaks; the books are refused unless `betting`."""
    last_pm = _FIXTURE["polymarket_rows"][-1]
    bag = {
        "polymarket": {
            "value": last_pm["home_probability"],
            "updated_at": _at(last_pm["captured_at"], offset).isoformat(),
            "eligibility": dict(_ELIGIBLE),
        },
        "betting_book_count": book_count,
    }
    if betting is not None:
        bag["betting"] = betting
    return SimpleNamespace(
        id=_SPECIMEN_ID,
        status=status,
        commence_time=_at(_FIXTURE["commence_time"], offset),
        completed_at=None,
        home_team_name="JYP",
        away_team_name="Tappara",
        home_score=None,
        away_score=None,
        sport=SimpleNamespace(key="icehockey_liiga"),
        sport_id=1,
        box_score_data=None,
        win_probability_sources=bag,
        opening_home_probability=None,
        opening_away_probability=None,
    )


async def _serve(event, wp_rows, odds_rows, hours=48):
    session = _DispatchingSession(event, wp_rows, odds_rows)
    return await get_event_odds_history(
        event_id=event.id, hours=hours, response=MagicMock(headers={}), db=session
    )


def _without_the_floor(monkeypatch):
    """The pre-fix line: no per-minute spans, #9081's edge withdrawal only."""
    monkeypatch.setattr(events_route, "_sportsbook_floor_spans", lambda *a, **k: [])


def _line(payload, offset, *, since=_HELD_FROM):
    """The served line as (stored-clock minute, value), from `since`."""
    return [
        (datetime.fromisoformat(p["timestamp"]) - offset, p["home_probability"])
        for p in payload["aggregate_line"]
        if datetime.fromisoformat(p["timestamp"]) - offset >= since
    ]


def _polymarket_at_bucket_end(bucket: datetime) -> float:
    """What a held page's frame says for a minute: Polymarket's newest reading in it."""
    limit = bucket.replace(second=0, microsecond=0) + timedelta(minutes=1)
    latest = None
    for r in _FIXTURE["polymarket_rows"]:
        if datetime.fromisoformat(r["captured_at"]) < limit:
            latest = r["home_probability"]
    return latest


# ---------------------------------------------------------------------------
# The ship — held equals fresh on the specimen
# ---------------------------------------------------------------------------


async def test_the_served_line_is_the_headline_blend_in_every_held_minute():
    """After the fix a fresh load draws, minute by minute, what the frames drew."""
    offset = _offset()
    wp, odds = _specimen(offset)
    payload = await _serve(_event(offset), wp, odds)

    line = _line(payload, offset)
    assert len(line) >= 12, line
    for minute, value in line:
        assert value == pytest.approx(_polymarket_at_bucket_end(minute), abs=1e-6), (
            f"{minute:%H:%M:%S} served {value}: the refused books still speak"
        )


async def test_the_books_are_withheld_from_the_whole_game_not_only_the_held_window():
    offset = _offset()
    wp, odds = _specimen(offset)
    payload = await _serve(_event(offset), wp, odds)

    whole = _line(payload, offset, since=datetime(2026, 10, 28, 16, 30, tzinfo=UTC))
    assert len(whole) > 40
    mismatched = [
        (m, v) for m, v in whole
        if v != pytest.approx(_polymarket_at_bucket_end(m), abs=1e-6)
    ]
    assert mismatched == []


async def test_control_before_the_fix_the_route_served_what_production_served(
    monkeypatch,
):
    """The pre-fix control replays production: the fixture is the real shape.

    Every held-window minute production served (17:40-17:51) is reproduced to
    the stored 6 decimals with the floor removed — and those are the values that
    disagree with the frames, so the test above cannot pass against the old code.
    """
    _without_the_floor(monkeypatch)
    offset = _offset()
    wp, odds = _specimen(offset)
    payload = await _serve(_event(offset), wp, odds)

    got = dict(_line(payload, offset))
    stored = {
        datetime.fromisoformat(p["timestamp"]): p["home_probability"]
        for p in _FIXTURE["served_held_window"]
        if datetime.fromisoformat(p["timestamp"]) < datetime(2026, 10, 28, 17, 52, tzinfo=UTC)
    }
    assert len(stored) == 12
    for minute, value in stored.items():
        assert got[minute] == pytest.approx(value, abs=1e-6), minute
    disagreeing = [
        m for m, v in stored.items()
        if v != pytest.approx(_polymarket_at_bucket_end(m), abs=1e-6)
    ]
    assert len(disagreeing) >= 10, "the control must carry the defect it controls for"


# ---------------------------------------------------------------------------
# What must not move
# ---------------------------------------------------------------------------


def _with_more_books(odds):
    """Two more books standing all game: three or more quote every poll.

    Two, not one: betrivers first quotes at 16:33, so with one extra book the
    16:30 poll still counts two and is (correctly) refused.
    """
    first = min(r.captured_at for r in odds)
    last = max(r.valid_until or r.captured_at for r in odds)
    return [*odds, _book("fanduel", first, last, 0.19), _book("betmgm", first, last, 0.19)]


def _body(payload):
    """The line minus its live-edge point, which each call stamps at its own `now`."""
    line = payload["aggregate_line"]
    return line[:-1], line[-1]["home_probability"]


async def test_a_game_with_three_or_more_books_draws_exactly_the_line_it_drew(
    monkeypatch,
):
    offset = _offset()
    wp, odds = _specimen(offset)
    odds = _with_more_books(odds)
    admitted = {
        "value": 0.19,
        "updated_at": (odds[-1].valid_until).isoformat(),
    }
    after = await _serve(_event(offset, betting=admitted, book_count=4), wp, odds)
    _without_the_floor(monkeypatch)
    before = await _serve(_event(offset, betting=admitted, book_count=4), wp, odds)

    assert _body(after) == _body(before)
    # And it is a line the books are in, so the equality is not vacuous.
    held = _line(after, offset)
    assert any(
        v != pytest.approx(_polymarket_at_bucket_end(m), abs=1e-6) for m, v in held
    )


async def test_the_sportsbook_series_itself_is_untouched():
    """Only the blend stops hearing the books; their own line is still served."""
    offset = _offset()
    wp, odds = _specimen(offset)
    payload = await _serve(_event(offset), wp, odds)

    assert len(payload["history"]) > 40
    assert set(payload["bookmaker_history"]) == {"draftkings", "betrivers"}


async def test_a_pre_match_tail_the_hero_still_counts_keeps_its_line(monkeypatch):
    """#5426: a narrow caller can thin the tail while the hero keeps the books.

    The hero is the authority for "now": while it counts the sportsbooks, a thin
    trailing span is not applied, and the line is the line it was.
    """
    offset = _offset()
    wp, odds = _specimen(offset)
    admitted = {"value": 0.19, "updated_at": odds[-1].captured_at.isoformat()}
    event = _event(offset, betting=admitted, book_count=3)
    after = await _serve(event, wp, odds)
    _without_the_floor(monkeypatch)
    before = await _serve(event, wp, odds)

    assert _body(after) == _body(before)


# ---------------------------------------------------------------------------
# Membership flips at the minute the count crosses the floor
# ---------------------------------------------------------------------------


def _crossing_rows(t0):
    """Three books at 0.60 against Polymarket 0.40, one book dark for 10 minutes.

    fanduel is last seen at t0+10:00 and returns at t0+20:20. draftkings reprices
    at t0+12:00 — the first poll on record that counts two books — and
    betrivers at t0+15:00, inside the dark stretch. No book writes again after
    fanduel's return, and its own consensus point is keyed 20:00, BEFORE the
    poll that met the floor — so the books are heard from 20:20 to the end only
    if their return carries the consensus they stood on.
    """
    wp = [_wp(t0 + timedelta(minutes=m, seconds=5), 0.40) for m in range(0, 31)]
    odds = [
        _book("draftkings", t0 + timedelta(seconds=10), t0 + timedelta(minutes=12), 0.60),
        _book("draftkings", t0 + timedelta(minutes=12), t0 + timedelta(minutes=30), 0.61),
        _book("betrivers", t0 + timedelta(seconds=10), t0 + timedelta(minutes=15), 0.60),
        _book("betrivers", t0 + timedelta(minutes=15), t0 + timedelta(minutes=30), 0.59),
        _book("fanduel", t0 + timedelta(seconds=10), t0 + timedelta(minutes=10), 0.60),
        _book(
            "fanduel", t0 + timedelta(minutes=20, seconds=20), t0 + timedelta(minutes=30), 0.60
        ),
    ]
    return wp, odds


async def test_membership_flips_at_the_minute_the_count_crosses_three():
    t0 = datetime.now(UTC).replace(second=0, microsecond=0) - timedelta(minutes=31)
    offset = timedelta(0)
    wp, odds = _crossing_rows(t0)
    event = _event(offset)  # the hero has refused the books (2 now… 3 at the end)
    event.commence_time = t0 - timedelta(minutes=30)
    event.win_probability_sources["polymarket"]["value"] = 0.40
    event.win_probability_sources["polymarket"]["updated_at"] = wp[-1].captured_at.isoformat()
    payload = await _serve(event, wp, odds)

    by_minute = {
        round((datetime.fromisoformat(p["timestamp"]) - t0).total_seconds() / 60, 3):
            p["home_probability"]
        for p in payload["aggregate_line"]
    }
    for minute in (0, 5, 11):
        assert by_minute[minute] > 0.45, (minute, "three books stood: they speak")
    for minute in (12, 13, 15, 19):
        assert by_minute[minute] == pytest.approx(0.40), (minute, "two books: refused")
    for minute in (20, 25, 29):
        assert by_minute[minute] > 0.45, (minute, "the third book returned at 20:20")


# ---------------------------------------------------------------------------
# The count
# ---------------------------------------------------------------------------

_T = datetime(2026, 10, 28, 17, 0, tzinfo=UTC)


def _spans(odds, **kw):
    kw.setdefault("trusted_from", None)
    kw.setdefault("trusted_until", None)
    kw.setdefault("trailing", True)
    return _sportsbook_floor_spans(odds, **kw)


def test_one_poll_stamps_each_book_milliseconds_apart_and_still_counts_three():
    """A book first seen by a poll must cover its siblings' stamps of that poll."""
    odds = [
        _book("a", _T, _T + timedelta(minutes=5), 0.5),
        _book("b", _T + timedelta(milliseconds=3), _T + timedelta(minutes=5), 0.5),
        _book("c", _T + timedelta(milliseconds=6), _T + timedelta(minutes=5), 0.5),
    ]
    assert _spans(odds) == []


def test_a_book_that_reprices_is_still_one_book():
    """Old row ends where the new one opens: two rows, one vote."""
    odds = [
        _book("a", _T, _T + timedelta(minutes=2), 0.5),
        _book("a", _T + timedelta(minutes=2), _T + timedelta(minutes=5), 0.6),
        _book("b", _T, _T + timedelta(minutes=5), 0.5),
    ]
    assert _spans(odds) == [(_T, None)]


def test_a_refusal_holds_until_the_floor_is_met_again():
    odds = [
        _book("a", _T, _T + timedelta(minutes=9), 0.5),
        _book("b", _T, _T + timedelta(minutes=9), 0.5),
        _book("c", _T + timedelta(minutes=6), _T + timedelta(minutes=9), 0.5),
    ]
    assert _spans(odds) == [(_T, _T + timedelta(minutes=6))]


def test_a_book_quoting_no_home_probability_is_not_counted():
    odds = [
        _book("a", _T, _T + timedelta(minutes=5), 0.5),
        _book("b", _T, _T + timedelta(minutes=5), 0.5),
        _book("c", _T, _T + timedelta(minutes=5), 0.5),
    ]
    odds[2].home_win_probability = None
    assert _spans(odds) == [(_T, None)]


def test_an_open_tail_is_applied_only_when_asked():
    odds = [_book("a", _T, _T + timedelta(minutes=5), 0.5)]
    assert _spans(odds, trailing=False) == []


def test_no_count_is_taken_where_a_row_the_read_dropped_could_stand():
    """Truncated read / end cap: a span reaching the bound closes on it."""
    odds = [
        _book("a", _T, _T + timedelta(minutes=30), 0.5),
        _book("b", _T, _T + timedelta(minutes=30), 0.5),
        _book("a", _T + timedelta(minutes=30), _T + timedelta(minutes=40), 0.6),
    ]
    bound = _T + timedelta(minutes=20)
    assert _spans(odds, trusted_until=bound) == [(_T, bound)]


def test_no_count_is_taken_before_the_window_can_see_every_row():
    odds = [
        _book("a", _T, _T + timedelta(minutes=30), 0.5),
        _book("b", _T, _T + timedelta(minutes=30), 0.5),
        _book("b", _T + timedelta(minutes=30), _T + timedelta(minutes=40), 0.6),
    ]
    assert _spans(odds, trusted_from=_T + timedelta(minutes=1)) == [
        (_T + timedelta(minutes=30), None)
    ]


def test_a_full_half_of_the_read_is_where_completeness_ends():
    split = _T + timedelta(days=1)
    pre = [
        SimpleNamespace(captured_at=_T + timedelta(seconds=i))
        for i in range(EVENT_HISTORY_PRE_WINDOW_SNAPSHOT_CAP)
    ]
    post = [SimpleNamespace(captured_at=split + timedelta(seconds=1))]
    assert _snapshot_read_complete_until([*pre, *post], split_at=split) == pre[-1].captured_at
    assert _snapshot_read_complete_until([*pre[:-1], *post], split_at=split) is None

    full_post = [
        SimpleNamespace(captured_at=split + timedelta(seconds=i))
        for i in range(EVENT_HISTORY_IN_WINDOW_SNAPSHOT_CAP)
    ]
    assert (
        _snapshot_read_complete_until(full_post, split_at=split)
        == full_post[-1].captured_at
    )
    assert _snapshot_read_complete_until(full_post[:-1], split_at=None) is None
