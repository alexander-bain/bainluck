"""#11105 / #10090 — the served line's betting input is the headline's consensus.

THE SPECIMEN, latency on production 2026-10-29 (native build-91 hold, 23:15-23:18Z):

    /events/15338028 — CBJ @ CAR, NHL, live.

    18 sportsbooks stood all through 23:15. The served line's `betting` input was
    that minute's `history` row, the MEAN of the 9 books that wrote a row in it
    (0.7097); the headline's `betting` was the MEDIAN of every book the poll saw
    (0.7032, `_ingest_event_odds`). The 23:15 bucket drew 0.70167, a +0.6 pt
    out-and-back beside frames of 0.6954 / 0.6934 that the headline never showed.
    The book floor (#11691) cannot see it: 9, 12, 6 and 7 books are all >= 3.

The fixture is the served shape of that game (`tests/fixtures/
served_betting_full_book_15338028.json`, provenance inside). Before the fix it
reproduces production's served line exactly, minute for minute, so the red here
is the defect production served, not a model of it.
"""

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from statistics import median
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

import app.utils.aggregation as aggregation
from app.routes.events import (
    _BOOK_FLOOR_POLL_TOLERANCE,
    _full_book_consensus_points,
    get_event_odds_history,
)
from app.utils.aggregation import TimestampedProb
from tests.test_history_end_cap_hides_every_point import _DispatchingSession

UTC = timezone.utc
_FIXTURE = json.loads(
    (Path(__file__).parent / "fixtures" / "served_betting_full_book_15338028.json").read_text()
)
_P = datetime.fromisoformat

_ELIGIBLE = {
    "evidence_status": "verified",
    "verified_scope": "full_event_winner",
    "contract_version": "live_blend.admissible_as_blend_speaker@5031",
}


def _newest_stored() -> datetime:
    rows = _FIXTURE["odds_rows"]
    stamps = [_P(r["captured_at"]) for r in rows]
    stamps += [_P(r["valid_until"]) for r in rows if r["valid_until"]]
    stamps += [_P(p["captured_at"]) for v in _FIXTURE["win_prob_rows"].values() for p in v]
    return max(stamps)


#: Shifted by whole minutes so the stored minute boundaries survive and the newest
#: stored stamp lands under a minute before the route's clock. Offset first, then
#: truncate: no branch (gotcha #44).
_ANCHOR = (_newest_stored() + timedelta(minutes=1)).replace(second=0, microsecond=0)


def _offset() -> timedelta:
    return datetime.now(UTC).replace(second=0, microsecond=0) - _ANCHOR


def _specimen(offset):
    def at(stamp):
        return None if stamp is None else _P(stamp) + offset

    ids = iter(range(1, 1_000_000))
    odds = [
        SimpleNamespace(
            id=next(ids),
            event_id=_FIXTURE["event_id"],
            bookmaker=r["bookmaker"],
            captured_at=at(r["captured_at"]),
            valid_until=at(r["valid_until"]),
            home_win_probability=r["home_probability"],
            away_win_probability=(
                None if r["home_probability"] is None else round(1 - r["home_probability"], 4)
            ),
            home_spread=None,
            away_spread=None,
            over_under=None,
            projected_home_score=None,
            projected_away_score=None,
            home_moneyline=None,
            away_moneyline=None,
            reading_count=1,
        )
        for r in _FIXTURE["odds_rows"]
    ]
    wp = [
        SimpleNamespace(
            event_id=_FIXTURE["event_id"],
            captured_at=at(p["captured_at"]),
            source=source,
            home_win_probability=p["home_probability"],
            away_win_probability=round(1 - p["home_probability"], 4),
            draw_probability=None,
            game_state=p["game_state"],
        )
        for source, points in _FIXTURE["win_prob_rows"].items()
        for p in points
    ]
    bag = {}
    for source, points in _FIXTURE["win_prob_rows"].items():
        bag[source] = {
            "value": points[-1]["home_probability"],
            "updated_at": at(points[-1]["captured_at"]).isoformat(),
            **({} if source == "stat_model" else _ELIGIBLE),
        }
    bag["betting"] = {"value": 0.6803, "updated_at": (_ANCHOR + offset).isoformat()}
    bag["betting_book_count"] = 18
    event = SimpleNamespace(
        id=_FIXTURE["event_id"],
        status="live",
        commence_time=at(_FIXTURE["commence_time"]),
        completed_at=None,
        home_team_name=_FIXTURE["home_team"],
        away_team_name=_FIXTURE["away_team"],
        home_score=0,
        away_score=0,
        sport=SimpleNamespace(key="icehockey_nhl"),
        sport_id=1,
        box_score_data=None,
        win_probability_sources=bag,
        opening_home_probability=None,
        opening_away_probability=None,
    )
    return event, wp, odds


