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

The fixture is the SERVED shape of that game, read from the served payload
(`tests/fixtures/held_tail_book_floor_15336073.json`, provenance inside): each
book's recorded rows with their served `valid_until` — truncated to the minute,
not the stored stamp — and Polymarket's readings. The specimen had two books
throughout, so the truncation cannot move its count.

Route-level for the ship (the #6863 lesson: a unit guard on a helper passes just
as happily when the call site never asks it), unit-level for the count.
"""

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

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
    monkeypatch.setattr(
        "app.routes.events._sportsbook_floor_spans", lambda *a, **k: []
    )


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
# The final — the refusal does not vanish when the row turns terminal (R1)
# ---------------------------------------------------------------------------


def _terminal_event(offset, odds, status):
    event = _event(offset, status=status)
    if status == "completed":
        # Authoritative and prompt: 40 s after the last poll, so #1833 keeps it.
        event.completed_at = max(r.valid_until or r.captured_at for r in odds) + timedelta(
            seconds=40
        )
    return event


@pytest.mark.parametrize("status", ["completed", "suspended"])
async def test_a_finished_or_suspended_row_keeps_the_refusal_it_held_live(
    status, monkeypatch
):
    """lane1b R1 on 34b1cca7: a terminal row DISCARDED the open span.

    The game was refused all game, so its span is still open at the last stamp,
    and on a completed or suspended row #9081 does not withdraw. Discarding the
    span put the books back into every minute the moment the row turned
    terminal: the live line was Polymarket's, the settled line books-weighted
    again — the whole chart redrawn at the final. Held through the last stamp,
    every in-game minute is Polymarket's reading, exactly as while live.
    """
    offset = _offset()
    wp, odds = _specimen(offset)
    event = _terminal_event(offset, odds, status)
    payload = await _serve(event, wp, odds)

    whole = _line(payload, offset, since=datetime(2026, 10, 28, 16, 30, tzinfo=UTC))
    assert len(whole) > 40
    mismatched = [
        (m, v) for m, v in whole
        if v != pytest.approx(_polymarket_at_bucket_end(m), abs=1e-6)
    ]
    assert mismatched == []

    # The control carries the defect: without the floor the same terminal row
    # draws the books-weighted line in nearly every minute.
    _without_the_floor(monkeypatch)
    before = _line(
        await _serve(event, wp, odds), offset,
        since=datetime(2026, 10, 28, 16, 30, tzinfo=UTC),
    )
    assert sum(
        v != pytest.approx(_polymarket_at_bucket_end(m), abs=1e-6) for m, v in before
    ) > 40


def _narrow_tail_rows(kickoff):
    """lane1b probe 3: four books full-polled to K+60, then a #5426 narrow
    caller stamps two of them at K+62 and again at K+64."""
    odds = [
        _book(b, kickoff, kickoff + timedelta(minutes=60), 0.60)
        for b in ("draftkings", "fanduel", "betmgm", "caesars")
    ]
    odds += [
        _book(b, kickoff + timedelta(minutes=62), kickoff + timedelta(minutes=64), 0.62)
        for b in ("draftkings", "fanduel")
    ]
    wp = [_wp(kickoff + timedelta(minutes=m, seconds=5), 0.40) for m in range(65)]
    return wp, odds


def _narrow_tail_event(kickoff, wp, status):
    admitted = {"value": 0.62, "updated_at": (kickoff + timedelta(minutes=64)).isoformat()}
    event = _event(timedelta(0), betting=admitted, book_count=4, status=status)
    event.commence_time = kickoff
    event.win_probability_sources["polymarket"]["value"] = 0.40
    event.win_probability_sources["polymarket"]["updated_at"] = wp[-1].captured_at.isoformat()
    if status == "completed":
        event.completed_at = kickoff + timedelta(minutes=64, seconds=40)
    return event


@pytest.mark.parametrize("status", ["live", "completed", "suspended"])
async def test_a_narrow_tail_the_hero_counts_is_not_refused_at_the_final(
    status, monkeypatch
):
    """lane1b N1 on eea6b000: the terminal tail dropped the "counted" escape.

    The narrow caller's two-book stamps after the last full poll open a span
    still open at the last stamp. While live the hero still counts the books,
    so that span is dropped (#5426). Chosen from the terminal status alone, the
    same span was HELD through the last stamp at the final — 0.40 where the line
    had read 0.574 — a refusal the hero never made, redrawn at the final. The
    hero counting the books wins over the terminal tail, as while live.
    """
    kickoff = datetime.now(UTC).replace(second=0, microsecond=0) - timedelta(minutes=70)
    wp, odds = _narrow_tail_rows(kickoff)
    event = _narrow_tail_event(kickoff, wp, status)
    payload = await _serve(event, wp, odds)

    def tail(p):
        return [
            (x["timestamp"], x["home_probability"])
            for x in p["aggregate_line"]
            if kickoff + timedelta(minutes=62)
            <= datetime.fromisoformat(x["timestamp"])
            < kickoff + timedelta(minutes=65)
        ]

    after = tail(payload)
    _without_the_floor(monkeypatch)
    before = tail(await _serve(event, wp, odds))

    assert len(after) == 3
    assert after == before
    # The books are in the tail, so the equality is not vacuous.
    assert all(v != pytest.approx(0.40, abs=1e-6) for _, v in after)


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
    thin tail is not applied, and the line is the line it was.
    """
    offset = _offset()
    wp, odds = _specimen(offset)
    admitted = {"value": 0.19, "updated_at": odds[-1].captured_at.isoformat()}
    event = _event(offset, betting=admitted, book_count=3)
    after = await _serve(event, wp, odds)
    _without_the_floor(monkeypatch)
    before = await _serve(event, wp, odds)

    assert _body(after) == _body(before)


async def test_a_folded_event_fails_open_to_the_line_it_drew(monkeypatch):
    """lane1b R2 on 34b1cca7: the count ran on #6399's richest-row-per-book filter.

    A stale twin holds books A and B's rich pre-match history, ending five
    minutes before kickoff; the canonical row is polled every minute with A, B,
    D, E (and F from K+30). The filter picks A and B from the twin, so counted
    on the filtered rows the books stand two from K-5 to K+30 and a refusal is
    invented while every canonical poll saw four. A folded event's hero can rest
    on a sibling row, so the route fails open, as `_hero_sources` does.
    """
    from collections import Counter

    from app.utils.proven_duplicates import series_row_for_each_source

    ghost_id = _SPECIMEN_ID + 1
    kickoff = datetime.now(UTC).replace(second=0, microsecond=0) - timedelta(minutes=61)
    odds = []
    for bookmaker in ("A", "B"):
        for i in range(100):
            start = kickoff - timedelta(hours=10) + timedelta(minutes=5 * i)
            row = _book(bookmaker, start, start + timedelta(minutes=5), 0.5 + i / 1000)
            row.event_id = ghost_id
            odds.append(row)
    for minute in range(60):
        start = kickoff + timedelta(minutes=minute, seconds=7)
        for bookmaker in ("A", "B", "D", "E") + (("F",) if minute >= 30 else ()):
            odds.append(
                _book(bookmaker, start, start + timedelta(minutes=1), 0.6 + minute / 1000)
            )
    wp = [_wp(kickoff + timedelta(minutes=m, seconds=5), 0.40) for m in range(60)]

    # The hazard is real on these rows: the filtered set invents a refusal.
    chosen = series_row_for_each_source(
        Counter((r.bookmaker, r.event_id) for r in odds), _SPECIMEN_ID
    )
    filtered = [r for r in odds if chosen.get(r.bookmaker) == r.event_id]
    assert _spans(filtered, tail="counted")[-1][1] > kickoff + timedelta(minutes=29)

    async def _folded(_db, event_id, _absorbed=None):
        return [event_id, ghost_id]

    monkeypatch.setattr("app.utils.proven_duplicates.folded_series_event_ids", _folded)
    event = _event(timedelta(0))
    event.commence_time = kickoff
    event.win_probability_sources["polymarket"]["value"] = 0.40
    event.win_probability_sources["polymarket"]["updated_at"] = wp[-1].captured_at.isoformat()
    after = await _serve(event, wp, odds)
    _without_the_floor(monkeypatch)
    before = await _serve(event, wp, odds)

    assert after["aggregate_line"] and _body(after) == _body(before)


async def test_a_raise_inside_the_floor_fails_open_to_the_line_it_drew(monkeypatch):
    """lane1b P2: the withholding runs inside the floor's own fail-open guard.

    Outside it, a raise would reach the blend block's catch-all and serve
    `aggregate_line: []` — the reader loses the Bain Luck line, unlogged.
    """
    offset = _offset()
    wp, odds = _specimen(offset)
    event = _event(offset)
    _without_the_floor(monkeypatch)
    before = await _serve(event, wp, odds)

    def _boom(*_a, **_k):
        raise RuntimeError("withholding failed")

    monkeypatch.undo()
    monkeypatch.setattr("app.routes.events._withhold_refused_sportsbook_minutes", _boom)
    after = await _serve(event, wp, odds)

    assert after["aggregate_line"] and _body(after) == _body(before)


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
    kw.setdefault("tail", "withdrawn")
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
    assert _spans(odds, tail="counted") == []


def test_a_terminal_tail_holds_a_standing_refusal_through_the_last_stamp():
    """No point re-admits the books at the final: the terminal point owns the edge."""
    odds = [
        _book("a", _T, _T + timedelta(minutes=5), 0.5),
        _book("b", _T, _T + timedelta(minutes=5), 0.5),
    ]
    assert _spans(odds, tail="terminal") == [(_T, None)]


def test_a_refusal_first_counted_at_a_terminal_rows_last_stamp_is_the_terminal_points():
    """#8951's shape: three books until the last poll, which counted two."""
    odds = [
        _book("a", _T, _T + timedelta(minutes=19), 0.5),
        _book("b", _T, _T + timedelta(minutes=19), 0.5),
        _book("c", _T, _T + timedelta(minutes=18), 0.5),
    ]
    assert _spans(odds, tail="terminal") == []
    assert _spans(odds, tail="withdrawn") == [(_T + timedelta(minutes=19), None)]


def test_an_unknown_tail_is_refused_loudly():
    with pytest.raises(ValueError):
        _spans([_book("a", _T, _T + timedelta(minutes=5), 0.5)], tail="open")


def test_a_stamp_within_one_poll_of_the_trust_bound_is_not_counted():
    """lane1b M9: a row lost at the cut covers from the cut minus the tolerance.

    A stamp 10 s before the bound could be the same poll as a row the read did
    not return, so it is past the trusted span: the refusal closes on it.
    """
    bound = _T + timedelta(minutes=20)
    near = bound - timedelta(seconds=10)
    odds = [
        _book("a", _T, near, 0.5),
        _book("a", near, _T + timedelta(minutes=30), 0.6),
        _book("b", _T, _T + timedelta(minutes=30), 0.5),
    ]
    assert _spans(odds, trusted_until=bound) == [(_T, near)]


@pytest.mark.parametrize("read_cut", [None, timedelta(minutes=-50)])
async def test_a_settled_games_end_cap_bounds_the_count(read_cut, monkeypatch):
    """lane1b M10: the route passes the EARLIER of the read's cut and `end_cap`.

    Asked of the call site (the #6863 lesson): an authoritative `completed_at`
    caps the read at completed_at + 30 min, and a row captured before the cap
    can stretch past it, so no count is trusted beyond it; a truncated read is
    trusted only to its own cut, wherever that falls.
    """
    seen = []

    def _spy(rows, **kw):
        seen.append(kw)
        return []

    offset = _offset()
    wp, odds = _specimen(offset)
    event = _terminal_event(offset, odds, "completed")
    end_cap = event.completed_at + timedelta(minutes=30)
    cut = None if read_cut is None else event.completed_at + read_cut
    monkeypatch.setattr("app.routes.events._sportsbook_floor_spans", _spy)
    monkeypatch.setattr(
        "app.routes.events._snapshot_read_complete_until", lambda *_a, **_k: cut
    )
    await _serve(event, wp, odds)

    assert [kw["trusted_until"] for kw in seen] == [cut or end_cap]
    assert [kw["tail"] for kw in seen] == ["terminal"]


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
