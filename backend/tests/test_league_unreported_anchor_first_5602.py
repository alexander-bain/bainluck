"""#5602, league page — the unreported rail's cap may not go to the claims first.

THE SPECIMEN, PRODUCTION 2026-09-30 09:4xZ
══════════════════════════════════════════
`GET /api/leagues/mma_mixed_martial_arts`, `unreported_games`. Five bouts of the
Sep 29 card, each two `suspended` rows::

    Kalshi claim (no id)          Odds API row (external_id)
    15319835  03:20Z  Abushaar    15320849  00:20Z
    15319836  03:00Z  Diop        15320967  23:55Z
    15319837  02:40Z  Escuza      15320966  23:40Z   "Ian Escuza wins"
    15319838  02:20Z  Bertolso    15320965  23:15Z
    15319839  02:00Z  Bulaid      15320964  23:15Z

`ORDER BY commence_time DESC LIMIT 7` admitted all five claims and two anchored
rows. The drain took 35/36 (their markets had moved to the anchored rows); 37,
38 and 39 printed "No result reported" and their anchored twins were never on
the page, so `_merge_combat_claim_bouts` (#7993) — which folds exactly this
pair — was handed one half of each. The feed had the same cut and #9760 fixed
it there with the same key used here.

`TestTheDefectReproduces` rebuilds the old ordering over this corpus. Without
it every assertion below could be passing over a slate that never cut.
"""

from __future__ import annotations

import inspect
from datetime import datetime, timezone

import pytest
from sqlalchemy import create_engine
from sqlalchemy.dialects import postgresql
from sqlalchemy.dialects.postgresql import ARRAY, JSONB
from sqlalchemy.ext.compiler import compiles
from sqlalchemy.orm import Session


@compiles(JSONB, "sqlite")
def _jsonb_on_sqlite(type_, compiler, **kw):  # pragma: no cover - DDL shim
    return "JSON"


@compiles(ARRAY, "sqlite")
def _array_on_sqlite(type_, compiler, **kw):  # pragma: no cover - DDL shim
    return "JSON"


from app.models import Event, Sport  # noqa: E402
from app.models.models import Base  # noqa: E402
from app.routes import league_futures  # noqa: E402
from app.routes.league_futures import (  # noqa: E402
    UNREPORTED_LIMIT,
    _folded_past_rails,
    _kickoff_order,
    unreported_games_query,
)

#: A fixed anchor (gotcha #44).
NOW = datetime(2026, 9, 30, 9, 45, tzinfo=timezone.utc)
LEAGUE = "mma_mixed_martial_arts"
S_MMA = 1


def _t(day, hour, minute):
    return datetime(2026, 9, day, hour, minute, tzinfo=timezone.utc)


#: (claim id, claim kick-off, anchor id, anchor kick-off, home, away)
BOUTS = [
    (15319835, _t(30, 3, 20), 15320849, _t(30, 0, 20), "Loai Abushaar", "George Staines"),
    (15319836, _t(30, 3, 0), 15320967, _t(29, 23, 55), "Adama Diop", "Zaurbek Sabanov"),
    (15319837, _t(30, 2, 40), 15320966, _t(29, 23, 40), "Ian Escuza", "Luca Borando"),
    (15319838, _t(30, 2, 20), 15320965, _t(29, 23, 15), "Aieza Bertolso", "Camila Reynoso"),
    (15319839, _t(30, 2, 0), 15320964, _t(29, 23, 15), "Ilias Bulaid", "Erick Visconde"),
]
CLAIMS = {b[0] for b in BOUTS}
ANCHORS = {b[2] for b in BOUTS}
ESCUZA_CLAIM, ESCUZA_ANCHOR = 15319837, 15320966


def _row(eid, when, home, away, external_id=None, source="kalshi"):
    return Event(
        id=eid,
        sport_id=S_MMA,
        external_id=external_id,
        home_team_name=home,
        away_team_name=away,
        commence_time=when,
        commence_time_source=source,
        status="suspended",
    )


def _corpus(session, bouts):
    session.add(Sport(id=S_MMA, key=LEAGUE, name="MMA"))
    for claim, c_when, anchor, a_when, home, away in bouts:
        session.add(_row(claim, c_when, home, away))
        session.add(
            _row(anchor, a_when, home, away, external_id=f"odds-{anchor}", source="odds_api")
        )
    session.commit()


@pytest.fixture
def session():
    eng = create_engine("sqlite://")
    Base.metadata.create_all(eng)
    with Session(eng) as s:
        _corpus(s, BOUTS)
        yield s


