"""#10090 decision J x `preview_from_commit` (lane1 on #11774).

SHIP. On a live game page the "seconds ago" counter never claims "confirmed"
while a newer, different price is still owed to readers, including on the
`preview_from_commit` path serving added.

`preview_from_commit` proposes a committed price's preview OUTSIDE any refresh
batch, so `ConfirmedAt.begin` never sees it: a throttled event has no batch,
and a batch already in flight commits an OLDER proposal (`LedgerRegistry.
committed` retires only ``entry.seq <= seq``), which leaves this one on
readers' screens. The venue then flicking back to the published price must not
advance ``confirmed_at`` while readers still see the preview.
"""

from __future__ import annotations

from types import SimpleNamespace

from app.utils.confirmed_at import ConfirmedAt
from tests.test_confirmed_at_10090 import STAMPED_AT, _Clock, _rows
from tests.test_preview_from_commit_10090 import (  # noqa: F401 — `r` is a fixture
    EV, HOME_LEG, drained, event, legs, proposals, r, read, returned,
)

TTL = 60.0


def _tracker(clock):
    return ConfirmedAt("polymarket", mono=lambda: clock.mono, wall=lambda: clock.wall,
                       preview_ttl_s=TTL)


def _batch(t, price, *, kind="stamped", rev=9, begun=True):
    """One refresh batch for EV whose reading blended the home leg at ``price``."""
    if begun:
        t.begin([EV])
    t.note_basis(EV, _rows(**{f"o{HOME_LEG}": price}))
    t.resolved(EV, ("stamped", price, STAMPED_AT, None, rev, "live") if kind == "stamped"
               else (kind, price))
    if kind == "stamped":
        t.published({(EV, rev)})


def _c(t):
    return t._events[EV].confirmed


def _held(t):
    return t._events[EV].held_since is not None


# ── the real composition path ────────────────────────────────────────────────

async def test_a_throttled_commit_preview_freezes_confirmed_at_on_the_real_path(r):  # noqa: F811
    """Stamped 0.46 acknowledged; the venue moves to 0.48; the flush commits
    it and `_preview_from_commit_rows` shows 0.48 with no batch (throttled);
    the venue flicks back to 0.46. Readers see 0.48: no advance."""
    clock = _Clock()
    t = _tracker(clock)
    r.receipts = SimpleNamespace(confirmed=t)
    _batch(t, "0.460000")
    clock.tick(1)
    t.note_input(EV, HOME_LEG, 0.48, clock.wall)
    before = _c(t)
    read(r, event(), legs())
    r.note_committed_rows([returned(price="0.480000")])
    await drained(r)
    assert [op["value"] for op in proposals(r.sent)] == [0.48]  # on readers' screens
    clock.tick(0.4)
    t.note_input(EV, HOME_LEG, 0.46, clock.wall)
    assert _c(t) == before
    assert _held(t)


async def test_no_proposal_no_freeze(r):  # noqa: F811
    """Strawman guard: a commit whose plan is refused proposes nothing and
    leaves the tracker as it was (an agreeing input still advances)."""
    clock = _Clock()
    t = _tracker(clock)
    r.receipts = SimpleNamespace(confirmed=t)
    _batch(t, "0.460000")
    read(r, event(status="scheduled"), legs())  # not live: no graph, no plan
    r.note_committed_rows([returned(price="0.480000")])
    await drained(r)
    assert proposals(r.sent) == []
    clock.tick(1)
    t.note_input(EV, HOME_LEG, 0.46, clock.wall)
    assert _c(t) == clock.wall


# ── the tracker: who supersedes an outside preview ───────────────────────────

def test_a_batch_in_flight_does_not_supersede_a_later_outside_preview():
    clock = _Clock()
    t = _tracker(clock)
    _batch(t, "0.580000", rev=8)
    clock.tick(1)
    t.note_input(EV, HOME_LEG, 0.60, clock.wall)
    t.begin([EV])                       # batch B takes the 0.60 commit
    clock.tick(0.2)
    t.note_input(EV, HOME_LEG, 0.62, clock.wall)
    t.previewed([EV])                   # 0.62's commit previews; B still open
    _batch(t, "0.600000", rev=9, begun=False)  # B stamps 0.60 (an older seq)
    before = _c(t)
    clock.tick(0.4)
    t.note_input(EV, HOME_LEG, 0.60, clock.wall)  # flick back; readers see 0.62
    assert _c(t) == before
    assert _held(t)


def test_a_batch_begun_after_the_outside_preview_supersedes_it():
    clock = _Clock()
    t = _tracker(clock)
    _batch(t, "0.460000")
    t.note_input(EV, HOME_LEG, 0.48, clock.wall)
    t.previewed([EV])
    for kind, rev in (("unchanged", None), ("stamped", 10)):
        clock.tick(1)
        _batch(t, "0.460000", kind=kind, rev=rev)  # its settlement retires 0.48
        clock.tick(0.5)
        t.note_input(EV, HOME_LEG, 0.46, clock.wall)
        assert _c(t) == clock.wall, kind
        t.previewed([EV])  # re-arm for the next kind


def test_an_outside_preview_freezes_only_for_its_own_lifetime():
    clock = _Clock()
    t = _tracker(clock)
    _batch(t, "0.460000")
    t.previewed([EV])
    clock.tick(TTL - 1)
    t.note_input(EV, HOME_LEG, 0.46, clock.wall)
    assert _c(t) != clock.wall
    clock.tick(2)
    t.note_input(EV, HOME_LEG, 0.46, clock.wall)
    assert _c(t) == clock.wall
    assert t._events[EV].outside is None


def test_an_outside_preview_is_written_as_a_hold_at_once():
    clock = _Clock()
    t = _tracker(clock)
    _batch(t, "0.460000")
    t.note_input(EV, HOME_LEG, 0.46, clock.wall)
    t._events[EV].written = t.report(t._events[EV], clock.wall)
    t._urgent.clear()
    t.note_input(EV, HOME_LEG, 0.48, clock.wall)
    t.note_input(EV, HOME_LEG, 0.46, clock.wall)
    t._events[EV].written = t.report(t._events[EV], clock.wall)
    t._urgent.clear()
    t.previewed([EV])
    assert EV in t._urgent