async def _serve(monkeypatch, *, fixed=True):
    """The served payload and the `betting` input the blend was given, by stored minute."""
    offset = _offset()
    event, wp, odds = _specimen(offset)
    if not fixed:
        monkeypatch.setattr(
            "app.routes.events._full_book_consensus_points", lambda points, *a, **k: points
        )
    seen = {}
    real = aggregation.compute_aggregated_probability

    def spy(sources, *args, **kwargs):
        seen["betting"] = {
            (p.timestamp - offset).strftime("%H:%M"): p.home_probability
            for p in sources.get("betting", [])
        }
        return real(sources, *args, **kwargs)

    monkeypatch.setattr(aggregation, "compute_aggregated_probability", spy)
    payload = await get_event_odds_history(
        event_id=event.id,
        hours=48,
        response=MagicMock(headers={}),
        db=_DispatchingSession(event, wp, odds),
    )
    line = {
        (_P(p["timestamp"]) - offset).strftime("%H:%M"): p["home_probability"]
        for p in payload["aggregate_line"]
    }
    return line, seen["betting"]


def _stored_full_book_median(at: str) -> tuple[int, float]:
    """Every book's newest stored row at `at`, while it stands — computed by hand."""
    instant = _P(at)
    newest = {}
    for r in _FIXTURE["odds_rows"]:
        if _P(r["captured_at"]) <= instant:
            if r["bookmaker"] not in newest or _P(r["captured_at"]) > _P(
                newest[r["bookmaker"]]["captured_at"]
            ):
                newest[r["bookmaker"]] = r
    probs = [
        r["home_probability"]
        for r in newest.values()
        if r["home_probability"]
        and _P(r["valid_until"] or r["captured_at"]) + _BOOK_FLOOR_POLL_TOLERANCE >= instant
    ]
    return len(probs), round(median(probs), 4)


# ---------------------------------------------------------------------------
# The ship — on the specimen
# ---------------------------------------------------------------------------


async def test_the_pre_fix_route_reproduces_the_line_production_served(monkeypatch):
    """The fixture IS the specimen: the old route redraws production's line exactly."""
    line, betting = await _serve(monkeypatch, fixed=False)
    served = {_P(t).strftime("%H:%M"): v for t, v in _FIXTURE["served_aggregate_line"]}
    # 23:25 is the live edge, pinned against the clock the read ran on.
    compared = [m for m in served if "23:00" <= m < "23:25"]
    assert len(compared) == 25
    assert [line.get(m) for m in compared] == [served[m] for m in compared]
    assert line["23:15"] == 0.70167
    # The defect: the input was the mean of the 9 books that wrote a row.
    assert betting["23:15"] == 0.7097
    assert ["2026-10-29T23:15:00+00:00", 0.7097, 9] in _FIXTURE["served_history"]


async def test_the_betting_input_is_the_headline_consensus_at_each_minutes_end(monkeypatch):
    """Each minute weighs the median of every standing book, the headline's value."""
    _line, betting = await _serve(monkeypatch)
    # The headline at 23:14 (native's pick): 0.6847 over 18 books.
    assert _stored_full_book_median("2026-10-29T23:14:00.843+00:00") == (18, 0.6847)
    assert betting["23:14"] == 0.6847
    # The 23:15 poll (23:15:04) moved 9 of 18 books; the headline is all 18.
    assert _stored_full_book_median("2026-10-29T23:15:04.288+00:00") == (18, 0.7032)
    assert betting["23:15"] == 0.7032
    assert betting["23:16"] == _stored_full_book_median("2026-10-29T23:16:54.838+00:00")[1]
    assert betting["23:17"] == _stored_full_book_median("2026-10-29T23:17:59.367+00:00")[1]


async def test_the_23_15_bucket_no_longer_overshoots_the_frames(monkeypatch):
    before, _ = await _serve(monkeypatch, fixed=False)
    monkeypatch.undo()
    after, _ = await _serve(monkeypatch)
    frames = _FIXTURE["frames_last_in_minute"]
    assert after["23:15"] == 0.699395
    for minute in ("23:15", "23:17"):
        assert abs(after[minute] - frames[minute]) < abs(before[minute] - frames[minute])
    # Minutes with no history row stay minutes with no betting point: only values move.
    assert set(after) == set(before)


# ---------------------------------------------------------------------------
# The rule, unit-level
# ---------------------------------------------------------------------------

_M = datetime(2026, 10, 29, 23, 15, tzinfo=UTC)


def _row(book, captured, until, prob):
    return SimpleNamespace(
        bookmaker=book, captured_at=captured, valid_until=until, home_win_probability=prob
    )


def _point(stamp=_M, prob=0.5):
    return TimestampedProb(timestamp=stamp, home_probability=prob)


def _consensus(points, rows, trusted_from=None, trusted_until=None):
    return _full_book_consensus_points(
        points, rows, trusted_from=trusted_from, trusted_until=trusted_until
    )


