"""#9600 — a singles match's markets never land on a doubles match's row.

## What a reader saw, on production

`/events/15320104` (2026-09-29 10:55Z, 390px) is the doubles match
**Balshaw/Martineau v Harris/Whitehouse**. It showed the SINGLES match Harris v
Balshaw: "Billy Harris vs Felix Balshaw · Felix Balshaw wins Set 1 >99%" under
Additional Markets, and a Games map built from the singles over/under lines. The
singles match had no row of its own.

## Why

`_fuzzy_team_match` reads containment. Kalshi's singles market "Harris vs
Balshaw" (KXATPCHALLENGERMATCH-26SEP29HARBAL) found "Harris" inside
"Harris/Whitehouse" and "Balshaw" inside "Balshaw/Martineau", so the two-sided
gate passed (receipt: `sides_matched: 2`). The matched path then swept all
eleven Polymarket legs of the singles match onto the row, and the group join
(#9450 / #8430), which reads no names, kept pulling them back each time Phase 1.5
unlinked one: 62937255 was unlinked 9 times in 24 hours.

## What this file gates

* the pure shape test, including the club names a slash on ONE side belongs to;
* the forward scorer, Phase 1.5 and the group-sibling resolver, each driven for
  real, each with a control that the correct link still happens.

Population replay (production, links on rows dated now-10d..now+10d whose market
or both row sides carry a slash, 1,936 two-sided): old-yes/new-no = 9, every one
a singles/doubles crossing; new-yes/old-no = 0.
"""

from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest
from sqlalchemy.dialects.postgresql import ARRAY, JSONB
from sqlalchemy.ext.compiler import compiles

from app.tasks import prediction_market_matching as pmm
from app.tasks.prediction_market_matching import _score_candidates
from app.utils.prediction_market_matching import (
    _names_both_sides,
    extract_matchup,
    pair_shape,
    pair_shapes_disagree,
)


@compiles(JSONB, "sqlite")
def _jsonb_on_sqlite(type_, compiler, **kw):  # pragma: no cover - DDL shim
    return "TEXT"


@compiles(ARRAY, "sqlite")
def _array_on_sqlite(type_, compiler, **kw):  # pragma: no cover - DDL shim
    return "TEXT"


DOUBLES_HOME, DOUBLES_AWAY = "Balshaw/Martineau", "Harris/Whitehouse"
KALSHI_SINGLES = "Harris vs Balshaw"
PM_SINGLES_LEG = "Harris vs. Balshaw: Match O/U 22.5"
PM_SINGLES_MONEYLINE = "Mouilleron-Le-Captif: Billy Harris vs Felix Balshaw"
KALSHI_DOUBLES = "Balshaw / Martineau vs Harris / Whitehouse"
DOUBLES_START = datetime(2026, 9, 29, 8, 0, tzinfo=timezone.utc)
NOW = datetime(2026, 9, 29, 6, 0, tzinfo=timezone.utc)
GROUP = "polymarket:1088318"


# --------------------------------------------------------------------------
# The pure helpers
# --------------------------------------------------------------------------


class TestPairShape:
    @pytest.mark.parametrize("a,b,expected", [
        ("Balshaw/Martineau", "Harris/Whitehouse", True),
        ("Balshaw / Martineau", "Harris / Whitehouse", True),
        ("Harris", "Balshaw", False),
        # A slash on one side only is a club, not a pair: no shape.
        ("Bodø/Glimt", "Kristiansund BK", None),
        ("Iowa Cubs", "Scranton/Wilkes-Barre RailRiders", None),
        # The venue's over/under label is not a pair.
        ("Harris", "Balshaw: Match O/U 22.5", False),
    ])
    def test_shape(self, a, b, expected):
        assert pair_shape(a, b) is expected

    def test_the_specimen_disagrees_both_ways(self):
        assert pair_shapes_disagree("Harris", "Balshaw", DOUBLES_HOME, DOUBLES_AWAY)
        assert pair_shapes_disagree(
            "Adeshina / Pawlikowska", "Fedorova / Hatouka", "Pawlikowska", "Hatouka",
        )

    def test_a_club_slash_never_disagrees(self):
        """Control: a one-sided slash says nothing about shape, so the name
        test alone decides (Bodø/Glimt's own fixtures must keep linking)."""
        assert not pair_shapes_disagree(
            "Bodo Glimt", "Kristiansund", "Bodø/Glimt", "Kristiansund BK",
        )
        assert not pair_shapes_disagree(
            "Bodø/Glimt", "Borussia Dortmund", "Bodø/Glimt", "Borussia Dortmund",
        )


