"""#8586: a live match priced by Kalshi keeps its price until the match ends.

THE DEFECT. #2644 (CAL-P1127) taught ``derive_resolution_window`` to take the
venue's ``expected_expiration_time`` when ``close_time`` is only a pad
(``close == expiration``). For a championship future that estimate is the end.
For ONE match or fight it is the START. Venue-read 2026-09-25 09:00Z while
Medvedev–Royer (ATP Hangzhou) was live::

    KXATPMATCH-26SEP25MEDROY   status active   result ''
    close_time               2026-10-09T05:00Z
    expiration_time          2026-10-09T05:00Z   (the same pad twice)
    expected_expiration_time 2026-09-25T08:00Z   (the scheduled start)

``min()`` stored 08:00Z as ``resolution_date``; ``mark_resolved_futures`` ran at
08:15Z and resolved both of the match's Kalshi markets, and the event page's
headline read "No price" mid-match. 11 markets that day, 51 on 9/20.

Two layers, both tested here:

* the root — a single contest (game ticker or dated-fixture ticker) keeps the
  pad, as before #2644, and settles on the venue's own status;
* the sweep, the second writer of ``resolution_date``, applies the same rule.

The third layer — ``mark_resolved_futures`` never date-resolves a market whose
linked event is live or not yet started — needs a real Postgres and lives in
``tests/integration/test_mark_resolved_spares_live_events_8586_pg.py``.

No clock is read anywhere in this file (gotcha #44).
"""

from __future__ import annotations

import ast
import asyncio
import pathlib
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Optional

import pytest

from app.utils.kalshi_resolution_window import derive_resolution_window


def _ts(s: str) -> datetime:
    return datetime.fromisoformat(s.replace("Z", "+00:00"))


@dataclass
class Leg:
    close_time: Optional[datetime] = None
    expiration_time: Optional[datetime] = None
    expected_expiration_time: Optional[datetime] = None


PAD = _ts("2026-10-09T05:00:00Z")
START = _ts("2026-09-25T08:00:00Z")

#: The specimen, as the venue served it at 09:00Z (two legs, one per player).
MEDVEDEV_ROYER = [Leg(PAD, PAD, START), Leg(PAD, PAD, START)]

#: The #2644 shape the tie-break exists for — must keep working.
SUPER_BOWL_27 = [
    Leg(
        _ts("2029-02-13T23:30:00Z"),
        _ts("2029-02-13T23:30:00Z"),
        _ts("2027-02-14T23:30:00Z"),
    )
]


class TestTheRule:
    def test_a_single_contest_keeps_the_pad_not_the_start(self):
        w = derive_resolution_window(MEDVEDEV_ROYER, single_contest=True)
        assert w.resolution_date == PAD, (
            "a live match's resolution_date became its START — "
            "mark_resolved_futures resolves it minutes into play"
        )
        assert w.used_expected_expiration is False
        assert w.declined_expected_for_single_contest is True
        assert w.expiration_time == PAD

    def test_without_the_flag_the_specimen_reproduces_the_defect(self):
        """Strawman: the input really is the #8586 shape, not a pass-by-accident."""
        w = derive_resolution_window(MEDVEDEV_ROYER)
        assert w.resolution_date == START
        assert w.used_expected_expiration is True
        assert w.declined_expected_for_single_contest is False

    def test_a_future_still_takes_the_estimate(self):
        """#2644 is untouched for what it was built for."""
        w = derive_resolution_window(SUPER_BOWL_27, single_contest=False)
        assert w.resolution_date == _ts("2027-02-14T23:30:00Z")
        assert w.used_expected_expiration is True

    def test_a_real_close_on_a_single_contest_is_still_taken(self):
        """A settled match's close has collapsed to the settlement instant; the
        flag only matters where the tie-break would have fired."""
        settled = _ts("2026-09-25T10:12:00Z")
        w = derive_resolution_window(
            [Leg(settled, PAD, START)], single_contest=True
        )
        assert w.resolution_date == settled
        assert w.declined_expected_for_single_contest is False

    def test_the_flag_changes_nothing_when_the_gate_is_closed(self):
        """No estimate: identical answer with or without the flag."""
        legs = [Leg(PAD, PAD, None)]
        assert derive_resolution_window(legs, single_contest=True) == (
            derive_resolution_window(legs)
        )


