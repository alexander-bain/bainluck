"""Tomic v Sun shows only Tomic v Sun's prices — #9584.

**SHIP: the Tomic v Sun page (15320530) stops showing another match's prices —
"Yingqun Sun vs Junlu Sun — Yingqun Sun wins Set 1 >99%" under its Additional
Markets — and a match whose two players share a surname is never filed on a row
that names that surname once.** (Pillar: MATCHING.)

The two-sided name gate asked each market name, on its own, "do you match home
or away?". Polymarket's W15 Maanshan legs are "Sun vs. Sun" (Yingqun Sun v
Junlu Sun), so both halves matched the single ``Sun`` of ``Tomic v Sun`` and the
gate passed. Production, ``market_match_receipts`` 2026-09-29:

    63199205  Sun vs. Sun: Set 1 Games O/U 8.5
              pass3_backlog linked -> 15320530 (Tomic v Sun), sides_matched 2
              runner-up 15320683 (Lys v Sun) passed the same gate, scored lower

and the rest of group ``polymarket:1098150`` followed it onto the row — six legs
of a different match, and a second fixture clock (03:30Z against Tomic's 08:30Z)
that left #9418's refresher holding the row.

WHAT EACH TEST DEFENDS:
* the pure helper — opposite sides required, either orientation, the
  one-name-matches-both-sides case still passes;
* the forward scorer refuses the specimen and still links Tomic's own line;
* Phase 1.5 breaks the specimen link that is already there, and keeps
  Tomic's own line (the #9472 tennis arm cannot re-accept it either);
* 🔴 every copy of the two-sided gate goes through the helper.
"""

from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest
from sqlalchemy.dialects.postgresql import ARRAY, JSONB
from sqlalchemy.ext.compiler import compiles

from app.tasks.prediction_market_matching import _score_candidates
from app.utils.prediction_market_matching import (
    _names_both_sides,
    extract_matchup,
)


@compiles(JSONB, "sqlite")
def _jsonb_on_sqlite(type_, compiler, **kw):  # pragma: no cover - DDL shim
    return "TEXT"


@compiles(ARRAY, "sqlite")
def _array_on_sqlite(type_, compiler, **kw):  # pragma: no cover - DDL shim
    return "TEXT"


SPECIMEN = "Sun vs. Sun: Set 1 Games O/U 8.5"
TOMIC_OWN = "Tomic vs. Sun: Match O/U 22.5"
TOMIC_START = datetime(2026, 9, 29, 3, 0, tzinfo=timezone.utc)
NOW = datetime(2026, 9, 29, 8, 29, tzinfo=timezone.utc)


# --------------------------------------------------------------------------
# The pure helper
# --------------------------------------------------------------------------


class TestNamesBothSides:
    def test_two_names_on_the_same_side_do_not_pass(self):
        assert not _names_both_sides("Sun", "Sun", "Tomic", "Sun")
        assert not _names_both_sides("Sun", "Sun", "Lys", "Sun")

    def test_the_full_names_of_the_other_match_do_not_pass(self):
        assert not _names_both_sides(
            "Yingqun Sun", "Junlu Sun", "Bernard Tomic", "Fajing Sun",
        )

    def test_the_rows_own_players_pass_in_either_orientation(self):
        assert _names_both_sides("Tomic", "Sun", "Tomic", "Sun")
        assert _names_both_sides("Sun", "Tomic", "Tomic", "Sun")

    def test_a_name_matching_both_sides_still_passes_with_its_opponent(self):
        # "New York" reaches both clubs; its opponent fixes the assignment.
        assert _names_both_sides(
            "New York", "Nets", "New York Knicks", "Brooklyn Nets",
        )

    def test_the_old_either_side_gate_really_did_pass_the_specimen(self):
        """🔴 Strawman: the per-name test this replaces said yes."""
        from app.utils.prediction_market_matching import _fuzzy_team_match

        def old(a, b, h, w):
            return (
                (_fuzzy_team_match(a, h) or _fuzzy_team_match(a, w))
                and (_fuzzy_team_match(b, h) or _fuzzy_team_match(b, w))
            )

        assert old("Sun", "Sun", "Tomic", "Sun")
        assert not _names_both_sides("Sun", "Sun", "Tomic", "Sun")


# --------------------------------------------------------------------------
# The forward scorer
# --------------------------------------------------------------------------