class TestNamesBothSides:
    def test_singles_names_do_not_pass_a_doubles_row(self):
        """🔴 The receipt's `sides_matched: 2`, refused."""
        assert not _names_both_sides("Harris", "Balshaw", DOUBLES_HOME, DOUBLES_AWAY)

    def test_the_old_gate_really_did_pass_the_specimen(self):
        """The strawman: without the shape test this file would prove nothing."""
        from app.utils.prediction_market_matching import _fuzzy_team_match

        assert _fuzzy_team_match("Harris", DOUBLES_AWAY)
        assert _fuzzy_team_match("Balshaw", DOUBLES_HOME)

    def test_the_laver_cup_singles_does_not_pass_its_doubles_row(self):
        assert not _names_both_sides(
            "Alcaraz", "Fritz", "Alcaraz / Mensik", "Bublik / Fritz",
        )

    def test_the_rows_own_pairs_pass_under_either_separator(self):
        """Control: the doubles market still names its own doubles row."""
        assert _names_both_sides(
            "Balshaw / Martineau", "Harris / Whitehouse", DOUBLES_HOME, DOUBLES_AWAY,
        )

    def test_singles_names_still_pass_a_singles_row(self):
        assert _names_both_sides("Harris", "Balshaw", "Balshaw", "Billy Harris")


# --------------------------------------------------------------------------
# The forward scorer
# --------------------------------------------------------------------------


def _event(eid, home, away, commence=DOUBLES_START):
    return SimpleNamespace(
        id=eid,
        sport=SimpleNamespace(key="tennis_other"),
        home_team_name=home,
        away_team_name=away,
        commence_time=commence,
        status="scheduled",
        external_id=None,
        sport_id=1,
    )


def _pm_market(name):
    return SimpleNamespace(
        external_id="0xspecimen", name=name, source="polymarket",
        llm_sport_category="tennis", commence_time=None, market_metadata={},
        group_id=None,
    )


class TestTheForwardScorer:
    def test_the_singles_leg_links_to_no_doubles_row(self):
        """🔴 THE SHIP. The only candidate is the doubles row; now nothing is chosen."""
        result = _score_candidates(
            [_event(15320104, DOUBLES_HOME, DOUBLES_AWAY)],
            extract_matchup(PM_SINGLES_LEG), _pm_market(PM_SINGLES_LEG), NOW,
        )
        assert result is None, (
            f"'{PM_SINGLES_LEG}' linked to {result and result['event_id']} — "
            "the singles match's prices land on the doubles page"
        )

    def test_the_singles_leg_picks_the_singles_row_beside_the_doubles_one(self):
        result = _score_candidates(
            [
                _event(15320104, DOUBLES_HOME, DOUBLES_AWAY),
                _event(99, "Felix Balshaw", "Billy Harris"),
            ],
            extract_matchup(PM_SINGLES_LEG), _pm_market(PM_SINGLES_LEG), NOW,
        )
        assert result is not None and result["event_id"] == 99

    def test_the_doubles_market_still_links_to_its_doubles_row(self):
        """Control: the gate did not stop linking doubles rows at all."""
        result = _score_candidates(
            [_event(15320104, DOUBLES_HOME, DOUBLES_AWAY)],
            extract_matchup(KALSHI_DOUBLES), _pm_market(KALSHI_DOUBLES), NOW,
        )
        assert result is not None and result["event_id"] == 15320104


# --------------------------------------------------------------------------
# A real session: Phase 1.5 and the group-sibling resolver
# --------------------------------------------------------------------------


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


def _rail():
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

    sport = Sport(key="tennis_other", name="tennis_other")
    session.add(sport)
    session.flush()
    return session, sport


def _row(session, sport, home, away):
    from app.models.models import Event

    row = Event(
        sport_id=sport.id, home_team_name=home, away_team_name=away,
        commence_time=DOUBLES_START, status="scheduled",
        commence_time_source="kalshi",
        event_tags=["provenance:source:kalshi", "provenance:unanchored"],
    )
    session.add(row)
    session.flush()
    return row


def _child(session, row, name, *, market_id=None):
    from app.models.models import FuturesMarket

    m = FuturesMarket(
        source="polymarket", external_id="0x" + str(abs(hash(name)))[:16],
        name=name, category="sports", status="open",
        event_id=row.id if row is not None else None,
        sport_id=row.sport_id if row is not None else None,
        llm_sport_category="tennis", group_id=GROUP,
        group_type="polymarket_sub_market",
        market_metadata={"venue_game_start": DOUBLES_START.isoformat()},
    )
    if market_id is not None:
        m.id = market_id
    session.add(m)
    session.commit()
    return m