class TestTheTickersTheCallersClassify:
    """The callers decide ``single_contest`` as ``game ticker OR dated fixture``.
    UFC is the reason for the OR: ``KXUFCFIGHT`` is a game ticker but not a
    dated-fixture shape (``FIGHT`` is not in that vocabulary)."""

    @staticmethod
    def _single(ticker):
        from app.tasks.kalshi import _is_dated_fixture_ticker, _is_kalshi_game_ticker

        return bool(_is_kalshi_game_ticker(ticker)) or _is_dated_fixture_ticker(ticker)

    @pytest.mark.parametrize(
        "ticker",
        [
            "KXATPMATCH-26SEP25MEDROY",
            "KXATPEXACTMATCH-26SEP25MEDROY",
            "KXWTAMATCH-26SEP25ANDFER",
            "KXATPDOUBLES-26SEP25CHOHOZ",
            "KXUFCFIGHT-26SEP26GALDUM",
            "KXMLBGAME-26SEP25NYYBAL",
        ],
    )
    def test_the_specimens_are_single_contests(self, ticker):
        assert self._single(ticker), ticker

    @pytest.mark.parametrize("ticker", ["KXSB-27", "KXWTA-26USO"])
    def test_the_2644_futures_are_not(self, ticker):
        assert not self._single(ticker), ticker


# --- the sweep, driven end to end against a faked venue ---------------------


class _Session:
    def __init__(self, recorder):
        self.recorder = recorder

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False

    async def execute(self, statement, params=None):
        self.recorder.append((str(statement), params))

        class _R:
            def all(self):
                return []

            def first(self):
                return None

        return _R()

    async def commit(self):
        return None


class _LiveMatchVenue:
    """The exact 09:00Z payload shape: active, no result, pad close, start estimate."""

    async def get_event(self, ticker, with_nested_markets=True):
        leg = {
            "status": "active",
            "result": "",
            "close_time": "2026-10-09T05:00:00Z",
            "expiration_time": "2026-10-09T05:00:00Z",
            "expected_expiration_time": "2026-09-25T08:00:00Z",
        }
        return {"markets": [dict(leg), dict(leg)]}

    async def close(self):
        return None


NOW = datetime(2026, 9, 25, 9, 0, tzinfo=timezone.utc)


def _swept_date(ticker):
    from app.tasks import kalshi_resolution_sweep as sweep

    recorder: list = []
    row = (62164610, ticker, None, NOW - timedelta(hours=1), 5)
    asyncio.run(
        sweep.run_backfill(
            session_maker=lambda: _Session(recorder),
            client_factory=_LiveMatchVenue,
            apply=True,
            now=NOW,
            rows=[row],
        )
    )
    updates = [
        p for s, p in recorder
        if s.strip().upper().startswith("UPDATE") and p and "resolution_date" in p
    ]
    assert len(updates) == 1, recorder
    return updates[0]["resolution_date"]


class TestTheSweepAppliesTheSameRule:
    def test_the_sweep_writes_the_pad_for_the_live_match(self):
        assert _swept_date("KXATPMATCH-26SEP25MEDROY") == PAD

    def test_the_sweep_still_writes_the_estimate_for_a_future(self):
        """Control on the same payload: only the ticker differs, so the ticker
        is what the sweep's decision turns on."""
        assert _swept_date("KXWTA-26USO") == START


# --- every writer of resolution_date decides single_contest -----------------


def _calls_without_the_flag():
    import app as _app

    root = pathlib.Path(_app.__file__).resolve().parent
    missing, total = [], 0
    for path in sorted(root.rglob("*.py")):
        try:
            tree = ast.parse(path.read_text())
        except (SyntaxError, UnicodeDecodeError):  # pragma: no cover
            continue
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            f = node.func
            name = f.id if isinstance(f, ast.Name) else getattr(f, "attr", None)
            if name != "derive_resolution_window":
                continue
            total += 1
            if not any(k.arg == "single_contest" for k in node.keywords):
                missing.append(f"{path.relative_to(root)}:{node.lineno}")
    return missing, total


def test_every_call_site_decides_single_contest():
    """A caller that omits the flag silently re-arms #8586 for its rows.

    AST, not a text grep — the identifier is spelled in imports and prose, so a
    substring scan would stay green after a call lost its keyword.
    """
    missing, total = _calls_without_the_flag()
    assert total >= 3, f"expected the three known writers, found {total} calls"
    assert missing == [], (
        "derive_resolution_window called without single_contest= at "
        f"{missing}; a match written there resolves at its start (#8586)"
    )