def _event(eid, home, away, sport_key, commence):
    return SimpleNamespace(
        id=eid,
        sport=SimpleNamespace(key=sport_key),
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


def _rows():
    return [
        _event(15320530, "Tomic", "Sun", "tennis_other", TOMIC_START),
        _event(
            15320683, "Lys", "Sun", "tennis_wta",
            datetime(2026, 9, 30, 3, 0, tzinfo=timezone.utc),
        ),
    ]


class TestTheForwardScorer:
    def test_the_specimen_parses_to_one_surname_twice(self):
        m = extract_matchup(SPECIMEN)
        assert m is not None and (m.team_a, m.team_b) == ("Sun", "Sun")

    def test_sun_vs_sun_links_to_neither_sun_row(self):
        """🔴 THE SHIP. The receipt chose 15320530; now nothing is chosen."""
        result = _score_candidates(
            _rows(), extract_matchup(SPECIMEN), _pm_market(SPECIMEN), NOW,
        )
        assert result is None, (
            f"'Sun vs. Sun' linked to {result and result['event_id']} — "
            "a different match's prices land on that page"
        )

    def test_tomics_own_line_still_links_to_his_row(self):
        """Control: the gate did not stop linking this row at all."""
        result = _score_candidates(
            _rows(), extract_matchup(TOMIC_OWN), _pm_market(TOMIC_OWN), NOW,
        )
        assert result is not None and result["event_id"] == 15320530


# --------------------------------------------------------------------------
# Phase 1.5 — the link already on production
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
    row = Event(
        sport_id=sport.id, home_team_name="Tomic", away_team_name="Sun",
        commence_time=TOMIC_START, status="scheduled",
        commence_time_source="kalshi",
        event_tags=["provenance:source:kalshi", "provenance:unanchored"],
    )
    session.add(row)
    session.flush()
    return session, row


def _linked(session, row, name, group):
    from app.models.models import FuturesMarket

    m = FuturesMarket(
        source="polymarket", external_id="0x" + str(abs(hash(name)))[:16],
        name=name, category="sports", status="open", event_id=row.id,
        sport_id=row.sport_id, llm_sport_category="tennis", group_id=group,
    )
    session.add(m)
    session.commit()
    return m


async def _run_phase15(session):
    from app.tasks import prediction_market_matching as task_mod

    stats = {
        "orphaned_snapshots_deleted": 0,
        "funnel": {"stale_relinked": 0, "mislink_fixed": 0},
    }
    link_changes = []
    with patch.object(
        task_mod, "_find_matching_event", new=AsyncMock(return_value=None),
    ):
        await task_mod._phase15_revalidate(
            _AsyncShim(session), stats, NOW, lambda: 600.0, link_changes,
        )
    session.commit()
    return stats, link_changes


@pytest.mark.asyncio
async def test_phase15_breaks_the_sun_vs_sun_link_on_tomic_v_sun():
    """🔴 THE SHIP, on the link already stored: the leg leaves Tomic's row."""
    session, row = _rail()
    market = _linked(session, row, SPECIMEN, "polymarket:1098150")
    await _run_phase15(session)
    session.refresh(market)
    assert market.event_id != row.id, (
        "Phase 1.5 kept 'Sun vs. Sun' on Tomic v Sun — the W15 Set 1 line "
        "stays under Tomic's Additional Markets"
    )


@pytest.mark.asyncio
async def test_phase15_keeps_tomics_own_line():
    """Control: Tomic's own leg is not broken by the stricter test."""
    session, row = _rail()
    market = _linked(session, row, TOMIC_OWN, "polymarket:1092875")
    _stats, link_changes = await _run_phase15(session)
    session.refresh(market)
    assert market.event_id == row.id
    assert not link_changes, f"a kept link published a move: {link_changes}"


# --------------------------------------------------------------------------
# 🔴 Every copy of the gate
# --------------------------------------------------------------------------


def test_no_two_sided_gate_asks_each_name_on_its_own():
    """The four copies (scorer, Phase 1.5, two relink arms) use the helper.

    A per-name ``(match home or away) and (match home or away)`` anywhere in
    the matcher re-opens #9584 on that arm, so the source is read whole.
    """
    src = (
        Path(__file__).resolve().parents[1]
        / "app" / "tasks" / "prediction_market_matching.py"
    ).read_text()
    assert "_fuzzy_team_match(matchup.team_b" not in src
    assert src.count("_names_both_sides(") >= 4


# --------------------------------------------------------------------------
# The hand unlink that clears the two legs Phase 1.5 cannot parse
# --------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_admin_unlink_takes_only_the_unlinked_markets_rows():
    """🔴 Unlinking a W15 leg keeps Tomic's own Polymarket line.

    "W15 Maanshan: Yingqun Sun vs Junlu Sun" and "Set 1 Winner: …" do not
    parse, so Phase 1.5 never checks them and a hand unlink is how they leave.
    The endpoint deleted every Polymarket row on the event — #9504's defect,
    still in the admin tool — which would have erased Tomic's chart.
    """
    from app.models.models import WinProbSnapshot
    from app.routes import admin_matching

    session, row = _rail()
    tomic = _linked(session, row, TOMIC_OWN, "polymarket:1092875")
    w15 = _linked(
        session, row, "Set 1 Winner: Yingqun Sun vs Junlu Sun",
        "polymarket:1098150",
    )
    for market, n in ((tomic, 3), (w15, 2)):
        for i in range(n):
            session.add(WinProbSnapshot(
                event_id=row.id, source="polymarket",
                captured_at=datetime(2026, 9, 29, 3, i, tzinfo=timezone.utc),
                home_win_probability=0.6, away_win_probability=0.4,
                game_state={"market_id": market.id},
            ))
    session.commit()

    with patch.object(admin_matching, "_check_admin_destructive"), patch(
        "app.utils.match_receipts.record_link_change_receipts",
        new=AsyncMock(return_value=1),
    ):
        out = await admin_matching.unlink_prediction_market(
            request=None, secret="x", market_id=w15.id, db=_AsyncShim(session),
        )

    session.refresh(w15)
    assert w15.event_id is None and out["snapshots_deleted"] == 2
    left = session.query(WinProbSnapshot).filter_by(
        event_id=row.id, source="polymarket",
    ).all()
    assert sorted(s.game_state["market_id"] for s in left) == [tomic.id] * 3, (
        "unlinking the W15 leg deleted Tomic's own Polymarket rows"
    )
