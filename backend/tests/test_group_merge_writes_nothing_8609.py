"""#8609 — the group merge on the themed dashboards must not write.

`/politics` read "Failed to load politics data" from 2026-09-22 23:25Z: every
`GET /api/politics` raised `uq_outcome_market_external` during autoflush.
`group_markets_by_group_id` attached a sibling's outcomes to the representative
with `representative.outcomes = merged`, on a LIVE ORM row. That reparents each
borrowed outcome, and the next query's autoflush sent the UPDATE. Polymarket
group `polymarket:1061741` ("Republican Senate odds hit __ by October 31?")
carries the parent 61876974 with rung "↑ 45%" and a sub-market 61891079 whose
"45%" rung has the SAME external_id. The name dedupe borrows it (the labels
differ) and the UPDATE collides.

Every earlier test of this helper used SimpleNamespace markets, which have no
session and so could never flush. These run the production specimen's shape
through a real SQLAlchemy session and a real unique constraint.
"""

from __future__ import annotations

import pytest
from sqlalchemy import create_engine, event, select
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.compiler import compiles
from sqlalchemy.orm import Session, selectinload

from app.models import FuturesMarket, FuturesOutcome
from app.utils.cross_source_matching import group_markets_by_group_id

GROUP = "polymarket:1061741"
SHARED_EXT = "0xe95f14e0db9837856e3c8c01e9a191e81e0327839df77ef012569d14ed8664c4"
PARENT_ID = 61876974
SUB_ID = 61891079


@compiles(JSONB, "sqlite")
def _jsonb_as_json(_type, _compiler, **_kw):  # pragma: no cover - DDL shim
    return "JSON"


@pytest.fixture()
def session():
    engine = create_engine("sqlite://")
    FuturesMarket.__table__.create(engine)
    FuturesOutcome.__table__.create(engine)
    with Session(engine) as s:
        s.add_all(
            [
                FuturesMarket(
                    id=PARENT_ID,
                    source="polymarket",
                    external_id="1061741",
                    name="Republican Senate odds hit __ by October 31?",
                    category="politics",
                    group_id=GROUP,
                    status="open",
                ),
                FuturesMarket(
                    id=SUB_ID,
                    source="polymarket",
                    external_id="sub-45",
                    name="Republican Senate odds hit 45% by October 31?",
                    category="politics",
                    group_id=GROUP,
                    status="open",
                ),
            ]
        )
        s.flush()
        s.add_all(
            [
                FuturesOutcome(
                    id=1, market_id=PARENT_ID, external_id=SHARED_EXT, name="↑ 45%"
                ),
                FuturesOutcome(
                    id=2, market_id=PARENT_ID, external_id="ext-40", name="↑ 40%"
                ),
                FuturesOutcome(
                    id=3, market_id=SUB_ID, external_id=SHARED_EXT, name="45%"
                ),
            ]
        )
        s.commit()
        yield s


def _load(s: Session) -> list[FuturesMarket]:
    return list(
        s.execute(
            select(FuturesMarket)
            .options(selectinload(FuturesMarket.outcomes))
            .order_by(FuturesMarket.id)
        )
        .scalars()
        .all()
    )


def _owners(s: Session) -> dict[int, int]:
    return dict(s.execute(select(FuturesOutcome.id, FuturesOutcome.market_id)).all())


def test_control_the_old_assignment_autoflushes_into_the_unique_key(session):
    """Strawman: the pre-fix line, on the production specimen, reproduces the 500."""
    markets = _load(session)
    parent = next(m for m in markets if m.id == PARENT_ID)
    sub = next(m for m in markets if m.id == SUB_ID)
    parent.outcomes = list(parent.outcomes) + list(sub.outcomes)
    with pytest.raises(IntegrityError, match="futures_outcomes"):
        # The route's next query (politics.py presidential history).
        session.execute(select(FuturesOutcome.id)).all()


def test_the_next_query_after_grouping_does_not_raise(session):
    grouped = group_markets_by_group_id(_load(session))
    # This is the query that raised in production.
    session.execute(select(FuturesOutcome.id)).all()
    assert [m.id for m in grouped] == [PARENT_ID]


def test_the_view_still_carries_the_merged_outcome_set(session):
    (rep,) = group_markets_by_group_id(_load(session))
    assert sorted(o.name for o in rep.outcomes) == ["45%", "↑ 40%", "↑ 45%"]


def test_the_session_holds_nothing_to_write(session):
    statements: list[str] = []
    event.listen(
        session.get_bind(),
        "before_cursor_execute",
        lambda _c, _cur, stmt, *_a: statements.append(stmt),
    )
    group_markets_by_group_id(_load(session))
    assert not session.dirty and not session.new and not session.deleted
    session.flush()
    session.commit()
    writes = [
        s
        for s in statements
        if s.lstrip().upper().startswith(("UPDATE", "INSERT", "DELETE"))
    ]
    assert writes == []
    # Every outcome still belongs to the market that owns it in the database.
    assert _owners(session) == {1: PARENT_ID, 2: PARENT_ID, 3: SUB_ID}


def test_a_sibling_with_no_collision_is_not_moved_either(session):
    """The latent half on /economics, /entertainment, /weather: no collision, still no write."""
    session.add(
        FuturesOutcome(id=4, market_id=SUB_ID, external_id="ext-55", name="55%")
    )
    session.commit()
    (rep,) = group_markets_by_group_id(_load(session))
    assert "55%" in {o.name for o in rep.outcomes}
    session.commit()
    assert _owners(session)[4] == SUB_ID
