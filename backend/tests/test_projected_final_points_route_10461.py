"""#10461 route half: `/history`'s per-sportsbook points carry recorded-vs-carry provenance.

`get_event_odds_history` keeps an in-window snapshot at its capture minute and
re-stamps a pre-cutoff snapshot (still valid at the cutoff) at the cutoff
minute. Each point now also carries `kind` and `observed_at` from
`bookmaker_history_provenance`. These guards pin the three things the wiring
promised: expired rows stay excluded, the re-stamp is named `synthetic` with
its ORIGINAL capture time, and a response stripped of the two additive keys is
byte-identical to what the route served without them.
"""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone


import app.routes.events as events_module
from tests.test_history_one_vote_per_bookmaker_6771 import _live_event, _row, _serve

UTC = timezone.utc
# The event page's own window. Kickoff (an hour ago) sits inside it, so the route
# takes its windowed branch, the one that carries pre-cutoff snapshots.
HOURS = 48
ADDITIVE = ("kind", "observed_at")


def _rows(now):
    cutoff_estimate = now - timedelta(hours=HOURS)
    carried = _row(
        "draftkings", 0.41, at=cutoff_estimate - timedelta(minutes=37, seconds=12)
    )
    carried.valid_until = None  # still current — the route carries it to the cutoff
    expired = _row("fanduel", 0.44, at=cutoff_estimate - timedelta(minutes=50))
    expired.valid_until = cutoff_estimate - timedelta(
        minutes=20
    )  # gone before the window
    recorded = _row("draftkings", 0.43, at=now - timedelta(minutes=30, seconds=5))
    return carried, expired, recorded


def _event(now):
    return _live_event(now)  # live, kickoff an hour ago


def _distinct(points):
    # The rig answers both halves of the route's split read with every row, so
    # each point is served twice; the order of first appearance is the route's.
    seen, out = set(), []
    for point in points:
        key = json.dumps(point, sort_keys=True, default=str)
        if key not in seen:
            seen.add(key)
            out.append(point)
    return out


class _AcceptsRealDatetimes(type):
    def __instancecheck__(cls, obj):
        return isinstance(obj, datetime)


def _frozen_clock(at):
    """`events.datetime` with `now()` pinned, so two serves stamp the same instant."""

    class _Frozen(datetime, metaclass=_AcceptsRealDatetimes):
        @classmethod
        def now(cls, tz=None):
            return at if tz is None else at.astimezone(tz)

    return _Frozen


def _strip(payload):
    out = json.loads(json.dumps(payload, default=str))
    for points in out["bookmaker_history"].values():
        for point in points:
            for key in ADDITIVE:
                point.pop(key, None)
    return out


async def test_carry_is_synthetic_with_its_original_capture_and_recorded_stays_recorded():
    now = datetime.now(UTC)
    carried, _expired, recorded = _rows(now)
    payload = await _serve(_event(now), list(_rows(now)), hours=HOURS)

    points = _distinct(payload["bookmaker_history"]["draftkings"])
    assert [p["kind"] for p in points] == ["synthetic", "recorded"]
    synthetic, real = points
    # Displayed where the route always put it (the cutoff minute)…
    assert (
        synthetic["timestamp"]
        != carried.captured_at.replace(second=0, microsecond=0).isoformat()
    )
    # …but it names when the snapshot was actually captured, seconds and all.
    assert synthetic["observed_at"] == carried.captured_at.isoformat()
    assert real["observed_at"] == recorded.captured_at.isoformat()
    assert (
        real["timestamp"]
        == recorded.captured_at.replace(second=0, microsecond=0).isoformat()
    )


async def test_expired_pre_cutoff_rows_are_still_excluded():
    now = datetime.now(UTC)
    payload = await _serve(_event(now), list(_rows(now)), hours=HOURS)
    assert "fanduel" in payload["bookmaker_history"], "the book key is still built"
    assert payload["bookmaker_history"]["fanduel"] == []


async def test_additive_keys_are_appended_after_every_existing_key():
    now = datetime.now(UTC)
    payload = await _serve(_event(now), list(_rows(now)), hours=HOURS)
    for point in payload["bookmaker_history"]["draftkings"]:
        assert list(point)[-2:] == list(ADDITIVE)


async def test_stripped_response_is_byte_identical_to_the_response_without_provenance(
    monkeypatch,
):
    now = datetime.now(UTC)
    rows = list(_rows(now))
    event = _event(now)
    # The payload carries wall-clock stamps (`time_domain.end`); pin them so the
    # comparison below is byte-exact rather than field-filtered.
    monkeypatch.setattr(events_module, "datetime", _frozen_clock(now))
    with_provenance = await _serve(event, rows, hours=HOURS)

    monkeypatch.setattr(events_module, "bookmaker_history_provenance", lambda **_: None)
    legacy = await _serve(event, rows, hours=HOURS)

    # Strawman: the two responses DO differ before stripping, so the parity is not vacuous.
    assert json.dumps(with_provenance, default=str) != json.dumps(legacy, default=str)
    assert all(
        not (set(ADDITIVE) & set(p))
        for pts in legacy["bookmaker_history"].values()
        for p in pts
    ), "a refusal adds no key at all"
    assert json.dumps(_strip(with_provenance)) == json.dumps(
        json.loads(json.dumps(legacy, default=str))
    )
