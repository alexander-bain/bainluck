"""A soccer match's chart keeps its Polymarket line — #9504.

**SHIP: SC Braga v Sporting CP, Argentinos Juniors v Tigre and every soccer
match with Polymarket's derivative books keep their Polymarket line on the
chart, instead of losing its whole history about once an hour.** (Pillar:
MATCHING.)

Two defects, both in Phase 1.5 (`_phase15_revalidate`):

1. **The delete was source-wide.** Moving one market off an event ran
   ``DELETE win_prob_snapshots WHERE event_id = E AND source = 'polymarket'`` —
   every Polymarket row on the event, the match line's included. Every row
   carries ``game_state.market_id`` (78,625 of 78,625 in the 48h to
   2026-09-29 02:35Z), so the delete now takes the departing markets' rows only.

2. **It broke a link the forward path had just made.** #6134 taught the forward
   path to take the market type off a derivative's team_b before searching
   (``matchup_for_link_search``: "Sporting CP - Exact Score" -> "Sporting CP"),
   so the books link to their fixture. Phase 1.5 verified against the RAW name,
   called every one "mislinked", unlinked it, and the forward path linked it
   again the next cycle. Production, ``market_link_changes`` 24h to 00:15Z
   9/29: 684 Phase 1.5 Polymarket unlinks over 65 events; for 62583713 (Braga
   Exact Score) ``pass2_general`` re-linked at 00:05:00 what Phase 1.5 unlinked
   at 23:50:00. Replayed over the 21 unlinks after 00:00Z (the tennis half was
   already cured by #9472): 21 of 21 are kept under the search copy.

WHAT EACH TEST DEFENDS:

* the ship — the production derivative specimens stay linked, no link change;
* 🔴 a genuinely wrong derivative (another fixture's book) still breaks;
* 🔴 when it breaks, the match line's rows survive and only its own go;
* 🔴 the relink arm moves only what moves — the market and its group siblings;
* the pure delete helper: scoped by id, unstamped rows go, empty ids is a no-op.
"""

from datetime import datetime, timezone
from unittest.mock import AsyncMock, patch

import pytest
from sqlalchemy.dialects.postgresql import ARRAY, JSONB
from sqlalchemy.ext.compiler import compiles


@compiles(JSONB, "sqlite")
def _jsonb_on_sqlite(type_, compiler, **kw):  # pragma: no cover - DDL shim
    return "JSON"


@compiles(ARRAY, "sqlite")
def _array_on_sqlite(type_, compiler, **kw):  # pragma: no cover - DDL shim
    return "TEXT"


START = datetime(2026, 10, 9, 19, 15, tzinfo=timezone.utc)
NOW = datetime(2026, 9, 28, 23, 50, tzinfo=timezone.utc)
SNAP_AT = datetime(2026, 9, 28, 16, 0, tzinfo=timezone.utc)

#: (market name, row home, row away) — production, verbatim (#9504).
DERIVATIVE_SPECIMENS = [
    ("SC Braga vs. Sporting CP - Exact Score", "Braga", "Sporting Lisbon"),
    ("SC Braga vs. Sporting CP - Halftime Result", "Braga", "Sporting Lisbon"),
    ("SC Braga vs. Sporting CP - First Team to Score", "Braga", "Sporting Lisbon"),
    ("SC Braga vs. Sporting CP - Second Half Result", "Braga", "Sporting Lisbon"),
    ("AA Argentinos Juniors vs. CA Tigre - Total Corners", "Argentinos Juniors", "CA Tigre BA"),
    ("AA Argentinos Juniors vs. CA Tigre - Exact Score", "Argentinos Juniors", "CA Tigre BA"),
]


class _AsyncShim:
    """Async surface over a real sync session (no aiosqlite in this sandbox)."""

    def __init__(self, session):
        self._s = session

    async def execute(self, statement, *a, **k):
        return self._s.execute(statement, *a, **k)

    def add(self, obj):
        self._s.add(obj)

    async def commit(self):
        self._s.commit()

    async def flush(self):
        self._s.flush()


def _new_rail():
    from sqlalchemy import create_engine
    from sqlalchemy import event as sa_event
    from sqlalchemy.orm import Session

    from app.models.models import (
        Base, Event, FuturesMarket, Sport, Team, WinProbSnapshot,
    )

    engine = create_engine("sqlite://")
    Base.metadata.create_all(
        engine,
        tables=[
            Sport.__table__, Event.__table__, Team.__table__,
            FuturesMarket.__table__, WinProbSnapshot.__table__,
        ],
    )
    session = Session(engine, expire_on_commit=False)

    @sa_event.listens_for(session, "loaded_as_persistent")
    def _reattach_utc(_sess, instance):  # pragma: no cover - test rail
        for attr, value in list(instance.__dict__.items()):
            if isinstance(value, datetime) and value.tzinfo is None:
                instance.__dict__[attr] = value.replace(tzinfo=timezone.utc)

    sport = Sport(key="soccer_portugal_primeira_liga", name="Primeira Liga")
    session.add(sport)
    session.flush()
    return session, sport