def test_a_book_that_reconfirmed_is_counted_at_its_standing_price():
    poll = _M + timedelta(seconds=40)
    rows = [
        # Repriced in the minute.
        _row("a", poll, None, 0.70),
        # Re-confirmed at the poll a few ms later: no new row, only valid_until.
        _row("b", _M - timedelta(minutes=5), poll + timedelta(milliseconds=8), 0.60),
        _row("c", _M - timedelta(minutes=9), poll + timedelta(minutes=3), 0.62),
    ]
    [out] = _consensus([_point(prob=0.70)], rows)
    assert out.home_probability == 0.62
    assert out.timestamp == _M


def test_a_poll_whose_stamps_scatter_by_milliseconds_counts_each_book_once():
    poll = _M + timedelta(seconds=40)
    rows = [
        _row("a", poll, None, 0.70),
        # Last seen by the same poll, stamped 20 ms before the newest stamp.
        _row("b", _M - timedelta(minutes=5), poll - timedelta(milliseconds=20), 0.60),
        _row("c", poll - timedelta(milliseconds=10), None, 0.66),
    ]
    [out] = _consensus([_point()], rows)
    assert out.home_probability == 0.66


def test_a_book_gone_from_the_feed_is_not_carried():
    poll = _M + timedelta(seconds=50)
    rows = [
        _row("a", poll, None, 0.70),
        _row("b", poll - timedelta(milliseconds=5), None, 0.66),
        # Last seen 4 minutes ago: the poll did not see it.
        _row("gone", _M - timedelta(minutes=8), _M - timedelta(minutes=4), 0.10),
    ]
    [out] = _consensus([_point()], rows)
    assert out.home_probability == 0.68


def test_the_newest_row_is_the_books_price_even_without_a_probability():
    poll = _M + timedelta(seconds=30)
    rows = [
        _row("a", poll, None, 0.70),
        _row("b", poll, None, 0.66),
        # Superseded at the poll by a row with no moneyline: the old price is gone.
        _row("c", _M - timedelta(minutes=3), poll, 0.10),
        _row("c", poll, None, None),
    ]
    [out] = _consensus([_point()], rows)
    assert out.home_probability == 0.68


def test_the_value_is_read_at_the_minutes_end_not_its_start():
    rows = [
        _row("a", _M - timedelta(minutes=2), _M + timedelta(seconds=45), 0.40),
        _row("a", _M + timedelta(seconds=45), None, 0.80),
        _row("b", _M - timedelta(minutes=2), _M + timedelta(seconds=45), 0.80),
        _row("c", _M - timedelta(minutes=2), _M + timedelta(seconds=45), 0.82),
    ]
    [out] = _consensus([_point()], rows)
    assert out.home_probability == 0.80
    # A stamp exactly on the next minute belongs to the next minute (#8349).
    rows.append(_row("d", _M + timedelta(minutes=1), None, 0.99))
    rows.append(_row("e", _M + timedelta(minutes=1), None, 0.99))
    [out] = _consensus([_point()], rows)
    assert out.home_probability == 0.80


def test_an_untrusted_instant_leaves_the_point_as_it_was():
    poll = _M + timedelta(seconds=30)
    rows = [_row("a", poll, None, 0.70), _row("b", poll, None, 0.60)]
    kept = _point(prob=0.55)
    assert _consensus([kept], rows, trusted_from=poll + timedelta(seconds=1)) == [kept]
    assert _consensus([kept], rows, trusted_until=poll + timedelta(seconds=10)) == [kept]
    [out] = _consensus([kept], rows, trusted_until=poll + _BOOK_FLOOR_POLL_TOLERANCE * 2)
    assert out.home_probability == 0.65


def test_no_standing_book_and_no_stamp_leave_the_point_as_it_was():
    kept = _point(prob=0.55)
    assert _consensus([kept], []) == [kept]
    # The minute's last stamp is a row with no moneyline; the only priced book
    # was last seen nine minutes earlier.
    stale = [
        _row("a", _M - timedelta(minutes=10), _M - timedelta(minutes=9), 0.7),
        _row("b", _M + timedelta(seconds=10), None, None),
    ]
    assert _consensus([kept], stale) == [kept]


def test_a_withdrawal_marker_is_not_revalued():
    marker = TimestampedProb(timestamp=_M, home_probability=None)
    rows = [_row("a", _M + timedelta(seconds=5), None, 0.7)] * 3
    assert _consensus([marker], rows) == [marker]


@pytest.mark.parametrize("folded", [False, True])
async def test_a_folded_event_fails_open_to_the_row_line(monkeypatch, folded):
    """Folded series fail open, as the floor and `_hero_sources` do."""
    calls = []
    real = _full_book_consensus_points

    def spy(*args, **kwargs):
        calls.append(1)
        return real(*args, **kwargs)

    monkeypatch.setattr("app.routes.events._full_book_consensus_points", spy)
    if folded:
        # A tagged pair: the series reads two rows (the twin holds no odds rows).
        async def fold(db, event_id, *args, **kwargs):
            return [event_id, event_id + 1]

        monkeypatch.setattr("app.utils.proven_duplicates.folded_series_event_ids", fold)
    await _serve(monkeypatch)
    assert bool(calls) is (not folded)