async def _run_phase15(session):
    stats = {
        "orphaned_snapshots_deleted": 0,
        "funnel": {"stale_relinked": 0, "mislink_fixed": 0},
    }
    link_changes = []
    with patch.object(
        pmm, "_find_matching_event", new=AsyncMock(return_value=None),
    ):
        await pmm._phase15_revalidate(
            _AsyncShim(session), stats, NOW, lambda: 600.0, link_changes,
        )
    session.commit()
    return stats, link_changes


@pytest.mark.asyncio
async def test_phase15_breaks_the_singles_leg_on_the_doubles_row():
    """🔴 THE SHIP, on the link already stored: the leg leaves the doubles row."""
    session, sport = _rail()
    row = _row(session, sport, DOUBLES_HOME, DOUBLES_AWAY)
    market = _child(session, row, PM_SINGLES_LEG)
    await _run_phase15(session)
    session.refresh(market)
    assert market.event_id != row.id, (
        "Phase 1.5 kept the singles O/U line on the doubles row"
    )


@pytest.mark.asyncio
async def test_phase15_keeps_the_doubles_market_on_its_row():
    """Control: the doubles row's own market is not broken."""
    session, sport = _rail()
    row = _row(session, sport, DOUBLES_HOME, DOUBLES_AWAY)
    market = _child(session, row, KALSHI_DOUBLES)
    _stats, link_changes = await _run_phase15(session)
    session.refresh(market)
    assert market.event_id == row.id
    assert not link_changes, f"a kept link published a move: {link_changes}"


class TestTheGroupSiblingResolver:
    """`_polymarket_group_sibling_event_id` — the join that reads no names."""

    @pytest.mark.asyncio
    async def test_a_singles_child_does_not_follow_its_siblings_onto_a_doubles_row(self):
        """🔴 The flap: Phase 1.5 unlinked the leg, the join put it back."""
        session, sport = _rail()
        doubles = _row(session, sport, DOUBLES_HOME, DOUBLES_AWAY)
        _child(session, doubles, PM_SINGLES_MONEYLINE)
        _child(session, doubles, "Set Handicap: Billy Harris (-1.5) vs Felix Balshaw (+1.5)")
        arriving = _child(session, None, PM_SINGLES_LEG)

        found = await pmm._polymarket_group_sibling_event_id(_AsyncShim(session), arriving)
        assert found is None, (
            f"the singles leg joined the doubles row {found} through its group"
        )

    @pytest.mark.asyncio
    async def test_the_singles_row_is_chosen_when_the_group_spans_both(self):
        session, sport = _rail()
        doubles = _row(session, sport, DOUBLES_HOME, DOUBLES_AWAY)
        singles = _row(session, sport, "Felix Balshaw", "Billy Harris")
        _child(session, doubles, PM_SINGLES_MONEYLINE)
        _child(session, singles, "Set 1 Winner: Billy Harris vs Felix Balshaw")
        arriving = _child(session, None, PM_SINGLES_LEG)

        found = await pmm._polymarket_group_sibling_event_id(_AsyncShim(session), arriving)
        assert found == singles.id

    @pytest.mark.asyncio
    async def test_a_singles_group_still_joins_its_singles_row(self):
        """Control: the join itself is untouched for the right shape."""
        session, sport = _rail()
        singles = _row(session, sport, "Felix Balshaw", "Billy Harris")
        _child(session, singles, PM_SINGLES_MONEYLINE)
        arriving = _child(session, None, PM_SINGLES_LEG)

        found = await pmm._polymarket_group_sibling_event_id(_AsyncShim(session), arriving)
        assert found == singles.id

    @pytest.mark.asyncio
    async def test_a_group_whose_titles_name_no_shape_keeps_its_row(self):
        """Handicap titles parse as neither shape: say nothing, refuse nothing."""
        session, sport = _rail()
        doubles = _row(session, sport, DOUBLES_HOME, DOUBLES_AWAY)
        _child(session, doubles, "Set Handicap: Billy Harris (-1.5) vs Felix Balshaw (+1.5)")
        arriving = _child(
            session, None, "Set Handicap: Felix Balshaw (-1.5) vs Billy Harris (+1.5)",
        )

        found = await pmm._polymarket_group_sibling_event_id(_AsyncShim(session), arriving)
        assert found == doubles.id


def test_the_group_shape_reads_every_parseable_title():
    assert pmm._group_pair_shape([PM_SINGLES_MONEYLINE, PM_SINGLES_LEG]) is False
    assert pmm._group_pair_shape([KALSHI_DOUBLES]) is True
    assert pmm._group_pair_shape(["Set Handicap: A (-1.5) vs B (+1.5)"]) is None
    # Titles that disagree give the group no shape — nothing is refused on a guess.
    assert pmm._group_pair_shape([PM_SINGLES_LEG, KALSHI_DOUBLES]) is None