def _row(session, sport, home, away, *, external_id=None):
    from app.models.models import Event

    e = Event(
        sport_id=sport.id, home_team_name=home, away_team_name=away,
        commence_time=START, status="scheduled", external_id=external_id,
    )
    session.add(e)
    session.flush()
    return e


_ids = iter(range(1_086_500, 1_087_000))


def _market(session, event, name, *, group_id=None, group_type="negrisk"):
    from app.models.models import FuturesMarket

    ext = str(next(_ids))
    m = FuturesMarket(
        source="polymarket", external_id=ext, name=name,
        category="championship", status="open", event_id=event.id,
        sport_id=event.sport_id, llm_sport_category="soccer",
        group_id=group_id or f"polymarket:{ext}", group_type=group_type,
    )
    session.add(m)
    session.commit()
    return m


def _snap(session, event, market_id, minute, *, source="polymarket"):
    from datetime import timedelta

    from app.models.models import WinProbSnapshot

    gs = {"market_id": market_id} if market_id is not None else None
    session.add(WinProbSnapshot(
        event_id=event.id, source=source,
        home_win_probability=0.4, away_win_probability=0.3,
        captured_at=SNAP_AT + timedelta(minutes=minute), game_state=gs,
    ))
    session.commit()


def _rows(session, event, source="polymarket"):
    """``(market_id or None)`` for every row of ``source`` left on the event."""
    from app.models.models import WinProbSnapshot

    out = []
    for s in session.query(WinProbSnapshot).filter_by(event_id=event.id, source=source):
        out.append((s.game_state or {}).get("market_id"))
    return sorted(out, key=lambda v: (v is None, v or 0))


async def _run_phase15(session, better=None):
    """Run the ACTUAL entry point, with the scorer pinned to ``better``."""
    from app.tasks import prediction_market_matching as task_mod

    stats = {
        "orphaned_snapshots_deleted": 0,
        "funnel": {"stale_relinked": 0, "mislink_fixed": 0},
    }
    link_changes = []
    with patch.object(task_mod, "_find_matching_event", new=AsyncMock(return_value=better)):
        await task_mod._phase15_revalidate(
            _AsyncShim(session), stats, NOW, lambda: 600.0, link_changes,
        )
    session.commit()
    return stats, link_changes


def _event_id(session, market):
    session.refresh(market)
    return market.event_id


# --------------------------------------------------------------------------
# The ship (defect 2): the derivative stays on its fixture
# --------------------------------------------------------------------------


@pytest.mark.asyncio
@pytest.mark.parametrize("name,home,away", DERIVATIVE_SPECIMENS)
async def test_a_derivative_book_stays_on_its_fixture(name, home, away):
    """🔴 THE SHIP. The production derivative keeps the link the forward path made."""
    session, sport = _new_rail()
    row = _row(session, sport, home, away)
    line = _market(session, row, name.split(" - ")[0])
    book = _market(session, row, name)
    _snap(session, row, line.id, 0)
    _snap(session, row, line.id, 1)

    stats, link_changes = await _run_phase15(session)

    assert _event_id(session, book) == row.id, (
        f"Phase 1.5 broke the link of {name!r} on {home} v {away}; the forward "
        "path will link it again next cycle and the unlink repeats"
    )
    assert _event_id(session, line) == row.id
    assert not link_changes, f"a kept link published a move: {link_changes}"
    assert stats["funnel"]["mislink_fixed"] == 0
    assert _rows(session, row) == [line.id, line.id]


# --------------------------------------------------------------------------
# A wrong link still breaks — and takes only its own rows (defect 1)
# --------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_another_fixtures_book_still_breaks():
    """🔴 Stripping the market type is not a pass: the teams must still agree."""
    session, sport = _new_rail()
    row = _row(session, sport, "Braga", "Sporting Lisbon")
    wrong = _market(session, row, "Mirassol vs. Red Bull Bragantino - Exact Score")

    stats, link_changes = await _run_phase15(session)

    assert _event_id(session, wrong) is None
    assert stats["funnel"]["mislink_fixed"] == 1
    assert [c for c in link_changes if c.market_id == wrong.id]


