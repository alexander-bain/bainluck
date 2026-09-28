"""A China Open match keeps its Polymarket price on one card — #9472.

**SHIP: Van de Zandschulp v Cui, Lys v Sun, Gao v Udvardy, Cerundolo v Bu and
every match with a short-surname player keep Polymarket on the card readers see,
instead of Polymarket being pulled off it every 15 minutes.** (Pillar: MATCHING.)

Phase 1.5 asks "is this link wrong enough to break?" with ``_fuzzy_team_match``,
which cannot read a surname of <=3 letters stored alone (``Cui`` v ``Jie Cui``):
its containment floor is 4 and its acronym arm refuses a bare 3-letter surname on
purpose. Production 2026-09-28, ``market_match_receipts``:

    63068233  Botic van de Zandschulp vs. Jie Cui: Total Sets O/U 2.5
              on 15320912 `Van de Zandschulp v Cui` (tennis_atp, Kalshi)
              20:21Z phase15_revalidate cause=mislinked -> new row 15321040,
              and the whole Polymarket group followed it there.

83 tennis ``mislinked`` breaks in the 7 days to 2026-09-28; replayed through the
new helper, 82 are kept and the one left is a genuinely wrong link (a singles
line on a doubles row).

WHAT EACH TEST DEFENDS:

* the ship — the production specimens stay on their row, with the funnel count;
* 🔴 a genuinely wrong link still breaks: one player differs, singles on doubles;
* 🔴 the arm is tennis-only — a non-tennis row never consults it;
* the pure helper: both players, either orientation, sport gate, empty inputs.
"""

from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, patch

import pytest
from sqlalchemy.dialects.postgresql import ARRAY, JSONB
from sqlalchemy.ext.compiler import compiles


@compiles(JSONB, "sqlite")
def _jsonb_on_sqlite(type_, compiler, **kw):  # pragma: no cover - DDL shim
    return "TEXT"


@compiles(ARRAY, "sqlite")
def _array_on_sqlite(type_, compiler, **kw):  # pragma: no cover - DDL shim
    return "TEXT"


START = datetime(2026, 9, 29, 5, 0, tzinfo=timezone.utc)
NOW = datetime(2026, 9, 28, 20, 21, tzinfo=timezone.utc)
KALSHI_TAGS = ["provenance:source:kalshi", "provenance:unanchored"]

#: (market name, row home, row away, row sport) — production, verbatim.
SPECIMENS = [
    (
        "Botic van de Zandschulp vs. Jie Cui: Total Sets O/U 2.5",
        "Van de Zandschulp", "Cui", "tennis_atp",
    ),
    ("China Open: Eva Lys vs Xinran Sun", "Lys", "Sun", "tennis_wta"),
    (
        "Juan Manuel Cerundolo vs Yunchaokete Bu: Exact Match Score",
        "Cerundolo", "Bu", "tennis_atp",
    ),
    # Polymarket's own surname-only line against its own full-name row.
    ("Kakenova vs. Pan: Match O/U 21.5", "Albina Kakenova", "Jiayue Pan", "tennis_other"),
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

    sports = {
        key: Sport(key=key, name=key)
        for key in ("tennis_atp", "tennis_wta", "tennis_other", "basketball_nba")
    }
    session.add_all(sports.values())
    session.flush()
    return session, sports


def _row(session, sport, home, away):
    from app.models.models import Event

    e = Event(
        sport_id=sport.id, home_team_name=home, away_team_name=away,
        commence_time=START, status="scheduled", commence_time_source="kalshi",
        event_tags=list(KALSHI_TAGS),
    )
    session.add(e)
    session.flush()
    return e


def _market(session, event, name, *, category="tennis"):
    from app.models.models import FuturesMarket

    m = FuturesMarket(
        source="polymarket", external_id="0x" + str(abs(hash(name)))[:16], name=name,
        category="sports", status="open", event_id=event.id,
        sport_id=event.sport_id, llm_sport_category=category,
        group_id="polymarket:1098779",
    )
    session.add(m)
    session.commit()
    return m


async def _run_phase15(session):
    """Run the ACTUAL entry point; the scorer is pinned so it finds nothing."""
    from app.tasks import prediction_market_matching as task_mod

    stats = {
        "orphaned_snapshots_deleted": 0,
        "funnel": {"stale_relinked": 0, "mislink_fixed": 0},
    }
    link_changes = []
    with patch.object(task_mod, "_find_matching_event", new=AsyncMock(return_value=None)):
        await task_mod._phase15_revalidate(
            _AsyncShim(session), stats, NOW, lambda: 600.0, link_changes,
        )
    session.commit()
    return stats, link_changes


def _event_id(session, market):
    session.refresh(market)
    return market.event_id


# --------------------------------------------------------------------------
# The ship
# --------------------------------------------------------------------------


@pytest.mark.asyncio
@pytest.mark.parametrize("name,home,away,sport_key", SPECIMENS)
async def test_a_short_surname_link_is_kept(name, home, away, sport_key):
    """🔴 THE SHIP. The production specimen stays on the row readers see."""
    session, sports = _new_rail()
    row = _row(session, sports[sport_key], home, away)
    market = _market(session, row, name)

    stats, link_changes = await _run_phase15(session)

    assert _event_id(session, market) == row.id, (
        f"Phase 1.5 broke the link of {name!r} on {home} v {away} — "
        "Polymarket leaves the card"
    )
    assert stats["funnel"].get("phase15_tennis_names_kept") == 1
    assert not link_changes, f"a kept link published a move: {link_changes}"


# --------------------------------------------------------------------------
# A wrong link still breaks
# --------------------------------------------------------------------------


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "name,home,away",
    [
        # One player differs: Cui's OTHER match this week.
        ("Jie Cui vs. Daniel Altmaier: Total Sets O/U 2.5", "Cui", "Zverev"),
        # A singles line on a doubles row (the 1 of 83 left, production 62937255).
        (
            "Billy Harris vs. Felix Balshaw: Total Sets O/U 2.5",
            "Balshaw/Martineau", "Harris/Whitehouse",
        ),
    ],
)
async def test_a_genuinely_wrong_link_still_breaks(name, home, away):
    """🔴 Keeping needs BOTH players to agree; a doubles row never takes singles."""
    session, sports = _new_rail()
    row = _row(session, sports["tennis_other"], home, away)
    market = _market(session, row, name)

    stats, _ = await _run_phase15(session)

    assert _event_id(session, market) != row.id, (
        f"{name!r} stayed on {home} v {away} — a wrong link survived revalidation"
    )
    assert stats["funnel"].get("phase15_tennis_names_kept") is None


