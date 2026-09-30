"""#8072 follow-up (CERT-3801: 8072-STEP0-CONFERENCE-ADMISSION-GUARD).

Step 0 binds a Kalshi outcome inside the league its ticker names (#9617). It ran
BEFORE `_admit`, so the conference check #8072 added at every other bind site did
not cover it. No production board shows the gap today. The shape it guards is an
outcome whose venue data contradicts its ticker: "Los Angeles" on KXMLBAL-26,
the American League champion board, where the only Los Angeles club in the
league rows is the Dodgers (National League). Step 0 matches it to the Dodgers by
city; the conference check refuses the bind.
"""

from __future__ import annotations

from sqlalchemy.orm import Session

from app.models.models import FuturesOutcome
from tests.test_team_link_conference_8072 import (
    ATHLETICS,
    DODGERS,
    _drain,
    _links,
    _make_engine,
    _seed,
)


def _add(session: Session, oid: int, market_id: int, name: str) -> None:
    session.add(FuturesOutcome(id=oid, market_id=market_id, external_id=f"o{oid}", name=name))
    session.commit()


def test_step0_refuses_a_city_bind_into_the_other_conference():
    with Session(_make_engine()) as session:
        _seed(session)
        _add(session, 20, 213, "Los Angeles")  # the Dodgers by city, on the AL board
        stats = _drain(session)
        links = _links(session)

    assert links[20] != DODGERS[0]
    # Without the guard Step 0 binds it and the same run's Phase 3b clears it
    # again, so the final link alone cannot tell the two apart; the counts can.
    # Guarded: it is refused at the bind (Step 0, then Step 1's name match), so
    # Phase 3b finds only the seed's three stored crossings (1, 2, 3).
    assert stats["links_outside_market_conference"] == 3
    assert stats["outcomes_unlinked_outside_market_conference"] == 2  # the seed's 1 and 2
    assert stats["outcomes_refused_outside_market_conference"] == 3  # 8, and 20 twice


def test_step0_still_binds_inside_the_conference():
    # Control: an AL club on the AL board still binds through Step 0.
    with Session(_make_engine()) as session:
        _seed(session)
        _add(session, 21, 213, "Athletics")
        stats = _drain(session)
        links = _links(session)

    assert links[21] == ATHLETICS[0]
    assert stats["outcomes_linked_by_league"] >= 1