@pytest.mark.asyncio
async def test_unlinking_one_market_keeps_the_match_lines_rows():
    """🔴 DEFECT 1. The departing market's rows go; the match line's stay.

    The old delete was ``event_id = E AND source = 'polymarket'`` and would
    leave ``[]`` here — Braga's chart drawn from sportsbooks only.
    """
    session, sport = _new_rail()
    row = _row(session, sport, "Braga", "Sporting Lisbon")
    line = _market(session, row, "SC Braga vs. Sporting CP")
    wrong = _market(session, row, "Mirassol vs. Red Bull Bragantino - Exact Score")
    for minute in range(3):
        _snap(session, row, line.id, minute)
    _snap(session, row, wrong.id, 10)
    _snap(session, row, wrong.id, 11)
    _snap(session, row, 999, 0, source="kalshi")  # another source: untouched

    stats, _ = await _run_phase15(session)

    assert _event_id(session, wrong) is None
    assert _event_id(session, line) == row.id
    assert _rows(session, row) == [line.id] * 3, (
        "unlinking one Polymarket market erased another market's chart rows"
    )
    assert stats["orphaned_snapshots_deleted"] == 2
    assert _rows(session, row, source="kalshi") == [999]


@pytest.mark.asyncio
async def test_the_relink_arm_moves_only_what_moves():
    """🔴 An auto-created row's market moves with its group; a bystander stays.

    The group-follow UPDATE carries ``polymarket_sub_market`` siblings of the
    moving market; their rows leave with it. A market of another group on the
    same row is not moving and keeps its curve.
    """
    session, sport = _new_rail()
    phantom = _row(session, sport, "Braga", "Sporting CP - Exact Score", external_id="pm_1086527")
    real = _row(session, sport, "Braga", "Sporting Lisbon")
    mover = _market(
        session, phantom, "SC Braga vs. Sporting CP",
        group_id="polymarket:1086500", group_type="polymarket_sub_market",
    )
    sibling = _market(
        session, phantom, "Will the match end in a draw?",
        group_id="polymarket:1086500", group_type="polymarket_sub_market",
    )
    bystander = _market(session, phantom, "Some other question")
    _snap(session, phantom, mover.id, 0)
    _snap(session, phantom, sibling.id, 1)
    _snap(session, phantom, bystander.id, 2)
    _snap(session, phantom, None, 3)  # unattributable: goes with the mover

    better = {"event_id": real.id, "sport_id": sport.id, "score": 90}
    from app.tasks import prediction_market_matching as task_mod

    with patch.object(
        task_mod, "_check_duplicate_kalshi_linkage_reason",
        new=AsyncMock(return_value=None),
    ), patch.object(
        task_mod, "_check_polymarket_fixture_reason",
        new=AsyncMock(return_value=None),
    ):
        # Only the mover is judged: neither other name parses to a matchup, so
        # the sibling moves ONLY by the group-follow UPDATE — its rows must go
        # in the mover's delete or nothing ever takes them.
        stats, _ = await _run_phase15(session, better=better)

    assert _event_id(session, mover) == real.id
    assert _event_id(session, sibling) == real.id
    assert _event_id(session, bystander) == phantom.id
    assert _rows(session, phantom) == [bystander.id], (
        "the relink deleted a staying market's rows, or left a departing one's"
    )


# --------------------------------------------------------------------------
# The pure delete helper
# --------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_the_helper_deletes_by_id_and_takes_unstamped_rows():
    from app.tasks.prediction_market_matching import _delete_departing_market_snapshots

    session, sport = _new_rail()
    row = _row(session, sport, "Braga", "Sporting Lisbon")
    _snap(session, row, 1, 0)
    _snap(session, row, 2, 1)
    _snap(session, row, 2, 2)
    _snap(session, row, None, 3)
    _snap(session, row, 2, 4, source="kalshi")

    n = await _delete_departing_market_snapshots(_AsyncShim(session), row.id, "polymarket", [2])
    session.commit()

    assert n == 3
    assert _rows(session, row) == [1]
    assert _rows(session, row, source="kalshi") == [2]


@pytest.mark.asyncio
async def test_the_helper_with_no_ids_deletes_nothing():
    """No departing market means nothing departs — never the old source-wide sweep."""
    from app.tasks.prediction_market_matching import _delete_departing_market_snapshots

    session, sport = _new_rail()
    row = _row(session, sport, "Braga", "Sporting Lisbon")
    _snap(session, row, 1, 0)
    _snap(session, row, None, 1)

    assert await _delete_departing_market_snapshots(
        _AsyncShim(session), row.id, "polymarket", [None],
    ) == 0
    assert _rows(session, row) == [1, None]


def test_no_source_wide_snapshot_delete_is_left_in_phase15():
    """🔴 Static: Phase 1.5 deletes win-prob rows only through the scoped helper."""
    import inspect

    from app.tasks.prediction_market_matching import _phase15_revalidate

    src = inspect.getsource(_phase15_revalidate)
    assert "delete(WinProbSnapshot)" not in src
    assert src.count("_delete_departing_market_snapshots(") == 2