@pytest.mark.asyncio
async def test_a_non_tennis_row_never_consults_the_tennis_names():
    """🔴 The arm is tennis-only: the same names on a basketball row still break.

    `players_agree` would read `Cui ~ Jie Cui`, so this pins the sport gate at
    the call site, not just in the helper.
    """
    session, sports = _new_rail()
    row = _row(session, sports["basketball_nba"], "Van de Zandschulp", "Cui")
    market = _market(
        session, row, "Botic van de Zandschulp vs. Jie Cui: Total Sets O/U 2.5",
        category="basketball",
    )

    stats, _ = await _run_phase15(session)

    assert _event_id(session, market) != row.id
    assert stats["funnel"].get("phase15_tennis_names_kept") is None


# --------------------------------------------------------------------------
# The pure helper
# --------------------------------------------------------------------------


def _agree(*args):
    from app.tasks.prediction_market_matching import _tennis_link_players_agree

    return _tennis_link_players_agree(*args)


def test_the_helper_needs_both_players():
    assert _agree("tennis_atp", "Botic van de Zandschulp", "Jie Cui", "Van de Zandschulp", "Cui")
    assert not _agree("tennis_atp", "Botic van de Zandschulp", "Jie Cui", "Van de Zandschulp", "Wu")
    assert not _agree("tennis_atp", "Botic van de Zandschulp", "Jie Cui", "Norrie", "Cui")


def test_the_helper_reads_either_orientation():
    assert _agree("tennis_wta", "Xinran Sun", "Eva Lys", "Lys", "Sun")


@pytest.mark.parametrize("sport_key", [None, "", "basketball_nba", "soccer_epl"])
def test_the_helper_is_tennis_only(sport_key):
    assert not _agree(sport_key, "Eva Lys", "Xinran Sun", "Lys", "Sun")


@pytest.mark.parametrize(
    "team_a,team_b,home,away",
    [(None, "Sun", "Lys", "Sun"), ("Lys", None, "Lys", "Sun"),
     ("Lys", "Sun", None, "Sun"), ("Lys", "Sun", "Lys", "")],
)
def test_the_helper_refuses_a_missing_name(team_a, team_b, home, away):
    assert not _agree("tennis_wta", team_a, team_b, home, away)


def test_the_start_clock_is_fixed():
    """Anchors are literal instants, never derived from the wall clock (gotcha #44)."""
    assert START - NOW == timedelta(hours=8, minutes=39)