def _admitted(session, query):
    return list(session.execute(query).scalars().all())


def _old_query():
    """The pre-fix statement: the same builder with its ORDER BY replaced by the
    one it used to carry, `commence_time DESC` alone."""
    q = unreported_games_query(LEAGUE, NOW)
    fenced = q.get_final_froms()[0]
    return q.order_by(None).order_by(fenced.c.commence_time.desc())


class TestTheDefectReproduces:
    """🔴 RED-FIRST. The old ordering over this same corpus."""

    def test_newest_first_gives_the_cap_to_the_claims(self, session):
        ids = {e.id for e in _admitted(session, _old_query())}
        assert len(ids) == UNREPORTED_LIMIT + 1
        assert CLAIMS <= ids
        assert ESCUZA_ANCHOR not in ids, (
            "the corpus no longer reproduces the cut — every assertion below "
            "would be passing over a slate that never starved"
        )

    def test_so_the_fold_leaves_the_claim_printing(self, session):
        rows = _kickoff_order(_admitted(session, _old_query()))
        _, unreported, _ = _folded_past_rails([], rows, [])
        ids = {e.id for e in unreported}
        assert ESCUZA_CLAIM in ids and ESCUZA_ANCHOR not in ids


class TestAnchoredRowsAreAdmittedFirst:
    def test_every_anchored_row_makes_the_cap(self, session):
        ids = {e.id for e in _admitted(session, unreported_games_query(LEAGUE, NOW))}
        assert ANCHORS <= ids

    def test_claims_fill_what_is_left_newest_first(self, session):
        ids = [e.id for e in _admitted(session, unreported_games_query(LEAGUE, NOW))]
        assert set(ids[: len(ANCHORS)]) == ANCHORS
        assert ids[len(ANCHORS):] == [15319835, 15319836]

    def test_the_fold_now_keeps_the_graded_row_and_drops_the_claim(self, session):
        rows = _kickoff_order(_admitted(session, unreported_games_query(LEAGUE, NOW)))
        _, unreported, _ = _folded_past_rails([], rows, [])
        ids = {e.id for e in unreported}
        assert ESCUZA_ANCHOR in ids
        assert ESCUZA_CLAIM not in ids
        assert ids.isdisjoint(CLAIMS), f"a claim still prints beside its bout: {ids & CLAIMS}"

    def test_the_rail_still_reads_in_kickoff_order(self, session):
        rows = _kickoff_order(_admitted(session, unreported_games_query(LEAGUE, NOW)))
        kickoffs = [e.commence_time for e in rows]
        assert kickoffs == sorted(kickoffs, reverse=True)
        assert rows[0].id == 15319835, "the newest row no longer leads the rail"


class TestInertWhereNothingIsAnchored:
    """Both directions (gotcha #43): a rail of claims alone is admitted exactly
    as before — the key is a constant there."""

    def test_claims_only_rail_is_unchanged(self):
        eng = create_engine("sqlite://")
        Base.metadata.create_all(eng)
        with Session(eng) as s:
            s.add(Sport(id=S_MMA, key=LEAGUE, name="MMA"))
            for i in range(10):
                s.add(_row(900 + i, _t(29, 10 + i, 0), f"A{i} Aa", f"B{i} Bb"))
            s.commit()
            new = [e.id for e in _admitted(s, unreported_games_query(LEAGUE, NOW))]
            old = [e.id for e in _admitted(s, _old_query())]
        assert new == old == [909, 908, 907, 906, 905, 904, 903]


class TestShape:
    def test_the_anchor_key_leads_the_outer_order_and_stays_outside_the_fence(self):
        sql = str(
            unreported_games_query(LEAGUE, NOW).compile(dialect=postgresql.dialect())
        )
        inside, outside = sql.rsplit("OFFSET", 1)
        assert "ORDER BY" not in inside, "the ORDER BY was pushed inside the fence"
        assert "espn_id IS NOT NULL" not in inside, "the key was pushed inside the fence"
        order = outside.split("ORDER BY", 1)[1]
        assert order.lstrip().startswith("CASE WHEN")
        assert "espn_id IS NOT NULL" in order and "external_id IS NOT NULL" in order
        assert order.index("END") < order.index("commence_time DESC")

    def test_the_route_restores_kickoff_order_before_anything_counts(self):
        source = inspect.getsource(league_futures)
        fetch = source.index("_u_events = list(_u.scalars().all())")
        reorder = source.index("_u_events = _kickoff_order(_u_events)")
        fold = source.index("_folded_past_rails(\n            _r_events")
        assert fetch < reorder < fold
